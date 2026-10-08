import asyncio
import csv
import os
import struct
import threading
from datetime import datetime
from typing import Optional, List

from bleak import BleakClient, BleakScanner, BleakError
from src.modules.bms.domain.ports.bms_repository import BmsRepository
from src.modules.bms.domain.models.reading import BmsReading
from src.modules.shared.infrastructure.config.config import config

UUID_TX = "00002760-08c2-11e1-9073-0e8ac72e0001"
UUID_RX = "00002760-08c2-11e1-9073-0e8ac72e0002"
FUNC_READ = 0x03
REG_STATUS_START = 0x0000
REG_STATUS_COUNT = 0x003B

class ModbusCollector:
    """Reassembles a Modbus RTU response that BLE delivers fragmented.

    On Linux the ATT MTU is 23, so the usable payload per notification is 20 bytes.
    A status response is 123 bytes (slave+func+byteCount+118 data+CRC), therefore it
    arrives split across ~7 notifications. We MUST NOT guess "header vs continuation"
    from the bytes, because payload values can also look like a header (e.g. 01 03).
    """

    def __init__(self, slave_addr):
        self.slave_addr = slave_addr
        self._buf: bytearray = bytearray()
        self._event: asyncio.Event = asyncio.Event()
        self._frame: bytes | None = None
        self._in_frame: bool = False

    def _reset(self) -> None:
        self._buf = bytearray()
        self._in_frame = False

    def handle_notify(self, _sender, data: bytearray) -> None:
        # Explicit state machine: only a real header starts a frame. Once in frame we
        # always accumulate; we never restart the buffer on a byte coincidence.
        if not self._in_frame:
            if len(data) >= 2 and data[0] == self.slave_addr and data[1] in (FUNC_READ, FUNC_READ | 0x80):
                self._buf = bytearray(data)
                self._in_frame = True
            else:
                return  # stray fragment without header -> discard
        else:
            self._buf.extend(data)

        if len(self._buf) < 5:
            return
        # Modbus exception response (0x83): reset and wait for the next header.
        if self._buf[1] == (FUNC_READ | 0x80):
            self._reset()
            return

        expected = 5 + self._buf[2]
        if len(self._buf) < expected:
            return

        self._frame = bytes(self._buf[:expected])
        self._event.set()
        self._reset()

    async def request(self, client, cmd: bytes, timeout: float = 5.0) -> bytes | None:
        self._frame = None
        self._event.clear()
        self._reset()  # start each request with a clean reassembly state
        await client.write_gatt_char(UUID_TX, cmd, response=False)
        try:
            await asyncio.wait_for(self._event.wait(), timeout)
        except asyncio.TimeoutError:
            self._reset()  # drop residual so a lost frame does not contaminate the next one
            return None
        return self._frame

class BleakBmsRepository(BmsRepository):
    def __init__(self):
        self._latest_reading: Optional[BmsReading] = None
        self._is_connected = False
        self._lock = threading.Lock()
        self._stop_event = asyncio.Event()
        self._client: Optional[BleakClient] = None

    async def connect(self) -> bool: return True

    def request_stop(self) -> None:
        # Signal the polling loop to stop. Call it on the BLE event loop
        # (e.g. via loop.call_soon_threadsafe) since asyncio.Event is not thread-safe.
        self._stop_event.set()

    async def disconnect(self) -> None:
        # Release the BLE link so the BMS resumes advertising; otherwise it stays
        # connected and the next start fails to find it ("no encontrado").
        self._stop_event.set()
        client = self._client
        if client is not None:
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception as e:
                print(f"[BLE] Error al desconectar: {type(e).__name__}: {e!r}")
        self._client = None
        self._is_connected = False

    async def get_latest_reading(self) -> Optional[BmsReading]:
        with self._lock: return self._latest_reading

    async def get_history(self, metric: str, limit: int) -> List[dict]:
        filename_map = {"voltage": "voltage_history.csv", "current": "current_history.csv", "soc": "soc_history.csv"}
        filename = filename_map.get(metric)
        if not filename: return []
        if limit <= 0: return []
        path = os.path.join(config.DATA_DIR, filename)
        points = []
        if os.path.exists(path):
            with open(path, newline="") as f:
                rows = list(csv.reader(f))
            for row in rows[-limit:]:
                try:
                    ts, val = row
                except ValueError:
                    continue
                try:
                    points.append({"ts": ts, "value": float(val)})
                except ValueError:
                    continue
        return points

    def _crc_modbus(self, data: bytes) -> int:
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 0x0001: crc = (crc >> 1) ^ 0xA001
                else: crc >>= 1
        return crc

    def _build_read_cmd(self, slave: int, start: int, count: int) -> bytes:
        payload = bytes([slave, FUNC_READ]) + struct.pack(">HH", start, count)
        return payload + struct.pack("<H", self._crc_modbus(payload))

    def _parse_status(self, data: bytes) -> BmsReading:
        def reg(offset: int) -> int: return struct.unpack_from(">H", data, offset * 2)[0]
        def reg_signed(offset: int) -> int: return struct.unpack_from(">h", data, offset * 2)[0]
        cells = []
        cell_count = reg(15) & 0xFF if len(data) > 31 else 0
        base = 32  # cell voltages start at register 16 (byte 32), big-endian millivolts
        for i in range(min(cell_count, 32)):
            if base + i * 2 + 2 <= len(data):
                mv = struct.unpack_from(">H", data, base + i * 2)[0]
                cells.append(mv / 1000)
        return BmsReading(current_a=reg_signed(0) / 100, voltage_v=reg(1) / 100, soc_pct=reg(2), soh_pct=reg(3), cap_remain_ah=reg(4) / 100, cap_design_ah=reg(5) / 100, cycles=reg(7), cell_voltages_v=cells)

    def _save_reading(self, name: str, value: float):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        path = os.path.join(config.DATA_DIR, f"{name}_history.csv")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", newline="") as f: csv.writer(f).writerow([ts, value])

    async def start_polling(self):
        cmd = self._build_read_cmd(config.BMS_SLAVE_ADDR, REG_STATUS_START, REG_STATUS_COUNT)
        backoff = 5
        while not self._stop_event.is_set():
            try:
                print(f"[BLE] Buscando {config.BMS_MAC_ADDRESS}...")
                device = await BleakScanner.find_device_by_address(config.BMS_MAC_ADDRESS, timeout=15.0)
                if not device: raise BleakError("BMS no encontrado")
                collector = ModbusCollector(config.BMS_SLAVE_ADDR)
                async with BleakClient(device, timeout=20.0) as client:
                    self._client = client
                    print(f"[BLE] Conectado a BMS BUKUNGO")
                    # MTU is best-effort only: on Linux/bleak 3.0.1 it cannot be negotiated
                    # (request_mtu was removed, BlueZ reports 23). Its failure must never
                    # break the read path -- fragmentation is handled by ModbusCollector.
                    try:
                        mtu = getattr(client, "mtu_size", None)
                        print(f"[BLE] MTU efectivo: {mtu} (fragmentacion asumida)")
                    except Exception as mtu_err:
                        print(f"[BLE] MTU no disponible ({type(mtu_err).__name__}); continuo con fragmentacion")
                    await client.start_notify(UUID_RX, collector.handle_notify)
                    self._is_connected = True
                    backoff = 5
                    while self._is_connected and not self._stop_event.is_set():
                        frame = await collector.request(client, cmd, timeout=6.0)
                        if frame:
                            payload = frame[3:-2]
                            reading = self._parse_status(payload)
                            with self._lock: self._latest_reading = reading
                            self._save_reading("voltage", reading.voltage_v)
                            self._save_reading("current", reading.current_a)
                            self._save_reading("soc",     reading.soc_pct)
                        await asyncio.sleep(config.BMS_POLLING_INTERVAL)
                # Reached only when the with-block exits cleanly (client disconnected).
                self._client = None
                self._is_connected = False
            except Exception as e:
                print(f"[BLE] Error: {type(e).__name__}: {e!r}. Reintentando en {backoff}s...")
                self._is_connected = False
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
