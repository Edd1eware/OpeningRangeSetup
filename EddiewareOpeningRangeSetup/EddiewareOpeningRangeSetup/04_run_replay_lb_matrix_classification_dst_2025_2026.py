"""R5 replay: post-LB transition matrices, causal patterns and A/B classification."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import lb_matrix_classification_research as matrix_research
from lb_matrix_classification_monitor import calculate, format_status, update_status_file
import replay_sync_runner_common_after_sync as replay_sync
from telegram_run_summary_after_sync import (
    clear_telegram_before_run,
    send_photo,
    send_run_summary,
    send_text,
)


BASE_DIR = Path(__file__).resolve().parent
EXPORT_FOLDER = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator")
RESULTS_FOLDER = EXPORT_FOLDER / "trade_results_score"
RUN_ROOT = RESULTS_FOLDER / "visual_tests" / "04_run_replay_lb_matrix_classification_r5_dst_2025_2026_runs"
STATE_FILE = RUN_ROOT / "run_state.json"
AUDIT_MD = BASE_DIR / "contexto_features_atas" / "AUDITORIA_DISENO_MATRIX_CLASSIFICATION_TEST_R5_20260722.md"
AUDIT_CSV = BASE_DIR / "contexto_features_atas" / "AUDITORIA_DISENO_MATRIX_CLASSIFICATION_TEST_R5_20260722.csv"
PROTOCOL_MD = BASE_DIR / "contexto_features_atas" / "PROTOCOLO_MATRIX_CLASSIFICATION_POST_LB_R5_20260722.md"
RUN_LABEL = "MATRIX CLASSIFICATION TEST"
FROZEN_LAST_DATE = date(2026, 7, 17)
REPLAY_TO_TIME = "10:30"
TECHNICAL_DATES = ["10/03/2025", "18/03/2025", "27/03/2025", "03/04/2025"]
OBSERVATIONAL_NAMES = (
    "burst_events.csv", "burst_response_events.csv", "burst_causal_timeline.csv",
    "trade_inputs.csv", "trade_results.csv", "exporter_lifecycle_diagnostics.csv",
)


def _load_base_runner():
    path = BASE_DIR / "04_run_replay_score_trade_results_dst_2025_2026_after_sync.py"
    spec = importlib.util.spec_from_file_location("score_dst_base_for_matrix", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load base replay runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE_RUNNER = _load_base_runner()


def replay_dates() -> list[str]:
    last_date = min(datetime.now(ZoneInfo("America/New_York")).date() - timedelta(days=1), FROZEN_LAST_DATE)
    seasons = (
        (date(2025, 3, 10), date(2025, 10, 31)),
        (date(2026, 3, 9), date(2026, 10, 30)),
    )
    values: list[str] = []
    for start, configured_end in seasons:
        end = min(configured_end, last_date)
        if end >= start:
            values.extend(BASE_RUNNER.build_trading_dates(start, end))
    return values


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def _read_state() -> dict[str, object] | None:
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def _set_state(status: str, dates: list[str], **extra: object) -> None:
    previous = _read_state() or {}
    state = {
        **previous,
        "status": status,
        "run_label": RUN_LABEL,
        "dates": dates,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    state.setdefault("created_at_utc", datetime.now(timezone.utc).isoformat())
    _write_json(STATE_FILE, state)


def _capture_observational_files() -> None:
    target = RUN_ROOT / "observational"
    target.mkdir(parents=True, exist_ok=True)
    for name in OBSERVATIONAL_NAMES:
        source = RESULTS_FOLDER / name
        if source.exists():
            shutil.copy2(source, target / name)


def design_audit(dates: list[str]) -> tuple[pd.DataFrame, bool]:
    detector = (BASE_DIR / "12_LiquidityBurstDetector.cs").read_text(encoding="utf-8")
    analysis = (BASE_DIR / "lb_matrix_classification_research.py").read_text(encoding="utf-8")
    common = (BASE_DIR / "replay_sync_runner_common_after_sync.py").read_text(encoding="utf-8")
    exporter = (BASE_DIR / "ATASScoreTradeResultExporter.cs").read_text(encoding="utf-8")
    signal_bus = (BASE_DIR / "12_B_LiquidityBurstSignalBus.cs").read_text(encoding="utf-8")
    workspace_path = Path.home() / "AppData" / "Roaming" / "ATAS" / "Workspaces_v3" / "Eddieware_workspace.ws"
    workspace = workspace_path.read_text(encoding="utf-8") if workspace_path.exists() else ""
    built_dll = BASE_DIR / "bin" / "Debug" / "net10.0" / "EddiewareOpeningRangeSetup.dll"
    installed_dll = Path.home() / "AppData" / "Roaming" / "ATAS" / "Indicators" / "EddiewareOpeningRangeSetup.dll"
    parsed = [datetime.strptime(value, "%d/%m/%Y").date() for value in dates]
    state_owned = not STATE_FILE.exists()
    if STATE_FILE.exists():
        try:
            state_owned = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("run_label") == RUN_LABEL
        except (OSError, json.JSONDecodeError):
            state_owned = False
    checks = [
        ("DETECTOR_VERSION", matrix_research.EXPECTED_VERSION, matrix_research.EXPECTED_VERSION in detector),
        ("POST_LB_EXPORT_BOUND", "start=max(configured,t_burst)", "snapshot.TimestampUtc > configuredStartTimestampUtc" in detector),
        ("DECISION_EXPORT_BOUND", "event<=t_decision", "item.CausalTimestampUtc <= decisionTimestampUtc" in detector),
        ("ANALYSIS_CAUSAL_BOUND", "t_burst<=event<=t_decision", "ge(timeline[\"Burst_Timestamp_UTC\"])" in analysis and "le(timeline[\"Decision_Timestamp_UTC\"])" in analysis),
        ("PHYSICAL_100MS_STATES", "100 ms macro states", "BIN_MILLISECONDS = 100" in analysis),
        ("PATTERN_MINING", "bigrams/trigrams/length4 + bifurcations", "for length in (2, 3, 4)" in analysis and "_bifurcation_matrix" in analysis),
        ("OUTCOMES_AFTER_FEATURES", "labels joined after state construction", analysis.index("states, sequences = build_macro_states(post)") < analysis.index("labeled, outcome_audit = join_labels(results, sequences)")),
        ("NO_OUTCOME_IN_TRADING", "matrix files never enter exporter/signal bus", "matrix_classification" not in exporter.lower() and "matrix_classification" not in signal_bus.lower()),
        ("TEMPORAL_VALIDATION", "discovery/validation/holdout", all(value in analysis for value in ('"discovery"', '"validation"', '"holdout"'))),
        ("PERMUTATION_AND_CI", "permutation + bootstrap CI", "_permutation_p_value" in analysis and "_bootstrap_balanced_accuracy" in analysis),
        ("ABSTENTION", "NO_DECISION at frozen confidence", "ABSTENTION_CONFIDENCE = 0.65" in analysis),
        ("TELEGRAM_LABEL", RUN_LABEL, "matrix_classification" in common and RUN_LABEL in first_telegram_message(dates)),
        ("WORKSPACE_DETECTOR", "LiquidityBurstDetector attached", "ATAS.Indicators.LiquidityBurstDetector" in workspace),
        ("DLL_INSTALLED", "installed DLL equals current build", built_dll.exists() and installed_dll.exists() and _sha256(built_dll) == _sha256(installed_dll)),
        ("X10_ONLY", "X10_R1 only", replay_sync.build_run_plan(quick=True, x10_only=True) == [("X10_R1", "X10", replay_sync.X10_TIMEOUT_SECONDS)]),
        ("DST_SCOPE", f"{len(dates)} dates {min(parsed)}->{max(parsed)}", len(dates) == 256 and all(value.year in (2025, 2026) for value in parsed)),
        ("TECHNICAL_GATE", f"known burst dates={TECHNICAL_DATES}", all(value in dates for value in TECHNICAL_DATES)),
        ("ISOLATED_ROOT", "R5 root new/owned", state_owned and (not RUN_ROOT.exists() or STATE_FILE.exists())),
        ("PROTOCOL_PRESENT", str(PROTOCOL_MD), PROTOCOL_MD.exists()),
    ]
    audit = pd.DataFrame(checks, columns=["check", "evidence", "passed"])
    passed = bool(audit["passed"].all())
    AUDIT_CSV.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_CSV, index=False)
    lines = [
        "# Auditoría de diseño — MATRIX CLASSIFICATION TEST R5",
        "",
        f"Estado: **{'PASS' if passed else 'FAIL'}**.",
        "",
        "La ruta predictora comienza en LB y termina en t_decision. El outcome A/B/C se une después.",
        "",
        "| Control | Evidencia | Pasó |", "| --- | --- | ---: |",
    ]
    for row in audit.itertuples(index=False):
        lines.append(f"| {row.check} | {row.evidence} | {int(row.passed)} |")
    AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return audit, passed


def first_telegram_message(dates: list[str]) -> str:
    return f"""MATRIX CLASSIFICATION TEST
PROPUESTO POR CODEX — DST 2025–2026

OBJETIVO:
Detectar el Liquidity Burst y leer los patrones que aparecen DESPUES del burst para anticipar A) ABSORCION LIMPIA o B) BREAKOUT/CONTINUACION LIMPIA. C) TRADE VARIABLE se conserva como diagnostico/abstencion.

QUE SE MIDE Y POR QUE:
- Ruta causal t_burst -> t_decision, nunca el lookback previo como secuencia.
- Estados fisicos cada 100 ms: progreso eficiente, stall, contraflujo, retiro/consumo, refill y refill persistente delante/detras.
- Orden, transiciones, bifurcaciones, duracion, intensidad tape/DOM, persistencia, ciclos y lead time explotable.
- Matrices A, B y contraste A-B; bigramas, trigramas y rutas de longitud 4.
- Validacion temporal, permutacion, calibracion y NO_DECISION cuando la evidencia sea ambigua.

CONTROL CAUSAL:
Solo eventos con t_burst <= timestamp causal <= t_decision. MAE, MFE, TP, SL y resultado se unen despues y nunca son predictores. MBP no se presentara como identidad MBO.

PUERTA TECNICA:
Primero {len(TECHNICAL_DATES)} sesiones conocidas. Se exige version v7, DOM+tape, orden monotono, eventos post-LB y cero eventos posteriores a t_decision.

CORRIDA:
Historia X10 unicamente | X1 deshabilitado.
{len(dates)} sesiones DST: {dates[0]} -> {dates[-1]}.
Telegram reportara progreso, ETA, trades y estado de MATRIX CLASSIFICATION TEST."""


def _progress(stage_index: int, label: str, dates: list[str], all_dates: list[str]) -> dict[str, object]:
    return {
        "stage_index": stage_index,
        "stage_total": 2,
        "stage_label": label,
        "stage_period": f"{dates[0]} -> {dates[-1]}",
        "session_roots": [str(RUN_ROOT)],
        "run_label": RUN_LABEL,
        "stats_root": str(RUN_ROOT),
        "global_target": len(all_dates),
        "hypothesis_monitor_root": str(RESULTS_FOLDER),
        "hypothesis_monitor_kind": "matrix_classification",
    }


def _run_dates(dates: list[str], progress: dict[str, object], report_prefix: str):
    iso = [replay_sync.date_iso_from_replay(value) for value in dates]
    return replay_sync.run_replay_period(
        iso,
        output_folder=RUN_ROOT,
        run_plan=replay_sync.build_run_plan(quick=True, x10_only=True),
        report_prefix=report_prefix,
        force=False,
        step=False,
        compare_only=False,
        replay_to_time=REPLAY_TO_TIME,
        progress_meta=progress,
    )


def _final_capability_message(manifest: dict[str, object]) -> str:
    if manifest.get("verdict") == "SEPARACION_RESPALDADA":
        return "YA SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO"
    return (
        "NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO\n"
        "me falta analizar: identidad MBO por orden para distinguir cancelacion, modificacion y fill; "
        "supervivencia/reposicion y posicion de cola; reloj exchange-time DOM+tape mas preciso; "
        "y una muestra mayor de absorciones y breakouts limpios estable en BUY y SELL."
    )


def _scientific_summary(manifest: dict[str, object], scientific: Path) -> str:
    metrics_path = scientific / "feature_family_classification_matrix.csv"
    best = "Sin holdout suficiente"
    if metrics_path.exists() and metrics_path.stat().st_size:
        metrics = pd.read_csv(metrics_path)
        holdout = metrics.loc[metrics.get("split", pd.Series(dtype=str)).astype(str).eq("holdout")].copy()
        if not holdout.empty:
            score = pd.to_numeric(holdout.get("balanced_accuracy"), errors="coerce")
            if score.notna().any():
                row = holdout.loc[score.idxmax()]
                best = (
                    f"mejor holdout {row.get('feature_family','')}/{row.get('model','')}: "
                    f"BA {float(row.get('balanced_accuracy')):.3f} | AUC {float(row.get('roc_auc_A_vs_B')):.3f}"
                )
    return (
        "MATRIX CLASSIFICATION TEST — RESULTADO\n"
        f"Auditoria causal: {'PASS' if manifest.get('audit_pass') else 'FAIL'}\n"
        f"Eventos post-LB: {manifest.get('postburst_rows', 0)} | bursts: {manifest.get('timeline_bursts', 0)} | "
        f"etiquetados: {manifest.get('labeled_bursts', 0)} | A/B: {manifest.get('clean_A_B', 0)}\n"
        f"Patrones prometedores estables: {manifest.get('promising_patterns', 0)}\n"
        f"{best}\n"
        "Las metricas son separacion A/B; no son WR ni PF."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = _read_state()
    configured = replay_dates()
    dates = list(state.get("dates", [])) if state and state.get("dates") else configured
    if not dates:
        raise SystemExit("No replay dates available")
    audit, audit_pass = design_audit(dates)
    print(audit.to_string(index=False))
    print(f"AUDIT={'PASS' if audit_pass else 'FAIL'} | {AUDIT_MD}")
    print(f"DATES={len(dates)} | {dates[0]} -> {dates[-1]}")
    if not audit_pass:
        raise SystemExit("Design audit failed; Replay was not launched")
    if args.audit_only or args.prepare_only:
        print("PREPARE/AUDIT ONLY: Replay and Telegram were not touched.")
        return 0

    fresh = state is None
    if state and state.get("status") == "COMPLETE":
        raise SystemExit(f"Matrix replay already complete: {RUN_ROOT}")
    if state and state.get("dates") != dates:
        raise SystemExit("Active matrix run manifest differs")

    BASE_RUNNER.DATES_DST = dates
    if fresh:
        BASE_RUNNER.reset_replay_run_state(RUN_ROOT)
        _set_state("ACTIVE_TECHNICAL", dates, audit="PASS", detector_version=matrix_research.EXPECTED_VERSION)
        clear_telegram_before_run(str(RESULTS_FOLDER))
        update_status_file(RESULTS_FOLDER)
        send_text(str(RESULTS_FOLDER), first_telegram_message(dates))
    else:
        send_text(str(RESULTS_FOLDER), "MATRIX CLASSIFICATION TEST | REANUDACION\nSe conservan sesiones terminales y se llenan solo huecos.")

    technical = [value for value in TECHNICAL_DATES if value in dates]
    passed, failures = _run_dates(
        technical,
        _progress(1, "PUERTA TECNICA: secuencias exclusivamente post-LB", technical, dates),
        "matrix_classification_r5_technical",
    )
    if failures or not passed:
        _capture_observational_files()
        _set_state("INCOMPLETE_TECHNICAL", dates, failures=failures)
        send_text(str(RESULTS_FOLDER), f"MATRIX CLASSIFICATION TEST | PUERTA TECNICA INCOMPLETA\nErrores: {len(failures)}. No se lanza la corrida larga.")
        return 1

    gate, gate_pass = matrix_research.technical_gate(RESULTS_FOLDER)
    gate.to_csv(RUN_ROOT / "technical_gate_audit.csv", index=False)
    print(gate.to_string(index=False))
    if not gate_pass:
        _capture_observational_files()
        _set_state("BLOCKED_TECHNICAL_GATE", dates, technical_gate=gate.to_dict("records"))
        send_text(str(RESULTS_FOLDER), "MATRIX CLASSIFICATION TEST | PUERTA TECNICA FAIL\nReplay largo detenido: revisar ventana post-LB, timestamps u orden.")
        return 2

    _set_state("ACTIVE_FULL", dates, technical_gate="PASS")
    send_text(str(RESULTS_FOLDER), "MATRIX CLASSIFICATION TEST | PUERTA TECNICA PASS\nSolo eventos post-LB y cero eventos posteriores a t_decision. Continua la corrida completa DST 2025–2026.")
    passed, failures = _run_dates(
        dates,
        _progress(2, "CAPTURA: patrones y secuencias post-LB", dates, dates),
        "matrix_classification_r5_full",
    )
    if failures or not passed:
        _capture_observational_files()
        _set_state("INCOMPLETE_FULL", dates, failures=failures)
        send_text(str(RESULTS_FOLDER), f"MATRIX CLASSIFICATION TEST | CORRIDA INCOMPLETA\nHuecos/errores: {len(failures)}. Relanzar reanuda solo huecos.")
        return 1

    _capture_observational_files()
    send_run_summary(str(RESULTS_FOLDER), dates, [], RUN_LABEL)
    scientific = RUN_ROOT / "scientific_analysis"
    if scientific.exists():
        archive = RUN_ROOT / f"_archive_scientific_analysis_{datetime.now():%Y%m%d_%H%M%S}"
        shutil.move(str(scientific), str(archive))
    try:
        manifest = matrix_research.run_analysis(RESULTS_FOLDER, scientific)
        send_text(str(RESULTS_FOLDER), _scientific_summary(manifest, scientific))
        for visual in manifest.get("visuals", []):
            send_photo(str(RESULTS_FOLDER), visual, "MATRIX CLASSIFICATION TEST — A vs B")
        send_text(str(RESULTS_FOLDER), format_status(calculate(RESULTS_FOLDER)))
        send_text(str(RESULTS_FOLDER), _final_capability_message(manifest))
        _set_state("COMPLETE", dates, failures=[], scientific_output=str(scientific), manifest=manifest)
    except Exception as exc:
        _set_state("REPLAY_COMPLETE_ANALYSIS_FAILED", dates, analysis_error=f"{type(exc).__name__}: {exc}")
        send_text(str(RESULTS_FOLDER), f"MATRIX CLASSIFICATION TEST | REPLAY COMPLETO, ANALISIS FALLIDO\n{type(exc).__name__}: {exc}\nNo se repite Replay; reparar solo el reporte.")
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
