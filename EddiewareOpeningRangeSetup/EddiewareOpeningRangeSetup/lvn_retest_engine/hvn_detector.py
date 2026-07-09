from __future__ import annotations

import math

import numpy as np

from .config import ResearchConfig
from .profile_builder import Profile
from .statistics import safe_div


def detect_hvns(profile: Profile, config: ResearchConfig) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not profile.has_data:
        return [], [{"candidate_type": "HVN", "status": "REJECTED", "reason": "NO_PROFILE_DATA"}]
    levels = profile.levels
    n = config.hvn_neighbor_levels
    bins = levels.index.to_numpy(dtype=int)
    volumes = levels["volume"].to_numpy(dtype=float)
    debug: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []

    for i, price_bin in enumerate(bins):
        volume = float(volumes[i])
        row: dict[str, object] = {
            "candidate_type": "HVN",
            "price": float(price_bin * config.tick_size),
            "price_bin": int(price_bin),
            "volume": volume,
            "status": "REJECTED",
        }
        if i < n or i >= len(bins) - n:
            row["reason"] = "INSUFFICIENT_NEIGHBORS"
            debug.append(row)
            continue
        left_mean = float(volumes[i - n : i].mean())
        right_mean = float(volumes[i + 1 : i + n + 1].mean())
        stronger_neighbor_mean = max(left_mean, right_mean)
        ratio = safe_div(volume, stronger_neighbor_mean)
        reasons: list[str] = []
        if volume <= left_mean or volume <= right_mean:
            reasons.append("NOT_HIGHER_THAN_BOTH_SIDES")
        if math.isfinite(ratio) and ratio < config.hvn_min_percent_of_neighbors:
            reasons.append("BELOW_NEIGHBOR_MULTIPLE")
        if volume < config.min_hvn_volume:
            reasons.append("BELOW_MIN_HVN_VOLUME")
        row.update({
            "left_neighbor_mean": left_mean,
            "right_neighbor_mean": right_mean,
            "volume_multiple_of_neighbors": ratio,
        })
        if reasons:
            row["reason"] = "|".join(reasons)
        else:
            half_height = volume * 0.5
            left_i = i
            right_i = i
            while left_i > 0 and volumes[left_i - 1] >= half_height:
                left_i -= 1
            while right_i < len(volumes) - 1 and volumes[right_i + 1] >= half_height:
                right_i += 1
            row.update({
                "status": "ACCEPTED",
                "reason": "QUALIFIED",
                "width_ticks": int(right_i - left_i + 1),
                "low_price": float(bins[left_i] * config.tick_size),
                "high_price": float(bins[right_i] * config.tick_size),
                "prominence": 1.0 - safe_div(stronger_neighbor_mean, volume, 1.0),
            })
            candidates.append(row)
        debug.append(row)

    # Suppress overlapping half-height peaks deterministically, retaining the larger peak.
    selected: list[dict[str, object]] = []
    for candidate in sorted(candidates, key=lambda row: (-float(row["volume"]), float(row["price"]))):
        overlaps = any(
            float(candidate["low_price"]) <= float(node["high_price"])
            and float(candidate["high_price"]) >= float(node["low_price"])
            for node in selected
        )
        if not overlaps:
            selected.append(candidate)
    selected.sort(key=lambda row: float(row["price"]))
    for index, node in enumerate(selected, start=1):
        node["hvn_id"] = f"{profile.profile_name}_HVN_{index:02d}"
    return selected, debug

