from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from atas_cache_decoder import CACHE_RECORD_DTYPE  # noqa: E402
from src.vt_core import (  # noqa: E402
    TICKS_PER_MILLISECOND,
    causalize_trade_timestamps,
    compute_outcomes,
    contiguous_trade_ticks,
    datetime_to_dotnet_ticks,
    profile_snapshots,
)


def make_trades(prices, sides=None, volumes=None, spacing_ms=50):
    sides = sides or [1] * len(prices)
    volumes = volumes or [1] * len(prices)
    start = datetime_to_dotnet_ticks(
        datetime(2022, 8, 1, 14, 0, tzinfo=timezone.utc)
    )
    rows = np.empty(len(prices), dtype=CACHE_RECORD_DTYPE)
    rows["template_id"] = 101
    rows["ticks"] = start + np.arange(len(prices)) * spacing_ms * TICKS_PER_MILLISECOND
    rows["side_code"] = sides
    rows["price_raw"] = prices
    rows["volume_raw"] = volumes
    return rows


def test_signed_outcomes_are_mirrored():
    trades = make_trades([100, 101, 102, 103, 104, 108, 108, 108, 108, 108] * 20)
    config = {
        "outcome_horizon_ms": 5000,
        "sniper_success": {
            "time_to_impulse_4t_max_ms": 750,
            "signed_displacement_1s_min_ticks": 4,
            "signed_displacement_2s_min_ticks": 8,
            "pre_expansion_ae_4t_max_ticks": 2,
            "initial_impulse_mfe_3t_pullback_min_ticks": 8,
            "directional_efficiency_2s_min": 0.65,
        },
    }
    candidate = int(trades[0]["ticks"])
    buy = compute_outcomes(trades, candidate, 1, config)
    sell = compute_outcomes(trades, candidate, -1, config)
    assert buy["signed_displacement_1000ms"] == -sell["signed_displacement_1000ms"]


def test_profiles_never_use_trades_after_target():
    trades = make_trades([100, 100, 100, 200], volumes=[1, 1, 1, 100])
    first_target = int(trades[2]["ticks"])
    final_target = int(trades[3]["ticks"])
    snapshots = profile_snapshots(trades, [first_target, final_target])
    assert snapshots[first_target]["poc_raw"] == 100
    assert snapshots[final_target]["poc_raw"] == 200


def test_outcome_columns_are_future_only_not_input_contract():
    trades = make_trades(list(range(100, 220)))
    config = {
        "outcome_horizon_ms": 5000,
        "sniper_success": {
            "time_to_impulse_4t_max_ms": 750,
            "signed_displacement_1s_min_ticks": 4,
            "signed_displacement_2s_min_ticks": 8,
            "pre_expansion_ae_4t_max_ticks": 2,
            "initial_impulse_mfe_3t_pullback_min_ticks": 8,
            "directional_efficiency_2s_min": 0.65,
        },
    }
    outcome = compute_outcomes(trades, int(trades[0]["ticks"]), 1, config)
    assert outcome["outcome_valid"] == 1
    assert all(
        key.startswith(
            (
                "outcome_",
                "entry_",
                "time_to_",
                "pre_expansion_",
                "initial_impulse_",
                "signed_displacement_",
                "directional_efficiency_",
                "sniper_success",
            )
        )
        for key in outcome
    )


def test_small_timestamp_backtrack_is_delayed_without_reordering():
    trades = make_trades([100, 101, 102, 103], spacing_ms=10)
    original_prices = trades["price_raw"].copy()
    trades["ticks"][2] = trades["ticks"][1] - 2 * TICKS_PER_MILLISECOND
    normalized, audit = causalize_trade_timestamps(
        trades,
        {
            "causal_policy": "FILE_ORDER_CUMMAX",
            "max_backtrack_count": 10,
            "max_single_backtrack_ms": 50.0,
        },
    )
    assert np.array_equal(normalized["price_raw"], original_prices)
    assert normalized["ticks"][2] == normalized["ticks"][1]
    assert np.all(np.diff(normalized["ticks"]) >= 0)
    assert audit["raw_timestamp_backtracks"] == 1
    assert audit["largest_raw_backtrack_ms"] == 2.0


def test_material_timestamp_backtrack_excludes_session():
    trades = make_trades([100, 101, 102], spacing_ms=10)
    trades["ticks"][2] = trades["ticks"][1] - 100 * TICKS_PER_MILLISECOND
    with pytest.raises(ValueError, match="timestamp QC failed"):
        causalize_trade_timestamps(
            trades,
            {
                "causal_policy": "FILE_ORDER_CUMMAX",
                "max_backtrack_count": 10,
                "max_single_backtrack_ms": 50.0,
            },
        )


def test_contiguous_timestamp_index_is_outcome_equivalent():
    trades = make_trades(list(range(100, 220)))
    config = {
        "outcome_horizon_ms": 5000,
        "sniper_success": {
            "time_to_impulse_4t_max_ms": 750,
            "signed_displacement_1s_min_ticks": 4,
            "signed_displacement_2s_min_ticks": 8,
            "pre_expansion_ae_4t_max_ticks": 2,
            "initial_impulse_mfe_3t_pullback_min_ticks": 8,
            "directional_efficiency_2s_min": 0.65,
        },
    }
    candidate = int(trades[0]["ticks"])
    original = compute_outcomes(trades, candidate, 1, config)
    optimized = compute_outcomes(
        trades,
        candidate,
        1,
        config,
        trade_ticks=contiguous_trade_ticks(trades),
    )
    assert original == optimized
