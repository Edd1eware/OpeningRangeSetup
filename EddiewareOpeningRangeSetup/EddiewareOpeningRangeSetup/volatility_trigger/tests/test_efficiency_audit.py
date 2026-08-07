from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from atas_cache_decoder import CACHE_RECORD_DTYPE  # noqa: E402
from src.efficiency_audit import (  # noqa: E402
    QuoteSeries,
    causal_depth_timestamps,
    path_efficiency,
    quote_path,
    reconstruct_quotes,
)
from src.post_lb_regime import reference_quote_at  # noqa: E402
from src.vt_core import TICKS_PER_MILLISECOND  # noqa: E402


def depth_rows(records):
    rows = np.empty(len(records), dtype=CACHE_RECORD_DTYPE)
    rows["template_id"] = 130
    for index, (ticks, side, price, volume) in enumerate(records):
        rows[index]["ticks"] = ticks
        rows[index]["side_code"] = side
        rows[index]["price_raw"] = price
        rows[index]["volume_raw"] = volume
    return rows


def test_depth_watermark_clamps_jitter_and_drops_stale_rows():
    base = 1_000_000
    rows = depth_rows(
        [
            (base, 0, 100, 10),
            (base + 10 * TICKS_PER_MILLISECOND, 1, 101, 10),
            (base + 9 * TICKS_PER_MILLISECOND, 0, 100, 11),
            (base - 100 * TICKS_PER_MILLISECOND, 1, 101, 99),
            (base + 11 * TICKS_PER_MILLISECOND, 1, 101, 12),
        ]
    )
    accepted, effective, audit = causal_depth_timestamps(rows, 50.0)
    assert len(accepted) == 4
    assert np.all(np.diff(effective) >= 0)
    assert effective[2] == effective[1]
    assert audit["clamped_rows"] == 1
    assert audit["stale_rows_dropped"] == 1
    assert 99 not in accepted["volume_raw"]


def test_quote_reconstruction_coalesces_timestamp_and_microprice():
    rows = depth_rows(
        [
            (100, 0, 100, 10),
            (100, 1, 101, 10),
            (110, 0, 100, 20),
            (120, 1, 101, 30),
        ]
    )
    quotes, audit = reconstruct_quotes(
        rows,
        rows["ticks"].astype(np.int64),
        {"min_spread_ticks": 1, "max_spread_ticks": 4},
    )
    assert quotes.ticks.tolist() == [100, 110, 120]
    assert quotes.mid.tolist() == [100.5, 100.5, 100.5]
    assert quotes.microprice[0] == pytest.approx(100.5)
    assert quotes.microprice[1] == pytest.approx(
        (101 * 20 + 100 * 10) / 30
    )
    assert audit["quote_change_events"] == 3


def test_sampled_mid_is_strictly_asof_without_future_interpolation():
    base = 1_000_000
    quotes = QuoteSeries(
        ticks=np.asarray(
            [base, base + 2 * TICKS_PER_MILLISECOND],
            dtype=np.int64,
        ),
        mid=np.asarray([100.0, 200.0]),
        microprice=np.asarray([100.0, 200.0]),
        best_bid=np.asarray([99, 199]),
        best_ask=np.asarray([101, 201]),
        bid_size=np.asarray([10, 10]),
        ask_size=np.asarray([10, 10]),
    )
    values = quote_path(
        quotes,
        np.asarray(
            [
                base,
                base + TICKS_PER_MILLISECOND,
                base + 2 * TICKS_PER_MILLISECOND,
            ],
            dtype=np.int64,
        ),
        start_ticks=base + TICKS_PER_MILLISECOND,
        horizon_ms=1,
        value_name="mid",
        max_quote_age_ms=10.0,
        sample_ms=1,
    )
    assert values is not None
    assert values[0] == 100.0
    assert values[-1] == 200.0
    assert np.all(values[:-1] == 100.0)


def test_path_efficiency_is_exact_under_price_direction_mirror():
    buy_values = np.asarray([100, 101, 100, 103], dtype=float)
    sell_values = 200.0 - buy_values
    buy = path_efficiency(buy_values, 1)
    sell = path_efficiency(sell_values, -1)
    assert buy == sell
    assert buy[0] == pytest.approx(0.6)
    assert 0.0 <= buy[0] <= 1.0


def test_invalid_current_book_state_is_not_carried_forward():
    base = 1_000_000
    rows = depth_rows(
        [
            (base, 0, 100, 10),
            (base, 1, 101, 10),
            (
                base + TICKS_PER_MILLISECOND,
                1,
                101,
                0,
            ),
            (
                base + 2 * TICKS_PER_MILLISECOND,
                0,
                100,
                11,
            ),
        ]
    )
    effective = rows["ticks"].astype(np.int64)
    quotes, _ = reconstruct_quotes(
        rows,
        effective,
        {"min_spread_ticks": 1, "max_spread_ticks": 4},
    )
    reference = reference_quote_at(
        quotes,
        effective,
        base + 2 * TICKS_PER_MILLISECOND,
        max_age_ms=250.0,
    )
    assert reference is None


def test_same_quote_is_emitted_again_after_revalidation():
    base = 1_000_000
    rows = depth_rows(
        [
            (base, 0, 100, 10),
            (base, 1, 101, 10),
            (
                base + TICKS_PER_MILLISECOND,
                1,
                101,
                0,
            ),
            (
                base + 2 * TICKS_PER_MILLISECOND,
                1,
                101,
                10,
            ),
        ]
    )
    effective = rows["ticks"].astype(np.int64)
    quotes, _ = reconstruct_quotes(
        rows,
        effective,
        {"min_spread_ticks": 1, "max_spread_ticks": 4},
    )
    assert quotes.ticks.tolist() == [
        base,
        base + TICKS_PER_MILLISECOND,
        base + 2 * TICKS_PER_MILLISECOND,
    ]
    assert quotes.valid is not None
    assert quotes.valid.tolist() == [True, False, True]
    assert (
        reference_quote_at(
            quotes,
            effective,
            base + TICKS_PER_MILLISECOND,
            max_age_ms=250.0,
        )
        is None
    )
    restored = reference_quote_at(
        quotes,
        effective,
        base + 2 * TICKS_PER_MILLISECOND,
        max_age_ms=250.0,
    )
    assert restored is not None
    assert restored["mid_raw"] == 100.5


def test_quote_path_rejects_an_invalid_interior_state():
    base = 1_000_000
    rows = depth_rows(
        [
            (base, 0, 100, 10),
            (base, 1, 101, 10),
            (
                base + TICKS_PER_MILLISECOND,
                1,
                101,
                0,
            ),
            (
                base + 2 * TICKS_PER_MILLISECOND,
                1,
                101,
                10,
            ),
        ]
    )
    effective = rows["ticks"].astype(np.int64)
    quotes, _ = reconstruct_quotes(
        rows,
        effective,
        {"min_spread_ticks": 1, "max_spread_ticks": 4},
    )
    values = quote_path(
        quotes,
        effective,
        start_ticks=base,
        horizon_ms=2,
        value_name="mid",
        max_quote_age_ms=250.0,
    )
    assert values is None
