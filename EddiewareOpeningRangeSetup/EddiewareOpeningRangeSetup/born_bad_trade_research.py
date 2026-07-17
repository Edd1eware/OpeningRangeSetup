"""Investigacion causal de trades que nacen mal (Grupo D).

Es un analizador observacional. No escribe archivos consumidos por ATAS, no
modifica entradas/salidas y usa MFE/MAE/resultado exclusivamente como etiquetas.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import absorption_breakout_research as base


TELEGRAM_TITLE = "ANALISIS  FAMILIAS A, B, C, ETC.\nGRUPO D - TRADES QUE NACEN MAL"
RESULT_TICKS_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")


DERIVED_FEATURES = [
    "seconds_from_open",
    "minute_from_open",
    "weekday_index",
    "month_index",
    "execution_side_sign",
    "or_position_fraction",
    "distance_nearest_or_edge_ticks",
    "distance_nearest_profile_reference_ticks",
    "vwap_poc_spread_ticks",
    "signed_velocity_decay_1_5",
    "signed_delta_decay_1_5",
    "execution_cvd_alignment",
]


def _result_ticks(frame: pd.DataFrame) -> pd.Series:
    result = pd.Series(np.nan, index=frame.index, dtype=float)
    for column in ("Result_After_Slippage_Ticks", "result TP SL BE"):
        if column not in frame:
            continue
        parsed = frame[column].astype(str).str.extract(f"({RESULT_TICKS_PATTERN.pattern})", expand=False)
        result = result.fillna(pd.to_numeric(parsed, errors="coerce"))
    labels = frame.get("Result_Label", pd.Series("", index=frame.index)).astype(str).str.upper()
    result = result.mask(result.isna() & labels.eq("TP"), 1.0)
    result = result.mask(result.isna() & labels.eq("SL"), -1.0)
    result = result.mask(result.isna() & labels.eq("BE"), 0.0)
    return result


def _add_causal_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    timestamp = pd.to_datetime(frame["prediction_timestamp"], utc=True, errors="coerce")
    ny = timestamp.dt.tz_convert("America/New_York")
    frame["seconds_from_open"] = (
        (ny.dt.hour * 3600 + ny.dt.minute * 60 + ny.dt.second) - (9 * 3600 + 30 * 60)
    )
    frame["minute_from_open"] = frame["seconds_from_open"] / 60.0
    frame["weekday_index"] = ny.dt.weekday
    frame["month_index"] = ny.dt.month

    execution_side = frame.get("ExecutionSide", pd.Series("", index=frame.index)).astype(str).str.upper()
    frame["execution_side_sign"] = np.where(execution_side.eq("BUY"), 1.0, -1.0)
    frame["or_position_fraction"] = (
        pd.to_numeric(frame.get("Dist_OR_Low_Ticks"), errors="coerce") /
        pd.to_numeric(frame.get("OR_WidthTicks"), errors="coerce").abs().clip(lower=1)
    )
    frame["distance_nearest_or_edge_ticks"] = pd.concat(
        [
            pd.to_numeric(frame.get("Dist_OR_High_Ticks"), errors="coerce").abs(),
            pd.to_numeric(frame.get("Dist_OR_Low_Ticks"), errors="coerce").abs(),
        ],
        axis=1,
    ).min(axis=1)
    profile_columns = [
        "Dist_POC_Ticks", "Dist_VAH_Ticks", "Dist_VAL_Ticks",
        "Dist_HVN_Ticks", "Dist_LVN_Ticks",
    ]
    frame["distance_nearest_profile_reference_ticks"] = frame[profile_columns].apply(
        pd.to_numeric, errors="coerce"
    ).abs().min(axis=1)
    frame["vwap_poc_spread_ticks"] = (
        pd.to_numeric(frame.get("Dist_VWAP_Ticks"), errors="coerce") -
        pd.to_numeric(frame.get("Dist_POC_Ticks"), errors="coerce")
    ).abs()
    sign = frame["execution_side_sign"]
    frame["signed_velocity_decay_1_5"] = sign * (
        pd.to_numeric(frame.get("Velocity1s"), errors="coerce") -
        pd.to_numeric(frame.get("Velocity5s"), errors="coerce")
    )
    frame["signed_delta_decay_1_5"] = sign * (
        pd.to_numeric(frame.get("Delta1s"), errors="coerce") -
        pd.to_numeric(frame.get("Delta5s"), errors="coerce") / 5.0
    )
    cvd = pd.to_numeric(frame.get("Cumulative_Delta_AtEntry"), errors="coerce")
    frame["execution_cvd_alignment"] = sign * np.sign(cvd)
    return frame


def _classify(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["realized_ticks_for_label"] = _result_ticks(frame)
    frame["MFE_ticks"] = pd.to_numeric(frame.get("MFE_ticks"), errors="coerce")
    frame["MAE_ticks"] = pd.to_numeric(frame.get("MAE_ticks"), errors="coerce")
    result = frame.get("Result_Label", pd.Series("", index=frame.index)).astype(str).str.upper()
    winner = frame["realized_ticks_for_label"].gt(0) | result.eq("TP")
    loser = frame["realized_ticks_for_label"].lt(0) | result.eq("SL")

    frame["born_bad_group"] = "EXCLUDED_OTHER_EXIT"
    frame["born_bad_reason"] = "BE/time/otra salida; no entra en A/B/C/D"
    frame.loc[winner, "born_bad_group"] = "A_WINNER"
    frame.loc[winner, "born_bad_reason"] = "Resultado realizado positivo"
    frame.loc[loser & frame["MFE_ticks"].gt(30), "born_bad_group"] = "B_LOSER_MFE_GT_30"
    frame.loc[loser & frame["MFE_ticks"].gt(30), "born_bad_reason"] = "Perdedor con MFE > 30 ticks"
    normal = loser & frame["MFE_ticks"].gt(2) & frame["MFE_ticks"].le(30)
    frame.loc[normal, "born_bad_group"] = "C_LOSER_MFE_3_TO_30"
    frame.loc[normal, "born_bad_reason"] = "Perdedor con 2 < MFE <= 30 ticks"
    born_bad = loser & frame["MFE_ticks"].le(2)
    frame.loc[born_bad, "born_bad_group"] = "D_BORN_BAD_MFE_LE_2"
    frame.loc[born_bad, "born_bad_reason"] = "Perdedor con MFE <= 2 ticks"
    return frame


def _comparison_dataset(dataset: pd.DataFrame, comparator: str) -> pd.DataFrame:
    if comparator == "A":
        keep = dataset["born_bad_group"].isin(["D_BORN_BAD_MFE_LE_2", "A_WINNER"])
        compared = dataset.loc[keep].copy()
        compared["family"] = np.where(
            compared["born_bad_group"].eq("D_BORN_BAD_MFE_LE_2"),
            "A_TRUE_ABSORPTION",
            "B_CLEAN_BREAKOUT",
        )
    else:
        keep = dataset["born_bad_group"].isin(
            ["A_WINNER", "B_LOSER_MFE_GT_30", "C_LOSER_MFE_3_TO_30", "D_BORN_BAD_MFE_LE_2"]
        )
        compared = dataset.loc[keep].copy()
        compared["family"] = np.where(
            compared["born_bad_group"].eq("D_BORN_BAD_MFE_LE_2"),
            "A_TRUE_ABSORPTION",
            "B_CLEAN_BREAKOUT",
        )
    return compared


def _run_comparison(dataset: pd.DataFrame, comparator: str) -> dict[str, pd.DataFrame]:
    compared = _comparison_dataset(dataset, comparator)
    if compared.empty or compared["family"].nunique() < 2:
        empty = pd.DataFrame()
        return {"dataset": compared, "statistics": empty, "importance": empty,
                "validation": empty, "models": empty, "ranking": empty}
    statistics = base._statistical_tests(compared)
    importance, validation, models = base._model_and_rankings(compared, statistics)
    ranking = base._rankings(statistics, importance, validation)
    return {
        "dataset": compared,
        "statistics": statistics,
        "importance": importance,
        "validation": validation,
        "models": models,
        "ranking": ranking,
    }


def _feature_proposals() -> pd.DataFrame:
    rows = [
        ("seconds_from_open", "(entry_ny - 09:30 NY).total_seconds", "Régimen temporal de apertura", "HIGH", "EASY", "LOW", "AVAILABLE_NOW"),
        ("or_position_fraction", "(price-OR_low)/max(OR_width,1 tick)", "Entrada extendida o dentro del balance", "HIGH", "EASY", "LOW", "AVAILABLE_NOW"),
        ("execution_cvd_alignment", "side_sign*sign(session_CVD_at_entry)", "Conflicto con agresión acumulada", "HIGH", "EASY", "LOW", "AVAILABLE_NOW"),
        ("velocity_decay_1_5", "side_sign*(velocity_1s-velocity_5s)", "Impulso que se extingue al disparar", "HIGH", "EASY", "MEDIUM", "AVAILABLE_NOW"),
        ("delta_decay_1_5", "side_sign*(delta_1s-delta_5s/5)", "Agresión instantánea sin persistencia", "HIGH", "EASY", "MEDIUM", "AVAILABLE_NOW"),
        ("nearest_profile_reference", "min(|dPOC|,|dVAH|,|dVAL|,|dHVN|,|dLVN|)", "Choque inmediato contra liquidez estructural", "HIGH", "EASY", "LOW", "AVAILABLE_NOW"),
        ("prior_atr_ticks", "ATR_N de barras cerradas antes de entry", "Normaliza SL/OR por volatilidad", "HIGH", "MEDIUM", "LOW", "ADD_EXPORTER_NEXT"),
        ("overnight_range_ticks", "(ON_high-ON_low)/tick hasta 09:29:59", "Compresión/expansión previa", "HIGH", "MEDIUM", "LOW", "ADD_EXPORTER_NEXT"),
        ("opening_gap_atr", "(RTH_open-prior_settle)/prior_ATR", "Inventario overnight y repricing", "HIGH", "MEDIUM", "LOW", "ADD_EXPORTER_NEXT"),
        ("vwap_slope_ticks_per_min", "OLS slope VWAP causal en últimos N minutos", "Dirección/curvatura del valor negociado", "HIGH", "MEDIUM", "MEDIUM", "ADD_EXPORTER_NEXT"),
        ("poc_migration_ticks_per_min", "(POC_now-POC_Nmin_ago)/(N*min*tick)", "Migración del valor contra la entrada", "HIGH", "HARD", "MEDIUM", "ADD_EXPORTER_NEXT"),
        ("profile_shape_moments", "skew,kurtosis,modes de volumen por precio causal", "P/b/D/B/doble distribución sin etiqueta subjetiva", "MEDIUM", "HARD", "MEDIUM", "ADD_EXPORTER_LATER"),
        ("acceptance_dwell_ratio", "time_inside_level_band/window_before_entry", "Acceptance frente a rechazo instantáneo", "HIGH", "HARD", "MEDIUM", "ADD_EXPORTER_NEXT"),
        ("level_retest_count", "count(cross/retest causal de OR/VA/POC)", "Nivel debilitado por pruebas repetidas", "MEDIUM", "MEDIUM", "LOW", "ADD_EXPORTER_NEXT"),
        ("refill_after_sweep_ratio", "added_size/consumed_size antes de entry", "Absorción real frente a vacío de liquidez", "HIGH", "HARD", "HIGH", "REQUIRES_REPLAYABLE_BOOK"),
        ("book_imbalance_multilevel", "sum_bid_depth_L/sum_ask_depth_L", "Asimetría de profundidad preentrada", "MEDIUM", "HARD", "HIGH", "REQUIRES_REPLAYABLE_BOOK"),
    ]
    return pd.DataFrame(rows, columns=[
        "feature", "formula", "market_mechanism", "expected_impact",
        "implementation", "overfit_risk", "recommendation",
    ])


def _plots(dataset: pd.DataFrame, comparisons: dict[str, dict[str, pd.DataFrame]], output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    counts = dataset["born_bad_group"].value_counts()
    fig, ax = plt.subplots(figsize=(10, 5))
    counts.plot(kind="bar", ax=ax, color="#2563eb")
    ax.set_title("Familias de trades")
    ax.set_ylabel("Trades")
    fig.tight_layout()
    path = output / "group_counts.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    for label, comparison in comparisons.items():
        ranking = comparison["ranking"]
        if ranking.empty:
            continue
        top = ranking.head(10).iloc[::-1]
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.barh(top["feature"], top["evidence_score"], color="#dc2626")
        ax.set_title(f"Grupo D vs {label}: evidencia preentrada")
        ax.set_xlabel("Evidence score")
        fig.tight_layout()
        path = output / f"ranking_D_vs_{label}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)
    return paths


def _report(
    dataset: pd.DataFrame,
    comparisons: dict[str, dict[str, pd.DataFrame]],
    proposals: pd.DataFrame,
    output: Path,
) -> str:
    counts = dataset["born_bad_group"].value_counts().to_dict()
    causal = dataset.loc[dataset["causal_row_flag"]]
    lines = [
        "# Investigación cuantitativa — Trades que nacen mal",
        "",
        "## Resultado principal",
        "",
    ]
    robust_union: list[str] = []
    for comparison in comparisons.values():
        ranking = comparison["ranking"]
        if not ranking.empty:
            robust_union.extend(ranking.loc[ranking["robust_candidate"].eq(1), "feature"].tolist())
    robust_union = list(dict.fromkeys(robust_union))
    if robust_union:
        lines.append(
            "Las siguientes variables preentrada superaron el criterio estadístico pre-registrado: "
            + ", ".join(robust_union[:10])
            + ". Esto demuestra separación observacional, no autoriza todavía un filtro."
        )
    else:
        lines.append(
            "Ninguna variable disponible superó simultáneamente significancia corregida, tamaño de efecto "
            "y estabilidad cronológica. La hipótesis no queda demostrada con el dataset actual y no se "
            "autoriza modificar la estrategia."
        )
    lines.extend([
        "",
        "## Definición congelada",
        "",
        "- A: trade ganador (resultado realizado positivo).",
        "- B: trade perdedor con MFE > 30 ticks.",
        "- C: trade perdedor con 2 < MFE <= 30 ticks.",
        "- D: trade perdedor con MFE <= 2 ticks.",
        "- MFE, MAE, duración y resultado son etiquetas posteriores; nunca entran como features.",
        "",
        "## Muestra",
        "",
        f"- Filas Liquidity Burst unidas: {len(dataset)}.",
        f"- Filas causales válidas: {int(causal.shape[0])}.",
        f"- Grupo A: {counts.get('A_WINNER', 0)}.",
        f"- Grupo B: {counts.get('B_LOSER_MFE_GT_30', 0)}.",
        f"- Grupo C: {counts.get('C_LOSER_MFE_3_TO_30', 0)}.",
        f"- Grupo D: {counts.get('D_BORN_BAD_MFE_LE_2', 0)}.",
        "- Split cronológico congelado: 60% discovery, 20% validation, 20% holdout.",
    ])
    for label, title in (("A", "Grupo D vs Grupo A"), ("REST", "Grupo D vs todos los demás")):
        ranking = comparisons[label]["ranking"]
        lines.extend(["", f"## {title}", "", "| Feature | q permutación | |Cliff δ| | Overlap | Estable | Robusta |", "|---|---:|---:|---:|---:|---:|"])
        if ranking.empty:
            lines.append("| Muestra insuficiente | | | | | |")
        else:
            for _, row in ranking.head(12).iterrows():
                lines.append(
                    f"| {row['feature']} | {row.get('permutation_q_bh', np.nan):.4f} | "
                    f"{row.get('abs_cliffs_delta', np.nan):.3f} | {row.get('overlap_coefficient', np.nan):.3f} | "
                    f"{int(row.get('direction_stable_discovery_validation_holdout', 0) or 0)} | "
                    f"{int(row.get('robust_candidate', 0) or 0)} |"
                )
    lines.extend([
        "",
        "## Variables nuevas recomendadas para Build Alpha",
        "",
        "| Feature | Impacto | Implementación | Overfit | Estado | Mecanismo |",
        "|---|---|---|---|---|---|",
    ])
    for _, row in proposals.iterrows():
        lines.append(
            f"| {row['feature']} | {row['expected_impact']} | {row['implementation']} | "
            f"{row['overfit_risk']} | {row['recommendation']} | {row['market_mechanism']} |"
        )
    lines.extend([
        "",
        "## Orden mínimo de instrumentación siguiente",
        "",
        "1. ATR previo, overnight range y gap normalizado.",
        "2. Pendiente causal de VWAP y migración de POC/Value Area.",
        "3. Acceptance dwell ratio y número de retests de OR/VA/POC.",
        "4. Momentos matemáticos del perfil (skew, kurtosis y multimodalidad).",
        "5. Refill/book/icebergs sólo si Historia X10 entrega un stream reproducible; si no, se rechazan.",
        "",
        "## Salvaguardas",
        "",
        "- No se optimizaron parámetros, thresholds, TP, SL, trailing ni gestión.",
        "- No se creó ningún filtro de entrada.",
        "- No se usó información posterior a la entrada como predictor.",
        "- Ninguna ausencia de order book se rellenó o simuló.",
        "- Cualquier feature descubierta deberá validarse en una temporada futura no utilizada aquí.",
        "",
        f"Artefactos: `{output}`",
    ])
    return "\n".join(lines) + "\n"


def run_analysis(results_folder: Path, output_folder: Path | None = None) -> dict[str, object]:
    results_folder = Path(results_folder)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if output_folder is None:
        output_folder = Path(__file__).resolve().parent / "outputs" / f"born_bad_trade_research_{stamp}"
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    dataset, audit = base.build_dataset(results_folder)
    if dataset.empty:
        raise RuntimeError("No hay dataset causal Liquidity Burst suficiente.")
    dataset = _classify(_add_causal_features(dataset))

    original_names = list(base.FEATURE_NAMES)
    base.FEATURE_NAMES[:] = list(dict.fromkeys(original_names + DERIVED_FEATURES))
    try:
        comparisons = {
            "A": _run_comparison(dataset, "A"),
            "REST": _run_comparison(dataset, "REST"),
        }
    finally:
        base.FEATURE_NAMES[:] = original_names

    proposals = _feature_proposals()
    visuals = _plots(dataset, comparisons, output_folder / "visualizations")
    report = _report(dataset, comparisons, proposals, output_folder)

    identity = [
        "fecha", "prediction_timestamp", "split", "born_bad_group", "born_bad_reason",
        "Result_Label", "realized_ticks_for_label", "MFE_ticks", "MAE_ticks",
        "Trade_Duration", "Entry_price", "ExecutionSide", "canonical_source_file",
        "causal_row_flag",
    ]
    feature_columns = [c for c in original_names + DERIVED_FEATURES if c in dataset]
    dataset[[c for c in identity + feature_columns if c in dataset]].to_csv(
        output_folder / "grouped_trades.csv", index=False
    )
    audit.to_csv(output_folder / "dataset_audit.csv", index=False)
    proposals.to_csv(output_folder / "new_feature_proposals.csv", index=False)
    for label, comparison in comparisons.items():
        suffix = "D_vs_A" if label == "A" else "D_vs_all_others"
        for name in ("statistics", "importance", "validation", "models", "ranking"):
            comparison[name].to_csv(output_folder / f"{name}_{suffix}.csv", index=False)
    (output_folder / "final_report.md").write_text(report, encoding="utf-8")

    context = Path(__file__).resolve().parent / "contexto_features_atas"
    context.mkdir(parents=True, exist_ok=True)
    context_report = context / f"INVESTIGACION_TRADES_NACEN_MAL_{stamp}.md"
    shutil.copy2(output_folder / "final_report.md", context_report)

    counts = dataset["born_bad_group"].value_counts().to_dict()
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "Historia X10 únicamente",
        "replay_x1": "DESHABILITADO",
        "rows": len(dataset),
        "groups": counts,
        "output_folder": str(output_folder),
        "context_report": str(context_report),
        "trading_logic_changed": False,
        "filters_created": False,
        "holdout_opened_once": True,
    }
    (output_folder / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    (results_folder / "latest_born_bad_trade_research.txt").write_text(str(output_folder), encoding="utf-8")
    return {"report": report, "manifest": manifest, "visuals": visuals, "output_folder": output_folder}


def send_to_telegram(results_folder: Path, analysis: dict[str, object]) -> bool:
    from telegram_run_summary_after_sync import send_photo, send_text

    ok = send_text(str(results_folder), TELEGRAM_TITLE)
    for index, chunk in enumerate(base._telegram_chunks(str(analysis["report"])), start=1):
        ok = send_text(str(results_folder), f"[{index}] {chunk}") and ok
    for path in analysis["visuals"]:
        ok = send_photo(str(results_folder), str(path), TELEGRAM_TITLE) and ok
    return ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-folder", type=Path, required=True)
    parser.add_argument("--output-folder", type=Path, default=None)
    parser.add_argument("--telegram", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    analysis = run_analysis(args.results_folder, args.output_folder)
    print(json.dumps(analysis["manifest"], indent=2, default=str))
    if args.telegram and not send_to_telegram(args.results_folder, analysis):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
