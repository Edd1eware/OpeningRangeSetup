from __future__ import annotations

import numpy as np
import pandas as pd

import ab_joint_calibrate_v2 as calibration


def test_grid_from_0829_gives_12_windows_for_0831_decision() -> None:
    windows = calibration.window_grid(
        "2024-07-16", "2024-07-16T13:31:00Z"
    )
    assert len(windows) == 12
    assert windows[0][0].tz_convert("America/Chicago").strftime(
        "%H:%M:%S"
    ) == "08:29:00"


def test_contiguous_dwell_resets_after_leaving_threshold() -> None:
    base = pd.Timestamp("2024-01-01T00:00:00Z").value
    times = base + np.asarray(
        [0, 100_000_000, 200_000_000, 500_000_000], dtype=np.int64
    )
    values = np.asarray([2.0, 2.0, 0.0, 2.0])
    dwell, crossed = calibration.max_contiguous_dwell_seconds(
        times, values, 1.0, "above", base + 900_000_000
    )
    assert crossed
    assert abs(dwell - 0.4) < 1e-12


def test_same_timestamp_intermediate_state_has_zero_dwell_and_resets() -> None:
    base = pd.Timestamp("2024-01-01T00:00:00Z").value
    times = base + np.asarray([0, 100_000_000, 100_000_000], dtype=np.int64)
    values = np.asarray([2.0, 0.0, 2.0])
    dwell, crossed = calibration.max_contiguous_dwell_seconds(
        times, values, 1.0, "above", base + 300_000_000
    )
    assert crossed
    assert abs(dwell - 0.2) < 1e-12


def test_dual_orientation_has_symmetric_crossing_support() -> None:
    base = pd.Timestamp("2024-01-01T00:00:00Z").value
    path = calibration.WindowPath(
        fecha="2024-01-01",
        start_ns=base,
        end_ns=base + 5_000_000_000,
        p0=100.0,
        event_ns=base
        + np.asarray([1_000_000_000, 2_000_000_000], dtype=np.int64),
        raw_ticks=np.asarray([-2.0, -3.0]),
    )
    dwell, crossed = calibration.max_contiguous_dwell_seconds(
        path.event_ns, -path.raw_ticks, 2.0, "above", path.end_ns
    )
    assert crossed
    assert abs(dwell - 4.0) < 1e-12
