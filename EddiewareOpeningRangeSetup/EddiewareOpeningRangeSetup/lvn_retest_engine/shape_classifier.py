from __future__ import annotations

import math

import numpy as np

from .config import ResearchConfig
from .profile_builder import Profile
from .statistics import clamp01, sigmoid


SHAPES = ("D", "P", "b", "double", "trend_up", "trend_down", "unknown")


def _mode_structure(profile: Profile) -> tuple[int, float, float]:
    if profile.levels.empty:
        return 0, 0.0, 0.0
    volumes = profile.levels["volume"].to_numpy(dtype=float)
    if len(volumes) < 3 or volumes.max() <= 0:
        return int(volumes.max() > 0), 0.0, 0.0
    smoothed = np.convolve(volumes, np.array([0.25, 0.5, 0.25]), mode="same")
    peak_floor = float(smoothed.max()) * 0.35
    peaks = [
        i for i in range(1, len(smoothed) - 1)
        if smoothed[i] >= smoothed[i - 1] and smoothed[i] > smoothed[i + 1] and smoothed[i] >= peak_floor
    ]
    if not peaks:
        peaks = [int(np.argmax(smoothed))]
    peaks = sorted(peaks, key=lambda i: (-smoothed[i], i))[:3]
    separation = 0.0
    valley_depth = 0.0
    if len(peaks) >= 2:
        a, b = sorted(peaks[:2])
        separation = (b - a) / max(1, len(smoothed) - 1)
        valley = float(smoothed[a : b + 1].min())
        weaker_peak = float(min(smoothed[a], smoothed[b]))
        valley_depth = clamp01(1.0 - valley / max(weaker_peak, 1e-12))
    return min(3, len(peaks)), float(separation), float(valley_depth)


def classify_shape(profile: Profile, config: ResearchConfig) -> dict[str, object]:
    if not profile.has_data:
        return {
            "profile_shape": "unknown",
            "shape_confidence_score": 1.0,
            **{f"prob_{shape}": 1.0 if shape == "unknown" else 0.0 for shape in SHAPES},
            "distribution_count": 0,
            "double_mode_separation": 0.0,
            "double_valley_depth": 0.0,
            "shape_probability_type": "MATHEMATICAL_PROTOTYPE_NOT_CALIBRATED",
        }

    metrics = profile.metrics
    upper = float(metrics.get("upper_volume_share", 0.0))
    lower = float(metrics.get("lower_volume_share", 0.0))
    poc_position = float(metrics.get("poc_position", 0.5))
    mean_position = float(metrics.get("center_of_mass_position", 0.5))
    skew = float(metrics.get("skewness", 0.0))
    slope = float(metrics.get("volume_slope", 0.0))
    entropy = float(metrics.get("entropy", 0.0))
    distributions, separation, valley_depth = _mode_structure(profile)

    balance = math.exp(-abs(math.log((upper + 1e-9) / (lower + 1e-9))))
    centered = math.exp(-abs(poc_position - 0.5) / 0.20)
    symmetric = math.exp(-abs(skew) / 0.85)
    single_mode = 1.0 if distributions == 1 else 0.35 if distributions == 2 else 0.10
    upper_heavy = sigmoid((upper - lower - 0.08) / 0.06)
    lower_heavy = sigmoid((lower - upper - 0.08) / 0.06)
    top_location = sigmoid((poc_position - 0.57) / 0.08)
    bottom_location = sigmoid((0.43 - poc_position) / 0.08)
    positive_slope = sigmoid((slope - 0.08) / 0.08)
    negative_slope = sigmoid((-slope - 0.08) / 0.08)

    scores = {
        "D": clamp01(balance * centered * symmetric * single_mode),
        "P": clamp01(upper_heavy * top_location * (0.55 + 0.45 * clamp01(-skew / 2.0)) * single_mode),
        "b": clamp01(lower_heavy * bottom_location * (0.55 + 0.45 * clamp01(skew / 2.0)) * single_mode),
        "double": clamp01((1.0 if distributions >= 2 else 0.0) * separation * 2.0 * valley_depth),
        "trend_up": clamp01(positive_slope * sigmoid((mean_position - 0.53) / 0.08) * (0.6 + 0.4 * entropy)),
        "trend_down": clamp01(negative_slope * sigmoid((0.47 - mean_position) / 0.08) * (0.6 + 0.4 * entropy)),
    }
    strongest = max(scores.values(), default=0.0)
    scores["unknown"] = clamp01(0.65 - strongest + 0.25 * (1.0 - entropy))

    temperature = max(0.05, config.shape_temperature)
    logits = np.array([scores[shape] / temperature for shape in SHAPES], dtype=float)
    logits -= logits.max()
    probabilities = np.exp(logits)
    probabilities /= probabilities.sum()
    probability_map = {shape: float(probabilities[i]) for i, shape in enumerate(SHAPES)}
    winner = max(SHAPES, key=lambda shape: (probability_map[shape], -SHAPES.index(shape)))
    return {
        "profile_shape": winner,
        "shape_confidence_score": probability_map[winner],
        **{f"prob_{shape}": probability_map[shape] for shape in SHAPES},
        "distribution_count": distributions,
        "double_mode_separation": separation,
        "double_valley_depth": valley_depth,
        "shape_probability_type": "MATHEMATICAL_PROTOTYPE_NOT_CALIBRATED",
    }

