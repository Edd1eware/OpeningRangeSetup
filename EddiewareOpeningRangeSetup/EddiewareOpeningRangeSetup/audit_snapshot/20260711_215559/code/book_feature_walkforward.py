"""Low-complexity walk-forward audit of book-inspired feature families.

Each concept has a theory-fixed action and orientation: a larger score should
support that action.  On each expanding training window only one percentile
threshold is selected, then applied unchanged to the next 40 sessions.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import book_feature_combo_search as search


OUT = Path(__file__).resolve().parent / "outputs" / "newbooks_feature_walkforward_20260701"
RATE = 101 / 486


def metrics(correct: np.ndarray) -> dict:
    correct = np.asarray(correct, dtype=int)
    n = len(correct)
    wins = int(correct.sum())
    losses = n - wins
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "wr": wins / n if n else None,
        "pf_gross": wins / losses if losses else None,
        "pf_after_2t": wins * 28 / (losses * 32) if losses else None,
        "wilson_low": search.wilson_low(wins, n) if n else None,
    }


def build_scores(meta: pd.DataFrame, X: pd.DataFrame) -> dict[str, tuple[str, np.ndarray]]:
    direction = np.where(meta["direction"].eq("UP"), 1.0, -1.0)
    safe = lambda name: pd.to_numeric(X[name], errors="coerce").fillna(0.0).to_numpy(float)
    return {
        "CONT_open_drive": ("CONT", safe("of_open_drive_score")),
        "CONT_price_alignment": ("CONT", safe("of_open_drive_price_alignment")),
        "CONT_flow_alignment": ("CONT", safe("of_open_drive_flow_alignment")),
        "CONT_late_flow_alignment": (
            "CONT", direction * safe("of_last_quarter_aggr_imbalance")
        ),
        "CONT_flow_persistence": (
            "CONT",
            safe("of_open_drive_price_alignment")
            * np.maximum(0.0, safe("of_trade_sign_persistence")),
        ),
        "CONT_initiative_profile": (
            "CONT",
            safe("book_initiative_breakout")
            + np.tanh(safe("book_value_migration_with_breakout_ticks") / 50.0),
        ),
        "CONT_responsive_to_value": (
            "CONT", safe("book_responsive_breakout_toward_value")
        ),
        "CONT_trade_sign_ema_8": ("CONT", safe("of_trade_sign_ema_8_alignment")),
        "CONT_trade_sign_ema_32": ("CONT", safe("of_trade_sign_ema_32_alignment")),
        "CONT_trade_sign_ema_128": ("CONT", safe("of_trade_sign_ema_128_alignment")),
        "CONT_sweep_alignment": ("CONT", safe("of_sweep_breakout_alignment")),
        "CONT_liquidity_alignment": (
            "CONT", safe("of_edge_liquidity_breakout_alignment")
        ),
        "CONT_spoof_alignment": (
            "CONT", safe("of_spoof_like_breakout_alignment")
        ),
        "CONT_vpin_drive": (
            "CONT",
            safe("of_vpin_20") * np.maximum(0.0, safe("of_open_drive_price_alignment")),
        ),
        "CONT_thin_profile": (
            "CONT",
            (1.0 - safe("book_edge_volume_percentile"))
            * np.maximum(0.0, safe("of_open_drive_price_alignment")),
        ),
        "FADE_absorption_alignment": (
            "FADE", -direction * safe("of_delta_no_move_absorption")
        ),
        "FADE_trapped_alignment": (
            "FADE", -direction * safe("of_trapped_aggressor_imbalance")
        ),
        "FADE_iceberg_alignment": (
            "FADE", -direction * safe("of_icebergorder_edge_imbalance")
        ),
        "FADE_edge_rejection": ("FADE", safe("of_edge_rejection_ticks")),
        "FADE_open_auction": ("FADE", safe("of_open_auction_score")),
        "FADE_value_acceptance": (
            "FADE", safe("book_or_overlap_prev_value_pct")
        ),
        "FADE_exhaustion": ("FADE", -safe("of_breakout_exhaustion_ratio")),
        "FADE_liquidity_opposition": (
            "FADE", -safe("of_edge_liquidity_breakout_alignment")
        ),
        "FADE_spoof_opposition": (
            "FADE", -safe("of_spoof_like_breakout_alignment")
        ),
        "FADE_high_volume_edge": ("FADE", safe("book_edge_volume_percentile")),
        "FADE_unfinished_auction": ("FADE", safe("book_edge_unfinished_auction")),
    }


def select_threshold(score: np.ndarray, correct: np.ndarray, minimum: int) -> float:
    finite = score[np.isfinite(score)]
    thresholds = np.unique(np.quantile(finite, np.arange(0.0, 0.91, 0.1)))
    best = None
    for threshold in thresholds:
        take = np.isfinite(score) & (score >= threshold)
        if take.sum() < minimum:
            continue
        stat = metrics(correct[take])
        rank = (stat["wilson_low"], stat["wr"], stat["n"])
        if best is None or rank > best[0]:
            best = (rank, float(threshold))
    return best[1] if best else float(np.nanmin(finite))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    meta, X, y_fade = search.load_matrix()
    scores = build_scores(meta, X)
    summaries = []
    fold_rows = []
    for name, (action, score) in scores.items():
        correct_all = y_fade if action == "FADE" else 1 - y_fade
        oos = []
        for test_start in range(240, len(X), 40):
            test_end = min(len(X), test_start + 40)
            minimum = max(30, math.ceil(RATE * test_start))
            threshold = select_threshold(
                score[:test_start], correct_all[:test_start], minimum
            )
            take = np.isfinite(score[test_start:test_end]) & (
                score[test_start:test_end] >= threshold
            )
            outcomes = correct_all[test_start:test_end][take]
            oos.extend(outcomes.tolist())
            fold_rows.append(
                {
                    "concept": name,
                    "action": action,
                    "train_end": str(meta["date"].iloc[test_start - 1].date()),
                    "test_start": str(meta["date"].iloc[test_start].date()),
                    "test_end": str(meta["date"].iloc[test_end - 1].date()),
                    "threshold": threshold,
                    **metrics(outcomes),
                }
            )
        summary = {"concept": name, "action": action, **metrics(np.asarray(oos))}
        summaries.append(summary)

    summaries.sort(
        key=lambda row: (row["wilson_low"] or -1, row["wr"] or -1, row["n"]),
        reverse=True,
    )
    pd.DataFrame(summaries).to_csv(OUT / "summary.csv", index=False)
    pd.DataFrame(fold_rows).to_csv(OUT / "folds.csv", index=False)
    (OUT / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    print(f"Saved {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
