from dataclasses import dataclass, field
from datetime import datetime
from typing import List

@dataclass(frozen=True)
class BmsReading:
    voltage_v: float
    current_a: float
    soc_pct: float
    soh_pct: float
    cap_remain_ah: float
    cap_design_ah: float
    cycles: int
    cell_voltages_v: List[float] = field(default_factory=list)
    cell_temperatures_c: List[float] = field(default_factory=list)
    mosfet_temperature_c: float = 0.0
    ambient_temperature_c: float = 0.0
    extra_temperatures_c: List[float] = field(default_factory=list)
    balance_status: int = 0
    warning_flags: int = 0
    protection_flags: int = 0
    status_flags: int = 0
    power_w: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "voltage_V": self.voltage_v,
            "current_A": self.current_a,
            "soc_pct": self.soc_pct,
            "soh_pct": self.soh_pct,
            "cap_remain_Ah": self.cap_remain_ah,
            "cap_design_Ah": self.cap_design_ah,
            "cycles": self.cycles,
            "cell_voltages_V": self.cell_voltages_v,
            "cell_temperatures_C": self.cell_temperatures_c,
            "mosfet_temperature_C": self.mosfet_temperature_c,
            "ambient_temperature_C": self.ambient_temperature_c,
            "extra_temperatures_C": self.extra_temperatures_c,
            "balance_status": self.balance_status,
            "warning_flags": self.warning_flags,
            "protection_flags": self.protection_flags,
            "status_flags": self.status_flags,
            "power_W": self.power_w,
            "ts": self.timestamp.isoformat()
        }
