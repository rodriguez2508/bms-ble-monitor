import asyncio

import pytest

from src.modules.bms.infrastructure.adapters.bleak_bms_repository import BleakBmsRepository
from src.modules.shared.infrastructure.config.config import config


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def write_history(directory, name, rows):
    path = directory / f"{name}_history.csv"
    path.write_text("".join(",".join(map(str, row)) + "\n" for row in rows))


def test_get_history_reads_csv(data_dir):
    write_history(data_dir, "voltage", [
        ["2026-10-08 12:00:00", 13.2],
        ["2026-10-08 12:00:05", 13.1],
        ["2026-10-08 12:00:10", 13.0],
    ])
    repo = BleakBmsRepository()
    points = asyncio.run(repo.get_history("voltage", 2))
    assert points == [
        {"ts": "2026-10-08 12:00:05", "value": 13.1},
        {"ts": "2026-10-08 12:00:10", "value": 13.0},
    ]


def test_get_history_skips_malformed_rows(data_dir):
    write_history(data_dir, "voltage", [
        ["2026-10-08 12:00:00", 13.2],
        ["broken-row-only-one-column"],
        ["2026-10-08 12:00:10", "not-a-number"],
        ["2026-10-08 12:00:15", 13.0],
    ])
    repo = BleakBmsRepository()
    points = asyncio.run(repo.get_history("voltage", 10))
    assert points == [
        {"ts": "2026-10-08 12:00:00", "value": 13.2},
        {"ts": "2026-10-08 12:00:15", "value": 13.0},
    ]


def test_get_history_unknown_metric_returns_empty(data_dir):
    repo = BleakBmsRepository()
    assert asyncio.run(repo.get_history("temperature", 10)) == []


def test_get_history_non_positive_limit_returns_empty(data_dir):
    write_history(data_dir, "soc", [["2026-10-08 12:00:00", 87]])
    repo = BleakBmsRepository()
    assert asyncio.run(repo.get_history("soc", 0)) == []
    assert asyncio.run(repo.get_history("soc", -3)) == []


def test_get_history_missing_file_returns_empty(data_dir):
    repo = BleakBmsRepository()
    assert asyncio.run(repo.get_history("current", 10)) == []
