import json
import os
import threading
from typing import Dict, Optional

from src.modules.bms.domain.models.reading import BmsReading
from src.modules.bms.infrastructure.adapters.push_service import PushService


class SocAlertService:
    """Fires a single push when the SOC crosses a low or a high threshold.

    Each threshold re-arms once the SOC recovers past its hysteresis band,
    which avoids a storm of notifications around the boundary. Thresholds are
    persisted so they survive restarts and can be changed from the UI.
    """

    def __init__(self, push_service: PushService, config_path: str,
                 threshold_pct: float = 10.0, hysteresis: float = 5.0,
                 high_threshold_pct: float = 95.0,
                 high_hysteresis: float = 5.0) -> None:
        self._push = push_service
        self._config_path = config_path
        self._hysteresis = hysteresis
        self._high_hysteresis = high_hysteresis
        self._threshold = threshold_pct
        self._high_threshold = high_threshold_pct
        self._fired = False
        self._fired_high = False
        self._last_soc: Optional[float] = None
        self._lock = threading.Lock()
        self._load_config()

    def _load_config(self) -> None:
        if not os.path.exists(self._config_path):
            return
        try:
            with open(self._config_path) as f:
                data = json.load(f)
        except (ValueError, OSError):
            return
        if not isinstance(data, dict):
            return
        for key, attr in (("soc_alert_pct", "_threshold"),
                          ("soc_high_alert_pct", "_high_threshold")):
            if key in data:
                try:
                    setattr(self, attr, float(data[key]))
                except (TypeError, ValueError):
                    pass

    def _save_config(self) -> None:
        os.makedirs(os.path.dirname(self._config_path) or ".", exist_ok=True)
        with open(self._config_path, "w") as f:
            json.dump({
                "soc_alert_pct": self._threshold,
                "soc_high_alert_pct": self._high_threshold,
            }, f)

    def get_threshold(self) -> float:
        with self._lock:
            return self._threshold

    def get_high_threshold(self) -> float:
        with self._lock:
            return self._high_threshold

    def set_threshold(self, pct: float) -> float:
        with self._lock:
            self._threshold = float(pct)
            self._fired = False  # a new threshold re-arms the alert
            self._save_config()
            return self._threshold

    def set_high_threshold(self, pct: float) -> float:
        with self._lock:
            self._high_threshold = float(pct)
            self._fired_high = False
            self._save_config()
            return self._high_threshold

    def status(self) -> Dict[str, object]:
        with self._lock:
            return {
                "soc_alert_pct": self._threshold,
                "soc_high_alert_pct": self._high_threshold,
                "fired": self._fired,
                "fired_high": self._fired_high,
                "last_soc": self._last_soc,
            }

    def evaluate(self, reading: BmsReading) -> bool:
        soc = reading.soc_pct
        fire_low = False
        fire_high = False
        with self._lock:
            self._last_soc = soc
            low = self._threshold
            high = self._high_threshold
            if soc >= low + self._hysteresis:
                self._fired = False
            elif soc <= low and not self._fired:
                self._fired = True
                fire_low = True
            if soc <= high - self._high_hysteresis:
                self._fired_high = False
            elif soc >= high and not self._fired_high:
                self._fired_high = True
                fire_high = True

        if fire_low:
            self._push.send(
                "Batería baja",
                f"El SOC llegó a {soc:.0f}% (umbral {low:.0f}%).",
                {"soc": soc, "voltage_v": reading.voltage_v},
            )
        if fire_high:
            self._push.send(
                "Batería llena",
                f"El SOC llegó a {soc:.0f}% (umbral {high:.0f}%).",
                {"soc": soc, "voltage_v": reading.voltage_v},
            )
        return fire_low or fire_high
