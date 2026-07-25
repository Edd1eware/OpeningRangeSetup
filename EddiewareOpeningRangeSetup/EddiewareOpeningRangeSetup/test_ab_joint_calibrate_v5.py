from __future__ import annotations

import numpy as np

import ab_joint_calibrate_v2 as common
from ab_joint_calibrate_v5 import (
    _max_dwell_after,
    calibrate_thresholds_v5,
)


def test_dwell_requires_sequence_start() -> None:
    event_ns = np.array([0, 1, 2, 3], dtype=np.int64) * 1_000_000_000
    values = np.array([-5.0, 2.0, -3.0, -3.0])
    dwell, crossed = _max_dwell_after(
        event_ns, values, 2, 3.0, "below", 4_000_000_000
    )
    assert crossed
    assert dwell == 2.0


def test_oriented_distribution_has_two_observations() -> None:
    path = common.WindowPath(
        fecha="2024-01-01",
        start_ns=0,
        end_ns=5_000_000_000,
        p0=100.0,
        event_ns=np.array([0, 1, 2, 3]) * 1_000_000_000,
        raw_ticks=np.array([4.0, 5.0, -5.0, -5.0]),
    )
    thresholds, metrics = calibrate_thresholds_v5([path] * 120)
    assert thresholds["oriented_observation_count"] == 240
    assert len(metrics) == 240
    assert thresholds["T_ext_ticks"] >= thresholds["T_push_ticks"]
    assert thresholds["dwell_B_oriented_sequence_support"] >= 100
    assert thresholds["dwell_A_oriented_sequence_support"] >= 100
