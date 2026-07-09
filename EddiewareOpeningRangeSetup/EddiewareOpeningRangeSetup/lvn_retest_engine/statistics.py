from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np


def safe_div(numerator: float, denominator: float, default: float = math.nan) -> float:
    if denominator == 0 or not np.isfinite(denominator):
        return default
    return float(numerator / denominator)


def clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def weighted_moments(prices: np.ndarray, volumes: np.ndarray) -> dict[str, float]:
    total = float(np.sum(volumes))
    if total <= 0 or prices.size == 0:
        return {
            "center_of_mass": math.nan,
            "variance": math.nan,
            "skewness": math.nan,
            "kurtosis_excess": math.nan,
        }
    mean = float(np.sum(prices * volumes) / total)
    centered = prices - mean
    variance = float(np.sum(volumes * centered**2) / total)
    if variance <= 0:
        return {
            "center_of_mass": mean,
            "variance": variance,
            "skewness": 0.0,
            "kurtosis_excess": -3.0,
        }
    sigma = math.sqrt(variance)
    skew = float(np.sum(volumes * (centered / sigma) ** 3) / total)
    kurtosis = float(np.sum(volumes * (centered / sigma) ** 4) / total - 3.0)
    return {
        "center_of_mass": mean,
        "variance": variance,
        "skewness": skew,
        "kurtosis_excess": kurtosis,
    }


def normalized_entropy(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    total = float(values.sum())
    positive = values[values > 0]
    if total <= 0 or positive.size <= 1:
        return 0.0
    probabilities = positive / total
    return float(-np.sum(probabilities * np.log(probabilities)) / math.log(len(values)))


def linear_slope(values: Iterable[float]) -> float:
    y = np.asarray(list(values), dtype=float)
    if y.size < 2 or np.allclose(y, y[0]):
        return 0.0
    x = np.linspace(-1.0, 1.0, y.size)
    scale = float(np.max(np.abs(y)))
    if scale <= 0:
        return 0.0
    return float(np.polyfit(x, y / scale, 1)[0])


def first_touch_result(
    times: np.ndarray,
    favorable: np.ndarray,
    adverse: np.ndarray,
    target_ticks: int,
) -> tuple[str, float, int]:
    tp_idx = np.flatnonzero(favorable >= target_ticks)
    sl_idx = np.flatnonzero(adverse >= target_ticks)
    if tp_idx.size == 0 and sl_idx.size == 0:
        return "NONE", math.nan, -1
    if tp_idx.size and sl_idx.size:
        tp_i, sl_i = int(tp_idx[0]), int(sl_idx[0])
        if times[tp_i] == times[sl_i]:
            return "AMBIGUOUS", float(times[tp_i]), tp_i
        return ("TP", float(times[tp_i]), tp_i) if times[tp_i] < times[sl_i] else ("SL", float(times[sl_i]), sl_i)
    if tp_idx.size:
        return "TP", float(times[int(tp_idx[0])]), int(tp_idx[0])
    return "SL", float(times[int(sl_idx[0])]), int(sl_idx[0])

