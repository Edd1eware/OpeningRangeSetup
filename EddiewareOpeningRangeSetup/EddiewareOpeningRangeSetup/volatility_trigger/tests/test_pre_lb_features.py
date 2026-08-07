from __future__ import annotations

import ast
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from volatility_trigger.src.pre_lb_features import (  # noqa: E402
    build_feature_matrix,
    catalog_features,
    cluster_metadata,
    dom_precursor_features,
    profile_feature_frame,
    trade_precursor_features,
    validate_catalog,
)
from volatility_trigger.src.vt_core import (  # noqa: E402
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
CONFIG_PATH = ROOT / "config" / "pre_lb_precursor_f2_config.json"


def _rows(values: list[tuple[int, int, int, int]]) -> np.ndarray:
    return np.asarray(values, dtype=ROW_DTYPE)


def _config() -> dict[str, object]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _burst(
    *,
    lb_id: str = "LB_TEST",
    session_date: str = "2022-08-01",
    cut: int = 40 * TICKS_PER_SECOND,
    direction: int = 1,
) -> LiquidityBurst:
    side = "BUY" if direction > 0 else "SELL"
    return LiquidityBurst(
        lb_id=lb_id,
        session_date=session_date,
        source_second_ticks=int(cut),
        publish_ticks=int(cut + 100 * TICKS_PER_MILLISECOND),
        side=side,
        direction=int(direction),
        price_raw=100,
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


def _book_snapshot(
    ticks: int,
    *,
    center: int = 100,
) -> list[tuple[int, int, int, int]]:
    rows: list[tuple[int, int, int, int]] = []
    for level in range(10):
        rows.append((ticks, 0, center - 1 - level, 20 + level))
        rows.append((ticks, 1, center + 1 + level, 40 + 2 * level))
    return rows


def _mirror_rows(
    rows: np.ndarray,
    *,
    center_twice: int = 200,
) -> np.ndarray:
    mirrored = rows.copy()
    mirrored["side_code"] = np.where(
        rows["side_code"] == 1,
        2,
        np.where(rows["side_code"] == 2, 1, 1 - rows["side_code"]),
    )
    mirrored["price_raw"] = center_twice - rows["price_raw"]
    return mirrored


def _mirror_depth(
    rows: np.ndarray,
    *,
    center_twice: int = 200,
) -> np.ndarray:
    mirrored = rows.copy()
    mirrored["side_code"] = 1 - rows["side_code"]
    mirrored["price_raw"] = center_twice - rows["price_raw"]
    return mirrored


def _dom(
    depth: np.ndarray,
    burst: LiquidityBurst,
    *,
    maximum_age_ms: float = 60_000.0,
) -> pd.Series:
    frame = dom_precursor_features(
        depth,
        depth["ticks"].astype(np.int64),
        [burst],
        load_start_ticks=(
            int(burst.source_second_ticks) - 30 * TICKS_PER_SECOND
        ),
        maximum_age_ms=maximum_age_ms,
        minimum_spread=1,
        maximum_spread=4,
    )
    return frame.iloc[0]


def test_catalog_is_exactly_the_frozen_60_unique_features() -> None:
    config = _config()
    features = validate_catalog(config)
    assert features == catalog_features(config)
    assert len(features) == 60
    assert len(set(features)) == 60


def test_trade_windows_are_left_closed_right_open_and_future_invariant() -> None:
    cut = 40 * TICKS_PER_SECOND
    burst = _burst(cut=cut)
    trades = _rows(
        [
            (cut - TICKS_PER_SECOND, 1, 100, 2),
            (cut - 1, 1, 103, 3),
            (cut, 2, 999, 1_000_000),
            (cut + 1, 2, 888, 1_000_000),
        ]
    )
    frame = trade_precursor_features(
        trades,
        [burst],
        rth_start_ticks=0,
    ).iloc[0]
    assert frame["PX_NetMoveFavor_ticks_pre_1s"] == 3
    assert frame["PX_Range_ticks_pre_1s"] == 3
    assert frame["TAPE_TradeRate_pre_1s"] == 2
    assert frame["TAPE_ContractRate_pre_1s"] == 5
    assert frame["MAX_PRECURSOR_TRADE_TICKS"] == cut - 1

    truncated = trade_precursor_features(
        trades[:2],
        [burst],
        rth_start_ticks=0,
    )
    pd.testing.assert_frame_equal(
        frame.to_frame().T.reset_index(drop=True),
        truncated.reset_index(drop=True),
        check_dtype=False,
    )


def test_trade_empty_window_has_preregistered_zero_semantics() -> None:
    cut = 40 * TICKS_PER_SECOND
    frame = trade_precursor_features(
        _rows([(cut - 31 * TICKS_PER_SECOND, 1, 100, 1)]),
        [_burst(cut=cut)],
        rth_start_ticks=0,
    ).iloc[0]
    for seconds in (1, 5, 30):
        assert frame[f"PX_NetMoveFavor_ticks_pre_{seconds}s"] == 0
        assert frame[f"PX_Range_ticks_pre_{seconds}s"] == 0
        assert frame[f"PX_PathEfficiencyFavor_pre_{seconds}s"] == 0
        assert frame[f"TAPE_TradeRate_pre_{seconds}s"] == 0
        assert frame[f"TAPE_ContractRate_pre_{seconds}s"] == 0


def test_tape_retention_uses_fixed_pseudocount_for_empty_half() -> None:
    cut = 40 * TICKS_PER_SECOND
    start = cut - TICKS_PER_SECOND
    first_only = trade_precursor_features(
        _rows(
            [
                (start, 1, 100, 9),
                (start + 750 * TICKS_PER_MILLISECOND, 2, 100, 99),
            ]
        ),
        [_burst(cut=cut)],
        rth_start_ticks=0,
    ).iloc[0]
    second_only = trade_precursor_features(
        _rows(
            [
                (start, 2, 100, 99),
                (start + 750 * TICKS_PER_MILLISECOND, 1, 100, 9),
            ]
        ),
        [_burst(cut=cut)],
        rth_start_ticks=0,
    ).iloc[0]
    assert first_only[
        "TAPE_AggressorSizeLogRetention_pre_1s"
    ] == pytest.approx(math.log(1 / 10))
    assert second_only[
        "TAPE_AggressorSizeLogRetention_pre_1s"
    ] == pytest.approx(math.log(10 / 1))


def test_trade_controls_reset_at_session_boundary() -> None:
    cut = 40 * TICKS_PER_SECOND
    bursts = [
        _burst(lb_id="A1", session_date="2022-08-01", cut=cut),
        _burst(lb_id="A2", session_date="2022-08-01", cut=cut + 20 * TICKS_PER_SECOND),
        _burst(lb_id="B1", session_date="2022-08-02", cut=cut),
    ]
    frame = trade_precursor_features(
        _rows([(1, 1, 100, 1)]),
        bursts,
        rth_start_ticks=0,
    ).set_index("lb_id")
    assert frame.loc["A1", "CTL_LbOrdinalPriorCount"] == 0
    assert frame.loc["A2", "CTL_LbOrdinalPriorCount"] == 1
    assert frame.loc["A2", "CTL_PriorLbWithin30s"] == 1
    assert frame.loc["B1", "CTL_LbOrdinalPriorCount"] == 0
    assert frame.loc["B1", "CTL_PriorLbWithin30s"] == 0


def test_dom_cut_group_is_excluded_and_start_group_is_included() -> None:
    cut = 40 * TICKS_PER_SECOND
    start = cut - TICKS_PER_SECOND
    burst = _burst(cut=cut)
    initial = _book_snapshot(start)
    at_cut = [(cut, 1, 101, 10_000)]
    row = _dom(_rows(initial + at_cut), burst)

    bid1 = 20.0
    ask1 = 40.0
    expected_microprice = (101 * bid1 + 99 * ask1) / (bid1 + ask1)
    assert row["DOM_STATE_SUPPORT"]
    assert row["DOM_W1_SUPPORT"]
    assert row["DOM_MicropriceOffsetFavor_ticks"] == pytest.approx(
        expected_microprice - 100.0
    )
    assert row["DOM_MicropriceDriftFavor_ticks_pre_1s"] == 0
    assert row["MAX_PRECURSOR_DEPTH_TICKS"] == start


def test_dom_microprice_drift_uses_microprice_not_midpoint() -> None:
    cut = 40 * TICKS_PER_SECOND
    start = cut - TICKS_PER_SECOND
    burst = _burst(cut=cut)
    rows = _book_snapshot(start)
    rows.append((cut - 1, 0, 99, 80))
    row = _dom(_rows(rows), burst)

    start_microprice = (101 * 20 + 99 * 40) / 60
    end_microprice = (101 * 80 + 99 * 40) / 120
    assert row["DOM_W1_SUPPORT"]
    assert row["DOM_MicropriceDriftFavor_ticks_pre_1s"] == pytest.approx(
        end_microprice - start_microprice
    )
    assert not math.isclose(
        row["DOM_MicropriceDriftFavor_ticks_pre_1s"],
        end_microprice - 100.0,
    )


def test_dom_requires_top10_for_every_instant_in_supported_window() -> None:
    cut = 40 * TICKS_PER_SECOND
    start = cut - TICKS_PER_SECOND
    rows = _book_snapshot(start)
    rows.extend(
        [
            (start + 250 * TICKS_PER_MILLISECOND, 0, 90, 0),
            (start + 500 * TICKS_PER_MILLISECOND, 0, 90, 29),
        ]
    )
    row = _dom(_rows(rows), _burst(cut=cut))
    assert not row["DOM_W1_SUPPORT"]
    assert math.isnan(row["DOM_ImbalanceL10MeanFavor_pre_1s"])


def test_dom_stale_gap_invalidates_entire_window() -> None:
    cut = 40 * TICKS_PER_SECOND
    start = cut - TICKS_PER_SECOND
    row = _dom(
        _rows(_book_snapshot(start)),
        _burst(cut=cut),
        maximum_age_ms=250.0,
    )
    assert not row["DOM_W1_SUPPORT"]
    assert not row["DOM_STATE_SUPPORT"]


def test_far_tail_update_does_not_change_top10_values_or_proxies() -> None:
    cut = 40 * TICKS_PER_SECOND
    start = cut - TICKS_PER_SECOND
    burst = _burst(cut=cut)
    base = _rows(_book_snapshot(start))
    with_tail = _rows(
        _book_snapshot(start)
        + [(start + 500 * TICKS_PER_MILLISECOND, 0, 1, 1_000_000)]
    )
    left = _dom(base, burst)
    right = _dom(with_tail, burst)
    feature_columns = [
        column
        for column in left.index
        if column.startswith("DOM_")
    ]
    np.testing.assert_allclose(
        left[feature_columns].to_numpy(dtype=float),
        right[feature_columns].to_numpy(dtype=float),
        equal_nan=True,
    )


def test_dom_directional_stack_pull_sign_is_symmetric() -> None:
    cut = 40 * TICKS_PER_SECOND
    start = cut - TICKS_PER_SECOND
    rows = _rows(
        _book_snapshot(start - TICKS_PER_SECOND)
        + [(start + 500 * TICKS_PER_MILLISECOND, 1, 101, 10)]
    )
    buy = _dom(rows, _burst(cut=cut, direction=1))
    mirrored = _dom(
        _mirror_depth(rows),
        _burst(cut=cut, direction=-1),
    )
    assert buy["DOM_ProxyDirectionalStackPullBalanceL10_pre_1s"] > 0
    assert mirrored[
        "DOM_ProxyDirectionalStackPullBalanceL10_pre_1s"
    ] == pytest.approx(
        buy["DOM_ProxyDirectionalStackPullBalanceL10_pre_1s"]
    )


def test_cluster_metadata_uses_connected_components_within_session() -> None:
    base = 100 * TICKS_PER_SECOND
    bursts = [
        _burst(lb_id="A1", session_date="2022-08-01", cut=base),
        _burst(lb_id="A2", session_date="2022-08-01", cut=base + 20 * TICKS_PER_SECOND),
        _burst(lb_id="A3", session_date="2022-08-01", cut=base + 40 * TICKS_PER_SECOND),
        _burst(lb_id="A4", session_date="2022-08-01", cut=base + 71 * TICKS_PER_SECOND),
        _burst(lb_id="B1", session_date="2022-08-02", cut=base),
    ]
    frame = cluster_metadata(bursts).set_index("lb_id")
    assert frame.loc["A1", "LB_CLUSTER_ID_30S"] == frame.loc[
        "A3", "LB_CLUSTER_ID_30S"
    ]
    assert frame.loc["A1", "LB_CLUSTER_SIZE_30S"] == 3
    assert frame.loc["A4", "LB_CLUSTER_SIZE_30S"] == 1
    assert frame.loc["B1", "LB_CLUSTER_SIZE_30S"] == 1
    assert frame.loc["B1", "LB_CLUSTER_ID_30S"] != frame.loc[
        "A1", "LB_CLUSTER_ID_30S"
    ]
    assert frame.loc["B1", "LB_CLUSTER_ID_30S"].endswith("_C00000")


def test_profile_f11_support_enforces_thresholds_and_nan_contract() -> None:
    cut = 310 * TICKS_PER_SECOND
    trade_values = [
        (
            (index + 1) * 6 * TICKS_PER_SECOND // 10,
            1 if index % 2 else 2,
            99 + index % 3,
            1,
        )
        for index in range(499)
    ]
    frame = profile_feature_frame(
        _rows(trade_values),
        [_burst(cut=cut)],
        rth_start_ticks=0,
        drift_seconds=300,
        value_area_fraction=0.70,
        minimum_trades=500,
        minimum_elapsed_seconds=1,
    ).iloc[0]
    profile_features = [
        "PRF_PocSignedDistance_ticks",
        "PRF_PocSide_Favor",
        "PRF_VaSignedPositionNorm",
        "PRF_InsideValueArea",
        "PRF_VaWidth_ticks",
        "PRF_PocDrift_ticks_300s",
        "PRF_PocVolumeShare",
        "PRF_ProfileEntropyNorm",
    ]
    assert frame["PROFILE_RAW_SUPPORT"]
    assert not frame["PROFILE_F11_SUPPORT"]
    assert frame[profile_features].isna().all()

    supported_trades = _rows(
        trade_values
        + [(cut - 1, 1, 100, 1)]
    )
    supported = profile_feature_frame(
        supported_trades,
        [_burst(cut=cut)],
        rth_start_ticks=0,
        drift_seconds=300,
        value_area_fraction=0.70,
        minimum_trades=500,
        minimum_elapsed_seconds=1,
    ).iloc[0]
    assert supported["PROFILE_F11_SUPPORT"]
    assert np.isfinite(
        supported[profile_features].to_numpy(dtype=float)
    ).all()


def _full_fixture(
    *,
    mirrored: bool,
) -> tuple[np.ndarray, np.ndarray, LiquidityBurst, int]:
    cut = 310 * TICKS_PER_SECOND
    trade_values: list[tuple[int, int, int, int]] = []
    for index in range(620):
        ticks = (index + 1) * 5 * TICKS_PER_SECOND // 10
        price = 98 + index % 5
        side = 1 if index % 3 else 2
        trade_values.append((ticks, side, price, 1 + index % 7))
    trades = _rows(trade_values)

    depth_values = _book_snapshot(cut - 30 * TICKS_PER_SECOND)
    for offset_ms in range(100, 30_000, 100):
        depth_values.append(
            (
                cut
                - 30 * TICKS_PER_SECOND
                + offset_ms * TICKS_PER_MILLISECOND,
                0,
                99,
                20,
            )
        )
    depth = _rows(depth_values)
    burst = _burst(cut=cut, direction=1)
    if mirrored:
        trades = _mirror_rows(trades)
        depth = _mirror_depth(depth)
        burst = replace(
            burst,
            side="SELL",
            direction=-1,
            price_raw=100,
            delta_1s=-burst.delta_1s,
            delta_3s=-burst.delta_3s,
            delta_change_1s=-burst.delta_change_1s,
            delta_change_zscore=-burst.delta_change_zscore,
            velocity_1s=-burst.velocity_1s,
            acceleration_1s=-burst.acceleration_1s,
            cumulative_delta=-burst.cumulative_delta,
        )
    return trades, depth, burst, cut


def test_full_feature_matrix_is_buy_sell_price_side_mirror_invariant() -> None:
    config = _config()
    left_trades, left_depth, left_burst, cut = _full_fixture(
        mirrored=False
    )
    right_trades, right_depth, right_burst, _ = _full_fixture(
        mirrored=True
    )
    left, _ = build_feature_matrix(
        trades=left_trades,
        depth=left_depth,
        effective_depth_ticks=left_depth["ticks"].astype(np.int64),
        bursts=[left_burst],
        rth_start_ticks=0,
        depth_load_start_ticks=cut - 30 * TICKS_PER_SECOND,
        config=config,
    )
    right, _ = build_feature_matrix(
        trades=right_trades,
        depth=right_depth,
        effective_depth_ticks=right_depth["ticks"].astype(np.int64),
        bursts=[right_burst],
        rth_start_ticks=0,
        depth_load_start_ticks=cut - 30 * TICKS_PER_SECOND,
        config=config,
    )
    features = catalog_features(config)
    np.testing.assert_allclose(
        left.loc[0, features].to_numpy(dtype=float),
        right.loc[0, features].to_numpy(dtype=float),
        equal_nan=True,
        rtol=1e-12,
        atol=1e-12,
    )
    assert left.loc[0, "COMBINED_W1_SUPPORT"]
    assert right.loc[0, "COMBINED_W1_SUPPORT"]
    assert left.loc[0, "COMBINED_W5_SUPPORT"]
    assert right.loc[0, "COMBINED_W5_SUPPORT"]
    assert left.loc[0, "COMBINED_W30_SUPPORT"]
    assert right.loc[0, "COMBINED_W30_SUPPORT"]


def test_full_matrix_has_exact_catalog_and_no_outcome_columns() -> None:
    trades, depth, burst, cut = _full_fixture(mirrored=False)
    config = _config()
    matrix, lineage = build_feature_matrix(
        trades=trades,
        depth=depth,
        effective_depth_ticks=depth["ticks"].astype(np.int64),
        bursts=[burst],
        rth_start_ticks=0,
        depth_load_start_ticks=cut - 30 * TICKS_PER_SECOND,
        config=config,
    )
    features = catalog_features(config)
    assert [column for column in features if column in matrix] == features
    assert lineage["feature_count"] == 60
    assert lineage["labels_opened"] is False
    assert lineage["outcomes_opened"] is False
    forbidden = ("regime", "continue_reached", "reverse_reached", "out_post")
    assert not [
        column
        for column in matrix
        if any(token in column.lower() for token in forbidden)
    ]
    assert matrix.loc[0, "MAX_PRECURSOR_TRADE_TICKS"] < cut
    assert matrix.loc[0, "MAX_PRECURSOR_DEPTH_TICKS"] < cut
    assert matrix.loc[0, "MAX_PROFILE_TRADE_TICKS"] < cut


def test_extractor_import_graph_is_isolated_from_models_and_labels() -> None:
    source_path = ROOT / "src" / "pre_lb_features.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    forbidden_imports = (
        "vt_model",
        "run_research",
        "regime_discovery",
        "post_lb_regime",
    )
    assert not [
        name
        for name in imports
        if any(token in name for token in forbidden_imports)
    ]
    lowered = source_path.read_text(encoding="utf-8").lower()
    assert "labels.parquet" not in lowered
    assert "result.json" not in lowered
