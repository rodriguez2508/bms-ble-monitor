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
    cap_design_ah: int
    cycles: int
    cell_voltages_v: List[float] = field(default_factory=list)
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
            "ts": self.timestamp.isoformat()
        }
