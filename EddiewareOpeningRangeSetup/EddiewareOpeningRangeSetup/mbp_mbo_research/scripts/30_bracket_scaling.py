"""Does the model's gross edge GROW with the bracket, or is it a fixed tick?

This is the question that decides whether the 1s price/volume space can ever
clear its own cost, and it has a sharp answer either way.

Script 27 measured the same gross edge, about +0.45 ticks per trade, at K=20
and at K=40. Two readings fit that:

    fixed-tick    the edge is an entry-timing effect worth a constant ~0.45
                  ticks whatever the bracket. Cost is a constant 1.8 ticks, so
                  it never clears, at any K. The space is closed.
    proportional  the edge is a genuine directional drift. Then it scales with
                  the horizon the bracket implies, the gross tick EV rises with
                  K, and somewhere above K=40 it crosses 1.8 ticks.

Two points cannot separate a flat line from a rising one when both sit inside
the noise, so this adds K = 80 and K = 150 with a timeout long enough that a
150-tick barrier can actually be reached (a 30-minute timeout would resolve
most of them by mark-to-market and measure the timeout rule instead of the
barrier). K=150 is also the stop size that script 28 found maximises the Lucid
50K pass probability under ZERO edge, so it is the size that matters most.

Pre-registered reading of the result
------------------------------------
* gross tick EV roughly flat across K=20..150  -> fixed-tick world, the 1s
  price/volume space is closed, and the budget moves to order-book data.
* gross tick EV rising and crossing ~1.8 at some K -> proportional world, and
  that K is the configuration to test out of sample on fresh data.
Nothing else counts as a pass. In particular a single large K cell with a wide
interval is not a rising trend.
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


def _load(name: str, fname: str):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DS = _load("ds26", "26_rth_ml_dataset.py")

COST_TICKS = 1.8
BRACKETS = (80, 150)
TIMEOUT_S = 3 * 3600          # a 150-tick barrier needs room to be reached
GRID_S = 300                  # 5-minute decisions; the labels overlap heavily
DEC_FROM = (9 * 3600 + 35 * 60) - (9 * 3600 + 30 * 60)
DEC_TO = (13 * 3600 + 0 * 60) - (9 * 3600 + 30 * 60)

N_FOLDS = 5
TEST_FRAC = 0.5
PURGE_SESSIONS = 5
SEL_PCT = 80
SEED = 20261013
CB = dict(iterations=400, depth=6, learning_rate=0.05, loss_function="RMSE",
          random_seed=SEED, verbose=0, allow_writing_files=False)


def label_side_long_timeout(s, dec, k, side):
    """Same first-passage rule as script 26, with the longer timeout."""
    op, hi, lo, c, n = s["open"], s["high"], s["low"], s["close"], s["n"]
    out = np.full(len(dec), np.nan)
    kk = k * DS.TICK
    INF = 1 << 30
    for m, i in enumerate(dec):
        e = i + 1
        if e >= n:
            continue
        entry = op[e]
        tp = entry + side * kk
        sl = entry - side * kk
        j = min(e + TIMEOUT_S, n - 1)
        h = hi[e:j + 1]; l = lo[e:j + 1]
        if side > 0:
            m_tp = h >= tp; m_sl = l <= sl
        else:
            m_tp = l <= tp; m_sl = h >= sl
        i_tp = int(np.argmax(m_tp)) if m_tp.any() else INF
        i_sl = int(np.argmax(m_sl)) if m_sl.any() else INF
        if i_tp == INF and i_sl == INF:
            out[m] = side * (c[j] - entry) / kk
        elif i_sl <= i_tp:
            out[m] = -1.0
        else:
            out[m] = 1.0
    return out


def build() -> pd.DataFrame:
    bars = DS.load_bars()
    groups = dict(tuple(bars.groupby("session", sort=True)))
    rows = []
    for sess in track(sorted(groups), label="big-bracket labels"):
        s = DS.session_grid(groups[sess])
        if not s:
            continue
        hi_sec = min(DEC_TO, s["n"] - TIMEOUT_S - 2)
        if hi_sec <= DEC_FROM:
            continue
        dec = np.arange(DEC_FROM, hi_sec, GRID_S)
        f = DS.build_features(s, dec)
        f.insert(0, "session", pd.Timestamp(sess))
        f.insert(1, "sec", dec)
        for k in BRACKETS:
            f[f"R_long_{k}"] = label_side_long_timeout(s, dec, k, +1)
            f[f"R_short_{k}"] = label_side_long_timeout(s, dec, k, -1)
        rows.append(f)
    df = pd.concat(rows, ignore_index=True)
    return df.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)


def walk(df, feats, col):
    from catboost import CatBoostRegressor
    sessions = sorted(df.session.unique())
    n = len(sessions)
    start = int(n * (1 - TEST_FRAC))
    block = (n - start) // N_FOLDS
    sel, base = [], []
    for i in range(N_FOLDS):
        a = start + i * block
        b = a + block if i < N_FOLDS - 1 else n
        tr = sessions[: max(a - PURGE_SESSIONS, 0)]
        te = sessions[a:b]
        m_tr = df.session.isin(tr); m_te = df.session.isin(te)
        Xtr = df.loc[m_tr, feats].to_numpy(np.float32)
        ytr = df.loc[m_tr, col].to_numpy(np.float32)
        Xte = df.loc[m_te, feats].to_numpy(np.float32)
        yte = df.loc[m_te, col].to_numpy(np.float32)
        mdl = CatBoostRegressor(**CB)
        mdl.fit(Xtr, ytr)
        thr = float(np.percentile(mdl.predict(Xtr), SEL_PCT))
        sel.append(yte[mdl.predict(Xte) > thr])
        base.append(yte)
    return np.concatenate(sel), np.concatenate(base)


def main():
    path = C.DATA / "features" / "rth_big_bracket.parquet"
    if path.exists():
        df = pd.read_parquet(path)
        print(f"reusing {path}")
    else:
        df = build()
        df.to_parquet(path, index=False)
    print(f"dataset {df.shape}, {df.session.nunique()} sessions", flush=True)

    labels = [c for c in df.columns if c.startswith("R_")]
    feats = [c for c in df.columns if c not in labels + ["session", "sec"]]

    rows = []
    print(f"\n{'K':>5} {'side':>6} {'n':>6} {'WR':>7} {'gross_tk':>9} "
          f"{'net_tk':>8} {'base_tk':>8} {'lift_tk':>8}")
    for k in BRACKETS:
        for side in ("long", "short"):
            col = f"R_{side}_{k}"
            sel, base = walk(df, feats, col)
            g = sel.mean() * k
            bt = base.mean() * k
            print(f"{k:>5} {side:>6} {len(sel):>6} {(sel>0).mean():>7.4f} "
                  f"{g:>+9.3f} {g-COST_TICKS:>+8.3f} {bt:>+8.3f} {g-bt:>+8.3f}")
            rows.append(dict(bracket=k, side=side, n=len(sel),
                             wr=float((sel > 0).mean()),
                             ev_gross_ticks=float(g),
                             ev_net_ticks=float(g - COST_TICKS),
                             baseline_ticks=float(bt),
                             lift_ticks=float(g - bt)))
    out = pd.DataFrame(rows)
    out.to_csv(C.DATA / "reports" / "bracket_scaling.csv", index=False)
    print(f"\nwrote {C.DATA / 'reports' / 'bracket_scaling.csv'}")
    print("\ncompare against script 27: K=20 gross +0.19/+0.46 tk, "
          "K=40 gross +0.47/+0.20 tk (long/short)")


if __name__ == "__main__":
    main()
