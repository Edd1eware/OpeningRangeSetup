from __future__ import annotations

import databento as db
import pandas as pd
import pytest

from mbo_snapshot_discovery_research import extract_snapshot_features


LAST = int(db.RecordFlags.F_LAST)


def _row(
    timestamp: pd.Timestamp,
    action: str,
    side: str,
    price: float,
    size: int,
    order_id: int,
    *,
    flags: int = 0,
) -> dict[str, object]:
    return {
        "ts_event": timestamp,
        "action": action,
        "side": side,
        "price": price,
        "size": size,
        "order_id": order_id,
        "flags": flags,
    }


def _manifest_row() -> pd.Series:
    return pd.Series(
        {
            "request_id": "synthetic",
            "BurstId": "LB_SYNTHETIC",
            "fecha": "2022-04-05",
            "year": 2022,
            "burst_side": "BUY",
            "resolved_raw_symbol": "NQM2",
            "burst_timestamp_utc": "2022-04-05T13:32:00.000Z",
            "strict_feature_cutoff_utc_exclusive": (
                "2022-04-05T13:32:00.600Z"
            ),
        }
    )


def _snapshot(start: pd.Timestamp, l0_size: int = 100) -> list[dict[str, object]]:
    timestamp = start - pd.Timedelta(seconds=1)
    return [
        _row(timestamp, "R", "N", 0.0, 0, 0),
        _row(timestamp, "A", "B", 99.75, 100, 10),
        _row(timestamp, "A", "A", 100.00, l0_size, 1),
        _row(timestamp, "A", "A", 100.25, 100, 2),
        _row(timestamp, "A", "A", 100.50, 100, 3, flags=LAST),
    ]


def test_fill_refill_hold_is_absorption_motif() -> None:
    start = pd.Timestamp("2022-04-05T13:32:00Z")
    event = start + pd.Timedelta(milliseconds=10)
    rows = _snapshot(start)
    rows.extend(
        [
            _row(event, "T", "B", 100.0, 40, 100),
            _row(event, "F", "A", 100.0, 40, 1),
            _row(event, "C", "A", 100.0, 40, 1),
            _row(event, "A", "A", 100.0, 40, 5, flags=LAST),
            _row(
                start + pd.Timedelta(milliseconds=490),
                "A",
                "B",
                98.0,
                1,
                20,
                flags=LAST,
            ),
        ]
    )
    frame = pd.DataFrame(rows)
    result = extract_snapshot_features(frame, _manifest_row())

    assert result["consumption_initial_depth_ratio_250ms"] == pytest.approx(
        40 / 300
    )
    assert result["withdrawal_initial_depth_ratio_250ms"] == 0
    assert result["durable_refill_removed_ratio_250ms"] == 1
    assert result["initial_queue_survival_ratio_250ms"] == pytest.approx(
        260 / 300
    )
    assert result["impact_efficiency_250ms"] == 0
    assert result["depletion_persistence_share_500ms"] == 0
    assert result["absorption_motif_share_500ms"] == 1
    assert result["breakout_motif_share_500ms"] == 0


def test_pure_cancel_deplete_advance_is_breakout_motif() -> None:
    start = pd.Timestamp("2022-04-05T13:32:00Z")
    rows = _snapshot(start, l0_size=10)
    rows.extend(
        [
            _row(
                start + pd.Timedelta(milliseconds=10),
                "C",
                "A",
                100.0,
                10,
                1,
                flags=LAST,
            ),
            _row(
                start + pd.Timedelta(milliseconds=120),
                "A",
                "B",
                98.0,
                1,
                20,
                flags=LAST,
            ),
            _row(
                start + pd.Timedelta(milliseconds=490),
                "A",
                "B",
                97.75,
                1,
                21,
                flags=LAST,
            ),
        ]
    )
    frame = pd.DataFrame(rows)
    result = extract_snapshot_features(frame, _manifest_row())

    assert result["consumption_initial_depth_ratio_250ms"] == 0
    assert result["withdrawal_initial_depth_ratio_250ms"] == pytest.approx(
        10 / 210
    )
    assert result["durable_refill_removed_ratio_250ms"] == 0
    assert result["initial_queue_survival_ratio_250ms"] == pytest.approx(
        200 / 210
    )
    assert result["directional_best_passive_progress_ticks_250ms"] == 1
    assert result["depletion_persistence_share_500ms"] > 0.9
    assert result["absorption_motif_share_500ms"] == 0
    assert result["breakout_motif_share_500ms"] == 1
