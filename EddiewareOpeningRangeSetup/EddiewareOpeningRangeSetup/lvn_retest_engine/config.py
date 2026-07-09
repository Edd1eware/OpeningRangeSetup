from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import time
from typing import Any


def parse_clock(value: str | time) -> time:
    if isinstance(value, time):
        return value
    parts = value.strip().split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"Hora inválida: {value!r}; use HH:MM o HH:MM:SS")
    hour, minute = int(parts[0]), int(parts[1])
    second = int(parts[2]) if len(parts) == 3 else 0
    return time(hour, minute, second)


@dataclass(slots=True)
class ResearchConfig:
    symbol: str = "NQ"
    tick_size: float = 0.25
    input_timezone: str = "America/New_York"
    market_timezone: str = "America/New_York"

    context_profile_start: time = time(8, 30)
    context_profile_end: time = time(9, 30)
    lvn_profile_start: time = time(9, 30)
    lvn_profile_end: time = time(9, 31)
    retest_start: time = time(9, 31)
    retest_end: time = time(9, 40)
    rth_end: time = time(16, 0)

    value_area_pct: float = 0.70
    lvn_neighbor_levels: int = 2
    lvn_max_percent_of_neighbors: float = 0.50
    min_total_volume_at_profile: float = 1.0
    min_lvn_volume: float = 1.0
    max_lvn_volume_percent_of_poc: float = 0.50
    hvn_neighbor_levels: int = 2
    hvn_min_percent_of_neighbors: float = 1.25
    min_hvn_volume: float = 1.0

    retest_tolerance_ticks: int = 0
    retest_rearm_ticks: int = 1
    resolution_confirm_ticks: int = 1
    imbalance_neighbor_levels: int = 2
    imbalance_ratio: float = 3.0
    imbalance_min_compare_volume: float = 5.0
    big_trade_min_size: float = 20.0
    atr_period: int = 14
    ema_span: int = 20
    shape_temperature: float = 0.22

    def __post_init__(self) -> None:
        for field_name in (
            "context_profile_start",
            "context_profile_end",
            "lvn_profile_start",
            "lvn_profile_end",
            "retest_start",
            "retest_end",
            "rth_end",
        ):
            setattr(self, field_name, parse_clock(getattr(self, field_name)))
        if self.tick_size <= 0:
            raise ValueError("tick_size debe ser > 0")
        if not 0 < self.value_area_pct <= 1:
            raise ValueError("value_area_pct debe estar en (0, 1]")
        if self.lvn_neighbor_levels < 1 or self.hvn_neighbor_levels < 1:
            raise ValueError("Los parámetros de vecinos deben ser >= 1")
        if not 0 <= self.lvn_max_percent_of_neighbors <= 1:
            raise ValueError("lvn_max_percent_of_neighbors debe estar en [0, 1]")
        if not 0 <= self.max_lvn_volume_percent_of_poc <= 1:
            raise ValueError("max_lvn_volume_percent_of_poc debe estar en [0, 1]")
        if self.retest_tolerance_ticks < 0:
            raise ValueError("retest_tolerance_ticks debe ser >= 0")
        if self.retest_rearm_ticks < 1:
            raise ValueError("retest_rearm_ticks debe ser >= 1")
        if self.resolution_confirm_ticks < 0:
            raise ValueError("resolution_confirm_ticks debe ser >= 0")

    def as_serializable_dict(self) -> dict[str, Any]:
        out = asdict(self)
        for key, value in list(out.items()):
            if isinstance(value, time):
                out[key] = value.isoformat()
        return out
