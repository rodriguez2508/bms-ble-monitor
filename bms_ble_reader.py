#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor de batería LiFePO₄ (Gobel Power BMS) vía BLE - Protocolo Modbus RTU.
Dispositivo: AA:BB:CC:DD:EE:FF  (CDZG202512050020000327)

Protocolo: Modbus RTU sobre BLE
  TX UUID (write-without-response): 00002760-08c2-11e1-9073-0e8ac72e0001
  RX UUID (notify):                 00002760-08c2-11e1-9073-0e8ac72e0002
"""

import asyncio
import csv
import os
import struct
from datetime import datetime

from bleak import BleakClient, BleakScanner

MAC = "AA:BB:CC:DD:EE:FF"
UUID_TX = "00002760-08c2-11e1-9073-0e8ac72e0001"  # write-without-response
UUID_RX = "00002760-08c2-11e1-9073-0e8ac72e0002"  # notify

# Modbus RTU constants
SLAVE_ADDR  = 0x01
FUNC_READ   = 0x03

# Register maps
REG_STATUS_START  = 0x0000
REG_STATUS_COUNT  = 0x003B  # 59 holding registers

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)


def crc_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def build_read_cmd(slave: int, start: int, count: int) -> bytes:
    payload = bytes([slave, FUNC_READ]) + struct.pack(">HH", start, count)
    return payload + struct.pack("<H", crc_modbus(payload))


def parse_status(data: bytes) -> dict:
    """Parse Modbus response payload (registers, big-endian, 2B each)."""
    def reg(offset):
        return struct.unpack_from(">H", data, offset * 2)[0]

    def reg_signed(offset):
        return struct.unpack_from(">h", data, offset * 2)[0]

    result = {
        "current_A":      reg_signed(0) / 100,
        "voltage_V":      reg(1) / 100,
        "soc_pct":        reg(2),
        "soh_pct":        reg(3),
        "cap_remain_Ah":  reg(4) / 100,
        "cap_design_Ah":  reg(5) // 100,
        "cycles":         reg(7),
    }

    # Cell voltages start at register offset 35 / 2 = byte offset 70
    # Each cell = 2 bytes, up to 32 cells
    cell_count = reg(15) & 0xFF if len(data) > 31 else 0
    cells = []
    base = 35  # byte offset in data
    for i in range(min(cell_count, 32)):
        if base + i * 2 + 2 <= len(data):
            mv = struct.unpack_from(">H", data, base + i * 2)[0]
            cells.append(mv / 1000)
    result["cell_voltages_V"] = cells

    return result


def save_reading(name: str, value):
    path = os.path.join(DATA_DIR, f"{name}_history.csv")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow([ts, value])


class ModbusCollector:
    def __init__(self):
        self._buf = bytearray()
        self._event = asyncio.Event()
        self._frame: bytes | None = None

    def handle_notify(self, _sender, data: bytearray):
        if len(data) >= 2 and data[0] == SLAVE_ADDR and data[1] in (FUNC_READ, FUNC_READ | 0x80):
            self._buf = bytearray(data)
        elif self._buf:
            self._buf.extend(data)
        else:
            return  # unexpected

        if len(self._buf) < 5:
            return

        if self._buf[1] == (FUNC_READ | 0x80):
            print(f"  [!] Modbus error code: 0x{self._buf[2]:02X}")
            self._buf.clear()
            return

        expected = 5 + self._buf[2]  # addr+func+len + data + crc(2)
        if len(self._buf) >= expected:
            frame = bytes(self._buf[:expected])
            # Validate CRC
            calc = crc_modbus(frame[:-2])
            recv = struct.unpack_from("<H", frame, -2)[0]
            if calc == recv:
                self._frame = frame
                self._event.set()
            else:
                print(f"  [!] CRC mismatch: calc=0x{calc:04X} recv=0x{recv:04X}")
            self._buf.clear()

    async def request(self, client: BleakClient, cmd: bytes, timeout: float = 5.0) -> bytes | None:
        self._frame = None
        self._event.clear()
        await client.write_gatt_char(UUID_TX, cmd, response=False)
        try:
            await asyncio.wait_for(self._event.wait(), timeout)
        except asyncio.TimeoutError:
            return None
        return self._frame


async def main():
    print(f"[*] Buscando {MAC}...")
    device = await BleakScanner.find_device_by_address(MAC, timeout=10.0)
    if device is None:
        print("[-] Dispositivo no encontrado. Verifica que la batería esté encendida y cerca.")
        return

    collector = ModbusCollector()
    cmd_status = build_read_cmd(SLAVE_ADDR, REG_STATUS_START, REG_STATUS_COUNT)
    print(f"[*] CMD status: {cmd_status.hex()}")

    async with BleakClient(device, timeout=15.0) as client:
        print(f"[+] Conectado a {MAC}")
        await client.start_notify(UUID_RX, collector.handle_notify)

        iteration = 0
        while True:
            iteration += 1
            frame = await collector.request(client, cmd_status)

            if frame is None:
                print(f"[{iteration}] Sin respuesta (timeout)")
            else:
                payload = frame[3:-2]  # strip addr+func+len prefix and CRC
                print(f"[{iteration}] Raw payload ({len(payload)}B): {payload.hex()}")
                try:
                    status = parse_status(payload)
                    print(f"  Voltaje:   {status['voltage_V']:.2f} V")
                    print(f"  Corriente: {status['current_A']:.2f} A")
                    print(f"  SOC:       {status['soc_pct']} %")
                    print(f"  SOH:       {status['soh_pct']} %")
                    print(f"  Cap rem:   {status['cap_remain_Ah']:.2f} Ah")
                    print(f"  Ciclos:    {status['cycles']}")
                    if status['cell_voltages_V']:
                        print(f"  Celdas:    {[f'{v:.3f}V' for v in status['cell_voltages_V']]}")

                    save_reading("voltage",  status["voltage_V"])
                    save_reading("current",  status["current_A"])
                    save_reading("soc",      status["soc_pct"])
                except Exception as e:
                    print(f"  [!] Error parseando: {e}")

            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[-] Detenido por el usuario.")
