from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, time

import numpy as np
import pandas as pd

from .config import ResearchConfig
from .statistics import linear_slope, normalized_entropy, safe_div, weighted_moments


def seconds_of_day(value: time) -> int:
    return value.hour * 3600 + value.minute * 60 + value.second


def window_mask(frame: pd.DataFrame, start: time, end: time) -> pd.Series:
    seconds = (
        frame["timestamp"].dt.hour * 3600
        + frame["timestamp"].dt.minute * 60
        + frame["timestamp"].dt.second
        + frame["timestamp"].dt.microsecond / 1_000_000
    )
    return (seconds >= seconds_of_day(start)) & (seconds < seconds_of_day(end))


@dataclass(slots=True)
class Profile:
    session_date: date
    profile_name: str
    start: time
    end: time
    tick_size: float
    levels: pd.DataFrame
    source_rows: int
    metrics: dict[str, object] = field(default_factory=dict)
    hvns: list[dict[str, object]] = field(default_factory=list)
    lvns: list[dict[str, object]] = field(default_factory=list)
    shape: dict[str, object] = field(default_factory=dict)

    @property
    def has_data(self) -> bool:
        return not self.levels.empty and float(self.metrics.get("total_volume", 0.0)) > 0


def _choose_poc(levels: pd.DataFrame, center_of_mass: float) -> int:
    max_volume = levels["volume"].max()
    tied = levels.index[levels["volume"].eq(max_volume)].to_numpy(dtype=int)
    if len(tied) == 1:
        return int(tied[0])
    center_bin = center_of_mass / float(levels.attrs["tick_size"])
    return int(sorted(tied, key=lambda value: (abs(value - center_bin), value))[0])


def _value_area(levels: pd.DataFrame, poc_bin: int, target_pct: float) -> tuple[int, int, float]:
    lo, hi = int(levels.index.min()), int(levels.index.max())
    target = float(levels["volume"].sum()) * target_pct
    accumulated = float(levels.at[poc_bin, "volume"])
    low = high = poc_bin
    while accumulated < target and (low > lo or high < hi):
        upper_volume = float(levels.at[high + 1, "volume"]) if high < hi else -1.0
        lower_volume = float(levels.at[low - 1, "volume"]) if low > lo else -1.0
        if upper_volume >= lower_volume:
            high += 1
            accumulated += max(0.0, upper_volume)
        else:
            low -= 1
            accumulated += max(0.0, lower_volume)
    return low, high, safe_div(accumulated, float(levels["volume"].sum()), 0.0)


def detect_level_step(prices: np.ndarray, tick_size: float) -> float:
    """Native price grid actually present in the data (mode of consecutive gaps).

    The chart's footprint row size sets how many real ticks each exported price
    level spans (e.g. 5 ticks/row instead of 1). Binning at a fixed config
    tick_size when the data grid is coarser leaves every "neighbor" bin at zero
    volume and breaks LVN/HVN neighbor detection structurally. Detecting the
    real grid per profile makes detection correct regardless of chart config.
    """
    unique_prices = np.unique(prices)
    if unique_prices.size < 2:
        return tick_size
    diffs = np.diff(unique_prices)
    diffs = diffs[diffs > 1e-9]
    if diffs.size == 0:
        return tick_size
    ticks = np.rint(diffs / tick_size).astype(np.int64)
    ticks = ticks[ticks > 0]
    if ticks.size == 0:
        return tick_size
    values, counts = np.unique(ticks, return_counts=True)
    step_ticks = int(values[np.argmax(counts)])
    return float(step_ticks) * tick_size


def build_profile(
    session_frame: pd.DataFrame,
    session_date: date,
    profile_name: str,
    start: time,
    end: time,
    config: ResearchConfig,
) -> Profile:
    selected = session_frame.loc[window_mask(session_frame, start, end)].copy()
    if selected.empty:
        return Profile(session_date, profile_name, start, end, config.tick_size, pd.DataFrame(), 0)

    level_step = detect_level_step(selected["price"].to_numpy(dtype=float), config.tick_size)
    selected["price_bin"] = np.rint(selected["price"] / level_step).astype("int64")
    grouped = selected.groupby("price_bin", sort=True).agg(
        volume=("volume", "sum"),
        bid_volume=("bid_volume", "sum"),
        ask_volume=("ask_volume", "sum"),
        observations=("price", "size"),
    )
    lo, hi = int(grouped.index.min()), int(grouped.index.max())
    full_index = pd.RangeIndex(lo, hi + 1, name="price_bin")
    levels = grouped.reindex(full_index, fill_value=0.0)
    levels["price"] = levels.index.to_numpy(dtype=float) * level_step
    levels["delta"] = levels["ask_volume"] - levels["bid_volume"]
    levels.attrs["tick_size"] = level_step

    prices = levels["price"].to_numpy(dtype=float)
    volumes = levels["volume"].to_numpy(dtype=float)
    moments = weighted_moments(prices, volumes)
    poc_bin = _choose_poc(levels, moments["center_of_mass"])
    va_low_bin, va_high_bin, actual_va_pct = _value_area(levels, poc_bin, config.value_area_pct)
    total = float(levels["volume"].sum())
    upper_volume = float(levels.loc[levels.index > poc_bin, "volume"].sum())
    lower_volume = float(levels.loc[levels.index < poc_bin, "volume"].sum())
    occupied = int((levels["volume"] > 0).sum())
    max_volume = float(levels["volume"].max())

    metrics: dict[str, object] = {
        "total_volume": total,
        "bid_volume": float(levels["bid_volume"].sum()),
        "ask_volume": float(levels["ask_volume"].sum()),
        "delta": float(levels["delta"].sum()),
        "poc": float(poc_bin * level_step),
        "poc_volume": float(levels.at[poc_bin, "volume"]),
        "vah": float(va_high_bin * level_step),
        "val": float(va_low_bin * level_step),
        "value_area_actual_pct": actual_va_pct,
        "high": float(hi * level_step),
        "low": float(lo * level_step),
        "level_step": level_step,
        "level_step_ticks": safe_div(level_step, config.tick_size),
        "profile_width_ticks": safe_div((hi - lo) * level_step, config.tick_size),
        "value_area_width_ticks": safe_div((va_high_bin - va_low_bin) * level_step, config.tick_size),
        "price_level_count": int(len(levels)),
        "occupied_price_level_count": occupied,
        "empty_level_count": int(len(levels) - occupied),
        "upper_volume": upper_volume,
        "lower_volume": lower_volume,
        "upper_lower_ratio": safe_div(upper_volume, lower_volume),
        "upper_volume_share": safe_div(upper_volume, total, 0.0),
        "lower_volume_share": safe_div(lower_volume, total, 0.0),
        "center_of_mass": moments["center_of_mass"],
        "skewness": moments["skewness"],
        "kurtosis_excess": moments["kurtosis_excess"],
        "entropy": normalized_entropy(volumes),
        "max_level_volume_share": safe_div(max_volume, total, 0.0),
        "volume_slope": linear_slope(volumes),
        "poc_position": safe_div(poc_bin - lo, max(1, hi - lo), 0.5),
        "center_of_mass_position": safe_div(
            moments["center_of_mass"] - lo * level_step,
            max(level_step, (hi - lo) * level_step),
            0.5,
        ),
        "source_rows": int(len(selected)),
    }
    return Profile(session_date, profile_name, start, end, level_step, levels, len(selected), metrics)


def flatten_profile(profile: Profile, prefix: str = "") -> dict[str, object]:
    base: dict[str, object] = {
        f"{prefix}profile_start": profile.start.isoformat(),
        f"{prefix}profile_end": profile.end.isoformat(),
        f"{prefix}has_data": profile.has_data,
        f"{prefix}hvn_count": len(profile.hvns),
        f"{prefix}lvn_count": len(profile.lvns),
        f"{prefix}hvn_prices": "|".join(f"{float(node['price']):.2f}" for node in profile.hvns),
        f"{prefix}lvn_prices": "|".join(f"{float(node['price']):.2f}" for node in profile.lvns),
    }
    base.update({f"{prefix}{key}": value for key, value in profile.metrics.items()})
    base.update({f"{prefix}{key}": value for key, value in profile.shape.items()})
    return base

