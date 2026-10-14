"""Audit of the K=150 result before anyone believes it.

Script 30 reported, out of sample, K=150 long: 207 trades, WR 57.49%, +22.46
ticks gross, +20.66 net. Taken at face value that is an enormous edge and it
would pass a Lucid 50K almost at will. It is almost certainly not real, and the
reason is structural rather than statistical:

    decisions are 300 seconds apart and the label looks 3 HOURS forward, so the
    ~42 decisions inside one session share almost the same forward window and
    almost the same answer. The effective sample is the number of SESSIONS, not
    the number of trades. If the 207 selected trades live in a handful of
    trending sessions, +22 ticks is one or two good days wearing a large n.

This script does not re-run the search. It takes the same frozen pipeline and
asks the only questions that can kill the result:

  A. CONCENTRATION  how many distinct sessions do the selected trades span, and
                    what does the edge look like per session? A mean of +22
                    ticks carried by 5 of 75 test sessions is not an edge.
  B. SESSION BOOTSTRAP  resample whole SESSIONS with replacement, 5,000 times,
                    and report the 95% interval of the mean. Resampling trades
                    would be cheating: they are not independent.
  C. PLACEBO        the identical pipeline on shuffled training labels, so the
                    null is "what this selection procedure extracts from data
                    with no signal", given the same overlap structure.
  D. PER-FOLD       the five folds separately. A real effect shows up in most
                    of them; an artifact lives in one.
  E. ONE-PER-SESSION  the same thing with at most one trade per session, which
                    destroys the overlap entirely. If the edge survives that,
                    it is about days; if it vanishes, it was always about days.

A result that survives all five is worth paying for. A result that fails any of
them goes in the notes as a trap, next to the other four this project has
already caught.
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
BRACKETS = (80, 150)
SIDES = ("long", "short")
N_FOLDS = 5
TEST_FRAC = 0.5
PURGE_SESSIONS = 5
SEL_PCT = 80
N_BOOT = 5000
N_PLACEBO = 100
SEED = 20261013
CB = dict(iterations=400, depth=6, learning_rate=0.05, loss_function="RMSE",
          random_seed=SEED, verbose=0, allow_writing_files=False)


def walk(df, feats, col, shuffle=False, rng=None):
    """Return the selected OOS trades, tagged with session and fold."""
    from catboost import CatBoostRegressor
    sessions = sorted(df.session.unique())
    n = len(sessions)
    start = int(n * (1 - TEST_FRAC))
    block = (n - start) // N_FOLDS
    out = []
    for i in range(N_FOLDS):
        a = start + i * block
        b = a + block if i < N_FOLDS - 1 else n
        tr = sessions[: max(a - PURGE_SESSIONS, 0)]
        te = sessions[a:b]
        m_tr = df.session.isin(tr); m_te = df.session.isin(te)
        Xtr = df.loc[m_tr, feats].to_numpy(np.float32)
        ytr = df.loc[m_tr, col].to_numpy(np.float32)
        if shuffle:
            ytr = rng.permutation(ytr)
        mdl = CatBoostRegressor(**CB)
        mdl.fit(Xtr, ytr)
        thr = float(np.percentile(mdl.predict(Xtr), SEL_PCT))
        sub = df.loc[m_te, ["session", "sec", col]].copy()
        sub["pred"] = mdl.predict(df.loc[m_te, feats].to_numpy(np.float32))
        sub = sub[sub.pred > thr]
        sub["fold"] = i
        sub = sub.rename(columns={col: "R"})
        out.append(sub)
    return pd.concat(out, ignore_index=True)


def session_bootstrap(sel: pd.DataFrame, k: int, rng) -> tuple[float, float]:
    """95% interval of mean gross ticks, resampling SESSIONS not trades."""
    by = [g["R"].to_numpy() for _, g in sel.groupby("session")]
    ns = len(by)
    if ns < 2:
        return (np.nan, np.nan)
    means = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = rng.integers(0, ns, ns)
        means[b] = np.concatenate([by[i] for i in idx]).mean() * k
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main():
    df = pd.read_parquet(C.DATA / "features" / "rth_big_bracket.parquet")
    labels = [c for c in df.columns if c.startswith("R_")]
    feats = [c for c in df.columns if c not in labels + ["session", "sec"]]
    rng = np.random.default_rng(SEED)
    summary = []

    for k in BRACKETS:
        for side in SIDES:
            col = f"R_{side}_{k}"
            sel = walk(df, feats, col)
            g = sel.R.mean() * k
            n_sess = sel.session.nunique()
            per = sel.groupby("session").R.mean() * k

            print(f"\n################ K={k} {side} ################", flush=True)
            print(f"trades {len(sel)}  sessions {n_sess}  "
                  f"gross {g:+.3f} tk  net {g - COST_TICKS:+.3f} tk")

            # A. concentration
            top = per.sort_values(ascending=False)
            share = (sel.groupby("session").R.sum() * k).sort_values(ascending=False)
            tot = share.sum()
            print(f"  A. top-3 sessions carry {share.head(3).sum()/tot:6.1%} of total ticks"
                  if tot != 0 else "  A. total is zero")
            print(f"     best  {top.index[0].date()} {top.iloc[0]:+.1f} tk/trade | "
                  f"worst {top.index[-1].date()} {top.iloc[-1]:+.1f}")
            # leave-one-session-out worst case
            loo = np.array([((sel[sel.session != s].R.mean()) * k)
                            for s in sel.session.unique()])
            print(f"     leave-one-session-out mean range "
                  f"[{loo.min():+.2f}, {loo.max():+.2f}] tk")

            # B. session bootstrap
            lo, hi = session_bootstrap(sel, k, rng)
            print(f"  B. session bootstrap 95% CI [{lo:+.2f}, {hi:+.2f}] tk "
                  f"(cost {COST_TICKS})")

            # D. per fold
            pf = sel.groupby("fold").R.agg(["count", "mean"])
            pf["ticks"] = pf["mean"] * k
            print("  D. per fold ticks: " +
                  "  ".join(f"f{int(i)}={r.ticks:+.1f}(n{int(r['count'])})"
                            for i, r in pf.iterrows()))
            folds_pos = int((pf.ticks > COST_TICKS).sum())

            # E. one trade per session: the highest-prediction decision only
            one = sel.sort_values("pred", ascending=False).groupby("session").head(1)
            g1 = one.R.mean() * k
            lo1, hi1 = session_bootstrap(one, k, rng)
            print(f"  E. one per session: n {len(one)}  gross {g1:+.3f} tk  "
                  f"CI [{lo1:+.2f}, {hi1:+.2f}]")

            summary.append(dict(bracket=k, side=side, n=len(sel), n_sessions=n_sess,
                                gross_ticks=g, net_ticks=g - COST_TICKS,
                                boot_lo=lo, boot_hi=hi,
                                loo_min=float(loo.min()), loo_max=float(loo.max()),
                                folds_above_cost=folds_pos,
                                one_per_sess_n=len(one), one_per_sess_ticks=g1,
                                one_lo=lo1, one_hi=hi1))

    # C. placebo on the single best combo
    best = max(summary, key=lambda r: r["gross_ticks"])
    k, side = best["bracket"], best["side"]
    print(f"\n### C. placebo for the best combo K={k} {side} "
          f"({best['gross_ticks']:+.2f} tk) ###", flush=True)
    col = f"R_{side}_{k}"
    null = []
    for _ in track(range(N_PLACEBO), label="placebo"):
        s = walk(df, feats, col, shuffle=True, rng=rng)
        null.append(s.R.mean() * k)
    null = np.array(null)
    p = float((null >= best["gross_ticks"]).mean())
    print(f"placebo mean {null.mean():+.3f} tk  sd {null.std():.3f}  "
          f"p95 {np.percentile(null,95):+.3f}  p99 {np.percentile(null,99):+.3f}")
    print(f"p-value {p:.4f}")
    pd.DataFrame(dict(placebo_ticks=null)).to_csv(
        C.DATA / "reports" / "bracket_scaling_placebo.csv", index=False)

    out = pd.DataFrame(summary)
    out["placebo_p"] = np.where((out.bracket == k) & (out.side == side), p, np.nan)
    out.to_csv(C.DATA / "reports" / "bracket_scaling_audit.csv", index=False)
    print("\n" + out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
