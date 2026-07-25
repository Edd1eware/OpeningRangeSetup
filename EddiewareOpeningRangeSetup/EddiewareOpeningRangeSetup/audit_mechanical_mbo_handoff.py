"""Audit and cache the causal MBO handoff at each decision timestamp."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
import numpy as np
import pandas as pd


CHUNK_RECORDS = 500_000
F_LAST = 128
F_MAYBE_BAD_BOOK = 4
F_SNAPSHOT = 32
OVERLAP_MS = 100
LOGICAL_COLUMNS = [
    "ts_recv",
    "ts_event",
    "sequence",
    "action",
    "side",
    "price",
    "size",
    "order_id",
    "flags",
    "instrument_id",
]


def _normalize(frame: pd.DataFrame, ordinal_start: int) -> pd.DataFrame:
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    missing = set(LOGICAL_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"MBO chunk missing {sorted(missing)}")
    rows = frame.copy()
    rows["record_ordinal"] = np.arange(
        ordinal_start, ordinal_start + len(rows), dtype=np.int64
    )
    for field in ("ts_recv", "ts_event"):
        rows[field] = pd.to_datetime(
            rows[field], utc=True, errors="raise", format="mixed"
        )
    for field in ("sequence", "order_id", "flags", "instrument_id"):
        rows[field] = pd.to_numeric(rows[field], errors="raise")
    rows["price"] = pd.to_numeric(rows["price"], errors="coerce")
    rows["size"] = pd.to_numeric(rows["size"], errors="raise")
    rows["action"] = rows["action"].astype(str)
    rows["side"] = rows["side"].astype(str)
    return rows


def apply_packet(
    packet: list[tuple],
    state: dict[int, tuple[str, float, float]],
) -> dict[str, int]:
    quality = {"unknown_modify": 0, "unknown_cancel": 0}
    for item in packet:
        action = str(item.action)
        order_id = int(item.order_id)
        side = str(item.side)
        price = float(item.price) if pd.notna(item.price) else math.nan
        size = float(item.size)
        if action == "R":
            state.clear()
        elif action == "A":
            state[order_id] = (side, price, size)
        elif action == "M":
            if order_id not in state:
                quality["unknown_modify"] += 1
            state[order_id] = (side, price, size)
        elif action == "C":
            old = state.get(order_id)
            if old is None:
                quality["unknown_cancel"] += 1
                continue
            removed = min(size, old[2])
            remaining = old[2] - removed
            if remaining <= 0:
                state.pop(order_id, None)
            else:
                state[order_id] = (old[0], old[1], remaining)
        # F and T are informational here.  The paired C record mutates state.
    return quality


def _logical_sha(frame: pd.DataFrame) -> str:
    if frame.empty:
        return hashlib.sha256(b"").hexdigest()
    payload = frame.loc[:, LOGICAL_COLUMNS].to_csv(
        index=False, lineterminator="\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _best_from_state(
    state: dict[int, tuple[str, float, float]], side: str
) -> float:
    prices = [
        value[1]
        for value in state.values()
        if value[0] == side and value[2] > 0 and math.isfinite(value[1])
    ]
    if not prices:
        return math.nan
    return max(prices) if side == "B" else min(prices)


def audit_one(task: dict[str, str]) -> dict[str, Any]:
    decision = pd.to_datetime(task["decision_utc"], utc=True)
    strategy_decision = pd.to_datetime(
        task["strategy_decision_utc"], utc=True
    )
    overlap_start = pd.to_datetime(
        task["outcome_request_start_utc"], utc=True
    )
    pre_path = Path(task["pre_path"])
    outcome_path = Path(task["outcome_path"])
    cache_path = Path(task["cache_path"])
    rows = _normalize(db.DBNStore.from_file(pre_path).to_df(), 0)
    rows = rows.loc[rows["ts_recv"].lt(decision)].copy()
    ordinal_start = len(rows)
    if rows.empty:
        raise ValueError(f"{task['BurstId']} empty pre-decision stream")
    is_last = (rows["flags"].astype("uint16") & F_LAST) != 0
    completed_packets = int(is_last.sum())
    last_completed_ordinal = int(
        rows.loc[is_last, "record_ordinal"].max()
    )
    tail_incomplete_records = int(
        rows["record_ordinal"].gt(last_completed_ordinal).sum()
    )
    rows = rows.loc[
        rows["record_ordinal"].le(last_completed_ordinal)
    ].copy()
    maybe_bad = int(
        ((rows["flags"].astype("uint16") & F_MAYBE_BAD_BOOK) != 0).sum()
    )
    incremental = rows.loc[
        (rows["flags"].astype("uint16") & F_SNAPSHOT) == 0
    ]
    sequence = incremental["sequence"].astype("int64").to_numpy()
    sequence_regressions = int((np.diff(sequence) < 0).sum())
    last_complete_ts_recv = rows.iloc[-1]["ts_recv"]
    last_complete_ts_event = rows.iloc[-1]["ts_event"]

    reset_rows = rows.loc[rows["action"].eq("R")]
    if not reset_rows.empty:
        last_reset = int(reset_rows["record_ordinal"].max())
        lifecycle = rows.loc[rows["record_ordinal"].gt(last_reset)].copy()
    else:
        lifecycle = rows.copy()
    setters = lifecycle.loc[
        lifecycle["action"].isin(["A", "M"]),
        ["record_ordinal", "order_id", "side", "price", "size", "action"],
    ].copy()
    setters = setters.sort_values("record_ordinal", kind="mergesort")
    first_setters = setters.groupby("order_id", sort=False).head(1)
    unknown_modify = int(first_setters["action"].eq("M").sum())
    last_setters = (
        setters.groupby("order_id", sort=False)
        .tail(1)
        .rename(
            columns={
                "record_ordinal": "setter_ordinal",
                "size": "setter_size",
            }
        )
    )
    cancels = lifecycle.loc[
        lifecycle["action"].eq("C"),
        ["record_ordinal", "order_id", "size"],
    ].rename(
        columns={
            "record_ordinal": "cancel_ordinal",
            "size": "cancel_size",
        }
    )
    cancel_join = cancels.merge(
        last_setters[["order_id", "setter_ordinal"]],
        on="order_id",
        how="left",
    )
    unknown_cancel = int(cancel_join["setter_ordinal"].isna().sum())
    cancel_after = cancel_join.loc[
        cancel_join["cancel_ordinal"].gt(cancel_join["setter_ordinal"])
    ]
    cancelled = cancel_after.groupby("order_id")["cancel_size"].sum()
    cache = last_setters[
        ["order_id", "side", "price", "setter_size"]
    ].copy()
    cache["size"] = (
        cache["setter_size"]
        - cache["order_id"].map(cancelled).fillna(0.0)
    ).clip(lower=0.0)
    cache = cache.loc[
        cache["size"].gt(0)
        & cache["side"].isin(["A", "B"])
        & cache["price"].notna(),
        ["order_id", "side", "price", "size"],
    ].copy()
    state = {
        int(item.order_id): (
            str(item.side),
            float(item.price),
            float(item.size),
        )
        for item in cache.itertuples(index=False)
    }
    if maybe_bad or sequence_regressions:
        raise ValueError(
            f"{task['BurstId']} pre integrity: bad={maybe_bad} "
            f"regressions={sequence_regressions} tail={tail_incomplete_records}"
        )

    pre_overlap = rows.loc[
        rows["ts_recv"].ge(overlap_start)
        & rows["ts_recv"].lt(decision),
        LOGICAL_COLUMNS,
    ].reset_index(drop=True)
    outcome = _normalize(
        db.DBNStore.from_file(outcome_path).to_df(), 0
    )
    outcome_overlap = outcome.loc[
        outcome["ts_recv"].ge(overlap_start)
        & outcome["ts_recv"].lt(decision),
        LOGICAL_COLUMNS,
    ].reset_index(drop=True)
    pre_overlap = pre_overlap.reset_index(drop=True)
    if len(outcome_overlap) < len(pre_overlap):
        raise ValueError(
            f"{task['BurstId']} outcome overlap shorter than confirmed pre "
            f"stream: pre={len(pre_overlap)} outcome={len(outcome_overlap)}"
        )
    outcome_confirmed_prefix = outcome_overlap.iloc[
        : len(pre_overlap)
    ].reset_index(drop=True)
    overlap_prefix_exact = (
        _logical_sha(pre_overlap) == _logical_sha(outcome_confirmed_prefix)
    )
    cross_boundary_tail = outcome_overlap.iloc[len(pre_overlap) :].copy()
    cross_boundary_tail_has_f_last = bool(
        (
            cross_boundary_tail["flags"].astype("uint16") & F_LAST
        ).ne(0).any()
    )
    if not overlap_prefix_exact or cross_boundary_tail_has_f_last:
        raise ValueError(
            f"{task['BurstId']} overlap mismatch: "
            f"pre={len(pre_overlap)} outcome={len(outcome_overlap)} "
            f"prefix={overlap_prefix_exact} "
            f"tail_F_LAST={cross_boundary_tail_has_f_last}"
        )
    overlap_exact = len(pre_overlap) == len(outcome_overlap)
    late_predecision_exchange = outcome.loc[
        outcome["ts_recv"].ge(decision)
        & outcome["ts_event"].lt(decision)
    ]
    post_receive = outcome.loc[outcome["ts_recv"].ge(decision)]
    if post_receive.empty:
        raise ValueError(f"{task['BurstId']} no post-decision receive events")

    cache = cache.sort_values(
        ["side", "price", "order_id"], kind="mergesort"
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache.to_parquet(cache_path, index=False)
    return {
        "fecha": task["fecha"],
        "BurstId": task["BurstId"],
        "burst_side": task["burst_side"],
        "decision_utc": decision.isoformat(),
        "strict_feature_cutoff_utc_exclusive": decision.isoformat(),
        "strategy_decision_utc": strategy_decision.isoformat(),
        "cutoff_to_strategy_decision_ms": float(
            (strategy_decision - decision).total_seconds() * 1000.0
        ),
        "resolved_raw_symbol": task["symbols"],
        "pre_path": str(pre_path),
        "outcome_path": str(outcome_path),
        "state_cache_path": str(cache_path),
        "pre_records_scanned": ordinal_start,
        "completed_packets": completed_packets,
        "active_orders_at_decision": int(len(cache)),
        "active_bid_orders": int(cache["side"].eq("B").sum()),
        "active_ask_orders": int(cache["side"].eq("A").sum()),
        "best_bid": _best_from_state(state, "B"),
        "best_ask": _best_from_state(state, "A"),
        "pre_overlap_records": int(len(pre_overlap)),
        "outcome_overlap_records": int(len(outcome_overlap)),
        "overlap_logical_sha256": _logical_sha(pre_overlap),
        "overlap_exact": overlap_exact,
        "overlap_prefix_exact": overlap_prefix_exact,
        "cross_boundary_uncommitted_records": int(
            len(cross_boundary_tail)
        ),
        "cross_boundary_tail_has_f_last": (
            cross_boundary_tail_has_f_last
        ),
        "uncommitted_tail_count_match": (
            int(len(cross_boundary_tail)) == tail_incomplete_records
        ),
        "late_received_predecision_exchange_records": int(
            len(late_predecision_exchange)
        ),
        "post_decision_receive_records": int(len(post_receive)),
        "last_pre_complete_ts_recv": (
            last_complete_ts_recv.isoformat()
            if last_complete_ts_recv is not None
            else None
        ),
        "last_pre_complete_ts_event": (
            last_complete_ts_event.isoformat()
            if last_complete_ts_event is not None
            else None
        ),
        "first_post_ts_recv": post_receive["ts_recv"].min().isoformat(),
        "first_post_ts_event": post_receive["ts_event"].min().isoformat(),
        "unknown_modify_during_full_reconstruction": unknown_modify,
        "unknown_cancel_during_full_reconstruction": unknown_cancel,
        "maybe_bad_book_records": maybe_bad,
        "sequence_regressions": sequence_regressions,
        "tail_incomplete_records": tail_incomplete_records,
        "information_status": "CAUSAL_HANDOFF_INFRASTRUCTURE",
    }


def main() -> int:
    project = Path(__file__).resolve().parent
    base = project / "contexto_codex_claude" / "mechanical_book_v1"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pre-audit",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "MBO_SNAPSHOT_DISCOVERY_100_AUDIT_20260723.csv",
    )
    parser.add_argument(
        "--pre-manifest",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "DATABENTO_MBO_SNAPSHOT_DISCOVERY_100_RESOLVED_20260723.csv",
    )
    parser.add_argument(
        "--outcome-manifest",
        type=Path,
        default=project
        / "contexto_codex_claude"
        / "joint_ab_v4"
        / "AB_V4_OUTCOME_98_QUOTE_MANIFEST.csv",
    )
    parser.add_argument(
        "--outcome-dir",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\databento_mbo\joint_ab_v4_outcome98_20260724"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base / "MECHANICAL_BOOK_HANDOFF_AUDIT_98.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=base / "MECHANICAL_BOOK_HANDOFF_SUMMARY.json",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=base / "state_cache",
    )
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    pre = pd.read_csv(args.pre_audit)
    pre_manifest = pd.read_csv(args.pre_manifest)
    outcome = pd.read_csv(args.outcome_manifest)
    outcome = outcome.loc[outcome["schema"].eq("mbo")].copy()
    rows = outcome.merge(
        pre[["BurstId", "file_path"]],
        on="BurstId",
        how="inner",
        validate="one_to_one",
    ).merge(
        pre_manifest[
            [
                "BurstId",
                "strategy_decision_timestamp_utc",
                "strict_feature_cutoff_utc_exclusive",
            ]
        ],
        on="BurstId",
        how="inner",
        validate="one_to_one",
    )
    rows = rows.loc[
        ~rows["fecha"].astype(str).isin({"2022-06-13", "2023-06-13"})
    ].sort_values(["fecha", "BurstId"]).reset_index(drop=True)
    if len(rows) != 98:
        raise ValueError(f"Expected 98 handoff rows, got {len(rows)}")
    tasks = []
    for row in rows.itertuples(index=False):
        padded_id = f"{row.request_id}_PAD100MS"
        tasks.append(
            {
                "fecha": str(row.fecha),
                "BurstId": str(row.BurstId),
                "burst_side": str(row.burst_side),
                "decision_utc": str(
                    row.strict_feature_cutoff_utc_exclusive
                ),
                "strategy_decision_utc": str(
                    row.strategy_decision_timestamp_utc
                ),
                "outcome_request_start_utc": str(row.start_utc),
                "symbols": str(row.symbols),
                "pre_path": str(row.file_path),
                "outcome_path": str(
                    args.outcome_dir / f"{padded_id}.mbo.dbn.zst"
                ),
                "cache_path": str(
                    args.cache_dir / f"{row.BurstId}.state.parquet"
                ),
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed: list[dict[str, Any]] = []
    if args.output.exists():
        prior = pd.read_csv(args.output)
        if "overlap_prefix_exact" not in prior.columns:
            prior["overlap_prefix_exact"] = prior["overlap_exact"]
        if "cross_boundary_uncommitted_records" not in prior.columns:
            prior["cross_boundary_uncommitted_records"] = 0
        if "cross_boundary_tail_has_f_last" not in prior.columns:
            prior["cross_boundary_tail_has_f_last"] = False
        if "uncommitted_tail_count_match" not in prior.columns:
            prior["uncommitted_tail_count_match"] = True
        completed = prior.to_dict(orient="records")
    completed_ids = {str(item["BurstId"]) for item in completed}
    pending_tasks = [
        task for task in tasks if task["BurstId"] not in completed_ids
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(audit_one, task): task for task in pending_tasks
        }
        for future in as_completed(futures):
            result = future.result()
            completed.append(result)
            completed.sort(key=lambda item: (item["fecha"], item["BurstId"]))
            pd.DataFrame(completed).to_csv(args.output, index=False)
            print(
                f"[HANDOFF {len(completed)}/98] {result['fecha']} "
                f"overlap={result['pre_overlap_records']} prefix-exact "
                f"cross={result['cross_boundary_uncommitted_records']} "
                f"orders={result['active_orders_at_decision']}",
                flush=True,
            )
    frame = pd.DataFrame(completed).sort_values(["fecha", "BurstId"])
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sessions": int(len(frame)),
        "overlap_exact_sessions": int(frame["overlap_exact"].sum()),
        "overlap_prefix_exact_sessions": int(
            frame["overlap_prefix_exact"].sum()
        ),
        "sessions_with_cross_boundary_uncommitted_records": int(
            frame["cross_boundary_uncommitted_records"].gt(0).sum()
        ),
        "total_cross_boundary_uncommitted_records": int(
            frame["cross_boundary_uncommitted_records"].sum()
        ),
        "total_overlap_records": int(frame["pre_overlap_records"].sum()),
        "sessions_with_late_received_predecision_exchange_records": int(
            frame["late_received_predecision_exchange_records"].gt(0).sum()
        ),
        "total_late_received_predecision_exchange_records": int(
            frame["late_received_predecision_exchange_records"].sum()
        ),
        "total_active_orders_cached": int(
            frame["active_orders_at_decision"].sum()
        ),
        "unknown_modify_during_reconstruction": int(
            frame["unknown_modify_during_full_reconstruction"].sum()
        ),
        "unknown_cancel_during_reconstruction": int(
            frame["unknown_cancel_during_full_reconstruction"].sum()
        ),
        "integrity_pass": bool(
            len(frame) == 98
            and frame["overlap_prefix_exact"].all()
            and not frame[
                "cross_boundary_tail_has_f_last"
            ].astype(bool).any()
            and frame["uncommitted_tail_count_match"].astype(bool).all()
            and frame["maybe_bad_book_records"].eq(0).all()
            and frame["sequence_regressions"].eq(0).all()
        ),
        "output": str(args.output),
        "cache_dir": str(args.cache_dir),
    }
    args.summary.write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["integrity_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
