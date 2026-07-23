"""R4 replay: capture causal DOM+tape sequences up to t_decision."""

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

import lb_causal_sequence_research as sequence
from lb_causal_sequence_monitor import format_status, calculate, update_status_file
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
RUN_ROOT = RESULTS_FOLDER / "visual_tests" / "04_run_replay_lb_causal_sequence_r4_dst_2025_2026_runs"
STATE_FILE = RUN_ROOT / "run_state.json"
AUDIT_MD = BASE_DIR / "contexto_features_atas" / "AUDITORIA_DISENO_LB_SECUENCIAS_CAUSALES_R4_20260721.md"
AUDIT_CSV = BASE_DIR / "contexto_features_atas" / "AUDITORIA_DISENO_LB_SECUENCIAS_CAUSALES_R4_20260721.csv"
PROTOCOL_MD = BASE_DIR / "contexto_features_atas" / "PROTOCOLO_LB_SECUENCIAS_CAUSALES_DOM_TAPE_R4_20260721.md"
RUN_LABEL = "CODEX LB SECUENCIAS CAUSALES DOM TAPE R4"
FROZEN_LAST_DATE = date(2026, 7, 17)
REPLAY_TO_TIME = "10:30"
TECHNICAL_DATES = ["10/03/2025", "18/03/2025", "27/03/2025", "03/04/2025"]
OBSERVATIONAL_NAMES = (
    "burst_events.csv", "burst_response_events.csv", "burst_causal_timeline.csv",
    "trade_inputs.csv", "trade_results.csv", "exporter_lifecycle_diagnostics.csv",
)


def _load_base_runner():
    path = BASE_DIR / "04_run_replay_score_trade_results_dst_2025_2026_after_sync.py"
    spec = importlib.util.spec_from_file_location("score_dst_base_for_sequence", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load base replay runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE_RUNNER = _load_base_runner()


def replay_dates() -> list[str]:
    last_date = min(
        datetime.now(ZoneInfo("America/New_York")).date() - timedelta(days=1),
        FROZEN_LAST_DATE,
    )
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
    detector_path = BASE_DIR / "12_LiquidityBurstDetector.cs"
    detector = detector_path.read_text(encoding="utf-8")
    base_runner = (BASE_DIR / "04_run_replay_score_trade_results_dst_2025_2026_after_sync.py").read_text(encoding="utf-8")
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
        ("DETECTOR_VERSION", sequence.EXPECTED_VERSION, sequence.EXPECTED_VERSION in detector),
        ("TIMELINE_ENABLED_DEFAULT", "ExportCausalTimeline defaults true", "public bool ExportCausalTimeline { get; set; } = true;" in detector),
        ("LOOKBACK_BOUND", "1..10 seconds", "[Range(1, 10)]" in detector and "CausalTimelineLookbackSeconds" in detector),
        ("EVENT_SCHEMA", "arrival/source/causal/available/decision timestamps", all(token in detector for token in (
            "Global_Arrival_Sequence", "Event_Source_Timestamp_UTC", "Event_Causal_Timestamp_UTC",
            "Event_Available_Timestamp_UTC", "Decision_Timestamp_UTC"))),
        ("DOM_AND_TAPE_CAPTURE", "MarketDepthChanged + ProcessTrade append events", detector.count("BuildCausalTimelineEventLocked(") >= 3),
        ("PREDECISION_FILTER", "timeline writer enforces causal timestamp <= decision", "item.CausalTimestampUtc <= decisionTimestampUtc" in detector),
        ("ACTUAL_DECISION_TIMESTAMP", "Feature available equals detector publish timestamp", detector.count("Csv(DetectorPublishTimestampUtc.ToString(\"O\"") >= 4),
        ("MBP_SEMANTICS", "depth changes are not mislabeled cancel/fill", "DEPTH_INCREASE" in detector and "DEPTH_DECREASE" in detector and "same_order" not in detector.lower()),
        ("NO_OUTCOME_IN_TIMELINE", "no MAE/MFE/result columns in timeline header", all(token not in detector[detector.index("public const string CsvHeader =", detector.index("private sealed class CausalTimelineEvent")):detector.index("public CausalTimelineEvent(", detector.index("private sealed class CausalTimelineEvent"))].lower() for token in ("mae", "mfe", "result", "exit"))),
        ("RESET_ARCHIVES_TIMELINE", "fresh runs archive burst_causal_timeline.csv", '"burst_causal_timeline.csv"' in base_runner),
        ("TRADING_UNCHANGED", "timeline never enters exporter or signal bus", "burst_causal_timeline" not in exporter and "burst_causal_timeline" not in signal_bus),
        ("WORKSPACE_DETECTOR", "LiquidityBurstDetector attached", "ATAS.Indicators.LiquidityBurstDetector" in workspace),
        ("DLL_INSTALLED", "installed indicator equals current build", built_dll.exists() and installed_dll.exists() and _sha256(built_dll) == _sha256(installed_dll)),
        ("X10_ONLY", "run plan X10_R1 only", replay_sync.build_run_plan(quick=True, x10_only=True) == [("X10_R1", "X10", replay_sync.X10_TIMEOUT_SECONDS)]),
        ("DST_SCOPE", f"{len(dates)} dates {min(parsed)}->{max(parsed)}", len(dates) == 256 and all(value.year in (2025, 2026) for value in parsed)),
        ("TECHNICAL_GATE", f"known burst dates={TECHNICAL_DATES}", all(value in dates for value in TECHNICAL_DATES)),
        ("ISOLATED_ROOT", "R4 root is new/owned", state_owned and (not RUN_ROOT.exists() or STATE_FILE.exists())),
        ("HANDLE_REPLAY", "Replay acquisition avoids whole-desktop UIA", "win32gui.EnumWindows" in (BASE_DIR / "replay_sync_runner_common_after_sync.py").read_text(encoding="utf-8")),
    ]
    audit = pd.DataFrame(checks, columns=["check", "evidence", "passed"])
    passed = bool(audit["passed"].all())
    AUDIT_CSV.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_CSV, index=False)
    lines = [
        "# Auditoría de diseño — secuencias causales DOM+tape R4",
        "",
        f"Estado: **{'PASS' if passed else 'FAIL'}**.",
        "",
        "La operativa permanece congelada. El nuevo archivo es observacional y solo incluye eventos con reloj causal no posterior a t_decision.",
        "",
        "| Control | Evidencia | Pasó |",
        "| --- | --- | ---: |",
    ]
    for row in audit.itertuples(index=False):
        lines.append(f"| {row.check} | {row.evidence} | {int(row.passed)} |")
    AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return audit, passed


def first_telegram_message(dates: list[str]) -> str:
    return f"""LIQUIDITY BURST | SECUENCIAS CAUSALES DOM+TAPE
PROPUESTO POR CODEX — R4 DST 2025–2026

OBJETIVO:
Detectar el Liquidity Burst y capturar el proceso que condujo a t_decision para investigar si una combinacion ordenada distingue A) ABSORCION LIMPIA de B) CONTINUACION/BREAKOUT LIMPIO. C) TRADE VARIABLE se conserva como abstencion. No cambia entrada, SL, TP, RR ni gestion.

QUE SE CAPTURA:
- Cada trade de tape y cada aumento/disminucion MBP del DOM.
- Orden global de llegada y secuencia dentro de BurstId.
- Timestamp original ATAS, reloj causal disponible y offset a t_decision.
- AHEAD/BEHIND, profundidad antes/despues, touch, microprice e imbalance despues de cada evento.
- Estados fisicos: agresion con progreso/stall, deplecion, reposicion y counterflow.

POR QUE:
La R3 demostro que snapshots y agregados aislados no separan A/B de forma estable. Esta R4 prueba si la informacion vive en el orden de las transiciones.

CONTROL CAUSAL:
Solo Model_Eligibility=CAUSAL_PRE_DECISION. MAE, MFE, TP, SL, continuacion y reversion etiquetan despues; nunca son predictores. MBP no se presentara como identidad de orden MBO.

PUERTA TECNICA:
Primero {len(TECHNICAL_DATES)} sesiones conocidas con bursts. Se exige DOM+tape, orden consecutivo, reloj monotono y cero eventos posteriores a t_decision. Si falla, la corrida larga se detiene automaticamente.

CORRIDA:
Historia X10 unicamente | X1 deshabilitado.
{len(dates)} sesiones: {dates[0]} -> {dates[-1]}.
Telegram actualizara sesiones, BurstId, eventos, porcentaje causal, ETA y detalle de trades."""


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
        "hypothesis_monitor_kind": "causal_sequence",
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


def _final_message(manifest: dict[str, object], scientific: Path) -> str:
    models_path = scientific / "sequence_model_metrics.csv"
    best = "SIN MUESTRA SUFICIENTE"
    if models_path.exists() and models_path.stat().st_size:
        models = pd.read_csv(models_path)
        holdout = models.loc[models.get("split", pd.Series(dtype=str)).astype(str).eq("holdout")].copy()
        if not holdout.empty and "roc_auc_A_vs_B" in holdout:
            auc = pd.to_numeric(holdout["roc_auc_A_vs_B"], errors="coerce")
            if auc.notna().any():
                row = holdout.loc[auc.idxmax()]
                best = f"mejor holdout {row.get('model','')}: AUC {float(row['roc_auc_A_vs_B']):.3f}"
    return (
        "LIQUIDITY BURST | SECUENCIAS CAUSALES DOM+TAPE — FINAL\n"
        f"Auditoria causal: {'PASS' if manifest.get('audit_pass') else 'FAIL'}\n"
        f"Eventos: {manifest.get('timeline_rows', 0)} | bursts timeline: {manifest.get('timeline_bursts', 0)} | "
        f"etiquetados: {manifest.get('labeled_bursts', 0)} | A/B: {manifest.get('clean_A_B', 0)}\n"
        f"{best}\n"
        "El porcentaje es separacion A-vs-B fuera de muestra, no WR. C permanece como abstencion."
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
        raise SystemExit(f"Sequence replay already complete: {RUN_ROOT}")
    if state and state.get("dates") != dates:
        raise SystemExit("Active sequence run manifest differs")

    BASE_RUNNER.DATES_DST = dates
    if fresh:
        BASE_RUNNER.reset_replay_run_state(RUN_ROOT)
        _set_state("ACTIVE_TECHNICAL", dates, audit="PASS", detector_version=sequence.EXPECTED_VERSION)
        clear_telegram_before_run(str(RESULTS_FOLDER))
        update_status_file(RESULTS_FOLDER)
        send_text(str(RESULTS_FOLDER), first_telegram_message(dates))
    else:
        send_text(str(RESULTS_FOLDER), "LB SECUENCIAS CAUSALES R4 | REANUDACION\nSe conservan sesiones terminales y se llenan solo huecos.")

    technical = [value for value in TECHNICAL_DATES if value in dates]
    passed, failures = _run_dates(
        technical,
        _progress(1, "PUERTA TECNICA: orden y causalidad DOM+tape", technical, dates),
        "lb_causal_sequence_r4_technical",
    )
    if failures or not passed:
        _capture_observational_files()
        _set_state("INCOMPLETE_TECHNICAL", dates, failures=failures)
        send_text(str(RESULTS_FOLDER), f"LB SECUENCIAS R4 | PUERTA TECNICA INCOMPLETA\nErrores: {len(failures)}. No se lanza la corrida larga.")
        return 1

    gate, gate_pass = sequence.technical_gate(RESULTS_FOLDER)
    gate.to_csv(RUN_ROOT / "technical_gate_audit.csv", index=False)
    print(gate.to_string(index=False))
    if not gate_pass:
        _capture_observational_files()
        _set_state("BLOCKED_TECHNICAL_GATE", dates, technical_gate=gate.to_dict("records"))
        send_text(str(RESULTS_FOLDER), "LB SECUENCIAS R4 | PUERTA TECNICA FAIL\nLa corrida larga fue detenida: revisar timestamps/orden/cobertura.")
        return 2

    _set_state("ACTIVE_FULL", dates, technical_gate="PASS")
    send_text(str(RESULTS_FOLDER), "LB SECUENCIAS R4 | PUERTA TECNICA PASS\nCero eventos posteriores a t_decision. Continua la corrida completa de 256 sesiones.")
    passed, failures = _run_dates(
        dates,
        _progress(2, "CAPTURA COMPLETA: secuencias causales DOM+tape", dates, dates),
        "lb_causal_sequence_r4_full",
    )
    if failures or not passed:
        _capture_observational_files()
        _set_state("INCOMPLETE_FULL", dates, failures=failures)
        send_text(str(RESULTS_FOLDER), f"LB SECUENCIAS R4 | CORRIDA INCOMPLETA\nHuecos/errores: {len(failures)}. Relanzar reanuda solo huecos.")
        return 1

    _capture_observational_files()
    send_run_summary(str(RESULTS_FOLDER), dates, [], f"LIQUIDITY BURST SEQUENCE | {RUN_LABEL}")
    scientific = RUN_ROOT / "scientific_analysis"
    if scientific.exists():
        archive = RUN_ROOT / f"_archive_scientific_analysis_{datetime.now():%Y%m%d_%H%M%S}"
        shutil.move(str(scientific), str(archive))
    try:
        manifest = sequence.run_analysis(RESULTS_FOLDER, scientific)
        send_text(str(RESULTS_FOLDER), _final_message(manifest, scientific))
        for visual in manifest.get("visuals", []):
            send_photo(str(RESULTS_FOLDER), visual, "Secuencias causales DOM+tape — A/B/C")
        final_status = format_status(calculate(RESULTS_FOLDER))
        send_text(str(RESULTS_FOLDER), final_status)
        _set_state("COMPLETE", dates, failures=[], scientific_output=str(scientific), manifest=manifest)
    except Exception as exc:
        _set_state("REPLAY_COMPLETE_ANALYSIS_FAILED", dates, analysis_error=f"{type(exc).__name__}: {exc}")
        send_text(str(RESULTS_FOLDER), f"LB SECUENCIAS R4 | REPLAY COMPLETO, ANALISIS FALLIDO\n{type(exc).__name__}: {exc}\nNo se repite Replay; reparar solo el reporte.")
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
