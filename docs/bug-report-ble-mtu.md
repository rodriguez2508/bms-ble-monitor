# Bug report: BLE readings lost due to notification fragmentation

Date: 2026-10-07
Scope: `src/modules/bms/infrastructure/adapters/bleak_bms_repository.py`
Status: diagnosed with evidence, fix pending

## Symptom

`/api/status` and `/api/history` return 200 (bug fixed in `6fd030b`), but
`connected` stays `false` and the history never grows: **not a single real
reading arrives from the BMS**. `get_latest_reading()` returns `None`
permanently.

## Root cause 1 — no MTU negotiation (and it can no longer be done with the current API)

The read requests `REG_STATUS_COUNT = 0x003B` = **59 registers**. The Modbus RTU
response measures:

```
slave(1) + func(1) + byteCount(1) + data(59*2=118) + CRC(2) = 123 bytes
```

The default ATT MTU is 23, so the maximum payload per notification is
**23 - 3 = 20 bytes**. One read therefore spans:

```
ceil(123 / 20) = 7 notifications
```

Verified in the environment with the installed version:

```
bleak 3.0.1
BleakClient -> methods: address, backend_id, connect, disconnect, is_connected,
              mtu_size, name, pair, read_gatt_char, services, start_notify,
              stop_notify, write_gatt_char, write_gatt_descriptor
request_mtu: DOES NOT EXIST
```

**`bleak` 3.0.1 removed `request_mtu`.** There is no public API to negotiate the
MTU. And the Linux BlueZ backend always returns the minimum:

```python
# bleak/backends/bluezdbus/client.py
@property
def mtu_size(self) -> int:
    if self._mtu_size is None:
        warnings.warn("Using default MTU value. Call _acquire_mtu() or set _mtu_size first ...")
        return 23
    return self._mtu_size
```

Conclusion: on Linux the MTU cannot be raised through a public API.
**Fragmentation is unavoidable and must be handled correctly.** MTU negotiation
becomes an optional optimization, not the fix.

## Root cause 2 — `handle_notify` mistakes a continuation for a header (THIS IS THE ONE THAT KILLS THE READ)

`ModbusCollector.handle_notify` (lines 27-43) decides whether a fragment is a
header by looking at the first two bytes:

```python
def handle_notify(self, _sender, data: bytearray) -> None:
    if len(data) >= 2 and data[0] == self.slave_addr and data[1] in (FUNC_READ, FUNC_READ | 0x80):
        self._buf = bytearray(data)      # <-- RESETS the buffer
    elif self._buf: self._buf.extend(data)
    else: return
    ...
```

The problem: **the payload also contains bytes that can match the header.** The
values are 16-bit big-endian integers, so a continuation fragment can start with
`01 03` or `01 83` without being a header. When that happens, the buffer is reset
mid-frame and **the whole reading is lost**.

### Reproduction

Since the header takes 3 bytes, the 20-byte boundaries fall on **odd** payload
offsets (17, 37, 57, 77, 97). `payload[17]` is the low byte of register 8 and
`payload[18]` the high byte of register 9. It is enough for register 8 to end in
`0x01` (e.g. a cell of **3.329 V** = `0x0D01`) and register 9 to start with
`0x03`:

```
frag@  0: 0x1 0x3     <- header, OK
frag@ 20: 0x1 0x3     <- RESETS THE BUFFER, everything lost

assembled frames: 0   (expected 1)
residual buffer: 103 bytes
RESULT: READING LOST -> request() times out after 6s and returns None
```

With synthetic data (payload `bytes(range(118))`) the bug does **not** reproduce.
That is why it goes unnoticed in tests and shows up "sometimes" in production: it
depends on the register values at that instant. With normal cell voltages
(3.2-3.4 V) the collision is frequent.

Consequence in the loop: `request()` does `wait_for(self._event.wait(), 6.0)`,
times out, returns `None`, and `start_polling` keeps saving nothing. Because the
residue is never cleared on timeout, the bug is self-perpetuating.

## Proposed fix

### 1. State-machine reassembly (mandatory)

Stop inferring "header or continuation" from the bytes. Use an explicit flag:

- `self._in_frame = False` initially.
- If we are **not** in a frame: require a header (`data[0] == slave_addr` and
  `data[1] in (0x03, 0x83)`), start the buffer, set `_in_frame = True`.
  If it is not a header, discard the fragment.
- If we **are** in a frame: **always accumulate**, never reset on a byte match.
- When complete (`len >= 5 + byte_count`): emit the frame, clear, `_in_frame = False`.
- Exception response (`0x83`): clear and go back to `_in_frame = False`.

### 2. Clear the buffer when the request times out

`request()` must drop the residue in the `except asyncio.TimeoutError` branch so a
lost frame does not contaminate the next one.

### 3. MTU as an optimization, with fallback

Try to negotiate the MTU if the backend exposes it somehow, measuring the result
with `mtu_size`; if it cannot (current BlueZ case), **continue with fragmentation
without failing**. No MTU path may bring the read down. Comment clearly that on
Linux the effective MTU is 23 and that the design must assume fragmentation.

## Acceptance criteria

1. A 123-byte frame split into 7 notifications of 20 **is assembled once**, even
   if a continuation fragment starts with `01 03` or `01 83`
   (use the reproduction values: reg8=`0x0D01`, reg9=`0x0383`).
2. Several consecutive frames on the same channel are all read, with no residue
   between them.
3. A garbage fragment without a header is discarded without breaking the state.
4. After a timeout, the next valid frame is assembled just the same (no
   contamination).
5. The MTU is queried but its failure breaks nothing.
6. Test with `ModbusCollector` **without BLE**: call `handle_notify` by hand with
   a `bytearray`, with no hardware and no network.

## Out of scope

- Do not touch `_parse_status`, `_build_read_cmd`, `_crc_modbus` or the register
  mapping.
- Do not touch the Flask view or the CQRS handlers.
- Do not refactor the architecture.
- The RSSI of -88 dBm and the CRC validation of the Modbus response are separate
  bugs (tracked as #2 and #4 of plan `adc52f07`); do not mix them into this fix.
