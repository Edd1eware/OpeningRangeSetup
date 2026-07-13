"""Reproducible audit of the theory-fixed Bookmap/Forthmann router veto."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import book_feature_combo_search as search


OUT = Path(__file__).resolve().parent / "outputs" / "newbook_orb_veto_20260701"


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
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    meta, X, y_fade = search.load_matrix()
    up = meta["direction"].eq("UP").to_numpy()
    or_size = X["bf_or_size_ticks"].to_numpy(float)
    prev_or = X["prev_orsz"].to_numpy(float)
    gap = X["gap"].to_numpy(float)
    big25 = X["of_big_25_imbalance"].to_numpy(float)

    branch = np.full(len(X), "", dtype=object)
    big_fade = (~up) & (or_size >= 185) & (prev_or >= 140) & (gap < 0) & (big25 < 0)
    narrow_fade = (~up) & (or_size < 140) & (prev_or >= 140) & (gap >= 0)
    narrow_cont = up & (or_size < 140) & (prev_or < 140) & (gap < 0)
    medium_cont = up & (or_size >= 140) & (or_size < 185) & (prev_or >= 140) & (gap >= 0)
    branch[big_fade] = "big_trades_fade"
    branch[narrow_fade] = "narrow_fade"
    branch[narrow_cont] = "narrow_cont"
    branch[medium_cont] = "medium_cont"
    fade = big_fade | narrow_fade
    cont = narrow_cont | medium_cont
    router = fade | cont
    correct = np.where(fade, y_fade, 1 - y_fade)

    sweep_alignment = X["of_sweep_breakout_alignment"].to_numpy(float)
    exhaustion_ratio = X["of_breakout_exhaustion_ratio"].to_numpy(float)
    selected = (cont & (sweep_alignment > 0)) | (fade & (exhaustion_ratio < 1))

    cut = 340
    train = np.arange(len(X)) < cut
    holdout = ~train
    result = {
        "definition": {
            "CONT": "current router CONT and sweep_breakout_alignment > 0",
            "FADE": "current router FADE and breakout_exhaustion_ratio < 1",
        },
        "router_all": metrics(correct[router]),
        "selected_all": metrics(correct[selected]),
        "selected_train_first_340_sessions": metrics(correct[selected & train]),
        "selected_holdout_last_146_sessions": metrics(correct[selected & holdout]),
        "weekly": search.weekly_stats(meta["date"], selected),
    }
    branch_rows = []
    for name in sorted(set(branch) - {""}):
        mask = selected & (branch == name)
        branch_rows.append({"branch": name, **metrics(correct[mask])})
    result["branches"] = branch_rows

    trades = pd.DataFrame(
        {
            "date": meta["date"],
            "direction": meta["direction"],
            "branch": branch,
            "action": np.where(fade, "FADE", "CONT"),
            "router_trade": router,
            "selected": selected,
            "correct": correct,
            "sweep_breakout_alignment": sweep_alignment,
            "breakout_exhaustion_ratio": exhaustion_ratio,
        }
    )
    trades.to_csv(OUT / "trades.csv", index=False)
    (OUT / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
