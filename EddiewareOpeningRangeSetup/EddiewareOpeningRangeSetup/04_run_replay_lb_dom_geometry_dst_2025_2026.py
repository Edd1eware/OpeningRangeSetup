"""DST 2025-2026 replay for causal DOM_GEOMETRY Liquidity Burst research."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import absorption_breakout_research as research
from lb_dom_hypothesis_monitor import calculate, format_status, update_status_file
import replay_sync_runner_common_after_sync as replay_sync
from telegram_run_summary_after_sync import (
    clear_telegram_before_run,
    send_run_summary,
    send_text,
)


BASE_DIR = Path(__file__).resolve().parent
EXPORT_FOLDER = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator")
RESULTS_FOLDER = EXPORT_FOLDER / "trade_results_score"
RUN_ROOT = RESULTS_FOLDER / "visual_tests" / "04_run_replay_lb_clean_ab_dom_r3_dst_2025_2026_runs"
STATE_FILE = RUN_ROOT / "run_state.json"
AUDIT_MD = BASE_DIR / "contexto_features_atas" / "AUDITORIA_DISENO_LB_DOM_AB_LIMPIAS_R3_DST_2025_2026_20260721.md"
AUDIT_CSV = BASE_DIR / "contexto_features_atas" / "AUDITORIA_DISENO_LB_DOM_AB_LIMPIAS_R3_DST_2025_2026_20260721.csv"
CONTEXT_RESULT = BASE_DIR / "contexto_features_atas" / "RESULTADO_LB_DOM_AB_LIMPIAS_R3_DST_2025_2026_20260721.md"
RUN_LABEL = "CODEX LB DOM ABSORCION VS CONTINUACION LIMPIAS R3"
REPLAY_TO_TIME = "10:30"
FROZEN_LAST_DATE = date(2026, 7, 17)
OBSERVATIONAL_NAMES = (
    "burst_events.csv",
    "burst_response_events.csv",
    "trade_inputs.csv",
    "trade_results.csv",
    "exporter_lifecycle_diagnostics.csv",
)
DOM_DIRECTIONS = {
    "DOM_Spread_Ticks": -1,
    "DOM_Directional_Microprice_Ticks": -1,
    "DOM_Directional_Depth_Imbalance_L1": -1,
    "DOM_Directional_Depth_Imbalance_L3": -1,
    "DOM_Directional_Depth_Imbalance_L5": -1,
    "DOM_Ahead_Depth_Per_Aggressive_L3": 1,
    "DOM_Ahead_L1_Concentration_L5": 1,
    "DOM_Directional_PullStack_1s": -1,
    "DOM_Directional_PullStack_3s": -1,
    "DOM_Ahead_Stack_Share_1s": 1,
    "DOM_Near_Churn_Per_Aggressive_1s": 1,
}


def _load_base_runner():
    path = BASE_DIR / "04_run_replay_score_trade_results_dst_2025_2026_after_sync.py"
    spec = importlib.util.spec_from_file_location("score_dst_base_for_dom", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load base replay runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE_RUNNER = _load_base_runner()
research.configure_feature_scope("DOM_ONLY")


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


def design_audit(dates: list[str]) -> tuple[pd.DataFrame, bool]:
    detector = (BASE_DIR / "12_LiquidityBurstDetector.cs").read_text(encoding="utf-8")
    exporter = (BASE_DIR / "ATASScoreTradeResultExporter.cs").read_text(encoding="utf-8")
    workspace_path = Path.home() / "AppData" / "Roaming" / "ATAS" / "Workspaces_v3" / "Eddieware_workspace.ws"
    workspace = workspace_path.read_text(encoding="utf-8") if workspace_path.exists() else ""
    built_dll = BASE_DIR / "bin" / "Debug" / "net10.0" / "EddiewareOpeningRangeSetup.dll"
    installed_dll = Path.home() / "AppData" / "Roaming" / "ATAS" / "Indicators" / "EddiewareOpeningRangeSetup.dll"
    dom_specs = [spec for spec in research.BURST_SPECS if spec.name.startswith("DOM_")]
    parsed = [datetime.strptime(value, "%d/%m/%Y").date() for value in dates]
    family_examples = [
        research._label_family(pd.Series({"Result_Label": "TP", "MAE_ticks": 10, "MFE_ticks": 60, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}))[0],
        research._label_family(pd.Series({"Result_Label": "SL", "MAE_ticks": 60, "MFE_ticks": 10, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}))[0],
        research._label_family(pd.Series({"Result_Label": "TP", "MAE_ticks": 25, "MFE_ticks": 60, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}))[0],
    ]
    expected_telegram = "Efectividad del DOM antes del movimiento : 69.6% 96 sesiones"
    actual_telegram = format_status({"percentage": 69.6, "sessions": 96})
    state_owned = not STATE_FILE.exists()
    if STATE_FILE.exists():
        try:
            state_owned = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("run_label") == RUN_LABEL
        except (OSError, json.JSONDecodeError):
            state_owned = False
    rows = [
        ("DETECTOR_VERSION", research.EXPECTED_BURST_VERSION, research.EXPECTED_BURST_VERSION in detector),
        ("DOM_FEATURE_COUNT", f"{len(dom_specs)} expected=11", len(dom_specs) == 11),
        ("DOM_ONLY_SCOPE", f"active predictors={len(research.FEATURE_NAMES)} expected=11", set(research.FEATURE_NAMES) == set(research.DOM_FEATURE_NAMES) and len(research.FEATURE_NAMES) == 11),
        ("NO_NON_DOM_PREDICTORS", "Every active predictor starts with DOM_", all(name.startswith("DOM_") for name in research.FEATURE_NAMES)),
        ("DOM_SCHEMA", "Every preregistered DOM feature is emitted by C#", all(spec.name in detector for spec in dom_specs)),
        ("DOM_CAUSAL_WINDOWS", "Every DOM window ends at t0 or earlier", all(spec.window_end_seconds <= 0 for spec in dom_specs)),
        ("DIRECT_DEPTH_CALLBACK", "MarketDepthChanged is consumed in arrival order", "MarketDepthChanged(MarketDataArg depth)" in detector and "_lastMarketTradeUtc" in detector),
        ("DOM_VALIDITY_GUARD", "top-5, spread, crossed/stale checks", "DOM_INSUFFICIENT_LEVELS" in detector and "DOM_CROSSED_OR_STALE_TOUCH" in detector),
        ("NO_POST_T0_DOM", "No response/MAE/MFE fields among DOM predictors", not any(token in spec.name.lower() for spec in dom_specs for token in ("mfe", "mae", "response", "future", "result"))),
        ("WORKSPACE_DETECTOR", "LiquidityBurstDetector attached to saved chart", "ATAS.Indicators.LiquidityBurstDetector" in workspace),
        ("WORKSPACE_EXPORTER", "ATASScoreTradeResultExporter attached to saved chart", "ATAS.Indicators.ATASScoreTradeResultExporter" in workspace),
        ("WORKSPACE_CSV_ENABLED", "Detector ExportCsv=true and expected output folder", "ExportCsv" in workspace and "ExportCsv" in workspace and "true" in workspace[workspace.index("ExportCsv"):workspace.index("ExportCsv") + 80].lower() and "trade_results_score" in workspace),
        ("DLL_INSTALLED", "Installed indicator DLL equals current Debug build", built_dll.exists() and installed_dll.exists() and _sha256(built_dll) == _sha256(installed_dll)),
        ("X10_ONLY", "Run plan contains X10_R1 only", replay_sync.build_run_plan(quick=True, x10_only=True) == [("X10_R1", "X10", replay_sync.X10_TIMEOUT_SECONDS)]),
        ("DST_SCOPE", f"{len(dates)} dates; {min(parsed)} -> {max(parsed)}", bool(parsed) and all(value.year in (2025, 2026) for value in parsed)),
        ("TRADING_UNCHANGED", "DOM fields are observational; exporter change is Telegram text only", "DOM_Ahead_Depth_Per_Aggressive_L3" not in exporter and "telegram_lb_hypothesis.txt" in exporter),
        ("CLEAN_AB_TARGET", "Model target is clean absorption versus clean continuation; C is abstention", research.MODEL_FAMILIES == (research.FAMILY_ABSORPTION, research.FAMILY_CONTINUATION)),
        ("THREE_FAMILY_LEDGER", "Every trade is still grouped A, B or C from terminal MAE/MFE", family_examples == [research.FAMILY_ABSORPTION, research.FAMILY_CONTINUATION, research.FAMILY_VARIABLE]),
        ("TELEGRAM_FORMAT", actual_telegram, actual_telegram == expected_telegram),
        ("R3_ISOLATED_ROOT", "New R3 root is empty/new or owned by this exact run label", state_owned and (not RUN_ROOT.exists() or STATE_FILE.exists())),
        ("OUTCOME_ONLY_PATH", "MAE/MFE organize labels but are excluded from predictor specifications", not any(token in spec.name.lower() for spec in research.ALL_SPECS for token in ("mae", "mfe"))),
        ("PRIMARY_HYPOTHESIS", "Wall ahead/aggression preregistered ABSORPTION > CONTINUATION", DOM_DIRECTIONS.get("DOM_Ahead_Depth_Per_Aggressive_L3") == 1),
    ]
    audit = pd.DataFrame(rows, columns=["check", "evidence", "passed"])
    passed = bool(audit["passed"].all())
    AUDIT_CSV.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_CSV, index=False)

    lines = [
        "# Auditoría de diseño — LB DOM absorción vs continuación limpias R3",
        "",
        f"Estado: **{'PASS' if passed else 'FAIL'}**.",
        "",
        "## Enfoque preservado",
        "",
        "Se detecta primero el Liquidity Burst y se fotografía el DOM disponible en el mismo cutoff causal. "
        "MAE/MFE y el resultado sólo etiquetan después: absorción limpia, continuación limpia o trade variable; nunca predicen la misma entrada. "
        "El target primario es A vs B; C se conserva como abstención descriptiva y no diluye la separación limpia.",
        "",
        "No se agregan Heatmap, Smart Tape ni DOM Power al chart de replay: son visualizaciones del mismo stream y no "
        "exportan columnas adicionales. El detector ya está adjunto y consume MarketDepthChanged directamente.",
        "",
        "## Checklist",
        "",
        "| Control | Evidencia | Pasó |",
        "| --- | --- | ---: |",
    ]
    for row in audit.itertuples(index=False):
        lines.append(f"| {row.check} | {row.evidence} | {int(row.passed)} |")
    AUDIT_MD.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return audit, passed


def first_telegram_message(dates: list[str]) -> str:
    eta_hours = len(dates) * replay_sync.SPEED_DEFAULT_SECONDS["X10"] / 3600
    return f"""LIQUIDITY BURST | ABSORCION VS CONTINUACION LIMPIAS
PROPUESTO POR CODEX — DOM_GEOMETRY DST 2025–2026 R3 LIMPIA

OBJETIVO UNICO:
Detectar primero el Liquidity Burst y, usando solamente features disponibles en t0, separar A) ABSORCION LIMPIA de B) CONTINUACION LIMPIA. C) TRADE VARIABLE se conserva como abstencion/descriptiva; no es el target primario. No cambia entrada, SL, TP ni gestion.

COMO SE ORGANIZAN:
- ABSORCION LIMPIA: TP con MAE <=10 ticks y MFE >= TP inicial.
- CONTINUACION LIMPIA: SL con MFE <=10 ticks y MAE >= SL inicial.
- TRADE VARIABLE: outcome terminal con MAE/MFE validos que no cumple ninguna trayectoria limpia. Se conserva su sesgo MFE/TP vs MAE/SL.

QUE SE MIDE Y POR QUE:
1) Spread y microprice direccional: vacio y presion inmediata del touch.
2) Imbalance de profundidad L1/L3/L5: geometria transversal del libro.
3) Profundidad pasiva delante por agresion y concentracion L1/L5: pared defensiva/absorcion.
4) Pull-stack 1s/3s y stack share delante: retirada o reposicion de liquidez.
5) Churn top-5 por volumen agresivo: resistencia pasiva frente al ataque.
6) Validez del snapshot, niveles, best bid/ask y conteos: cobertura y auditoria; valores invalidos no se imputan.

HIPOTESIS PRIMARIA:
DOM_Ahead_Depth_Per_Aggressive_L3 debe ser mayor en ABSORCION LIMPIA que en CONTINUACION LIMPIA. Telegram muestra AUC A-vs-B y conteos, no movimiento a 1s:
Efectividad del DOM antes del movimiento : xx% xx sesiones.

El porcentaje sigue siendo AUC causal A-vs-B. Los conteos y la familia A/B/C permanecen en el detalle de los trades y en el reporte, sin sobrecargar esta linea de progreso.

INDICADORES DEL GRAFICO:
Liquidity Burst Detector v5 DOM, ATAS Score Trade Result Exporter, CVD y visual OR ya estan adjuntos. No se agrega un heatmap/DOM visual redundante porque no exporta features y aumenta carga X10.

CONTROL DE CONTAMINACION:
La R2 queda archivada como exploratoria y no se reutiliza como validacion. Esta R3 empieza desde cero con manifiesto fijo de 256 sesiones hasta 17/07/2026. Respuestas futuras a 1/3/5s, MAE/MFE y outcomes no son predictores.

CORRIDA:
Historia X10 unicamente | X1 deshabilitado.
{len(dates)} sesiones: {dates[0]} -> {dates[-1]}.
ETA mecanico inicial: ~{eta_hours:.1f} h; se recalibra con la mediana real.
Telegram enviara detalle de cada trade, ETA, porcentaje provisional, resumen final, datos y graficas."""


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


def _capture_observational_files() -> None:
    target = RUN_ROOT / "observational"
    target.mkdir(parents=True, exist_ok=True)
    for name in OBSERVATIONAL_NAMES:
        source = RESULTS_FOLDER / name
        if source.exists():
            shutil.copy2(source, target / name)


def _dom_metrics(dataset: pd.DataFrame) -> pd.DataFrame:
    eligible = dataset.loc[
        dataset["causal_row_flag"].astype(bool)
        & dataset["family"].isin(research.ANALYSIS_FAMILIES)
    ].copy()
    if "Detector_VERSION" in eligible:
        eligible = eligible.loc[eligible["Detector_VERSION"].astype(str).eq(research.EXPECTED_BURST_VERSION)]
    rows: list[dict[str, object]] = []
    rng = np.random.default_rng(20260720)
    for feature, orientation in DOM_DIRECTIONS.items():
        values = pd.to_numeric(eligible.get(feature), errors="coerce")
        valid = values.notna() & np.isfinite(values)
        frame = eligible.loc[valid].copy()
        score = orientation * values.loc[valid]
        n_a = int(frame["family"].eq(research.FAMILY_ABSORPTION).sum())
        n_c = int(frame["family"].eq(research.FAMILY_VARIABLE).sum())
        n_b = int(frame["family"].eq(research.FAMILY_CONTINUATION).sum())
        auc_a_c = np.nan
        auc_c_b = np.nan
        auc_a_b = np.nan
        permutation_p = np.nan

        score_array = score.to_numpy(float)

        def pair_auc(scores: np.ndarray, labels: np.ndarray, high_family: str, low_family: str) -> float:
            high = scores[labels == high_family]
            low = scores[labels == low_family]
            comparisons = high[:, None] - low[None, :]
            return float(np.mean((comparisons > 0) + 0.5 * (comparisons == 0)))

        labels = frame["family"].astype(str).to_numpy()
        if n_a >= 2 and n_c >= 2:
            auc_a_c = pair_auc(score_array, labels, research.FAMILY_ABSORPTION, research.FAMILY_VARIABLE)
        if n_c >= 2 and n_b >= 2:
            auc_c_b = pair_auc(score_array, labels, research.FAMILY_VARIABLE, research.FAMILY_CONTINUATION)
        if n_a >= 2 and n_b >= 2:
            clean_mask = np.isin(labels, research.MODEL_FAMILIES)
            clean_scores = score_array[clean_mask]
            clean_labels = labels[clean_mask]
            auc_a_b = pair_auc(
                clean_scores,
                clean_labels,
                research.FAMILY_ABSORPTION,
                research.FAMILY_CONTINUATION,
            )
            hits = 0
            for _ in range(2000):
                shuffled = rng.permutation(clean_labels)
                permuted = pair_auc(
                    clean_scores,
                    shuffled,
                    research.FAMILY_ABSORPTION,
                    research.FAMILY_CONTINUATION,
                )
                hits += permuted >= auc_a_b
            permutation_p = (hits + 1) / 2001
        clean_eligible = eligible["family"].isin(research.MODEL_FAMILIES).sum()
        clean_valid = n_a + n_b
        rows.append({
            "feature": feature,
            "expected_raw": "A>B" if orientation > 0 else "B>A",
            "expected_oriented": "A>B",
            "eligible_all_families": len(eligible),
            "eligible_clean_A_B": int(clean_eligible),
            "valid_all_families": len(frame),
            "valid_clean_A_B": clean_valid,
            "coverage_clean_A_B": clean_valid / clean_eligible if clean_eligible else 0.0,
            "n_a": n_a,
            "n_c": n_c,
            "n_b": n_b,
            "auc_A_C": auc_a_c,
            "auc_C_B": auc_c_b,
            "auc_A_B": auc_a_b,
            "permutation_p_one_sided": permutation_p,
        })
    return pd.DataFrame(rows)


def _document_final(analysis: dict[str, object]) -> tuple[str, Path]:
    dataset = pd.read_csv(Path(analysis["output_folder"]) / "engineered_features.csv", low_memory=False)
    metrics = _dom_metrics(dataset)
    metrics.to_csv(Path(analysis["output_folder"]) / "dom_geometry_metrics.csv", index=False)
    primary = metrics.loc[metrics["feature"].eq("DOM_Ahead_Depth_Per_Aggressive_L3")].iloc[0]
    valid_auc = pd.to_numeric(metrics["auc_A_B"], errors="coerce")
    family_mean = float(valid_auc.mean()) if valid_auc.notna().any() else np.nan

    variable_path = dataset.loc[dataset["family"].eq(research.FAMILY_VARIABLE)].copy()
    primary_values = pd.to_numeric(dataset.get("DOM_Ahead_Depth_Per_Aggressive_L3"), errors="coerce")
    reference = dataset.loc[
        dataset["family"].isin(research.ANALYSIS_FAMILIES) & primary_values.notna(),
        ["fecha", "BurstId", "DOM_Ahead_Depth_Per_Aggressive_L3"],
    ].copy()
    reference["dom_absorption_percentile"] = pd.to_numeric(
        reference["DOM_Ahead_Depth_Per_Aggressive_L3"], errors="coerce"
    ).rank(method="average", pct=True)
    variable_path = variable_path.merge(
        reference[["fecha", "BurstId", "dom_absorption_percentile"]],
        on=["fecha", "BurstId"],
        how="left",
    )
    percentile = pd.to_numeric(variable_path["dom_absorption_percentile"], errors="coerce")
    variable_path["dom_hypothesis_organization"] = np.select(
        [percentile.isna(), percentile >= (2 / 3), percentile <= (1 / 3)],
        ["DOM_UNAVAILABLE", "DOM_LEAN_ABSORPTION", "DOM_LEAN_CONTINUATION"],
        default="DOM_MIDDLE_VARIABLE",
    )
    variable_columns = [
        column for column in (
            "fecha", "BurstId", "family", "family_reason", "Result_Label",
            "MAE_ticks", "MFE_ticks", "Initial_SL_ticks", "Initial_TP_ticks",
            "path_mae_fraction_of_sl", "path_mfe_fraction_of_tp", "variable_path_shape",
            "DOM_Ahead_Depth_Per_Aggressive_L3", "dom_absorption_percentile",
            "dom_hypothesis_organization",
        ) if column in variable_path.columns
    ]
    variable_path[variable_columns].to_csv(
        Path(analysis["output_folder"]) / "variable_trade_dom_organization.csv", index=False
    )

    promising = bool(
        primary["valid_clean_A_B"] >= 20
        and primary["coverage_clean_A_B"] >= 0.75
        and primary["auc_A_B"] >= 0.60
        and primary["permutation_p_one_sided"] < 0.10
        and family_mean >= 0.55
    )
    decision = "PROMETEDOR" if promising else "NO PROMETEDOR / DETENER ESTA LINEA"
    lines = [
        "# Resultado LB DOM — absorción vs continuación limpias DST 2025–2026",
        "",
        f"Decisión preregistrada: **{decision}**.",
        "",
        "La métrica primaria es AUC A–B orientada para que >0.50 apoye ABSORCIÓN LIMPIA sobre CONTINUACIÓN LIMPIA. C no entra al target ni al criterio. No es WR.",
        "",
        metrics.to_markdown(index=False, floatfmt=".4f"),
        "",
        f"AUC A–B media de la familia DOM: {family_mean:.4f}.",
        f"Hipótesis primaria: A–B={primary['auc_A_B']:.4f}; cobertura A/B {100 * primary['coverage_clean_A_B']:.1f}%; A={int(primary['n_a'])}; B={int(primary['n_b'])}; C descriptiva={int(primary['n_c'])}; p permutación unilateral={primary['permutation_p_one_sided']:.4f}.",
        "",
        "Criterio prometedor: >=20 eventos A/B con DOM válido, cobertura A/B >=75%, AUC primaria >=0.60, p unilateral <0.10 y AUC A/B media familiar >=0.55.",
        "La Familia C también queda organizada de forma descriptiva por trayectoria MFE/MAE y por terciles DOM en `variable_trade_dom_organization.csv`; estas columnas de resultado no entrenan predictores ni alteran trades.",
        "",
        f"Reporte científico completo: `{Path(analysis['output_folder']) / 'final_report.md'}`.",
    ]
    CONTEXT_RESULT.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_RESULT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return decision, CONTEXT_RESULT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--step", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = _read_state()
    configured_dates = replay_dates()
    # A long replay must retain the manifest frozen at its creation. Crossing
    # midnight can make a new trading date available, but it must not mutate or
    # block an already-active experiment.
    dates = list(state.get("dates", [])) if state and state.get("dates") else configured_dates
    if not dates:
        raise SystemExit("No DST 2025-2026 replay dates are currently available")
    audit, passed_audit = design_audit(dates)
    print(audit.to_string(index=False))
    print(f"AUDIT={'PASS' if passed_audit else 'FAIL'} | {AUDIT_MD}")
    print(f"DATES={len(dates)} | {dates[0]} -> {dates[-1]}")
    if not passed_audit:
        raise SystemExit("Design audit failed; ATAS Replay was not launched")
    if args.prepare_only or args.audit_only:
        print("PREPARE/AUDIT ONLY: Replay and Telegram were not touched.")
        return 0

    fresh = state is None
    if state and state.get("status") == "COMPLETE":
        raise SystemExit(f"DOM replay already complete: {RUN_ROOT}")
    if state and state.get("dates") != dates:
        raise SystemExit("Active DOM run date manifest differs from current manifest")

    BASE_RUNNER.DATES_DST = dates
    if fresh:
        BASE_RUNNER.reset_replay_run_state(RUN_ROOT)
        _set_state("ACTIVE", dates, audit="PASS", detector_version=research.EXPECTED_BURST_VERSION)
        clear_telegram_before_run(str(RESULTS_FOLDER))
        update_status_file(RESULTS_FOLDER)
        send_text(str(RESULTS_FOLDER), first_telegram_message(dates))
    else:
        _set_state("ACTIVE", dates, resumed=True)
        update_status_file(RESULTS_FOLDER)
        send_text(
            str(RESULTS_FOLDER),
            "LIQUIDITY BURST DOM A VS B LIMPIAS | REANUDACION DST 2025–2026\n"
            "Se conservan fechas completas y se llenan sólo huecos. C permanece como abstencion; trading y etiquetas no cambian.",
        )

    date_iso = [replay_sync.date_iso_from_replay(value) for value in dates]
    progress_meta = {
        "stage_index": 1,
        "stage_total": 1,
        "stage_label": "LB DOM: separar absorcion limpia vs continuacion limpia; C abstencion",
        "stage_period": f"{dates[0]} -> {dates[-1]}",
        "session_roots": [str(RUN_ROOT)],
        "run_label": RUN_LABEL,
        "stats_root": str(RUN_ROOT),
        "global_target": len(dates),
        "hypothesis_monitor_root": str(RESULTS_FOLDER),
    }
    passed, failures = replay_sync.run_replay_period(
        date_iso,
        output_folder=RUN_ROOT,
        run_plan=replay_sync.build_run_plan(quick=True, x10_only=True),
        report_prefix="lb_dom_clean_ab_dst_2025_2026_r3",
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
            "LIQUIDITY BURST DOM A VS B LIMPIAS | CORRIDA INCOMPLETA\n"
            f"Huecos/errores: {len(failures)}. No se publica conclusión parcial; relanzar reanuda sólo huecos.",
        )
        return 1

    _capture_observational_files()
    send_run_summary(str(RESULTS_FOLDER), dates, [], f"LIQUIDITY BURST DOM | {RUN_LABEL}")
    scientific = RUN_ROOT / "scientific_analysis"
    if scientific.exists():
        archive = RUN_ROOT / f"_archive_scientific_analysis_{datetime.now():%Y%m%d_%H%M%S}"
        shutil.move(str(scientific), str(archive))
    analysis = research.run_analysis(RESULTS_FOLDER, scientific)
    research.send_analysis_to_telegram(RESULTS_FOLDER, analysis)
    decision, document = _document_final(analysis)
    final_hypothesis = format_status(calculate(RESULTS_FOLDER))
    send_text(
        str(RESULTS_FOLDER),
        f"LIQUIDITY BURST DOM A VS B LIMPIAS | DECISION FINAL\n{final_hypothesis}\n{decision}\n"
        "El porcentaje es AUC causal de separación ABSORCION vs CONTINUACION LIMPIAS, no WR.",
    )
    _set_state(
        "COMPLETE",
        dates,
        failures=[],
        scientific_output=str(scientific),
        conclusion=decision,
        context_document=str(document),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
