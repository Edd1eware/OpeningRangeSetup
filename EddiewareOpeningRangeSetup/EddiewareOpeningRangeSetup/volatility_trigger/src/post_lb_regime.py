from __future__ import annotations

import math
from typing import Mapping

import numpy as np

from .efficiency_audit import QuoteSeries, quote_validity
from .vt_core import TICKS_PER_MILLISECOND


REGIME_CLASSES = (
    "CONTINUATION",
    "REVERSAL",
    "NO_EXPANSION",
    "AMBIGUOUS",
)


def classify_crossings(
    time_to_continue_ms: float,
    time_to_reverse_ms: float,
    horizon_ms: int,
    ambiguity_window_ms: int,
) -> str:
    continuation = (
        math.isfinite(time_to_continue_ms)
        and time_to_continue_ms <= horizon_ms
    )
    reversal = (
        math.isfinite(time_to_reverse_ms)
        and time_to_reverse_ms <= horizon_ms
    )
    if not continuation and not reversal:
        return "NO_EXPANSION"
    if continuation and reversal:
        difference = abs(time_to_continue_ms - time_to_reverse_ms)
        if difference <= ambiguity_window_ms:
            return "AMBIGUOUS"
        return (
            "CONTINUATION"
            if time_to_continue_ms < time_to_reverse_ms
            else "REVERSAL"
        )
    return "CONTINUATION" if continuation else "REVERSAL"


def reference_quote_at(
    quotes: QuoteSeries,
    depth_ticks: np.ndarray,
    at_ticks: int,
    max_age_ms: float,
) -> dict[str, float | int] | None:
    quote_index = (
        int(np.searchsorted(quotes.ticks, at_ticks, side="right")) - 1
    )
    depth_index = (
        int(np.searchsorted(depth_ticks, at_ticks, side="right")) - 1
    )
    if quote_index < 0 or depth_index < 0:
        return None
    valid = quote_validity(quotes)
    if not bool(valid[quote_index]):
        return None
    age_ms = (
        at_ticks - int(depth_ticks[depth_index])
    ) / TICKS_PER_MILLISECOND
    if age_ms > max_age_ms:
        return None
    return {
        "mid_raw": float(quotes.mid[quote_index]),
        "microprice_raw": float(quotes.microprice[quote_index]),
        "best_bid_raw": int(quotes.best_bid[quote_index]),
        "best_ask_raw": int(quotes.best_ask[quote_index]),
        "bid_size": int(quotes.bid_size[quote_index]),
        "ask_size": int(quotes.ask_size[quote_index]),
        "quote_ticks": int(quotes.ticks[quote_index]),
        "depth_age_ms": float(age_ms),
        "quote_group_lag_ms": float(
            (
                at_ticks
                - int(quotes.ticks[quote_index])
            )
            / TICKS_PER_MILLISECOND
        ),
    }


def label_regime_path(
    event_ticks: np.ndarray,
    prices_raw: np.ndarray,
    lb_ticks: int,
    reference_price_raw: float,
    lb_direction: int,
    threshold_ticks: int,
    horizon_ms: int,
    ambiguity_window_ms: int,
) -> dict[str, float | str]:
    if len(event_ticks) != len(prices_raw):
        raise ValueError("event tick/price length mismatch")
    end_ticks = lb_ticks + horizon_ms * TICKS_PER_MILLISECOND
    start = int(np.searchsorted(event_ticks, lb_ticks, side="right"))
    stop = int(np.searchsorted(event_ticks, end_ticks, side="right"))
    future_ticks = event_ticks[start:stop]
    future_prices = prices_raw[start:stop].astype(np.float64)
    signed_moves = lb_direction * (
        future_prices - float(reference_price_raw)
    )

    continue_hits = np.flatnonzero(signed_moves >= threshold_ticks)
    reverse_hits = np.flatnonzero(signed_moves <= -threshold_ticks)
    time_to_continue = (
        (
            int(future_ticks[int(continue_hits[0])]) - lb_ticks
        )
        / TICKS_PER_MILLISECOND
        if continue_hits.size
        else math.inf
    )
    time_to_reverse = (
        (
            int(future_ticks[int(reverse_hits[0])]) - lb_ticks
        )
        / TICKS_PER_MILLISECOND
        if reverse_hits.size
        else math.inf
    )
    regime = classify_crossings(
        time_to_continue,
        time_to_reverse,
        horizon_ms,
        ambiguity_window_ms,
    )
    if len(signed_moves):
        net_move = float(signed_moves[-1])
        max_continue = float(max(0.0, signed_moves.max()))
        max_reverse = float(max(0.0, -signed_moves.min()))
    else:
        net_move = 0.0
        max_continue = 0.0
        max_reverse = 0.0
    dominance = (
        (max_continue - max_reverse)
        / max(max_continue + max_reverse, 1e-12)
    )
    if math.isfinite(time_to_continue) and math.isfinite(time_to_reverse):
        first_direction = (
            "TIE"
            if time_to_continue == time_to_reverse
            else "CONTINUATION"
            if time_to_continue < time_to_reverse
            else "REVERSAL"
        )
        time_difference = time_to_continue - time_to_reverse
    elif math.isfinite(time_to_continue):
        first_direction = "CONTINUATION"
        time_difference = math.inf
    elif math.isfinite(time_to_reverse):
        first_direction = "REVERSAL"
        time_difference = -math.inf
    else:
        first_direction = "NONE"
        time_difference = math.nan
    return {
        "regime": regime,
        "time_to_continue_ms": float(time_to_continue),
        "time_to_reverse_ms": float(time_to_reverse),
        "continue_reached": int(math.isfinite(time_to_continue)),
        "reverse_reached": int(math.isfinite(time_to_reverse)),
        "first_expansion_direction": first_direction,
        "time_difference_continue_minus_reverse_ms": float(
            time_difference
        ),
        "net_move_signed_ticks": net_move,
        "max_move_continue_ticks": max_continue,
        "max_move_reverse_ticks": max_reverse,
        "expansion_dominance": float(dominance),
        "future_trade_count": int(len(future_ticks)),
    }


def reference_prices(
    quote: Mapping[str, float | int],
    lb_last_trade_raw: int,
    lb_direction: int,
) -> dict[str, float]:
    executable = (
        float(quote["best_ask_raw"])
        if lb_direction > 0
        else float(quote["best_bid_raw"])
    )
    return {
        "MID": float(quote["mid_raw"]),
        "EXECUTABLE": executable,
        "LAST_TRADE": float(lb_last_trade_raw),
    }
