"""Codex's remaining two attacks: the tie rule, and the sparse executable policy.

Attack 2: is the tie rule hiding an edge?
-----------------------------------------
When a single 1-second bar touches both barriers, the label charges the stop.
That is the honest default at this resolution, but it is a conservative BOUND.
Codex turned the worry into arithmetic: flipping one wrongly-charged stop to a
target is worth 2K ticks, so recovering the missing 1.35 ticks per trade needs

    K=20   3.38% of ALL decisions to be ambiguous AND actually targets first
    K=40   1.69%

and that is a lower bound on the ambiguous fraction itself, since only some of
the ambiguous ones resolved favourably. This measures the fraction directly. If
it is below the bar, the tie rule cannot be the reason the result is negative,
and the question is closed without needing the tape at all.

Attack 3: the top quintile is not an executable policy
-------------------------------------------------------
Averaging the top 20% of predictions can bury a rare, genuinely profitable
signal under four fifths of noise. A trader does not take 20% of every day's
decisions; they take at most one. So this also measures the policy that a
person could actually run:

    at most ONE trade per session, the FIRST decision of the day whose
    prediction clears a threshold fixed on training data, abstaining entirely
    on days where nothing clears it, no overlapping positions.

The threshold is swept over the 80th, 95th, 99th and 99.5th training
percentiles. "First to clear" matters: taking the day's best prediction in
hindsight is not a policy, it is a look-ahead. Every number carries a SESSION
bootstrap, and the bar to clear is not zero but the placebo null of this
selection procedure, measured at about +3.5 ticks gross in script 31.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as C
from progress import track


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DS = _load("ds26", "26_rth_ml_dataset.py")

TICK = 0.25
COST_TICKS = 1.8
TIMEOUT_S = 1800
GRID_S = 60
PCTS = (80, 95, 99, 99.5)
BRACKETS = (20, 40)
N_FOLDS = 5
TEST_FRAC = 0.5
PURGE = 5
N_BOOT = 5000
PLACEBO_BAR = 3.5
SEED = 20261013
CB = dict(iterations=400, depth=6, learning_rate=0.05, loss_function="RMSE",
          random_seed=SEED, verbose=0, allow_writing_files=False)


def ambiguous_fraction(bars_groups, sessions, k_list):
    """Share of decisions whose outcome was settled by a both-barriers bar."""
    counts = {k: [0, 0] for k in k_list}       # [ambiguous, total]
    for sess in track(sessions, label="tie audit"):
        s = DS.session_grid(bars_groups[sess])
        if not s:
            continue
        op, hi, lo, n = s["open"], s["high"], s["low"], s["n"]
        a = (9 * 3600 + 35 * 60) - (9 * 3600 + 30 * 60)
        b = min((15 * 3600 + 30 * 60) - (9 * 3600 + 30 * 60), n - TIMEOUT_S - 2)
        if b <= a:
            continue
        for sec in range(a, b, GRID_S):
            e = sec + 1
            if e >= n:
                continue
            entry = op[e]
            j = min(e + TIMEOUT_S, n - 1)
            h_ = hi[e:j + 1]; l_ = lo[e:j + 1]
            for k in k_list:
                kk = k * TICK
                m_tp = h_ >= entry + kk
                m_sl = l_ <= entry - kk
                counts[k][1] += 1
                if not (m_tp.any() or m_sl.any()):
                    continue
                i_tp = int(np.argmax(m_tp)) if m_tp.any() else 1 << 30
                i_sl = int(np.argmax(m_sl)) if m_sl.any() else 1 << 30
                # the decisive bar is ambiguous when BOTH fire on the same index
                if i_tp == i_sl:
                    counts[k][0] += 1
    return counts


def sparse_policy(df, feats, col, k, rng):
    """At most one trade per session: first prediction of the day over the bar."""
    from catboost import CatBoostRegressor
    sess = sorted(df.session.unique())
    n = len(sess)
    start = int(n * (1 - TEST_FRAC))
    block = (n - start) // N_FOLDS
    picks = {p: [] for p in PCTS}
    n_days = {p: 0 for p in PCTS}
    for i in range(N_FOLDS):
        a = start + i * block
        b = a + block if i < N_FOLDS - 1 else n
        tr = sess[: max(a - PURGE, 0)]
        te = sess[a:b]
        m_tr = df.session.isin(tr); m_te = df.session.isin(te)
        mdl = CatBoostRegressor(**CB)
        mdl.fit(df.loc[m_tr, feats].to_numpy(np.float32),
                df.loc[m_tr, col].to_numpy(np.float32))
        ptr = mdl.predict(df.loc[m_tr, feats].to_numpy(np.float32))
        sub = df.loc[m_te, ["session", "sec", col]].copy()
        sub["pred"] = mdl.predict(df.loc[m_te, feats].to_numpy(np.float32))
        sub = sub.sort_values(["session", "sec"])
        for p in PCTS:
            thr = float(np.percentile(ptr, p))
            over = sub[sub.pred > thr]
            first = over.groupby("session").head(1)      # FIRST, not best
            picks[p].append(first[["session", col]].rename(columns={col: "R"}))
            n_days[p] += len(te)
    return {p: (pd.concat(v, ignore_index=True) if v else pd.DataFrame()) for p, v in picks.items()}, n_days


def boot(sel, k, rng):
    by = [g.R.to_numpy() for _, g in sel.groupby("session")]
    if len(by) < 2:
        return np.nan, np.nan
    m = np.array([np.concatenate([by[i] for i in rng.integers(0, len(by), len(by))]).mean() * k
                  for _ in range(N_BOOT)])
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def main():
    bars = DS.load_bars()
    groups = dict(tuple(bars.groupby("session", sort=True)))
    sessions = sorted(groups)

    print("=== ATTACK 2: how often is the outcome decided by an ambiguous bar? ===")
    counts = ambiguous_fraction(groups, sessions, BRACKETS)
    need = {20: 0.0338, 40: 0.0169}
    arows = []
    print(f"\n{'K':>5} {'ambiguous':>10} {'total':>8} {'share':>8} {'needed':>8} {'verdict':>12}")
    for k in BRACKETS:
        amb, tot = counts[k]
        share = amb / max(tot, 1)
        v = "could matter" if share >= need[k] else "cannot explain it"
        print(f"{k:>5} {amb:>10} {tot:>8} {share:>8.4%} {need[k]:>8.2%} {v:>18}")
        arows.append(dict(bracket=k, ambiguous=amb, total=tot, share=share,
                          needed=need[k], verdict=v))
    pd.DataFrame(arows).to_csv(C.DATA / "reports" / "tie_rule_audit.csv", index=False)

    print("\n=== ATTACK 3: one trade per session, first signal over the bar ===")
    df = pd.read_parquet(C.DATA / "features" / "rth_ml_dataset.parquet")
    labels = [c for c in df.columns if c.startswith("R_")]
    feats = [c for c in df.columns if c not in labels + ["session", "sec"]]
    rng = np.random.default_rng(SEED)

    rows = []
    print(f"{'K':>4} {'side':>6} {'pct':>6} {'trades':>7} {'days':>6} {'WR':>7} "
          f"{'gross_tk':>9} {'net_tk':>8} {'CI_tk':>20}")
    for k in BRACKETS:
        for side in ("long", "short"):
            res, nd = sparse_policy(df, feats, f"R_{side}_{k}", k, rng)
            for p in PCTS:
                sel = res[p]
                if len(sel) < 10:
                    print(f"{k:>4} {side:>6} {p:>6} {len(sel):>7}   too few")
                    continue
                g = sel.R.mean() * k
                lo, hi = boot(sel, k, rng)
                print(f"{k:>4} {side:>6} {p:>6} {len(sel):>7} {nd[p]:>6} "
                      f"{(sel.R>0).mean():>7.4f} {g:>+9.3f} {g-COST_TICKS:>+8.3f} "
                      f"{f'[{lo:+.2f},{hi:+.2f}]':>20}")
                rows.append(dict(bracket=k, side=side, pct=p, trades=len(sel),
                                 days=nd[p], wr=float((sel.R > 0).mean()),
                                 gross_ticks=g, net_ticks=g - COST_TICKS,
                                 lo95=lo, hi95=hi))
    out = pd.DataFrame(rows)
    out.to_csv(C.DATA / "reports" / "sparse_policy.csv", index=False)
    live = out[(out.lo95 > PLACEBO_BAR)]
    print(f"\ncells whose session-bootstrap LOWER bound clears the "
          f"+{PLACEBO_BAR} tk placebo null: {len(live)}")
    if len(live):
        print(live.to_string(index=False))
    print(f"\nwrote tie_rule_audit.csv and sparse_policy.csv to {C.DATA/'reports'}")


if __name__ == "__main__":
    main()
