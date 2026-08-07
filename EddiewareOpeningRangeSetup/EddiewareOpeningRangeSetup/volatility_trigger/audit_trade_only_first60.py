from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from run_research import CONFIG_PATH, load_session, stage_dates  # noqa: E402
from src.vt_core import (  # noqa: E402
    causalize_trade_timestamps,
    detect_liquidity_bursts,
    load_config,
    session_bounds,
    ticks_iso,
)


OUTPUT = ROOT / "artifacts" / "data_coverage"
COVERAGE_PATH = OUTPUT / "depth_coverage_manifest.csv"
TABLE_PATH = OUTPUT / "trade_only_first60.csv"
SUMMARY_PATH = OUTPUT / "trade_only_first60_summary.json"
REPORT_PATH = OUTPUT / "trade_only_first60_report.md"
MANIFEST_PATH = OUTPUT / "trade_only_first60_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def minimum(values: list[float]) -> float | None:
    return float(min(values)) if values else None


def maximum(values: list[float]) -> float | None:
    return float(max(values)) if values else None


def audit_trade_session(session_date_text: str) -> dict[str, object]:
    config = load_config(CONFIG_PATH)
    session_date = date.fromisoformat(session_date_text)
    try:
        context, raw_trades, source = load_session(
            session_date,
            Path(config["cache_root"]),
        )
        trades, timestamp_qc = causalize_trade_timestamps(
            raw_trades,
            config["timestamp_qc"],
        )
        bursts = detect_liquidity_bursts(
            trades,
            session_date,
            config["detector"],
        )
        bounds = session_bounds(session_date)
        directional_delta_1s = [
            float(burst.direction * burst.delta_1s) for burst in bursts
        ]
        directional_delta_change = [
            float(burst.direction * burst.delta_change_1s)
            for burst in bursts
        ]
        directional_zscore = [
            float(burst.direction * burst.delta_change_zscore)
            for burst in bursts
        ]
        directional_cumulative = [
            float(burst.direction * burst.cumulative_delta)
            for burst in bursts
        ]
        return {
            "session_date": session_date_text,
            "trade_status": "PASS",
            "trade_reason": None,
            "trade_source": str(source),
            "trade_source_bytes": int(source.stat().st_size),
            "trade_tick_size": float(context.tick_size),
            "trade_lot_size": float(context.lot_size),
            "trade_rows": int(len(trades)),
            "trade_first_ticks": int(trades[0]["ticks"]),
            "trade_last_ticks": int(trades[-1]["ticks"]),
            "trade_first_utc": ticks_iso(int(trades[0]["ticks"])),
            "trade_last_utc": ticks_iso(int(trades[-1]["ticks"])),
            "detection_window_trade_coverage": bool(
                int(trades[0]["ticks"]) <= bounds["detection_start"]
                and int(trades[-1]["ticks"]) >= bounds["detection_end"]
            ),
            "trade_only_liquidity_bursts": int(len(bursts)),
            "minimum_directional_delta_1s": minimum(
                directional_delta_1s
            ),
            "minimum_directional_delta_change_1s": minimum(
                directional_delta_change
            ),
            "minimum_directional_zscore": minimum(
                directional_zscore
            ),
            "minimum_delta_percentile": minimum(
                [float(burst.delta_percentile) for burst in bursts]
            ),
            "minimum_trades_per_second": minimum(
                [float(burst.trades_per_second) for burst in bursts]
            ),
            "minimum_contracts_per_second": minimum(
                [float(burst.contracts_per_second) for burst in bursts]
            ),
            "minimum_directional_cumulative_delta": minimum(
                directional_cumulative
            ),
            "maximum_abs_delta_1s": maximum(
                [abs(float(burst.delta_1s)) for burst in bursts]
            ),
            "maximum_abs_delta_change_1s": maximum(
                [abs(float(burst.delta_change_1s)) for burst in bursts]
            ),
            "maximum_abs_zscore": maximum(
                [abs(float(burst.delta_change_zscore)) for burst in bursts]
            ),
            "raw_timestamp_backtracks": int(
                timestamp_qc["raw_timestamp_backtracks"]
            ),
            "largest_raw_backtrack_ms": float(
                timestamp_qc["largest_raw_backtrack_ms"]
            ),
            "timestamps_repaired": int(
                timestamp_qc["timestamps_repaired"]
            ),
        }
    except Exception as exc:
        return {
            "session_date": session_date_text,
            "trade_status": "EXCLUDED",
            "trade_reason": f"{type(exc).__name__}: {exc}",
            "trade_source": None,
            "trade_source_bytes": None,
            "trade_tick_size": None,
            "trade_lot_size": None,
            "trade_rows": None,
            "trade_first_ticks": None,
            "trade_last_ticks": None,
            "trade_first_utc": None,
            "trade_last_utc": None,
            "detection_window_trade_coverage": False,
            "trade_only_liquidity_bursts": None,
            "minimum_directional_delta_1s": None,
            "minimum_directional_delta_change_1s": None,
            "minimum_directional_zscore": None,
            "minimum_delta_percentile": None,
            "minimum_trades_per_second": None,
            "minimum_contracts_per_second": None,
            "minimum_directional_cumulative_delta": None,
            "maximum_abs_delta_1s": None,
            "maximum_abs_delta_change_1s": None,
            "maximum_abs_zscore": None,
            "raw_timestamp_backtracks": None,
            "largest_raw_backtrack_ms": None,
            "timestamps_repaired": None,
        }


def report_text(summary: dict[str, object]) -> str:
    return f"""# Auditoría trade-only de las primeras 60 fechas

Fecha: 2026-07-27

Estado: `MECHANICAL_DESCRIPTIVE_AUDIT_ONLY`

Esta corrida no calcula régimen, outcomes, features, modelos, bootstrap ni PnL.
Su resultado no puede modificar ningún umbral.

## Definición literal del gate LB

El detector requiere, para BUY o su espejo SELL:

```text
baseline_ready: history >= 30 s
direction * Delta1s > 100
direction * DeltaChange1s > 75
direction * DeltaChangeZScore >= 2.5
DeltaPercentile >= 0.95
TradesPerSecond >= 5
ContractsPerSecond >= 50
direction * CumulativeDelta3s >= 150
RequirePriceVelocity = false
detection window = 09:30:00..16:00:00 NY
same-side cooldown = 5 s
```

## Resultado

- fechas: {summary["min_session_date"]} a {summary["max_session_date"]};
- fechas intentadas: {summary["sessions_attempted"]};
- sesiones trade legibles: {summary["trade_sessions_pass"]};
- sesiones trade excluidas: {summary["trade_sessions_excluded"]};
- sesiones legibles con al menos un LB:
  {summary["trade_sessions_with_liquidity_burst"]};
- LB trade-only: {summary["trade_only_liquidity_bursts"]};
- mínimo/máximo por sesión legible:
  {summary["minimum_lbs_per_readable_session"]}/
  {summary["maximum_lbs_per_readable_session"]};
- sesiones con depth/MID válido: {summary["depth_present_sessions"]};
- referencias MID válidas posibles: 0.

El `0 LB válidos` del progreso anterior no significaba que el detector no
disparara. El `except Exception` reemplazó el conteo por cero después de fallar
depth. El defecto es de datos/instrumentación: no hay depth utilizable en
ninguna de las primeras 60 fechas.

La tabla completa está en `trade_only_first60.csv`.

`INFORMATION_STATUS=TRADE_ONLY_FIRST60_MECHANICAL_AUDIT_COMPLETE`
"""


def main() -> int:
    if not COVERAGE_PATH.is_file():
        raise FileNotFoundError(
            "run audit_data_coverage.py before this audit"
        )
    config = load_config(CONFIG_PATH)
    dates = stage_dates("discovery", config)[:60]
    date_texts = [value.isoformat() for value in dates]
    with ProcessPoolExecutor(max_workers=4) as pool:
        trade_records = list(pool.map(audit_trade_session, date_texts))

    trade_frame = pd.DataFrame(trade_records)
    coverage = pd.read_csv(COVERAGE_PATH)
    depth_columns = [
        "ordinal",
        "session_date",
        "source_date",
        "depth_status",
        "depth_path",
        "depth_bytes",
        "depth_template_id",
        "depth_tick_size",
        "depth_lot_size",
        "depth_has_blocks",
    ]
    frame = coverage.iloc[:60][depth_columns].merge(
        trade_frame,
        on="session_date",
        how="left",
        validate="one_to_one",
    )
    frame["depth_message_count"] = frame["depth_has_blocks"].map(
        lambda value: None if bool(value) else 0
    )
    frame["opening_range_used_by_lb_detector"] = False
    frame["valid_reference_bursts"] = 0
    frame["target_status"] = frame.apply(
        lambda row: (
            "EXCLUDED_TRADE_DATA"
            if row["trade_status"] != "PASS"
            else "EXCLUDED_NO_DEPTH_REFERENCE"
        ),
        axis=1,
    )
    readable = frame[frame["trade_status"].eq("PASS")]
    lb_counts = readable["trade_only_liquidity_bursts"].astype(int)
    summary = {
        "audit_id": "POST_LB_TRADE_ONLY_FIRST60_V1",
        "status": "MECHANICAL_DESCRIPTIVE_AUDIT_COMPLETE",
        "outcome_blind": True,
        "regime_labels_opened": False,
        "features_opened": False,
        "models_opened": False,
        "sessions_attempted": int(len(frame)),
        "min_session_date": str(frame["session_date"].min()),
        "max_session_date": str(frame["session_date"].max()),
        "trade_sessions_pass": int(len(readable)),
        "trade_sessions_excluded": int(
            len(frame) - len(readable)
        ),
        "trade_sessions_with_liquidity_burst": int(
            (lb_counts > 0).sum()
        ),
        "trade_only_liquidity_bursts": int(lb_counts.sum()),
        "minimum_lbs_per_readable_session": int(lb_counts.min()),
        "maximum_lbs_per_readable_session": int(lb_counts.max()),
        "zero_lb_readable_sessions": int((lb_counts == 0).sum()),
        "depth_present_sessions": int(
            frame["depth_status"].eq("DATA_PRESENT").sum()
        ),
        "depth_header_only_zero_scale_sessions": int(
            frame["depth_status"].eq(
                "HEADER_ONLY_ZERO_SCALE"
            ).sum()
        ),
        "depth_missing_sessions": int(
            frame["depth_status"].eq("MISSING").sum()
        ),
        "gate_thresholds": {
            "history_seconds": 300,
            "min_baseline_seconds": 30,
            "delta_change_zscore_threshold": 2.5,
            "delta_percentile_threshold": 0.95,
            "cumulative_window_seconds": 3,
            "min_abs_delta_1s_strict": 100,
            "min_abs_delta_change_1s_strict": 75,
            "min_abs_cumulative_delta": 150,
            "min_trades_per_second": 5,
            "min_contracts_per_second": 50,
            "require_price_velocity": False,
            "cooldown_seconds": 5,
        },
    }
    if (
        summary["trade_only_liquidity_bursts"] != 1868
        or summary["trade_sessions_pass"] != 57
        or summary["depth_present_sessions"] != 0
    ):
        raise AssertionError(
            "formal audit does not reproduce the observed diagnostic"
        )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(TABLE_PATH, index=False, lineterminator="\n")
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    REPORT_PATH.write_text(report_text(summary), encoding="utf-8")
    artifacts = (TABLE_PATH, SUMMARY_PATH, REPORT_PATH)
    manifest = {
        "audit_id": summary["audit_id"],
        "outcome_blind": True,
        "files": {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in artifacts
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, allow_nan=False))
    print(
        json.dumps(
            {
                "table_sha256": sha256_file(TABLE_PATH),
                "report_sha256": sha256_file(REPORT_PATH),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
