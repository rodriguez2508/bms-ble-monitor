import asyncio
from datetime import datetime
from typing import List, Optional

import pytest

from src.modules.bms.domain.models.reading import BmsReading
from src.modules.bms.domain.models.config import BmsConfig
from src.modules.bms.domain.ports.bms_repository import BmsRepository
from src.modules.bms.infrastructure.entrypoints.flask_app import create_app


class FakeBmsRepository(BmsRepository):
    def __init__(self, reading: Optional[BmsReading] = None,
                 history: Optional[dict] = None,
                 config: Optional[BmsConfig] = None,
                 balance: Optional[List[dict]] = None) -> None:
        self.reading = reading
        self.history = history or {}
        self.config = config
        self.balance = balance or []
        self.calls: List[tuple] = []

    async def get_latest_reading(self) -> Optional[BmsReading]:
        return self.reading

    async def get_history(self, metric: str, limit: int) -> List[dict]:
        self.calls.append((metric, limit))
        return self.history.get(metric, [])[:limit]

    async def get_config(self) -> Optional[BmsConfig]:
        return self.config

    async def get_balance_log(self, limit: int) -> List[dict]:
        return self.balance[:limit]

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        return None


class FakePushService:
    def __init__(self) -> None:
        self.public_key = "FAKEKEY"
        self.subs: List[dict] = []
        self.sent: List[tuple] = []

    def subscribe(self, subscription: dict) -> bool:
        self.subs.append(subscription)
        return True

    def unsubscribe(self, endpoint: str) -> None:
        self.subs = [s for s in self.subs if s.get("endpoint") != endpoint]

    def send(self, title: str, body: str, data=None) -> int:
        self.sent.append((title, body))
        return len(self.subs)


class FakeSocAlert:
    def __init__(self, threshold: float = 10.0, high_threshold: float = 95.0) -> None:
        self._threshold = threshold
        self._high_threshold = high_threshold
        self.fired = False
        self.fired_high = False

    def get_threshold(self) -> float:
        return self._threshold

    def get_high_threshold(self) -> float:
        return self._high_threshold

    def set_threshold(self, pct: float) -> float:
        self._threshold = float(pct)
        self.fired = False
        return self._threshold

    def set_high_threshold(self, pct: float) -> float:
        self._high_threshold = float(pct)
        self.fired_high = False
        return self._high_threshold

    def status(self) -> dict:
        return {
            "soc_alert_pct": self._threshold,
            "soc_high_alert_pct": self._high_threshold,
            "fired": self.fired,
            "fired_high": self.fired_high,
            "last_soc": None,
        }

    def evaluate(self, reading) -> bool:
        return False


def build_client(repo, push=None, alert=None):
    app = create_app(
        repo,
        push_service=push or FakePushService(),
        soc_alert=alert or FakeSocAlert(),
        start_watcher=False,
    )
    app.config.update({"TESTING": True})
    return app.test_client()


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
        cell_temperatures_c=[25.0, 25.5],
        mosfet_temperature_c=31.0,
        ambient_temperature_c=28.0,
        extra_temperatures_c=[30.5, 31.8],
        balance_status=0b0001,
        warning_flags=0x0001,
        protection_flags=0x0000,
        status_flags=0x0C00,
        power_w=-19.86,
        timestamp=datetime(2026, 10, 8, 12, 0, 0),
    )


def sample_config() -> BmsConfig:
    return BmsConfig(
        pack_ov_alarm_v=14.0,
        pack_ov_protection_v=14.6,
        cell_ov_protection_v=3.65,
        balance_start_cell_v=3.4,
        balance_start_delta_mv=30,
        soc_alarm_pct=5,
        raw_registers=[0] * 55,
    )


@pytest.fixture
def fake_repo() -> FakeBmsRepository:
    return FakeBmsRepository(
        reading=sample_reading(),
        config=sample_config(),
        history={
            "voltage": [{"ts": "2026-10-08 12:00:00", "value": 13.24}] * 3,
            "current": [{"ts": "2026-10-08 12:00:00", "value": -1.5}],
        },
    )


@pytest.fixture
def client(fake_repo):
    return build_client(fake_repo)


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


def test_status_includes_new_fields(client):
    body = client.get("/api/status").get_json()
    data = body["data"]
    assert data["power_W"] == -19.86
    assert data["cell_temperatures_C"] == [25.0, 25.5]
    assert data["mosfet_temperature_C"] == 31.0
    assert data["ambient_temperature_C"] == 28.0
    assert data["extra_temperatures_C"] == [30.5, 31.8]
    assert data["balance_status"] == 0b0001
    assert data["warning_flags"] == 0x0001
    assert data["status_flags"] == 0x0C00


def test_config_endpoint(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    body = res.get_json()
    assert body["connected"] is True
    assert body["data"]["pack_ov_alarm_V"] == 14.0
    assert body["data"]["balance_start_delta_mV"] == 30
    assert body["data"]["soc_alarm_pct"] == 5
    assert len(body["data"]["raw_registers"]) == 55


def test_config_endpoint_when_unavailable():
    res = build_client(FakeBmsRepository(reading=None, config=None)).get("/api/config")
    assert res.status_code == 200
    assert res.get_json() == {"connected": False, "data": None}


def test_status_without_reading_reports_disconnected():
    res = build_client(FakeBmsRepository(reading=None)).get("/api/status")
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


def test_balance_endpoint_returns_points():
    points = [
        {"ts": "2026-10-08 12:00:00", "delta_mv": 120, "reg12_balance": 0, "reg13": 0},
        {"ts": "2026-10-08 12:00:30", "delta_mv": 140, "reg12_balance": 1, "reg13": 0},
    ]
    repo = FakeBmsRepository(reading=sample_reading(), balance=points)
    res = build_client(repo).get("/api/balance")
    assert res.status_code == 200
    assert res.get_json()["points"] == points


def test_balance_endpoint_honors_limit():
    repo = FakeBmsRepository(reading=sample_reading(),
                             balance=[{"ts": "x", "delta_mv": i} for i in range(5)])
    res = build_client(repo).get("/api/balance?limit=2")
    assert res.status_code == 200
    assert len(res.get_json()["points"]) == 2


def test_balance_endpoint_empty_when_unavailable():
    res = build_client(FakeBmsRepository(reading=None)).get("/api/balance")
    assert res.status_code == 200
    assert res.get_json() == {"points": []}


def test_push_public_key(client):
    res = client.get("/api/push/public_key")
    assert res.status_code == 200
    assert res.get_json() == {"key": "FAKEKEY"}


def test_push_subscribe(client):
    res = client.post("/api/push/subscribe", json={"endpoint": "https://x/1", "keys": {}})
    assert res.status_code == 200
    assert res.get_json()["ok"] is True


def test_alerts_config_get_and_post(client):
    assert client.get("/api/alerts/config").get_json()["soc_alert_pct"] == 10.0
    res = client.post("/api/alerts/config", json={"soc_alert_pct": 15})
    assert res.get_json()["soc_alert_pct"] == 15.0
    assert client.get("/api/alerts/config").get_json()["soc_alert_pct"] == 15.0


def test_alerts_config_invalid(client):
    res = client.post("/api/alerts/config", json={"soc_alert_pct": "abc"})
    assert res.status_code == 400


def test_alerts_config_high_threshold(client):
    assert client.get("/api/alerts/config").get_json()["soc_high_alert_pct"] == 95.0
    res = client.post("/api/alerts/config", json={"soc_high_alert_pct": 90})
    assert res.get_json()["soc_high_alert_pct"] == 90.0
    assert client.get("/api/alerts/config").get_json()["soc_high_alert_pct"] == 90.0


def test_alerts_config_missing_both_is_400(client):
    res = client.post("/api/alerts/config", json={})
    assert res.status_code == 400


def test_service_worker_served(client):
    res = client.get("/sw.js")
    assert res.status_code == 200
    assert "javascript" in res.mimetype


def test_app_js_served(client):
    res = client.get("/app.js")
    assert res.status_code == 200
    assert "javascript" in res.mimetype


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
