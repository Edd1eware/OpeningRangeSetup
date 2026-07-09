from __future__ import annotations

import math

import numpy as np

from .config import ResearchConfig
from .profile_builder import Profile
from .statistics import safe_div


def _group_adjacent(indices: list[int]) -> list[list[int]]:
    if not indices:
        return []
    groups: list[list[int]] = [[indices[0]]]
    for index in indices[1:]:
        if index == groups[-1][-1] + 1:
            groups[-1].append(index)
        else:
            groups.append([index])
    return groups


def detect_lvns(profile: Profile, config: ResearchConfig) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not profile.has_data:
        return [], [{"candidate_type": "LVN", "status": "REJECTED", "reason": "NO_PROFILE_DATA"}]
    levels = profile.levels
    total = float(profile.metrics["total_volume"])
    poc = float(profile.metrics["poc"])
    poc_volume = float(profile.metrics["poc_volume"])
    n = config.lvn_neighbor_levels
    level_step = profile.tick_size  # native price grid detected for this profile
    levels_per_tick = safe_div(level_step, config.tick_size, 1.0)
    debug: list[dict[str, object]] = []
    accepted_indices: list[int] = []
    diagnostics: dict[int, dict[str, object]] = {}

    if total < config.min_total_volume_at_profile:
        return [], [{
            "candidate_type": "LVN",
            "status": "REJECTED",
            "reason": "PROFILE_VOLUME_BELOW_MINIMUM",
            "profile_total_volume": total,
            "required_total_volume": config.min_total_volume_at_profile,
        }]

    bins = levels.index.to_numpy(dtype=int)
    volumes = levels["volume"].to_numpy(dtype=float)
    for i, price_bin in enumerate(bins):
        volume = float(volumes[i])
        row: dict[str, object] = {
            "candidate_type": "LVN",
            "price": float(price_bin * level_step),
            "price_bin": int(price_bin),
            "volume": volume,
            "status": "REJECTED",
        }
        if i < n or i >= len(bins) - n:
            row["reason"] = "INSUFFICIENT_NEIGHBORS"
            debug.append(row)
            continue
        left = volumes[i - n : i]
        right = volumes[i + 1 : i + n + 1]
        left_mean, right_mean = float(left.mean()), float(right.mean())
        weaker_neighbor_mean = min(left_mean, right_mean)
        neighbor_ratio = safe_div(volume, weaker_neighbor_mean)
        depth = 1.0 - neighbor_ratio if math.isfinite(neighbor_ratio) else math.nan
        row.update({
            "left_neighbor_mean": left_mean,
            "right_neighbor_mean": right_mean,
            "weaker_neighbor_mean": weaker_neighbor_mean,
            "volume_percent_of_neighbors": neighbor_ratio,
            "depth": depth,
            "volume_percent_of_poc": safe_div(volume, poc_volume),
        })
        reasons: list[str] = []
        if weaker_neighbor_mean <= 0:
            reasons.append("NEIGHBORS_HAVE_NO_VOLUME")
        if volume >= left_mean or volume >= right_mean:
            reasons.append("NOT_LOWER_THAN_BOTH_SIDES")
        if math.isfinite(neighbor_ratio) and neighbor_ratio > config.lvn_max_percent_of_neighbors:
            reasons.append("ABOVE_NEIGHBOR_PERCENT_LIMIT")
        if volume < config.min_lvn_volume:
            reasons.append("BELOW_MIN_LVN_VOLUME")
        if poc_volume > 0 and volume > poc_volume * config.max_lvn_volume_percent_of_poc:
            reasons.append("ABOVE_POC_PERCENT_LIMIT")
        if reasons:
            row["reason"] = "|".join(reasons)
        else:
            row["status"] = "ACCEPTED"
            row["reason"] = "QUALIFIED"
            accepted_indices.append(i)
            diagnostics[i] = row
        debug.append(row)

    nodes: list[dict[str, object]] = []
    for node_number, group in enumerate(_group_adjacent(accepted_indices), start=1):
        representative = min(
            group,
            key=lambda i: (volumes[i], abs(float(bins[i] * level_step) - poc), bins[i]),
        )
        diag = diagnostics[representative]
        low_bin, high_bin = int(bins[group[0]]), int(bins[group[-1]])
        price = float(bins[representative] * level_step)
        nodes.append({
            "lvn_id": f"{profile.profile_name}_LVN_{node_number:02d}",
            "price": price,
            "volume": float(volumes[representative]),
            "depth": float(diag["depth"]),
            "width_ticks": round((high_bin - low_bin + 1) * levels_per_tick),
            "low_price": float(low_bin * level_step),
            "high_price": float(high_bin * level_step),
            "left_neighbor_mean": float(diag["left_neighbor_mean"]),
            "right_neighbor_mean": float(diag["right_neighbor_mean"]),
            "volume_percent_of_neighbors": float(diag["volume_percent_of_neighbors"]),
            "volume_percent_of_poc": safe_div(float(volumes[representative]), poc_volume),
            "distance_to_poc_ticks": (price - poc) / config.tick_size,
            "distance_to_vah_ticks": (price - float(profile.metrics["vah"])) / config.tick_size,
            "distance_to_val_ticks": (price - float(profile.metrics["val"])) / config.tick_size,
            "member_level_count": len(group),
        })
    return nodes, debug

