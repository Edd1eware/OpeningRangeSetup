"""Extract and evaluate the preregistered eight MBO snapshot features.

The raw MBO stream is reconstructed independently from ATAS.  ATAS contributes
only BurstId, t_burst, t_decision, side, and the frozen A/B/C labels.  All book,
tape, queue, fill, cancellation, and refill measurements come from the same
Databento MBO stream and use completed F_LAST packets before the exclusive
decision cutoff.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


TICK_SIZE = 0.25
RANDOM_SEED = 20260723
PERMUTATIONS = 1000
BOOTSTRAPS = 1000
MODEL_C = 0.2
FAMILY_A = "A_TRUE_ABSORPTION"
FAMILY_B = "B_CLEAN_BREAKOUT"
FAMILY_C = "C_MIXED_PATH"
PRIMARY_FAMILY = "MATRIX_TRANSITIONS_PLUS_MBO_SNAPSHOT_8"
FINAL_YES = "YA SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO"
FINAL_NO = "NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO"

MBO_FEATURES = [
    "consumption_initial_depth_ratio_250ms",
    "withdrawal_initial_depth_ratio_250ms",
    "durable_refill_removed_ratio_250ms",
    "initial_queue_survival_ratio_250ms",
    "impact_efficiency_250ms",
    "depletion_persistence_share_500ms",
    "absorption_motif_share_500ms",
    "breakout_motif_share_500ms",
]

DIRECTIONAL_EXPECTATIONS = {
    "withdrawal_initial_depth_ratio_250ms": -1,
    "durable_refill_removed_ratio_250ms": 1,
    "initial_queue_survival_ratio_250ms": 1,
    "impact_efficiency_250ms": -1,
    "depletion_persistence_share_500ms": -1,
    "absorption_motif_share_500ms": 1,
    "breakout_motif_share_500ms": -1,
}

FAMILY_ORDER = [
    "MATRIX_TRANSITIONS",
    "MBO_SNAPSHOT_8",
    PRIMARY_FAMILY,
]


def _utc(value: Any) -> pd.Timestamp:
    return pd.to_datetime(value, utc=True, errors="raise", format="mixed")


def _load_frame(path: Path) -> pd.DataFrame:
    store = db.DBNStore.from_file(path)
    frame = store.to_df()
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    frame["ts_event"] = pd.to_datetime(
        frame["ts_event"], utc=True, errors="raise", format="mixed"
    )
    frame["flags"] = pd.to_numeric(frame["flags"], errors="raise").astype("uint16")
    frame["order_id"] = pd.to_numeric(
        frame["order_id"], errors="raise"
    ).astype("uint64")
    frame["size"] = pd.to_numeric(frame["size"], errors="raise").astype("int64")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["action"] = frame["action"].astype(str)
    frame["side"] = frame["side"].astype(str)
    return frame


def _last_completed_ordinal(
    frame: pd.DataFrame,
    cutoff_exclusive: pd.Timestamp,
) -> int:
    last_mask = frame["flags"].map(
        lambda value: bool(int(value) & int(db.RecordFlags.F_LAST))
    )
    candidates = frame.index[last_mask & frame["ts_event"].lt(cutoff_exclusive)]
    if len(candidates) == 0:
        raise ValueError(f"No completed F_LAST packet before {cutoff_exclusive}")
    return int(candidates.max())


def _update_level(
    levels: dict[tuple[str, float], float],
    side: str,
    price: float,
    delta: float,
) -> None:
    key = (side, price)
    updated = levels.get(key, 0.0) + delta
    if abs(updated) < 1e-9:
        levels.pop(key, None)
    else:
        levels[key] = updated


def _top_levels(
    levels: dict[tuple[str, float], float],
    side: str,
    count: int = 3,
) -> list[tuple[float, float]]:
    rows = [
        (price, size)
        for (level_side, price), size in levels.items()
        if level_side == side and size > 0 and math.isfinite(price)
    ]
    rows.sort(key=lambda value: value[0], reverse=side == "B")
    return rows[:count]


def _best_price(
    levels: dict[tuple[str, float], float],
    side: str,
) -> float:
    values = [
        price
        for (level_side, price), size in levels.items()
        if level_side == side and size > 0 and math.isfinite(price)
    ]
    if not values:
        return math.nan
    return min(values) if side == "A" else max(values)


def _apply_preburst(
    item: Any,
    state: dict[int, tuple[str, float, float]],
    levels: dict[tuple[str, float], float],
) -> None:
    action = str(item.action)
    order_id = int(item.order_id)
    side = str(item.side)
    price = float(item.price) if pd.notna(item.price) else math.nan
    size = float(item.size)
    if action == "R":
        state.clear()
        levels.clear()
    elif action == "A":
        old = state.get(order_id)
        if old is not None:
            _update_level(levels, old[0], old[1], -old[2])
        state[order_id] = (side, price, size)
        _update_level(levels, side, price, size)
    elif action == "M":
        old = state.get(order_id)
        if old is not None:
            _update_level(levels, old[0], old[1], -old[2])
        state[order_id] = (side, price, size)
        _update_level(levels, side, price, size)
    elif action == "C":
        old = state.get(order_id)
        if old is None:
            return
        removed = min(size, old[2])
        remaining = old[2] - removed
        _update_level(levels, old[0], old[1], -removed)
        if remaining <= 0:
            state.pop(order_id, None)
        else:
            state[order_id] = (old[0], old[1], remaining)


def _token_remaining_at(token: dict[str, Any], timestamp_ns: int) -> float:
    if int(token["start_ns"]) > timestamp_ns:
        return 0.0
    remaining = float(token["initial_qty"])
    for change_time, value in token["changes"]:
        if int(change_time) > timestamp_ns:
            break
        remaining = float(value)
    return remaining


def _timeline_state_at(
    timeline: list[dict[str, Any]],
    timestamp_ns: int,
) -> dict[str, Any]:
    selected = timeline[0]
    for point in timeline[1:]:
        if int(point["time_ns"]) > timestamp_ns:
            break
        selected = point
    return selected


def _max_directional_advance(
    timeline: list[dict[str, Any]],
    start_ns: int,
    end_ns: int,
    baseline_best: float,
    direction: int,
) -> float:
    if not math.isfinite(baseline_best):
        return 0.0
    candidates = [_timeline_state_at(timeline, start_ns)]
    candidates.extend(
        point
        for point in timeline
        if start_ns <= int(point["time_ns"]) <= end_ns
    )
    values = [
        direction * (float(point["best_price"]) - baseline_best) / TICK_SIZE
        for point in candidates
        if math.isfinite(float(point["best_price"]))
    ]
    return max([0.0, *values])


def _longest_zero_duration_ns(
    timeline: list[dict[str, Any]],
    start_ns: int,
    end_ns: int,
) -> int:
    current = _timeline_state_at(timeline, start_ns)
    last_time = start_ns
    zero_start = start_ns if bool(current["l0_zero"]) else None
    longest = 0
    for point in timeline:
        timestamp = int(point["time_ns"])
        if timestamp <= start_ns:
            continue
        if timestamp > end_ns:
            break
        if zero_start is not None:
            longest = max(longest, timestamp - zero_start)
        if bool(point["l0_zero"]):
            if zero_start is None:
                zero_start = timestamp
        else:
            zero_start = None
        last_time = timestamp
    if zero_start is not None:
        longest = max(longest, end_ns - zero_start)
    return max(0, int(longest))


def _zero_share(
    timeline: list[dict[str, Any]],
    start_ns: int,
    end_ns: int,
) -> float:
    if end_ns <= start_ns:
        return math.nan
    current = _timeline_state_at(timeline, start_ns)
    last_time = start_ns
    zero_ns = 0
    for point in timeline:
        timestamp = int(point["time_ns"])
        if timestamp <= start_ns:
            continue
        if timestamp > end_ns:
            break
        if bool(current["l0_zero"]):
            zero_ns += timestamp - last_time
        current = point
        last_time = timestamp
    if bool(current["l0_zero"]):
        zero_ns += end_ns - last_time
    return float(zero_ns / (end_ns - start_ns))


def extract_snapshot_features(
    frame: pd.DataFrame,
    row: pd.Series,
) -> dict[str, Any]:
    burst = _utc(row["burst_timestamp_utc"]).floor("ms")
    decision_cutoff = _utc(row["strict_feature_cutoff_utc_exclusive"]).floor("ms")
    if decision_cutoff <= burst:
        raise ValueError("Decision cutoff is not after the burst")
    end_250 = min(burst + pd.Timedelta(milliseconds=250), decision_cutoff)
    end_500 = min(burst + pd.Timedelta(milliseconds=500), decision_cutoff)
    burst_ns = int(burst.value)
    end_250_ns = int(end_250.value)
    end_500_ns = int(end_500.value)
    decision_ns = int(decision_cutoff.value)

    burst_state_last = _last_completed_ordinal(frame, burst)
    observation_last = _last_completed_ordinal(frame, end_500)

    state: dict[int, tuple[str, float, float]] = {}
    levels: dict[tuple[str, float], float] = {}
    for item in frame.iloc[: burst_state_last + 1].itertuples(index=False):
        _apply_preburst(item, state, levels)

    burst_side = str(row["burst_side"]).upper()
    attacked_side = "A" if burst_side == "BUY" else "B"
    aggressor_side = "B" if burst_side == "BUY" else "A"
    direction = 1 if burst_side == "BUY" else -1
    top = _top_levels(levels, attacked_side, 3)
    if len(top) != 3:
        raise RuntimeError(f"Cannot reconstruct L0:L2 for {row['BurstId']}")
    attacked_prices = {float(price) for price, _ in top}
    initial_l0 = float(top[0][0])
    initial_depth = float(sum(size for _, size in top))
    initial_queue = {
        order_id: (side, price, size)
        for order_id, (side, price, size) in state.items()
        if side == attacked_side and price in attacked_prices and size > 0
    }
    initial_queue_size = float(sum(value[2] for value in initial_queue.values()))
    if initial_depth <= 0 or initial_queue_size <= 0:
        raise RuntimeError(f"Invalid initial attacked book for {row['BurstId']}")

    post = frame.iloc[burst_state_last + 1 : observation_last + 1]
    fill_keys: dict[tuple[int, int, float], float] = defaultdict(float)
    for item in post.loc[post["action"].eq("F")].itertuples(index=False):
        event_ns = int(item.ts_event.value)
        if event_ns < burst_ns or event_ns >= end_500_ns:
            continue
        price = float(item.price) if pd.notna(item.price) else math.nan
        fill_keys[(int(item.order_id), event_ns, price)] += float(item.size)

    tokens: list[dict[str, Any]] = []
    tokens_by_order: dict[int, list[int]] = defaultdict(list)
    removal_lots: dict[float, deque[list[float]]] = defaultdict(deque)

    def reduce_tokens(order_id: int, quantity: float, timestamp_ns: int) -> None:
        remaining_to_remove = max(0.0, quantity)
        for token_index in reversed(tokens_by_order.get(order_id, [])):
            if remaining_to_remove <= 0:
                break
            token = tokens[token_index]
            current = float(token["remaining"])
            if current <= 0:
                continue
            removed = min(current, remaining_to_remove)
            token["remaining"] = current - removed
            token["changes"].append((timestamp_ns, token["remaining"]))
            remaining_to_remove -= removed

    def record_removal(timestamp_ns: int, price: float, quantity: float) -> None:
        if quantity > 0 and price in attacked_prices:
            removal_lots[price].append([float(timestamp_ns), float(quantity)])

    def match_refill(
        timestamp_ns: int,
        order_id: int,
        price: float,
        quantity: float,
    ) -> float:
        if quantity <= 0 or price not in attacked_prices:
            return 0.0
        queue = removal_lots[price]
        threshold = timestamp_ns - 100_000_000
        while queue and queue[0][0] < threshold:
            queue.popleft()
        available = quantity
        matched = 0.0
        while queue and available > 0:
            lot = queue[0]
            take = min(float(lot[1]), available)
            matched += take
            available -= take
            lot[1] -= take
            if lot[1] <= 1e-9:
                queue.popleft()
        if matched > 0:
            token_index = len(tokens)
            tokens.append(
                {
                    "order_id": order_id,
                    "price": price,
                    "start_ns": timestamp_ns,
                    "initial_qty": matched,
                    "remaining": matched,
                    "changes": [],
                }
            )
            tokens_by_order[order_id].append(token_index)
        return matched

    initial_l0_zero = levels.get((attacked_side, initial_l0), 0.0) <= 0
    timeline: list[dict[str, Any]] = [
        {
            "time_ns": burst_ns,
            "best_price": initial_l0,
            "l0_zero": initial_l0_zero,
        }
    ]
    packet_records: list[dict[str, Any]] = []
    consumption_qty = 0.0
    pure_withdrawal_qty = 0.0
    aggressive_trade_qty = 0.0
    ambiguous_cancel_fill_rows = 0
    unknown_state_rows = 0
    refill_matched_qty = 0.0
    max_used_event_ns = burst_ns
    captured_250 = False
    queue_remaining_250 = initial_queue_size
    best_end_250 = initial_l0
    packets_before_250 = 0
    packets_before_500 = 0

    def capture_250() -> tuple[float, float]:
        queue_value = 0.0
        for order_id, (initial_side, initial_price, _) in initial_queue.items():
            current = state.get(order_id)
            if (
                current is not None
                and current[0] == initial_side
                and current[1] == initial_price
            ):
                queue_value += max(0.0, current[2])
        return queue_value, _best_price(levels, attacked_side)

    packet: list[Any] = []
    for item in post.itertuples(index=False):
        packet.append(item)
        if not bool(int(item.flags) & int(db.RecordFlags.F_LAST)):
            continue
        close_ns = int(item.ts_event.value)
        max_used_event_ns = max(max_used_event_ns, close_ns)
        if close_ns >= end_500_ns:
            break
        if not captured_250 and close_ns >= end_250_ns:
            queue_remaining_250, best_end_250 = capture_250()
            captured_250 = True

        best_before = _best_price(levels, attacked_side)
        packet_fill_qty = 0.0
        packet_removal_qty = 0.0
        packet_pure_cancel_qty = 0.0
        packet_refill_qty = 0.0
        packet_has_postburst_event = False

        for event in packet:
            event_ns = int(event.ts_event.value)
            action = str(event.action)
            side = str(event.side)
            price = float(event.price) if pd.notna(event.price) else math.nan
            size = float(event.size)
            order_id = int(event.order_id)
            in_postburst = event_ns >= burst_ns
            packet_has_postburst_event = packet_has_postburst_event or in_postburst

            if action == "R":
                for existing_id in list(tokens_by_order):
                    reduce_tokens(existing_id, math.inf, close_ns)
                state.clear()
                levels.clear()
                continue

            if action == "F":
                if (
                    in_postburst
                    and side == attacked_side
                    and price in attacked_prices
                ):
                    packet_fill_qty += size
                    packet_removal_qty += size
                    if close_ns < end_250_ns:
                        consumption_qty += size
                        record_removal(close_ns, price, size)
                continue

            if action == "T":
                directional_price_ok = (
                    price >= initial_l0 if direction > 0 else price <= initial_l0
                )
                if (
                    in_postburst
                    and close_ns < end_250_ns
                    and side == aggressor_side
                    and directional_price_ok
                ):
                    aggressive_trade_qty += size
                continue

            if action == "A":
                old = state.get(order_id)
                if old is not None:
                    reduce_tokens(order_id, math.inf, close_ns)
                    _update_level(levels, old[0], old[1], -old[2])
                state[order_id] = (side, price, size)
                _update_level(levels, side, price, size)
                if in_postburst and close_ns < end_500_ns:
                    matched = match_refill(close_ns, order_id, price, size)
                    packet_refill_qty += matched
                    refill_matched_qty += matched
                continue

            if action == "M":
                old = state.get(order_id)
                if old is None:
                    unknown_state_rows += 1
                    state[order_id] = (side, price, size)
                    _update_level(levels, side, price, size)
                    if in_postburst and close_ns < end_500_ns:
                        matched = match_refill(close_ns, order_id, price, size)
                        packet_refill_qty += matched
                        refill_matched_qty += matched
                    continue
                old_side, old_price, old_size = old
                _update_level(levels, old_side, old_price, -old_size)
                if old_side == side and old_price == price:
                    if size < old_size:
                        reduce_tokens(order_id, old_size - size, close_ns)
                    elif (
                        size > old_size
                        and in_postburst
                        and close_ns < end_500_ns
                    ):
                        matched = match_refill(
                            close_ns, order_id, price, size - old_size
                        )
                        packet_refill_qty += matched
                        refill_matched_qty += matched
                else:
                    reduce_tokens(order_id, math.inf, close_ns)
                    if in_postburst and close_ns < end_500_ns:
                        matched = match_refill(close_ns, order_id, price, size)
                        packet_refill_qty += matched
                        refill_matched_qty += matched
                state[order_id] = (side, price, size)
                _update_level(levels, side, price, size)
                continue

            if action == "C":
                old = state.get(order_id)
                if old is None:
                    unknown_state_rows += 1
                    continue
                old_side, old_price, old_size = old
                removed = min(size, old_size)
                reduce_tokens(order_id, removed, close_ns)
                _update_level(levels, old_side, old_price, -removed)
                remaining = old_size - removed
                if remaining <= 0:
                    state.pop(order_id, None)
                else:
                    state[order_id] = (old_side, old_price, remaining)

                key = (order_id, event_ns, price)
                paired_fill = fill_keys.get(key, 0.0)
                if paired_fill and not math.isclose(
                    paired_fill, size, rel_tol=0.0, abs_tol=1e-9
                ):
                    ambiguous_cancel_fill_rows += 1
                is_pure_cancel = paired_fill <= 0
                if (
                    in_postburst
                    and close_ns < end_250_ns
                    and is_pure_cancel
                    and old_side == attacked_side
                    and old_price in attacked_prices
                ):
                    pure_withdrawal_qty += removed
                    packet_pure_cancel_qty += removed
                    packet_removal_qty += removed
                    record_removal(close_ns, old_price, removed)

        best_after = _best_price(levels, attacked_side)
        l0_zero = levels.get((attacked_side, initial_l0), 0.0) <= 0
        timeline.append(
            {
                "time_ns": close_ns,
                "best_price": best_after,
                "l0_zero": l0_zero,
            }
        )
        if close_ns < end_250_ns:
            packets_before_250 += 1
        packets_before_500 += 1
        if packet_has_postburst_event and close_ns >= burst_ns:
            packet_records.append(
                {
                    "time_ns": close_ns,
                    "best_before": best_before,
                    "best_after": best_after,
                    "aggression_qty": packet_fill_qty,
                    "removal_qty": packet_removal_qty,
                    "pure_cancel_qty": packet_pure_cancel_qty,
                    "refill_qty": packet_refill_qty,
                }
            )
        packet = []

    if not captured_250:
        queue_remaining_250, best_end_250 = capture_250()
    if not math.isfinite(best_end_250):
        best_end_250 = initial_l0

    durable_refill_qty = sum(
        _token_remaining_at(token, end_500_ns) for token in tokens
    )
    removed_qty = consumption_qty + pure_withdrawal_qty
    progress_ticks = max(
        0.0, direction * (best_end_250 - initial_l0) / TICK_SIZE
    )
    normalized_aggression = max(
        aggressive_trade_qty / max(initial_depth, 1.0),
        1.0 / max(initial_depth, 1.0),
    )
    impact_efficiency = progress_ticks / normalized_aggression

    eligible_aggression = 0
    absorption_motifs = 0
    eligible_removal = 0
    breakout_motifs = 0
    for packet_row in packet_records:
        packet_time = int(packet_row["time_ns"])
        horizon = packet_time + 100_000_000
        if horizon > end_500_ns:
            continue
        durable = any(
            packet_time <= int(token["start_ns"]) <= horizon
            and _token_remaining_at(token, horizon) > 0
            for token in tokens
        )
        advance = _max_directional_advance(
            timeline,
            packet_time,
            horizon,
            float(packet_row["best_before"]),
            direction,
        )
        if float(packet_row["aggression_qty"]) > 0:
            eligible_aggression += 1
            if durable and advance < 1.0 - 1e-9:
                absorption_motifs += 1
        if float(packet_row["removal_qty"]) > 0:
            eligible_removal += 1
            longest_zero = _longest_zero_duration_ns(
                timeline, packet_time, horizon
            )
            if (
                longest_zero >= 50_000_000
                and advance >= 1.0 - 1e-9
                and not durable
            ):
                breakout_motifs += 1

    return {
        "request_id": str(row["request_id"]),
        "BurstId": str(row["BurstId"]),
        "fecha": str(row["fecha"]),
        "year": int(row["year"]),
        "burst_side": burst_side,
        "attacked_side": attacked_side,
        "resolved_raw_symbol": str(row["resolved_raw_symbol"]),
        "burst_timestamp_utc": burst.isoformat(),
        "strict_feature_cutoff_utc_exclusive": decision_cutoff.isoformat(),
        "initial_l0_price_mbo": initial_l0,
        "initial_l0_l2_depth": initial_depth,
        "initial_l0_l2_order_count": len(initial_queue),
        "coverage_250ms": (end_250_ns - burst_ns) / 1_000_000.0,
        "coverage_500ms": (end_500_ns - burst_ns) / 1_000_000.0,
        "packets_before_250ms": packets_before_250,
        "packets_before_500ms": packets_before_500,
        "consumption_fill_qty_250ms": consumption_qty,
        "pure_withdrawal_qty_250ms": pure_withdrawal_qty,
        "aggressive_trade_qty_250ms": aggressive_trade_qty,
        "matched_refill_qty": refill_matched_qty,
        "durable_refill_qty_500ms": durable_refill_qty,
        "initial_queue_remaining_qty_250ms": queue_remaining_250,
        "directional_best_passive_progress_ticks_250ms": progress_ticks,
        "eligible_aggression_packets_500ms": eligible_aggression,
        "absorption_motif_packets_500ms": absorption_motifs,
        "eligible_removal_packets_500ms": eligible_removal,
        "breakout_motif_packets_500ms": breakout_motifs,
        "ambiguous_cancel_fill_rows": ambiguous_cancel_fill_rows,
        "unknown_state_rows": unknown_state_rows,
        "max_used_event_utc": pd.Timestamp(max_used_event_ns, tz="UTC").isoformat(),
        "max_used_before_decision_cutoff": max_used_event_ns < decision_ns,
        "events_after_cutoff_used": 0,
        "consumption_initial_depth_ratio_250ms": consumption_qty
        / max(initial_depth, 1.0),
        "withdrawal_initial_depth_ratio_250ms": pure_withdrawal_qty
        / max(initial_depth, 1.0),
        "durable_refill_removed_ratio_250ms": durable_refill_qty
        / max(removed_qty, 1.0),
        "initial_queue_survival_ratio_250ms": queue_remaining_250
        / max(initial_queue_size, 1.0),
        "impact_efficiency_250ms": impact_efficiency,
        "depletion_persistence_share_500ms": _zero_share(
            timeline, burst_ns, end_500_ns
        ),
        "absorption_motif_share_500ms": absorption_motifs
        / max(eligible_aggression, 1),
        "breakout_motif_share_500ms": breakout_motifs
        / max(eligible_removal, 1),
    }


def _extract_item(
    payload: tuple[int, int, dict[str, Any], str],
) -> tuple[int, dict[str, Any]]:
    index, total, row_values, data_dir_value = payload
    row = pd.Series(row_values)
    path = Path(data_dir_value) / f"{row['request_id']}.mbo.dbn.zst"
    if not path.exists():
        raise FileNotFoundError(path)
    frame = _load_frame(path)
    result = extract_snapshot_features(frame, row)
    result["_progress"] = (
        f"[{index + 1}/{total}] {row['BurstId']} "
        f"fill={result['consumption_initial_depth_ratio_250ms']:.3f} "
        f"withdraw={result['withdrawal_initial_depth_ratio_250ms']:.3f} "
        f"durable_refill={result['durable_refill_removed_ratio_250ms']:.3f}"
    )
    return index, result


def extract_ledger(
    manifest: pd.DataFrame,
    data_dir: Path,
    workers: int,
) -> pd.DataFrame:
    payloads = [
        (index, len(manifest), row, str(data_dir))
        for index, row in enumerate(manifest.to_dict(orient="records"))
    ]
    if workers == 1:
        results = map(_extract_item, payloads)
        executor = None
    else:
        executor = ProcessPoolExecutor(max_workers=workers)
        results = executor.map(_extract_item, payloads)
    rows: list[dict[str, Any]] = []
    try:
        for _, result in results:
            print(result.pop("_progress"), flush=True)
            rows.append(result)
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
    ledger = pd.DataFrame(rows)
    return ledger.merge(
        manifest[
            [
                "request_id",
                "family_label_only",
                "selection_seed",
                "selection_hash",
                "predictor_policy",
            ]
        ],
        on="request_id",
        how="left",
        validate="one_to_one",
    )


def _make_model() -> Any:
    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(
            C=MODEL_C,
            class_weight="balanced",
            solver="liblinear",
            max_iter=3000,
            random_state=RANDOM_SEED,
        ),
    )


def _usable_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    usable: list[str] = []
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.notna().sum() >= 3 and values.dropna().nunique() >= 2:
            usable.append(column)
    if not usable:
        raise ValueError("No usable predictors in LOYO training fold")
    return usable


def _fold_frames(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, float | None]:
    train_x = train_frame[columns].apply(pd.to_numeric, errors="coerce").copy()
    test_x = test_frame[columns].apply(pd.to_numeric, errors="coerce").copy()
    impact_cap: float | None = None
    impact = "impact_efficiency_250ms"
    if impact in columns:
        finite = train_x[impact].replace([np.inf, -np.inf], np.nan).dropna()
        if not finite.empty:
            impact_cap = max(0.0, float(finite.quantile(0.99)))
            train_x[impact] = train_x[impact].clip(lower=0.0, upper=impact_cap)
            test_x[impact] = test_x[impact].clip(lower=0.0, upper=impact_cap)
    return train_x, test_x, impact_cap


def _loyo_predictions(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    target: pd.Series | None = None,
) -> pd.DataFrame:
    y = (
        frame["target"].astype(int)
        if target is None
        else pd.Series(target.to_numpy(), index=frame.index)
    )
    rows: list[dict[str, Any]] = []
    for year in sorted(frame["year"].unique()):
        train_mask = frame["year"].ne(year)
        test_mask = frame["year"].eq(year)
        selected = _usable_columns(frame.loc[train_mask], columns)
        train_x, test_x, impact_cap = _fold_frames(
            frame.loc[train_mask], frame.loc[test_mask], selected
        )
        if y.loc[train_mask].nunique() < 2:
            raise ValueError(f"Training fold without both classes for {year}")
        model = _make_model()
        model.fit(train_x, y.loc[train_mask])
        probability = model.predict_proba(test_x)[:, 1]
        for index, value in zip(frame.index[test_mask], probability, strict=True):
            rows.append(
                {
                    "row_index": int(index),
                    "BurstId": frame.at[index, "BurstId"],
                    "fecha": frame.at[index, "fecha"],
                    "year": int(year),
                    "burst_side": frame.at[index, "burst_side"],
                    "family": frame.at[index, "family"],
                    "target": int(y.at[index]),
                    "probability_A": float(value),
                    "prediction": int(value >= 0.5),
                    "feature_count": len(selected),
                    "impact_cap_training_fold": impact_cap,
                }
            )
    return pd.DataFrame(rows).sort_values("row_index").reset_index(drop=True)


def _metrics(predictions: pd.DataFrame) -> dict[str, float | int]:
    if predictions.empty or predictions["target"].nunique() < 2:
        return {
            "n": len(predictions),
            "n_A": int(predictions.get("target", pd.Series(dtype=int)).eq(1).sum()),
            "n_B": int(predictions.get("target", pd.Series(dtype=int)).eq(0).sum()),
            "balanced_accuracy": math.nan,
            "roc_auc_A_vs_B": math.nan,
            "sensitivity_A": math.nan,
            "specificity_B": math.nan,
        }
    y = predictions["target"].to_numpy(dtype=int)
    pred = predictions["prediction"].to_numpy(dtype=int)
    probability = predictions["probability_A"].to_numpy(dtype=float)
    return {
        "n": len(predictions),
        "n_A": int((y == 1).sum()),
        "n_B": int((y == 0).sum()),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "roc_auc_A_vs_B": float(roc_auc_score(y, probability)),
        "sensitivity_A": float(pred[y == 1].mean()),
        "specificity_B": float((pred[y == 0] == 0).mean()),
    }


def _bootstrap_ci(predictions: pd.DataFrame) -> tuple[float, float]:
    rng = np.random.default_rng(RANDOM_SEED)
    y = predictions["target"].to_numpy(dtype=int)
    pred = predictions["prediction"].to_numpy(dtype=int)
    groups = [np.flatnonzero(y == value) for value in (0, 1)]
    values: list[float] = []
    for _ in range(BOOTSTRAPS):
        sampled = np.concatenate(
            [rng.choice(group, len(group), replace=True) for group in groups]
        )
        values.append(float(balanced_accuracy_score(y[sampled], pred[sampled])))
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def _permutation_p_value(
    frame: pd.DataFrame,
    columns: list[str],
    observed: float,
) -> float:
    rng = np.random.default_rng(RANDOM_SEED)
    exceed = 0
    for _ in range(PERMUTATIONS):
        shuffled = frame["target"].copy()
        for indexes in frame.groupby("year").groups.values():
            shuffled.loc[indexes] = rng.permutation(
                shuffled.loc[indexes].to_numpy()
            )
        permuted = _loyo_predictions(frame, columns, target=shuffled)
        score = float(_metrics(permuted)["balanced_accuracy"])
        exceed += int(score >= observed - 1e-12)
    return float((exceed + 1) / (PERMUTATIONS + 1))


def _direction_stability(
    clean: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    rows: list[dict[str, Any]] = []
    for year in sorted(clean["year"].unique()):
        for side in ("BUY", "SELL"):
            cell = clean.loc[
                clean["year"].eq(year) & clean["burst_side"].eq(side)
            ]
            for feature, expected_sign in DIRECTIONAL_EXPECTATIONS.items():
                mean_a = float(
                    pd.to_numeric(
                        cell.loc[cell["family"].eq(FAMILY_A), feature],
                        errors="coerce",
                    ).mean()
                )
                mean_b = float(
                    pd.to_numeric(
                        cell.loc[cell["family"].eq(FAMILY_B), feature],
                        errors="coerce",
                    ).mean()
                )
                difference = mean_a - mean_b
                coherent = bool(
                    math.isfinite(difference)
                    and difference * expected_sign > 0
                )
                rows.append(
                    {
                        "year": int(year),
                        "burst_side": side,
                        "feature": feature,
                        "expected_A_minus_B_sign": expected_sign,
                        "n_A": int(cell["family"].eq(FAMILY_A).sum()),
                        "n_B": int(cell["family"].eq(FAMILY_B).sum()),
                        "mean_A": mean_a,
                        "mean_B": mean_b,
                        "A_minus_B": difference,
                        "direction_coherent": coherent,
                    }
                )
    detail = pd.DataFrame(rows)
    cell_summary = (
        detail.groupby(["year", "burst_side"], as_index=False)
        .agg(
            coherent_features=("direction_coherent", "sum"),
            tested_features=("direction_coherent", "size"),
            n_A=("n_A", "max"),
            n_B=("n_B", "max"),
        )
    )
    cell_summary["cell_coherent"] = cell_summary["coherent_features"].ge(4)
    coherent_cells = int(cell_summary["cell_coherent"].sum())
    return detail, cell_summary, coherent_cells


def _evaluate(
    clean: pd.DataFrame,
    feature_sets: dict[str, list[str]],
    coherent_cells: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    metric_rows: list[dict[str, Any]] = []
    prediction_rows: list[pd.DataFrame] = []
    slice_rows: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        columns = feature_sets[family]
        predictions = _loyo_predictions(clean, columns)
        predictions["feature_family"] = family
        prediction_rows.append(predictions)
        overall = _metrics(predictions)
        ci_low, ci_high = _bootstrap_ci(predictions)
        permutation_p = _permutation_p_value(
            clean, columns, float(overall["balanced_accuracy"])
        )
        marginal_values: list[float] = []
        for dimension, column in (("year", "year"), ("side", "burst_side")):
            for value, group in predictions.groupby(column):
                values = _metrics(group)
                slice_rows.append(
                    {
                        "feature_family": family,
                        "dimension": dimension,
                        "slice": str(value),
                        **values,
                    }
                )
                score = float(values["balanced_accuracy"])
                if math.isfinite(score):
                    marginal_values.append(score)
        for (year, side), group in predictions.groupby(["year", "burst_side"]):
            values = _metrics(group)
            slice_rows.append(
                {
                    "feature_family": family,
                    "dimension": "year_side",
                    "slice": f"{int(year)}_{side}",
                    **values,
                }
            )
        metric_rows.append(
            {
                "feature_family": family,
                "model": "logistic_C_0.2_balanced",
                "validation": "LOYO_2022_2023_2024",
                "feature_count": len(columns),
                **overall,
                "balanced_accuracy_ci_low": ci_low,
                "balanced_accuracy_ci_high": ci_high,
                "permutation_p_within_year": permutation_p,
                "minimum_marginal_year_side_balanced_accuracy": min(
                    marginal_values
                ),
                "direction_coherent_year_side_cells": coherent_cells,
            }
        )
    metrics = pd.DataFrame(metric_rows)
    matrix = metrics.loc[
        metrics["feature_family"].eq("MATRIX_TRANSITIONS")
    ].iloc[0]
    mbo = metrics.loc[metrics["feature_family"].eq("MBO_SNAPSHOT_8")].iloc[0]
    best_simple_ba = max(float(matrix.balanced_accuracy), float(mbo.balanced_accuracy))
    best_simple_auc = max(float(matrix.roc_auc_A_vs_B), float(mbo.roc_auc_A_vs_B))
    metrics["gain_vs_matrix_balanced_accuracy"] = (
        metrics["balanced_accuracy"] - float(matrix.balanced_accuracy)
    )
    metrics["gain_vs_matrix_auc"] = (
        metrics["roc_auc_A_vs_B"] - float(matrix.roc_auc_A_vs_B)
    )
    metrics["gain_vs_best_simple_balanced_accuracy"] = (
        metrics["balanced_accuracy"] - best_simple_ba
    )
    metrics["gain_vs_best_simple_auc"] = (
        metrics["roc_auc_A_vs_B"] - best_simple_auc
    )
    metrics["pilot_gate_passed"] = (
        metrics["n"].ge(60)
        & metrics["balanced_accuracy"].ge(0.58)
        & metrics["roc_auc_A_vs_B"].ge(0.62)
        & metrics["sensitivity_A"].ge(0.55)
        & metrics["specificity_B"].ge(0.55)
        & (
            metrics["gain_vs_matrix_balanced_accuracy"].ge(0.03)
            | metrics["gain_vs_matrix_auc"].ge(0.03)
        )
        & metrics["direction_coherent_year_side_cells"].ge(5)
    )
    metrics["strict_discovery_gate_passed"] = (
        metrics["n"].ge(60)
        & metrics["balanced_accuracy"].ge(0.65)
        & metrics["roc_auc_A_vs_B"].ge(0.68)
        & metrics["sensitivity_A"].ge(0.60)
        & metrics["specificity_B"].ge(0.60)
        & metrics["balanced_accuracy_ci_low"].gt(0.55)
        & metrics["permutation_p_within_year"].le(0.05)
        & metrics["minimum_marginal_year_side_balanced_accuracy"].ge(0.55)
        & (
            metrics["gain_vs_best_simple_balanced_accuracy"].ge(0.03)
            | metrics["gain_vs_best_simple_auc"].ge(0.03)
        )
    )
    metrics["final_gate_passed"] = (
        metrics["pilot_gate_passed"]
        & metrics["strict_discovery_gate_passed"]
    )
    metrics["status"] = np.where(
        metrics["final_gate_passed"],
        "SUPERA_PUERTA_DISCOVERY",
        "NO_SUPERA_PUERTA_DISCOVERY",
    )
    return (
        metrics.set_index("feature_family").loc[FAMILY_ORDER].reset_index(),
        pd.concat(prediction_rows, ignore_index=True),
        pd.DataFrame(slice_rows),
    )


def _plot_metrics(metrics: pd.DataFrame, output: Path) -> Path:
    ordered = metrics.iloc[::-1]
    labels = (
        ordered["feature_family"]
        .str.replace("MATRIX_TRANSITIONS_PLUS_", "MATRIX+")
        .str.replace("MATRIX_TRANSITIONS", "MATRIX")
    )
    y = np.arange(len(ordered))
    plt.figure(figsize=(11.5, 5.8))
    plt.barh(
        y - 0.18,
        ordered["balanced_accuracy"],
        height=0.34,
        label="Balanced accuracy LOYO",
        color="#2563EB",
    )
    plt.barh(
        y + 0.18,
        ordered["roc_auc_A_vs_B"],
        height=0.34,
        label="ROC AUC LOYO",
        color="#0F766E",
    )
    plt.axvline(0.5, color="#111827", linestyle="--", linewidth=1)
    plt.axvline(0.65, color="#DC2626", linestyle=":", linewidth=1)
    plt.yticks(y, labels)
    plt.xlim(0, 1)
    plt.xlabel("Separación A vs B fuera de año")
    plt.title("MBO snapshot 8 — validación discovery causal")
    plt.legend(loc="lower right")
    plt.tight_layout()
    path = output / "mbo_snapshot_discovery_effectiveness.png"
    plt.savefig(path, dpi=180)
    plt.close()
    return path


def _build_report(
    output: Path,
    ledger: pd.DataFrame,
    clean: pd.DataFrame,
    metrics: pd.DataFrame,
    direction_cells: pd.DataFrame,
    matrix_audit: pd.DataFrame,
    figure_path: Path,
) -> tuple[Path, Path, dict[str, Any]]:
    primary = metrics.loc[
        metrics["feature_family"].eq(PRIMARY_FAMILY)
    ].iloc[0]
    success = bool(primary["final_gate_passed"])
    verdict = FINAL_YES if success else FINAL_NO
    quality = {
        "sessions": int(len(ledger)),
        "clean_ab": int(len(clean)),
        "families": ledger["family_label_only"].value_counts().to_dict(),
        "years": ledger["year"].value_counts().sort_index().to_dict(),
        "sides": ledger["burst_side"].value_counts().to_dict(),
        "events_after_cutoff_used": int(ledger["events_after_cutoff_used"].sum()),
        "cutoff_passed": int(ledger["max_used_before_decision_cutoff"].sum()),
        "minimum_coverage_250ms": float(ledger["coverage_250ms"].min()),
        "minimum_coverage_500ms": float(ledger["coverage_500ms"].min()),
        "ambiguous_cancel_fill_rows": int(
            ledger["ambiguous_cancel_fill_rows"].sum()
        ),
        "unknown_state_rows": int(ledger["unknown_state_rows"].sum()),
        "matrix_required_checks_passed": int(
            matrix_audit.loc[
                matrix_audit["required"].astype(str).str.lower().eq("true"),
                "passed",
            ]
            .astype(str)
            .str.lower()
            .eq("true")
            .sum()
        ),
        "matrix_required_checks": int(
            matrix_audit["required"].astype(str).str.lower().eq("true").sum()
        ),
    }
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "capable_discovery": success,
        "primary_family": PRIMARY_FAMILY,
        "primary_metrics": primary.to_dict(),
        "quality": quality,
        "figure": str(figure_path),
    }
    json_path = output / "mbo_snapshot_discovery_result.json"
    json_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    lines = [
        "# MBO SNAPSHOT 8 — RESULTADO PREDICTIVO DISCOVERY",
        "",
        f"## {verdict}",
        "",
        "Este veredicto usa únicamente A/B discovery 2022–2024. C permanece fuera "
        "del entrenamiento y 2025–2026 permanece sellado.",
        "",
        "## Integridad",
        "",
        f"- Sesiones MBO: {len(ledger)}/100.",
        f"- A/B limpio: {len(clean)}; A={int(clean['target'].eq(1).sum())}; "
        f"B={int(clean['target'].eq(0).sum())}.",
        f"- Cutoff causal: {quality['cutoff_passed']}/100; eventos posteriores usados: "
        f"{quality['events_after_cutoff_used']}.",
        f"- Cobertura mínima: {quality['minimum_coverage_250ms']:.3f} ms en W250; "
        f"{quality['minimum_coverage_500ms']:.3f} ms en W500.",
        f"- MATRIX causal: {quality['matrix_required_checks_passed']}/"
        f"{quality['matrix_required_checks']} controles requeridos.",
        f"- C/F ambiguos excluidos de cancelación pura: "
        f"{quality['ambiguous_cancel_fill_rows']}.",
        f"- Eventos incrementales sin estado previo: {quality['unknown_state_rows']}.",
        "- MAE/MFE/TP/SL/PnL no usados.",
        "",
        "## Resultados LOYO",
        "",
        "| bloque | n | BA | IC95% | AUC | sens A | esp B | p perm | min año/lado | 5/6 mecanismo | estado |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in metrics.itertuples(index=False):
        lines.append(
            f"| {row.feature_family} | {row.n} | {row.balanced_accuracy:.3f} | "
            f"[{row.balanced_accuracy_ci_low:.3f},{row.balanced_accuracy_ci_high:.3f}] | "
            f"{row.roc_auc_A_vs_B:.3f} | {row.sensitivity_A:.3f} | "
            f"{row.specificity_B:.3f} | {row.permutation_p_within_year:.4f} | "
            f"{row.minimum_marginal_year_side_balanced_accuracy:.3f} | "
            f"{int(row.direction_coherent_year_side_cells)}/6 | {row.status} |"
        )
    lines.extend(
        [
            "",
            "## Estabilidad física año × lado",
            "",
            "| celda | n A | n B | signos coherentes | estado |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for row in direction_cells.itertuples(index=False):
        lines.append(
            f"| {row.year} {row.burst_side} | {row.n_A} | {row.n_B} | "
            f"{row.coherent_features}/{row.tested_features} | "
            f"{'PASS' if row.cell_coherent else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Decisión",
            "",
            (
                "La puerta discovery se superó. El siguiente paso permitido es una "
                "única evaluación sellada 2025–2026; no se reajustan features."
                if success
                else "La puerta discovery no se superó. 2025–2026 no se abre y no "
                "se compran más fechas bajo esta representación."
            ),
            "",
            f"Gráfica: `{figure_path}`.",
            "",
        ]
    )
    report_path = output / "MBO_SNAPSHOT_DISCOVERY_100_PREDICTIVE_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path, json_path, result


def run(
    manifest_path: Path,
    data_dir: Path,
    matrix_joined_path: Path,
    output: Path,
    workers: int,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_csv(manifest_path)
    if len(manifest) != 100 or manifest["BurstId"].nunique() != 100:
        raise ValueError("Manifest must contain 100 unique BurstIds")
    if not manifest["pilot_stage"].astype(str).eq("DISCOVERY_100").all():
        raise ValueError("Manifest is not the frozen DISCOVERY_100 selection")
    if not manifest["predictor_policy"].astype(str).eq(
        "PREDECISION_ONLY_NO_MFE_MAE_TP_SL_PNL"
    ).all():
        raise ValueError("Predictor policy mismatch")

    ledger = extract_ledger(manifest, data_dir, workers)
    ledger_path = output / "mbo_snapshot_8_feature_ledger_100.csv"
    ledger.to_csv(ledger_path, index=False)
    if len(ledger) != 100 or ledger["BurstId"].nunique() != 100:
        raise RuntimeError("Feature ledger coverage mismatch")
    if not ledger["max_used_before_decision_cutoff"].astype(bool).all():
        raise RuntimeError("Causal cutoff violation")
    if int(ledger["events_after_cutoff_used"].sum()) != 0:
        raise RuntimeError("Post-cutoff events were used")
    if not np.isfinite(
        ledger[MBO_FEATURES].apply(pd.to_numeric, errors="coerce").to_numpy()
    ).all():
        raise RuntimeError("Primary MBO features contain NaN or infinite values")

    matrix_joined = pd.read_csv(matrix_joined_path, low_memory=False)
    transition_columns = [
        column for column in matrix_joined if column.startswith("tr__")
    ]
    if len(transition_columns) != 6:
        raise ValueError(
            f"Expected six frozen MATRIX transitions; found {len(transition_columns)}"
        )
    matrix_predictors = matrix_joined[["BurstId", *transition_columns]].copy()
    matrix_predictors = matrix_predictors.drop_duplicates("BurstId")
    expected_ids = set(manifest["BurstId"].astype(str))
    if set(matrix_predictors["BurstId"].astype(str)) != expected_ids:
        raise RuntimeError("MATRIX and MBO BurstId sets differ")
    matrix_audit_path = matrix_joined_path.parent / "matrix_postburst_causal_audit.csv"
    matrix_audit = pd.read_csv(matrix_audit_path)
    required = matrix_audit["required"].astype(str).str.lower().eq("true")
    passed = matrix_audit["passed"].astype(str).str.lower().eq("true")
    if not passed.loc[required].all():
        raise RuntimeError("Frozen MATRIX causal audit does not pass")

    joined = ledger.merge(
        matrix_predictors,
        on="BurstId",
        how="left",
        validate="one_to_one",
    )
    joined["family"] = joined["family_label_only"]
    joined["target"] = joined["family"].map({FAMILY_A: 1, FAMILY_B: 0})
    clean = joined.loc[joined["family"].isin([FAMILY_A, FAMILY_B])].copy()
    if (
        len(clean) != 70
        or int(clean["target"].eq(1).sum()) != 29
        or int(clean["target"].eq(0).sum()) != 41
    ):
        raise RuntimeError("Frozen A/B sample changed")
    clean["target"] = clean["target"].astype(int)
    joined.to_csv(output / "mbo_snapshot_discovery_joined_100.csv", index=False)

    direction_detail, direction_cells, coherent_cells = _direction_stability(clean)
    direction_detail.to_csv(
        output / "mbo_snapshot_direction_stability_detail.csv", index=False
    )
    direction_cells.to_csv(
        output / "mbo_snapshot_direction_stability_cells.csv", index=False
    )

    feature_sets = {
        "MATRIX_TRANSITIONS": transition_columns,
        "MBO_SNAPSHOT_8": MBO_FEATURES,
        PRIMARY_FAMILY: transition_columns + MBO_FEATURES,
    }
    metrics, predictions, slices = _evaluate(
        clean, feature_sets, coherent_cells
    )
    metrics.to_csv(output / "mbo_snapshot_discovery_metrics.csv", index=False)
    predictions.to_csv(
        output / "mbo_snapshot_discovery_loyo_predictions.csv", index=False
    )
    slices.to_csv(output / "mbo_snapshot_discovery_slices.csv", index=False)
    summary = (
        clean.groupby("family")[MBO_FEATURES]
        .agg(["count", "mean", "median", "std"])
    )
    summary.to_csv(output / "mbo_snapshot_feature_summary_by_family.csv")
    figure_path = _plot_metrics(metrics, output)
    report_path, json_path, result = _build_report(
        output,
        ledger,
        clean,
        metrics,
        direction_cells,
        matrix_audit,
        figure_path,
    )
    result.update(
        {
            "ledger": str(ledger_path),
            "metrics": str(output / "mbo_snapshot_discovery_metrics.csv"),
            "predictions": str(
                output / "mbo_snapshot_discovery_loyo_predictions.csv"
            ),
            "report": str(report_path),
            "json": str(json_path),
        }
    )
    print(json.dumps(result, indent=2, default=str))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--matrix-joined", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("--workers must be >=1")
    result = run(
        args.manifest,
        args.data_dir,
        args.matrix_joined,
        args.output,
        args.workers,
    )
    return 0 if result else 2


if __name__ == "__main__":
    raise SystemExit(main())
