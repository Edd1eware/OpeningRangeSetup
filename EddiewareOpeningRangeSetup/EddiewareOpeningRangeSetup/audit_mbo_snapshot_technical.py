"""Audit historical MBO snapshot sessions without ATAS footprint joins."""

from __future__ import annotations

import argparse
import json
import math
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
import numpy as np
import pandas as pd


TICK_SIZE = 0.25
MIN_INTERNAL_RECONCILIATION_PCT = 99.0
MAX_LEFT_CENSORED_ORDER_PCT = 1.0


def _utc(value: Any) -> pd.Timestamp:
    return pd.to_datetime(value, utc=True, errors="raise", format="mixed")


def _load_frame(path: Path) -> tuple[pd.DataFrame, str]:
    store = db.DBNStore.from_file(path)
    metadata_stype_out = str(store.metadata.stype_out)
    frame = store.to_df()
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    frame["ts_event"] = pd.to_datetime(
        frame["ts_event"], utc=True, errors="raise", format="mixed"
    )
    frame["flags"] = pd.to_numeric(frame["flags"], errors="raise").astype("uint16")
    frame["sequence"] = pd.to_numeric(
        frame["sequence"], errors="raise"
    ).astype("uint64")
    frame["channel_id"] = pd.to_numeric(
        frame["channel_id"], errors="raise"
    ).astype("uint16")
    frame["order_id"] = pd.to_numeric(
        frame["order_id"], errors="raise"
    ).astype("uint64")
    frame["size"] = pd.to_numeric(frame["size"], errors="raise").astype("int64")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["action"] = frame["action"].astype(str)
    frame["side"] = frame["side"].astype(str)
    return frame, metadata_stype_out


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


def audit_frame(
    frame: pd.DataFrame,
    row: pd.Series,
    metadata_stype_out: str,
) -> dict[str, Any]:
    decision_cutoff = _utc(row["strict_feature_cutoff_utc_exclusive"])
    burst_cutoff = _utc(row["burst_timestamp_utc"]).floor("ms")
    feature_last = _last_completed_ordinal(frame, decision_cutoff)
    burst_state_last = _last_completed_ordinal(frame, burst_cutoff)
    if burst_state_last > feature_last:
        raise ValueError("Burst state packet occurs after feature cutoff")

    usable = frame.iloc[: feature_last + 1]
    snapshot_mask = usable["flags"].map(
        lambda value: bool(int(value) & int(db.RecordFlags.F_SNAPSHOT))
    )
    last_mask = usable["flags"].map(
        lambda value: bool(int(value) & int(db.RecordFlags.F_LAST))
    )
    bad_book_rows = int(
        usable["flags"]
        .map(lambda value: bool(int(value) & int(db.RecordFlags.F_MAYBE_BAD_BOOK)))
        .sum()
    )
    snapshot_rows = int(snapshot_mask.sum())
    snapshot_clear_rows = int(
        (snapshot_mask & usable["action"].eq("R")).sum()
    )
    snapshot_add_rows = int((snapshot_mask & usable["action"].eq("A")).sum())
    snapshot_last_rows = int((snapshot_mask & last_mask).sum())

    state: dict[int, tuple[str, float, float]] = {}
    levels: dict[tuple[str, float], float] = {}
    first_action: dict[int, str] = {}
    previous_sequence: dict[int, int] = {}
    sequence_regressions = 0
    duplicate_add_rows = 0
    modify_rows = 0
    modify_reconciled_rows = 0
    cancel_rows = 0
    cancel_reconciled_rows = 0
    cancel_exceeds_state_rows = 0
    fill_groups: set[tuple[int, int, float]] = set()
    fill_state_known_groups: set[tuple[int, int, float]] = set()
    book_effect_groups: set[tuple[int, int, float]] = set()
    bbo_at_burst: list[tuple[float, float]] | None = None
    attacked_order_count = 0

    def update_level(side: str, price: float, delta: float) -> None:
        key = (side, price)
        updated = levels.get(key, 0.0) + delta
        if abs(updated) < 1e-9:
            levels.pop(key, None)
        else:
            levels[key] = updated

    for ordinal, item in enumerate(usable.itertuples(index=False)):
        flags = int(item.flags)
        is_snapshot = bool(flags & int(db.RecordFlags.F_SNAPSHOT))
        # Synthetic snapshot A rows are ordered by queue priority and retain
        # historical sequence values. They are not an incremental feed sequence.
        if not is_snapshot:
            channel = int(item.channel_id)
            sequence = int(item.sequence)
            previous = previous_sequence.get(channel)
            if previous is not None and sequence < previous:
                sequence_regressions += 1
            previous_sequence[channel] = sequence

        action = str(item.action)
        order_id = int(item.order_id)
        price = float(item.price) if pd.notna(item.price) else math.nan
        side = str(item.side)
        size = float(item.size)
        if order_id and action in {"A", "M", "C", "F"}:
            first_action.setdefault(order_id, action)

        if action == "R":
            state.clear()
            levels.clear()
        elif action == "A":
            if order_id in state:
                duplicate_add_rows += 1
            else:
                state[order_id] = (side, price, size)
                update_level(side, price, size)
        elif action == "M":
            modify_rows += 1
            current = state.get(order_id)
            key = (order_id, int(item.ts_event.value), price)
            if current is None:
                state[order_id] = (side, price, size)
                update_level(side, price, size)
            else:
                old_side, old_price, old_size = current
                update_level(old_side, old_price, -old_size)
                update_level(side, price, size)
                state[order_id] = (side, price, size)
                modify_reconciled_rows += 1
                book_effect_groups.add(key)
        elif action == "C":
            cancel_rows += 1
            current = state.get(order_id)
            key = (order_id, int(item.ts_event.value), price)
            if current is not None:
                old_side, old_price, old_size = current
                if size <= old_size:
                    remaining = old_size - size
                    update_level(old_side, old_price, -size)
                    cancel_reconciled_rows += 1
                    book_effect_groups.add(key)
                    if remaining <= 0:
                        state.pop(order_id, None)
                    else:
                        state[order_id] = (old_side, old_price, remaining)
                else:
                    cancel_exceeds_state_rows += 1
        elif action == "F":
            key = (order_id, int(item.ts_event.value), price)
            fill_groups.add(key)
            if order_id in state:
                fill_state_known_groups.add(key)

        if ordinal == burst_state_last:
            attacked_side = "A" if str(row["burst_side"]).upper() == "BUY" else "B"
            bbo_at_burst = _top_levels(levels, attacked_side, 3)
            attacked_prices = {price_value for price_value, _ in bbo_at_burst}
            attacked_order_count = sum(
                1
                for current_side, current_price, current_size in state.values()
                if current_side == attacked_side
                and current_price in attacked_prices
                and current_size > 0
            )

    reconciled_fill_groups = fill_state_known_groups.union(
        fill_groups.intersection(book_effect_groups)
    )
    identity_units = modify_rows + cancel_rows + len(fill_groups)
    reconciled_identity_units = (
        modify_reconciled_rows
        + cancel_reconciled_rows
        + len(reconciled_fill_groups)
    )
    reconciliation_pct = (
        100.0 * reconciled_identity_units / identity_units
        if identity_units
        else math.nan
    )
    order_count = len(first_action)
    first_add_count = sum(value == "A" for value in first_action.values())
    left_censored_pct = (
        100.0 * (order_count - first_add_count) / order_count
        if order_count
        else math.nan
    )

    expected_id = int(float(row["resolved_instrument_id"]))
    observed_ids = {
        int(value) for value in usable["instrument_id"].dropna().unique()
    }
    snapshot_pass = (
        snapshot_rows > 0
        and snapshot_clear_rows > 0
        and snapshot_add_rows > 0
        and snapshot_last_rows > 0
    )
    contract_pass = (
        metadata_stype_out == "instrument_id"
        and observed_ids == {expected_id}
        and bool(str(row["resolved_raw_symbol"]).strip())
    )
    bbo_pass = bbo_at_burst is not None and len(bbo_at_burst) == 3
    cutoff_pass = bool(
        usable["ts_event"].lt(decision_cutoff).all()
        and int(feature_last) <= int(frame.index.max())
    )
    gate_checks = {
        "snapshot_pass": snapshot_pass,
        "contract_pass": contract_pass,
        "bad_book_pass": bad_book_rows == 0,
        "sequence_pass": sequence_regressions == 0,
        "reconciliation_pass": reconciliation_pct
        >= MIN_INTERNAL_RECONCILIATION_PCT,
        "left_censor_pass": left_censored_pct <= MAX_LEFT_CENSORED_ORDER_PCT,
        "attacked_levels_pass": bbo_pass and attacked_order_count > 0,
        "cutoff_pass": cutoff_pass,
    }
    l0_price = bbo_at_burst[0][0] if bbo_at_burst else math.nan
    return {
        "request_id": str(row["request_id"]),
        "fecha": str(row["fecha"]),
        "BurstId": str(row["BurstId"]),
        "year": int(row["year"]),
        "burst_side": str(row["burst_side"]),
        "family_label_only": str(row["family_label_only"]),
        "resolved_raw_symbol": str(row["resolved_raw_symbol"]),
        "resolved_instrument_id": expected_id,
        "metadata_stype_out": metadata_stype_out,
        "observed_instrument_ids": "|".join(map(str, sorted(observed_ids))),
        "file_records": int(len(frame)),
        "usable_records_through_last_f_last": int(len(usable)),
        "tail_records_excluded_after_last_f_last": int(len(frame) - len(usable)),
        "snapshot_rows": snapshot_rows,
        "snapshot_clear_rows": snapshot_clear_rows,
        "snapshot_add_rows": snapshot_add_rows,
        "snapshot_last_rows": snapshot_last_rows,
        "bad_book_rows": bad_book_rows,
        "sequence_regressions": sequence_regressions,
        "unique_identity_order_ids": order_count,
        "first_action_add_count": first_add_count,
        "left_censored_order_pct": left_censored_pct,
        "modify_rows": modify_rows,
        "modify_reconciled_rows": modify_reconciled_rows,
        "cancel_rows": cancel_rows,
        "cancel_reconciled_rows": cancel_reconciled_rows,
        "cancel_exceeds_state_rows": cancel_exceeds_state_rows,
        "fill_groups": len(fill_groups),
        "fill_reconciled_groups": len(reconciled_fill_groups),
        "identity_reconciliation_pct": reconciliation_pct,
        "attacked_l0_price_mbo": l0_price,
        "attacked_l0_depth_mbo": (
            bbo_at_burst[0][1] if bbo_at_burst else math.nan
        ),
        "attacked_l0_l2_depth_mbo": (
            sum(size for _, size in bbo_at_burst) if bbo_at_burst else math.nan
        ),
        "attacked_l0_l2_order_count": attacked_order_count,
        "atas_burst_price_informational": float(row["burst_price"]),
        "atas_vs_mbo_l0_abs_ticks_informational": (
            abs(float(row["burst_price"]) - l0_price) / TICK_SIZE
            if math.isfinite(l0_price)
            else math.nan
        ),
        "footprint_atas_comparison_used_as_gate": False,
        **gate_checks,
        "technical_gate_pass": all(gate_checks.values()),
    }


def _write_markdown(audit: pd.DataFrame, output: Path) -> None:
    passed = bool(audit["technical_gate_pass"].all())
    expected_sessions = len(audit)
    lines = [
        f"# AUDITORÍA TÉCNICA — MBO SNAPSHOT {expected_sessions}",
        "",
        f"Veredicto: **{'PASA' if passed else 'NO PASA'}**.",
        "",
        "La comparación de footprint ATAS–Databento no se usó como puerta. "
        "Toda reconciliación es interna al stream MBO.",
        "",
        "## Resumen",
        "",
        f"- Sesiones: {len(audit)}/{expected_sessions}.",
        f"- Registros: {int(audit['file_records'].sum()):,}.",
        f"- Snapshot válido: {int(audit['snapshot_pass'].sum())}/{expected_sessions}.",
        f"- Contrato raw/instrument_id válido: {int(audit['contract_pass'].sum())}/{expected_sessions}.",
        f"- F_MAYBE_BAD_BOOK: {int(audit['bad_book_rows'].sum()):,}.",
        f"- Retrocesos de sequence: {int(audit['sequence_regressions'].sum()):,}.",
        f"- Reconciliación interna mínima: {audit['identity_reconciliation_pct'].min():.4f}%.",
        f"- Censura izquierda máxima: {audit['left_censored_order_pct'].max():.4f}%.",
        f"- L0:L2 atacados reconstruibles: {int(audit['attacked_levels_pass'].sum())}/{expected_sessions}.",
        f"- Cutoff causal válido: {int(audit['cutoff_pass'].sum())}/{expected_sessions}.",
        "",
        "## Resultado por sesión",
        "",
        "| Fecha | Contrato | Snapshot | Reconciliación | Censura izq. | L0:L2 | Gate |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in audit.itertuples(index=False):
        lines.append(
            f"| {row.fecha} | {row.resolved_raw_symbol} | "
            f"{'PASS' if row.snapshot_pass else 'FAIL'} | "
            f"{row.identity_reconciliation_pct:.4f}% | "
            f"{row.left_censored_order_pct:.4f}% | "
            f"{'PASS' if row.attacked_levels_pass else 'FAIL'} | "
            f"{'PASS' if row.technical_gate_pass else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Alcance del veredicto",
            "",
            "PASA sólo significa que los datos permiten construir causalmente las "
            "ocho features preregistradas. No demuestra todavía separación entre "
            "absorción y breakout.",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")


def _audit_manifest_item(
    payload: tuple[int, int, dict[str, Any], str],
) -> tuple[int, dict[str, Any]]:
    index, total, row_values, data_dir_value = payload
    row = pd.Series(row_values)
    path = Path(data_dir_value) / f"{row['request_id']}.mbo.dbn.zst"
    if not path.exists():
        raise FileNotFoundError(path)
    frame, metadata_stype_out = _load_frame(path)
    result = audit_frame(frame, row, metadata_stype_out)
    result["file_path"] = str(path)
    result["file_bytes"] = path.stat().st_size
    result["_progress"] = (
        f"[{index + 1}/{total}] audited {row['request_id']}: "
        f"reconciliation={result['identity_reconciliation_pct']:.4f}% "
        f"left_censored={result['left_censored_order_pct']:.4f}% "
        f"gate={'PASS' if result['technical_gate_pass'] else 'FAIL'}"
    )
    return index, result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--md-output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest)
    if args.workers < 1:
        raise ValueError("--workers must be at least 1")
    payloads = [
        (index, len(manifest), row, str(args.data_dir))
        for index, row in enumerate(manifest.to_dict(orient="records"))
    ]
    rows = []
    if args.workers == 1:
        results = map(_audit_manifest_item, payloads)
    else:
        executor = ProcessPoolExecutor(max_workers=args.workers)
        results = executor.map(_audit_manifest_item, payloads)
    try:
        for _, result in results:
            print(result.pop("_progress"), flush=True)
            rows.append(result)
    finally:
        if args.workers != 1:
            executor.shutdown(wait=True, cancel_futures=True)

    audit = pd.DataFrame(rows)
    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.csv_output, index=False)
    expected_sessions = int(len(manifest))
    gate_passed = bool(
        len(audit) == expected_sessions and audit["technical_gate_pass"].all()
    )
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sessions": int(len(audit)),
        "total_records": int(audit["file_records"].sum()),
        "total_bytes": int(audit["file_bytes"].sum()),
        "snapshot_sessions_passed": int(audit["snapshot_pass"].sum()),
        "contract_sessions_passed": int(audit["contract_pass"].sum()),
        "bad_book_rows": int(audit["bad_book_rows"].sum()),
        "sequence_regressions": int(audit["sequence_regressions"].sum()),
        "minimum_internal_reconciliation_pct": float(
            audit["identity_reconciliation_pct"].min()
        ),
        "maximum_left_censored_order_pct": float(
            audit["left_censored_order_pct"].max()
        ),
        "attacked_levels_sessions_passed": int(
            audit["attacked_levels_pass"].sum()
        ),
        "cutoff_sessions_passed": int(audit["cutoff_pass"].sum()),
        "footprint_atas_comparison_used_as_gate": False,
        "technical_gate_passed": gate_passed,
        "next_action": (
            "READY_FOR_PREREGISTERED_FEATURE_EXTRACTION"
            if gate_passed
            else "STOP_AND_REPAIR_DATA_PIPELINE"
        ),
        "csv_output": str(args.csv_output),
        "md_output": str(args.md_output),
    }
    args.json_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_markdown(audit, args.md_output)
    print(json.dumps(summary, indent=2))
    return 0 if gate_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
