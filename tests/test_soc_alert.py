from datetime import datetime
from typing import Dict, List, Optional

from src.modules.bms.application.services.soc_alert import SocAlertService
from src.modules.bms.domain.models.reading import BmsReading


class FakePush:
    def __init__(self) -> None:
        self.sent: List[tuple] = []

    def send(self, title: str, body: str, data: Optional[Dict[str, object]] = None) -> int:
        self.sent.append((title, body, data))
        return 1


def reading(soc: float) -> BmsReading:
    return BmsReading(
        voltage_v=13.0, current_a=-1.0, soc_pct=soc, soh_pct=100.0,
        cap_remain_ah=10.0, cap_design_ah=82.0, cycles=1,
        timestamp=datetime.now(),
    )


def test_fires_once_on_crossing(tmp_path):
    push = FakePush()
    svc = SocAlertService(push, str(tmp_path / "a.json"), threshold_pct=10, hysteresis=5)

    assert svc.evaluate(reading(50)) is False
    assert svc.evaluate(reading(9)) is True
    assert len(push.sent) == 1
    assert svc.evaluate(reading(8)) is False  # already fired
    assert len(push.sent) == 1


def test_rearms_only_after_hysteresis(tmp_path):
    push = FakePush()
    svc = SocAlertService(push, str(tmp_path / "a.json"), threshold_pct=10, hysteresis=5)

    svc.evaluate(reading(9))
    assert len(push.sent) == 1
    svc.evaluate(reading(12))  # below threshold + hysteresis -> stays fired
    svc.evaluate(reading(9))
    assert len(push.sent) == 1
    svc.evaluate(reading(16))  # >= 15 -> re-arms
    svc.evaluate(reading(9))   # fires again
    assert len(push.sent) == 2


def test_no_fire_above_threshold(tmp_path):
    push = FakePush()
    svc = SocAlertService(push, str(tmp_path / "a.json"), threshold_pct=10)
    svc.evaluate(reading(50))
    assert push.sent == []


def test_threshold_persisted_and_rearms(tmp_path):
    path = str(tmp_path / "a.json")
    push = FakePush()
    svc = SocAlertService(push, path, threshold_pct=10)

    svc.evaluate(reading(9))  # fires
    assert svc.set_threshold(20) == 20
    svc.evaluate(reading(15))  # 15 <= 20 and re-armed -> fires
    assert len(push.sent) == 2

    reloaded = SocAlertService(FakePush(), path, threshold_pct=10)
    assert reloaded.get_threshold() == 20


def test_fires_high_once_on_crossing(tmp_path):
    push = FakePush()
    svc = SocAlertService(push, str(tmp_path / "a.json"),
                          threshold_pct=10, high_threshold_pct=95)

    assert svc.evaluate(reading(50)) is False
    assert svc.evaluate(reading(96)) is True
    assert len(push.sent) == 1
    assert svc.evaluate(reading(99)) is False  # already fired
    assert len(push.sent) == 1


def test_high_rearms_only_after_hysteresis(tmp_path):
    push = FakePush()
    svc = SocAlertService(push, str(tmp_path / "a.json"),
                          threshold_pct=10, high_threshold_pct=95,
                          high_hysteresis=5)

    svc.evaluate(reading(96))
    assert len(push.sent) == 1
    svc.evaluate(reading(92))  # above 90 -> stays fired
    svc.evaluate(reading(96))
    assert len(push.sent) == 1
    svc.evaluate(reading(89))  # <= 90 -> re-arms
    svc.evaluate(reading(96))  # fires again
    assert len(push.sent) == 2


def test_low_and_high_alerts_are_independent(tmp_path):
    push = FakePush()
    svc = SocAlertService(push, str(tmp_path / "a.json"),
                          threshold_pct=10, high_threshold_pct=95)

    assert svc.evaluate(reading(96)) is True   # high fires
    assert svc.evaluate(reading(50)) is False
    assert svc.evaluate(reading(9)) is True    # low fires
    assert len(push.sent) == 2


def test_high_threshold_persisted(tmp_path):
    path = str(tmp_path / "a.json")
    svc = SocAlertService(FakePush(), path, threshold_pct=10)
    assert svc.set_high_threshold(90) == 90

    reloaded = SocAlertService(FakePush(), path, threshold_pct=10)
    assert reloaded.get_high_threshold() == 90
