"""Does the model's gross signal CONCENTRATE, or is it spread thin?

Script 27 found a real but tiny effect: selecting the top 20% of predictions
earns about +0.45 ticks gross per trade at both K=20 and K=40, against a cost
of 1.8 ticks. That is a clean net negative, but it does not settle the
question, because a signal worth 0.45 ticks averaged over 20% of decisions is
compatible with two very different worlds:

    world A  the effect is uniform and weak -> the top 1% also earns ~0.45
             ticks, nothing clears the cost, and the space is exhausted.
    world B  the effect is concentrated -> the top 1% earns several ticks and
             only the dilution of the other 19% hid it.

Only world B is tradeable, and the two are told apart by the SHAPE of EV
against selectivity, not by any single cell. A monotone rise is the signature
of a real conditional effect; a flat or jagged profile is the signature of
noise being sorted.

Because this sweeps a threshold, it is a search, and it is scored as one: the
placebo pipeline reruns the entire sweep on shuffled training labels, so the
null is the best cell a sweep of this shape finds in data with no signal, not
the null of one pre-chosen cell.

Also reported: CatBoost feature importance, averaged over folds. It does not
prove anything on its own, but a top of the list made of features that cannot
mechanically carry information is a warning that the fit is on an artifact.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
from progress import track

COST_TICKS = 1.8
BRACKETS = (20, 40)
SIDES = ("long", "short")
PCTS = (50, 80, 90, 95, 98, 99, 99.5, 99.9)
N_FOLDS = 5
TEST_SESSIONS = 75
PURGE_SESSIONS = 5
N_PLACEBO = 40
SEED = 20261013

CB = dict(iterations=400, depth=6, learning_rate=0.05, loss_function="RMSE",
          random_seed=SEED, verbose=0, allow_writing_files=False)


def folds(sessions):
    n = len(sessions)
    start = n - TEST_SESSIONS
    block = TEST_SESSIONS // N_FOLDS
    for i in range(N_FOLDS):
        a = start + i * block
        b = a + block if i < N_FOLDS - 1 else n
        yield sessions[: max(a - PURGE_SESSIONS, 0)], sessions[a:b]


def sweep(df, feats, k, side, shuffle=False, rng=None, want_importance=False):
    """Fit each fold once, then read every selectivity off the same model."""
    from catboost import CatBoostRegressor
    col = f"R_{side}_{k}"
    sessions = sorted(df.session.unique())
    picked = {p: [] for p in PCTS}
    imps = []
    for tr, te in folds(sessions):
        m_tr = df.session.isin(tr); m_te = df.session.isin(te)
        Xtr = df.loc[m_tr, feats].to_numpy(np.float32)
        ytr = df.loc[m_tr, col].to_numpy(np.float32)
        Xte = df.loc[m_te, feats].to_numpy(np.float32)
        yte = df.loc[m_te, col].to_numpy(np.float32)
        if shuffle:
            ytr = rng.permutation(ytr)
        mdl = CatBoostRegressor(**CB)
        mdl.fit(Xtr, ytr)
        ptr = mdl.predict(Xtr)
        pte = mdl.predict(Xte)
        if want_importance:
            imps.append(mdl.get_feature_importance())
        for p in PCTS:
            thr = float(np.percentile(ptr, p))
            picked[p].append(yte[pte > thr])
    out = {}
    for p in PCTS:
        r = np.concatenate(picked[p]) if picked[p] else np.array([])
        out[p] = r
    imp = np.mean(imps, axis=0) if imps else None
    return out, imp


def main():
    df = pd.read_parquet(C.DATA / "features" / "rth_ml_dataset.parquet")
    labels = [c for c in df.columns if c.startswith("R_")]
    feats = [c for c in df.columns if c not in labels + ["session", "sec"]]
    rng = np.random.default_rng(SEED)

    rows, imp_rows = [], []
    for k in BRACKETS:
        cost_r = COST_TICKS / k
        for side in SIDES:
            real, imp = sweep(df, feats, k, side, want_importance=True)
            imp_rows.append(pd.Series(imp, index=feats, name=f"K{k}_{side}"))
            print(f"\n=== K={k} {side} (cost {cost_r:.4f}R = {COST_TICKS} ticks) ===",
                  flush=True)
            print(f"{'sel%':>6} {'n':>6} {'WR':>7} {'EVgross_R':>10} "
                  f"{'EVgross_tk':>11} {'EVnet_tk':>9} {'PF':>7}")
            for p in PCTS:
                r = real[p]
                if len(r) < 20:
                    print(f"{p:>6} {len(r):>6}   too few")
                    rows.append(dict(bracket=k, side=side, pct=p, n=len(r)))
                    continue
                net = r - cost_r
                pf = (net[net > 0].sum() / -net[net < 0].sum()) if (net < 0).any() else np.inf
                print(f"{p:>6} {len(r):>6} {(r>0).mean():>7.4f} {r.mean():>+10.4f} "
                      f"{r.mean()*k:>+11.3f} {net.mean()*k:>+9.3f} {pf:>7.3f}")
                rows.append(dict(bracket=k, side=side, pct=p, n=len(r),
                                 wr=float((r > 0).mean()),
                                 ev_gross_r=float(r.mean()),
                                 ev_gross_ticks=float(r.mean() * k),
                                 ev_net_ticks=float(net.mean() * k),
                                 pf=float(pf)))

    pd.DataFrame(rows).to_csv(C.DATA / "reports" / "rth_ml_concentration.csv", index=False)
    imp_df = pd.concat(imp_rows, axis=1)
    imp_df["mean"] = imp_df.mean(axis=1)
    imp_df.sort_values("mean", ascending=False).to_csv(
        C.DATA / "reports" / "rth_ml_importance.csv")
    print("\n=== top 15 features by mean importance across the 4 combos ===")
    print(imp_df.sort_values("mean", ascending=False).head(15).round(3).to_string())

    # placebo null for the WHOLE sweep: the best gross tick EV any cell reaches
    # with at least 50 trades, in data where the training labels carry nothing
    print(f"\nrunning {N_PLACEBO} placebo sweeps (null of the search itself) ...",
          flush=True)
    best_real = max(r["ev_gross_ticks"] for r in rows
                    if r.get("n", 0) >= 50 and "ev_gross_ticks" in r)
    null = []
    for _ in track(range(N_PLACEBO), label="placebo sweeps"):
        best = -np.inf
        for k in BRACKETS:
            for side in SIDES:
                res, _ = sweep(df, feats, k, side, shuffle=True, rng=rng)
                for p in PCTS:
                    r = res[p]
                    if len(r) >= 50:
                        best = max(best, float(r.mean() * k))
        null.append(best)
    null = np.array(null)
    p_val = float((null >= best_real).mean())
    print(f"\nbest real cell   {best_real:+.3f} ticks gross")
    print(f"placebo mean     {null.mean():+.3f} ticks, p95 {np.percentile(null,95):+.3f}")
    print(f"p-value          {p_val:.4f}")
    print(f"cost to beat     {COST_TICKS} ticks")
    pd.DataFrame(dict(placebo_best_ticks=null)).to_csv(
        C.DATA / "reports" / "rth_ml_concentration_placebo.csv", index=False)


if __name__ == "__main__":
    main()
