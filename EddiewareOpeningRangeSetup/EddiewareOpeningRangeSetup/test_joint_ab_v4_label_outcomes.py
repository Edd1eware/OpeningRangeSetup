from __future__ import annotations

import numpy as np
import pandas as pd

from joint_ab_v4_label_outcomes import (
    LABEL_A,
    LABEL_B,
    LABEL_C,
    classify_path,
)


THRESHOLDS = {
    "T_push_ticks": 2.0,
    "T_ext_ticks": 4.0,
    "T_ret_ticks": 2.0,
    "T_dwB_seconds": 0.4,
    "T_dwA_seconds": 0.5,
}


def _times(offsets):
    base = pd.Timestamp("2024-01-01T00:00:00Z")
    return pd.Series([base + pd.Timedelta(seconds=value) for value in offsets])


def test_breakout_requires_continuous_dwell() -> None:
    times = _times([0.1, 0.2, 0.7])
    prices = np.array([100.5, 101.0, 101.0])
    result = classify_path(
        times,
        prices,
        100.0,
        "BUY",
        pd.Timestamp("2024-01-01T00:00:01Z"),
        THRESHOLDS,
    )
    assert result["label"] == LABEL_B
    assert result["tau_B"] == pd.Timestamp("2024-01-01T00:00:00.6Z")


def test_absorption_requires_push_then_return_dwell() -> None:
    times = _times([0.1, 0.2, 0.8])
    prices = np.array([100.5, 99.5, 99.5])
    result = classify_path(
        times,
        prices,
        100.0,
        "BUY",
        pd.Timestamp("2024-01-01T00:00:01Z"),
        THRESHOLDS,
    )
    assert result["label"] == LABEL_A
    assert result["tau_A"] == pd.Timestamp("2024-01-01T00:00:00.7Z")


def test_no_push_is_variable() -> None:
    result = classify_path(
        _times([0.1, 0.9]),
        np.array([100.25, 100.0]),
        100.0,
        "BUY",
        pd.Timestamp("2024-01-01T00:00:01Z"),
        THRESHOLDS,
    )
    assert result["label"] == LABEL_C
