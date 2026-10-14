"""Codex's two concrete attacks on the negative, both answerable for free.

Attack 1: the bracket comparison was never paired
--------------------------------------------------
I wrote that the model's gross edge is "~0.45 ticks at both K=20 and K=40", and
read that constancy as evidence of an entry-timing artifact rather than real
drift. Codex checked the four numbers: long gives 0.190 and 0.472 ticks, short
gives 0.456 and 0.200. The ~0.45 comes from picking a DIFFERENT direction at
each K. On top of that the model reselects its entries for every K, so the two
cells do not even describe the same trades. It is not a paired experiment and
the constancy I read off it was not there.

The fix is to freeze the entries and the direction ONCE, then apply every
bracket to those identical observations, and alongside them measure the signed
displacement at a grid of horizons with the entry delayed by 0, 1 and 5
seconds. The two worlds separate cleanly:

    transient drift   displacement grows with the horizon and then plateaus,
                      and survives a 1-5 second delay. Roughly constant ticks
                      across brackets is then a real, if small, effect.
    artifact          displacement is there at 1 second and gone by 5, or dies
                      as soon as the entry is delayed. Nothing to trade.

Attack 2: charging every ambiguous second to the stop is a bound, not an estimate
---------------------------------------------------------------------------------
When one 1s bar touches both barriers, the label charges the stop. That is the
right default at 1-second resolution, but it is a conservative bound: some of
those bars really did touch the target first. Codex did the arithmetic that
turns this from a worry into a test. Flipping a false stop to a target is worth
2K ticks, so recovering the missing 1.35 ticks per trade needs

    K=20   3.38% of ALL trades to be wrongly-charged stops
    K=40   1.69%

The tick tape resolves the ordering exactly inside the second, for 09:25-10:30.
If the ambiguous fraction is not even that large, the tie rule cannot be hiding
the result, and the bound can stop being a worry.
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
PAIRED_K = (20, 40, 80, 150)
HORIZONS = (1, 5, 15, 60, 300, 900)
DELAYS = (0, 1, 5)
TIMEOUT_S = 3 * 3600
N_FOLDS = 5
TEST_FRAC = 0.5
PURGE = 5
SEL_PCT = 80
N_BOOT = 5000
SEED = 20261013
CB = dict(iterations=400, depth=6, learning_rate=0.05, loss_function="RMSE",
          random_seed=SEED, verbose=0, allow_writing_files=False)


def frozen_entries(df, feats, col):
    """Select once, with the K=40 long model, and never reselect again."""
    from catboost import CatBoostRegressor
    sess = sorted(df.session.unique())
    n = len(sess)
    start = int(n * (1 - TEST_FRAC))
    block = (n - start) // N_FOLDS
    out = []
    for i in range(N_FOLDS):
        a = start + i * block
        b = a + block if i < N_FOLDS - 1 else n
        tr = sess[: max(a - PURGE, 0)]
        te = sess[a:b]
        m_tr = df.session.isin(tr); m_te = df.session.isin(te)
        mdl = CatBoostRegressor(**CB)
        mdl.fit(df.loc[m_tr, feats].to_numpy(np.float32),
                df.loc[m_tr, col].to_numpy(np.float32))
        thr = float(np.percentile(mdl.predict(df.loc[m_tr, feats].to_numpy(np.float32)), SEL_PCT))
        sub = df.loc[m_te, ["session", "sec"]].copy()
        sub["pred"] = mdl.predict(df.loc[m_te, feats].to_numpy(np.float32))
        out.append(sub[sub.pred > thr].assign(fold=i))
    return pd.concat(out, ignore_index=True)


def boot_ci(vals_by_session, scale=1.0, rng=None):
    by = list(vals_by_session)
    if len(by) < 2:
        return np.nan, np.nan
    m = np.array([np.concatenate([by[i] for i in rng.integers(0, len(by), len(by))]).mean() * scale
                  for _ in range(N_BOOT)])
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def main():
    path = C.DATA / "features" / "rth_big_bracket.parquet"
    if not path.exists():
        print(f"missing {path}; run 30_bracket_scaling.py first")
        return 1
    df = pd.read_parquet(path)
    labels = [c for c in df.columns if c.startswith("R_")]
    feats = [c for c in df.columns if c not in labels + ["session", "sec"]]
    rng = np.random.default_rng(SEED)

    print("freezing the entry set once, with the K=80 long model ...", flush=True)
    ent = frozen_entries(df, feats, "R_long_80")
    print(f"frozen entries: {len(ent)} across {ent.session.nunique()} sessions\n")

    bars = DS.load_bars()
    groups = dict(tuple(bars.groupby("session", sort=True)))

    # ---- attack 1: the same entries, every bracket, every horizon ----------
    disp = {(h, d): [] for h in HORIZONS for d in DELAYS}
    brk = {k: [] for k in PAIRED_K}
    keys = []
    for sess, g in track(list(ent.groupby("session")), label="paired measurement"):
        s = DS.session_grid(groups[sess])
        if not s:
            continue
        op, hi, lo, c, n = s["open"], s["high"], s["low"], s["close"], s["n"]
        for sec in g.sec.to_numpy():
            keys.append(sess)
            for d in DELAYS:
                e = sec + 1 + d
                if e >= n:
                    for h in HORIZONS:
                        disp[(h, d)].append(np.nan)
                    continue
                entry = op[e]
                for h in HORIZONS:
                    j = min(e + h, n - 1)
                    disp[(h, d)].append((c[j] - entry) / TICK)
            e = sec + 1
            for k in PAIRED_K:
                if e >= n:
                    brk[k].append(np.nan)
                    continue
                entry = op[e]
                kk = k * TICK
                j = min(e + TIMEOUT_S, n - 1)
                h_ = hi[e:j + 1]; l_ = lo[e:j + 1]
                m_tp = h_ >= entry + kk
                m_sl = l_ <= entry - kk
                i_tp = int(np.argmax(m_tp)) if m_tp.any() else 1 << 30
                i_sl = int(np.argmax(m_sl)) if m_sl.any() else 1 << 30
                if i_tp == (1 << 30) and i_sl == (1 << 30):
                    brk[k].append((c[j] - entry) / kk)
                elif i_sl <= i_tp:
                    brk[k].append(-1.0)
                else:
                    brk[k].append(1.0)

    keys = np.array(keys)
    print("=== signed displacement on the FROZEN long entries, in ticks ===")
    print(f"{'horizon':>8} " + "".join(f"{'delay ' + str(d) + 's':>16}" for d in DELAYS))
    drows = []
    for h in HORIZONS:
        cells = []
        for d in DELAYS:
            v = np.array(disp[(h, d)], dtype=float)
            ok = ~np.isnan(v)
            by = [v[ok][keys[ok] == s] for s in np.unique(keys[ok])]
            lo_, hi_ = boot_ci(by, 1.0, rng)
            cells.append(f"{v[ok].mean():+7.2f}[{lo_:+.1f},{hi_:+.1f}]")
            drows.append(dict(horizon=h, delay=d, mean_ticks=float(v[ok].mean()),
                              lo95=lo_, hi95=hi_, n=int(ok.sum())))
        print(f"{h:>8} " + "".join(f"{c:>16}" for c in cells))

    print("\n=== the SAME entries, every bracket (paired at last) ===")
    print(f"{'K':>5} {'n':>5} {'WR':>7} {'gross_R':>9} {'gross_tk':>9} {'net_tk':>8} "
          f"{'CI_tk':>20}")
    brows = []
    for k in PAIRED_K:
        v = np.array(brk[k], dtype=float)
        ok = ~np.isnan(v)
        by = [v[ok][keys[ok] == s] for s in np.unique(keys[ok])]
        lo_, hi_ = boot_ci(by, k, rng)
        g = v[ok].mean() * k
        print(f"{k:>5} {ok.sum():>5} {(v[ok]>0).mean():>7.4f} {v[ok].mean():>+9.4f} "
              f"{g:>+9.3f} {g-COST_TICKS:>+8.3f} {f'[{lo_:+.2f},{hi_:+.2f}]':>20}")
        brows.append(dict(bracket=k, n=int(ok.sum()), wr=float((v[ok] > 0).mean()),
                          gross_r=float(v[ok].mean()), gross_ticks=g,
                          net_ticks=g - COST_TICKS, lo95=lo_, hi95=hi_))

    pd.DataFrame(drows).to_csv(C.DATA / "reports" / "paired_displacement.csv", index=False)
    pd.DataFrame(brows).to_csv(C.DATA / "reports" / "paired_brackets.csv", index=False)
    print(f"\nwrote paired_displacement.csv and paired_brackets.csv to {C.DATA/'reports'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
