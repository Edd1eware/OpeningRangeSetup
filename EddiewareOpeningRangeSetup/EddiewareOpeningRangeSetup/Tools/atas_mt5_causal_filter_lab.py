from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

import atas_mt5_lead_feature_lab as feature_lab
import atas_mt5_pivot_backtest as structural
from causal_feature_audit import audit_feature_columns, audit_timestamp_order


SEASONS = {
    2023: ("2023-03-12T00:00:00", "2023-11-05T00:00:00"),
    2024: ("2024-03-10T00:00:00", "2024-11-03T00:00:00"),
    2025: ("2025-03-09T00:00:00", "2025-11-02T00:00:00"),
    2026: ("2026-03-08T00:00:00", "2026-08-11T00:00:00"),
}

MODEL_FEATURES = [
    "MappedPivotGapATR_AtEntry",
    "ATASApproachBars3_AtEntry",
    "LeadDivergence3ATR_AtEntry",
    "ReturnCorrelation20_AtEntry",
    "ATASAway3ATR_AtEntry",
    "IsLong_AtEntry",
    "ATASAbsorptionScore_AtEntry",
    "ATASDeltaReversal_AtEntry",
    "ATASDirectionalDelta3_AtEntry",
    "ATASVolumeRel20_AtEntry",
    "ATASDirectionalImbalance_AtEntry",
    "ATASEdgeOpposingShare_AtEntry",
]

# Causal hypotheses fixed before opening the 2026 holdout.  Zero means that
# the feature may have a direction-specific/non-monotonic relation.
MONOTONIC_DIRECTIONS = [1, -1, -1, 1, 1, 0, 1, 1, 1, 1, 1, 1]

SELECTION_FRACTIONS = (0.10, 0.15, 0.20, 0.25, 0.30)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Causal 3R selector for CFD->ATAS candidates.")
    parser.add_argument("--sweep-root", type=Path, required=True)
    parser.add_argument("--atas-cache", type=Path, required=True)
    parser.add_argument("--terminal", type=Path, required=True)
    parser.add_argument("--symbol", default="USTEC")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_full_dataset(args: argparse.Namespace) -> tuple[pd.DataFrame, list[dict]]:
    events: dict[str, dict[str, str]] = {}
    trades: list[dict] = []
    atas_sessions: dict[str, list[structural.Bar]] = {}
    mt5_bars: dict[datetime, structural.Bar] = {}

    for year, (start_text, end_text) in SEASONS.items():
        events.update(
            feature_lab.load_events(
                args.sweep_root / f"structure_{year}" / "atas_mt5_pivot_events.csv"
            )
        )
        trades.extend(
            json.loads(
                (args.sweep_root / str(year) / "raw_trades_3.0R.json").read_text(
                    encoding="utf-8"
                )
            )
        )
        start = datetime.fromisoformat(start_text).replace(tzinfo=structural.NY)
        end = datetime.fromisoformat(end_text).replace(tzinfo=structural.NY)
        atas_sessions.update(structural.load_atas_bars(None, args.atas_cache, start, end))
        mt5_bars.update(structural.load_mt5_bars(args.terminal, args.symbol, start, end))

    inputs, outcomes, skipped = feature_lab.build_dataset(
        events, trades, atas_sessions, mt5_bars
    )
    audit_feature_columns(MODEL_FEATURES)
    audit_timestamp_order(inputs)
    frame = pd.DataFrame(inputs).merge(
        pd.DataFrame(outcomes), on="trade_id", validate="one_to_one"
    )
    frame["Year"] = frame["fecha"].str[:4].astype(int)
    frame["TargetHit"] = (frame["TradeResult"] == "WIN").astype(int)
    frame["OutcomePositive"] = (frame["RealizedR"] > 0).astype(int)
    return frame.sort_values("entry_timestamp").reset_index(drop=True), skipped


def max_drawdown(values: np.ndarray) -> float:
    equity = np.concatenate([[0.0], np.cumsum(values)])
    peak = np.maximum.accumulate(equity)
    return float((peak - equity).max())


def longest_loss_streak(values: np.ndarray) -> int:
    longest = current = 0
    for value in values:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def metrics(frame: pd.DataFrame, mask: np.ndarray | pd.Series | None = None) -> dict:
    selected = frame if mask is None else frame.loc[np.asarray(mask, dtype=bool)]
    selected = selected.sort_values("entry_timestamp")
    values = selected["RealizedR"].to_numpy(float)
    positive = values[values > 0]
    negative = values[values < 0]
    n = len(values)
    mean = float(values.mean()) if n else math.nan
    std = float(values.std(ddof=1)) if n > 1 else math.nan
    half = 1.96 * std / math.sqrt(n) if n > 1 else math.nan
    gross_loss = abs(negative.sum())
    return {
        "n": n,
        "wins": int(len(positive)),
        "losses": int(len(negative)),
        "wr": float(len(positive) / n) if n else math.nan,
        "target_hits": int(selected["TargetHit"].sum()),
        "target_hit_rate": float(selected["TargetHit"].mean()) if n else math.nan,
        "replications": int(selected["ConfirmedLater"].sum()),
        "replication_rate": float(selected["ConfirmedLater"].mean()) if n else math.nan,
        "pf": float(positive.sum() / gross_loss) if gross_loss else math.nan,
        "avg_r": mean,
        "avg_r_ci95_low": mean - half if n > 1 else math.nan,
        "avg_r_ci95_high": mean + half if n > 1 else math.nan,
        "net_r": float(values.sum()),
        "max_drawdown_r": max_drawdown(values) if n else math.nan,
        "longest_loss_streak": longest_loss_streak(values),
    }


def make_model(name: str):
    if name == "ridge_ev":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", Ridge(alpha=10.0)),
            ]
        )
    if name == "logistic_win":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", LogisticRegression(C=0.1, max_iter=2000, random_state=20260811)),
            ]
        )
    if name == "monotonic_hgb_ev":
        return HistGradientBoostingRegressor(
            loss="squared_error",
            learning_rate=0.05,
            max_iter=80,
            max_depth=2,
            min_samples_leaf=50,
            l2_regularization=10.0,
            monotonic_cst=MONOTONIC_DIRECTIONS,
            random_state=20260811,
        )
    raise KeyError(name)


def fit_model(name: str, train: pd.DataFrame):
    model = make_model(name)
    x = train[MODEL_FEATURES]
    y = train["OutcomePositive"] if name == "logistic_win" else train["RealizedR"]
    model.fit(x, y)
    return model


def predict_model(name: str, model, frame: pd.DataFrame) -> np.ndarray:
    if name == "logistic_win":
        return model.predict_proba(frame[MODEL_FEATURES])[:, 1]
    return np.asarray(model.predict(frame[MODEL_FEATURES]), dtype=float)


def fit_replication_model(train: pd.DataFrame):
    model = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(C=0.1, max_iter=2000, random_state=20260811)),
        ]
    )
    model.fit(train[MODEL_FEATURES], train["ConfirmedLater"])
    return model


def empirical_rank(reference: np.ndarray, values: np.ndarray) -> np.ndarray:
    ordered = np.sort(np.asarray(reference, dtype=float))
    return np.searchsorted(ordered, values, side="right") / len(ordered)


@dataclass
class Scores:
    train: np.ndarray
    validation: np.ndarray


def candidate_scores(train: pd.DataFrame, validation: pd.DataFrame) -> dict[str, Scores]:
    result: dict[str, Scores] = {}
    raw_scores: dict[str, Scores] = {}
    for name in ("ridge_ev", "logistic_win", "monotonic_hgb_ev"):
        model = fit_model(name, train)
        raw_scores[name] = Scores(
            predict_model(name, model, train), predict_model(name, model, validation)
        )
        result[name] = raw_scores[name]

    rep = fit_replication_model(train)
    rep_train = rep.predict_proba(train[MODEL_FEATURES])[:, 1]
    rep_validation = rep.predict_proba(validation[MODEL_FEATURES])[:, 1]
    ev = raw_scores["monotonic_hgb_ev"]
    result["hgb_ev_plus_replication"] = Scores(
        0.75 * empirical_rank(ev.train, ev.train)
        + 0.25 * empirical_rank(rep_train, rep_train),
        0.75 * empirical_rank(ev.train, ev.validation)
        + 0.25 * empirical_rank(rep_train, rep_validation),
    )
    return result


def selection_table(train: pd.DataFrame, validation: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, scores in candidate_scores(train, validation).items():
        for fraction in SELECTION_FRACTIONS:
            threshold = float(np.quantile(scores.train, 1 - fraction))
            train_metrics = metrics(train, scores.train >= threshold)
            val_metrics = metrics(validation, scores.validation >= threshold)
            stable = (
                train_metrics["avg_r"] > 0
                and val_metrics["avg_r"] > 0
                and train_metrics["pf"] > 1
                and val_metrics["pf"] > 1
                and val_metrics["n"] >= 50
            )
            robust_score = (
                min(train_metrics["avg_r"], val_metrics["avg_r"])
                * math.sqrt(min(train_metrics["n"], val_metrics["n"]) / 50)
                if stable
                else -999.0
            )
            rows.append(
                {
                    "candidate": name,
                    "selection_fraction": fraction,
                    "threshold_train": threshold,
                    "stable_train_validation": stable,
                    "robust_score": robust_score,
                    **{f"train_{key}": value for key, value in train_metrics.items()},
                    **{f"validation_{key}": value for key, value in val_metrics.items()},
                }
            )

    for name, mask_train, mask_validation in (
        (
            "fixed_gap_and_stall",
            (train["MappedPivotGapATR_AtEntry"] > 0)
            & (train["ATASApproachBars3_AtEntry"] <= 1),
            (validation["MappedPivotGapATR_AtEntry"] > 0)
            & (validation["ATASApproachBars3_AtEntry"] <= 1),
        ),
        (
            "fixed_gap_stall_moderate_divergence",
            (train["MappedPivotGapATR_AtEntry"] > 0)
            & (train["ATASApproachBars3_AtEntry"] <= 1)
            & (train["LeadDivergence3ATR_AtEntry"] <= 1.5),
            (validation["MappedPivotGapATR_AtEntry"] > 0)
            & (validation["ATASApproachBars3_AtEntry"] <= 1)
            & (validation["LeadDivergence3ATR_AtEntry"] <= 1.5),
        ),
    ):
        train_metrics = metrics(train, mask_train)
        val_metrics = metrics(validation, mask_validation)
        stable = train_metrics["avg_r"] > 0 and val_metrics["avg_r"] > 0
        rows.append(
            {
                "candidate": name,
                "selection_fraction": math.nan,
                "threshold_train": math.nan,
                "stable_train_validation": stable,
                "robust_score": min(train_metrics["avg_r"], val_metrics["avg_r"]) if stable else -999,
                **{f"train_{key}": value for key, value in train_metrics.items()},
                **{f"validation_{key}": value for key, value in val_metrics.items()},
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["stable_train_validation", "robust_score", "validation_pf"], ascending=False
    )


def refit_selected(
    candidate: str, fraction: float, development: pd.DataFrame, holdout: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray, float, dict]:
    if candidate.startswith("fixed_"):
        development_mask = (
            (development["MappedPivotGapATR_AtEntry"] > 0)
            & (development["ATASApproachBars3_AtEntry"] <= 1)
        )
        holdout_mask = (
            (holdout["MappedPivotGapATR_AtEntry"] > 0)
            & (holdout["ATASApproachBars3_AtEntry"] <= 1)
        )
        if candidate.endswith("moderate_divergence"):
            development_mask &= development["LeadDivergence3ATR_AtEntry"] <= 1.5
            holdout_mask &= holdout["LeadDivergence3ATR_AtEntry"] <= 1.5
        return (
            development_mask.to_numpy(bool),
            holdout_mask.to_numpy(bool),
            math.nan,
            {"type": "fixed_rule"},
        )

    if candidate == "hgb_ev_plus_replication":
        ev = fit_model("monotonic_hgb_ev", development)
        rep = fit_replication_model(development)
        ev_dev = predict_model("monotonic_hgb_ev", ev, development)
        ev_holdout = predict_model("monotonic_hgb_ev", ev, holdout)
        rep_dev = rep.predict_proba(development[MODEL_FEATURES])[:, 1]
        rep_holdout = rep.predict_proba(holdout[MODEL_FEATURES])[:, 1]
        dev_score = 0.75 * empirical_rank(ev_dev, ev_dev) + 0.25 * empirical_rank(
            rep_dev, rep_dev
        )
        holdout_score = 0.75 * empirical_rank(ev_dev, ev_holdout) + 0.25 * empirical_rank(
            rep_dev, rep_holdout
        )
        details = {"type": "blend", "ev_model": "monotonic_hgb_ev", "replication_weight": 0.25}
    else:
        model = fit_model(candidate, development)
        dev_score = predict_model(candidate, model, development)
        holdout_score = predict_model(candidate, model, holdout)
        details = {"type": candidate}
        if candidate in ("ridge_ev", "logistic_win"):
            fitted = model.named_steps["model"]
            details["coefficients"] = {
                feature: float(value)
                for feature, value in zip(MODEL_FEATURES, np.asarray(fitted.coef_).ravel())
            }

    threshold = float(np.quantile(dev_score, 1 - fraction))
    return dev_score >= threshold, holdout_score >= threshold, threshold, details


def fmt(result: dict) -> str:
    return (
        f"n={result['n']}, W-L={result['wins']}-{result['losses']}, "
        f"WR={100 * result['wr']:.2f}%, hits3R={result['target_hits']}, "
        f"rep={100 * result['replication_rate']:.2f}%, PF={result['pf']:.3f}, "
        f"AvgR={result['avg_r']:+.3f}, NetR={result['net_r']:+.2f}, "
        f"DD={result['max_drawdown_r']:.2f}R"
    )


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    frame, skipped = load_full_dataset(args)
    frame.to_csv(args.output / "causal_candidates_3R.csv", index=False)
    pd.DataFrame(skipped).to_csv(args.output / "skipped_rows.csv", index=False)

    train = frame.loc[frame["Year"].isin([2023, 2024])].copy()
    validation = frame.loc[frame["Year"] == 2025].copy()
    holdout = frame.loc[frame["Year"] == 2026].copy()
    development = frame.loc[frame["Year"] <= 2025].copy()

    candidates = selection_table(train, validation)
    candidates.to_csv(args.output / "candidate_selection_2023_2025.csv", index=False)
    selected = candidates.iloc[0]
    candidate = str(selected["candidate"])
    fraction = float(selected["selection_fraction"]) if pd.notna(selected["selection_fraction"]) else math.nan
    development_mask, holdout_mask, final_threshold, model_details = refit_selected(
        candidate, fraction, development, holdout
    )

    period_rows = []
    for period, subset, mask in (
        ("DEVELOPMENT_2023_2025", development, development_mask),
        ("HOLDOUT_2026", holdout, holdout_mask),
    ):
        period_rows.append({"period": period, **metrics(subset, mask)})
    for year in (2023, 2024, 2025):
        year_mask = development["Year"].eq(year).to_numpy() & np.asarray(development_mask)
        period_rows.append({"period": str(year), **metrics(development, year_mask)})
    final_metrics = pd.DataFrame(period_rows)
    final_metrics.to_csv(args.output / "frozen_filter_metrics.csv", index=False)

    holdout_result = final_metrics.loc[final_metrics["period"] == "HOLDOUT_2026"].iloc[0]
    validation_result = metrics(
        validation,
        (
            candidate_scores(train, validation)[candidate].validation
            >= float(selected["threshold_train"])
        )
        if candidate in ("ridge_ev", "logistic_win", "monotonic_hgb_ev", "hgb_ev_plus_replication")
        else (
            (validation["MappedPivotGapATR_AtEntry"] > 0)
            & (validation["ATASApproachBars3_AtEntry"] <= 1)
            & (
                True
                if candidate == "fixed_gap_and_stall"
                else validation["LeadDivergence3ATR_AtEntry"] <= 1.5
            )
        ),
    )
    approved = bool(
        validation_result["pf"] >= 1.20
        and validation_result["avg_r"] >= 0.10
        and holdout_result.pf >= 1.30
        and holdout_result.avg_r >= 0.15
        and holdout_result.avg_r_ci95_low > 0
        and holdout_result.n >= 30
        and holdout_result.wr >= 0.32
        and holdout_result.max_drawdown_r <= 10
    )

    selected_holdout = holdout.loc[np.asarray(holdout_mask)].copy()
    selected_holdout.to_csv(args.output / "selected_holdout_2026.csv", index=False)

    rep_model = fit_replication_model(development)
    rep_auc = roc_auc_score(
        holdout["ConfirmedLater"], rep_model.predict_proba(holdout[MODEL_FEATURES])[:, 1]
    )
    baseline = {str(year): metrics(frame.loc[frame["Year"] == year]) for year in SEASONS}

    fig, axis = plt.subplots(figsize=(11, 5))
    values = selected_holdout.sort_values("entry_timestamp")["RealizedR"].to_numpy(float)
    axis.plot(np.arange(len(values) + 1), np.concatenate([[0], np.cumsum(values)]), color="#0F766E")
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set_title(f"Filtro congelado {candidate} — holdout 2026")
    axis.set_xlabel("Operación seleccionada")
    axis.set_ylabel("R acumulada")
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(args.output / "holdout_2026_equity.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    payload = {
        "dataset": {
            "rows": len(frame),
            "skipped": len(skipped),
            "features": MODEL_FEATURES,
            "years": {str(year): int((frame["Year"] == year).sum()) for year in SEASONS},
        },
        "selection_protocol": "train 2023-2024; validation/model selection 2025; frozen holdout 2026",
        "selected_candidate": candidate,
        "selection_fraction": None if math.isnan(fraction) else fraction,
        "final_threshold": None if math.isnan(final_threshold) else final_threshold,
        "model_details": model_details,
        "validation_2025": validation_result,
        "holdout_2026": json.loads(holdout_result.to_json()),
        "replication_auc_holdout_2026": float(rep_auc),
        "approved_for_live": approved,
        "baseline": baseline,
        "leakage_guard": "PASS: completed ATAS footprint/AtEntry allowlist and feature_timestamp <= entry_timestamp",
    }
    (args.output / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )

    report = [
        "# Filtro causal CFD MT5 -> ATAS L2/footprint — objetivo 3R",
        "",
        f"Dataset: {len(frame)} candidatos llenados, {len(skipped)} omitidos. Guard de leakage: PASS.",
        "",
        "Protocolo: entrenamiento 2023-2024; selección de modelo/umbral solo con 2025; refit 2023-2025; apertura única del holdout 2026.",
        "",
        f"Candidato seleccionado antes de abrir 2026: **{candidate}**"
        + (f", top {100 * fraction:.0f}%" if not math.isnan(fraction) else ""),
        "",
        f"- Validación 2025: {fmt(validation_result)}.",
        f"- Holdout 2026: {fmt(holdout_result.to_dict())}.",
        f"- AUC de predicción de replicación en 2026: {rep_auc:.3f}.",
        f"- Estado de despliegue: **{'APROBADO' if approved else 'RECHAZADO / SOLO PAPER'}**.",
        "",
        "## Gate exigido",
        "",
        "Para aprobar: PF>=1.30, AvgR>=+0.15R, IC95% inferior>0, n>=30, WR>=32% y MaxDD<=10R en 2026; además 2025 PF>=1.20 y AvgR>=+0.10R.",
        "",
        "La confirmación posterior de ATAS se usa únicamente como outcome de diagnóstico. Nunca entra como feature ni como condición del filtro live.",
    ]
    (args.output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    print(f"OUTPUT={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
