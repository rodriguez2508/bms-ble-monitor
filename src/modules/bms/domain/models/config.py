from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class BmsConfig:
    """Read-only thresholds read from the BMS parameter block (registers 83..137).

    This firmware stores the PACE parameter block shifted +23 registers relative to
    the published PACE Modbus V1.3 map. Units: pack voltages are 10 mV/LSB, cell
    voltages are mV/LSB, temperatures 0.1 C/LSB.
    """

    pack_ov_alarm_v: float = 0.0          # reg83  /100
    pack_ov_protection_v: float = 0.0     # reg84  /100
    cell_ov_alarm_v: float = 0.0          # reg87  /1000
    cell_ov_protection_v: float = 0.0     # reg88  /1000
    pack_uv_protection_v: float = 0.0     # reg92  /100
    cell_uv_protection_v: float = 0.0     # reg96  /1000
    charge_oc_alarm_a: int = 0            # reg99
    charge_oc_protection_a: int = 0       # reg100
    charge_ot_alarm_c: float = 0.0        # reg107 /10
    balance_start_cell_v: float = 0.0     # reg128 /1000
    balance_start_delta_mv: int = 0       # reg129
    pack_full_charge_v: float = 0.0       # reg130 /100
    cell_sleep_v: float = 0.0             # reg132 /1000
    cell_sleep_delay_min: int = 0         # reg133
    soc_alarm_pct: int = 0                # reg135
    raw_registers: List[int] = field(default_factory=list)  # regs 83..137

    def to_dict(self):
        return {
            "pack_ov_alarm_V": self.pack_ov_alarm_v,
            "pack_ov_protection_V": self.pack_ov_protection_v,
            "cell_ov_alarm_V": self.cell_ov_alarm_v,
            "cell_ov_protection_V": self.cell_ov_protection_v,
            "pack_uv_protection_V": self.pack_uv_protection_v,
            "cell_uv_protection_V": self.cell_uv_protection_v,
            "charge_oc_alarm_A": self.charge_oc_alarm_a,
            "charge_oc_protection_A": self.charge_oc_protection_a,
            "charge_ot_alarm_C": self.charge_ot_alarm_c,
            "balance_start_cell_V": self.balance_start_cell_v,
            "balance_start_delta_mV": self.balance_start_delta_mv,
            "pack_full_charge_V": self.pack_full_charge_v,
            "cell_sleep_V": self.cell_sleep_v,
            "cell_sleep_delay_min": self.cell_sleep_delay_min,
            "soc_alarm_pct": self.soc_alarm_pct,
            "raw_registers": self.raw_registers,
        }
