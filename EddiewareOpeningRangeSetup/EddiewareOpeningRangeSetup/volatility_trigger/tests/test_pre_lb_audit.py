from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from volatility_trigger.src.pre_lb_audit import (
    NO_PRIOR_DEPTH,
    ONE_SIDED_BOOK,
    SPREAD_GT_4,
    SPREAD_LE_0,
    STALE_DEPTH_GT_250MS,
    VALID,
    IncrementalL2Book,
    audit_book_session,
    causal_profile_snapshots,
    classify_reference,
    cluster_bursts,
    forbidden_output_columns,
    level_viability,
    profile_diagnostics,
    profile_snapshot,
)
from volatility_trigger.src.vt_core import (
    LiquidityBurst,
    TICKS_PER_MILLISECOND,
    TICKS_PER_SECOND,
)


ROW_DTYPE = np.dtype(
    [
        ("ticks", "<i8"),
        ("side_code", "u1"),
        ("price_raw", "<i4"),
        ("volume_raw", "<u4"),
    ]
)


def _rows(values: list[tuple[int, int, int, int]]) -> np.ndarray:
    return np.asarray(values, dtype=ROW_DTYPE)


def _burst(
    *,
    lb_id: str = "LB_TEST",
    cut: int = 2 * TICKS_PER_SECOND,
    publish: int = 2 * TICKS_PER_SECOND + 100 * TICKS_PER_MILLISECOND,
    side: str = "BUY",
    direction: int = 1,
) -> LiquidityBurst:
    return LiquidityBurst(
        lb_id=lb_id,
        session_date="2022-08-01",
        source_second_ticks=cut,
        publish_ticks=publish,
        side=side,
        direction=direction,
        price_raw=101,
        delta_1s=150 * direction,
        delta_3s=200 * direction,
        delta_change_1s=100 * direction,
        delta_change_zscore=3.0 * direction,
        delta_percentile=0.99,
        trades_per_second=10,
        contracts_per_second=200,
        velocity_1s=2.0 * direction,
        acceleration_1s=1.0 * direction,
        cumulative_delta=250 * direction,
    )


def test_profile_excludes_cut_and_future_volume() -> None:
    cut = 10 * TICKS_PER_SECOND
    base = _rows(
        [
            (cut - 2, 1, 100, 10),
            (cut - 1, 2, 101, 20),
            (cut, 1, 500, 1_000_000),
            (cut + 1, 1, 600, 1_000_000),
        ]
    )
    ticks = base["ticks"].astype(np.int64)
    snapshot = causal_profile_snapshots(
        base,
        ticks,
        [cut],
        rth_start_ticks=0,
        value_area_fraction=0.70,
    )[cut]
    assert snapshot is not None
    assert snapshot.total_volume == 30
    assert snapshot.poc_raw == 101
    assert snapshot.last_trade_raw == 101


def test_profile_tie_seed_is_deterministic_and_symmetric() -> None:
    snapshot = profile_snapshot(
        {99: 10.0, 100: 1.0, 101: 10.0},
        target_ticks=123,
        last_trade_raw=100,
        trade_count=3,
        value_area_fraction=0.70,
    )
    assert snapshot is not None
    assert snapshot.poc_raw == 100.0
    assert snapshot.poc_tie_count == 2
    assert snapshot.poc_candidate_span_ticks == 2
    assert snapshot.val_raw == 99
    assert snapshot.vah_raw == 101
    assert snapshot.va_tie_steps == 0
    assert math.isclose(snapshot.poc_volume_share, 10 / 21)

    mirrored = profile_snapshot(
        {-101: 10.0, -100: 1.0, -99: 10.0},
        target_ticks=123,
        last_trade_raw=-100,
        trade_count=3,
        value_area_fraction=0.70,
    )
    assert mirrored is not None
    assert mirrored.poc_raw == -snapshot.poc_raw
    assert mirrored.val_raw == -snapshot.vah_raw
    assert mirrored.vah_raw == -snapshot.val_raw


def test_profile_drift_before_anchor_is_missing_not_imputed() -> None:
    cut = 120 * TICKS_PER_SECOND
    trades = _rows(
        [
            (10 * TICKS_PER_SECOND, 1, 100, 10),
            (cut - 1, 1, 101, 20),
        ]
    )
    frame = profile_diagnostics(
        trades,
        trades["ticks"].astype(np.int64),
        [_burst(cut=cut, publish=cut + 1)],
        rth_start_ticks=0,
        drift_seconds=300,
        value_area_fraction=0.70,
    )
    row = frame.iloc[0]
    assert bool(row["profile_raw_available"])
    assert not bool(row["PRF_PocDrift_ticks_300s_available"])
    assert math.isnan(float(row["PRF_PocDrift_ticks_300s"]))


def test_incremental_level_does_not_expire_by_individual_age() -> None:
    book = IncrementalL2Book()
    book.update_group(
        _rows([(0, 0, 100, 10), (0, 1, 101, 20)]),
        ticks=0,
        maximum_recent_age_ticks=250 * TICKS_PER_MILLISECOND,
    )
    book.expire_recent(
        10 * TICKS_PER_SECOND,
        250 * TICKS_PER_MILLISECOND,
    )
    assert book.counts() == (1, 1)
    assert book.recent_counts_at(
        10 * TICKS_PER_SECOND,
        250 * TICKS_PER_MILLISECOND,
    ) == (0, 0)

    book.update_group(
        _rows([(11 * TICKS_PER_SECOND, 0, 100, 0)]),
        ticks=11 * TICKS_PER_SECOND,
        maximum_recent_age_ticks=250 * TICKS_PER_MILLISECOND,
    )
    assert book.counts() == (0, 1)


def test_book_reason_covers_crossed_and_wide_spread() -> None:
    crossed = IncrementalL2Book()
    crossed.update_group(
        _rows([(0, 0, 102, 10), (0, 1, 101, 10)]),
        ticks=0,
        maximum_recent_age_ticks=250 * TICKS_PER_MILLISECOND,
    )
    assert crossed.reason(1, 4) == SPREAD_LE_0

    wide = IncrementalL2Book()
    wide.update_group(
        _rows([(0, 0, 100, 10), (0, 1, 110, 10)]),
        ticks=0,
        maximum_recent_age_ticks=250 * TICKS_PER_MILLISECOND,
    )
    assert wide.reason(1, 4) == SPREAD_GT_4


def test_missingness_precedence_invalid_before_stale() -> None:
    status, age_ms = classify_reference(
        has_prior_depth=True,
        state_reason=ONE_SIDED_BOOK,
        at_ticks=TICKS_PER_SECOND,
        last_group_ticks=0,
        maximum_age_ticks=250 * TICKS_PER_MILLISECOND,
    )
    assert status == ONE_SIDED_BOOK
    assert age_ms == 1000

    status, _ = classify_reference(
        has_prior_depth=True,
        state_reason=VALID,
        at_ticks=TICKS_PER_SECOND,
        last_group_ticks=0,
        maximum_age_ticks=250 * TICKS_PER_MILLISECOND,
    )
    assert status == STALE_DEPTH_GT_250MS


def _book_audit(
    depth: np.ndarray,
    burst: LiquidityBurst,
    *,
    end_ticks: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    missing, pre, _, _, _ = audit_book_session(
        session_date="2022-08-01",
        depth=depth,
        effective_ticks=depth["ticks"].astype(np.int64),
        bursts=[burst],
        load_start_ticks=0,
        rth_start_ticks=0,
        rth_end_ticks=end_ticks,
        load_end_ticks=end_ticks,
        minimum_spread=1,
        maximum_spread=4,
        maximum_age_ms=250.0,
        pre_windows_seconds=[1],
        level_ks=[1],
        far_level_ticks=50,
        startup_minutes=0,
        eligible=True,
    )
    return missing, pre


def test_reference_before_first_group_is_no_prior_depth() -> None:
    first_group = TICKS_PER_SECOND
    depth = _rows(
        [
            (first_group, 0, 100, 10),
            (first_group, 1, 101, 10),
        ]
    )
    burst = _burst(
        cut=500 * TICKS_PER_MILLISECOND,
        publish=500 * TICKS_PER_MILLISECOND,
    )
    missing, _ = _book_audit(
        depth,
        burst,
        end_ticks=2 * TICKS_PER_SECOND,
    )
    assert missing.iloc[0]["reference_status"] == NO_PRIOR_DEPTH


def test_reference_at_group_tick_includes_group() -> None:
    group = TICKS_PER_SECOND
    depth = _rows(
        [
            (group, 0, 100, 10),
            (group, 1, 101, 10),
        ]
    )
    burst = _burst(cut=group, publish=group)
    missing, _ = _book_audit(
        depth,
        burst,
        end_ticks=2 * TICKS_PER_SECOND,
    )
    assert missing.iloc[0]["reference_status"] == VALID


def test_pre_window_at_group_tick_excludes_group() -> None:
    cut = 2 * TICKS_PER_SECOND
    values: list[tuple[int, int, int, int]] = []
    for index in range(21):
        ticks = index * 100 * TICKS_PER_MILLISECOND
        values.append((ticks, 0, 100, 10 + index % 2))
        values.append((ticks, 1, 101, 20 + index % 2))
    values.append((cut, 1, 101, 0))
    depth = _rows(values)
    burst = _burst(cut=cut, publish=cut)
    _, pre = _book_audit(
        depth,
        burst,
        end_ticks=3 * TICKS_PER_SECOND,
    )
    assert bool(pre.iloc[0]["book_fresh_valid_full_pre_1s"])


def test_book_audit_uses_strict_pre_window_and_causal_reference() -> None:
    rows: list[tuple[int, int, int, int]] = []
    for index in range(31):
        ticks = index * 100 * TICKS_PER_MILLISECOND
        rows.append((ticks, 0, 100, 10 + index % 2))
        rows.append((ticks, 1, 101, 20 + index % 2))
    depth = _rows(rows)
    effective = depth["ticks"].astype(np.int64)
    burst = _burst()
    missing, pre, depth_frame, startup, session = audit_book_session(
        session_date="2022-08-01",
        depth=depth,
        effective_ticks=effective,
        bursts=[burst],
        load_start_ticks=0,
        rth_start_ticks=0,
        rth_end_ticks=3 * TICKS_PER_SECOND,
        load_end_ticks=3 * TICKS_PER_SECOND,
        minimum_spread=1,
        maximum_spread=4,
        maximum_age_ms=250.0,
        pre_windows_seconds=[1, 5, 30],
        level_ks=[1, 3],
        far_level_ticks=50,
        startup_minutes=0,
        eligible=True,
    )
    assert missing.iloc[0]["reference_status"] == VALID
    assert bool(pre.iloc[0]["book_fresh_valid_full_pre_1s"])
    assert not bool(pre.iloc[0]["book_fresh_valid_full_pre_5s"])
    assert depth_frame.loc[depth_frame["k"].eq(1), "both_ge_k_fraction"].iloc[0] == 1
    assert depth_frame.loc[depth_frame["k"].eq(3), "both_ge_k_fraction"].iloc[0] == 0
    assert len(startup) == 1
    assert session["fresh_valid_fraction"] > 0.99


def test_profile_diagnostics_full_mirror_is_invariant() -> None:
    pivot = 48_000
    cut = 400 * TICKS_PER_SECOND
    values = [
        (10 * TICKS_PER_SECOND, 1, 47_990, 10),
        (20 * TICKS_PER_SECOND, 2, 47_992, 20),
        (200 * TICKS_PER_SECOND, 1, 47_995, 40),
        (cut - 1, 1, 47_996, 5),
    ]
    original = _rows(values)
    reflected = _rows(
        [
            (ticks, side, 2 * pivot - price, volume)
            for ticks, side, price, volume in values
        ]
    )
    buy = profile_diagnostics(
        original,
        original["ticks"].astype(np.int64),
        [_burst(cut=cut, publish=cut + 1, side="BUY", direction=1)],
        rth_start_ticks=0,
        drift_seconds=300,
        value_area_fraction=0.70,
    ).iloc[0]
    sell = profile_diagnostics(
        reflected,
        reflected["ticks"].astype(np.int64),
        [_burst(cut=cut, publish=cut + 1, side="SELL", direction=-1)],
        rth_start_ticks=0,
        drift_seconds=300,
        value_area_fraction=0.70,
    ).iloc[0]
    for column in [
        "PRF_PocSignedDistance_ticks",
        "PRF_PocSide_Favor",
        "PRF_VaSignedPositionNorm",
        "PRF_InsideValueArea",
        "PRF_VaWidth_ticks",
        "PRF_PocDrift_ticks_300s",
        "PRF_PocVolumeShare",
        "PRF_ProfileEntropyNorm",
    ]:
        assert math.isclose(float(buy[column]), float(sell[column]))
    assert sell["profile_poc_raw"] == 2 * pivot - buy["profile_poc_raw"]
    assert sell["profile_val_raw"] == 2 * pivot - buy["profile_vah_raw"]
    assert sell["profile_vah_raw"] == 2 * pivot - buy["profile_val_raw"]


def test_profile_diagnostics_direction_only_flip_has_declared_signs() -> None:
    cut = 400 * TICKS_PER_SECOND
    trades = _rows(
        [
            (10 * TICKS_PER_SECOND, 1, 100, 10),
            (20 * TICKS_PER_SECOND, 2, 101, 20),
            (200 * TICKS_PER_SECOND, 1, 103, 40),
            (cut - 1, 1, 102, 5),
        ]
    )
    buy = profile_diagnostics(
        trades,
        trades["ticks"].astype(np.int64),
        [_burst(cut=cut, publish=cut + 1, side="BUY", direction=1)],
        rth_start_ticks=0,
        drift_seconds=300,
        value_area_fraction=0.70,
    ).iloc[0]
    sell = profile_diagnostics(
        trades,
        trades["ticks"].astype(np.int64),
        [_burst(cut=cut, publish=cut + 1, side="SELL", direction=-1)],
        rth_start_ticks=0,
        drift_seconds=300,
        value_area_fraction=0.70,
    ).iloc[0]
    for column in [
        "PRF_PocSignedDistance_ticks",
        "PRF_PocSide_Favor",
        "PRF_VaSignedPositionNorm",
        "PRF_PocDrift_ticks_300s",
    ]:
        assert math.isclose(float(buy[column]), -float(sell[column]))
    for column in [
        "PRF_InsideValueArea",
        "PRF_VaWidth_ticks",
        "PRF_PocVolumeShare",
        "PRF_ProfileEntropyNorm",
    ]:
        assert math.isclose(float(buy[column]), float(sell[column]))


def test_cluster_bursts_is_session_ordered() -> None:
    first = _burst(lb_id="A", cut=10 * TICKS_PER_SECOND)
    second = _burst(
        lb_id="B",
        cut=12 * TICKS_PER_SECOND,
        publish=12 * TICKS_PER_SECOND + 1,
        side="SELL",
        direction=-1,
    )
    frame = cluster_bursts([second, first])
    assert list(frame["lb_id"]) == ["A", "B"]
    row = frame.iloc[1]
    assert row["time_since_previous_any_ms"] == 2000
    assert bool(row["overlap_any_5s"])
    assert bool(row["overlap_any_30s"])


def test_level_viability_is_nested_and_uses_every_session() -> None:
    frame = pd.DataFrame(
        [
            {
                "session_date": "A",
                "eligible_after_trade_qc": True,
                "k": 1,
                "fresh_valid_seconds": 100,
                "both_ge_k_seconds": 100,
                "both_ge_k_fraction": 1.0,
            },
            {
                "session_date": "B",
                "eligible_after_trade_qc": True,
                "k": 1,
                "fresh_valid_seconds": 100,
                "both_ge_k_seconds": 100,
                "both_ge_k_fraction": 1.0,
            },
            {
                "session_date": "A",
                "eligible_after_trade_qc": True,
                "k": 3,
                "fresh_valid_seconds": 100,
                "both_ge_k_seconds": 99,
                "both_ge_k_fraction": 0.99,
            },
            {
                "session_date": "B",
                "eligible_after_trade_qc": True,
                "k": 3,
                "fresh_valid_seconds": 100,
                "both_ge_k_seconds": 94,
                "both_ge_k_fraction": 0.94,
            },
        ]
    )
    result, nested = level_viability(
        frame,
        aggregate_minimum=0.99,
        each_session_minimum=0.95,
        expected_eligible_sessions=2,
    )
    assert nested
    assert bool(result.loc[result["k"].eq(1), "viable"].iloc[0])
    assert not bool(result.loc[result["k"].eq(3), "viable"].iloc[0])
    assert result.loc[result["k"].eq(3), "binding_session"].iloc[0] == "B"


def test_level_viability_detects_non_nested_input() -> None:
    rows = []
    for k, fraction in [(1, 1.0), (3, 0.90), (5, 1.0)]:
        rows.append(
            {
                "session_date": "A",
                "eligible_after_trade_qc": True,
                "k": k,
                "fresh_valid_seconds": 100,
                "both_ge_k_seconds": 100 * fraction,
                "both_ge_k_fraction": fraction,
            }
        )
    _, nested = level_viability(
        pd.DataFrame(rows),
        aggregate_minimum=0.95,
        each_session_minimum=0.95,
        expected_eligible_sessions=1,
    )
    assert not nested


def test_level_viability_rejects_missing_session() -> None:
    frame = pd.DataFrame(
        [
            {
                "session_date": "A",
                "eligible_after_trade_qc": True,
                "k": 1,
                "fresh_valid_seconds": 100,
                "both_ge_k_seconds": 100,
                "both_ge_k_fraction": 1.0,
            },
            {
                "session_date": "B",
                "eligible_after_trade_qc": True,
                "k": 1,
                "fresh_valid_seconds": 100,
                "both_ge_k_seconds": 100,
                "both_ge_k_fraction": 1.0,
            },
        ]
    )
    try:
        level_viability(
            frame,
            aggregate_minimum=0.99,
            each_session_minimum=0.95,
            expected_eligible_sessions=3,
        )
    except ValueError as exc:
        assert "expected 3" in str(exc)
    else:
        raise AssertionError("missing session must raise")


def test_startup_produces_sixteen_snapshots() -> None:
    _, _, _, startup, _ = audit_book_session(
        session_date="2022-08-01",
        depth=np.empty(0, dtype=ROW_DTYPE),
        effective_ticks=np.asarray([], dtype=np.int64),
        bursts=[],
        load_start_ticks=0,
        rth_start_ticks=5 * 60 * TICKS_PER_SECOND,
        rth_end_ticks=15 * 60 * TICKS_PER_SECOND,
        load_end_ticks=15 * 60 * TICKS_PER_SECOND,
        minimum_spread=1,
        maximum_spread=4,
        maximum_age_ms=250,
        pre_windows_seconds=[1, 5, 30],
        level_ks=[1],
        far_level_ticks=50,
        startup_minutes=15,
        eligible=False,
    )
    assert len(startup) == 16


def test_recent_set_matches_exact_scan_after_expiry() -> None:
    book = IncrementalL2Book()
    age = 250 * TICKS_PER_MILLISECOND
    book.update_group(
        _rows([(0, 0, 100, 10), (0, 1, 101, 10)]),
        ticks=0,
        maximum_recent_age_ticks=age,
    )
    book.update_group(
        _rows([(200 * TICKS_PER_MILLISECOND, 0, 99, 10)]),
        ticks=200 * TICKS_PER_MILLISECOND,
        maximum_recent_age_ticks=age,
    )
    now = 300 * TICKS_PER_MILLISECOND
    book.expire_recent(now, age)
    assert (len(book.bid_recent), len(book.ask_recent)) == book.recent_counts_at(
        now, age
    )


def test_hot_loop_budget_for_one_hundred_thousand_groups() -> None:
    initial = [
        (0, 0, 1_000 + index, 10) for index in range(300)
    ] + [
        (0, 1, 1_300 + index, 10) for index in range(300)
    ]
    updates = [
        (
            index * TICKS_PER_MILLISECOND,
            0,
            1_299,
            10 + index % 2,
        )
        for index in range(1, 100_001)
    ]
    depth = _rows(initial + updates)
    started = time.perf_counter()
    audit_book_session(
        session_date="SYNTHETIC",
        depth=depth,
        effective_ticks=depth["ticks"].astype(np.int64),
        bursts=[],
        load_start_ticks=0,
        rth_start_ticks=0,
        rth_end_ticks=100 * TICKS_PER_SECOND,
        load_end_ticks=100 * TICKS_PER_SECOND,
        minimum_spread=1,
        maximum_spread=4,
        maximum_age_ms=250,
        pre_windows_seconds=[1, 5, 30],
        level_ks=[1, 3, 5, 10],
        far_level_ticks=50,
        startup_minutes=1,
        eligible=True,
    )
    assert time.perf_counter() - started < 3.0


def test_forbidden_output_columns_detects_future_fields() -> None:
    observed = forbidden_output_columns(
        [
            pd.DataFrame(
                {
                    "lb_id": ["A"],
                    "regime": ["CONTINUATION"],
                    "OUT_PostLbPoc_raw": [100],
                    "continue_reached": [True],
                    "reverse_reached": [False],
                    "first_expansion_direction": [1],
                    "future_trade_count": [7],
                    "time_difference_continue_minus_reverse_ms": [100],
                }
            )
        ]
    )
    assert observed == [
        "OUT_PostLbPoc_raw",
        "continue_reached",
        "first_expansion_direction",
        "future_trade_count",
        "regime",
        "reverse_reached",
        "time_difference_continue_minus_reverse_ms",
    ]
