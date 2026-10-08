import csv
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List

from src.modules.bms.domain.models.reading import BmsReading

# Fixed columns; per-cell columns are appended after these, one per detected cell.
BASE_FIELDS = [
    "ts", "voltage_v", "current_a", "soc_pct", "power_w", "delta_mv",
    "reg9_warn", "reg10_prot", "reg11_status", "reg12_balance", "reg13",
    "warn_hex", "prot_hex", "status_hex",
]

ROTATE_EVERY = 60  # appends between retention passes (avoids rewriting on every row)
TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"


class BalanceLog:
    """Append-only CSV of the charge/balance cycle, with time-based retention.

    Written from the BLE polling thread and read from Flask request threads, so
    every file access is guarded by a lock. Purely a local sink: no BLE writes.
    """

    def __init__(self, path: str, retention_hours: float = 48.0) -> None:
        self.path = path
        self.retention_hours = retention_hours
        self._lock = threading.Lock()
        self._cell_count = 4
        self._writes = 0

    def _fields(self) -> List[str]:
        return BASE_FIELDS + [f"cell{i}_v" for i in range(1, self._cell_count + 1)]

    def append(self, reading: BmsReading, reg13: int) -> None:
        cells = list(reading.cell_voltages_v)
        if cells:
            self._cell_count = len(cells)

        delta_mv = 0
        if len(cells) >= 2:
            delta_mv = round((max(cells) - min(cells)) * 1000)

        row: Dict[str, object] = {
            "ts": reading.timestamp.strftime(TIMESTAMP_FMT),
            "voltage_v": reading.voltage_v,
            "current_a": reading.current_a,
            "soc_pct": reading.soc_pct,
            "power_w": round(reading.power_w, 2),
            "delta_mv": delta_mv,
            "reg9_warn": reading.warning_flags,
            "reg10_prot": reading.protection_flags,
            "reg11_status": reading.status_flags,
            "reg12_balance": reading.balance_status,
            "reg13": reg13,
            "warn_hex": f"0x{reading.warning_flags:04X}",
            "prot_hex": f"0x{reading.protection_flags:04X}",
            "status_hex": f"0x{reading.status_flags:04X}",
        }
        for i in range(self._cell_count):
            row[f"cell{i + 1}_v"] = cells[i] if i < len(cells) else ""

        with self._lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            new_file = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
            with open(self.path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self._fields())
                if new_file:
                    writer.writeheader()
                writer.writerow(row)
            self._writes += 1
            if self._writes % ROTATE_EVERY == 0:
                self._rotate_locked()

    def read(self, limit: int) -> List[Dict[str, object]]:
        if limit <= 0:
            return []
        with self._lock:
            if not os.path.exists(self.path):
                return []
            with open(self.path, newline="") as f:
                rows = list(csv.DictReader(f))
        return [self._coerce(r) for r in rows[-limit:]]

    def rotate(self) -> None:
        with self._lock:
            self._rotate_locked()

    def _rotate_locked(self) -> None:
        if not os.path.exists(self.path):
            return
        cutoff = datetime.now() - timedelta(hours=self.retention_hours)
        with open(self.path, newline="") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or self._fields()
            kept = []
            for row in reader:
                try:
                    ts = datetime.strptime(row.get("ts", ""), TIMESTAMP_FMT)
                except ValueError:
                    continue
                if ts >= cutoff:
                    kept.append(row)
        with open(self.path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(kept)

    @staticmethod
    def _coerce(row: Dict[str, str]) -> Dict[str, object]:
        out: Dict[str, object] = {}
        for key, value in row.items():
            if key == "ts" or value is None or value == "":
                out[key] = value
                continue
            try:
                out[key] = int(value)
            except ValueError:
                try:
                    out[key] = float(value)
                except ValueError:
                    out[key] = value
        return out
