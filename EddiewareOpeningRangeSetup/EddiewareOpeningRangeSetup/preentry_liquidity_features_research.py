"""Research causal MBP+tape features available before Liquidity Burst entry.

Post-burst response fields are used only to define scientific labels elsewhere;
they are never predictors here. Every extracted market-data row is bounded by the
original prediction timestamp.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


NY_ZONE = ZoneInfo("America/New_York")
WINDOWS = (1, 3, 5, 10)
FAMILIES = ("A_TRUE_ABSORPTION", "B_CLEAN_BREAKOUT")

BASELINE_FEATURES = [
    "Profile_Local_Maxima_Count",
    "Previous_Delta_AtEntry",
    "Pre_Approach_Pause_Seconds",
    "Prior_Closed_ATR3_Ticks_AtEntry",
    "Prior_Closed_ATR5_Ticks_AtEntry",
    "Flow_3_5_DirectionalNetDelta",
    "Flow_3_5_GrossAggressive",
    "BuySellRatio",
    "Directional_VWAP_Distance_Ticks_AtEntry",
    "Signal_To_Entry_Latency_Milliseconds",
]

CORE_MBP_FEATURES = [
    "burst_w1_add_to_aggressive",
    "burst_w1_refill_to_remove",
    "burst_w1_depth_balance",
    "burst_w1_recovery_from_min",
    "burst_w1_refill_latency_ms",
    "burst_w1_aggressive_volume",
    "reference_w3_add_to_aggressive",
    "reference_w3_refill_to_remove",
    "reference_w3_depth_balance",
    "reference_w3_recovery_from_min",
    "reference_w3_refill_latency_ms",
    "reference_w3_aggressive_volume",
]


def _seconds(timestamp: object) -> float | None:
    if timestamp is None or (isinstance(timestamp, float) and np.isnan(timestamp)):
        return None
    try:
        stamp = pd.Timestamp(timestamp)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        stamp = stamp.tz_convert(NY_ZONE)
        return stamp.hour * 3600 + stamp.minute * 60 + stamp.second + stamp.microsecond / 1e6
    except (TypeError, ValueError):
        return None


def _read_market_file(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns + ["seconds"])
    try:
        frame = pd.read_csv(path, usecols=columns, on_bad_lines="skip", low_memory=False)
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame(columns=columns + ["seconds"])
    frame["seconds"] = pd.to_timedelta(frame["time_ny"], errors="coerce").dt.total_seconds()
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    if "volume" in frame:
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    return frame.dropna(subset=["seconds", "price", "volume"]).sort_values("seconds", kind="stable").reset_index(drop=True)


def prepare_mbp(frame: pd.DataFrame, cutoff_seconds: float) -> pd.DataFrame:
    frame = frame.loc[frame["seconds"].le(cutoff_seconds)].copy()
    if frame.empty:
        frame["previous_volume"] = pd.Series(dtype=float)
        frame["depth_change"] = pd.Series(dtype=float)
        return frame
    frame["previous_volume"] = frame.groupby(["side", "price"], sort=False)["volume"].shift(1)
    frame["depth_change"] = frame["volume"] - frame["previous_volume"]
    return frame


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else np.nan


def level_window_features(
    mbp: pd.DataFrame,
    tape: pd.DataFrame,
    *,
    cutoff_seconds: float,
    window_seconds: int,
    level: float,
    burst_side: str,
    mbp_available: bool = True,
    tape_available: bool = True,
) -> dict[str, float]:
    """Aggregate one attacked price level without reading after cutoff."""
    start = cutoff_seconds - window_seconds
    passive_side = "Ask" if burst_side.upper() == "BUY" else "Bid"
    aggressive_direction = "Buy" if burst_side.upper() == "BUY" else "Sell"
    level_history = mbp.loc[
        mbp["side"].eq(passive_side) & np.isclose(mbp["price"], level)
    ].copy()
    window = level_history.loc[level_history["seconds"].ge(start)].copy()
    before = level_history.loc[level_history["seconds"].lt(start)]
    start_depth = float(before["volume"].iloc[-1]) if not before.empty else np.nan
    end_depth = float(level_history["volume"].iloc[-1]) if not level_history.empty else np.nan
    depth_values = window["volume"].tolist()
    if np.isfinite(start_depth):
        depth_values.insert(0, start_depth)
    min_depth = float(np.min(depth_values)) if depth_values else np.nan
    max_depth = float(np.max(depth_values)) if depth_values else np.nan

    known = window.dropna(subset=["depth_change"])
    additions = float(known.loc[known["depth_change"].gt(0), "depth_change"].sum())
    removals = float(-known.loc[known["depth_change"].lt(0), "depth_change"].sum())
    add_events = int(known["depth_change"].gt(0).sum())
    remove_events = int(known["depth_change"].lt(0).sum())

    trades = tape.loc[tape["seconds"].between(start, cutoff_seconds, inclusive="both")]
    trades = trades.loc[np.isclose(trades["price"], level)].copy()
    aggressive = trades.loc[trades["direction"].eq(aggressive_direction)]
    counter = trades.loc[~trades["direction"].eq(aggressive_direction)]
    aggressive_volume = float(aggressive["volume"].sum())
    counter_volume = float(counter["volume"].sum())

    refill_latency = np.nan
    refill_events_after = 0
    refill_volume_after = 0.0
    if not aggressive.empty:
        first_aggression = float(aggressive["seconds"].iloc[0])
        refill = known.loc[known["depth_change"].gt(0) & known["seconds"].ge(first_aggression)]
        if not refill.empty:
            refill_latency = 1000 * (float(refill["seconds"].iloc[0]) - first_aggression)
            refill_events_after = int(len(refill))
            refill_volume_after = float(refill["depth_change"].sum())

    last_update_age = (
        1000 * (cutoff_seconds - float(level_history["seconds"].iloc[-1]))
        if not level_history.empty
        else np.nan
    )
    values = {
        "level_seen": float(not level_history.empty) if mbp_available else np.nan,
        "update_count": float(len(window)),
        "known_change_count": float(len(known)),
        "start_depth": start_depth,
        "end_depth": end_depth,
        "min_depth": min_depth,
        "max_depth": max_depth,
        "depth_net_change": end_depth - start_depth if np.isfinite(start_depth) and np.isfinite(end_depth) else np.nan,
        "depth_balance": _safe_ratio(additions - removals, additions + removals),
        "add_volume": additions,
        "remove_volume": removals,
        "add_events": float(add_events),
        "remove_events": float(remove_events),
        "refill_to_remove": _safe_ratio(additions, removals),
        "recovery_from_min": end_depth - min_depth if np.isfinite(end_depth) and np.isfinite(min_depth) else np.nan,
        "level_survived": float(end_depth > 0) if np.isfinite(end_depth) else np.nan,
        "last_update_age_ms": last_update_age,
        "aggressive_volume": aggressive_volume,
        "counter_volume": counter_volume,
        "execution_imbalance": _safe_ratio(aggressive_volume - counter_volume, aggressive_volume + counter_volume),
        "add_to_aggressive": _safe_ratio(additions, aggressive_volume),
        "remove_to_aggressive": _safe_ratio(removals, aggressive_volume),
        "refill_latency_ms": refill_latency,
        "refill_events_after_aggression": float(refill_events_after),
        "refill_volume_after_aggression": refill_volume_after,
    }
    mbp_only = {
        "update_count", "known_change_count", "start_depth", "end_depth", "min_depth", "max_depth",
        "depth_net_change", "depth_balance", "add_volume", "remove_volume", "add_events", "remove_events",
        "refill_to_remove", "recovery_from_min", "level_survived", "last_update_age_ms",
    }
    tape_only = {"aggressive_volume", "counter_volume", "execution_imbalance"}
    combined = {
        "add_to_aggressive", "remove_to_aggressive", "refill_latency_ms",
        "refill_events_after_aggression", "refill_volume_after_aggression",
    }
    if not mbp_available or level_history.empty:
        for name in mbp_only | combined:
            values[name] = np.nan
    if not tape_available:
        for name in tape_only | combined:
            values[name] = np.nan
    return values


def extract_features(outcomes: pd.DataFrame, events: pd.DataFrame, book_folder: Path) -> pd.DataFrame:
    joined = outcomes.merge(events, on="BurstId", how="left", validate="one_to_one")
    rows: list[dict[str, object]] = []
    for row in joined.to_dict("records"):
        cutoff = _seconds(row.get("prediction_timestamp"))
        event_time = _seconds(row.get("Timestamp_UTC"))
        publish_time = _seconds(row.get("Detector_Publish_Timestamp_UTC"))
        date = str(row["fecha"])
        mbp_path = book_folder / f"mbp_{date}_NY.csv"
        tape_path = book_folder / f"tape_{date}_NY.csv"
        mbp_raw = _read_market_file(mbp_path, ["time_ny", "side", "price", "volume"])
        tape = _read_market_file(tape_path, ["time_ny", "price", "volume", "direction"])
        mbp = prepare_mbp(mbp_raw, cutoff) if cutoff is not None else prepare_mbp(mbp_raw.iloc[0:0], 0)
        tape = tape.loc[tape["seconds"].le(cutoff)].copy() if cutoff is not None else tape.iloc[0:0].copy()
        result: dict[str, object] = {
            "fecha": date,
            "BurstId": row["BurstId"],
            "split": row["split"],
            "family": row["family"],
            "prediction_timestamp": row["prediction_timestamp"],
            "burst_timestamp_utc": row.get("Timestamp_UTC"),
            "detector_publish_timestamp_utc": row.get("Detector_Publish_Timestamp_UTC"),
            "burst_side": row.get("Side"),
            "burst_price": row.get("Price"),
            "reference_level": row.get("Broken_Reference_Level"),
            "cutoff_seconds_ny": cutoff,
            "event_seconds_ny": event_time,
            "publish_seconds_ny": publish_time,
            "causal_timestamp_valid": float(
                cutoff is not None
                and event_time is not None
                and publish_time is not None
                and event_time <= publish_time <= cutoff
            ),
            "mbp_file_exists": float(mbp_path.exists()),
            "tape_file_exists": float(tape_path.exists()),
            "mbp_rows_pre_cutoff": float(len(mbp)),
            "tape_rows_pre_cutoff": float(len(tape)),
        }
        burst_price = pd.to_numeric(pd.Series([row.get("Price")]), errors="coerce").iloc[0]
        reference = pd.to_numeric(pd.Series([row.get("Broken_Reference_Level")]), errors="coerce").iloc[0]
        for level_name, level in (("burst", burst_price), ("reference", reference)):
            if not np.isfinite(level) or cutoff is None:
                continue
            for window in WINDOWS:
                values = level_window_features(
                    mbp,
                    tape,
                    cutoff_seconds=cutoff,
                    window_seconds=window,
                    level=float(level),
                    burst_side=str(row.get("Side", "")),
                    mbp_available=mbp_path.exists() and not mbp.empty,
                    tape_available=tape_path.exists() and not tape.empty,
                )
                result.update({f"{level_name}_w{window}_{name}": value for name, value in values.items()})
        rows.append(result)
    return pd.DataFrame(rows)


def _cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) == 0 or len(b) == 0:
        return np.nan
    return float((np.greater.outer(a, b).sum() - np.less.outer(a, b).sum()) / (len(a) * len(b)))


def _bh(p_values: pd.Series) -> pd.Series:
    valid = p_values.dropna().sort_values()
    adjusted = pd.Series(np.nan, index=p_values.index, dtype=float)
    if valid.empty:
        return adjusted
    n = len(valid)
    raw = valid.to_numpy() * n / np.arange(1, n + 1)
    corrected = np.minimum.accumulate(raw[::-1])[::-1].clip(max=1)
    adjusted.loc[valid.index] = corrected
    return adjusted


def analyze_features(frame: pd.DataFrame) -> pd.DataFrame:
    metadata = {
        "cutoff_seconds_ny", "event_seconds_ny", "publish_seconds_ny", "causal_timestamp_valid",
        "mbp_file_exists", "tape_file_exists", "mbp_rows_pre_cutoff", "tape_rows_pre_cutoff",
    }
    features = [
        column for column in frame.columns
        if (column.startswith("burst_w") or column.startswith("reference_w"))
        and column not in metadata
        and not column.endswith("_level_seen")
    ]
    ab = frame.loc[frame["family"].isin(FAMILIES)].copy()
    rows = []
    for feature in features:
        discovery = ab.loc[ab["split"].eq("discovery")]
        a = pd.to_numeric(discovery.loc[discovery["family"].eq(FAMILIES[0]), feature], errors="coerce").dropna().to_numpy()
        b = pd.to_numeric(discovery.loc[discovery["family"].eq(FAMILIES[1]), feature], errors="coerce").dropna().to_numpy()
        p = mannwhitneyu(a, b, alternative="two-sided").pvalue if len(a) >= 3 and len(b) >= 3 else np.nan
        directions = []
        split_counts = {}
        for split in ("discovery", "validation", "holdout"):
            subset = ab.loc[ab["split"].eq(split)]
            av = pd.to_numeric(subset.loc[subset["family"].eq(FAMILIES[0]), feature], errors="coerce").dropna()
            bv = pd.to_numeric(subset.loc[subset["family"].eq(FAMILIES[1]), feature], errors="coerce").dropna()
            split_counts[f"{split}_n_a"] = len(av)
            split_counts[f"{split}_n_b"] = len(bv)
            difference = av.median() - bv.median() if len(av) >= 3 and len(bv) >= 3 else np.nan
            directions.append(np.sign(difference) if np.isfinite(difference) else np.nan)
        finite_directions = [value for value in directions if np.isfinite(value) and value != 0]
        stable = len(finite_directions) == 3 and len(set(finite_directions)) == 1
        coverage = 100 * pd.to_numeric(ab[feature], errors="coerce").notna().mean()
        rows.append({
            "feature": feature,
            "coverage_pct": coverage,
            "mann_whitney_p_discovery": p,
            "cliffs_delta_A_minus_B_discovery": _cliffs_delta(a, b),
            "median_A_discovery": float(np.median(a)) if len(a) else np.nan,
            "median_B_discovery": float(np.median(b)) if len(b) else np.nan,
            "direction_discovery": directions[0],
            "direction_validation": directions[1],
            "direction_holdout": directions[2],
            "direction_stable_all_splits": int(stable),
            **split_counts,
        })
    result = pd.DataFrame(rows)
    result["mann_whitney_q_bh"] = _bh(result["mann_whitney_p_discovery"])
    result["robust_candidate"] = (
        result["mann_whitney_q_bh"].le(0.10)
        & result["cliffs_delta_A_minus_B_discovery"].abs().ge(0.33)
        & result["direction_stable_all_splits"].eq(1)
        & result["coverage_pct"].ge(70)
    ).astype(int)
    return result.sort_values(
        ["robust_candidate", "mann_whitney_q_bh", "coverage_pct"],
        ascending=[False, True, False],
        na_position="last",
    ).reset_index(drop=True)


def model_comparison(feature_frame: pd.DataFrame, engineered_file: Path) -> pd.DataFrame:
    engineered = pd.read_csv(engineered_file)
    frame = feature_frame.merge(engineered, on="BurstId", how="left", suffixes=("", "_existing"))
    frame = frame.loc[frame["family"].isin(FAMILIES)].copy()
    frame["target"] = frame["family"].eq(FAMILIES[0]).astype(int)
    baseline = [name for name in BASELINE_FEATURES if name in frame.columns]
    mbp = [name for name in CORE_MBP_FEATURES if name in frame.columns]
    sets = {"BASELINE": baseline, "MBP_ONLY": mbp, "BASELINE_PLUS_MBP": baseline + mbp}
    rows = []
    train = frame.loc[frame["split"].eq("discovery")]
    for feature_set, columns in sets.items():
        if not columns:
            continue
        models = {
            "logistic": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.2, class_weight="balanced", max_iter=3000)),
            "random_forest": make_pipeline(SimpleImputer(strategy="median"), RandomForestClassifier(n_estimators=800, max_depth=2, min_samples_leaf=6, class_weight="balanced", random_state=20260720)),
        }
        for model_name, model in models.items():
            model.fit(train[columns], train["target"])
            for split in ("validation", "holdout"):
                test = frame.loc[frame["split"].eq(split)]
                probabilities = model.predict_proba(test[columns])[:, 1]
                predictions = (probabilities >= 0.5).astype(int)
                rows.append({
                    "feature_set": feature_set,
                    "model": model_name,
                    "split": split,
                    "n": len(test),
                    "feature_count": len(columns),
                    "balanced_accuracy": balanced_accuracy_score(test["target"], predictions),
                    "roc_auc": roc_auc_score(test["target"], probabilities),
                    "mbp_nonmissing_mean_pct": 100 * test[mbp].notna().mean().mean() if mbp else np.nan,
                })
    return pd.DataFrame(rows)


def _fmt(value: object, digits: int = 3) -> str:
    try:
        number = float(value)
        return f"{number:.{digits}f}" if np.isfinite(number) else "N/A"
    except (TypeError, ValueError):
        return "N/A"


def write_report(output: Path, features: pd.DataFrame, ranking: pd.DataFrame, models: pd.DataFrame) -> None:
    robust = ranking.loc[ranking["robust_candidate"].eq(1)]
    top = ranking.head(12)
    lines = [
        "# Investigación features pre-entry MBP+tape",
        "",
        "## Resultado principal",
        "",
        f"Features MBP robustas bajo criterios congelados: **{len(robust)}**.",
        "",
        "Esta investigación usa exclusivamente filas de mercado con timestamp menor o igual al `prediction_timestamp` original. Las respuestas de 1/3/5 segundos no son predictors.",
        "",
        "## Cobertura",
        "",
        f"- Eventos: {len(features)}.",
        f"- Cutoff causal válido: {int(features['causal_timestamp_valid'].sum())}/{len(features)}.",
        f"- MBP disponible antes del cutoff: {int(features['mbp_file_exists'].sum())}/{len(features)}.",
        f"- Tape disponible antes del cutoff: {int(features['tape_file_exists'].sum())}/{len(features)}.",
        "",
        "## Features con mayor evidencia discovery",
        "",
        "| Feature | Cobertura | q BH | Cliff A-B | Dirección estable | Robusta |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in top.itertuples(index=False):
        lines.append(f"| {row.feature} | {_fmt(row.coverage_pct,1)}% | {_fmt(row.mann_whitney_q_bh)} | {_fmt(row.cliffs_delta_A_minus_B_discovery)} | {row.direction_stable_all_splits} | {row.robust_candidate} |")
    lines.extend(["", "## Información incremental fuera de muestra", "", "| Set | Modelo | Split | n | Balanced accuracy | ROC AUC |", "| --- | --- | --- | ---: | ---: | ---: |"])
    for row in models.itertuples(index=False):
        lines.append(f"| {row.feature_set} | {row.model} | {row.split} | {row.n} | {_fmt(row.balanced_accuracy)} | {_fmt(row.roc_auc)} |")
    lines.extend([
        "",
        "## Restricciones",
        "",
        "- MBP permite cambios agregados por nivel, pero no identidad MBO; `refill` significa aproximación MBP, no iceberg confirmado.",
        "- El mejor bid/ask no se reconstruye de forma confiable, por lo que estas features no simulan fills.",
        "- El holdout existente ya fue abierto; cualquier hallazgo sirve para decidir una captura futura, no para activar un filtro.",
        "- Ninguna feature post-entry fue usada como predictor.",
        "",
        f"Artefactos: `{output}`",
    ])
    (output / "final_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def visualizations(output: Path, ranking: pd.DataFrame, features: pd.DataFrame) -> list[str]:
    folder = output / "visualizations"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    top = ranking.head(20).iloc[::-1]
    plt.figure(figsize=(11, 7))
    plt.barh(top["feature"], top["cliffs_delta_A_minus_B_discovery"].abs())
    plt.xlabel("|Cliff delta| discovery")
    plt.title("Evidencia univariada — features MBP pre-entry")
    plt.tight_layout()
    path = folder / "mbp_feature_effects.png"
    plt.savefig(path, dpi=150)
    plt.close()
    paths.append(str(path))

    coverage = features.groupby("family")[["mbp_file_exists", "tape_file_exists"]].mean() * 100
    ax = coverage.plot(kind="bar", figsize=(9, 5))
    ax.set_ylabel("Cobertura %")
    ax.set_title("Cobertura causal por familia")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    path = folder / "coverage_by_family.png"
    plt.savefig(path, dpi=150)
    plt.close()
    paths.append(str(path))
    return paths


def run(project: Path, results: Path, book: Path, output: Path | None = None) -> dict[str, object]:
    source = project / "outputs" / "absorption_breakout_research_20260720_085139"
    outcomes = pd.read_csv(source / "absorption_vs_breakout.csv")
    events = pd.read_csv(results / "burst_events.csv")
    events = events.loc[events["BurstId"].isin(outcomes["BurstId"]), [
        "BurstId", "Timestamp_UTC", "Feature_Available_Timestamp_UTC", "Detector_Publish_Timestamp_UTC",
        "Side", "Price", "Broken_Reference_Level", "AvailableBeforeEntry",
    ]].drop_duplicates("BurstId", keep="last")
    if output is None:
        output = project / "outputs" / f"preentry_liquidity_features_{datetime.now():%Y%m%d_%H%M%S}"
    output.mkdir(parents=True, exist_ok=False)
    feature_frame = extract_features(outcomes, events, book)
    ranking = analyze_features(feature_frame)
    models = model_comparison(feature_frame, source / "engineered_features.csv")
    feature_frame.to_csv(output / "preentry_mbp_feature_ledger.csv", index=False)
    ranking.to_csv(output / "feature_rankings.csv", index=False)
    models.to_csv(output / "incremental_model_comparison.csv", index=False)
    write_report(output, feature_frame, ranking, models)
    plots = visualizations(output, ranking, feature_frame)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": len(feature_frame),
        "causal_cutoff": "prediction_timestamp",
        "post_burst_predictors_used": False,
        "trading_logic_changed": False,
        "atas_replay_launched": False,
        "robust_features": ranking.loc[ranking["robust_candidate"].eq(1), "feature"].tolist(),
        "output_folder": str(output),
        "visualizations": plots,
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--results", type=Path, default=Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"))
    parser.add_argument("--book", type=Path, default=Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\book_recordings"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.project, args.results, args.book, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
