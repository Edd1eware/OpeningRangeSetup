"""Validate HOLC candle features (candle_holc_features.csv) on the ORB sample.

Four independent views, from most to least conservative:

1. Theory-fixed concept walk-forward: each candle concept has a fixed action
   and orientation; only one percentile threshold is fitted per expanding
   train window (same protocol as book_feature_walkforward.py).
2. Router veto: does a theory-fixed candle condition improve the frozen
   73.75%/PF 2.81 router, evaluated on all/first-340/last-146 splits.
3. Conjunction search + static tree on the full matrix augmented with the
   candle family (in-sample, descriptive only).
4. Nested walk-forward of the augmented tree (honest estimate).

Timers: prints one [Xs] line per stage plus total elapsed.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

import book_feature_combo_search as search

BASE = Path(__file__).resolve().parent
CANDLE_CSV = search.ROOT / "features" / "candle_holc_features.csv"
OUT = BASE / "outputs" / "candle_holc_validation_20260701"
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


def load_matrix_with_candles():
    meta, X, y_fade = search.load_matrix()
    cand = pd.read_csv(CANDLE_CSV)
    cand["date"] = pd.to_datetime(cand["session_date"])
    cand = cand.drop(columns=["session_date"])
    merged = meta[["date"]].merge(cand, on="date", how="left", validate="one_to_one")
    missing = int(merged.drop(columns=["date"]).isna().all(axis=1).sum())
    if missing:
        # the ohlcv-1s-full download skips US holidays; those sessions stay NaN
        # (median-imputed inside the tree, excluded by finite-only conditions)
        print(f"[warn] {missing} sessions without candle features (holiday dates)")
    for column in merged.columns:
        if column != "date":
            X[column] = pd.to_numeric(merged[column], errors="coerce")
    return meta, X, y_fade


def candle_scores(meta: pd.DataFrame, X: pd.DataFrame) -> dict[str, tuple[str, np.ndarray]]:
    up = meta["direction"].eq("UP").to_numpy()
    safe = lambda name: pd.to_numeric(X[name], errors="coerce").fillna(0.0).to_numpy(float)
    wick_at_breakout_side = np.where(
        up, safe("candle_wick_share_at_highs"), safe("candle_wick_share_at_lows")
    )
    return {
        # continuation: conviction of the open (Dalton), structure (SMC BOS),
        # efficiency and leg asymmetry (Grimes)
        "CONT_candle_drive_clv": ("CONT", safe("candle_window_clv_alignment")),
        "CONT_candle_net_bos": ("CONT", safe("candle_net_bos_alignment")),
        "CONT_candle_last_structure": ("CONT", safe("candle_last_structure_alignment")),
        "CONT_candle_efficiency": ("CONT", safe("candle_cc_efficiency_alignment")),
        "CONT_candle_slope": ("CONT", safe("candle_close_slope_alignment")),
        "CONT_candle_leg_asymmetry": ("CONT", safe("candle_leg_asymmetry")),
        "CONT_candle_consec_edge": (
            "CONT", safe("candle_max_consec_with") - safe("candle_max_consec_against"),
        ),
        "CONT_candle_close_share": ("CONT", safe("candle_close_with_breakout_share")),
        "CONT_candle_body_conviction": ("CONT", safe("candle_last10_body_share")),
        # liquidity magnet beyond the edge (ALS): pools on breakout side attract
        "CONT_candle_liquidity_magnet": ("CONT", safe("candle_liquidity_pool_alignment")),
        # fade: failure tests (Grimes module 6 / Wyckoff spring), climax
        # exhaustion (Grimes p.283-285), rejection wicks, chop
        "FADE_candle_failure_tests": ("FADE", safe("candle_failure_test_against_breakout")),
        "FADE_candle_sweep_wick": ("FADE", safe("candle_sweep_wick_ticks")),
        "FADE_candle_climax": ("FADE", safe("candle_climax_ratio")),
        "FADE_candle_climax_shadow": (
            "FADE", safe("candle_climax_ratio") * safe("candle_climax_shadow_share"),
        ),
        "FADE_candle_wick_rejection": ("FADE", wick_at_breakout_side),
        "FADE_candle_choch": ("FADE", safe("candle_choch_count")),
        "FADE_candle_doji": ("FADE", safe("candle_doji_count")),
        "FADE_candle_anti_drive": ("FADE", -safe("candle_window_clv_alignment")),
        "FADE_candle_range_contraction": ("FADE", -safe("candle_range_expansion")),
    }


def concept_walkforward(meta, X, y_fade) -> list[dict]:
    summaries = []
    for name, (action, score) in candle_scores(meta, X).items():
        correct_all = y_fade if action == "FADE" else 1 - y_fade
        oos = []
        for test_start in range(240, len(X), 40):
            test_end = min(len(X), test_start + 40)
            minimum = max(30, math.ceil(RATE * test_start))
            finite = score[:test_start][np.isfinite(score[:test_start])]
            thresholds = np.unique(np.quantile(finite, np.arange(0.0, 0.91, 0.1)))
            best = None
            for threshold in thresholds:
                take = np.isfinite(score[:test_start]) & (score[:test_start] >= threshold)
                if take.sum() < minimum:
                    continue
                stat = metrics(correct_all[:test_start][take])
                rank = (stat["wilson_low"], stat["wr"], stat["n"])
                if best is None or rank > best[0]:
                    best = (rank, float(threshold))
            threshold = best[1] if best else float(np.nanmin(finite))
            segment = score[test_start:test_end]
            take = np.isfinite(segment) & (segment >= threshold)
            oos.extend(correct_all[test_start:test_end][take].tolist())
        summaries.append({"concept": name, "action": action, **metrics(np.asarray(oos))})
    summaries.sort(
        key=lambda row: (row["wilson_low"] or -1, row["wr"] or -1, row["n"]), reverse=True
    )
    return summaries


def router_masks(meta, X, y_fade):
    up = meta["direction"].eq("UP").to_numpy()
    or_size = X["bf_or_size_ticks"].to_numpy(float)
    prev_or = X["prev_orsz"].to_numpy(float)
    gap = X["gap"].to_numpy(float)
    big25 = X["of_big_25_imbalance"].to_numpy(float)
    big_fade = (~up) & (or_size >= 185) & (prev_or >= 140) & (gap < 0) & (big25 < 0)
    narrow_fade = (~up) & (or_size < 140) & (prev_or >= 140) & (gap >= 0)
    narrow_cont = up & (or_size < 140) & (prev_or < 140) & (gap < 0)
    medium_cont = up & (or_size >= 140) & (or_size < 185) & (prev_or >= 140) & (gap >= 0)
    fade = big_fade | narrow_fade
    cont = narrow_cont | medium_cont
    correct = np.where(fade, y_fade, 1 - y_fade)
    return fade, cont, correct


def router_veto(meta, X, y_fade) -> dict:
    fade, cont, correct = router_masks(meta, X, y_fade)
    router = fade | cont
    net_bos = X["candle_net_bos_alignment"].to_numpy(float)
    structure = X["candle_last_structure_alignment"].to_numpy(float)
    failures = X["candle_failure_test_against_breakout"].to_numpy(float)
    clv = X["candle_window_clv_alignment"].to_numpy(float)

    vetoes = {
        "cont_needs_net_bos_pos__fade_needs_failure_test": (
            (cont & (net_bos > 0)) | (fade & (failures >= 1))
        ),
        "cont_needs_structure_pos__fade_needs_failure_test": (
            (cont & (structure > 0)) | (fade & (failures >= 1))
        ),
        "cont_needs_clv_pos__fade_needs_anti_clv": (
            (cont & (clv > 0)) | (fade & (clv < 0))
        ),
    }
    cut = 340
    train = np.arange(len(X)) < cut
    result = {"router_all": metrics(correct[router])}
    for name, selected in vetoes.items():
        result[name] = {
            "all": metrics(correct[selected]),
            "train_first_340": metrics(correct[selected & train]),
            "holdout_last_146": metrics(correct[selected & ~train]),
            "weekly": search.weekly_stats(meta["date"], selected),
        }
    return result


def main() -> int:
    total_start = time.time()
    OUT.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    meta, X, y_fade = load_matrix_with_candles()
    candle_cols = [c for c in X.columns if c.startswith("candle_")]
    print(f"[{time.time()-t0:.1f}s] matrix: {len(X)} rows, {X.shape[1]} features "
          f"({len(candle_cols)} candle)")

    t0 = time.time()
    concepts = concept_walkforward(meta, X, y_fade)
    print(f"[{time.time()-t0:.1f}s] concept walk-forward")
    for row in concepts[:8]:
        print("  ", json.dumps(row, ensure_ascii=False))

    t0 = time.time()
    veto = router_veto(meta, X, y_fade)
    print(f"[{time.time()-t0:.1f}s] router veto")
    print(json.dumps(veto, ensure_ascii=False, indent=2))

    t0 = time.time()
    conjunctions = search.conjunction_search(X, y_fade, search.TARGET_TRADES)
    print(f"[{time.time()-t0:.1f}s] conjunction search")
    for row in conjunctions:
        print("  ", json.dumps(row, ensure_ascii=False))

    t0 = time.time()
    tree, selected, predictions, static = search.best_static_tree(X, y_fade, search.TARGET_TRADES)
    static.pop("trade_mask"), static.pop("pred"), static.pop("leaf_rows")
    print(f"[{time.time()-t0:.1f}s] static tree (in-sample):", json.dumps(static, ensure_ascii=False))

    t0 = time.time()
    folds, oos = search.nested_walkforward(X, y_fade, meta["date"])
    oos_metrics = search.metrics(oos)
    print(f"[{time.time()-t0:.1f}s] nested walk-forward OOS:", json.dumps(oos_metrics, ensure_ascii=False))
    folds.to_csv(OUT / "nested_walkforward.csv", index=False)

    payload = {
        "candle_columns": candle_cols,
        "concept_walkforward": concepts,
        "router_veto": veto,
        "conjunctions": conjunctions,
        "static_tree": static,
        "nested_oos": oos_metrics,
    }
    (OUT / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Saved {OUT} TOTAL [{time.time()-total_start:.1f}s]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
