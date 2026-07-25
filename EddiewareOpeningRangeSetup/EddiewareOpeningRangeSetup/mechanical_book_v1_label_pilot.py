"""Apply the frozen Mechanical Book Outcome V1 instrument once."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
import numpy as np
import pandas as pd


DESIGN_HASH = "9c804cab08fc3e4c457909906254feebe8a3c1bd169aa5b503436bf03a046541"
F_LAST = 128
F_MAYBE_BAD_BOOK = 4
LABEL_A = "A_ABSORCION_LIMPIA"
LABEL_B = "B_BREAKOUT_LIMPIO"
LABEL_C = "C_VARIABLE"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    result = frame.copy()
    for field in ("ts_recv", "ts_event"):
        result[field] = pd.to_datetime(
            result[field], utc=True, errors="raise", format="mixed"
        )
    for field in ("sequence", "order_id", "flags", "instrument_id"):
        result[field] = pd.to_numeric(result[field], errors="raise")
    result["price"] = pd.to_numeric(result["price"], errors="coerce")
    result["size"] = pd.to_numeric(result["size"], errors="raise")
    result["action"] = result["action"].astype(str)
    result["side"] = result["side"].astype(str)
    result["record_ordinal"] = np.arange(len(result), dtype=np.int64)
    return result


def _update_level(
    levels: dict[tuple[str, float], float],
    side: str,
    price: float,
    delta: float,
) -> None:
    key = (side, price)
    updated = levels.get(key, 0.0) + delta
    if updated <= 1e-9:
        levels.pop(key, None)
    else:
        levels[key] = updated


def _best(
    levels: dict[tuple[str, float], float], side: str
) -> float:
    prices = [
        price
        for (level_side, price), size in levels.items()
        if level_side == side and size > 0 and math.isfinite(price)
    ]
    if not prices:
        return math.nan
    return min(prices) if side == "A" else max(prices)


def _is_ceded(
    levels: dict[tuple[str, float], float],
    attacked_side: str,
    l0: float,
) -> bool:
    best = _best(levels, attacked_side)
    if not math.isfinite(best):
        return True
    return best > l0 if attacked_side == "A" else best < l0


def classify_metrics(metrics: dict[str, float | bool], h: float) -> str:
    q0 = float(metrics["Q0"])
    fill = float(metrics["F_dep"])
    pure_cancel = float(metrics["C_dep"])
    fill_share = fill / (fill + pure_cancel) if fill + pure_cancel > 0 else 0.0
    is_a = (
        fill >= h * q0
        and bool(metrics["never_ceded"])
        and float(metrics["Q_end"]) > 0
    )
    is_b = (
        bool(metrics["queue_zero"])
        and fill_share >= h
        and bool(metrics["ceded_terminal"])
    )
    if is_a and not is_b:
        return LABEL_A
    if is_b and not is_a:
        return LABEL_B
    return LABEL_C


def apply_outcome(
    state_frame: pd.DataFrame,
    outcome: pd.DataFrame,
    confirmed_prefix_records: int,
    cutoff: pd.Timestamp,
    burst_side: str,
) -> dict[str, Any]:
    state = {
        int(item.order_id): (
            str(item.side),
            float(item.price),
            float(item.size),
        )
        for item in state_frame.itertuples(index=False)
    }
    levels: dict[tuple[str, float], float] = defaultdict(float)
    for side, price, size in state.values():
        _update_level(levels, side, price, size)
    attacked_side = "A" if burst_side == "BUY" else "B"
    l0 = _best(levels, attacked_side)
    if not math.isfinite(l0):
        return {"eligible": False, "exclusion_reason": "Q0_NO_L0"}
    q0 = float(levels.get((attacked_side, l0), 0.0))
    if q0 <= 0:
        return {"eligible": False, "exclusion_reason": "Q0_ZERO"}

    initial_orders = {
        order_id: size
        for order_id, (side, price, size) in state.items()
        if side == attacked_side and price == l0 and size > 0
    }
    refill_tokens: dict[int, float] = defaultdict(float)
    window_end = cutoff + pd.Timedelta(seconds=5)
    stream = outcome.iloc[int(confirmed_prefix_records) :].copy()
    packet: list[Any] = []
    f_dep = 0.0
    c_dep = 0.0
    add_qty = 0.0
    modify_add_qty = 0.0
    modify_remove_qty = 0.0
    queue_zero = False
    never_ceded = True
    unknown_state_rows = 0
    clear_rows = 0
    committed_packets = 0
    excluded_terminal_packet_records = 0
    fill_without_c_qty = 0.0
    last_time = cutoff
    zero_since: pd.Timestamp | None = None
    zero_duration_s = 0.0
    longest_zero_s = 0.0

    def reduce_refill_token(order_id: int, quantity: float) -> None:
        refill_tokens[order_id] = max(
            0.0, refill_tokens.get(order_id, 0.0) - max(0.0, quantity)
        )

    for item in stream.itertuples(index=False):
        packet.append(item)
        if not bool(int(item.flags) & F_LAST):
            continue
        close_recv = max(value.ts_recv for value in packet)
        if close_recv < cutoff:
            raise ValueError("Confirmed prefix did not end at F_LAST boundary")
        if close_recv >= window_end:
            excluded_terminal_packet_records += len(packet)
            packet = []
            break

        if zero_since is not None:
            elapsed = max(0.0, (close_recv - last_time).total_seconds())
            zero_duration_s += elapsed
            longest_zero_s = max(
                longest_zero_s,
                (close_recv - zero_since).total_seconds(),
            )
        last_time = close_recv
        fills_by_key: dict[tuple[int, float], float] = defaultdict(float)
        for value in packet:
            if (
                str(value.action) == "F"
                and str(value.side) == attacked_side
                and float(value.price) == l0
            ):
                quantity = float(value.size)
                f_dep += quantity
                fills_by_key[(int(value.order_id), float(value.price))] += (
                    quantity
                )

        for value in packet:
            action = str(value.action)
            order_id = int(value.order_id)
            side = str(value.side)
            price = float(value.price) if pd.notna(value.price) else math.nan
            size = float(value.size)
            if action in {"F", "T"}:
                continue
            if action == "R":
                clear_rows += 1
                state.clear()
                levels.clear()
                refill_tokens.clear()
                continue
            if action == "A":
                old = state.get(order_id)
                if old is not None:
                    _update_level(levels, old[0], old[1], -old[2])
                    if old[0] == attacked_side and old[1] == l0:
                        reduce_refill_token(order_id, old[2])
                state[order_id] = (side, price, size)
                _update_level(levels, side, price, size)
                if side == attacked_side and price == l0:
                    add_qty += size
                    refill_tokens[order_id] += size
                continue
            if action == "M":
                old = state.get(order_id)
                if old is None:
                    unknown_state_rows += 1
                    state[order_id] = (side, price, size)
                    _update_level(levels, side, price, size)
                    if side == attacked_side and price == l0:
                        modify_add_qty += size
                        refill_tokens[order_id] += size
                    continue
                old_side, old_price, old_size = old
                _update_level(levels, old_side, old_price, -old_size)
                if old_side == attacked_side and old_price == l0:
                    removed = (
                        old_size - size
                        if side == old_side and price == old_price
                        else old_size
                    )
                    if removed > 0:
                        modify_remove_qty += removed
                        reduce_refill_token(order_id, removed)
                if side == attacked_side and price == l0:
                    added = (
                        max(0.0, size - old_size)
                        if old_side == side and old_price == price
                        else size
                    )
                    if added > 0:
                        modify_add_qty += added
                        refill_tokens[order_id] += added
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
                if old_side == attacked_side and old_price == l0:
                    key = (order_id, old_price)
                    paired = min(
                        removed, fills_by_key.get(key, 0.0)
                    )
                    fills_by_key[key] = max(
                        0.0, fills_by_key.get(key, 0.0) - paired
                    )
                    c_dep += max(0.0, removed - paired)
                    reduce_refill_token(order_id, removed)
                _update_level(levels, old_side, old_price, -removed)
                remaining = old_size - removed
                if remaining <= 0:
                    state.pop(order_id, None)
                else:
                    state[order_id] = (
                        old_side,
                        old_price,
                        remaining,
                    )
        fill_without_c_qty += sum(fills_by_key.values())
        q_now = float(levels.get((attacked_side, l0), 0.0))
        is_zero = q_now <= 1e-9
        queue_zero = queue_zero or is_zero
        ceded = _is_ceded(levels, attacked_side, l0)
        never_ceded = never_ceded and not ceded
        if is_zero and zero_since is None:
            zero_since = close_recv
        elif not is_zero and zero_since is not None:
            longest_zero_s = max(
                longest_zero_s,
                (close_recv - zero_since).total_seconds(),
            )
            zero_since = None
        committed_packets += 1
        packet = []

    if zero_since is not None:
        zero_duration_s += max(0.0, (window_end - last_time).total_seconds())
        longest_zero_s = max(
            longest_zero_s,
            (window_end - zero_since).total_seconds(),
        )
    q_end = float(levels.get((attacked_side, l0), 0.0))
    initial_survival_qty = sum(
        max(0.0, state.get(order_id, ("", math.nan, 0.0))[2])
        if state.get(order_id, ("", math.nan, 0.0))[0] == attacked_side
        and state.get(order_id, ("", math.nan, 0.0))[1] == l0
        else 0.0
        for order_id in initial_orders
    )
    durable_refill_qty = sum(
        min(
            quantity,
            state.get(order_id, ("", math.nan, 0.0))[2]
            if state.get(order_id, ("", math.nan, 0.0))[0] == attacked_side
            and state.get(order_id, ("", math.nan, 0.0))[1] == l0
            else 0.0,
        )
        for order_id, quantity in refill_tokens.items()
    )
    ceded_terminal = _is_ceded(levels, attacked_side, l0)
    fill_share = f_dep / (f_dep + c_dep) if f_dep + c_dep > 0 else 0.0
    metrics: dict[str, Any] = {
        "eligible": True,
        "exclusion_reason": "",
        "attacked_side": attacked_side,
        "L0": l0,
        "Q0": q0,
        "initial_order_count": len(initial_orders),
        "F_dep": f_dep,
        "C_dep": c_dep,
        "fill_initial_depth_ratio": f_dep / q0,
        "fill_depletion_share": fill_share,
        "ADD_qty": add_qty,
        "MODIFY_add_qty": modify_add_qty,
        "MODIFY_remove_qty": modify_remove_qty,
        "Q_end": q_end,
        "terminal_depth_ratio": q_end / q0,
        "initial_queue_survival_qty": initial_survival_qty,
        "initial_queue_survival_ratio": initial_survival_qty / q0,
        "durable_refill_qty": durable_refill_qty,
        "durable_refill_initial_depth_ratio": durable_refill_qty / q0,
        "queue_zero": queue_zero,
        "never_ceded": never_ceded,
        "ceded_terminal": ceded_terminal,
        "zero_duration_s": zero_duration_s,
        "longest_zero_s": longest_zero_s,
        "committed_packets": committed_packets,
        "unknown_state_rows": unknown_state_rows,
        "clear_rows": clear_rows,
        "fill_without_c_qty": fill_without_c_qty,
        "excluded_terminal_packet_records": (
            excluded_terminal_packet_records + len(packet)
        ),
    }
    metrics["base_label"] = classify_metrics(metrics, 0.5)
    metrics["low_425_label"] = classify_metrics(metrics, 0.425)
    metrics["high_575_label"] = classify_metrics(metrics, 0.575)
    return metrics


def _jaccard(
    frame: pd.DataFrame, label: str, candidate_column: str
) -> float:
    base = set(frame.loc[frame["base_label"].eq(label), "BurstId"])
    candidate = set(
        frame.loc[frame[candidate_column].eq(label), "BurstId"]
    )
    union = base | candidate
    return len(base & candidate) / len(union) if union else 1.0


def summarize(frame: pd.DataFrame) -> dict[str, Any]:
    eligible = frame.loc[frame["eligible"]].copy()
    counts = eligible["base_label"].value_counts().to_dict()
    count_a = int(counts.get(LABEL_A, 0))
    count_b = int(counts.get(LABEL_B, 0))
    count_c = int(counts.get(LABEL_C, 0))
    minimum = int(math.ceil(0.15 * len(eligible)))
    clean = count_a + count_b
    jaccards = {
        "A_low_425": _jaccard(eligible, LABEL_A, "low_425_label"),
        "A_high_575": _jaccard(eligible, LABEL_A, "high_575_label"),
        "B_low_425": _jaccard(eligible, LABEL_B, "low_425_label"),
        "B_high_575": _jaccard(eligible, LABEL_B, "high_575_label"),
    }
    by_year = (
        eligible.groupby(["year", "base_label"]).size().unstack(fill_value=0)
    )
    by_side = (
        eligible.groupby(["burst_side", "base_label"])
        .size()
        .unstack(fill_value=0)
    )
    gates = {
        "handoff_integrity_98": len(frame) == 98,
        "all_eligible": len(eligible) == 98,
        "state_reconciliation_zero_unknown": bool(
            eligible["unknown_state_rows"].eq(0).all()
        ),
        "zero_clear_rows": bool(eligible["clear_rows"].eq(0).all()),
        "fills_reconciled_with_C": bool(
            eligible["fill_without_c_qty"].abs().le(1e-9).all()
        ),
        "A_at_least_15pct": count_a >= minimum,
        "B_at_least_15pct": count_b >= minimum,
        "no_clean_class_over_70pct": bool(
            clean > 0 and max(count_a, count_b) / clean <= 0.70
        ),
        "A_and_B_each_year": all(
            int(by_year.get(LABEL_A, pd.Series()).get(year, 0)) > 0
            and int(by_year.get(LABEL_B, pd.Series()).get(year, 0)) > 0
            for year in (2022, 2023, 2024)
        ),
        "A_and_B_each_side": all(
            int(by_side.get(LABEL_A, pd.Series()).get(side, 0)) > 0
            and int(by_side.get(LABEL_B, pd.Series()).get(side, 0)) > 0
            for side in ("BUY", "SELL")
        ),
        "jaccard_A_both_at_least_070": min(
            jaccards["A_low_425"], jaccards["A_high_575"]
        )
        >= 0.70,
        "jaccard_B_both_at_least_070": min(
            jaccards["B_low_425"], jaccards["B_high_575"]
        )
        >= 0.70,
    }
    return {
        "sessions": int(len(frame)),
        "eligible_sessions": int(len(eligible)),
        "excluded_sessions": int(len(frame) - len(eligible)),
        "counts": {
            LABEL_A: count_a,
            LABEL_B: count_b,
            LABEL_C: count_c,
        },
        "prevalence": {
            LABEL_A: count_a / len(eligible) if len(eligible) else None,
            LABEL_B: count_b / len(eligible) if len(eligible) else None,
            LABEL_C: count_c / len(eligible) if len(eligible) else None,
        },
        "minimum_class_count_15pct": minimum,
        "clean_class_max_share": (
            max(count_a, count_b) / clean if clean else None
        ),
        "jaccards": jaccards,
        "by_year": by_year.to_dict(orient="index"),
        "by_side": by_side.to_dict(orient="index"),
        "total_late_received_predecision_exchange_records": int(
            frame["late_received_predecision_exchange_records"].sum()
        ),
        "total_F_dep": float(eligible["F_dep"].sum()),
        "total_C_dep": float(eligible["C_dep"].sum()),
        "gates": gates,
        "instrument_pass": all(gates.values()),
    }


def main() -> int:
    project = Path(__file__).resolve().parent
    base = project / "contexto_codex_claude" / "mechanical_book_v1"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--design",
        type=Path,
        default=project
        / "contexto_codex_claude"
        / "20260724_021_PREREGISTRO_MECHANICAL_BOOK_V1.md",
    )
    parser.add_argument(
        "--handoff-audit",
        type=Path,
        default=base / "MECHANICAL_BOOK_HANDOFF_AUDIT_98.csv",
    )
    parser.add_argument(
        "--labels-output",
        type=Path,
        default=base / "MECHANICAL_BOOK_V1_LABELS_98.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=base / "MECHANICAL_BOOK_V1_RESULT.json",
    )
    args = parser.parse_args()

    actual_hash = sha256_file(args.design)
    if actual_hash != DESIGN_HASH:
        raise RuntimeError(
            f"Frozen design hash mismatch: {actual_hash} != {DESIGN_HASH}"
        )
    audit = pd.read_csv(args.handoff_audit).sort_values(
        ["fecha", "BurstId"]
    )
    if len(audit) != 98 or not audit["overlap_prefix_exact"].all():
        raise ValueError("Handoff audit is not 98/98 prefix-exact")
    records = []
    for position, row in audit.reset_index(drop=True).iterrows():
        cutoff_value = row.get(
            "strict_feature_cutoff_utc_exclusive"
        )
        if pd.isna(cutoff_value) or not str(cutoff_value).strip():
            cutoff_value = row["decision_utc"]
        cutoff = pd.to_datetime(
            cutoff_value,
            utc=True,
        )
        outcome = _normalize(
            db.DBNStore.from_file(Path(row["outcome_path"])).to_df()
        )
        metrics = apply_outcome(
            pd.read_parquet(row["state_cache_path"]),
            outcome,
            int(row["pre_overlap_records"]),
            cutoff,
            str(row["burst_side"]),
        )
        records.append(
            {
                "fecha": str(row["fecha"]),
                "year": int(str(row["fecha"])[:4]),
                "BurstId": str(row["BurstId"]),
                "burst_side": str(row["burst_side"]),
                "cutoff_utc": cutoff.isoformat(),
                "late_received_predecision_exchange_records": int(
                    row["late_received_predecision_exchange_records"]
                ),
                **metrics,
                "information_status": (
                    "MECHANICAL_OUTCOME_ONLY_NEVER_PREDICTOR"
                ),
            }
        )
        print(
            f"[MECH LABEL {position + 1}/98] {row['fecha']} "
            f"{metrics.get('base_label', metrics['exclusion_reason'])} "
            f"F={metrics.get('F_dep', 0):.0f} "
            f"C={metrics.get('C_dep', 0):.0f}",
            flush=True,
        )
    frame = pd.DataFrame(records)
    frame.to_csv(args.labels_output, index=False)
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "design_path": str(args.design),
        "design_sha256": actual_hash,
        "labels_path": str(args.labels_output),
        "predictive_model_trained": False,
        "terminal_results_used": False,
        "last_sale_future_used": False,
        **summarize(frame),
    }
    args.summary_output.write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
