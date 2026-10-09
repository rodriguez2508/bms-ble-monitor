import base64
import json
import os
import threading
from typing import Dict, List, Optional

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush


def _public_key_b64(vapid: Vapid) -> str:
    """Application server key (base64url, unpadded) for the browser subscription."""
    raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class PushService:
    """VAPID key management + browser push subscriptions.

    Keys are generated once and persisted; subscriptions are stored in a JSON
    file so the server can push even when no dashboard tab is open.
    """

    def __init__(self, keys_path: str, subscriptions_path: str, subject: str) -> None:
        self._keys_path = keys_path
        self._subs_path = subscriptions_path
        self._subject = subject
        self._lock = threading.Lock()
        self._vapid: Optional[Vapid] = None
        self._subs: List[Dict[str, object]] = self._load_subs()

    def _ensure_vapid(self) -> Vapid:
        # Keys are generated lazily so merely constructing the service (e.g. in
        # tests) never touches the filesystem.
        with self._lock:
            if self._vapid is None:
                if os.path.exists(self._keys_path):
                    self._vapid = Vapid.from_file(self._keys_path)
                else:
                    vapid = Vapid()
                    vapid.generate_keys()
                    os.makedirs(os.path.dirname(self._keys_path) or ".", exist_ok=True)
                    with open(self._keys_path, "wb") as f:
                        f.write(vapid.private_pem())
                    self._vapid = vapid
            return self._vapid

    @property
    def public_key(self) -> str:
        return _public_key_b64(self._ensure_vapid())

    def _load_subs(self) -> List[Dict[str, object]]:
        if not os.path.exists(self._subs_path):
            return []
        try:
            with open(self._subs_path) as f:
                data = json.load(f)
        except (ValueError, OSError):
            return []
        return data if isinstance(data, list) else []

    def _save_subs(self) -> None:
        os.makedirs(os.path.dirname(self._subs_path) or ".", exist_ok=True)
        with open(self._subs_path, "w") as f:
            json.dump(self._subs, f)

    def subscribe(self, subscription: Dict[str, object]) -> bool:
        endpoint = subscription.get("endpoint")
        if not endpoint:
            return False
        with self._lock:
            self._subs = [s for s in self._subs if s.get("endpoint") != endpoint]
            self._subs.append(subscription)
            self._save_subs()
        return True

    def unsubscribe(self, endpoint: str) -> None:
        with self._lock:
            self._subs = [s for s in self._subs if s.get("endpoint") != endpoint]
            self._save_subs()

    def count(self) -> int:
        with self._lock:
            return len(self._subs)

    def send(self, title: str, body: str, data: Optional[Dict[str, object]] = None) -> int:
        vapid = self._ensure_vapid()  # make sure the private key exists
        payload = json.dumps({"title": title, "body": body, "data": data or {}})
        with self._lock:
            subs = list(self._subs)
        sent = 0
        dead: List[object] = []
        for sub in subs:
            try:
                webpush(
                    subscription_info=sub,
                    data=payload,
                    vapid_private_key=vapid,
                    vapid_claims={"sub": self._subject},
                )
                sent += 1
            except WebPushException as e:
                response = getattr(e, "response", None)
                status = getattr(response, "status_code", None)
                if status in (404, 410):
                    dead.append(sub.get("endpoint"))
            except Exception:
                # A single malformed subscription must not break the others.
                continue
        if dead:
            with self._lock:
                self._subs = [s for s in self._subs if s.get("endpoint") not in dead]
                self._save_subs()
        return sent
