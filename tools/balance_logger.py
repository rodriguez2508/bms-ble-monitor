#!/usr/bin/env python3
"""Read-only logger for a full charge/discharge cycle.

Goal: capture, over time, the raw balancing-related registers so we can see
*when* (if ever) this firmware activates cell balancing. The published 2017
PACE map says balancing starts at 3.4 V/cell with a 30 mV delta, but the live
firmware never seems to honor it. Logging cells + reg12/reg13 + current across
a real cycle is the only way to know for sure.

STRICTLY READ-ONLY: only Modbus function 0x03 (read holding registers) is ever
sent. No coil/register writes, no config changes.

Usage:
    PYTHONPATH=. python3 tools/balance_logger.py --interval 30

The BLE link is exclusive, so stop the web server before running this.
Stop the logger with Ctrl+C.
"""

import argparse
import asyncio
import os
import signal
import struct
from datetime import datetime

from bleak import BleakClient, BleakScanner, BleakError

from src.modules.bms.infrastructure.adapters.bleak_bms_repository import (
    BleakBmsRepository,
    ModbusCollector,
    UUID_RX,
    REG_STATUS_START,
    REG_STATUS_COUNT,
)
from src.modules.bms.infrastructure.adapters.balance_log import BalanceLog
from src.modules.shared.infrastructure.config.config import config


async def run(interval: int, out_path: str) -> None:
    repo = BleakBmsRepository()
    log = BalanceLog(out_path, config.BALANCE_LOG_RETENTION_H)
    cmd = repo._build_read_cmd(config.BMS_SLAVE_ADDR, REG_STATUS_START, REG_STATUS_COUNT)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    backoff = 5
    while not stop.is_set():
        try:
            print(f"[LOG] Buscando {config.BMS_MAC_ADDRESS}...")
            device = await BleakScanner.find_device_by_address(config.BMS_MAC_ADDRESS, timeout=15.0)
            if not device:
                raise BleakError("BMS no encontrado")
            collector = ModbusCollector(config.BMS_SLAVE_ADDR)
            async with BleakClient(device, timeout=20.0) as client:
                await client.start_notify(UUID_RX, collector.handle_notify)
                print(f"[LOG] Conectado. Guardando en {out_path} cada {interval}s")
                backoff = 5
                while not stop.is_set():
                    frame = await collector.request(client, cmd, timeout=6.0)
                    if frame:
                        payload = frame[3:-2]
                        reading = repo._parse_status(payload)
                        reg13 = (
                            struct.unpack_from(">H", payload, 13 * 2)[0]
                            if len(payload) > 27
                            else 0
                        )
                        log.append(reading, reg13)
                        cells = reading.cell_voltages_v
                        delta_mv = round((max(cells) - min(cells)) * 1000) if len(cells) >= 2 else 0
                        ts = reading.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                        print(
                            f"[LOG] {ts}  {reading.voltage_v:.2f}V "
                            f"{reading.current_a:+.2f}A  SoC {reading.soc_pct}%  "
                            f"delta {delta_mv}mV  reg12={reading.balance_status} reg13={reg13}"
                        )
                    else:
                        print("[LOG] Sin respuesta (timeout), reintento...")
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=interval)
                    except asyncio.TimeoutError:
                        pass
        except Exception as e:
            print(f"[LOG] Error: {type(e).__name__}: {e!r}. Reintentando en {backoff}s...")
            try:
                await asyncio.wait_for(stop.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 60)

    print(f"[LOG] Detenido. Datos en {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only BMS charge-cycle logger")
    parser.add_argument("--interval", type=int, default=30, help="seconds between samples (default 30)")
    parser.add_argument(
        "--out",
        default=os.path.join(
            config.DATA_DIR,
            f"balance_cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        ),
        help="output CSV path",
    )
    args = parser.parse_args()
    try:
        asyncio.run(run(args.interval, args.out))
    except KeyboardInterrupt:
        print("\n[LOG] Interrumpido por el usuario.")


if __name__ == "__main__":
    main()
