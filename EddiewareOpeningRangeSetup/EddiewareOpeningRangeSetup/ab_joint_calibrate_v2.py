"""Blind calibration for the joint Codex-Claude A/B label V4.

This program reads only pre-decision trades embedded in the already downloaded
MBO snapshot files.  It does not read terminal trade outcomes and does not
download data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
import numpy as np
import pandas as pd


TICK_SIZE = 0.25
WINDOW_SECONDS = 5
CALIBRATION_LOCAL_START = "08:29:00"
EXCLUDED_ROLLOVER_DATES = {"2022-06-13", "2023-06-13"}
MIN_WINDOWS_PER_SESSION = 10
MIN_WINDOWS_AGGREGATE = 1000
MIN_DWELL_CROSSING_WINDOWS = 100
CHUNK_RECORDS = 500_000
EVENT_LOOKBACK_SECONDS = 10
DOUBLE_DECODE_DATES = {"2022-04-05", "2023-05-18", "2024-07-16"}
DESIGN_HASH = "c1eb770c0d69b9d684fc60147a0cf9d9aa15fdd7d39eccb33e367f612c9a339c"


@dataclass(frozen=True)
class WindowPath:
    fecha: str
    start_ns: int
    end_ns: int
    p0: float
    event_ns: np.ndarray
    raw_ticks: np.ndarray

    @property
    def max_abs_ticks(self) -> float:
        if len(self.raw_ticks) == 0:
            return 0.0
        return float(np.max(np.abs(self.raw_ticks)))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def calibration_bounds(
    fecha: str,
    decision_utc: Any,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    local_start = pd.Timestamp(
        f"{fecha} {CALIBRATION_LOCAL_START}",
        tz="America/Chicago",
    )
    start = local_start.tz_convert("UTC")
    end = pd.to_datetime(decision_utc, utc=True, errors="raise") - pd.Timedelta(
        seconds=60
    )
    return start, end


def window_grid(
    fecha: str,
    decision_utc: Any,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    start, end = calibration_bounds(fecha, decision_utc)
    available_seconds = (end - start).total_seconds()
    count = max(0, int(np.floor(available_seconds / WINDOW_SECONDS)))
    return [
        (
            start + pd.Timedelta(seconds=WINDOW_SECONDS * index),
            start + pd.Timedelta(seconds=WINDOW_SECONDS * (index + 1)),
        )
        for index in range(count)
    ]


def _normalize_mbo_rows(
    frame: pd.DataFrame,
    ordinal_start: int,
) -> pd.DataFrame:
    required = {
        "ts_event",
        "sequence",
        "price",
        "size",
        "action",
        "side",
        "flags",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"MBO chunk lacks required fields: {sorted(missing)}")
    rows = frame[
        ["ts_event", "sequence", "price", "size", "action", "side", "flags"]
    ].copy()
    rows["record_ordinal"] = np.arange(
        ordinal_start, ordinal_start + len(rows), dtype=np.int64
    )
    rows["ts_event"] = pd.to_datetime(
        rows["ts_event"], utc=True, errors="raise", format="mixed"
    )
    rows["sequence"] = pd.to_numeric(
        rows["sequence"], errors="raise"
    ).astype("uint64")
    rows["price"] = pd.to_numeric(rows["price"], errors="coerce")
    rows["size"] = pd.to_numeric(rows["size"], errors="raise").astype("uint64")
    rows["flags"] = pd.to_numeric(rows["flags"], errors="raise").astype("uint16")
    rows["action"] = rows["action"].astype(str)
    rows["side"] = rows["side"].astype(str)
    return rows


def _physical_stream_hash(rows: pd.DataFrame) -> str:
    columns = [
        "ts_event",
        "sequence",
        "record_ordinal",
        "side",
        "price",
        "size",
        "flags",
    ]
    hashed = pd.util.hash_pandas_object(rows[columns], index=False)
    return hashlib.sha256(hashed.to_numpy().tobytes()).hexdigest()


def _is_direction_monotonic(group: pd.DataFrame) -> bool:
    trades = group.loc[group["action"].eq("T")]
    if len(trades) <= 1 or trades["side"].nunique() != 1:
        return len(trades) <= 1
    prices = trades["price"].astype(float).to_numpy()
    differences = np.diff(prices)
    side = str(trades.iloc[0]["side"])
    if side == "B":
        return bool(np.all(differences >= 0))
    if side == "A":
        return bool(np.all(differences <= 0))
    return False


def load_calibration_events(
    path: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return one last-sale state per complete F_LAST-delimited Match Event."""
    lower = start - pd.Timedelta(seconds=EVENT_LOOKBACK_SECONDS)
    pieces: list[pd.DataFrame] = []
    ordinal_start = 0
    for chunk in db.DBNStore.from_file(path).to_df(count=CHUNK_RECORDS):
        rows = _normalize_mbo_rows(chunk, ordinal_start)
        ordinal_start += len(rows)
        inside = rows.loc[
            rows["ts_event"].ge(lower) & rows["ts_event"].lt(end)
        ]
        if not inside.empty:
            pieces.append(inside)
        if rows["ts_event"].min() >= end:
            break

    if not pieces:
        raise ValueError(f"No MBO rows in calibration interval: {path}")
    combined = pd.concat(pieces, ignore_index=True)
    combined = combined.sort_values(
        "record_ordinal", kind="mergesort"
    ).reset_index(drop=True)
    if combined["record_ordinal"].duplicated().any():
        raise ValueError(f"Duplicate physical ordinal in {path}")

    maybe_bad_book = int(
        ((combined["flags"].astype("uint16") & 4) != 0).sum()
    )
    sequence_values = combined["sequence"].astype("int64").to_numpy()
    sequence_regressions = int((np.diff(sequence_values) < 0).sum())
    if maybe_bad_book:
        raise ValueError(f"F_MAYBE_BAD_BOOK in calibration interval: {path}")
    if sequence_regressions:
        raise ValueError(
            f"{path.name}: {sequence_regressions} incremental sequence regressions"
        )

    combined["is_last"] = (combined["flags"].astype("uint16") & 128) != 0
    combined["match_event_id"] = (
        combined["is_last"].shift(fill_value=False).cumsum().astype("int64")
    )
    event_groups = combined.groupby("match_event_id", sort=False)
    event_summary = event_groups.agg(
        closed=("is_last", "any"),
        timestamp_count=("ts_event", "nunique"),
        sequence_count=("sequence", "nunique"),
        record_count=("record_ordinal", "size"),
    )
    trade_rows = combined.loc[
        combined["action"].eq("T") & combined["price"].notna()
    ].copy()
    if trade_rows.empty:
        raise ValueError(f"No T records in calibration interval: {path}")
    trade_event_ids = trade_rows["match_event_id"].unique()
    used_summary = event_summary.loc[trade_event_ids]
    unclosed = int((~used_summary["closed"]).sum())
    mixed_timestamp = int((used_summary["timestamp_count"] != 1).sum())
    if unclosed:
        raise ValueError(f"{path.name}: {unclosed} T-events lack F_LAST")
    if mixed_timestamp:
        raise ValueError(
            f"{path.name}: {mixed_timestamp} T-events mix ts_event values"
        )

    t_event_groups = trade_rows.groupby("match_event_id", sort=False)
    last_sales = t_event_groups.tail(1).copy()
    last_sales = last_sales.sort_values(
        "record_ordinal", kind="mergesort"
    ).reset_index(drop=True)
    if not last_sales["ts_event"].lt(start).any():
        raise ValueError(f"No complete T-event before calibration start: {path}")

    multi_price = int(
        t_event_groups["price"].nunique(dropna=False).gt(1).sum()
    )
    multi_side = int(t_event_groups["side"].nunique(dropna=False).gt(1).sum())
    nonmonotonic = int(
        sum(
            not _is_direction_monotonic(group)
            for _, group in t_event_groups
            if len(group) > 1
        )
    )
    quality = {
        "physical_stream_sha256": _physical_stream_hash(combined),
        "mbo_records_loaded": int(len(combined)),
        "t_records_loaded": int(len(trade_rows)),
        "t_match_events": int(len(last_sales)),
        "multi_sequence_t_events": int(
            (used_summary["sequence_count"] > 1).sum()
        ),
        "multi_price_t_events": multi_price,
        "multi_side_t_events": multi_side,
        "nonmonotonic_t_events": nonmonotonic,
        "unclosed_t_events": unclosed,
        "mixed_timestamp_t_events": mixed_timestamp,
        "maybe_bad_book_records": maybe_bad_book,
        "sequence_regressions": sequence_regressions,
    }
    return last_sales, quality


def build_paths(
    fecha: str,
    trades: pd.DataFrame,
    windows: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> tuple[list[WindowPath], list[dict[str, Any]]]:
    times = trades["ts_event"].astype("int64").to_numpy()
    prices = trades["price"].astype(float).to_numpy()
    paths: list[WindowPath] = []
    quality: list[dict[str, Any]] = []
    for start, end in windows:
        start_ns = int(start.value)
        end_ns = int(end.value)
        prior_index = int(np.searchsorted(times, start_ns, side="left") - 1)
        left = int(np.searchsorted(times, start_ns, side="left"))
        right = int(np.searchsorted(times, end_ns, side="left"))
        has_p0 = prior_index >= 0
        event_count = max(0, right - left)
        valid = has_p0 and event_count > 0
        quality.append(
            {
                "fecha": fecha,
                "window_start_utc": start.isoformat(),
                "window_end_utc_exclusive": end.isoformat(),
                "has_p0": has_p0,
                "event_count": event_count,
                "valid": valid,
            }
        )
        if not valid:
            continue
        p0 = float(prices[prior_index])
        event_ns = times[left:right].astype(np.int64, copy=True)
        raw_ticks = ((prices[left:right] - p0) / TICK_SIZE).astype(
            np.float64, copy=False
        )
        paths.append(
            WindowPath(
                fecha=fecha,
                start_ns=start_ns,
                end_ns=end_ns,
                p0=p0,
                event_ns=event_ns,
                raw_ticks=raw_ticks.copy(),
            )
        )
    return paths, quality


def max_contiguous_dwell_seconds(
    event_ns: np.ndarray,
    oriented_ticks: np.ndarray,
    threshold: float,
    direction: str,
    end_ns: int,
) -> tuple[float, bool]:
    """Return maximum continuous qualifying run and whether a crossing exists."""
    if direction not in {"above", "below"}:
        raise ValueError("direction must be above or below")
    if len(event_ns) != len(oriented_ticks):
        raise ValueError("event and price path lengths differ")
    if len(event_ns) == 0:
        return 0.0, False

    current_ns = 0
    maximum_ns = 0
    crossed = False
    for index, value in enumerate(oriented_ticks):
        qualifies = (
            bool(value >= threshold)
            if direction == "above"
            else bool(value <= -threshold)
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


def calibrate_thresholds(
    paths: list[WindowPath],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    max_abs = np.asarray([path.max_abs_ticks for path in paths], dtype=float)
    if len(max_abs) == 0:
        raise ValueError("No valid pseudo-windows")
    t_push = float(np.quantile(max_abs, 0.50))
    t_ext = float(np.quantile(max_abs, 0.90))
    t_ret = t_push

    dwell_b_values: list[float] = []
    dwell_a_values: list[float] = []
    dwell_b_physical_support = 0
    dwell_a_physical_support = 0
    metrics: list[dict[str, Any]] = []

    for path in paths:
        plus_b, plus_b_cross = max_contiguous_dwell_seconds(
            path.event_ns, path.raw_ticks, t_ext, "above", path.end_ns
        )
        minus_b, minus_b_cross = max_contiguous_dwell_seconds(
            path.event_ns, -path.raw_ticks, t_ext, "above", path.end_ns
        )
        plus_a, plus_a_cross = max_contiguous_dwell_seconds(
            path.event_ns, path.raw_ticks, t_ret, "below", path.end_ns
        )
        minus_a, minus_a_cross = max_contiguous_dwell_seconds(
            path.event_ns, -path.raw_ticks, t_ret, "below", path.end_ns
        )

        if plus_b_cross:
            dwell_b_values.append(plus_b)
        if minus_b_cross:
            dwell_b_values.append(minus_b)
        if plus_a_cross:
            dwell_a_values.append(plus_a)
        if minus_a_cross:
            dwell_a_values.append(minus_a)
        dwell_b_physical_support += int(plus_b_cross or minus_b_cross)
        dwell_a_physical_support += int(plus_a_cross or minus_a_cross)

        metrics.append(
            {
                "fecha": path.fecha,
                "window_start_utc": pd.Timestamp(
                    path.start_ns, tz="UTC"
                ).isoformat(),
                "window_end_utc_exclusive": pd.Timestamp(
                    path.end_ns, tz="UTC"
                ).isoformat(),
                "p0": path.p0,
                "event_count": int(len(path.event_ns)),
                "max_abs_ticks": path.max_abs_ticks,
                "dwell_plus_ext_s": plus_b,
                "dwell_minus_ext_s": minus_b,
                "dwell_plus_ret_s": minus_a,
                "dwell_minus_ret_s": plus_a,
            }
        )

    if not dwell_b_values or not dwell_a_values:
        raise ValueError("No dwell observations for one or both thresholds")
    t_dwb = float(np.quantile(np.asarray(dwell_b_values), 0.50))
    t_dwa = float(np.quantile(np.asarray(dwell_a_values), 0.50))
    thresholds = {
        "T_push_ticks": t_push,
        "T_ext_ticks": t_ext,
        "T_ret_ticks": t_ret,
        "T_dwB_seconds": t_dwb,
        "T_dwA_seconds": t_dwa,
        "pseudo_window_count": int(len(paths)),
        "dwell_B_physical_crossing_windows": int(dwell_b_physical_support),
        "dwell_A_physical_crossing_windows": int(dwell_a_physical_support),
        "dwell_B_oriented_observations": int(len(dwell_b_values)),
        "dwell_A_oriented_observations": int(len(dwell_a_values)),
    }
    return thresholds, metrics


def _diagnostic_without_0829(
    metrics: pd.DataFrame,
) -> dict[str, Any]:
    starts = pd.to_datetime(metrics["window_start_utc"], utc=True)
    local = starts.dt.tz_convert("America/Chicago")
    keep = local.dt.strftime("%H:%M:%S").ge("08:30:00")
    values = metrics.loc[keep, "max_abs_ticks"].astype(float).to_numpy()
    if len(values) == 0:
        return {"windows": 0, "P50_max_abs_ticks": None, "P90_max_abs_ticks": None}
    return {
        "windows": int(len(values)),
        "P50_max_abs_ticks": float(np.quantile(values, 0.50)),
        "P90_max_abs_ticks": float(np.quantile(values, 0.90)),
    }


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
        / "20260724_007_CONVERGENCIA_FINAL_V4.md",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project / "contexto_codex_claude" / "joint_ab_v4",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    actual_hash = sha256_file(args.design)
    if actual_hash != DESIGN_HASH:
        raise RuntimeError(
            f"Frozen design hash mismatch: {actual_hash} != {DESIGN_HASH}"
        )

    manifest = pd.read_csv(args.manifest)
    audit = pd.read_csv(args.audit)
    required_manifest = {
        "fecha",
        "BurstId",
        "strategy_decision_timestamp_utc",
        "resolved_raw_symbol",
    }
    required_audit = {"fecha", "BurstId", "file_path"}
    if required_manifest - set(manifest.columns):
        raise ValueError("Manifest missing required columns")
    if required_audit - set(audit.columns):
        raise ValueError("Audit missing required columns")

    rows = manifest.merge(
        audit[["fecha", "BurstId", "file_path"]],
        on=["fecha", "BurstId"],
        how="left",
        validate="one_to_one",
    )
    rows["fecha"] = rows["fecha"].astype(str)
    rows = rows.loc[~rows["fecha"].isin(EXCLUDED_ROLLOVER_DATES)].copy()
    rows = rows.sort_values(["fecha", "BurstId"]).reset_index(drop=True)
    if args.limit is None and len(rows) != 98:
        raise ValueError(f"Expected 98 valid sessions, found {len(rows)}")
    if args.limit is not None:
        rows = rows.head(args.limit).copy()

    all_paths: list[WindowPath] = []
    all_window_quality: list[dict[str, Any]] = []
    session_quality: list[dict[str, Any]] = []

    for position, row in rows.iterrows():
        fecha = str(row["fecha"])
        path = Path(str(row["file_path"]))
        if not path.exists():
            raise FileNotFoundError(path)
        windows = window_grid(
            fecha, row["strategy_decision_timestamp_utc"]
        )
        start, end = calibration_bounds(
            fecha, row["strategy_decision_timestamp_utc"]
        )
        trades, event_quality = load_calibration_events(path, start, end)
        deterministic_repeat = True
        repeat_hash = ""
        if fecha in DOUBLE_DECODE_DATES:
            _, repeat_quality = load_calibration_events(path, start, end)
            repeat_hash = str(repeat_quality["physical_stream_sha256"])
            deterministic_repeat = (
                repeat_hash == event_quality["physical_stream_sha256"]
            )
            if not deterministic_repeat:
                raise ValueError(f"Non-deterministic DBN decoding: {path}")
        paths, quality = build_paths(fecha, trades, windows)
        all_paths.extend(paths)
        all_window_quality.extend(quality)
        session_quality.append(
            {
                "fecha": fecha,
                "BurstId": str(row["BurstId"]),
                "symbol": str(row["resolved_raw_symbol"]),
                "file_path": str(path),
                "planned_windows": int(len(windows)),
                "valid_windows": int(len(paths)),
                "invalid_windows": int(len(windows) - len(paths)),
                "last_sale_events_loaded": int(len(trades)),
                **event_quality,
                "double_decode_checked": fecha in DOUBLE_DECODE_DATES,
                "double_decode_sha256": repeat_hash,
                "double_decode_match": deterministic_repeat,
                "support_pass": len(paths) >= MIN_WINDOWS_PER_SESSION,
            }
        )
        print(
            f"[CAL {position + 1}/{len(rows)}] {fecha} "
            f"windows={len(paths)}/{len(windows)} "
            f"T-events={len(trades)}",
            flush=True,
        )

    thresholds, metrics = calibrate_thresholds(all_paths)
    metrics_frame = pd.DataFrame(metrics)
    session_frame = pd.DataFrame(session_quality)
    window_quality_frame = pd.DataFrame(all_window_quality)
    diagnostic = _diagnostic_without_0829(metrics_frame)

    gates = {
        "design_hash_match": actual_hash == DESIGN_HASH,
        "session_count_98": len(rows) == 98,
        "all_sessions_min_10_windows": bool(
            session_frame["support_pass"].all()
        ),
        "aggregate_min_1000_windows": (
            thresholds["pseudo_window_count"] >= MIN_WINDOWS_AGGREGATE
        ),
        "dwell_B_min_100_crossing_windows": (
            thresholds["dwell_B_physical_crossing_windows"]
            >= MIN_DWELL_CROSSING_WINDOWS
        ),
        "dwell_A_min_100_crossing_windows": (
            thresholds["dwell_A_physical_crossing_windows"]
            >= MIN_DWELL_CROSSING_WINDOWS
        ),
        "positive_price_thresholds": (
            thresholds["T_push_ticks"] > 0
            and thresholds["T_ext_ticks"] >= thresholds["T_push_ticks"]
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
                session_frame["double_decode_checked"], "double_decode_match"
            ].all()
        )
        and int(session_frame["double_decode_checked"].sum()) == 3,
    }
    calibration_pass = bool(all(gates.values()))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    session_path = args.output_dir / "AB_V4_CALIBRATION_SESSION_QUALITY.csv"
    window_quality_path = (
        args.output_dir / "AB_V4_CALIBRATION_WINDOW_QUALITY.csv"
    )
    metrics_path = args.output_dir / "AB_V4_PSEUDO_WINDOW_METRICS.csv"
    thresholds_path = args.output_dir / "AB_V4_FROZEN_THRESHOLDS.json"
    report_path = args.output_dir / "AB_V4_CALIBRATION_REPORT.md"
    session_frame.to_csv(session_path, index=False)
    window_quality_frame.to_csv(window_quality_path, index=False)
    metrics_frame.to_csv(metrics_path, index=False)

    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "design_path": str(args.design),
        "design_sha256": actual_hash,
        "calibration_pass": calibration_pass,
        "gates": gates,
        "thresholds": thresholds,
        "diagnostic_without_0829": diagnostic,
        "excluded_rollover_dates": sorted(EXCLUDED_ROLLOVER_DATES),
        "predictors_or_terminal_outcomes_read": False,
        "download_performed": False,
    }
    thresholds_path.write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    gate_lines = "\n".join(
        f"- `{name}`: {'PASS' if passed else 'FAIL'}"
        for name, passed in gates.items()
    )
    report = f"""# Calibración conjunta A/B V4

Estado: **{'PASS' if calibration_pass else 'FAIL'}**

## Integridad

- Diseño SHA-256: `{actual_hash}`
- Sesiones leídas: {len(rows)}
- Pseudo-ventanas válidas: {thresholds['pseudo_window_count']}
- No se leyeron predictores ni outcomes terminales.
- No se descargaron datos.

## Umbrales congelados

- T_push/T_ret: {thresholds['T_push_ticks']:.6f} ticks
- T_ext: {thresholds['T_ext_ticks']:.6f} ticks
- T_dwA: {thresholds['T_dwA_seconds']:.9f} s
- T_dwB: {thresholds['T_dwB_seconds']:.9f} s
- Soporte dwell A: {thresholds['dwell_A_physical_crossing_windows']} ventanas
- Soporte dwell B: {thresholds['dwell_B_physical_crossing_windows']} ventanas

## Gates

{gate_lines}

## Diagnóstico no vinculante sin 08:29–08:30 CT

- Ventanas: {diagnostic['windows']}
- P50 max|d|: {diagnostic['P50_max_abs_ticks']}
- P90 max|d|: {diagnostic['P90_max_abs_ticks']}

## Siguiente paso

{'Cotizar el tape postdecisión uniforme de 5.1 s para las 98 sesiones.' if calibration_pass else 'Detener: la calibración preregistrada no tiene soporte suficiente.'}
"""
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return 0 if calibration_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
