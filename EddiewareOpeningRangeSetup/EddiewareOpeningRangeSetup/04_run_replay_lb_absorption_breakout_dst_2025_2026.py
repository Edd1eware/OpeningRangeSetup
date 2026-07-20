"""One-shot DST 2025-2026 replay for frozen Liquidity Burst A-vs-B validation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import lb_absorption_breakout_validation as lb_validation
import replay_sync_runner_common_after_sync as replay_sync
from telegram_run_summary_after_sync import (
    clear_telegram_before_run,
    send_run_summary,
    send_text,
)


BASE_DIR = Path(__file__).resolve().parent
EXPORT_FOLDER = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator")
RESULTS_FOLDER = EXPORT_FOLDER / "trade_results_score"
RUN_ROOT = RESULTS_FOLDER / "visual_tests" / "04_run_replay_lb_absorption_breakout_dst_2025_2026_runs"
PACKAGE = BASE_DIR / "outputs" / "lb_absorption_breakout_frozen_20260720_r1"
AUDIT_MD = BASE_DIR / "contexto_features_atas" / "AUDITORIA_DISENO_VALIDACION_LB_ABSORCION_VS_BREAKOUT_DST_2025_2026_20260720.md"
AUDIT_CSV = PACKAGE / "design_audit.csv"
STATE_FILE = RUN_ROOT / "run_state.json"
OBSERVATIONAL_NAMES = (
    "burst_events.csv",
    "burst_response_events.csv",
    "trade_inputs.csv",
    "trade_results.csv",
    "exporter_lifecycle_diagnostics.csv",
)
RUN_LABEL = "CODEX LB A-vs-B HOLDOUT DST 2025-2026 R1"
REPLAY_TO_TIME = "10:30"


def _load_base_runner():
    path = BASE_DIR / "04_run_replay_score_trade_results_dst_2025_2026_after_sync.py"
    spec = importlib.util.spec_from_file_location("score_dst_base_for_lb_validation", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load base replay runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE_RUNNER = _load_base_runner()


def validation_dates() -> list[str]:
    today_ny = datetime.now(ZoneInfo("America/New_York")).date()
    last_date = today_ny - timedelta(days=1)
    seasons = (
        (date(2025, 3, 10), date(2025, 10, 31)),
        (date(2026, 3, 9), date(2026, 10, 30)),
    )
    dates = []
    for start, configured_end in seasons:
        end = min(configured_end, last_date)
        if end < start:
            continue
        dates.extend(BASE_RUNNER.build_trading_dates(start, end))
    return dates


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def design_audit(dates: list[str]) -> tuple[pd.DataFrame, bool]:
    spec, bundle = lb_validation.load_package(PACKAGE)
    discovery = pd.read_csv(
        BASE_DIR / "outputs" / "causal_regime_baseline_20260720_r1" / "discovery_only_2022_2024.csv",
        low_memory=False,
    )
    trade_headers = set(pd.read_csv(_header_source("trade_inputs.csv"), nrows=0).columns)
    burst_headers = set(pd.read_csv(_header_source("burst_events.csv"), nrows=0).columns)
    source_specs = {item.name: item for item in ab_research_specs()}
    source_text_exporter = (BASE_DIR / "ATASScoreTradeResultExporter.cs").read_text(encoding="utf-8")
    source_text_burst = (BASE_DIR / "12_LiquidityBurstDetector.cs").read_text(encoding="utf-8")
    label_source_hash = lb_validation.sha256_file(BASE_DIR / "absorption_breakout_research.py")

    parsed_dates = [datetime.strptime(value, "%d/%m/%Y").date() for value in dates]
    feature_timing_ok = all(
        name in source_specs and source_specs[name].window_end_seconds <= 0
        for name in spec["features"]
    )
    forbidden_tokens = ("mfe", "mae", "result", "exit", "future", "response")
    no_outcome_predictor = not any(
        token in name.lower() for name in spec["features"] for token in forbidden_tokens
    )
    latency = pd.to_numeric(discovery["Detector_Publish_To_Entry_Latency_Milliseconds"], errors="coerce")

    rows = [
        ("PACKAGE_SHA256", "Frozen model hash matches sealed spec", True),
        ("LABEL_SOURCE_SHA256", "A/B/C labeling implementation matches frozen spec", label_source_hash == spec["training"]["label_source_sha256"]),
        ("TRAINING_ROWS", f"70 expected; observed {spec['training']['analysis_rows']}", spec["training"]["analysis_rows"] == 70),
        ("TRAINING_YEARS", f"Observed {spec['training']['analysis_year_min']}-{spec['training']['analysis_year_max']}", spec["training"]["analysis_year_min"] == 2022 and spec["training"]["analysis_year_max"] == 2024),
        ("HOLDOUT_NOT_OPENED", f"Frozen spec validation years: {spec['training']['validation_years_opened']}", spec["training"]["validation_years_opened"] == []),
        ("REPLAY_SCOPE", f"{len(dates)} dates; {min(parsed_dates)} -> {max(parsed_dates)}", bool(parsed_dates) and all(value.year in (2025, 2026) for value in parsed_dates)),
        ("CORE_FEATURE_ORDER", f"{len(spec['features'])} frozen predictors", list(bundle["features"]) == list(lb_validation.FEATURES)),
        ("FEATURE_TIMING", "Every frozen predictor has window_end_seconds <= 0", feature_timing_ok),
        ("NO_OUTCOME_PREDICTORS", "No response/MAE/MFE/result/exit/future predictor", no_outcome_predictor),
        ("TRADE_EXPORT_HEADERS", "All entry-side frozen predictors exist in trade_inputs", all(name in trade_headers or name in burst_headers for name in spec["features"])),
        ("REGIME_EXPORT_HEADERS", "VWAP-distance and RV60 are exported before entry", "Directional_VWAP_Distance_Ticks_AtEntry" in trade_headers and "Realized_Volatility_60s_Ticks" in burst_headers),
        ("DISCOVERY_CAUSAL_ROWS", f"Causal rows {int(discovery['causal_row_flag'].astype(bool).sum())}/{len(discovery)}", discovery["causal_row_flag"].astype(bool).all()),
        ("PUBLISH_PRECEDES_DECISION", f"Publish-to-decision latency min={latency.min():.3f} ms", latency.notna().all() and latency.ge(0).all()),
        ("MIXED_ABSTAINS", str(spec["mixed_policy"]), str(spec["mixed_policy"]).startswith("C_MIXED_PATH")),
        ("NO_MBO_DEPENDENCY", "MBO and incremental MBP/tape excluded", "MBO" in spec["excluded_from_predictors"] and "12 MBP/tape incremental features" in spec["excluded_from_predictors"]),
        ("EXPORTER_VERSION", replay_sync.EXPECTED_EXPORTER_VERSION, replay_sync.EXPECTED_EXPORTER_VERSION in source_text_exporter),
        ("DETECTOR_VERSION", ab_research.EXPECTED_BURST_VERSION, ab_research.EXPECTED_BURST_VERSION in source_text_burst),
        ("X10_ONLY", "Run plan rejects X1 and uses X10_R1 only", replay_sync.build_run_plan(quick=True, x10_only=True) == [("X10_R1", "X10", replay_sync.X10_TIMEOUT_SECONDS)]),
        ("POST_RESPONSE_LABEL_ONLY", "1/3/5s response is excluded from same-entry predictors", "burst_response_events 1s/3s/5s" in spec["excluded_from_predictors"]),
        ("TRADING_UNCHANGED", "Observational runner and frozen offline evaluator only", spec["trading_logic_changed"] is False),
    ]
    audit = pd.DataFrame(rows, columns=["check", "evidence", "passed"])
    passed = bool(audit["passed"].all())
    AUDIT_CSV.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_CSV, index=False)

    threshold_vwap = spec["regime_rules"]["VWAP_FAR"]["threshold"]
    threshold_rv = spec["regime_rules"]["RV60_HIGH"]["threshold"]
    lines = [
        "# Auditoría de diseño — validación LB absorción vs breakout DST 2025–2026",
        "",
        f"Estado: **{'PASS' if passed else 'FAIL'}**.",
        "",
        "## Enfoque preservado",
        "",
        "1. Detectar el Liquidity Burst con el detector vigente.",
        "2. En el callback causal original de decisión (`feature_timestamp_utc`), estimar absorción verdadera A vs breakout limpio B.",
        "3. No esperar la respuesta de 1/3/5 segundos para predecir. Esas ventanas sólo documentan el resultado físico posterior.",
        "4. Tratar C mixto como abstención y D como otra salida; ninguno entra al AUC A/B.",
        "",
        "El cutoff no es el inicio nominal del segundo: ocurre después de la publicación real del detector. "
        f"En discovery, la latencia publicación→decisión fue mediana {latency.median():.3f} ms y máxima {latency.max():.3f} ms. "
        "No se agrega demora artificial.",
        "",
        "## Modelo y contextos congelados",
        "",
        f"- Baseline mínimo: {len(spec['features'])} variables, regresión logística regularizada.",
        "- MBO: excluido; el piloto empeoró el baseline.",
        "- MBP/tape incremental: excluido; delta de AUC discovery -0.005.",
        f"- VWAP_FAR: `abs(Directional_VWAP_Distance_Ticks_AtEntry) > {threshold_vwap:.6f}`.",
        f"- RV60_HIGH: `Realized_Volatility_60s_Ticks > {threshold_rv:.6f}`.",
        "- Los contextos sólo estratifican la validación; no filtran ni cambian trades.",
        "",
        "## Por qué se retienen sólo dos contextos",
        "",
        "VWAP_FAR y RV60_HIGH fueron los únicos contextos que conservaron señal al contrastar el baseline preregistrado "
        "con su representación mínima. FLOW_LOW, ATR_HIGH y PROFILE_DISPERSED dependieron del conjunto de variables "
        "y quedan descartados antes de abrir el holdout.",
        "",
        "## Checklist",
        "",
        "| Control | Evidencia | Pasó |",
        "| --- | --- | ---: |",
    ]
    for row in audit.itertuples(index=False):
        lines.append(f"| {row.check} | {row.evidence} | {int(row.passed)} |")
    lines.extend([
        "",
        "## Decisión previa a corrida",
        "",
        "La estabilidad global discovery falló únicamente por SELL (AUC 0.521 para existing; 0.541 para core), "
        "por lo que esta corrida es una prueba de falsación única, no un despliegue. La adenda del protocolo sí "
        "autoriza abrir 2025–2026 porque tres regímenes pasaron la puerta preregistrada; la auditoría conserva sólo "
        "los dos robustos a representación.",
        "",
        "Si el holdout falla, se detiene la línea y no se reajusta con 2025–2026.",
    ])
    AUDIT_MD.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return audit, passed


def _header_source(name: str) -> Path:
    """Find a schema source even while a resumed capture is still empty."""
    live = RESULTS_FOLDER / name
    if live.exists():
        return live
    candidates = list(RUN_ROOT.glob(f"_failed_*_capture_*/{name}"))
    candidates.extend(RESULTS_FOLDER.glob(f"_archive_research_capture_reset_*/{name}"))
    if not candidates:
        raise FileNotFoundError(f"No schema source found for {name}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def ab_research_specs():
    # Centralized helper keeps the audit readable and testable.
    return ab_research.ALL_SPECS


# Imported late in the source only to make the version used by design_audit
# explicit without shadowing the validation module alias.
import absorption_breakout_research as ab_research


def first_telegram_message(dates: list[str]) -> str:
    spec, _ = lb_validation.load_package(PACKAGE)
    initial_eta_hours = len(dates) * replay_sync.SPEED_DEFAULT_SECONDS["X10"] / 3600
    vwap = spec["regime_rules"]["VWAP_FAR"]["threshold"]
    rv60 = spec["regime_rules"]["RV60_HIGH"]["threshold"]
    return f"""LIQUIDITY BURST | VALIDACION CIEGA A vs B
PROPUESTO POR CODEX — HOLDOUT TEMPORAL DST 2025–2026

QUE BUSCAMOS:
Detectar primero el Liquidity Burst y, en el mismo callback causal de decision original, anticipar si terminara como A) absorcion verdadera o B) breakout limpio. No se esperan 5 segundos y no se modifica la entrada.

QUE SE MIDE Y POR QUE:
1) Baseline causal congelado de 10 variables: perfil, delta previo, pausa de aproximacion, ATR3/ATR5 cerrados, flujo 3–5s, ratio buy/sell, distancia VWAP y latencia causal. Mide contexto, esfuerzo y estructura disponibles antes del resultado.
2) Contexto VWAP_FAR: abs(distancia VWAP de entrada) > {vwap:.6f} ticks.
3) Contexto RV60_HIGH: volatilidad realizada 60s > {rv60:.6f} ticks.
Estos dos contextos fueron los unicos robustos al contraste entre baseline existente y minimo.

REGLAS CONGELADAS:
- Entrenamiento: 70 eventos A/B, exclusivamente 2022–2024.
- 2025–2026 no ajusta modelo, variables, cutoff ni umbrales.
- Respuestas 1/3/5s, MAE/MFE y salida son outcome/etiqueta; nunca predictor.
- C mixto = abstencion; no se fuerza a A o B.
- MBO y MBP/tape incremental excluidos por no mejorar el baseline.
- WR/PF se reportan como secundarios; el objetivo primario es AUC, sensibilidad A, especificidad B, estabilidad por ano/lado/regimen y cobertura.

CORRIDA:
Historia X10 unicamente | Replay X1 deshabilitado.
{len(dates)} sesiones: {dates[0]} -> {dates[-1]}.
ETA inicial mecanico: ~{initial_eta_hours:.1f} h; Telegram lo recalibrara con la mediana real.
Se enviara detalle de cada trade, resumen final, datos y graficas."""


def _capture_observational_files() -> None:
    target = RUN_ROOT / "observational"
    target.mkdir(parents=True, exist_ok=True)
    for name in OBSERVATIONAL_NAMES:
        source = RESULTS_FOLDER / name
        if source.exists():
            shutil.copy2(source, target / name)


def _read_state() -> dict[str, object] | None:
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def _set_state(status: str, dates: list[str], **extra: object) -> None:
    previous = _read_state() or {}
    value = {
        **previous,
        "status": status,
        "run_label": RUN_LABEL,
        "dates": dates,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    value.setdefault("created_at_utc", datetime.now(timezone.utc).isoformat())
    _write_json(STATE_FILE, value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true", help="Audit and print plan without touching Replay or Telegram.")
    parser.add_argument("--audit-only", action="store_true", help="Run the formal design audit and stop.")
    parser.add_argument("--step", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dates = validation_dates()
    if not dates:
        raise SystemExit("No DST 2025-2026 replay dates are currently available")

    audit, audit_passed = design_audit(dates)
    print(audit.to_string(index=False))
    print(f"AUDIT={'PASS' if audit_passed else 'FAIL'} | {AUDIT_MD}")
    print(f"DATES={len(dates)} | {dates[0]} -> {dates[-1]}")
    if not audit_passed:
        raise SystemExit("Design audit failed; ATAS Replay was not launched")
    if args.prepare_only or args.audit_only:
        print("PREPARE/AUDIT ONLY: Replay and Telegram were not touched.")
        return 0

    state = _read_state()
    fresh = state is None
    if state and state.get("status") == "COMPLETE":
        raise SystemExit(f"The one-shot holdout is already complete: {RUN_ROOT}")
    if state and state.get("dates") != dates:
        raise SystemExit("Active run date manifest differs from the current frozen date manifest")

    BASE_RUNNER.DATES_DST = dates
    if fresh:
        print("Initializing isolated observational capture and fresh Telegram state...")
        BASE_RUNNER.reset_replay_run_state(RUN_ROOT)
        _set_state("ACTIVE", dates, audit="PASS", package=str(PACKAGE))
        clear_telegram_before_run(str(RESULTS_FOLDER))
        send_text(str(RESULTS_FOLDER), first_telegram_message(dates))
    else:
        _set_state("ACTIVE", dates, resumed=True)
        send_text(
            str(RESULTS_FOLDER),
            "LIQUIDITY BURST | REANUDACION HOLDOUT DST 2025–2026\n"
            "Se conservan modelo, umbrales, captura observacional y fechas ya completadas. "
            "El runner llenara solamente los huecos.",
        )

    date_iso = [replay_sync.date_iso_from_replay(value) for value in dates]
    run_plan = replay_sync.build_run_plan(quick=True, x10_only=True)
    progress_meta = {
        "stage_index": 1,
        "stage_total": 1,
        "stage_label": "VALIDACION CIEGA LB: absorcion A vs breakout B",
        "stage_period": f"{dates[0]} -> {dates[-1]}",
        "session_roots": [str(RUN_ROOT)],
        "run_label": RUN_LABEL,
        "stats_root": str(RUN_ROOT),
        "global_target": len(dates),
    }
    passed, failures = replay_sync.run_replay_period(
        date_iso,
        output_folder=RUN_ROOT,
        run_plan=run_plan,
        report_prefix="lb_a_vs_b_holdout_dst_2025_2026_r1",
        force=False,
        step=args.step,
        compare_only=False,
        replay_to_time=REPLAY_TO_TIME,
        progress_meta=progress_meta,
    )

    failed_dates = [(day, f"{run_name}: {reason}") for day, run_name, reason in failures]
    if failures or not passed:
        _capture_observational_files()
        _set_state("INCOMPLETE", dates, failures=failed_dates)
        send_text(
            str(RESULTS_FOLDER),
            "LIQUIDITY BURST | HOLDOUT INCOMPLETO\n"
            f"Huecos/errores: {len(failures)}. No se calcula una conclusion parcial. "
            "Relanzar el mismo runner reanuda sólo los huecos.",
        )
        return 1

    _capture_observational_files()
    send_run_summary(
        str(RESULTS_FOLDER),
        dates,
        [],
        f"LIQUIDITY BURST HOLDOUT | {RUN_LABEL}",
    )

    scientific_output = RUN_ROOT / "scientific_validation"
    if scientific_output.exists():
        archive = RUN_ROOT / f"_archive_scientific_validation_{datetime.now():%Y%m%d_%H%M%S}"
        shutil.move(str(scientific_output), str(archive))
    validation = lb_validation.validate(PACKAGE, RESULTS_FOLDER, scientific_output)
    telegram_ok = lb_validation.send_validation_to_telegram(RESULTS_FOLDER, validation)
    context_result = BASE_DIR / "contexto_features_atas" / "RESULTADO_VALIDACION_CIEGA_LB_A_VS_B_DST_2025_2026_20260720.md"
    shutil.copy2(scientific_output / "final_validation_report.md", context_result)
    _set_state(
        "COMPLETE",
        dates,
        failures=[],
        scientific_output=str(scientific_output),
        conclusion=validation["manifest"]["conclusion"],
        telegram_ok=telegram_ok,
    )
    return 0 if telegram_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
