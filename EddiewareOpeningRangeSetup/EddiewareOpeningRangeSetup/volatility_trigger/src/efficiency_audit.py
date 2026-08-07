from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .vt_core import TICKS_PER_MILLISECOND


EPSILON = 1e-12


@dataclass(frozen=True)
class QuoteSeries:
    ticks: np.ndarray
    mid: np.ndarray
    microprice: np.ndarray
    best_bid: np.ndarray
    best_ask: np.ndarray
    bid_size: np.ndarray
    ask_size: np.ndarray
    valid: np.ndarray | None = None


def causal_depth_timestamps(
    depth: np.ndarray,
    max_jitter_ms: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, float | int | str]]:
    """Keep file order, clamp small jitter, and drop stale late updates."""
    raw_ticks = np.ascontiguousarray(depth["ticks"], dtype=np.int64)
    if len(raw_ticks) == 0:
        return depth, raw_ticks, {
            "policy": "FILE_ORDER_WATERMARK",
            "raw_rows": 0,
            "accepted_rows": 0,
            "clamped_rows": 0,
            "stale_rows_dropped": 0,
            "largest_lateness_ms": 0.0,
        }
    watermark = np.maximum.accumulate(raw_ticks)
    lateness = watermark - raw_ticks
    tolerance = float(max_jitter_ms) * TICKS_PER_MILLISECOND
    accepted = lateness <= tolerance
    effective = np.ascontiguousarray(watermark[accepted], dtype=np.int64)
    accepted_rows = depth[accepted]
    return accepted_rows, effective, {
        "policy": "FILE_ORDER_WATERMARK",
        "raw_rows": int(len(depth)),
        "accepted_rows": int(accepted.sum()),
        "clamped_rows": int(np.sum((lateness > 0) & accepted)),
        "stale_rows_dropped": int(np.sum(~accepted)),
        "largest_lateness_ms": float(
            lateness.max() / TICKS_PER_MILLISECOND
        ),
    }


def reconstruct_quotes(
    depth: np.ndarray,
    effective_ticks: np.ndarray,
    quote_policy: Mapping[str, object],
) -> tuple[QuoteSeries, dict[str, int]]:
    if len(depth) != len(effective_ticks):
        raise ValueError("depth/effective tick length mismatch")

    bid_volume: dict[int, int] = {}
    ask_volume: dict[int, int] = {}
    bid_heap: list[int] = []
    ask_heap: list[int] = []
    quote_ticks: list[int] = []
    mids: list[float] = []
    microprices: list[float] = []
    best_bids: list[int] = []
    best_asks: list[int] = []
    bid_sizes: list[int] = []
    ask_sizes: list[int] = []
    validity: list[bool] = []
    prior_state: tuple[int, int, int, int] | None = None
    prior_valid: bool | None = None
    invalid_groups = 0
    valid_groups = 0
    minimum_spread = int(quote_policy["min_spread_ticks"])
    maximum_spread = int(quote_policy["max_spread_ticks"])

    pointer = 0
    total = len(depth)
    while pointer < total:
        group_ticks = int(effective_ticks[pointer])
        stop = pointer + 1
        while stop < total and int(effective_ticks[stop]) == group_ticks:
            stop += 1

        for index in range(pointer, stop):
            side = int(depth[index]["side_code"])
            price = int(depth[index]["price_raw"])
            volume = int(depth[index]["volume_raw"])
            levels = bid_volume if side == 0 else ask_volume
            heap = bid_heap if side == 0 else ask_heap
            heap_price = -price if side == 0 else price
            if volume > 0:
                if price not in levels:
                    heapq.heappush(heap, heap_price)
                levels[price] = volume
            else:
                levels.pop(price, None)

        while bid_heap and -bid_heap[0] not in bid_volume:
            heapq.heappop(bid_heap)
        while ask_heap and ask_heap[0] not in ask_volume:
            heapq.heappop(ask_heap)

        if not bid_heap or not ask_heap:
            invalid_groups += 1
            if prior_valid is not False:
                quote_ticks.append(group_ticks)
                best_bids.append(0)
                best_asks.append(0)
                bid_sizes.append(0)
                ask_sizes.append(0)
                mids.append(math.nan)
                microprices.append(math.nan)
                validity.append(False)
            prior_valid = False
            pointer = stop
            continue
        best_bid = -bid_heap[0]
        best_ask = ask_heap[0]
        spread = best_ask - best_bid
        if spread < minimum_spread or spread > maximum_spread:
            invalid_groups += 1
            if prior_valid is not False:
                quote_ticks.append(group_ticks)
                best_bids.append(best_bid)
                best_asks.append(best_ask)
                bid_sizes.append(bid_volume[best_bid])
                ask_sizes.append(ask_volume[best_ask])
                mids.append(math.nan)
                microprices.append(math.nan)
                validity.append(False)
            prior_valid = False
            pointer = stop
            continue

        bid_size = bid_volume[best_bid]
        ask_size = ask_volume[best_ask]
        state = (best_bid, best_ask, bid_size, ask_size)
        valid_groups += 1
        if prior_valid is not True or state != prior_state:
            denominator = bid_size + ask_size
            quote_ticks.append(group_ticks)
            best_bids.append(best_bid)
            best_asks.append(best_ask)
            bid_sizes.append(bid_size)
            ask_sizes.append(ask_size)
            mids.append((best_bid + best_ask) / 2.0)
            microprices.append(
                (
                    best_ask * bid_size
                    + best_bid * ask_size
                )
                / denominator
            )
            validity.append(True)
            prior_state = state
        prior_valid = True
        pointer = stop

    return QuoteSeries(
        ticks=np.asarray(quote_ticks, dtype=np.int64),
        mid=np.asarray(mids, dtype=np.float64),
        microprice=np.asarray(microprices, dtype=np.float64),
        best_bid=np.asarray(best_bids, dtype=np.int64),
        best_ask=np.asarray(best_asks, dtype=np.int64),
        bid_size=np.asarray(bid_sizes, dtype=np.int64),
        ask_size=np.asarray(ask_sizes, dtype=np.int64),
        valid=np.asarray(validity, dtype=np.bool_),
    ), {
        "effective_timestamp_groups": valid_groups + invalid_groups,
        "valid_quote_groups": valid_groups,
        "invalid_quote_groups": invalid_groups,
        "quote_change_events": len(quote_ticks),
        "invalid_quote_state_events": int(
            len(validity) - sum(validity)
        ),
    }


def quote_validity(quotes: QuoteSeries) -> np.ndarray:
    if quotes.valid is None:
        return np.ones(len(quotes.ticks), dtype=np.bool_)
    valid = np.asarray(quotes.valid, dtype=np.bool_)
    if len(valid) != len(quotes.ticks):
        raise ValueError("quote validity/timestamp length mismatch")
    return valid


def path_efficiency(
    values: Sequence[float] | np.ndarray,
    direction: int,
) -> tuple[float, float, float]:
    numeric = np.asarray(values, dtype=np.float64)
    if len(numeric) == 0 or not np.all(np.isfinite(numeric)):
        return math.nan, math.nan, math.nan
    path_length = float(np.abs(np.diff(numeric)).sum())
    signed_net = float(direction * (numeric[-1] - numeric[0]))
    efficiency = max(0.0, signed_net) / max(path_length, EPSILON)
    return float(np.clip(efficiency, 0.0, 1.0)), path_length, signed_net


def quote_path(
    quotes: QuoteSeries,
    depth_ticks: np.ndarray,
    start_ticks: int,
    horizon_ms: int,
    value_name: str,
    max_quote_age_ms: float,
    sample_ms: int | None = None,
) -> np.ndarray | None:
    if len(quotes.ticks) == 0 or len(depth_ticks) == 0:
        return None
    end_ticks = start_ticks + horizon_ms * TICKS_PER_MILLISECOND
    entry = int(np.searchsorted(quotes.ticks, start_ticks, side="right")) - 1
    terminal = int(np.searchsorted(quotes.ticks, end_ticks, side="right")) - 1
    if entry < 0 or terminal < entry:
        return None
    valid = quote_validity(quotes)
    if not bool(valid[entry]) or not bool(valid[terminal]):
        return None

    depth_entry = (
        int(np.searchsorted(depth_ticks, start_ticks, side="right")) - 1
    )
    depth_terminal = (
        int(np.searchsorted(depth_ticks, end_ticks, side="right")) - 1
    )
    if depth_entry < 0 or depth_terminal < 0:
        return None
    maximum_age = max_quote_age_ms * TICKS_PER_MILLISECOND
    if (
        start_ticks - int(depth_ticks[depth_entry]) > maximum_age
        or end_ticks - int(depth_ticks[depth_terminal]) > maximum_age
    ):
        return None

    values = getattr(quotes, value_name)
    if sample_ms is None:
        first_after = int(
            np.searchsorted(quotes.ticks, start_ticks, side="right")
        )
        if np.any(~valid[first_after : terminal + 1]):
            return None
        return np.r_[
            values[entry],
            values[first_after : terminal + 1],
        ]

    sample_ticks = np.arange(
        start_ticks,
        end_ticks + 1,
        int(sample_ms) * TICKS_PER_MILLISECOND,
        dtype=np.int64,
    )
    indices = np.searchsorted(
        quotes.ticks,
        sample_ticks,
        side="right",
    ) - 1
    if np.any(indices < 0):
        return None
    if np.any(~valid[indices]):
        return None
    return values[indices]


def sniper_core_mask(
    candidates: pd.DataFrame,
    gates: Mapping[str, object],
) -> pd.Series:
    return (
        (
            candidates["time_to_impulse_4t_ms"]
            <= float(gates["time_to_impulse_4t_max_ms"])
        )
        & (
            candidates["signed_displacement_1000ms"]
            >= float(gates["signed_displacement_1s_min_ticks"])
        )
        & (
            candidates["signed_displacement_2000ms"]
            >= float(gates["signed_displacement_2s_min_ticks"])
        )
        & (
            candidates["pre_expansion_ae_4t"]
            <= float(gates["pre_expansion_ae_4t_max_ticks"])
        )
        & (
            candidates["initial_impulse_mfe_3t_pullback"]
            >= float(
                gates["initial_impulse_mfe_3t_pullback_min_ticks"]
            )
        )
    )


def _trade_path(
    trades: np.ndarray,
    trade_ticks: np.ndarray,
    start_ticks: int,
    horizon_ms: int,
) -> tuple[np.ndarray, int]:
    entry_index = (
        int(np.searchsorted(trade_ticks, start_ticks, side="right")) - 1
    )
    if entry_index < 0:
        return np.asarray([], dtype=np.float64), 0
    future_start = int(
        np.searchsorted(trade_ticks, start_ticks, side="right")
    )
    future_stop = int(
        np.searchsorted(
            trade_ticks,
            start_ticks + horizon_ms * TICKS_PER_MILLISECOND,
            side="right",
        )
    )
    entry_price = float(trades[entry_index]["price_raw"])
    future = trades["price_raw"][future_start:future_stop].astype(
        np.float64
    )
    return np.r_[entry_price, future], int(future_stop - future_start)


def compute_session_efficiencies(
    candidates: pd.DataFrame,
    trades: np.ndarray,
    trade_ticks: np.ndarray,
    quotes: QuoteSeries,
    depth_ticks: np.ndarray,
    config: Mapping[str, object],
) -> pd.DataFrame:
    horizon_ms = int(config["horizon_ms"])
    quote_policy = config["quote_policy"]
    max_quote_age = max(
        float(quote_policy["max_entry_quote_age_ms"]),
        float(quote_policy["max_terminal_quote_age_ms"]),
    )
    sample_steps = [
        int(value) for value in config["mid_sampling_ms"]
    ]
    records: list[dict[str, object]] = []

    for candidate_ticks, group in candidates.groupby(
        "candidate_ticks",
        sort=False,
    ):
        candidate_ticks = int(candidate_ticks)
        trade_values, trade_count = _trade_path(
            trades,
            trade_ticks,
            candidate_ticks,
            horizon_ms,
        )
        mid_events = quote_path(
            quotes,
            depth_ticks,
            candidate_ticks,
            horizon_ms,
            "mid",
            max_quote_age,
        )
        micro_events = quote_path(
            quotes,
            depth_ticks,
            candidate_ticks,
            horizon_ms,
            "microprice",
            max_quote_age,
        )
        sampled_mid = {
            step: quote_path(
                quotes,
                depth_ticks,
                candidate_ticks,
                horizon_ms,
                "mid",
                max_quote_age,
                sample_ms=step,
            )
            for step in sample_steps
        }
        depth_start = int(
            np.searchsorted(depth_ticks, candidate_ticks, side="right")
        )
        depth_stop = int(
            np.searchsorted(
                depth_ticks,
                candidate_ticks
                + horizon_ms * TICKS_PER_MILLISECOND,
                side="right",
            )
        )
        dom_update_count = depth_stop - depth_start

        for row in group.itertuples(index=False):
            direction = int(row.candidate_direction)
            trade_eff, trade_length, signed_net = path_efficiency(
                trade_values,
                direction,
            )
            signed_moves = (
                direction * (trade_values - trade_values[0])
                if len(trade_values)
                else np.asarray([], dtype=float)
            )
            mfe = (
                float(max(0.0, signed_moves.max()))
                if len(signed_moves)
                else math.nan
            )
            mae = (
                float(max(0.0, -signed_moves.min()))
                if len(signed_moves)
                else math.nan
            )
            positive_final = (
                max(0.0, float(signed_moves[-1]))
                if len(signed_moves)
                else math.nan
            )
            excursion_span = mfe + mae if math.isfinite(mfe + mae) else math.nan
            excursion = (
                positive_final / max(excursion_span, EPSILON)
                if math.isfinite(positive_final)
                else math.nan
            )
            retention = (
                positive_final / max(mfe, EPSILON)
                if math.isfinite(positive_final)
                else math.nan
            )
            if math.isfinite(excursion):
                excursion = float(np.clip(excursion, 0.0, 1.0))
            if math.isfinite(retention):
                retention = float(np.clip(retention, 0.0, 1.0))

            mid_quote = (
                path_efficiency(mid_events, direction)
                if mid_events is not None
                else (math.nan, math.nan, math.nan)
            )
            micro = (
                path_efficiency(micro_events, direction)
                if micro_events is not None
                else (math.nan, math.nan, math.nan)
            )
            sampled_results = {
                step: (
                    path_efficiency(values, direction)
                    if values is not None
                    else (math.nan, math.nan, math.nan)
                )
                for step, values in sampled_mid.items()
            }
            record = {
                "session_date": row.session_date,
                "lb_id": row.lb_id,
                "candidate_ticks": candidate_ticks,
                "candidate_side": row.candidate_side,
                "candidate_direction": direction,
                "time_since_lb_ms": row.time_since_lb_ms,
                "sniper_core": int(row.sniper_core),
                "trade_count": trade_count,
                "trade_rate": trade_count / (horizon_ms / 1000.0),
                "dom_update_count": dom_update_count,
                "trade_path_length": trade_length,
                "trade_path_efficiency_v1": trade_eff,
                "trade_signed_net_2s": signed_net,
                "mfe_2s": mfe,
                "mae_2s": mae,
                "excursion_span": excursion_span,
                "excursion_efficiency": excursion,
                "impulse_retention": retention,
                "mid_efficiency_quote_changes": mid_quote[0],
                "mid_quote_path_length": mid_quote[1],
                "microprice_efficiency": micro[0],
                "microprice_path_length": micro[1],
            }
            for step, result in sampled_results.items():
                record[f"mid_efficiency_sampled_{step}ms"] = result[0]
                record[f"mid_sampled_{step}ms_path_length"] = result[1]
            records.append(record)
    return pd.DataFrame(records)
