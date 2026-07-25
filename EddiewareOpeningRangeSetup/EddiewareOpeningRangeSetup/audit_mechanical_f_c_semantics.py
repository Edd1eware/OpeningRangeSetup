"""Audit the F/C relationship used by Mechanical Book V1.

This is a read-only diagnostic. It does not relabel sessions and does not
change the frozen Mechanical Book V1 instrument.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
import pandas as pd

from mechanical_book_v1_label_pilot import F_LAST, _normalize


def _event_groups(
    frame: pd.DataFrame,
    start_record: int,
    cutoff: pd.Timestamp,
) -> list[tuple[int, pd.Timestamp, list[Any]]]:
    window_end = cutoff + pd.Timedelta(seconds=5)
    groups: list[tuple[int, pd.Timestamp, list[Any]]] = []
    packet: list[Any] = []
    event_number = 0
    for item in frame.iloc[int(start_record) :].itertuples(index=False):
        packet.append(item)
        if not bool(int(item.flags) & F_LAST):
            continue
        event_number += 1
        close_recv = max(value.ts_recv for value in packet)
        if close_recv < cutoff:
            raise ValueError("Confirmed prefix did not end at an F_LAST boundary")
        if close_recv >= window_end:
            break
        groups.append((event_number, close_recv, packet))
        packet = []
    return groups


def audit_session(
    audit_row: Any,
    label_row: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    cutoff_value = getattr(
        audit_row,
        "strict_feature_cutoff_utc_exclusive",
        None,
    )
    if cutoff_value is None or pd.isna(cutoff_value) or not str(cutoff_value).strip():
        cutoff_value = audit_row.decision_utc
    cutoff = pd.to_datetime(cutoff_value, utc=True)
    frame = _normalize(
        db.DBNStore.from_file(Path(audit_row.outcome_path)).to_df()
    )
    attacked_side = "A" if str(audit_row.burst_side) == "BUY" else "B"
    l0 = float(label_row.L0)
    state_frame = pd.read_parquet(Path(audit_row.state_cache_path))
    state = {
        int(item.order_id): (
            str(item.side),
            float(item.price),
            float(item.size),
        )
        for item in state_frame.itertuples(index=False)
    }

    group_rows: list[dict[str, Any]] = []
    packet_rows: list[dict[str, Any]] = []
    totals: dict[str, float] = defaultdict(float)
    identity_keys = 0
    sibling_keys = 0
    equal_qty_keys = 0
    c_less_than_f_keys = 0
    c_greater_than_f_keys = 0
    state_reduction_keys = 0
    equal_state_reduction_keys = 0

    for event_number, close_recv, packet in _event_groups(
        frame,
        int(audit_row.pre_overlap_records),
        cutoff,
    ):
        fills: dict[tuple[int, float], float] = defaultdict(float)
        cancels: dict[tuple[int, float], float] = defaultdict(float)
        modify_reductions: dict[tuple[int, float], float] = defaultdict(float)
        cancel_reductions: dict[tuple[int, float], float] = defaultdict(float)
        for value in packet:
            action = str(value.action)
            price = float(value.price) if pd.notna(value.price) else math.nan
            key = (int(value.order_id), price)
            if (
                action == "F"
                and str(value.side) == attacked_side
                and price == l0
            ):
                fills[key] += float(value.size)
            elif action == "C":
                cancels[key] += float(value.size)

        for value in packet:
            action = str(value.action)
            if action in {"F", "T", "N"}:
                continue
            order_id = int(value.order_id)
            side = str(value.side)
            price = float(value.price) if pd.notna(value.price) else math.nan
            size = float(value.size)
            if action == "R":
                state.clear()
                continue
            if action == "A":
                state[order_id] = (side, price, size)
                continue
            if action == "M":
                old = state.get(order_id)
                if old is None:
                    state[order_id] = (side, price, size)
                    continue
                old_side, old_price, old_size = old
                removed = (
                    max(0.0, old_size - size)
                    if old_side == side and old_price == price
                    else old_size
                )
                if old_side == attacked_side and old_price == l0:
                    modify_reductions[(order_id, old_price)] += removed
                state[order_id] = (side, price, size)
                continue
            if action == "C":
                old = state.get(order_id)
                if old is None:
                    continue
                old_side, old_price, old_size = old
                removed = min(size, old_size)
                if old_side == attacked_side and old_price == l0:
                    cancel_reductions[(order_id, old_price)] += removed
                remaining = old_size - removed
                if remaining <= 0:
                    state.pop(order_id, None)
                else:
                    state[order_id] = (old_side, old_price, remaining)

        if not fills:
            continue
        for key, fill_qty in fills.items():
            cancel_qty = float(cancels.get(key, 0.0))
            modify_reduction = float(modify_reductions.get(key, 0.0))
            cancel_reduction = float(cancel_reductions.get(key, 0.0))
            total_state_reduction = modify_reduction + cancel_reduction
            has_sibling = cancel_qty > 0
            equal_qty = math.isclose(fill_qty, cancel_qty, abs_tol=1e-9)
            has_state_reduction = total_state_reduction > 0
            equal_state_reduction = math.isclose(
                fill_qty,
                total_state_reduction,
                abs_tol=1e-9,
            )
            identity_keys += 1
            sibling_keys += int(has_sibling)
            equal_qty_keys += int(equal_qty)
            c_less_than_f_keys += int(has_sibling and cancel_qty < fill_qty)
            c_greater_than_f_keys += int(cancel_qty > fill_qty)
            state_reduction_keys += int(has_state_reduction)
            equal_state_reduction_keys += int(equal_state_reduction)
            totals["fill_qty"] += fill_qty
            totals["cancel_qty"] += cancel_qty
            totals["fill_qty_without_identity_sibling"] += (
                fill_qty if not has_sibling else 0.0
            )
            totals["fill_qty_exceeding_sibling_C"] += max(
                0.0, fill_qty - cancel_qty
            )
            totals["cancel_qty_exceeding_sibling_F"] += max(
                0.0, cancel_qty - fill_qty
            )
            totals["modify_state_reduction_qty"] += modify_reduction
            totals["cancel_state_reduction_qty"] += cancel_reduction
            totals["fill_qty_without_state_reduction"] += max(
                0.0,
                fill_qty - total_state_reduction,
            )
            totals["state_reduction_qty_exceeding_fill"] += max(
                0.0,
                total_state_reduction - fill_qty,
            )
            group_rows.append(
                {
                    "fecha": str(audit_row.fecha),
                    "BurstId": str(audit_row.BurstId),
                    "burst_side": str(audit_row.burst_side),
                    "attacked_side": attacked_side,
                    "L0": l0,
                    "event_number_after_prefix": event_number,
                    "event_close_ts_recv": close_recv.isoformat(),
                    "order_id": key[0],
                    "price": key[1],
                    "F_qty": fill_qty,
                    "C_qty_same_event_order_price": cancel_qty,
                    "has_C_identity_sibling": has_sibling,
                    "F_C_qty_equal": equal_qty,
                    "F_minus_C_qty": fill_qty - cancel_qty,
                    "M_state_reduction_qty": modify_reduction,
                    "C_state_reduction_qty": cancel_reduction,
                    "total_state_reduction_qty": total_state_reduction,
                    "has_M_or_C_state_reduction": has_state_reduction,
                    "F_state_reduction_qty_equal": equal_state_reduction,
                    "F_minus_state_reduction_qty": (
                        fill_qty - total_state_reduction
                    ),
                }
            )
            if not equal_state_reduction:
                for ordinal, value in enumerate(packet):
                    packet_rows.append(
                        {
                            "fecha": str(audit_row.fecha),
                            "BurstId": str(audit_row.BurstId),
                            "burst_side": str(audit_row.burst_side),
                            "attacked_side": attacked_side,
                            "L0": l0,
                            "event_number_after_prefix": event_number,
                            "event_close_ts_recv": close_recv.isoformat(),
                            "target_order_id": key[0],
                            "target_price": key[1],
                            "packet_ordinal": ordinal,
                            "ts_recv": value.ts_recv.isoformat(),
                            "ts_event": value.ts_event.isoformat(),
                            "sequence": int(value.sequence),
                            "order_id": int(value.order_id),
                            "action": str(value.action),
                            "side": str(value.side),
                            "price": (
                                float(value.price)
                                if pd.notna(value.price)
                                else None
                            ),
                            "size": float(value.size),
                            "flags": int(value.flags),
                            "is_target_identity": (
                                int(value.order_id) == key[0]
                                and pd.notna(value.price)
                                and float(value.price) == key[1]
                            ),
                        }
                    )

    summary = {
        "fecha": str(audit_row.fecha),
        "BurstId": str(audit_row.BurstId),
        "burst_side": str(audit_row.burst_side),
        "attacked_side": attacked_side,
        "L0": l0,
        "F_C_identity_keys": identity_keys,
        "keys_with_C_identity_sibling": sibling_keys,
        "keys_with_equal_F_C_qty": equal_qty_keys,
        "keys_C_less_than_F": c_less_than_f_keys,
        "keys_C_greater_than_F": c_greater_than_f_keys,
        "keys_with_M_or_C_state_reduction": state_reduction_keys,
        "keys_with_equal_F_state_reduction_qty": (
            equal_state_reduction_keys
        ),
        **totals,
        "previous_fill_without_c_qty": float(label_row.fill_without_c_qty),
    }
    return summary, group_rows, packet_rows


def main() -> int:
    project = Path(__file__).resolve().parent
    base = project / "contexto_codex_claude" / "mechanical_book_v1"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--handoff-audit",
        type=Path,
        default=base / "MECHANICAL_BOOK_HANDOFF_AUDIT_98.csv",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=base / "MECHANICAL_BOOK_V1_LABELS_98.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=base / "f_c_semantics_audit",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    audit = pd.read_csv(args.handoff_audit).sort_values(["fecha", "BurstId"])
    labels = pd.read_csv(args.labels).sort_values(["fecha", "BurstId"])
    joined = audit.merge(
        labels[
            [
                "fecha",
                "BurstId",
                "L0",
                "fill_without_c_qty",
            ]
        ],
        on=["fecha", "BurstId"],
        how="inner",
        validate="one_to_one",
        suffixes=("", "_label"),
    )
    if len(joined) != 98:
        raise ValueError(f"Expected 98 joined rows, found {len(joined)}")

    session_rows: list[dict[str, Any]] = []
    group_rows: list[dict[str, Any]] = []
    packet_rows: list[dict[str, Any]] = []
    for position, row in enumerate(joined.itertuples(index=False), start=1):
        session, groups, packets = audit_session(row, row)
        session_rows.append(session)
        group_rows.extend(groups)
        packet_rows.extend(packets)
        print(
            f"[F/C {position:02d}/98] {row.fecha} "
            f"keys={session['F_C_identity_keys']:.0f} "
            f"siblings={session['keys_with_C_identity_sibling']:.0f} "
            f"F>C={session['keys_C_less_than_F']:.0f}",
            flush=True,
        )

    sessions = pd.DataFrame(session_rows).fillna(0)
    groups = pd.DataFrame(group_rows)
    packets = pd.DataFrame(packet_rows)
    sessions_path = args.output_dir / "MECHANICAL_F_C_SESSION_AUDIT.csv"
    groups_path = args.output_dir / "MECHANICAL_F_C_IDENTITY_GROUPS.csv"
    packets_path = args.output_dir / "MECHANICAL_F_C_NON_EQUAL_PACKET_ROWS.csv"
    sessions.to_csv(sessions_path, index=False)
    groups.to_csv(groups_path, index=False)
    packets.to_csv(packets_path, index=False)

    total_keys = int(sessions["F_C_identity_keys"].sum())
    total_sibling_keys = int(sessions["keys_with_C_identity_sibling"].sum())
    total_fill_qty = float(sessions["fill_qty"].sum())
    missing_sibling_qty = float(
        sessions["fill_qty_without_identity_sibling"].sum()
    )
    f_excess_qty = float(sessions["fill_qty_exceeding_sibling_C"].sum())
    prior_unmatched_qty = float(
        sessions["previous_fill_without_c_qty"].sum()
    )
    state_unmatched_qty = float(
        sessions["fill_qty_without_state_reduction"].sum()
    )
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sessions": len(sessions),
        "sessions_with_F_at_L0": int(
            sessions["F_C_identity_keys"].gt(0).sum()
        ),
        "identity_keys": total_keys,
        "keys_with_C_identity_sibling": total_sibling_keys,
        "identity_sibling_key_coverage": (
            total_sibling_keys / total_keys if total_keys else 1.0
        ),
        "F_qty_at_L0": total_fill_qty,
        "F_qty_without_C_identity_sibling": missing_sibling_qty,
        "identity_sibling_quantity_coverage": (
            1.0 - missing_sibling_qty / total_fill_qty
            if total_fill_qty
            else 1.0
        ),
        "F_qty_exceeding_C_sibling_qty": f_excess_qty,
        "previous_algorithm_fill_without_c_qty": prior_unmatched_qty,
        "previous_unmatched_explained_by_F_gt_C": math.isclose(
            f_excess_qty,
            prior_unmatched_qty,
            abs_tol=1e-9,
        ),
        "sessions_with_F_gt_C": int(
            sessions["keys_C_less_than_F"].gt(0).sum()
        ),
        "sessions_with_missing_identity_sibling": int(
            sessions["fill_qty_without_identity_sibling"].gt(0).sum()
        ),
        "keys_with_M_or_C_state_reduction": int(
            sessions["keys_with_M_or_C_state_reduction"].sum()
        ),
        "keys_with_equal_F_state_reduction_qty": int(
            sessions["keys_with_equal_F_state_reduction_qty"].sum()
        ),
        "F_qty_without_M_or_C_state_reduction": state_unmatched_qty,
        "F_state_reduction_quantity_reconciled": math.isclose(
            state_unmatched_qty,
            0.0,
            abs_tol=1e-9,
        ),
        "sessions_with_unreconciled_F_state_reduction": int(
            sessions["fill_qty_without_state_reduction"].gt(0).sum()
        ),
        "labels_modified": False,
        "model_trained": False,
        "outputs": {
            "sessions": str(sessions_path),
            "groups": str(groups_path),
            "non_equal_packet_rows": str(packets_path),
        },
    }
    result_path = args.output_dir / "MECHANICAL_F_C_AUDIT_RESULT.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
