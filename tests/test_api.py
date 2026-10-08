import asyncio
from datetime import datetime
from typing import List, Optional

import pytest

from src.modules.bms.domain.models.reading import BmsReading
from src.modules.bms.domain.ports.bms_repository import BmsRepository
from src.modules.bms.infrastructure.entrypoints.flask_app import create_app


class FakeBmsRepository(BmsRepository):
    def __init__(self, reading: Optional[BmsReading] = None,
                 history: Optional[dict] = None) -> None:
        self.reading = reading
        self.history = history or {}
        self.calls: List[tuple] = []

    async def get_latest_reading(self) -> Optional[BmsReading]:
        return self.reading

    async def get_history(self, metric: str, limit: int) -> List[dict]:
        self.calls.append((metric, limit))
        return self.history.get(metric, [])[:limit]

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        return None


def sample_reading() -> BmsReading:
    return BmsReading(
        voltage_v=13.24,
        current_a=-1.5,
        soc_pct=87.0,
        soh_pct=99.0,
        cap_remain_ah=100.5,
        cap_design_ah=120,
        cycles=42,
        cell_voltages_v=[3.31, 3.30, 3.32, 3.31],
        timestamp=datetime(2026, 10, 8, 12, 0, 0),
    )


@pytest.fixture
def fake_repo() -> FakeBmsRepository:
    return FakeBmsRepository(
        reading=sample_reading(),
        history={
            "voltage": [{"ts": "2026-10-08 12:00:00", "value": 13.24}] * 3,
            "current": [{"ts": "2026-10-08 12:00:00", "value": -1.5}],
        },
    )


@pytest.fixture
def client(fake_repo):
    app = create_app(fake_repo)
    app.config.update({"TESTING": True})
    return app.test_client()


def test_status_returns_reading(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    body = res.get_json()
    assert body["connected"] is True
    assert body["data"]["voltage_V"] == 13.24
    assert body["data"]["current_A"] == -1.5
    assert body["data"]["soc_pct"] == 87.0
    assert body["data"]["cycles"] == 42
    assert body["data"]["cell_voltages_V"] == [3.31, 3.30, 3.32, 3.31]
    assert body["data"]["ts"] == "2026-10-08T12:00:00"


def test_status_without_reading_reports_disconnected():
    app = create_app(FakeBmsRepository(reading=None))
    app.config.update({"TESTING": True})
    res = app.test_client().get("/api/status")
    assert res.status_code == 200
    body = res.get_json()
    assert body == {"connected": False, "data": None}


def test_history_returns_points(client, fake_repo):
    res = client.get("/api/history/voltage")
    assert res.status_code == 200
    body = res.get_json()
    assert body["metric"] == "voltage"
    assert len(body["points"]) == 3
    assert body["points"][0]["value"] == 13.24
    assert fake_repo.calls[-1] == ("voltage", 200)


def test_history_honors_limit(client, fake_repo):
    res = client.get("/api/history/voltage?limit=1")
    assert res.status_code == 200
    assert len(res.get_json()["points"]) == 1
    assert fake_repo.calls[-1] == ("voltage", 1)


def test_history_unknown_metric_returns_empty(client):
    res = client.get("/api/history/nope")
    assert res.status_code == 200
    assert res.get_json()["points"] == []


def test_history_limit_zero_returns_empty(client, fake_repo):
    res = client.get("/api/history/voltage?limit=0")
    assert res.status_code == 200
    assert res.get_json()["points"] == []
    assert fake_repo.calls[-1] == ("voltage", 0)


def test_dashboard_served_at_root(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.mimetype == "text/html"
    html = res.get_data(as_text=True)
    assert "BMS Dashboard" in html
    assert "/api/status" in html
    assert "/api/history/" in html


def test_dashboard_served_at_dashboard_path(client):
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert res.mimetype == "text/html"
    assert "BMS Dashboard" in res.get_data(as_text=True)


def test_status_handler_returns_repository_reading():
    from src.modules.bms.application.queries.get_status_handler import (
        GetBmsStatusHandler,
        GetBmsStatusQuery,
    )

    handler = GetBmsStatusHandler(FakeBmsRepository(reading=sample_reading()))
    reading = asyncio.run(handler.execute(GetBmsStatusQuery()))
    assert reading is not None
    assert reading.voltage_v == 13.24


def test_history_handler_clamps_limit(fake_repo):
    from src.modules.bms.application.queries.get_history_handler import (
        GetBmsHistoryHandler,
        GetBmsHistoryQuery,
        MAX_HISTORY_LIMIT,
    )

    handler = GetBmsHistoryHandler(fake_repo)
    asyncio.run(handler.execute(GetBmsHistoryQuery("voltage", MAX_HISTORY_LIMIT + 100)))
    assert fake_repo.calls[-1] == ("voltage", MAX_HISTORY_LIMIT)

    asyncio.run(handler.execute(GetBmsHistoryQuery("voltage", -5)))
    assert fake_repo.calls[-1] == ("voltage", 0)
