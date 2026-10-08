import asyncio

from src.modules.bms.infrastructure.adapters.bleak_bms_repository import (
    FUNC_READ,
    BleakBmsRepository,
    ModbusCollector,
)

# Real 123-byte status response captured from the BMS (4S LiFePO4, SoC 69%).
REAL_FRAME_HEX = (
    "0103760000053200450064164f2021232800860000000000000c0000000000c00000040cff0d00"
    "0d000cfc00000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000101350000000000000000000000000000000000000135ffff444e"
)

SLAVE = 0x01
BYTE_COUNT = 118  # 59 registers * 2 bytes


def build_frame(reg8: int = 0x0D01, reg9_high: int = 0x03) -> bytes:
    """Build a 123-byte Modbus RTU status response.

    Register 8 lives at payload[16:18] and register 9 at payload[18:20]. With the
    reproduction values (reg8=0x0D01, reg9 high byte=0x03) the 20-byte fragment that
    starts at frame offset 20 begins with ``01 03`` -- a false header.
    """
    payload = bytearray(BYTE_COUNT)
    payload[16] = (reg8 >> 8) & 0xFF
    payload[17] = reg8 & 0xFF
    payload[18] = reg9_high & 0xFF
    payload[19] = 0x00
    frame = bytes([SLAVE, FUNC_READ, BYTE_COUNT]) + bytes(payload) + b"\x00\x00"
    assert len(frame) == 123
    return frame


def feed_fragments(collector: ModbusCollector, frame: bytes, chunk: int = 20) -> None:
    for i in range(0, len(frame), chunk):
        collector.handle_notify(None, bytearray(frame[i:i + chunk]))


def test_reassembles_frame_even_when_continuation_looks_like_header():
    # Criterion 1: 123-byte frame in 7 notifications of 20 assembles exactly once,
    # even though the fragment at offset 20 starts with 01 03 (false header).
    collector = ModbusCollector(SLAVE)
    frame = build_frame(reg8=0x0D01, reg9_high=0x03)
    assert frame[20] == 0x01 and frame[21] == 0x03

    feed_fragments(collector, frame)

    assert collector._frame == frame
    assert collector._in_frame is False
    assert collector._buf == bytearray()


def test_consecutive_frames_are_all_read_without_residue():
    # Criterion 2: several frames on the same channel are all assembled cleanly.
    collector = ModbusCollector(SLAVE)
    first = build_frame(reg8=0x0D01, reg9_high=0x03)
    second = build_frame(reg8=0x0CFF, reg9_high=0x03)

    feed_fragments(collector, first)
    assert collector._frame == first
    assert collector._buf == bytearray()

    collector._frame = None  # request() resets the frame between reads
    feed_fragments(collector, second)
    assert collector._frame == second


def test_garbage_fragment_without_header_is_discarded():
    # Criterion 3: a stray fragment without a header must not break the state.
    collector = ModbusCollector(SLAVE)
    collector.handle_notify(None, bytearray(b"\xAA\xBB\xCC\xDD"))

    assert collector._frame is None
    assert collector._buf == bytearray()
    assert collector._in_frame is False

    frame = build_frame()
    feed_fragments(collector, frame)
    assert collector._frame == frame


def test_parse_status_reads_pack_and_cell_voltages():
    # The cell voltages start at register 16 (byte 32); a wrong offset reads misaligned
    # garbage (e.g. 64.512 V) instead of the real ~3.3 V per cell.
    repo = BleakBmsRepository()
    frame = bytes.fromhex(REAL_FRAME_HEX)
    reading = repo._parse_status(frame[3:-2])

    assert reading.voltage_v == 13.3
    assert reading.soc_pct == 69
    assert reading.cycles == 134
    assert [round(v, 3) for v in reading.cell_voltages_v] == [3.327, 3.328, 3.328, 3.324]


def test_disconnect_releases_the_ble_client():
    # On shutdown the active client must be disconnected, otherwise the BMS stays
    # connected, stops advertising and the next start reports "no encontrado".
    repo = BleakBmsRepository()

    class FakeClient:
        def __init__(self):
            self.is_connected = True
            self.disconnected = False

        async def disconnect(self):
            self.disconnected = True
            self.is_connected = False

    fake = FakeClient()
    repo._client = fake

    asyncio.run(repo.disconnect())

    assert fake.disconnected is True
    assert repo._client is None
    assert repo._is_connected is False


def test_request_timeout_clears_residual_so_next_frame_assembles():
    # Criterion 4: after a timeout the residual is dropped and the next frame is fine.
    collector = ModbusCollector(SLAVE)

    class FakeClient:
        async def write_gatt_char(self, *_args, **_kwargs):
            return None

    # Simulate a partial frame already buffered before the request times out.
    collector.handle_notify(None, bytearray([SLAVE, FUNC_READ, BYTE_COUNT] + [0] * 10))
    assert collector._in_frame is True

    result = asyncio.run(collector.request(FakeClient(), b"\x00", timeout=0.05))

    assert result is None
    assert collector._in_frame is False
    assert collector._buf == bytearray()

    frame = build_frame()
    feed_fragments(collector, frame)
    assert collector._frame == frame
