"""Blind, sequence-aligned calibration for the joint A/B V5 instrument."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import ab_joint_calibrate_v2 as common


DESIGN_HASH = "22b486cc7e310f5117f0a932817695d3c702a69ec975162927ca90fc8e9070a8"
MIN_ORIENTED_SEQUENCE_SUPPORT = 100


def _max_dwell_after(
    event_ns: np.ndarray,
    oriented_ticks: np.ndarray,
    start_index: int,
    threshold: float,
    direction: str,
    end_ns: int,
) -> tuple[float, bool]:
    if start_index >= len(oriented_ticks):
        return 0.0, False
    current_ns = 0
    maximum_ns = 0
    crossed = False
    for index in range(start_index, len(oriented_ticks)):
        value = float(oriented_ticks[index])
        qualifies = (
            value >= threshold if direction == "above" else value <= -threshold
        )
        next_ns = (
            int(event_ns[index + 1])
            if index + 1 < len(event_ns)
            else int(end_ns)
        )
        duration_ns = max(0, next_ns - int(event_ns[index]))
        if qualifies:
            crossed = True
            current_ns += duration_ns
            maximum_ns = max(maximum_ns, current_ns)
        else:
            current_ns = 0
    return maximum_ns / 1_000_000_000.0, crossed


def calibrate_thresholds_v5(
    paths: list[common.WindowPath],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    oriented: list[tuple[common.WindowPath, str, np.ndarray]] = []
    for path in paths:
        oriented.append((path, "PLUS", path.raw_ticks))
        oriented.append((path, "MINUS", -path.raw_ticks))
    if not oriented:
        raise ValueError("No oriented pseudo-window observations")

    positive = np.asarray(
        [max(0.0, float(np.max(values))) for _, _, values in oriented],
        dtype=float,
    )
    adverse = np.asarray(
        [max(0.0, float(np.max(-values))) for _, _, values in oriented],
        dtype=float,
    )
    t_push = float(np.quantile(positive, 0.50))
    t_ext = float(np.quantile(positive, 0.75))
    t_ret = float(np.quantile(adverse, 0.50))

    dwell_b_values: list[float] = []
    dwell_a_values: list[float] = []
    metrics: list[dict[str, Any]] = []
    for path, orientation, values in oriented:
        push_candidates = np.flatnonzero(values >= t_push)
        push_index = (
            int(push_candidates[0]) if len(push_candidates) else None
        )
        dwell_b = dwell_a = 0.0
        sequence_b = sequence_a = False
        if push_index is not None:
            dwell_b, sequence_b = _max_dwell_after(
                path.event_ns,
                values,
                push_index,
                t_ext,
                "above",
                path.end_ns,
            )
            dwell_a, sequence_a = _max_dwell_after(
                path.event_ns,
                values,
                push_index + 1,
                t_ret,
                "below",
                path.end_ns,
            )
        if sequence_b:
            dwell_b_values.append(dwell_b)
        if sequence_a:
            dwell_a_values.append(dwell_a)
        metrics.append(
            {
                "fecha": path.fecha,
                "window_start_utc": pd.Timestamp(
                    path.start_ns, tz="UTC"
                ).isoformat(),
                "window_end_utc_exclusive": pd.Timestamp(
                    path.end_ns, tz="UTC"
                ).isoformat(),
                "orientation": orientation,
                "p0": path.p0,
                "event_count": int(len(path.event_ns)),
                "positive_excursion_ticks": max(
                    0.0, float(np.max(values))
                ),
                "adverse_excursion_ticks": max(
                    0.0, float(np.max(-values))
                ),
                "push_exists": push_index is not None,
                "push_ordinal_in_window": push_index,
                "sequence_B_exists": sequence_b,
                "sequence_A_exists": sequence_a,
                "sequence_B_max_dwell_s": dwell_b,
                "sequence_A_max_dwell_s": dwell_a,
            }
        )
    if not dwell_b_values or not dwell_a_values:
        raise ValueError("No qualifying sequence for one or both dwell branches")
    thresholds = {
        "T_push_ticks": t_push,
        "T_ext_ticks": t_ext,
        "T_ret_ticks": t_ret,
        "T_dwB_seconds": float(np.quantile(dwell_b_values, 0.50)),
        "T_dwA_seconds": float(np.quantile(dwell_a_values, 0.50)),
        "pseudo_window_count": int(len(paths)),
        "oriented_observation_count": int(len(oriented)),
        "dwell_B_oriented_sequence_support": int(len(dwell_b_values)),
        "dwell_A_oriented_sequence_support": int(len(dwell_a_values)),
    }
    return thresholds, metrics


def main() -> int:
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "DATABENTO_MBO_SNAPSHOT_DISCOVERY_100_RESOLVED_20260723.csv",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "MBO_SNAPSHOT_DISCOVERY_100_AUDIT_20260723.csv",
    )
    parser.add_argument(
        "--design",
        type=Path,
        default=project
        / "contexto_codex_claude"
        / "20260724_016_PREREGISTRO_V5_INSTRUMENTO.md",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project / "contexto_codex_claude" / "joint_ab_v5",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    actual_hash = common.sha256_file(args.design)
    if actual_hash != DESIGN_HASH:
        raise RuntimeError(
            f"Frozen design hash mismatch: {actual_hash} != {DESIGN_HASH}"
        )
    manifest = pd.read_csv(args.manifest)
    audit = pd.read_csv(args.audit)
    rows = manifest.merge(
        audit[["fecha", "BurstId", "file_path"]],
        on=["fecha", "BurstId"],
        how="left",
        validate="one_to_one",
    )
    rows["fecha"] = rows["fecha"].astype(str)
    rows = rows.loc[
        ~rows["fecha"].isin(common.EXCLUDED_ROLLOVER_DATES)
    ].sort_values(["fecha", "BurstId"]).reset_index(drop=True)
    if args.limit is None and len(rows) != 98:
        raise ValueError(f"Expected 98 valid sessions, found {len(rows)}")
    if args.limit is not None:
        rows = rows.head(args.limit).copy()

    paths: list[common.WindowPath] = []
    window_quality: list[dict[str, Any]] = []
    session_quality: list[dict[str, Any]] = []
    for position, row in rows.iterrows():
        fecha = str(row["fecha"])
        path = Path(str(row["file_path"]))
        windows = common.window_grid(
            fecha, row["strategy_decision_timestamp_utc"]
        )
        start, end = common.calibration_bounds(
            fecha, row["strategy_decision_timestamp_utc"]
        )
        trades, event_quality = common.load_calibration_events(
            path, start, end
        )
        repeat_hash = ""
        repeat_match = True
        if fecha in common.DOUBLE_DECODE_DATES:
            _, repeat_quality = common.load_calibration_events(
                path, start, end
            )
            repeat_hash = str(repeat_quality["physical_stream_sha256"])
            repeat_match = (
                repeat_hash == event_quality["physical_stream_sha256"]
            )
            if not repeat_match:
                raise ValueError(f"Non-deterministic DBN decoding: {path}")
        session_paths, quality = common.build_paths(
            fecha, trades, windows
        )
        paths.extend(session_paths)
        window_quality.extend(quality)
        session_quality.append(
            {
                "fecha": fecha,
                "BurstId": str(row["BurstId"]),
                "symbol": str(row["resolved_raw_symbol"]),
                "file_path": str(path),
                "planned_windows": int(len(windows)),
                "valid_windows": int(len(session_paths)),
                "invalid_windows": int(len(windows) - len(session_paths)),
                "last_sale_events_loaded": int(len(trades)),
                **event_quality,
                "double_decode_checked": (
                    fecha in common.DOUBLE_DECODE_DATES
                ),
                "double_decode_sha256": repeat_hash,
                "double_decode_match": repeat_match,
                "support_pass": (
                    len(session_paths) >= common.MIN_WINDOWS_PER_SESSION
                ),
            }
        )
        print(
            f"[V5 CAL {position + 1}/{len(rows)}] {fecha} "
            f"windows={len(session_paths)}/{len(windows)}",
            flush=True,
        )

    thresholds, metrics = calibrate_thresholds_v5(paths)
    session_frame = pd.DataFrame(session_quality)
    window_frame = pd.DataFrame(window_quality)
    metrics_frame = pd.DataFrame(metrics)
    gates = {
        "design_hash_match": actual_hash == DESIGN_HASH,
        "session_count_98": len(rows) == 98,
        "all_sessions_min_10_windows": bool(
            session_frame["support_pass"].all()
        ),
        "aggregate_min_1000_physical_windows": (
            thresholds["pseudo_window_count"]
            >= common.MIN_WINDOWS_AGGREGATE
        ),
        "exactly_two_orientations_per_window": (
            thresholds["oriented_observation_count"]
            == 2 * thresholds["pseudo_window_count"]
        ),
        "dwell_B_min_100_oriented_sequences": (
            thresholds["dwell_B_oriented_sequence_support"]
            >= MIN_ORIENTED_SEQUENCE_SUPPORT
        ),
        "dwell_A_min_100_oriented_sequences": (
            thresholds["dwell_A_oriented_sequence_support"]
            >= MIN_ORIENTED_SEQUENCE_SUPPORT
        ),
        "positive_ordered_price_thresholds": (
            thresholds["T_push_ticks"] > 0
            and thresholds["T_ext_ticks"] >= thresholds["T_push_ticks"]
            and thresholds["T_ret_ticks"] > 0
        ),
        "positive_dwell_thresholds": (
            thresholds["T_dwB_seconds"] > 0
            and thresholds["T_dwA_seconds"] > 0
        ),
        "all_used_events_closed": int(
            session_frame["unclosed_t_events"].sum()
        )
        == 0,
        "all_used_events_single_timestamp": int(
            session_frame["mixed_timestamp_t_events"].sum()
        )
        == 0,
        "zero_maybe_bad_book_records": int(
            session_frame["maybe_bad_book_records"].sum()
        )
        == 0,
        "zero_sequence_regressions": int(
            session_frame["sequence_regressions"].sum()
        )
        == 0,
        "deterministic_double_decode_3_sessions": bool(
            session_frame.loc[
                session_frame["double_decode_checked"],
                "double_decode_match",
            ].all()
        )
        and int(session_frame["double_decode_checked"].sum()) == 3,
    }
    calibration_pass = bool(all(gates.values()))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    session_frame.to_csv(
        args.output_dir / "AB_V5_CALIBRATION_SESSION_QUALITY.csv",
        index=False,
    )
    window_frame.to_csv(
        args.output_dir / "AB_V5_CALIBRATION_WINDOW_QUALITY.csv",
        index=False,
    )
    metrics_frame.to_csv(
        args.output_dir / "AB_V5_ORIENTED_PSEUDO_WINDOW_METRICS.csv",
        index=False,
    )
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "design_path": str(args.design),
        "design_sha256": actual_hash,
        "calibration_pass": calibration_pass,
        "gates": gates,
        "thresholds": thresholds,
        "excluded_rollover_dates": sorted(
            common.EXCLUDED_ROLLOVER_DATES
        ),
        "real_outcomes_read": False,
        "predictors_or_terminal_results_read": False,
        "download_performed": False,
    }
    (args.output_dir / "AB_V5_FROZEN_THRESHOLDS.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    gate_lines = "\n".join(
        f"- `{name}`: {'PASS' if passed else 'FAIL'}"
        for name, passed in gates.items()
    )
    report = f"""# Calibración causal A/B V5

Estado: **{'PASS' if calibration_pass else 'FAIL'}**

- Diseño SHA-256: `{actual_hash}`
- Sesiones: {len(rows)}
- Pseudoventanas físicas: {thresholds['pseudo_window_count']}
- Observaciones orientadas: {thresholds['oriented_observation_count']}
- T_push: {thresholds['T_push_ticks']:.6f} ticks
- T_ext: {thresholds['T_ext_ticks']:.6f} ticks
- T_ret: {thresholds['T_ret_ticks']:.6f} ticks
- T_dwB: {thresholds['T_dwB_seconds']:.9f} s
- T_dwA: {thresholds['T_dwA_seconds']:.9f} s
- Soporte B: {thresholds['dwell_B_oriented_sequence_support']}
- Soporte A: {thresholds['dwell_A_oriented_sequence_support']}

## Gates

{gate_lines}

No se leyeron outcomes reales, predictores ni resultados terminales.
"""
    (args.output_dir / "AB_V5_CALIBRATION_REPORT.md").write_text(
        report, encoding="utf-8"
    )
    print(json.dumps(result, indent=2), flush=True)
    return 0 if calibration_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
