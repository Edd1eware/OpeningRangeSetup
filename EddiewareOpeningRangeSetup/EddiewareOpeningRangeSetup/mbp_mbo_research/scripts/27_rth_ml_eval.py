"""Purged walk-forward evaluation of the full-RTH decision dataset.

Everything here was fixed before the first run. The dataset (script 26) is
treated as read-only: no label, barrier or tie rule may be revisited from here,
because a search that can reach back and change its own labels is not a test.

Protocol
--------
* Folds       : 5 expanding windows over sessions in chronological order. The
                last 75 sessions are the test half, cut into 5 blocks of 15.
                Training always ends PURGE_SESSIONS before its test block, so
                a 30-minute label cannot straddle the boundary.
* Model       : CatBoost regressor on realised R, fixed params, no tuning.
* Selection   : trade only decisions whose prediction sits above the TRAINING
                80th percentile. The threshold never sees test data.
* Cost        : 1.8 ticks round trip = 1.8/K in R units, charged to every trade.
* Baseline    : the same side taken on EVERY decision in the test block. If the
                model cannot beat take-all, the model is doing nothing.
* Placebo     : the identical pipeline with training labels shuffled, repeated
                N_PLACEBO times. This is the null distribution of the SELECTION
                PROCEDURE, which is the thing that can manufacture an edge -- a
                coin-flip null would be far too easy to beat.
* Correction  : Bonferroni over the 4 combinations tested (2 brackets x 2 sides).

Pass condition: OOS net EV per trade > 0, above both baselines, and above the
placebo distribution at p < 0.05/4. Anything else is a negative, and the
remaining Databento budget goes to order-book data rather than more 1s bars.
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
N_FOLDS = 5
TEST_SESSIONS = 75
PURGE_SESSIONS = 5
SEL_PCT = 80
N_PLACEBO = 100
SEED = 20261013

CB_PARAMS = dict(iterations=400, depth=6, learning_rate=0.05,
                 loss_function="RMSE", random_seed=SEED, verbose=0,
                 allow_writing_files=False)

OUT = C.DATA / "reports"


def folds(sessions: list) -> list[tuple]:
    """Expanding-window folds with a purge gap, oldest training data first."""
    n = len(sessions)
    start = n - TEST_SESSIONS
    block = TEST_SESSIONS // N_FOLDS
    out = []
    for i in range(N_FOLDS):
        a = start + i * block
        b = a + block if i < N_FOLDS - 1 else n
        tr = sessions[: max(a - PURGE_SESSIONS, 0)]
        te = sessions[a:b]
        out.append((tr, te))
    return out


def metrics(r: np.ndarray, cost_r: float) -> dict:
    """Trade statistics in R, with cost already decided by the caller."""
    net = r - cost_r
    wins = net[net > 0].sum()
    losses = -net[net < 0].sum()
    return dict(n=len(r),
                wr=float((r > 0).mean()) if len(r) else np.nan,
                ev_gross=float(r.mean()) if len(r) else np.nan,
                ev_net=float(net.mean()) if len(r) else np.nan,
                pf=float(wins / losses) if losses > 0 else np.inf)


def run_combo(df: pd.DataFrame, feats: list[str], k: int, side: str,
              placebo: int = 0, rng: np.random.Generator | None = None):
    """One bracket x side. Returns per-fold selected OOS R and the baseline."""
    from catboost import CatBoostRegressor
    col = f"R_{side}_{k}"
    sessions = sorted(df.session.unique())
    sel_all, base_all, rows = [], [], []
    for fi, (tr, te) in enumerate(folds(sessions)):
        m_tr = df.session.isin(tr)
        m_te = df.session.isin(te)
        Xtr = df.loc[m_tr, feats].to_numpy(np.float32)
        ytr = df.loc[m_tr, col].to_numpy(np.float32)
        Xte = df.loc[m_te, feats].to_numpy(np.float32)
        yte = df.loc[m_te, col].to_numpy(np.float32)
        if placebo:
            ytr = rng.permutation(ytr)
        mdl = CatBoostRegressor(**CB_PARAMS)
        mdl.fit(Xtr, ytr)
        thr = float(np.percentile(mdl.predict(Xtr), SEL_PCT))
        pte = mdl.predict(Xte)
        pick = pte > thr
        sel_all.append(yte[pick])
        base_all.append(yte)
        if not placebo:
            rows.append(dict(fold=fi, test_from=str(te[0])[:10], test_to=str(te[-1])[:10],
                             n_test=int(m_te.sum()), n_sel=int(pick.sum()),
                             thr=thr))
    return (np.concatenate(sel_all) if sel_all else np.array([]),
            np.concatenate(base_all), rows)


def main() -> None:
    path = C.DATA / "features" / "rth_ml_dataset.parquet"
    df = pd.read_parquet(path)
    label_cols = [c for c in df.columns if c.startswith("R_")]
    feats = [c for c in df.columns if c not in label_cols + ["session", "sec"]]
    print(f"dataset {df.shape}, {len(feats)} features, "
          f"{df.session.nunique()} sessions", flush=True)

    rng = np.random.default_rng(SEED)
    results, fold_rows = [], []

    for k in BRACKETS:
        cost_r = COST_TICKS / k
        for side in SIDES:
            sel, base, rows = run_combo(df, feats, k, side)
            ms = metrics(sel, cost_r)
            mb = metrics(base, cost_r)
            print(f"\n=== K={k} {side} | cost {cost_r:.4f} R ===", flush=True)
            print(f"  model    n {ms['n']:6d}  WR {ms['wr']:.4f}  "
                  f"EV gross {ms['ev_gross']:+.4f}R  EV net {ms['ev_net']:+.4f}R  PF {ms['pf']:.3f}")
            print(f"  take-all n {mb['n']:6d}  WR {mb['wr']:.4f}  "
                  f"EV gross {mb['ev_gross']:+.4f}R  EV net {mb['ev_net']:+.4f}R  PF {mb['pf']:.3f}")
            for r in rows:
                r.update(bracket=k, side=side)
            fold_rows += rows

            p_val = np.nan
            if ms["ev_net"] > 0 and ms["ev_net"] > mb["ev_net"]:
                print(f"  positive -> running {N_PLACEBO} placebos", flush=True)
                null = []
                for _ in track(range(N_PLACEBO), label=f"placebo K{k} {side}"):
                    s2, _, _ = run_combo(df, feats, k, side, placebo=1, rng=rng)
                    null.append(metrics(s2, cost_r)["ev_net"])
                null = np.array(null)
                p_val = float((null >= ms["ev_net"]).mean())
                print(f"  placebo mean {null.mean():+.4f}R  p95 {np.percentile(null,95):+.4f}R  "
                      f"p-value {p_val:.4f}  (Bonferroni alpha {0.05/4:.4f})")
            else:
                print("  not positive vs baseline -> placebo skipped")

            results.append(dict(bracket=k, side=side, scope="model", p_value=p_val, **ms))
            results.append(dict(bracket=k, side=side, scope="take_all", p_value=np.nan, **mb))

    res = pd.DataFrame(results)
    res.to_csv(OUT / "rth_ml_eval.csv", index=False)
    pd.DataFrame(fold_rows).to_csv(OUT / "rth_ml_folds.csv", index=False)
    print("\n" + res.to_string(index=False))
    print(f"\nwrote {OUT / 'rth_ml_eval.csv'}")


if __name__ == "__main__":
    main()
