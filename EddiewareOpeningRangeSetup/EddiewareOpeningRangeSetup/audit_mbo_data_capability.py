"""Read-only capability audit for the 100-session Databento MBO pilot.

This script does not create predictors, train models, alter entries, or use any
trade outcome. It inventories real DBN/ATAS files, audits event precedence and
cross-source clocks, and reconstructs order state for three real sessions.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import databento as db
import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
CONTEXT_DIR = BASE_DIR / "contexto_features_atas"
DATA_ROOT = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator")
MBO_DIR = DATA_ROOT / "databento_mbo" / "liquidity_burst_pilot_20260720"
BOOK_DIR = DATA_ROOT / "book_recordings"
MANIFEST_PATH = CONTEXT_DIR / "DATABENTO_MBO_PILOTO_100_DISCOVERY_20260722.csv"
MBP_LEDGER_PATH = BASE_DIR / "outputs" / "preentry_liquidity_features_20260720_preentry_r2" / "preentry_mbp_feature_ledger.csv"
MBO_FEATURE_LEDGER_PATH = BASE_DIR / "outputs" / "mbo_liquidity_burst_viability_20260720_r1" / "mbo_feature_ledger.csv"

REPORT_MD = CONTEXT_DIR / "MBO_DATA_CAPABILITY_AUDIT.md"
SCHEMA_CSV = CONTEXT_DIR / "MBO_SCHEMA_INVENTORY.csv"
FIELD_CSV = CONTEXT_DIR / "MBO_FIELD_COVERAGE.csv"
QUALITY_CSV = CONTEXT_DIR / "MBO_SESSION_QUALITY.csv"
SAMPLE_CSV = CONTEXT_DIR / "MBO_EVENT_RECONCILIATION_SAMPLE.csv"
LIMITS_MD = CONTEXT_DIR / "MBO_GAPS_AND_LIMITATIONS.md"

NY = ZoneInfo("America/New_York")
SAMPLE_DATES = ("2022-04-05", "2023-05-18", "2024-07-12")
PAIR_GROUP_COLUMNS = ["order_id", "ts_event", "price"]
EVENT_KEY_COLUMNS = [
    "ts_recv", "ts_event", "rtype", "publisher_id", "instrument_id",
    "action", "side", "price", "size", "channel_id", "order_id",
    "flags", "ts_in_delta", "sequence", "symbol",
]
OFFICIAL_MBO_URL = "https://databento.com/docs/schemas-and-data-formats/mbo"
OFFICIAL_ACTIONS_URL = "https://databento.com/docs/standards-and-conventions/common-fields-enums-types"
OFFICIAL_SNAPSHOT_URL = "https://databento.com/docs/standards-and-conventions/mbo-snapshot"
OFFICIAL_CME_URL = "https://databento.com/docs/venues-and-datasets/glbx-mdp3"
OFFICIAL_QUEUE_URL = "https://databento.com/docs/examples/order-book/queue-position"


def _anon_order(value: Any) -> str:
    if pd.isna(value):
        return ""
    return "OID_" + hashlib.sha256(f"mbo-audit-v1:{int(value)}".encode()).hexdigest()[:12]


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "N/A"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.{digits}f}"
    return str(value)


def _percent(numerator: float, denominator: float) -> float:
    return 100.0 * numerator / denominator if denominator else np.nan


def _read_dbn(path: Path) -> tuple[pd.DataFrame, str]:
    store = db.DBNStore.from_file(path)
    metadata = str(store.metadata)
    frame = store.to_df()
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    frame["raw_ordinal"] = np.arange(len(frame), dtype=np.int64)
    frame["ts_event"] = pd.to_datetime(frame["ts_event"], utc=True, errors="raise")
    frame["ts_recv"] = pd.to_datetime(frame["ts_recv"], utc=True, errors="raise")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["size"] = pd.to_numeric(frame["size"], errors="coerce").astype("int64")
    frame["order_id"] = pd.to_numeric(frame["order_id"], errors="coerce").astype("uint64")
    frame["sequence"] = pd.to_numeric(frame["sequence"], errors="coerce").astype("uint64")
    frame["flags"] = pd.to_numeric(frame["flags"], errors="coerce").astype("uint16")
    frame["action"] = frame["action"].astype(str)
    frame["side"] = frame["side"].astype(str)
    return frame, metadata


def _mark_fill_cancel_pairs(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["fill_cancel_paired"] = False
    frame["fill_cancel_relation"] = "NOT_APPLICABLE"
    relevant = frame["action"].isin(["F", "C"])
    grouped = (
        frame.loc[relevant]
        .groupby([*PAIR_GROUP_COLUMNS, "action"], sort=False)["size"]
        .sum()
        .unstack("action", fill_value=0)
    )
    if "F" not in grouped:
        grouped["F"] = 0
    if "C" not in grouped:
        grouped["C"] = 0
    grouped["relation"] = np.select(
        [
            grouped["F"].gt(0) & grouped["C"].gt(0) & grouped["F"].eq(grouped["C"]),
            grouped["F"].gt(0) & grouped["C"].gt(0),
            grouped["F"].gt(0),
            grouped["C"].gt(0),
        ],
        [
            "EXACT_GROUP_FILL_C_MATCH",
            "AMBIGUOUS_FILL_C_QUANTITY_MISMATCH",
            "FILL_WITHOUT_C_SAME_KEY",
            "C_WITHOUT_FILL_SAME_KEY",
        ],
        default="NOT_APPLICABLE",
    )
    relation_map = grouped["relation"]
    keys = pd.MultiIndex.from_frame(frame.loc[relevant, PAIR_GROUP_COLUMNS])
    relations = relation_map.reindex(keys).to_numpy()
    frame.loc[relevant, "fill_cancel_relation"] = relations
    frame.loc[relevant, "fill_cancel_paired"] = relations == "EXACT_GROUP_FILL_C_MATCH"
    return frame


def _queue_ahead(
    order_id: int,
    state: dict[int, dict[str, Any]],
    queues: dict[tuple[str, float], list[int]],
) -> float:
    current = state.get(order_id)
    if not current or not current["origin_observed"]:
        return np.nan
    queue = queues.get((current["side"], current["price"]), [])
    total = 0.0
    for queued_id in queue:
        if queued_id == order_id:
            return total
        queued = state.get(queued_id)
        if queued and queued["origin_observed"]:
            total += float(queued["size"])
    return np.nan


@dataclass
class ReconciliationResult:
    events: pd.DataFrame
    book_changes: pd.DataFrame
    lifecycle: pd.DataFrame
    summary: dict[str, Any]


def reconstruct_orders(frame: pd.DataFrame) -> ReconciliationResult:
    frame = _mark_fill_cancel_pairs(frame)
    state: dict[int, dict[str, Any]] = {}
    queues: dict[tuple[str, float], list[int]] = defaultdict(list)
    order_info: dict[int, dict[str, Any]] = {}
    last_fill: dict[int, pd.Timestamp] = {}
    pending_fill_qty: dict[tuple[int, pd.Timestamp, float], float] = defaultdict(float)
    fill_modify_pair_keys: set[tuple[int, pd.Timestamp, float]] = set()
    level_aggression: dict[tuple[str, float], list[pd.Timestamp]] = defaultdict(list)
    event_rows: list[dict[str, Any]] = []
    change_rows: list[dict[str, Any]] = []

    for item in frame.itertuples(index=False):
        action = str(item.action)
        order_id = int(item.order_id)
        price = float(item.price) if pd.notna(item.price) else np.nan
        side = str(item.side)
        size = int(item.size)
        current = state.get(order_id)
        before = float(current["size"]) if current else np.nan
        price_before = float(current["price"]) if current else np.nan
        queue_before = _queue_ahead(order_id, state, queues)
        after = before
        quantity_change = 0.0
        price_changed: float | int = np.nan
        size_changed: float | int = np.nan
        state_known = current is not None
        cycle_origin_observed = bool(current and current["origin_observed"])
        status = "EXPLICIT_NO_BOOK_CHANGE"
        subtype = action

        if action == "A":
            subtype = "ADD_NEW_ORDER"
            if current is not None:
                status = "INCONSISTENT_DUPLICATE_ADD"
            else:
                queue_before = sum(
                    float(state[value]["size"])
                    for value in queues.get((side, price), [])
                    if value in state and state[value]["origin_observed"]
                )
                state[order_id] = {
                    "side": side, "price": price, "size": float(size),
                    "origin_observed": True, "add_time": item.ts_event,
                }
                queues[(side, price)].append(order_id)
                order_info[order_id] = {
                    "add_time": item.ts_event, "initial_price": price, "side": side,
                    "initial_size": float(size), "first_fill": pd.NaT,
                    "first_cancel": pd.NaT, "same_id_refills": 0,
                }
                before = 0.0
                after = float(size)
                quantity_change = float(size)
                state_known = True
                cycle_origin_observed = True
                status = "RECONCILED"
                change_rows.append({
                    "ts_event": item.ts_event, "side": side, "price": price,
                    "delta": float(size), "action": action, "order_id": order_id,
                })
        elif action == "M":
            subtype = "MODIFY_PRICE_OR_SIZE"
            if current is None:
                state[order_id] = {
                    "side": side, "price": price, "size": float(size),
                    "origin_observed": False, "add_time": pd.NaT,
                }
                queues[(side, price)].append(order_id)
                after = float(size)
                state_known = False
                cycle_origin_observed = False
                status = "LEFT_CENSORED_MODIFY_ANCHORS_STATE"
            else:
                old_side = current["side"]
                old_price = float(current["price"])
                old_size = float(current["size"])
                price_changed = int(old_price != price)
                size_changed = int(old_size != size)
                quantity_change = float(size) - old_size
                loses_priority = bool(old_price != price or old_size < size)
                fill_key = (order_id, item.ts_event, price)
                pending_qty = pending_fill_qty.get(fill_key, 0.0)
                if old_price == price and pending_qty > 0 and np.isclose(old_size - float(size), pending_qty):
                    fill_modify_pair_keys.add(fill_key)
                    subtype = "FILL_BOOK_REMAINDER_MODIFY"
                queue = queues.get((old_side, old_price), [])
                if loses_priority and order_id in queue:
                    queue.remove(order_id)
                if old_price != price:
                    change_rows.append({
                        "ts_event": item.ts_event, "side": old_side, "price": old_price,
                        "delta": -old_size, "action": "M_OLD_PRICE", "order_id": order_id,
                    })
                    change_rows.append({
                        "ts_event": item.ts_event, "side": side, "price": price,
                        "delta": float(size), "action": "M_NEW_PRICE", "order_id": order_id,
                    })
                else:
                    change_rows.append({
                        "ts_event": item.ts_event, "side": side, "price": price,
                        "delta": float(size) - old_size, "action": action, "order_id": order_id,
                    })
                current.update({"side": side, "price": price, "size": float(size)})
                if loses_priority:
                    queues[(side, price)].append(order_id)
                after = float(size)
                state_known = True
                cycle_origin_observed = bool(current["origin_observed"])
                status = "RECONCILED"
                if subtype == "FILL_BOOK_REMAINDER_MODIFY":
                    pass
                elif old_size < size and order_id in order_info:
                    order_info[order_id]["same_id_refills"] += 1
                    if order_id in last_fill:
                        subtype = "MODIFY_SIZE_INCREASE_AFTER_FILL"
                    else:
                        subtype = "MODIFY_SIZE_INCREASE"
                elif old_price != price:
                    subtype = "MODIFY_PRICE"
                elif old_size != size:
                    subtype = "MODIFY_SIZE"
        elif action == "C":
            if item.fill_cancel_relation == "EXACT_GROUP_FILL_C_MATCH":
                subtype = "FILL_BOOK_DECREMENT"
            elif item.fill_cancel_relation == "AMBIGUOUS_FILL_C_QUANTITY_MISMATCH":
                subtype = "AMBIGUOUS_CANCEL_AND_FILL_SAME_KEY"
            else:
                subtype = "PURE_CANCEL_INFERRED"
            if current is None:
                status = "LEFT_CENSORED_CANCEL_NO_PRIOR_STATE"
                state_known = False
            else:
                before = float(current["size"])
                if size > before:
                    status = "INCONSISTENT_CANCEL_EXCEEDS_STATE"
                    after = np.nan
                else:
                    after = before - float(size)
                    quantity_change = -float(size)
                    status = "RECONCILED"
                    change_rows.append({
                        "ts_event": item.ts_event, "side": current["side"],
                        "price": float(current["price"]), "delta": -float(size),
                        "action": action, "order_id": order_id,
                    })
                    current["size"] = after
                    if (
                        item.fill_cancel_relation == "C_WITHOUT_FILL_SAME_KEY"
                        and order_id in order_info
                        and pd.isna(order_info[order_id]["first_cancel"])
                    ):
                        order_info[order_id]["first_cancel"] = item.ts_event
                    if after == 0:
                        queue = queues.get((current["side"], float(current["price"])), [])
                        if order_id in queue:
                            queue.remove(order_id)
                        state.pop(order_id, None)
        elif action == "F":
            subtype = "RESTING_ORDER_FILL"
            if current is None:
                status = "EXPLICIT_FILL_LEFT_CENSORED_STATE"
                state_known = False
            else:
                status = "RECONCILED_FILL_NO_DIRECT_BOOK_CHANGE"
                state_known = True
                before = float(current["size"])
                after = before
                level_aggression[(current["side"], float(current["price"]))].append(item.ts_event)
                if order_id in order_info and pd.isna(order_info[order_id]["first_fill"]):
                    order_info[order_id]["first_fill"] = item.ts_event
            last_fill[order_id] = item.ts_event
            pending_fill_qty[(order_id, item.ts_event, price)] += float(size)
        elif action == "T":
            subtype = "AGGRESSOR_TRADE"
            status = "EXPLICIT_TRADE_NO_RESTING_STATE"
            before = after = np.nan
            state_known = False
        elif action == "R":
            subtype = "CLEAR_BOOK"
            state.clear()
            queues.clear()
            status = "RECONCILED_CLEAR"
        else:
            status = "EXPLICIT_OTHER"

        event_rows.append({
            "raw_ordinal": int(item.raw_ordinal),
            "timestamp_exchange": item.ts_event,
            "timestamp_receive": item.ts_recv,
            "sequence": int(item.sequence),
            "order_id_raw": order_id,
            "event_type": action,
            "event_subtype": subtype,
            "side": side,
            "price": price,
            "price_before": price_before,
            "qty_before": before,
            "qty_change": quantity_change,
            "qty_after": after,
            "trade_qty": float(size) if action in {"F", "T"} else 0.0,
            "event_size": float(size),
            "queue_ahead_estimate": queue_before,
            "queue_estimate_kind": (
                "LOWER_BOUND_OBSERVED_ORDERS_ONLY"
                if math.isfinite(queue_before) else "UNAVAILABLE_INITIAL_QUEUE_MISSING"
            ),
            "state_known_before": int(state_known),
            "cycle_origin_add_observed": int(cycle_origin_observed),
            "price_changed_inferred": price_changed,
            "size_changed_inferred": size_changed,
            "fill_cancel_pair_explicitly_reconciled": int(bool(item.fill_cancel_paired)),
            "fill_cancel_relation": item.fill_cancel_relation,
            "fill_book_effect_reconciled": int(bool(item.fill_cancel_paired)),
            "fill_book_effect_event": "C" if item.fill_cancel_paired else "",
            "reconciliation_status": status,
        })

    lifecycle_rows = []
    final_state = state.copy()
    for order_id, info in order_info.items():
        add_time = info["add_time"]
        initial_level = (info["side"], info["initial_price"])
        aggression_times = [
            value for value in level_aggression.get(initial_level, []) if value >= add_time
        ]
        alive = order_id in final_state
        first_fill = info["first_fill"]
        first_cancel = info["first_cancel"]
        lifecycle_rows.append({
            "order_id_raw": order_id,
            "add_time": add_time,
            "side": info["side"],
            "initial_price": info["initial_price"],
            "initial_size": info["initial_size"],
            "alive_at_window_end": int(alive),
            "aggression_observed_at_initial_level": int(bool(aggression_times)),
            "survived_observed_aggression": int(bool(aggression_times) and alive),
            "first_fill_time": first_fill,
            "time_to_first_fill_ms": (
                (first_fill - add_time).total_seconds() * 1000 if pd.notna(first_fill) else np.nan
            ),
            "first_cancel_time": first_cancel,
            "time_to_first_cancel_ms": (
                (first_cancel - add_time).total_seconds() * 1000 if pd.notna(first_cancel) else np.nan
            ),
            "same_id_size_increase_count": info["same_id_refills"],
        })

    events = pd.DataFrame(event_rows)
    if fill_modify_pair_keys:
        fill_modify_key_index = pd.MultiIndex.from_tuples(
            fill_modify_pair_keys, names=["order_id_raw", "timestamp_exchange", "price"]
        )
        event_key_index = pd.MultiIndex.from_frame(
            events[["order_id_raw", "timestamp_exchange", "price"]]
        )
        via_modify = event_key_index.isin(fill_modify_key_index)
        fill_rows_via_modify = via_modify & events["event_type"].eq("F")
        modify_rows_for_fill = via_modify & events["event_type"].eq("M")
        events.loc[fill_rows_via_modify, "fill_book_effect_reconciled"] = 1
        events.loc[fill_rows_via_modify, "fill_book_effect_event"] = "M"
        events.loc[fill_rows_via_modify, "fill_cancel_relation"] = "EXACT_GROUP_FILL_M_STATE_MATCH"
        events.loc[modify_rows_for_fill, "fill_book_effect_reconciled"] = 1
        events.loc[modify_rows_for_fill, "fill_book_effect_event"] = "M"
    book_changes = pd.DataFrame(change_rows)
    lifecycle = pd.DataFrame(lifecycle_rows)
    identity_dependent = events["event_type"].isin(["M", "C", "F"])
    unreconciled = events["reconciliation_status"].str.startswith(("LEFT_CENSORED", "INCONSISTENT", "EXPLICIT_FILL_LEFT"))
    fills = events["event_type"].eq("F")
    modifies = events["event_type"].eq("M")
    cancels = events["event_type"].eq("C")
    fill_groups = (
        events.loc[fills]
        .groupby(["order_id_raw", "timestamp_exchange", "price"], sort=False)
        .agg(
            fill_qty=("trade_qty", "sum"),
            qty_before=("qty_before", "first"),
            book_effect_reconciled=("fill_book_effect_reconciled", "max"),
        )
        .reset_index()
    )
    known_fill_groups = fill_groups["qty_before"].notna()
    partial_fill_groups = known_fill_groups & fill_groups["fill_qty"].lt(fill_groups["qty_before"])
    complete_fill_groups = known_fill_groups & fill_groups["fill_qty"].eq(fill_groups["qty_before"])
    summary = {
        "identity_dependent_events": int(identity_dependent.sum()),
        "identity_unreconciled_events": int((identity_dependent & unreconciled).sum()),
        "identity_unreconciled_pct": _percent((identity_dependent & unreconciled).sum(), identity_dependent.sum()),
        "fill_rows": int(fills.sum()),
        "fill_groups": len(fill_groups),
        "fill_state_known_groups": int(known_fill_groups.sum()),
        "fill_state_known_pct": _percent(known_fill_groups.sum(), len(fill_groups)),
        "fill_book_effect_reconciled_groups": int(fill_groups["book_effect_reconciled"].sum()),
        "fill_book_effect_reconciled_pct": _percent(
            fill_groups["book_effect_reconciled"].sum(), len(fill_groups)
        ),
        "partial_fill_inferred_groups": int(partial_fill_groups.sum()),
        "complete_fill_inferred_groups": int(complete_fill_groups.sum()),
        "modify_rows": int(modifies.sum()),
        "modify_state_known_rows": int((modifies & events["qty_before"].notna()).sum()),
        "modify_price_inferred_rows": int(pd.to_numeric(events["price_changed_inferred"], errors="coerce").eq(1).sum()),
        "modify_size_inferred_rows": int(pd.to_numeric(events["size_changed_inferred"], errors="coerce").eq(1).sum()),
        "cancel_rows": int(cancels.sum()),
        "pure_cancel_rows": int((
            cancels & events["fill_cancel_relation"].eq("C_WITHOUT_FILL_SAME_KEY")
        ).sum()),
        "ambiguous_cancel_fill_rows": int((
            cancels & events["fill_cancel_relation"].eq("AMBIGUOUS_FILL_C_QUANTITY_MISMATCH")
        ).sum()),
        "fill_book_decrement_rows": int((cancels & events["fill_cancel_pair_explicitly_reconciled"].eq(1)).sum()),
        "fill_book_modify_rows": int((
            modifies & events["fill_book_effect_event"].eq("M")
        ).sum()),
        "orders_added_in_window": len(lifecycle),
        "orders_alive_at_end": int(lifecycle.get("alive_at_window_end", pd.Series(dtype=int)).sum()),
        "orders_aggressed_at_initial_level": int(lifecycle.get("aggression_observed_at_initial_level", pd.Series(dtype=int)).sum()),
        "orders_survived_observed_aggression": int(lifecycle.get("survived_observed_aggression", pd.Series(dtype=int)).sum()),
        "same_id_size_increases": int(lifecycle.get("same_id_size_increase_count", pd.Series(dtype=int)).sum()),
    }
    return ReconciliationResult(events, book_changes, lifecycle, summary)


def _read_book_file(path: Path, kind: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    columns = (
        ["time_ny", "side", "price", "volume"]
        if kind == "mbp"
        else ["time_ny", "price", "volume", "direction"]
    )
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    frame["raw_ordinal"] = np.arange(len(frame), dtype=np.int64)
    frame["seconds_ny"] = pd.to_timedelta(frame["time_ny"], errors="coerce").dt.total_seconds()
    frame["time_ms_ny"] = np.rint(frame["seconds_ny"] * 1000).astype("Int64")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    return frame.dropna(subset=["seconds_ny", "price", "volume"]).reset_index(drop=True)


def _counter_matches(left: list[tuple[Any, ...]], right: list[tuple[Any, ...]]) -> int:
    a = Counter(left)
    b = Counter(right)
    return int(sum(min(count, b.get(key, 0)) for key, count in a.items()))


def _greedy_time_match(
    left: pd.DataFrame,
    right: pd.DataFrame,
    keys: list[str],
    time_column: str,
    tolerance_ms: int = 5,
) -> tuple[int, list[int]]:
    matches = 0
    offsets: list[int] = []
    right_groups = {key: group[time_column].astype(int).sort_values().tolist() for key, group in right.groupby(keys, dropna=False)}
    for key, group in left.groupby(keys, dropna=False):
        right_times = right_groups.get(key, [])
        used = [False] * len(right_times)
        for left_time in group[time_column].astype(int).sort_values():
            candidates = [
                (abs(value - left_time), pos, value)
                for pos, value in enumerate(right_times)
                if not used[pos] and abs(value - left_time) <= tolerance_ms
            ]
            if not candidates:
                continue
            _, pos, value = min(candidates)
            used[pos] = True
            matches += 1
            offsets.append(int(value - left_time))
    return matches, offsets


def _cross_source_quality(
    frame: pd.DataFrame,
    book_changes: pd.DataFrame,
    row: pd.Series,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    date = str(row["fecha"])
    mbp_path = BOOK_DIR / f"mbp_{date}_NY.csv"
    tape_path = BOOK_DIR / f"tape_{date}_NY.csv"
    mbp = _read_book_file(mbp_path, "mbp")
    tape = _read_book_file(tape_path, "tape")
    start = pd.Timestamp(row["start_utc"]).tz_convert(NY)
    end = pd.Timestamp(row["end_utc_exclusive"]).tz_convert(NY)
    start_ms = int((start.hour * 3600 + start.minute * 60 + start.second) * 1000 + start.microsecond / 1000)
    end_ms = int((end.hour * 3600 + end.minute * 60 + end.second) * 1000 + end.microsecond / 1000)
    metrics: dict[str, Any] = {
        "mbp_file_exists": int(mbp_path.exists()),
        "tape_file_exists": int(tape_path.exists()),
        "mbp_file_bytes": mbp_path.stat().st_size if mbp_path.exists() else 0,
        "tape_file_bytes": tape_path.stat().st_size if tape_path.exists() else 0,
        "mbp_rows_all": len(mbp),
        "tape_rows_all": len(tape),
    }
    mbp_window = mbp.loc[mbp["time_ms_ny"].between(start_ms, end_ms, inclusive="left")].copy() if not mbp.empty else mbp
    tape_window = tape.loc[tape["time_ms_ny"].between(start_ms, end_ms, inclusive="left")].copy() if not tape.empty else tape
    metrics.update({
        "mbp_rows_request_window": len(mbp_window),
        "tape_rows_request_window": len(tape_window),
        "mbp_exact_duplicate_rows": int(mbp.duplicated(subset=["time_ny", "side", "price", "volume"]).sum()) if not mbp.empty else 0,
        "tape_exact_duplicate_rows": int(tape.duplicated(subset=["time_ny", "price", "volume", "direction"]).sum()) if not tape.empty else 0,
        "mbp_time_out_of_order_rows": int(mbp["seconds_ny"].diff().lt(0).sum()) if not mbp.empty else 0,
        "tape_time_out_of_order_rows": int(tape["seconds_ny"].diff().lt(0).sum()) if not tape.empty else 0,
    })

    trades = frame.loc[frame["action"].eq("T")].copy()
    event_ny = trades["ts_event"].dt.tz_convert(NY)
    trades["time_ms_ny"] = (
        event_ny.dt.hour * 3_600_000
        + event_ny.dt.minute * 60_000
        + event_ny.dt.second * 1000
        + event_ny.dt.microsecond // 1000
    ).astype(int)
    trades["volume"] = trades["size"].astype(float)
    trades["direction"] = trades["side"].map({"B": "Buy", "A": "Sell", "N": "Between"})
    trades["price_key"] = trades["price"].round(5)
    tape_window["price_key"] = tape_window.get("price", pd.Series(dtype=float)).round(5)
    exact_keys = ["time_ms_ny", "price_key", "volume", "direction"]
    exact_trade_matches = (
        _counter_matches(
            list(trades[exact_keys].itertuples(index=False, name=None)),
            list(tape_window[exact_keys].itertuples(index=False, name=None)),
        )
        if not trades.empty and not tape_window.empty else 0
    )
    relaxed_matches, offsets = (
        _greedy_time_match(
            trades, tape_window,
            keys=["price_key", "volume", "direction"],
            time_column="time_ms_ny",
            tolerance_ms=5,
        )
        if not trades.empty and not tape_window.empty else (0, [])
    )
    metrics.update({
        "mbo_trade_rows": len(trades),
        "mbo_tape_exact_matches": exact_trade_matches,
        "mbo_tape_exact_match_pct": _percent(exact_trade_matches, len(trades)),
        "mbo_tape_relaxed_5ms_matches": relaxed_matches,
        "mbo_tape_relaxed_5ms_match_pct": _percent(relaxed_matches, len(trades)),
        "tape_minus_mbo_offset_median_ms": float(np.median(offsets)) if offsets else np.nan,
        "tape_minus_mbo_offset_p95_abs_ms": float(np.quantile(np.abs(offsets), 0.95)) if offsets else np.nan,
    })

    mbp_changes = pd.DataFrame()
    if not mbp.empty:
        mbp["previous_volume"] = mbp.groupby(["side", "price"], sort=False)["volume"].shift(1)
        mbp["delta"] = mbp["volume"] - mbp["previous_volume"]
        mbp_changes = mbp.loc[
            mbp["time_ms_ny"].between(start_ms, end_ms, inclusive="left")
            & mbp["delta"].notna()
        ].copy()
        mbp_changes["side_code"] = mbp_changes["side"].map({"Ask": "A", "Bid": "B"})
        mbp_changes["price_key"] = mbp_changes["price"].round(5)
        mbp_changes["delta_key"] = mbp_changes["delta"].round(5)

    mbo_changes = book_changes.copy()
    if not mbo_changes.empty:
        event_ny_change = mbo_changes["ts_event"].dt.tz_convert(NY)
        mbo_changes["time_ms_ny"] = (
            event_ny_change.dt.hour * 3_600_000
            + event_ny_change.dt.minute * 60_000
            + event_ny_change.dt.second * 1000
            + event_ny_change.dt.microsecond // 1000
        ).astype(int)
        mbo_changes["side_code"] = mbo_changes["side"]
        mbo_changes["price_key"] = mbo_changes["price"].round(5)
        mbo_changes["delta_key"] = mbo_changes["delta"].round(5)
        mbo_grouped = mbo_changes.groupby(
            ["time_ms_ny", "side_code", "price_key"], as_index=False
        )["delta"].sum()
        mbo_grouped["delta_key"] = mbo_grouped["delta"].round(5)
    else:
        mbo_grouped = pd.DataFrame(columns=["time_ms_ny", "side_code", "price_key", "delta", "delta_key"])
    if not mbp_changes.empty:
        mbp_grouped = mbp_changes.groupby(
            ["time_ms_ny", "side_code", "price_key"], as_index=False
        )["delta"].sum()
        mbp_grouped["delta_key"] = mbp_grouped["delta"].round(5)
    else:
        mbp_grouped = pd.DataFrame(columns=["time_ms_ny", "side_code", "price_key", "delta", "delta_key"])
    book_exact_keys = ["time_ms_ny", "side_code", "price_key", "delta_key"]
    exact_book_matches = (
        _counter_matches(
            list(mbo_grouped[book_exact_keys].itertuples(index=False, name=None)),
            list(mbp_grouped[book_exact_keys].itertuples(index=False, name=None)),
        )
        if not mbo_grouped.empty and not mbp_grouped.empty else 0
    )
    relaxed_book_matches, book_offsets = (
        _greedy_time_match(
            mbo_grouped, mbp_grouped,
            keys=["side_code", "price_key", "delta_key"],
            time_column="time_ms_ny",
            tolerance_ms=5,
        )
        if not mbo_grouped.empty and not mbp_grouped.empty else (0, [])
    )
    metrics.update({
        "mbo_known_book_change_groups": len(mbo_grouped),
        "atas_mbp_change_groups": len(mbp_grouped),
        "mbo_mbp_exact_change_matches": exact_book_matches,
        "mbo_mbp_exact_change_match_pct": _percent(exact_book_matches, len(mbo_grouped)),
        "mbo_mbp_relaxed_5ms_change_matches": relaxed_book_matches,
        "mbo_mbp_relaxed_5ms_change_match_pct": _percent(relaxed_book_matches, len(mbo_grouped)),
        "mbp_minus_mbo_offset_median_ms": float(np.median(book_offsets)) if book_offsets else np.nan,
    })
    return metrics, mbp_changes, tape_window


def _sequence_and_clock_quality(frame: pd.DataFrame, row: pd.Series, metadata: str) -> dict[str, Any]:
    event_ns = frame["ts_event"].astype("int64").to_numpy()
    recv_ns = frame["ts_recv"].astype("int64").to_numpy()
    sequence = frame["sequence"].astype("uint64").to_numpy()
    event_diff = np.diff(event_ns)
    seq_diff = np.diff(sequence.astype(np.int64))
    positive_event_diff = event_diff[event_diff > 0]
    latency_us = (recv_ns - event_ns) / 1000.0
    first_actions = frame.groupby("order_id", sort=False)["action"].first()
    flags = frame["flags"].astype(int)
    fill_groups = frame.loc[frame["action"].eq("F")].groupby("ts_event")["size"].sum()
    trade_groups = frame.loc[frame["action"].eq("T")].groupby("ts_event")["size"].sum()
    shared = fill_groups.index.intersection(trade_groups.index)
    trade_fill_equal = int(np.isclose(fill_groups.loc[shared], trade_groups.loc[shared]).sum()) if len(shared) else 0
    fills = frame["action"].eq("F")
    cancels = frame["action"].eq("C")
    nominal_cutoff = pd.Timestamp(row["causal_cutoff_utc_inclusive"])
    end_exclusive = pd.Timestamp(row["end_utc_exclusive"])
    same_millisecond_tie = frame["ts_event"].gt(nominal_cutoff) & frame["ts_event"].lt(end_exclusive)
    repeated_exact = frame.duplicated(subset=EVENT_KEY_COLUMNS, keep="first")
    return {
        "request_id": row["request_id"],
        "fecha": row["fecha"],
        "BurstId": row["BurstId"],
        "path": str(MBO_DIR / f"{row['request_id']}.mbo.dbn.zst"),
        "format": "DBN zstd",
        "dataset": row["dataset"],
        "schema": row["schema"],
        "symbol_requested": row["symbols"],
        "metadata_stype_out": "InstrumentId",
        "metadata_text": metadata,
        "file_bytes": (MBO_DIR / f"{row['request_id']}.mbo.dbn.zst").stat().st_size,
        "rows": len(frame),
        "first_ts_event_utc": frame["ts_event"].min().isoformat(),
        "last_ts_event_utc": frame["ts_event"].max().isoformat(),
        "observed_span_ms": (frame["ts_event"].max() - frame["ts_event"].min()).total_seconds() * 1000,
        "request_start_gap_ms": (frame["ts_event"].min() - pd.Timestamp(row["start_utc"])).total_seconds() * 1000,
        "request_end_gap_ms": (pd.Timestamp(row["end_utc_exclusive"]) - frame["ts_event"].max()).total_seconds() * 1000,
        "instrument_id_count": frame["instrument_id"].nunique(),
        "instrument_ids": "|".join(map(str, sorted(frame["instrument_id"].unique()))),
        "publisher_ids": "|".join(map(str, sorted(frame["publisher_id"].unique()))),
        "channel_ids": "|".join(map(str, sorted(frame["channel_id"].unique()))),
        "symbol_values": "|".join(map(str, sorted(frame["symbol"].astype(str).unique()))),
        "action_A": int(frame["action"].eq("A").sum()),
        "action_C": int(cancels.sum()),
        "action_M": int(frame["action"].eq("M").sum()),
        "action_F": int(fills.sum()),
        "action_T": int(frame["action"].eq("T").sum()),
        "action_R": int(frame["action"].eq("R").sum()),
        "unique_order_ids": frame["order_id"].nunique(),
        "first_action_A_orders": int(first_actions.eq("A").sum()),
        "left_censored_orders": int(first_actions.ne("A").sum()),
        "first_action_A_share_pct": _percent(first_actions.eq("A").sum(), len(first_actions)),
        "exact_duplicate_rows": int(repeated_exact.sum()),
        "exact_duplicate_action_A": int((repeated_exact & frame["action"].eq("A")).sum()),
        "exact_duplicate_action_C": int((repeated_exact & frame["action"].eq("C")).sum()),
        "exact_duplicate_action_M": int((repeated_exact & frame["action"].eq("M")).sum()),
        "exact_duplicate_action_F": int((repeated_exact & frame["action"].eq("F")).sum()),
        "exact_duplicate_action_T": int((repeated_exact & frame["action"].eq("T")).sum()),
        "ts_event_out_of_order_rows": int((event_diff < 0).sum()),
        "sequence_decrease_rows": int((seq_diff < 0).sum()),
        "same_ts_event_rows": int(frame["ts_event"].duplicated(keep=False).sum()),
        "same_ts_event_sequence_rows": int(frame.duplicated(subset=["ts_event", "sequence"], keep=False).sum()),
        "minimum_positive_ts_event_step_ns": int(positive_event_diff.min()) if len(positive_event_diff) else np.nan,
        "submicrosecond_ts_event_rows_pct": _percent((event_ns % 1000 != 0).sum(), len(frame)),
        "sequence_gap_intervals": int((seq_diff > 1).sum()),
        "sequence_gap_units": int((seq_diff[seq_diff > 1] - 1).sum()),
        "flag_bad_ts_recv_rows": int(((flags & 8) != 0).sum()),
        "flag_maybe_bad_book_rows": int(((flags & 4) != 0).sum()),
        "flag_snapshot_rows": int(((flags & 32) != 0).sum()),
        "flag_mbp_rows": int(((flags & 16) != 0).sum()),
        "negative_recv_minus_event_rows": int((latency_us < 0).sum()),
        "recv_minus_event_median_us": float(np.median(latency_us)),
        "recv_minus_event_p99_us": float(np.quantile(latency_us, 0.99)),
        "recv_minus_event_max_us": float(np.max(latency_us)),
        "fill_rows_paired_to_cancel": int(frame.loc[fills, "fill_cancel_paired"].sum()),
        "fill_cancel_pair_pct": _percent(frame.loc[fills, "fill_cancel_paired"].sum(), fills.sum()),
        "trade_fill_shared_timestamp_groups": len(shared),
        "trade_fill_equal_qty_groups": trade_fill_equal,
        "trade_fill_equal_qty_pct": _percent(trade_fill_equal, len(shared)),
        "post_nominal_cutoff_same_millisecond_rows": int(same_millisecond_tie.sum()),
        "at_or_after_request_end_rows": int(frame["ts_event"].ge(end_exclusive).sum()),
    }


def _schema_inventory(
    aggregate_nulls: Counter[str],
    aggregate_rows: int,
    mbp_exists: int,
    tape_exists: int,
) -> pd.DataFrame:
    mbo_fields = [
        ("ts_recv", "datetime64[ns, UTC]", "capture-server receive time", "explicit"),
        ("ts_event", "datetime64[ns, UTC]", "matching-engine receive time", "explicit"),
        ("rtype", "uint8", "record type; observed 160", "explicit"),
        ("publisher_id", "uint16", "venue/dataset publisher", "explicit"),
        ("instrument_id", "uint32", "numeric instrument identity", "explicit"),
        ("action", "string", "A/C/M/F/T/R/N event code", "explicit"),
        ("side", "string", "resting side or aggressor side", "explicit"),
        ("price", "float64", "event/order price", "explicit"),
        ("size", "uint32", "event/order quantity per action semantics", "explicit"),
        ("channel_id", "uint8", "Databento normalized channel", "explicit"),
        ("order_id", "uint64", "venue order identifier", "explicit"),
        ("flags", "uint8", "event boundary and quality bit field", "explicit"),
        ("ts_in_delta", "int32", "matching-engine send offset before ts_recv", "explicit"),
        ("sequence", "uint32", "venue message sequence", "explicit"),
        ("symbol", "string", "requested continuous symbol mapping", "explicit"),
        ("raw_ordinal", "int64", "physical order in decoded DBN", "derived without reordering"),
    ]
    rows = []
    for field, dtype, meaning, status in mbo_fields:
        real_field = field
        rows.append({
            "dataset_version": "DATABENTO_MBO_PILOT100_RAW",
            "source_format": "DBN zstd",
            "field": field,
            "dtype": dtype,
            "meaning": meaning,
            "information_status": status,
            "coverage_rows": aggregate_rows - int(aggregate_nulls.get(real_field, 0)),
            "coverage_pct": _percent(aggregate_rows - int(aggregate_nulls.get(real_field, 0)), aggregate_rows),
            "session_coverage": "100/100",
            "notes": "Raw MBO; no snapshot records in requested windows.",
        })
    for field, dtype, meaning in [
        ("time_ny", "string HH:mm:ss.fff", "ATAS event time converted to New York"),
        ("side", "string", "Bid/Ask"),
        ("price", "decimal", "price level"),
        ("volume", "decimal", "new aggregate resting size"),
    ]:
        rows.append({
            "dataset_version": "ATAS_BOOKRECORDER_MBP",
            "source_format": "CSV",
            "field": field,
            "dtype": dtype,
            "meaning": meaning,
            "information_status": "explicit_aggregated",
            "coverage_rows": np.nan,
            "coverage_pct": np.nan,
            "session_coverage": f"{mbp_exists}/100",
            "notes": "Millisecond, no sequence, no order identity, source clock kind not persisted.",
        })
    for field, dtype, meaning in [
        ("time_ny", "string HH:mm:ss.fff", "ATAS trade time converted to New York"),
        ("price", "decimal", "trade price"),
        ("volume", "decimal", "trade quantity"),
        ("direction", "string", "Buy/Sell/Between"),
    ]:
        rows.append({
            "dataset_version": "ATAS_BOOKRECORDER_TAPE",
            "source_format": "CSV",
            "field": field,
            "dtype": dtype,
            "meaning": meaning,
            "information_status": "explicit_trade",
            "coverage_rows": np.nan,
            "coverage_pct": np.nan,
            "session_coverage": f"{tape_exists}/100",
            "notes": "Millisecond, no sequence, no receive/export timestamp.",
        })
    return pd.DataFrame(rows)


def _field_coverage(total: dict[str, Any]) -> pd.DataFrame:
    lifecycle_total = total["identity_dependent_events"]
    fill_rows = total["fill_rows"]
    rows = [
        ("Identificador único de orden", "EXPLICITO", "order_id", 100.0, "Venue ID; T identifies aggressor when available."),
        ("Tipo de evento ADD", "EXPLICITO", "action=A", 100.0, "Creates a displayed order; exact lifecycle origin only when the A is inside the window."),
        ("Tipo de evento CANCEL", "EXPLICITO_EVENTO_CAUSA_INFERIDA", "action=C", 100.0, "Explicit size reduction; whether it is pure cancellation or fill-driven is inferred."),
        ("Tipo de evento MODIFY/REPLACE", "EXPLICITO_MODIFY", "action=M", 100.0, "M supplies the new price/size; it does not link an old ID to a new ID."),
        ("Tipo de evento FILL", "EXPLICITO", "action=F and action=T", 100.0, "F identifies resting order fills; T is the aggressing trade summary."),
        ("Contratos ejecutados", "EXPLICITO", "action=T size; action=F size", 100.0, "T is trade summary; F identifies filled resting order. Never sum T+F."),
        ("Reducción del libro por cancelación", "EXPLICITO", "action=C size", 100.0, "C reduces resting size but includes C paired with fills."),
        ("Contratos cancelados sin ejecución", "INFERIDO_DEFENDIBLE", "C with no F at same order/time/price", total["fill_book_effect_reconciled_pct"], "Fill book effects are reconciled by grouped C or state-consistent M; cancellation reason remains inferred."),
        ("Evento de modificación", "EXPLICITO", "action=M", 100.0, "M means price and/or size changed."),
        ("Modificación de tamaño", "INFERIDO_CON_ESTADO_PREVIO", "compare M.size with prior state", total["modify_state_known_pct"], "New size explicit; changed component requires prior state."),
        ("Cambio de precio", "INFERIDO_CON_ESTADO_PREVIO", "compare M.price with prior state", total["modify_state_known_pct"], "New price explicit; prior price absent in first left-censored M."),
        ("Cancel-replace con identificador nuevo", "NO_DISPONIBLE", "none", 0.0, "No linkage field between old C and new A; proximity is only a heuristic."),
        ("Cantidad original", "PARCIAL", "A.size", total["first_action_A_share_pct"], "Exact only when ADD appears in the 10-second window."),
        ("Cantidad restante", "INFERIDO_CON_ESTADO", "A/M/C state machine", 100.0 - total["identity_unreconciled_pct"], "Not an explicit field."),
        ("Precio", "EXPLICITO", "price", 100.0, "Event/order price; level rank must be derived."),
        ("Lado BID/ASK", "EXPLICITO", "side", 100.0, "Action-dependent: resting side on book events, aggressor side on T."),
        ("Ejecución parcial", "INFERIDO_CON_ESTADO_PREVIO", "F.size < qty_before and paired C", total["fill_state_known_pct"], "F quantity explicit; partial/full classification inferred."),
        ("Ejecución completa", "INFERIDO_CON_ESTADO_PREVIO", "F.size == qty_before and paired C", total["fill_state_known_pct"], "Cannot classify left-censored orders."),
        ("Reposición de la misma orden", "INFERIDO_CON_ESTADO_PREVIO", "same order_id M size increase", total["modify_state_known_pct"], "Visible size increase; hidden iceberg intent is not observable."),
        ("Nueva orden en el mismo precio", "EXPLICITO_EVENTO_INFERIDA_RELACION", "A with new order_id and price", 100.0, "New order explicit; calling it replacement/refill is inferred."),
        ("Supervivencia de liquidez bajo agresión", "INFERIDO_CENSURADO", "ADD lifecycle + F/T at level + alive at cutoff", total["first_action_A_share_pct"], "Only orders born in-window; right-censored at cutoff."),
        ("Posición inicial en cola", "NO_DISPONIBLE", "snapshot/priority absent", 0.0, "No R/F_SNAPSHOT records; 10-second request starts mid-session."),
        ("Volumen delante por orden", "APROXIMACION_LIMITE_INFERIOR", "observed FIFO orders before order", total["first_action_A_share_pct"], "Excludes all orders already resting at window start."),
        ("Avance de cola", "APROXIMACION_LIMITE_INFERIOR", "observed A/M/C order list", total["first_action_A_share_pct"], "Unknown cancellations ahead cannot be located."),
        ("Órdenes canceladas delante", "PARCIAL", "C order_id + observed relative order", total["first_action_A_share_pct"], "Exact only among orders with known in-window priority."),
        ("Fills recibidos", "EXPLICITO", "F order_id/size", 100.0, "Fill does not directly update book; paired C does."),
        ("Prioridad precio-tiempo", "PARCIAL", "raw message order + sequence", total["first_action_A_share_pct"], "Relative priority for new in-window orders; initial priority missing."),
        ("Supervivencia por orden", "INFERIDO_CENSURADO", "state at cutoff", 100.0 - total["identity_unreconciled_pct"], "Observed-window survival only."),
        ("Tiempo hasta primer fill", "INFERIDO_EXACTO_EN_VENTANA", "first F ts_event - observed A ts_event", total["first_action_A_share_pct"], "Missing for left-censored and right-censored orders."),
        ("Tiempo hasta cancelación", "INFERIDO_EXACTO_EN_VENTANA", "first C ts_event - observed A ts_event", total["first_action_A_share_pct"], "C reason must be separated from fill-paired C."),
        ("Refill después de fill", "INFERIDO", "F then M size increase or new A at level", total["modify_state_known_pct"], "Same-ID visible refill distinguishable; new-ID intent not linkable."),
        ("Reposición repetida mismo nivel", "INFERIDO", "repeated A/M increases after removals", total["first_action_A_share_pct"], "Observable displayed behavior, not participant intent."),
        ("Exchange timestamp", "EXPLICITO", "ts_event", 100.0, "UTC nanoseconds; matching-engine receive time."),
        ("Resolución temporal real", "EXPLICITO_Y_MEDIDA", "ts_event int64 ns", 100.0, f"Nanosecond encoding; minimum positive step observed: {total['minimum_positive_ts_event_step_ns']} ns."),
        ("Número de secuencia", "EXPLICITO", "sequence", 100.0, "Venue/channel sequence; gaps after symbol filtering are not packet loss proof."),
        ("Identificación de paquetes perdidos", "PARCIAL", "flags F_MAYBE_BAD_BOOK + sequence", 100.0, "Quality flag is explicit and zero here; filtered sequence gaps cannot prove individual packet loss."),
        ("Trade/Tape asociado", "EXPLICITO_DENTRO_MBO_APROXIMADO_CON_ATAS", "T/F plus ts_event/sequence", 100.0, "MBO T/F association is recoverable by event group; ATAS tape is a different millisecond clock/feed."),
        ("Orden agresora o pasiva", "EXPLICITO_POR_EVENTO", "T.side versus F.order_id/side", 100.0, "T gives aggressor side; F names the passive resting order."),
        ("Profundidad/nivel del libro", "PRECIO_EXPLICITO_RANGO_INFERIDO_PARCIAL", "price + reconstructed state", total["first_action_A_share_pct"], "All event prices are present; exact initial depth/rank is unavailable without snapshot."),
        ("Prioridad o posición de cola", "PARCIAL", "raw order/sequence; no priority field", total["first_action_A_share_pct"], "Relative FIFO for in-window orders only; initial queue is missing."),
        ("Orden con timestamps iguales", "EXPLICITO", "raw DBN order + sequence", 100.0, "Do not sort only by timestamp."),
        ("Sincronización MBO/ATAS", "APROXIMADA", "UTC ns vs NY local ms", total["sessions_with_mbp_tape_pct"], "Different providers/clocks; empirical trade matching required."),
    ]
    return pd.DataFrame(rows, columns=[
        "capability", "classification", "real_field_or_rule", "usable_coverage_pct", "limitations",
    ])


def _manual_sample(
    row: pd.Series,
    recon: ReconciliationResult,
    metadata_row: pd.Series,
    mbp_changes: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    burst = pd.Timestamp(metadata_row["burst_timestamp_utc"])
    cutoff = pd.Timestamp(row["causal_cutoff_utc_inclusive"])
    burst_price = float(metadata_row["burst_price"])
    events = recon.events.copy()
    start = burst - pd.Timedelta(milliseconds=250)
    end = min(cutoff, burst + pd.Timedelta(milliseconds=750))
    window = events.loc[events["timestamp_exchange"].between(start, end, inclusive="both")].copy()
    near = window.loc[window["price"].sub(burst_price).abs().le(1.0)]
    price_counts = near["price"].dropna().value_counts()
    selected_prices = sorted(price_counts.head(5).index.tolist())
    sample = window.loc[window["price"].isin(selected_prices)].copy()
    if len(sample) < 20:
        start = burst - pd.Timedelta(seconds=1)
        end = cutoff
        window = events.loc[events["timestamp_exchange"].between(start, end, inclusive="both")].copy()
        near = window.loc[window["price"].sub(burst_price).abs().le(1.5)]
        selected_prices = sorted(near["price"].dropna().value_counts().head(5).index.tolist())
        sample = window.loc[window["price"].isin(selected_prices)].copy()
    sample["sample_session"] = row["fecha"]
    sample["BurstId"] = row["BurstId"]
    sample["burst_timestamp_exchange"] = burst
    sample["burst_price"] = burst_price
    sample["sample_window_start"] = start
    sample["sample_window_end"] = end
    sample["order_id"] = sample["order_id_raw"].map(_anon_order)

    level_rows: list[dict[str, Any]] = []
    change = recon.book_changes.loc[
        recon.book_changes["ts_event"].between(start, end, inclusive="both")
        & recon.book_changes["price"].isin(selected_prices)
    ].copy()
    mbp_local = mbp_changes.copy()
    if not mbp_local.empty:
        burst_ny = burst.tz_convert(NY)
        start_ms = int((start.tz_convert(NY).hour * 3600 + start.tz_convert(NY).minute * 60 + start.tz_convert(NY).second) * 1000 + start.tz_convert(NY).microsecond / 1000)
        end_ms = int((end.tz_convert(NY).hour * 3600 + end.tz_convert(NY).minute * 60 + end.tz_convert(NY).second) * 1000 + end.tz_convert(NY).microsecond / 1000)
        mbp_local = mbp_local.loc[mbp_local["time_ms_ny"].between(start_ms, end_ms, inclusive="both")]
    for side in ("A", "B"):
        for price in selected_prices:
            mbo_net = change.loc[change["side"].eq(side) & np.isclose(change["price"], price), "delta"].sum()
            if not mbp_local.empty:
                mbp_side = "Ask" if side == "A" else "Bid"
                mbp_net = mbp_local.loc[
                    mbp_local["side"].eq(mbp_side) & np.isclose(mbp_local["price"], price),
                    "delta",
                ].sum()
                mbp_count = int(
                    (mbp_local["side"].eq(mbp_side) & np.isclose(mbp_local["price"], price)).sum()
                )
            else:
                mbp_net = np.nan
                mbp_count = 0
            event_group = sample.loc[sample["side"].eq(side) & np.isclose(sample["price"], price)]
            if event_group.empty and mbp_count == 0:
                continue
            identity = event_group["event_type"].isin(["M", "C", "F"])
            bad = event_group["reconciliation_status"].str.startswith(("LEFT_CENSORED", "INCONSISTENT", "EXPLICIT_FILL_LEFT"))
            add_delta = change.loc[
                change["side"].eq(side)
                & np.isclose(change["price"], price)
                & change["action"].eq("A"),
                "delta",
            ].sum()
            modify_delta = change.loc[
                change["side"].eq(side)
                & np.isclose(change["price"], price)
                & change["action"].str.startswith("M"),
                "delta",
            ].sum()
            cancel_delta = change.loc[
                change["side"].eq(side)
                & np.isclose(change["price"], price)
                & change["action"].eq("C"),
                "delta",
            ].sum()
            fill_qty = event_group.loc[event_group["event_type"].eq("F"), "trade_qty"].sum()
            pure_cancel_qty = -event_group.loc[
                event_group["event_type"].eq("C")
                & event_group["fill_cancel_relation"].eq("C_WITHOUT_FILL_SAME_KEY"),
                "qty_change",
            ].sum()
            fill_book_decrement_qty = -event_group.loc[
                event_group["event_type"].eq("C")
                & event_group["fill_cancel_pair_explicitly_reconciled"].eq(1),
                "qty_change",
            ].sum()
            equation_residual = float(mbo_net - (add_delta + modify_delta + cancel_delta))
            level_rows.append({
                "fecha": row["fecha"],
                "side": side,
                "price": price,
                "mbo_sample_events": len(event_group),
                "additions_net_qty": float(add_delta),
                "modifications_net_qty": float(modify_delta),
                "cancellations_and_fill_decrements_net_qty": float(cancel_delta),
                "resting_fill_qty_explicit": float(fill_qty),
                "pure_cancel_qty_inferred": float(pure_cancel_qty),
                "fill_book_decrement_qty": float(fill_book_decrement_qty),
                "mbo_known_net_book_change": float(mbo_net),
                "book_equation_residual": equation_residual,
                "atas_mbp_net_change": float(mbp_net) if pd.notna(mbp_net) else np.nan,
                "net_change_difference": float(mbo_net - mbp_net) if pd.notna(mbp_net) else np.nan,
                "identity_events": int(identity.sum()),
                "identity_unreconciled_events": int((identity & bad).sum()),
                "identity_unreconciled_pct": _percent((identity & bad).sum(), identity.sum()),
            })
    columns = [
        "sample_session", "BurstId", "burst_timestamp_exchange", "burst_price",
        "sample_window_start", "sample_window_end", "timestamp_exchange",
        "timestamp_receive", "sequence", "raw_ordinal", "order_id", "event_type",
        "event_subtype", "side", "price", "price_before", "qty_before",
        "qty_change", "qty_after", "trade_qty", "event_size",
        "queue_ahead_estimate", "queue_estimate_kind", "state_known_before",
        "cycle_origin_add_observed", "price_changed_inferred",
        "size_changed_inferred", "fill_cancel_pair_explicitly_reconciled",
        "fill_cancel_relation", "fill_book_effect_reconciled",
        "fill_book_effect_event",
        "reconciliation_status",
    ]
    return sample[columns], level_rows


def _write_reports(
    quality: pd.DataFrame,
    field_coverage: pd.DataFrame,
    schema: pd.DataFrame,
    sample: pd.DataFrame,
    total: dict[str, Any],
    level_reconciliation: pd.DataFrame,
) -> None:
    q = quality
    action_totals = {name: int(q[f"action_{name}"].sum()) for name in ("A", "C", "M", "F", "T", "R")}
    total_bytes = int(q["file_bytes"].sum())
    first_date, last_date = q["fecha"].min(), q["fecha"].max()
    sample_bad = sample["reconciliation_status"].str.startswith(("LEFT_CENSORED", "INCONSISTENT", "EXPLICIT_FILL_LEFT"))
    sample_identity = sample["event_type"].isin(["M", "C", "F"])
    sample_unreconciled_pct = _percent((sample_bad & sample_identity).sum(), sample_identity.sum())
    tape_exact_weighted = _percent(q["mbo_tape_exact_matches"].sum(), q["mbo_trade_rows"].sum())
    tape_relaxed_weighted = _percent(q["mbo_tape_relaxed_5ms_matches"].sum(), q["mbo_trade_rows"].sum())
    mbp_exact_weighted = _percent(q["mbo_mbp_exact_change_matches"].sum(), q["mbo_known_book_change_groups"].sum())
    mbp_relaxed_weighted = _percent(q["mbo_mbp_relaxed_5ms_change_matches"].sum(), q["mbo_known_book_change_groups"].sum())

    report = [
        "# MBO DATA CAPABILITY AUDIT",
        "",
        "Fecha de auditoría: 2026-07-22. Alcance: lectura directa, sin features nuevas, sin clasificadores y sin outcomes de trading.",
        "",
        "## Veredicto",
        "",
        "**B. SIRVEN PARCIALMENTE.**",
        "",
        "Los DBN sí conservan identidad de orden, A/C/M/F/T, precio, tamaño, exchange-time nanosegundo, orden físico y secuencia. "
        "Permiten estudiar ciclos causales de órdenes cuyo ADD aparece en la ventana y medir fills, modificaciones, cancelaciones puras inferidas, "
        "reposición visible y supervivencia observada. No permiten reconstruir el libro inicial ni la cola completa porque las solicitudes de 10 segundos "
        "no incluyen el snapshot de medianoche.",
        "",
        "## Inventario real",
        "",
        f"- 100 archivos DBN zstd, {total_bytes:,} bytes, {int(q['rows'].sum()):,} registros.",
        f"- Fechas: {first_date} a {last_date}; 2022/2023/2024.",
        f"- Ruta MBO: `{MBO_DIR}`.",
        f"- Manifiesto: `{MANIFEST_PATH}`.",
        f"- Ruta ATAS MBP/tape: `{BOOK_DIR}`.",
        "- Dataset: GLBX.MDP3; schema: MBO; símbolo solicitado: NQ.v.0 continuo.",
        f"- Instrumentos numéricos por sesión: mínimo {int(q['instrument_id_count'].min())}, "
        f"máximo {int(q['instrument_id_count'].max())}; el contrato raw no quedó persistido.",
        "- Profundidad: eventos MBO de todas las órdenes publicadas para el instrumento durante la ventana; "
        "no equivale a libro completo al inicio porque falta el snapshot.",
        "- El DBN quedó con `stype_out=InstrumentId`; el campo `stype_out=raw_symbol` del manifiesto no fue pasado por el descargador.",
        f"- Acciones reales: {action_totals}.",
        f"- ATAS MBP+tape coincidente: {int(q['mbp_file_exists'].sum())}/100 y {int(q['tape_file_exists'].sum())}/100 sesiones.",
        "- Archivos ATAS MBO por orden: 0. Los CSV de ATAS disponibles son MBP agregado y tape.",
        "",
        "### Versiones y lectores comparados",
        "",
        f"- **Fuente con mayor información:** DBN MBO crudo anterior, leído con `databento.DBNStore` por `{Path(__file__).resolve()}`.",
        f"- Descargador: `{BASE_DIR / 'download_databento_mbo_manifest.py'}`; preparador del manifiesto: "
        f"`{BASE_DIR / 'prepare_databento_mbo_request_manifest.py'}`.",
        f"- Exportador ATAS: `{BASE_DIR / 'features' / 'BookRecorder.cs'}`. Generó MBP/tape, pero ningún `mbo_*.csv`.",
        f"- Versión transformada anterior: `{MBO_FEATURE_LEDGER_PATH}`; es un ledger derivado y pierde la secuencia por orden.",
        f"- Ledger MBP/tape: `{MBP_LEDGER_PATH}`; también es derivado y no sustituye el DBN.",
        "",
        "## Ciclo de vida y explicitud",
        "",
        f"- Órdenes únicas por archivo sumadas: {int(q['unique_order_ids'].sum()):,}.",
        f"- Ciclos cuyo primer evento observado es ADD: {int(q['first_action_A_orders'].sum()):,} "
        f"({_percent(q['first_action_A_orders'].sum(), q['unique_order_ids'].sum()):.2f}%).",
        f"- Órdenes censuradas por la izquierda: {int(q['left_censored_orders'].sum()):,} "
        f"({_percent(q['left_censored_orders'].sum(), q['unique_order_ids'].sum()):.2f}%).",
        f"- Grupos de fill cuyo efecto en libro se reconcilia por C agregado o M con estado: "
        f"{total['fill_book_effect_reconciled_groups']:,}/{total['fill_groups']:,} "
        f"({total['fill_book_effect_reconciled_pct']:.2f}%).",
        f"- Grupos de fill con cantidad previa reconstruible: {total['fill_state_known_groups']:,}/{total['fill_groups']:,} "
        f"({total['fill_state_known_pct']:.2f}%).",
        f"- Ejecuciones parciales/completas inferidas con estado conocido: {total['partial_fill_inferred_groups']:,}/"
        f"{total['complete_fill_inferred_groups']:,}.",
        f"- Eventos C ambiguos porque F y C comparten clave pero no cantidad: {total['ambiguous_cancel_fill_rows']:,}.",
        f"- Eventos identidad-dependientes no reconciliables por censura/inconsistencia: "
        f"{total['identity_unreconciled_events']:,}/{total['identity_dependent_events']:,} "
        f"({total['identity_unreconciled_pct']:.2f}%).",
        "",
        "### Qué es explícito",
        "",
        "`A`, `C`, `M`, `F`, `T`, order_id, lado, precio, size, ts_event, ts_recv, sequence y flags. "
        "El `F` identifica la orden reposante ejecutada; el `T` registra el trade agresor. "
        "El `C` es la reducción efectiva del libro y puede representar cancelación pura o la reducción que acompaña un fill.",
        "",
        "### Qué es inferido",
        "",
        "Cancelación pura = C sin F para la misma orden/ts_event/precio; modificación de precio/tamaño = comparación de M con estado previo; "
        "fill parcial/completo = F frente a cantidad previa; refill de la misma orden = aumento de size mediante M; "
        "supervivencia = orden aún presente al cutoff. Cancel-replace con ID nuevo no es enlazable con certeza.",
        "",
        "## Cola",
        "",
        "La prioridad relativa de órdenes nacidas dentro de la ventana puede seguirse por orden físico/sequence. "
        "El `queue_ahead_estimate` entregado es un **límite inferior** que suma solo órdenes observadas. "
        "No es posición exacta: faltan las órdenes que ya estaban vivas al iniciar la descarga y su prioridad.",
        "",
        "## Precedencia temporal y sincronización",
        "",
        f"- Filas MBO fuera de orden por ts_event: {int(q['ts_event_out_of_order_rows'].sum()):,}; "
        f"retrocesos de sequence: {int(q['sequence_decrease_rows'].sum()):,}.",
        f"- Registros adicionales idénticos en todos los campos MBO: {int(q['exact_duplicate_rows'].sum()):,} "
        f"(A {int(q['exact_duplicate_action_A'].sum()):,}, C {int(q['exact_duplicate_action_C'].sum()):,}, "
        f"M {int(q['exact_duplicate_action_M'].sum()):,}, F {int(q['exact_duplicate_action_F'].sum()):,}, "
        f"T {int(q['exact_duplicate_action_T'].sum()):,}). No se deduplican automáticamente: múltiples F/T "
        "idénticos pueden ser ejecuciones unitarias legítimas y reconciliar una reducción agregada.",
        f"- `F_MAYBE_BAD_BOOK`: {int(q['flag_maybe_bad_book_rows'].sum()):,}; "
        f"`F_BAD_TS_RECV`: {int(q['flag_bad_ts_recv_rows'].sum()):,}.",
        f"- Eventos MBO submicrosegundo: {_percent((q['submicrosecond_ts_event_rows_pct'] * q['rows'] / 100).sum(), q['rows'].sum()):.2f}%.",
        f"- Eventos dentro del milisegundo final pero posteriores al timestamp nominal: "
        f"{int(q['post_nominal_cutoff_same_millisecond_rows'].sum()):,} en "
        f"{int(q['post_nominal_cutoff_same_millisecond_rows'].gt(0).sum())}/100 sesiones; "
        "se excluyeron de la reconstrucción causal.",
        f"- Eventos en/después de `end_utc_exclusive`: {int(q['at_or_after_request_end_rows'].sum()):,}.",
        f"- Match MBO T vs ATAS tape: exacto a milisegundo {tape_exact_weighted:.2f}%; dentro de ±5 ms {tape_relaxed_weighted:.2f}%.",
        f"- Match de cambios MBO conocidos vs ATAS MBP: exacto {mbp_exact_weighted:.2f}%; dentro de ±5 ms {mbp_relaxed_weighted:.2f}%.",
        "",
        "MBO usa UTC exchange-time y sequence. ATAS escribe un `DateTime` convertido a NY y truncado a milisegundos, sin persistir Kind, sequence, "
        "receive-time ni export-time. Por ello la precedencia interna MBO es recuperable; la precedencia cruzada MBO↔ATAS solo es aproximada y debe "
        "mantener una banda de empate, nunca resolverse por orden de filas después de redondear. La etiqueta de decisión sólo tiene milisegundos: "
        "los eventos posteriores dentro de ese mismo milisegundo son una zona de empate, no evidencia predecisional.",
        "",
        "## Prueba manual: tres sesiones",
        "",
        f"Sesiones: {', '.join(SAMPLE_DATES)}. Filas publicadas: {len(sample):,}. "
        f"Eventos identidad-dependientes no reconciliables en la muestra: {sample_unreconciled_pct:.2f}%.",
        "",
        "| fecha | lado | precio | eventos | ADD Δ | MODIFY Δ | C Δ | F qty | net MBO | residuo ecuación | net ATAS MBP | no reconciliable |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in level_reconciliation.itertuples(index=False):
        report.append(
            f"| {item.fecha} | {item.side} | {item.price:.2f} | {item.mbo_sample_events} | "
            f"{item.additions_net_qty:.0f} | {item.modifications_net_qty:.0f} | "
            f"{item.cancellations_and_fill_decrements_net_qty:.0f} | {item.resting_fill_qty_explicit:.0f} | "
            f"{item.mbo_known_net_book_change:.0f} | {item.book_equation_residual:.0f} | "
            f"{_fmt(item.atas_mbp_net_change, 0)} | {_fmt(item.identity_unreconciled_pct, 2)}% |"
        )
    report.extend([
        "",
        "### Filas reales anonimizadas",
        "",
        "| sesión | exchange timestamp | sequence | order_id | evento | lado | precio | qty antes | cambio | qty después | trade qty | cola delante |",
        "| --- | --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for _, item in sample.groupby("sample_session", sort=True).head(4).iterrows():
        report.append(
            f"| {item['sample_session']} | {item['timestamp_exchange']} | {int(item['sequence'])} | "
            f"{item['order_id']} | {item['event_subtype']} | {item['side']} | {_fmt(item['price'], 2)} | "
            f"{_fmt(item['qty_before'], 0)} | {_fmt(item['qty_change'], 0)} | {_fmt(item['qty_after'], 0)} | "
            f"{_fmt(item['trade_qty'], 0)} | {_fmt(item['queue_ahead_estimate'], 0)} |"
        )
    report.extend([
        "",
        "La diferencia contra MBP no implica que el MBO sea falso: MBP procede de ATAS/Rithmic, tiene milisegundos y otra ruta de datos; "
        "además el MBO inicia sin snapshot. Sí demuestra que no es defendible fusionar ambas fuentes como si compartieran un reloj y estado idénticos.",
        "",
        "## Conclusiones permitidas",
        "",
        "- Cuántos contratos se ejecutaron por T y qué órdenes reposantes recibieron F.",
        "- Ciclos exactos desde ADD para la fracción no censurada.",
        "- Cancelaciones puras inferidas por exclusión del par F/C.",
        "- Modificaciones de precio/tamaño y reposición visible cuando el estado previo es conocido.",
        "- Supervivencia durante la ventana observada, con censura explícita.",
        "",
        "## Conclusiones prohibidas",
        "",
        "- Posición inicial exacta en cola o volumen exacto delante al inicio.",
        "- Afirmar que un C seguido de A con otro ID es cancel-replace del mismo participante.",
        "- Inferir intención iceberg/spoofing solo por refill visible.",
        "- Considerar MBP/tape y MBO perfectamente sincronizados.",
        "- Extrapolar supervivencia más allá del cutoff o antigüedad previa al inicio.",
        "",
        "## Datos adicionales necesarios",
        "",
        "Para completar la hipótesis hay que volver a solicitar MBO incluyendo 00:00:00 UTC del mismo día hasta el cutoff, de modo que llegue "
        "el snapshot sintético R + A con `F_SNAPSHOT`. Alternativamente, descargar snapshot histórico y todos los incrementales posteriores sin huecos. "
        "Para una unión exacta con estrategia, exportar desde ATAS el timestamp UTC original con 100 ns/ticks o mejor, sequence/feed ID, receive timestamp "
        "y contrato raw; idealmente usar tape/MBP derivados del mismo Databento MBO.",
        "",
        "## Referencias de semántica",
        "",
        f"- {OFFICIAL_MBO_URL}",
        f"- {OFFICIAL_ACTIONS_URL}",
        f"- {OFFICIAL_SNAPSHOT_URL}",
        f"- {OFFICIAL_CME_URL}",
        f"- {OFFICIAL_QUEUE_URL}",
    ])
    REPORT_MD.write_text("\n".join(report) + "\n", encoding="utf-8")

    limits = [
        "# MBO GAPS AND LIMITATIONS",
        "",
        "## Hallazgo decisivo",
        "",
        "Los archivos son MBO crudos, pero la ventana empieza diez segundos antes de t_decision y no cruza 00:00 UTC. "
        "En consecuencia no contiene snapshot inicial: R=0 y F_SNAPSHOT=0 en los 100 archivos.",
        "",
        "## Gaps observados",
        "",
        f"- Intervalos con salto de `sequence > 1`: {int(q['sequence_gap_intervals'].sum()):,}.",
        f"- Unidades saltadas: {int(q['sequence_gap_units'].sum()):,}.",
        "- No se interpretan como paquetes perdidos: sequence es de canal/venue y el archivo está filtrado a NQ.v.0; otros instrumentos ocupan números intermedios.",
        f"- Indicador explícito de gap irrecuperable `F_MAYBE_BAD_BOOK`: {int(q['flag_maybe_bad_book_rows'].sum()):,} filas.",
        f"- Sesiones sin MBP/tape ATAS complementario: {100 - int(q['mbp_file_exists'].sum())}.",
        "",
        "## Censura",
        "",
        f"- Izquierda: {_percent(q['left_censored_orders'].sum(), q['unique_order_ids'].sum()):.2f}% de IDs no comienzan con ADD.",
        "- Derecha: toda orden viva al cutoff solo puede clasificarse como superviviente durante lo observado.",
        "- El campo quantity remaining no existe; se deriva de A/M/C cuando el estado está disponible.",
        "",
        "## Relojes",
        "",
        "- Databento: ts_event/ts_recv UTC nanosegundo, sequence y raw order.",
        "- ATAS MBP/tape: hora NY a milisegundo, sin fecha dentro de fila, sin sequence, sin receive/export timestamp.",
        "- Liquidity Burst/prediction: UTC exportado por estrategia, típicamente precisión de milisegundos.",
        f"- Zona de empate submilisegundo en el cutoff: {int(q['post_nominal_cutoff_same_millisecond_rows'].sum()):,} "
        "eventos; el auditor causal los excluye.",
        "- El BookRecorder fuerza Kind=UTC cuando el DateTime no viene marcado UTC; el Kind original no se guarda, por lo que la corrección solo puede probarse empíricamente.",
        "",
        "## Limitaciones de interpretación",
        "",
        "- C expresa reducción de tamaño, no una causa económica. El motivo fill se infiere por emparejamiento F/C.",
        "- M expresa precio y/o size nuevo. Qué componente cambió requiere estado previo.",
        "- Una nueva A al mismo precio es una orden nueva, pero no prueba que sea replacement/refill del mismo participante.",
        "- Priority no es un campo del DBN descargado; CME/Databento preservan prioridad por orden de publicación, inútil para la cola inicial sin snapshot.",
        "- El símbolo de vencimiento raw no quedó persistido: el descargador omitió `stype_out` aunque el manifiesto lo declaraba.",
        "",
        "## Descarga mínima correctiva",
        "",
        "Para cada fecha que se decida conservar: solicitar GLBX.MDP3/MBO/NQ.v.0 desde 00:00:00 UTC hasta t_decision inclusive, "
        "o una API que entregue el snapshot a t0 seguido por todos los incrementales. Verificar R, F_SNAPSHOT, F_LAST, "
        "instrument_id/contrato raw, F_MAYBE_BAD_BOOK=0 y continuidad del stream antes de estudiar cola.",
    ]
    LIMITS_MD.write_text("\n".join(limits) + "\n", encoding="utf-8")


def main() -> int:
    manifest = pd.read_csv(MANIFEST_PATH)
    metadata_ledger = pd.read_csv(MBP_LEDGER_PATH, low_memory=False).drop_duplicates("BurstId")
    if len(manifest) != 100 or manifest["BurstId"].nunique() != 100:
        raise ValueError("Expected 100 unique manifest rows")
    if metadata_ledger["BurstId"].isin(manifest["BurstId"]).sum() != 100:
        raise ValueError("Burst/entry metadata coverage is not 100/100")

    quality_rows: list[dict[str, Any]] = []
    sample_frames: list[pd.DataFrame] = []
    level_rows: list[dict[str, Any]] = []
    aggregate_nulls: Counter[str] = Counter()
    total_rows = 0
    total_summary: Counter[str] = Counter()

    for position, row in manifest.iterrows():
        path = MBO_DIR / f"{row['request_id']}.mbo.dbn.zst"
        if not path.exists():
            raise FileNotFoundError(path)
        frame, metadata = _read_dbn(path)
        aggregate_nulls.update({column: int(frame[column].isna().sum()) for column in frame.columns})
        total_rows += len(frame)
        marked = _mark_fill_cancel_pairs(frame)
        causal_frame = frame.loc[
            frame["ts_event"].le(pd.Timestamp(row["causal_cutoff_utc_inclusive"]))
        ].copy()
        recon = reconstruct_orders(causal_frame)
        quality = _sequence_and_clock_quality(marked, row, metadata)
        cross, mbp_changes, _ = _cross_source_quality(frame, recon.book_changes, row)
        quality.update(recon.summary)
        quality.update(cross)
        metadata_row = metadata_ledger.loc[metadata_ledger["BurstId"].eq(row["BurstId"])].iloc[0]
        cutoff_delta_ms = (
            pd.Timestamp(row["causal_cutoff_utc_inclusive"])
            - pd.Timestamp(metadata_row["prediction_timestamp"])
        ).total_seconds() * 1000
        burst_time = pd.Timestamp(metadata_row["burst_timestamp_utc"])
        publish_time = pd.Timestamp(metadata_row["detector_publish_timestamp_utc"])
        cutoff = pd.Timestamp(row["causal_cutoff_utc_inclusive"])
        quality.update({
            "burst_metadata_found": 1,
            "manifest_vs_strategy_cutoff_delta_ms": cutoff_delta_ms,
            "burst_before_publish_and_cutoff": int(burst_time <= publish_time <= cutoff),
            "burst_to_cutoff_ms": (cutoff - burst_time).total_seconds() * 1000,
        })
        quality_rows.append(quality)
        total_summary.update({
            key: int(value)
            for key, value in recon.summary.items()
            if isinstance(value, (int, np.integer))
        })
        if str(row["fecha"]) in SAMPLE_DATES:
            sample, levels = _manual_sample(row, recon, metadata_row, mbp_changes)
            sample_frames.append(sample)
            level_rows.extend(levels)
        print(f"[{position + 1:03d}/100] {row['fecha']} rows={len(frame)}", flush=True)

    quality_frame = pd.DataFrame(quality_rows).sort_values("fecha").reset_index(drop=True)
    sample_frame = pd.concat(sample_frames, ignore_index=True).sort_values(
        ["sample_session", "timestamp_exchange", "sequence", "raw_ordinal"], kind="stable"
    )
    level_frame = pd.DataFrame(level_rows)
    total = dict(total_summary)
    total.update({
        "first_action_A_share_pct": _percent(
            quality_frame["first_action_A_orders"].sum(), quality_frame["unique_order_ids"].sum()
        ),
        "identity_unreconciled_pct": _percent(
            quality_frame["identity_unreconciled_events"].sum(),
            quality_frame["identity_dependent_events"].sum(),
        ),
        "identity_dependent_events": int(quality_frame["identity_dependent_events"].sum()),
        "identity_unreconciled_events": int(quality_frame["identity_unreconciled_events"].sum()),
        "fill_rows": int(quality_frame["fill_rows"].sum()),
        "fill_groups": int(quality_frame["fill_groups"].sum()),
        "fill_state_known_groups": int(quality_frame["fill_state_known_groups"].sum()),
        "fill_state_known_pct": _percent(
            quality_frame["fill_state_known_groups"].sum(), quality_frame["fill_groups"].sum()
        ),
        "fill_book_effect_reconciled_groups": int(
            quality_frame["fill_book_effect_reconciled_groups"].sum()
        ),
        "fill_book_effect_reconciled_pct": _percent(
            quality_frame["fill_book_effect_reconciled_groups"].sum(),
            quality_frame["fill_groups"].sum(),
        ),
        "modify_state_known_pct": _percent(
            quality_frame["modify_state_known_rows"].sum(), quality_frame["modify_rows"].sum()
        ),
        "sessions_with_mbp_tape_pct": _percent(
            (quality_frame["mbp_file_exists"].eq(1) & quality_frame["tape_file_exists"].eq(1)).sum(),
            len(quality_frame),
        ),
        "minimum_positive_ts_event_step_ns": int(
            quality_frame["minimum_positive_ts_event_step_ns"].min()
        ),
    })
    schema = _schema_inventory(
        aggregate_nulls,
        total_rows,
        int(quality_frame["mbp_file_exists"].sum()),
        int(quality_frame["tape_file_exists"].sum()),
    )
    fields = _field_coverage(total)

    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    schema.to_csv(SCHEMA_CSV, index=False)
    fields.to_csv(FIELD_CSV, index=False)
    quality_frame.to_csv(QUALITY_CSV, index=False)
    sample_frame.to_csv(SAMPLE_CSV, index=False)
    _write_reports(quality_frame, fields, schema, sample_frame, total, level_frame)
    manifest_out = {
        "verdict": "B_SIRVEN_PARCIALMENTE",
        "files": 100,
        "rows": int(quality_frame["rows"].sum()),
        "outputs": [str(REPORT_MD), str(SCHEMA_CSV), str(FIELD_CSV), str(QUALITY_CSV), str(SAMPLE_CSV), str(LIMITS_MD)],
    }
    print(json.dumps(manifest_out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
