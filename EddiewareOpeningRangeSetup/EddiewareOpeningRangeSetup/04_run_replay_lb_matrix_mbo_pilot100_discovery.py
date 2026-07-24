"""Replay and discovery analysis for MATRIX + MBO CLASSIFICATION TEST."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import databento as db
import pandas as pd

import lb_matrix_classification_research as matrix_research
import lb_matrix_mbo_combined_research as combined_research
from lb_matrix_mbo_monitor import calculate, format_status, update_status_file
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
RUN_ROOT = RESULTS_FOLDER / "visual_tests" / "04_run_replay_lb_matrix_mbo_pilot100_discovery_r1_runs"
STATE_FILE = RUN_ROOT / "run_state.json"
CONTEXT_DIR = BASE_DIR / "contexto_features_atas"
MANIFEST_PATH = CONTEXT_DIR / "DATABENTO_MBO_PILOTO_100_DISCOVERY_20260722.csv"
PROTOCOL_MD = CONTEXT_DIR / "PROTOCOLO_CORRIDA_MATRIX_MBO_POST_AUDITORIA_R2_20260723.md"
AUDIT_MD = CONTEXT_DIR / "AUDITORIA_DISENO_MATRIX_MBO_POST_AUDITORIA_R2_20260723.md"
AUDIT_CSV = CONTEXT_DIR / "AUDITORIA_DISENO_MATRIX_MBO_POST_AUDITORIA_R2_20260723.csv"
MBO_DIRECT_AUDIT_JSON = CONTEXT_DIR / "AUDITORIA_DIRECTA_MBO_PILOTO100_POST_R2_20260723.json"
MBO_CAPABILITY_MD = CONTEXT_DIR / "MBO_DATA_CAPABILITY_AUDIT.md"
MBO_QUALITY_CSV = CONTEXT_DIR / "MBO_SESSION_QUALITY.csv"
MBO_FIELD_COVERAGE_CSV = CONTEXT_DIR / "MBO_FIELD_COVERAGE.csv"
MBO_DIR = EXPORT_FOLDER / "databento_mbo" / "liquidity_burst_pilot_20260720"
MBP_LEDGER = BASE_DIR / "outputs" / "preentry_liquidity_features_20260720_preentry_r2" / "preentry_mbp_feature_ledger.csv"
RUN_LABEL = "MATRIX + MBO CLASSIFICATION TEST"
REPLAY_TO_TIME = "10:30"
TECHNICAL_DATES = ["05/04/2022", "06/04/2022", "26/04/2022", "27/04/2022"]
FINAL_NO = "NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO"
FINAL_YES = "SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO"
OBSERVATIONAL_NAMES = (
    "burst_events.csv",
    "burst_response_events.csv",
    "burst_causal_timeline.csv",
    "trade_inputs.csv",
    "trade_results.csv",
    "exporter_lifecycle_diagnostics.csv",
)


def _load_base_runner():
    path = BASE_DIR / "04_run_replay_score_trade_results_dst_2025_2026_after_sync.py"
    spec = importlib.util.spec_from_file_location("score_dst_base_for_matrix_mbo", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load base replay runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE_RUNNER = _load_base_runner()


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


def replay_dates() -> list[str]:
    manifest = pd.read_csv(MANIFEST_PATH)
    values = pd.to_datetime(manifest["fecha"], errors="raise")
    return [value.strftime("%d/%m/%Y") for value in values]


def _capture_observational_files() -> None:
    target = RUN_ROOT / "observational"
    target.mkdir(parents=True, exist_ok=True)
    for name in OBSERVATIONAL_NAMES:
        source = RESULTS_FOLDER / name
        if source.exists():
            shutil.copy2(source, target / name)


def audit_mbo_files(manifest: pd.DataFrame) -> dict[str, object]:
    action_counts: dict[str, int] = {}
    total_rows = 0
    unique_file_orders = 0
    first_add_orders = 0
    bad_book_rows = 0
    snapshot_rows = 0
    clear_rows = 0
    post_request_end_rows = 0
    files: list[dict[str, object]] = []
    for row in manifest.itertuples(index=False):
        path = MBO_DIR / f"{row.request_id}.mbo.dbn.zst"
        if not path.exists():
            raise FileNotFoundError(path)
        frame = db.DBNStore.from_file(path).to_df()
        if not isinstance(frame.index, pd.RangeIndex):
            frame = frame.reset_index()
        required = {
            "ts_event", "ts_recv", "action", "side", "price", "size", "order_id",
            "flags", "sequence", "instrument_id", "publisher_id", "channel_id",
        }
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{path.name}: missing MBO columns {missing}")
        event = pd.to_datetime(frame["ts_event"], utc=True, errors="raise")
        request_end = pd.Timestamp(row.end_utc_exclusive)
        flags = pd.to_numeric(frame["flags"], errors="coerce").fillna(0).astype("uint16")
        actions = frame["action"].astype(str)
        groups = frame.assign(_event=event).sort_values(["_event", "sequence"], kind="stable").groupby("order_id", sort=False)
        first_actions = groups["action"].first().astype(str)
        file_order_count = int(len(first_actions))
        file_first_add = int(first_actions.eq("A").sum())
        file_bad = int(flags.map(lambda value: bool(int(value) & 4)).sum())
        file_snapshot = int(flags.map(lambda value: bool(int(value) & 32)).sum())
        file_clear = int(actions.eq("R").sum())
        file_post_end = int(event.ge(request_end).sum())
        counts = actions.value_counts()
        for action, count in counts.items():
            action_counts[str(action)] = action_counts.get(str(action), 0) + int(count)
        total_rows += len(frame)
        unique_file_orders += file_order_count
        first_add_orders += file_first_add
        bad_book_rows += file_bad
        snapshot_rows += file_snapshot
        clear_rows += file_clear
        post_request_end_rows += file_post_end
        files.append(
            {
                "request_id": row.request_id,
                "path": str(path),
                "bytes": path.stat().st_size,
                "rows": len(frame),
                "first_ts_event": event.min().isoformat(),
                "last_ts_event": event.max().isoformat(),
                "unique_orders": file_order_count,
                "first_action_add_orders": file_first_add,
                "first_action_add_share": file_first_add / max(1, file_order_count),
                "bad_book_rows": file_bad,
                "snapshot_rows": file_snapshot,
                "clear_rows": file_clear,
                "post_request_end_rows": file_post_end,
                "schema_columns": list(frame.columns),
            }
        )
    result = {
        "files": len(files),
        "bytes": sum(item["bytes"] for item in files),
        "rows": total_rows,
        "action_counts": action_counts,
        "unique_orders_per_file_sum": unique_file_orders,
        "first_action_add_orders": first_add_orders,
        "first_action_add_share": first_add_orders / max(1, unique_file_orders),
        "left_censored_orders": unique_file_orders - first_add_orders,
        "left_censored_share": 1.0 - first_add_orders / max(1, unique_file_orders),
        "bad_book_rows": bad_book_rows,
        "snapshot_rows": snapshot_rows,
        "clear_rows": clear_rows,
        "post_request_end_rows": post_request_end_rows,
        "raw_mbo_schema": True,
        "initial_book_reconstructable": False,
        "files_detail": files,
    }
    _write_json(MBO_DIRECT_AUDIT_JSON, result)
    return result


def first_telegram_message(dates: list[str]) -> str:
    return f"""MATRIX + MBO CLASSIFICATION TEST
PROPUESTO POR CODEX — PILOTO DISCOVERY 100 POST-AUDITORIA MBO

OBJETIVO:
Detectar el Liquidity Burst y decidir si la combinacion causal de identidad MBO por orden con patrones y secuencias DOM+tape distingue A) ABSORCION LIMPIA de B) BREAKOUT LIMPIO. C) TRADE VARIABLE queda como diagnostico/abstencion.

CAPACIDAD DE DATOS AUDITADA:
- Veredicto: B SIRVEN PARCIALMENTE.
- 1,274,719 eventos MBO | 621,262 IDs | 21.88% censura izquierda.
- Snapshot inicial: 0. No se afirmara posicion inicial ni volumen exacto delante.
- 595 eventos del milisegundo final posteriores al timestamp nominal se excluyen.
- MBO y ATAS no se trataran como un reloj submilisegundo comun.

QUE SE MIDE SIN CREAR FEATURES NUEVAS:
- MBO pre-t_decision: 12 predictores congelados. ADD/FILL son explicitos; cancelacion pura, supervivencia y refill se reportan como inferidos/censurados.
- MATRIX post-LB: estados de 100 ms, transiciones y secuencias t_burst -> t_decision.
- Siete combinaciones congeladas; regresion logistica C=0.2; LOYO 2022/2023/2024; 1000 permutaciones y 1000 bootstraps.

LIMITES:
MAE, MFE, TP, SL, PnL y eventos posteriores a t_decision no son predictores. Cancel-replace con ID nuevo, intencion iceberg y cola inicial quedan prohibidos como conclusiones.

ALCANCE:
{len(dates)} sesiones discovery: {dates[0]} -> {dates[-1]}. Validacion y holdout siguen cerrados.
Historia X10 unicamente | X1 deshabilitado.

TELEGRAM:
Durante captura: sesiones y causalidad, sin porcentajes de eficacia prematuros.
Al final: ETIQUETA MATRIX+MBO con BA/AUC, sensibilidad A, especificidad B, IC, permutacion, estabilidad y limitaciones MBO. No se sustituiran por WR/PF.
Este discovery no puede emitir SOY CAPAZ sin validacion temporal sellada."""


def resume_telegram_message(dates: list[str], completed: int) -> str:
    return (
        "MATRIX + MBO CLASSIFICATION TEST | REANUDACION POST-AUDITORIA\n"
        f"Se conservan {completed} sesiones terminales porque detector/exportador/cutoff no cambiaron; "
        "se completan solo los huecos.\n"
        "MBO: B SIRVEN PARCIALMENTE | snapshot 0 | censura izquierda 21.88% | "
        "595 eventos de empate submilisegundo excluidos.\n"
        "Las 12 features permanecen congeladas; se corrigio solo el emparejamiento F/C agregado y "
        "la etiqueta explicito/inferido/censurado.\n"
        f"Discovery: {len(dates)} sesiones 2022-2024. Validacion y holdout continúan cerrados."
    )


def design_audit(dates: list[str]) -> tuple[pd.DataFrame, bool]:
    manifest = pd.read_csv(MANIFEST_PATH)
    detector = (BASE_DIR / "12_LiquidityBurstDetector.cs").read_text(encoding="utf-8")
    combined = (BASE_DIR / "lb_matrix_mbo_combined_research.py").read_text(encoding="utf-8")
    common = (BASE_DIR / "replay_sync_runner_common_after_sync.py").read_text(encoding="utf-8")
    exporter = (BASE_DIR / "ATASScoreTradeResultExporter.cs").read_text(encoding="utf-8")
    signal_bus = (BASE_DIR / "12_B_LiquidityBurstSignalBus.cs").read_text(encoding="utf-8")
    workspace_path = Path.home() / "AppData" / "Roaming" / "ATAS" / "Workspaces_v3" / "Eddieware_workspace.ws"
    workspace = workspace_path.read_text(encoding="utf-8") if workspace_path.exists() else ""
    built_dll = BASE_DIR / "bin" / "Debug" / "net10.0" / "EddiewareOpeningRangeSetup.dll"
    installed_dll = Path.home() / "AppData" / "Roaming" / "ATAS" / "Indicators" / "EddiewareOpeningRangeSetup.dll"
    direct = audit_mbo_files(manifest)
    capability_text = (
        MBO_CAPABILITY_MD.read_text(encoding="utf-8")
        if MBO_CAPABILITY_MD.exists()
        else ""
    )
    quality = (
        pd.read_csv(MBO_QUALITY_CSV, low_memory=False)
        if MBO_QUALITY_CSV.exists()
        else pd.DataFrame()
    )
    field_coverage = (
        pd.read_csv(MBO_FIELD_COVERAGE_CSV, low_memory=False)
        if MBO_FIELD_COVERAGE_CSV.exists()
        else pd.DataFrame()
    )
    tie_rows = (
        int(quality["post_nominal_cutoff_same_millisecond_rows"].sum())
        if "post_nominal_cutoff_same_millisecond_rows" in quality
        else -1
    )
    after_end_rows = (
        int(quality["at_or_after_request_end_rows"].sum())
        if "at_or_after_request_end_rows" in quality
        else -1
    )
    queue_coverage = field_coverage.loc[
        field_coverage.get("capability", pd.Series(dtype=str)).eq("Posición inicial en cola"),
        "classification",
    ]
    state_owned = not STATE_FILE.exists()
    if STATE_FILE.exists():
        try:
            state_owned = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("run_label") == RUN_LABEL
        except (OSError, json.JSONDecodeError):
            state_owned = False
    family_counts = manifest["family_label_only"].value_counts().to_dict()
    years = pd.to_datetime(manifest["fecha"]).dt.year.value_counts().sort_index().to_dict()
    checks = [
        ("MANIFEST_100_UNIQUE", "100 fechas/BurstId", len(manifest) == 100 and manifest["BurstId"].nunique() == 100 and manifest["fecha"].nunique() == 100),
        ("DISCOVERY_ONLY", "validation=0 holdout=0", manifest["split"].astype(str).eq("discovery").all()),
        ("TEMPORAL_COVERAGE", f"years={years}", set(years) == {2022, 2023, 2024}),
        ("FAMILY_COVERAGE", f"families={family_counts}", all(family_counts.get(name, 0) > 0 for name in ("A_TRUE_ABSORPTION", "B_CLEAN_BREAKOUT", "C_MIXED_PATH"))),
        ("MBO_FILES_100", f"files={direct['files']}", direct["files"] == 100),
        ("MBO_RAW_SCHEMA", "order_id/actions/timestamps/flags/sequence", bool(direct["raw_mbo_schema"])),
        ("MBO_NO_BAD_BOOK", f"F_MAYBE_BAD_BOOK rows={direct['bad_book_rows']}", direct["bad_book_rows"] == 0),
        ("MBO_WITHIN_REQUEST", f"rows at/after end={direct['post_request_end_rows']}", direct["post_request_end_rows"] == 0),
        ("MBO_ACTIONS", f"actions={direct['action_counts']}", all(direct["action_counts"].get(name, 0) > 0 for name in ("A", "C", "M", "F", "T"))),
        ("MBO_CENSORSHIP_EXPLICIT", f"snapshot={direct['snapshot_rows']} clear={direct['clear_rows']}", direct["snapshot_rows"] == 0 and direct["clear_rows"] == 0 and "initial_book_reconstructable" in direct),
        ("MBO_CAPABILITY_VERDICT_B", "B. SIRVEN PARCIALMENTE", "**B. SIRVEN PARCIALMENTE.**" in capability_text),
        ("MBO_QUALITY_100", f"quality rows={len(quality)}", len(quality) == 100 and quality.get("BurstId", pd.Series(dtype=str)).nunique() == 100),
        ("MBO_FINAL_MS_EXCLUDED", f"same-ms tie rows={tie_rows}", tie_rows == 595 and 'frame["ts_event"].le(cutoff)' in (BASE_DIR / "mbo_liquidity_burst_research.py").read_text(encoding="utf-8")),
        ("MBO_NO_ROWS_AFTER_END", f"at/after request end={after_end_rows}", after_end_rows == 0),
        ("MBO_INITIAL_QUEUE_PROHIBITED", f"classification={queue_coverage.tolist()}", len(queue_coverage) == 1 and queue_coverage.iloc[0] == "NO_DISPONIBLE"),
        ("MBO_GROUPED_FILL_CANCEL", "F/C grouped by order+exchange-time+price", "EXACT_GROUP_FILL_C_MATCH" in (BASE_DIR / "mbo_liquidity_burst_research.py").read_text(encoding="utf-8")),
        ("MBO_CORE_12_FROZEN", "12 features + status metadata", len(combined_research.mbo.CORE_MBO_FEATURES) == 12 and len(combined_research.mbo.CORE_MBO_FEATURE_STATUS) == 12),
        ("MBO_NO_QUEUE_PREDICTOR", "no queue feature in MBO_CORE", not any("queue" in name.lower() for name in combined_research.mbo.CORE_MBO_FEATURES)),
        ("MBP_METADATA_100", str(MBP_LEDGER), MBP_LEDGER.exists() and pd.read_csv(MBP_LEDGER, usecols=["BurstId"])["BurstId"].isin(manifest["BurstId"]).sum() >= 100),
        ("DETECTOR_VERSION", matrix_research.EXPECTED_VERSION, matrix_research.EXPECTED_VERSION in detector),
        ("POST_LB_EXPORT_BOUND", "start=max(configured,t_burst)", "snapshot.TimestampUtc > configuredStartTimestampUtc" in detector),
        ("DECISION_EXPORT_BOUND", "event<=t_decision", "item.CausalTimestampUtc <= decisionTimestampUtc" in detector),
        ("MBO_CAUSAL_BOUND", "ts_event<=cutoff", 'frame["ts_event"].le(cutoff)' in (BASE_DIR / "mbo_liquidity_burst_research.py").read_text(encoding="utf-8")),
        ("MATRIX_CAUSAL_BOUND", "matrix.audit_timeline", "matrix.audit_timeline" in combined),
        ("OUTCOMES_JOINED_LAST", "predictors before target", combined.index("_build_matrix_predictors") < combined.index('joined["target"]')),
        ("FROZEN_COMBINATIONS", "7 exact families", all(name in combined for name in combined_research.FAMILY_ORDER)),
        ("LOYO_FIXED_MODEL", "LOYO years; C=0.2", "_loyo_predictions" in combined and "MODEL_C = 0.2" in combined),
        ("PERMUTATION_BOOTSTRAP", "1000 + 1000", "PERMUTATIONS = 1000" in combined and "BOOTSTRAPS = 1000" in combined),
        ("NO_OUTCOME_IN_TRADING", "analysis observational", "matrix_mbo" not in exporter.lower() and "matrix_mbo" not in signal_bus.lower()),
        ("TELEGRAM_LABEL", "ETIQUETA MATRIX+MBO", "ETIQUETA MATRIX+MBO" in combined and RUN_LABEL in first_telegram_message(dates)),
        ("TELEGRAM_CAPABILITY_B", "explicit/inferred/censored limitations", "B SIRVEN PARCIALMENTE" in first_telegram_message(dates) and "21.88%" in first_telegram_message(dates)),
        ("FINAL_VERDICT_FROZEN", FINAL_NO, FINAL_NO in combined and FINAL_YES in Path(__file__).read_text(encoding="utf-8")),
        ("WORKSPACE_DETECTOR", "LiquidityBurstDetector attached", "ATAS.Indicators.LiquidityBurstDetector" in workspace),
        ("DLL_INSTALLED", "installed DLL equals current build", built_dll.exists() and installed_dll.exists() and _sha256(built_dll) == _sha256(installed_dll)),
        ("X10_ONLY", "X10_R1 only", replay_sync.build_run_plan(quick=True, x10_only=True) == [("X10_R1", "X10", replay_sync.X10_TIMEOUT_SECONDS)]),
        ("DATES_MATCH_MANIFEST", f"{len(dates)} manifest dates", dates == replay_dates()),
        ("TECHNICAL_GATE", f"dates={TECHNICAL_DATES}", all(value in dates for value in TECHNICAL_DATES)),
        ("ISOLATED_ROOT", "new/owned R1 root", state_owned and (not RUN_ROOT.exists() or STATE_FILE.exists())),
        ("PROTOCOL_PRESENT", str(PROTOCOL_MD), PROTOCOL_MD.exists()),
        ("EXPLICIT_LAUNCH_AUTHORIZATION", "--authorized-launch required", "--authorized-launch" in Path(__file__).read_text(encoding="utf-8")),
        ("MONITOR_REFRESH_EVERY_SESSION", "progress_every=1", "progress_every=1" in Path(__file__).read_text(encoding="utf-8") and "matrix_mbo" in common),
    ]
    audit = pd.DataFrame(checks, columns=["check", "evidence", "passed"])
    passed = bool(audit["passed"].all())
    AUDIT_CSV.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_CSV, index=False)
    lines = [
        "# Auditoría de diseño — MATRIX + MBO post-auditoría R2, piloto 100",
        "",
        f"Estado: **{'PASS' if passed else 'FAIL'}**.",
        "",
        f"MBO real: {direct['files']} archivos, {direct['rows']:,} filas, {direct['bytes']:,} bytes. "
        f"Ciclos iniciados con ADD dentro de ventana: {100 * direct['first_action_add_share']:.2f}%; "
        f"censurados por la izquierda: {100 * direct['left_censored_share']:.2f}%.",
        "",
        "La censura inicial no se imputa. La ruta predictora termina en t_decision y los outcomes se unen después. "
        f"Eventos de empate submilisegundo excluidos: {tie_rows}.",
        "",
        "| Control | Evidencia | Pasó |",
        "| --- | --- | ---: |",
    ]
    for row in audit.itertuples(index=False):
        lines.append(f"| {row.check} | {str(row.evidence).replace('|', '/')} | {int(row.passed)} |")
    AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return audit, passed


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
        "hypothesis_monitor_kind": "matrix_mbo",
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
        progress_every=1,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--authorized-launch",
        action="store_true",
        help="Required explicit authorization gate before Telegram or Replay can be touched.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = _read_state()
    configured = replay_dates()
    dates = list(state.get("dates", [])) if state and state.get("dates") else configured
    audit, audit_pass = design_audit(dates)
    print(audit.to_string(index=False))
    print(f"AUDIT={'PASS' if audit_pass else 'FAIL'} | {AUDIT_MD}")
    print(f"DATES={len(dates)} | {dates[0]} -> {dates[-1]}")
    if not audit_pass:
        raise SystemExit("Design audit failed; Replay was not launched")
    if args.audit_only or args.prepare_only:
        print("PREPARE/AUDIT ONLY: Replay and Telegram were not touched.")
        return 0
    if not args.authorized_launch:
        print(
            "READY_NOT_LAUNCHED: design audit passed, but --authorized-launch was not supplied. "
            "Replay, ATAS and Telegram were not touched."
        )
        return 0

    fresh = state is None
    if state and state.get("status") == "COMPLETE":
        raise SystemExit(f"Matrix+MBO replay already complete: {RUN_ROOT}")
    if state and state.get("dates") != dates:
        raise SystemExit("Active Matrix+MBO run manifest differs")

    BASE_RUNNER.DATES_DST = dates
    if fresh:
        BASE_RUNNER.reset_replay_run_state(RUN_ROOT)
        _set_state("ACTIVE_TECHNICAL", dates, audit="PASS", detector_version=matrix_research.EXPECTED_VERSION)
        clear_telegram_before_run(str(RESULTS_FOLDER))
        update_status_file(RESULTS_FOLDER)
        send_text(str(RESULTS_FOLDER), first_telegram_message(dates))
    else:
        send_text(
            str(RESULTS_FOLDER),
            first_telegram_message(dates)
            + "\n\n"
            + resume_telegram_message(
                dates,
                int(state.get("completed_full_sessions_at_pause", 0)),
            ),
        )

    technical = [value for value in TECHNICAL_DATES if value in dates]
    passed, failures = _run_dates(
        technical,
        _progress(1, "PUERTA TECNICA: Matrix post-LB y MBO causal", technical, dates),
        "matrix_mbo_pilot100_technical",
    )
    if failures or not passed:
        _capture_observational_files()
        _set_state("INCOMPLETE_TECHNICAL", dates, failures=failures)
        send_text(
            str(RESULTS_FOLDER),
            f"MATRIX + MBO CLASSIFICATION TEST | PUERTA TECNICA INCOMPLETA\n"
            f"Errores: {len(failures)}. No se lanza la corrida completa.",
        )
        return 1

    gate, gate_pass = matrix_research.technical_gate(RESULTS_FOLDER)
    gate.to_csv(RUN_ROOT / "technical_gate_audit.csv", index=False)
    print(gate.to_string(index=False))
    if not gate_pass:
        _capture_observational_files()
        _set_state("BLOCKED_TECHNICAL_GATE", dates, technical_gate=gate.to_dict("records"))
        send_text(
            str(RESULTS_FOLDER),
            "MATRIX + MBO CLASSIFICATION TEST | PUERTA TECNICA FAIL\n"
            "Replay completo detenido: revisar version, timestamps, orden o ventana post-LB.",
        )
        return 2

    _set_state("ACTIVE_FULL", dates, technical_gate="PASS")
    send_text(
        str(RESULTS_FOLDER),
        "MATRIX + MBO CLASSIFICATION TEST | PUERTA TECNICA PASS\n"
        "MATRIX usa solo t_burst->t_decision; MBO usa solo ts_event<=cutoff. Continua el piloto de 100 discovery.",
    )
    passed, failures = _run_dates(
        dates,
        _progress(2, "CAPTURA: Matrix post-LB para unir con MBO", dates, dates),
        "matrix_mbo_pilot100_full",
    )
    if failures or not passed:
        _capture_observational_files()
        _set_state("INCOMPLETE_FULL", dates, failures=failures)
        send_text(
            str(RESULTS_FOLDER),
            f"MATRIX + MBO CLASSIFICATION TEST | CORRIDA INCOMPLETA\n"
            f"Huecos/errores: {len(failures)}. Relanzar completa solo los huecos.",
        )
        return 1

    _capture_observational_files()
    send_run_summary(str(RESULTS_FOLDER), dates, [], RUN_LABEL)
    scientific = RUN_ROOT / "scientific_analysis"
    if scientific.exists():
        archive = RUN_ROOT / f"_archive_scientific_analysis_{datetime.now():%Y%m%d_%H%M%S}"
        shutil.move(str(scientific), str(archive))
    try:
        result = combined_research.run_analysis(
            RESULTS_FOLDER,
            scientific,
            MANIFEST_PATH,
            MBO_DIR,
            MBP_LEDGER,
        )
        send_text(
            str(RESULTS_FOLDER),
            "MATRIX + MBO CLASSIFICATION TEST | RESULTADO CIENTIFICO\n"
            f"Estado discovery: {result['pilot_status']}\n"
            f"A/B limpios: {result['clean_A_B']} | validacion sellada: 0 | holdout sellado: 0\n"
            "Las metricas siguientes son separacion fuera de año; no son WR ni PF.",
        )
        send_text(str(RESULTS_FOLDER), str(result["telegram_label"]))
        for visual in result.get("visuals", []):
            send_photo(str(RESULTS_FOLDER), visual, "MATRIX + MBO — combinaciones A vs B")
        send_text(str(RESULTS_FOLDER), format_status(calculate(RESULTS_FOLDER)))
        send_text(
            str(RESULTS_FOLDER),
            "Falta validacion temporal sellada antes de afirmar capacidad definitiva. "
            "Si discovery supera la puerta, el siguiente paso es comprar solo validacion; "
            "2025–2026 permanece intacto hasta entonces.",
        )
        _set_state("COMPLETE", dates, failures=[], scientific_output=str(scientific), manifest=result)
        send_text(str(RESULTS_FOLDER), str(result["final_telegram_verdict"]))
    except Exception as exc:
        _set_state("REPLAY_COMPLETE_ANALYSIS_FAILED", dates, analysis_error=f"{type(exc).__name__}: {exc}")
        send_text(
            str(RESULTS_FOLDER),
            "MATRIX + MBO CLASSIFICATION TEST | REPLAY COMPLETO, ANALISIS FALLIDO\n"
            f"{type(exc).__name__}: {exc}\nNo se repite Replay; se repara solo el analisis.",
        )
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
