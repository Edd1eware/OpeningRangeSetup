from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.post_lb_regime import label_regime_path  # noqa: E402
from src.vt_core import TICKS_PER_MILLISECOND  # noqa: E402


BASE = 1_000_000_000


def label(
    prices,
    offsets_ms,
    direction,
    *,
    horizon_ms=5000,
    threshold=4,
):
    ticks = BASE + np.asarray(offsets_ms) * TICKS_PER_MILLISECOND
    return label_regime_path(
        ticks.astype(np.int64),
        np.asarray(prices, dtype=np.int64),
        BASE,
        100.0,
        direction,
        threshold,
        horizon_ms,
        250,
    )


def test_clean_continuation_buy():
    result = label([101, 104, 108], [10, 100, 300], 1)
    assert result["regime"] == "CONTINUATION"
    assert result["time_to_continue_ms"] == 100


def test_clean_continuation_sell():
    result = label([99, 96, 92], [10, 100, 300], -1)
    assert result["regime"] == "CONTINUATION"
    assert result["time_to_continue_ms"] == 100


def test_clean_reversal_after_buy_lb():
    result = label([99, 96, 92], [10, 100, 300], 1)
    assert result["regime"] == "REVERSAL"
    assert result["time_to_reverse_ms"] == 100


def test_clean_reversal_after_sell_lb():
    result = label([101, 104, 108], [10, 100, 300], -1)
    assert result["regime"] == "REVERSAL"
    assert result["time_to_reverse_ms"] == 100


def test_no_expansion():
    result = label([101, 102, 99, 98], [10, 100, 200, 300], 1)
    assert result["regime"] == "NO_EXPANSION"


def test_bidirectional_within_window_is_ambiguous():
    result = label([104, 96], [100, 300], 1)
    assert result["regime"] == "AMBIGUOUS"


def test_exact_timestamp_tie_is_ambiguous():
    result = label([104, 96], [100, 100], 1)
    assert result["regime"] == "AMBIGUOUS"
    assert result["first_expansion_direction"] == "TIE"


def test_late_expansion_changes_only_later_horizon():
    early = label([104], [6000], 1, horizon_ms=5000)
    late = label([104], [6000], 1, horizon_ms=10000)
    assert early["regime"] == "NO_EXPANSION"
    assert late["regime"] == "CONTINUATION"


def test_trade_exactly_at_lb_is_not_an_outcome():
    result = label([104, 100], [0, 100], 1)
    assert result["regime"] == "NO_EXPANSION"
    assert result["future_trade_count"] == 1


def test_buy_sell_price_mirror_is_exact():
    buy = label([101, 104, 102, 96], [10, 100, 500, 900], 1)
    sell_prices = 200 - np.asarray([101, 104, 102, 96])
    sell = label(sell_prices, [10, 100, 500, 900], -1)
    assert buy == sell
