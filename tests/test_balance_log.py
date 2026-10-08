import os
from datetime import datetime, timedelta
from typing import List

from src.modules.bms.domain.models.reading import BmsReading
from src.modules.bms.infrastructure.adapters.balance_log import BalanceLog


def make_reading(ts: datetime,
                 cells: List[float],
                 current: float = 1.0,
                 voltage: float = 13.5,
                 warn: int = 0,
                 prot: int = 0,
                 status: int = 0,
                 balance: int = 0) -> BmsReading:
    return BmsReading(
        voltage_v=voltage,
        current_a=current,
        soc_pct=90.0,
        soh_pct=99.0,
        cap_remain_ah=100.0,
        cap_design_ah=120.0,
        cycles=10,
        cell_voltages_v=cells,
        warning_flags=warn,
        protection_flags=prot,
        status_flags=status,
        balance_status=balance,
        power_w=voltage * current,
        timestamp=ts,
    )


def test_append_and_read(tmp_path):
    log = BalanceLog(str(tmp_path / "b.csv"), retention_hours=48)
    log.append(make_reading(datetime(2026, 10, 8, 10, 0, 0), [3.5, 3.4, 3.38, 3.4], warn=1), reg13=0)

    rows = log.read(10)
    assert len(rows) == 1
    row = rows[0]
    assert row["ts"] == "2026-10-08 10:00:00"
    assert row["delta_mv"] == 120
    assert row["reg9_warn"] == 1
    assert row["warn_hex"] == "0x0001"
    assert row["cell1_v"] == 3.5
    assert row["reg13"] == 0


def test_read_honors_limit_and_zero(tmp_path):
    log = BalanceLog(str(tmp_path / "b.csv"))
    for i in range(5):
        log.append(make_reading(datetime(2026, 10, 8, 10, 0, i), [3.4, 3.4, 3.4, 3.4]), 0)

    assert len(log.read(2)) == 2
    assert log.read(0) == []


def test_read_missing_file_returns_empty(tmp_path):
    log = BalanceLog(str(tmp_path / "missing.csv"))
    assert log.read(10) == []


def test_rotate_drops_rows_outside_retention(tmp_path):
    log = BalanceLog(str(tmp_path / "b.csv"), retention_hours=48)
    old = datetime.now() - timedelta(days=3)
    log.append(make_reading(old, [3.4, 3.4, 3.4, 3.4]), 0)
    log.append(make_reading(datetime.now(), [3.4, 3.4, 3.4, 3.4]), 0)

    log.rotate()
    rows = log.read(10)
    assert len(rows) == 1
    assert rows[0]["ts"].startswith(datetime.now().strftime("%Y-%m-%d"))


def test_append_creates_parent_directory(tmp_path):
    path = tmp_path / "sub" / "b.csv"
    log = BalanceLog(str(path))
    log.append(make_reading(datetime.now(), [3.4, 3.4, 3.4, 3.4]), 0)
    assert os.path.exists(str(path))
