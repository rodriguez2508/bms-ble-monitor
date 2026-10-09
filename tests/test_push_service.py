import os

from src.modules.bms.infrastructure.adapters import push_service as ps_mod
from src.modules.bms.infrastructure.adapters.push_service import PushService


def make(tmp_path) -> PushService:
    return PushService(
        str(tmp_path / "vapid.json"),
        str(tmp_path / "subs.json"),
        "mailto:a@localhost",
    )


def test_subscribe_unsubscribe_persist(tmp_path):
    svc = make(tmp_path)
    assert svc.count() == 0
    assert svc.subscribe({"endpoint": "https://p/1", "keys": {}}) is True
    svc.subscribe({"endpoint": "https://p/2", "keys": {}})
    assert svc.count() == 2
    svc.unsubscribe("https://p/1")
    assert svc.count() == 1

    reloaded = make(tmp_path)
    assert reloaded.count() == 1


def test_subscribe_requires_endpoint(tmp_path):
    svc = make(tmp_path)
    assert svc.subscribe({"keys": {}}) is False
    assert svc.count() == 0


def test_public_key_generated_lazily(tmp_path):
    svc = make(tmp_path)
    assert not os.path.exists(str(tmp_path / "vapid.json"))
    key = svc.public_key
    assert isinstance(key, str) and len(key) > 50
    assert os.path.exists(str(tmp_path / "vapid.json"))


def test_send_removes_dead_subscriptions(tmp_path, monkeypatch):
    svc = make(tmp_path)
    svc.subscribe({"endpoint": "https://dead", "keys": {}})
    svc.subscribe({"endpoint": "https://alive", "keys": {}})

    def fake_webpush(subscription_info, data=None, vapid_private_key=None, vapid_claims=None):
        if subscription_info["endpoint"] == "https://dead":
            response = type("R", (), {"status_code": 410})()
            raise ps_mod.WebPushException("gone", response=response)
        return "ok"

    monkeypatch.setattr(ps_mod, "webpush", fake_webpush)
    sent = svc.send("t", "b")
    assert sent == 1
    assert svc.count() == 1
