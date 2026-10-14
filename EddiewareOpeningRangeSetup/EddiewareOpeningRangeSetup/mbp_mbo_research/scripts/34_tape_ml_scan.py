"""The one combination nobody has run: order flow AND bars, inside one model.

What has actually been tested, and what has not
-----------------------------------------------
Scripts 16-18 measured tape signals ONE AT A TIME: signed aggressor imbalance,
absorption, drive, each against a markout or a barrier. Script 27 ran a wide
model but fed it only bar-derived features, because the bar dataset spans the
whole RTH day while the tape only exists for 09:25-10:30.

Neither one asks whether order flow carries information CONDITIONALLY, that is
in combination with the state of the tape and of price. A univariate test of
imbalance cannot find "imbalance matters, but only when the book is thin and
the session has not yet picked a direction". That is the kind of structure a
tree model finds and a single regression cannot, and it is the last thing the
data on disk can answer for free.

Scope
-----
The tape window forces the scope: decisions every 60 s from 09:35 to 10:25 ET,
which is 51 per session and 150 sessions. Labels come from the 1s bars, so the
30-minute barrier can run past 10:30 even though the tape stops there.

Tape features, all causal, all from the 150-session tick file
-------------------------------------------------------------
    signed volume imbalance over 30 / 60 / 300 s
    the same restricted to LARGE prints, size >= the session's 90th percentile,
        which is the closest thing the tape has to an institutional footprint
    trade count and mean trade size against the session's own average
    sweep intensity: distinct price levels touched per second
    the share of volume that traded at a NEW extreme of the last 300 s
    first-order autocorrelation of signed volume, a crowding proxy

Guards, taken from what the K=150 audit taught today
----------------------------------------------------
Every number is reported with a SESSION bootstrap, never a trade bootstrap,
and the placebo is the same pipeline on shuffled training labels. Today's audit
measured that this selection procedure extracts +3.5 ticks (sd 10.8) from pure
noise at the 80th percentile and +4.5 ticks at extreme percentiles, so any
result below roughly +9 ticks gross is indistinguishable from the procedure
running on nothing. That number is the bar to clear, not zero.
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
BRACKETS = (20, 40)
TIMEOUT_S = 1800
GRID_S = 60
OPEN = 9 * 3600 + 30 * 60
DEC_FROM = (9 * 3600 + 35 * 60) - OPEN
DEC_TO = (10 * 3600 + 25 * 60) - OPEN
PLACEBO_BAR_TICKS = 9.0        # measured null of this procedure, see docstring

N_FOLDS = 5
TEST_FRAC = 0.5
PURGE = 5
SEL_PCT = 80
N_BOOT = 5000
N_PLACEBO = 100
SEED = 20261013
CB = dict(iterations=400, depth=6, learning_rate=0.05, loss_function="RMSE",
          random_seed=SEED, verbose=0, allow_writing_files=False)

PATH = C.DATA / "features" / "tape_ml_dataset.parquet"


def load_tape() -> pd.DataFrame:
    import duckdb
    con = duckdb.connect()
    con.execute("SET TimeZone='America/New_York'")
    src = (C.DATA / "tape" / "tape_trades_2026.parquet").as_posix()
    df = con.sql(f"""
        select session::DATE as session, ts_ns, px_t, size, sign
        from '{src}' order by session, ts_ns
    """).df()
    con.close()
    return df


def tape_features(t: pd.DataFrame, open_ns: int, dec: np.ndarray) -> pd.DataFrame:
    """Aggregate the tick tape onto the same decision grid, causally.

    Everything is built from per-second sums first, so a feature window is a
    prefix-sum difference and cannot accidentally reach past the decision.
    """
    rel = ((t.ts_ns.to_numpy() - open_ns) // 1_000_000_000).astype(np.int64)
    n = int(dec.max()) + 1
    keep = (rel >= 0) & (rel < n)
    rel = rel[keep]
    size = t["size"].to_numpy()[keep].astype(float)
    sgn = t["sign"].to_numpy()[keep].astype(float)
    px = t.px_t.to_numpy()[keep].astype(float)

    big_thr = np.percentile(size, 90) if len(size) else 1.0
    big = size >= big_thr

    def acc(vals):
        out = np.zeros(n)
        np.add.at(out, rel, vals)
        return np.cumsum(out)

    c_vol = acc(size)
    c_sv = acc(size * sgn)
    c_bigvol = acc(size * big)
    c_bigsv = acc(size * sgn * big)
    c_cnt = acc(np.ones_like(size))

    # distinct price levels touched per second, a cheap sweep proxy
    lvl = pd.DataFrame({"s": rel, "p": px}).groupby("s").p.nunique()
    per_sec_lvl = np.zeros(n)
    per_sec_lvl[lvl.index.to_numpy()] = lvl.to_numpy()
    c_lvl = np.cumsum(per_sec_lvl)

    def d(c, w):
        j = np.maximum(dec - w, 0)
        return c[dec] - c[j]

    f = pd.DataFrame(index=np.arange(len(dec)))
    for w in (30, 60, 300):
        v = np.maximum(d(c_vol, w), 1.0)
        f[f"t_imb{w}"] = d(c_sv, w) / v
        f[f"t_vol{w}"] = d(c_vol, w)
        f[f"t_cnt{w}"] = d(c_cnt, w)
        f[f"t_avgsz{w}"] = d(c_vol, w) / np.maximum(d(c_cnt, w), 1.0)
        bv = np.maximum(d(c_bigvol, w), 1.0)
        f[f"t_bigimb{w}"] = d(c_bigsv, w) / bv
        f[f"t_bigshare{w}"] = d(c_bigvol, w) / v
        f[f"t_lvl{w}"] = d(c_lvl, w) / np.maximum(w, 1)
    # each window against the session's own pace so far, which removes the
    # level difference between a quiet day and a busy one
    pace = np.maximum(c_vol[dec] / np.maximum(dec, 1), 1e-6)
    for w in (30, 60, 300):
        f[f"t_volr{w}"] = f[f"t_vol{w}"] / (pace * w)
    return f


def build() -> pd.DataFrame:
    bars = DS.load_bars()
    tape = load_tape()
    bar_groups = dict(tuple(bars.groupby("session", sort=True)))
    tape_groups = dict(tuple(tape.groupby("session", sort=True)))

    rows = []
    for sess in track(sorted(bar_groups), label="tape+bar features"):
        if sess not in tape_groups:
            continue
        s = DS.session_grid(bar_groups[sess])
        if not s:
            continue
        hi = min(DEC_TO, s["n"] - TIMEOUT_S - 2)
        if hi <= DEC_FROM:
            continue
        dec = np.arange(DEC_FROM, hi, GRID_S)
        fb = DS.build_features(s, dec)
        t = tape_groups[sess]
        open_ns = int(pd.Timestamp(sess).tz_localize(C.NY).value) + OPEN * 1_000_000_000
        ft = tape_features(t, open_ns, dec)
        f = pd.concat([fb.reset_index(drop=True), ft.reset_index(drop=True)], axis=1)
        f.insert(0, "session", pd.Timestamp(sess))
        f.insert(1, "sec", dec)
        for k in BRACKETS:
            f[f"R_long_{k}"] = DS.label_side(s, dec, k, +1)
            f[f"R_short_{k}"] = DS.label_side(s, dec, k, -1)
        rows.append(f)
    df = pd.concat(rows, ignore_index=True)
    return df.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)


def walk(df, feats, col, shuffle=False, rng=None):
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
        ytr = df.loc[m_tr, col].to_numpy(np.float32)
        if shuffle:
            ytr = rng.permutation(ytr)
        mdl = CatBoostRegressor(**CB)
        mdl.fit(df.loc[m_tr, feats].to_numpy(np.float32), ytr)
        thr = float(np.percentile(mdl.predict(df.loc[m_tr, feats].to_numpy(np.float32)), SEL_PCT))
        sub = df.loc[m_te, ["session", col]].rename(columns={col: "R"}).copy()
        sub["pred"] = mdl.predict(df.loc[m_te, feats].to_numpy(np.float32))
        out.append(sub[sub.pred > thr].assign(fold=i))
    return pd.concat(out, ignore_index=True)


def sess_boot(sel, k, rng):
    by = [g.R.to_numpy() for _, g in sel.groupby("session")]
    if len(by) < 2:
        return np.nan, np.nan
    m = np.array([np.concatenate([by[i] for i in rng.integers(0, len(by), len(by))]).mean() * k
                  for _ in range(N_BOOT)])
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def main():
    if PATH.exists():
        df = pd.read_parquet(PATH)
        print(f"reusing {PATH}")
    else:
        df = build()
        df.to_parquet(PATH, index=False)
    labels = [c for c in df.columns if c.startswith("R_")]
    feats = [c for c in df.columns if c not in labels + ["session", "sec"]]
    tape_feats = [c for c in feats if c.startswith("t_")]
    print(f"dataset {df.shape}, {df.session.nunique()} sessions, "
          f"{len(feats)} features of which {len(tape_feats)} from the tape\n", flush=True)

    rng = np.random.default_rng(SEED)
    rows = []
    # bars-only is the control: if adding the tape changes nothing, the tape
    # carries nothing conditional either
    for tag, fs in (("bars+tape", feats), ("bars_only", [c for c in feats if not c.startswith("t_")])):
        for k in BRACKETS:
            for side in ("long", "short"):
                sel = walk(df, fs, f"R_{side}_{k}")
                g = sel.R.mean() * k
                lo, hi = sess_boot(sel, k, rng)
                pf = sel.groupby("fold").R.mean() * k
                print(f"{tag:10} K={k:<3} {side:<5} n {len(sel):5d} sess {sel.session.nunique():3d} "
                      f"WR {(sel.R>0).mean():.4f} gross {g:+7.3f} tk  net {g-COST_TICKS:+7.3f}  "
                      f"CI [{lo:+6.2f},{hi:+6.2f}]  folds " +
                      " ".join(f"{v:+.1f}" for v in pf), flush=True)
                rows.append(dict(featureset=tag, bracket=k, side=side, n=len(sel),
                                 n_sessions=int(sel.session.nunique()),
                                 wr=float((sel.R > 0).mean()), gross_ticks=g,
                                 net_ticks=g - COST_TICKS, boot_lo=lo, boot_hi=hi))

    out = pd.DataFrame(rows)
    out.to_csv(C.DATA / "reports" / "tape_ml_scan.csv", index=False)

    best = out[out.featureset == "bars+tape"].sort_values("gross_ticks").iloc[-1]
    print(f"\nbest bars+tape cell: K={int(best.bracket)} {best.side} "
          f"{best.gross_ticks:+.3f} tk, CI [{best.boot_lo:+.2f}, {best.boot_hi:+.2f}]")
    print(f"bar to clear: the placebo null of this procedure is ~+{PLACEBO_BAR_TICKS} tk gross, "
          f"measured in script 31. Cost is {COST_TICKS} tk.")
    if best.boot_lo > PLACEBO_BAR_TICKS:
        print("-> clears both. Run the placebo and treat as a live candidate.")
        col = f"R_{best.side}_{int(best.bracket)}"
        null = []
        for _ in track(range(N_PLACEBO), label="placebo"):
            null.append(walk(df, feats, col, shuffle=True, rng=rng).R.mean() * int(best.bracket))
        null = np.array(null)
        print(f"placebo mean {null.mean():+.3f} p95 {np.percentile(null,95):+.3f} "
              f"p {(null >= best.gross_ticks).mean():.4f}")
    else:
        print("-> does not clear. The tape adds nothing conditional either.")
    print(f"\nwrote {C.DATA / 'reports' / 'tape_ml_scan.csv'}")


if __name__ == "__main__":
    main()
