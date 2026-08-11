# -*- coding: utf-8 -*-
"""Push win-rate as high as possible while keeping realized R:R >= 1.

Goal condition: WR >= 80%, R:R >= 1:1, >= 4 trades/month. The only free lever
left on price/volume data is trade management. High WR under R:R>=1 needs either
(a) symmetric small brackets, or (b) breakeven management so most give-backs
scratch at 0 instead of a full loss.

We run several WR-oriented managements on ALL UP breakouts, then on the robust
subset (UP + vol_per_tick not-HIGH), and report per year:
  WR_all   = wins / all trades (scratches count as non-win)
  WR_dec   = wins / (wins+losses)   (excludes breakeven scratches)
  RR_real  = avg win ticks / avg loss ticks
  trades/mo, EV net.
Then a CatBoost precision frontier: at the >=4/mo frequency floor, what is the
best out-of-sample WR the model can buy on a 60/60 (R:R 1) bracket.
"""

from __future__ import annotations

import glob
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

from progress import track

TICK = 0.25
OR_START, OR_END, SCAN_START = "13:30:00", "13:31:00", "13:31:00"
DBN_ROOT = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\data\raw_dbn_2")
OUT_DIR = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")

# management configs: (name, kind, params)
#  sym  : fixed symmetric bracket tp=sl=T  -> RR 1
#  be   : tp=T, sl=T, move stop to breakeven after +A  -> RR 1, scratches at 0
CONFIGS = [
    ("sym_20", "sym", dict(T=20)),
    ("sym_30", "sym", dict(T=30)),
    ("sym_40", "sym", dict(T=40)),
    ("be_30_10", "be", dict(T=30, A=10)),
    ("be_40_15", "be", dict(T=40, A=15)),
    ("be_50_20", "be", dict(T=50, A=20)),
    ("be_60_20", "be", dict(T=60, A=20)),
]


def load_session(date):
    hits = glob.glob(str(DBN_ROOT / date / "ohlcv-1s-full" / "*.dbn.zst"))
    if not hits:
        return None
    return db.DBNStore.from_file(hits[0]).to_df()[["open", "high", "low", "close", "volume"]].sort_index()


def find_breakout(df):
    day = df.index[0].strftime("%Y-%m-%d")
    orw = df.between_time(OR_START, OR_END, inclusive="left")
    if orw.empty:
        return None
    oh, ol = float(orw["high"].max()), float(orw["low"].min())
    post = df.loc[df.index >= pd.Timestamp(f"{day} {SCAN_START}", tz="UTC")]
    if post.empty:
        return None
    up = post.index[post["high"] > oh]
    dn = post.index[post["low"] < ol]
    tu = up[0] if len(up) else None
    td = dn[0] if len(dn) else None
    if tu is None and td is None:
        return None
    if td is None or (tu is not None and tu <= td):
        return "UP", oh, 1, post.loc[post.index >= tu]
    return "DOWN", ol, -1, post.loc[post.index >= td]


def sim(fwd, entry, sign, kind, p):
    hs, ls, cs = fwd["high"].to_numpy(), fwd["low"].to_numpy(), fwd["close"].to_numpy()
    if kind == "sym":
        T = p["T"]
        tp = entry + sign * T * TICK
        sl = entry - sign * T * TICK
        for h, l in zip(hs, ls):
            if sign == 1:
                if l <= sl:
                    return -T
                if h >= tp:
                    return T
            else:
                if h >= sl:
                    return -T
                if l <= tp:
                    return T
        return (cs[-1] - entry) / TICK * sign
    # breakeven
    T, A = p["T"], p["A"]
    tp = entry + sign * T * TICK
    stop = entry - sign * T * TICK
    be_trig = entry + sign * A * TICK
    be = False
    for h, l in zip(hs, ls):
        if sign == 1:
            if l <= stop:
                return round((stop - entry) / TICK)
            if h >= tp:
                return T
            if not be and h >= be_trig:
                stop, be = entry, True
        else:
            if h >= stop:
                return round((entry - stop) / TICK)
            if l <= tp:
                return T
            if not be and l <= be_trig:
                stop, be = entry, True
    return (cs[-1] - entry) / TICK * sign


def main():
    dates = sorted(p.name for p in DBN_ROOT.iterdir() if p.is_dir())
    rows = []
    for d in track(dates, label="WR search"):
        try:
            df = load_session(d)
            if df is None or df.empty:
                continue
            bo = find_breakout(df)
            if bo is None:
                continue
            direction, entry, sign, fwd = bo
            rec = {"date": d, "up": int(sign == 1)}
            for name, kind, p in CONFIGS:
                rec[name] = sim(fwd, entry, sign, kind, p)
            rows.append(rec)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {d}: {exc}")
    r = pd.DataFrame(rows)
    r["year"] = pd.to_datetime(r["date"]).dt.year
    # attach robust filter flag from features file
    feat = pd.read_csv(OUT_DIR / "orb_features_labels_1s.csv")[["date", "vpt_30"]]
    r = r.merge(feat, on="date", how="left")
    vhi = r["vpt_30"].quantile(2/3)
    r.to_csv(OUT_DIR / "orb_wr_pnl.csv", index=False)
    years = sorted(r["year"].unique())

    def report(sub, title):
        print(f"\n################ {title}  (n={len(sub)}) ################")
        for name, *_ in CONFIGS:
            print(f"--- {name}")
            print(f"{'year':>6} {'n':>4} {'t/mo':>5} {'WRall':>6} {'WRdec':>6} {'RRreal':>7} {'EVnet':>7}")
            for y in years + ["ALL"]:
                g = sub if y == "ALL" else sub[sub.year == y]
                v = g[name].to_numpy()
                if len(v) == 0:
                    continue
                wins = (v > 0).sum()
                losses = (v < 0).sum()
                wr_all = wins / len(v) * 100
                wr_dec = wins / (wins + losses) * 100 if (wins + losses) else 0
                aw = v[v > 0].mean() if wins else 0
                al = -v[v < 0].mean() if losses else 1
                rr = aw / al if al else float("inf")
                mo = pd.to_datetime(g["date"]).dt.to_period("M").nunique()
                print(f"{str(y):>6} {len(v):>4} {len(v)/max(mo,1):>5.1f} {wr_all:>5.1f}% "
                      f"{wr_dec:>5.1f}% {rr:>7.2f} {v.mean()-2:>7.1f}")

    up = r[r.up == 1]
    report(up[up.vpt_30 <= vhi], "UP + vpt not-HIGH (robust subset)")

    # ---- CatBoost precision frontier at >=4/mo on 60/60 (RR 1) ----
    print("\n################ CatBoost WR ceiling @ >=4 trades/mo, bracket 60/60 (RR 1) ################")
    fe = pd.read_csv(OUT_DIR / "orb_features_labels_1s.csv")
    fe["year"] = pd.to_datetime(fe["date"]).dt.year
    fcols = [c for c in fe.columns if c not in ("date", "y", "year")]
    print(f"{'testY':>6} {'sel':>4} {'t/mo':>5} {'WR%':>6}")
    for ty in [y for y in years if y > min(years)]:
        tr, te = fe[fe.year < ty], fe[fe.year == ty]
        if len(tr) < 100 or te.empty:
            continue
        m = CatBoostClassifier(iterations=400, depth=4, learning_rate=0.03,
                               l2_leaf_reg=6, loss_function="Logloss", verbose=False, random_seed=7)
        m.fit(tr[fcols], tr["y"])
        p = m.predict_proba(te[fcols])[:, 1]
        mo = te["date"].str.slice(0, 7).nunique()
        k = max(int(4 * mo), 1)                    # exactly the 4/mo floor
        idx = np.argsort(-p)[:k]
        wr = te["y"].to_numpy()[idx].mean() * 100
        print(f"{ty:>6} {k:>4} {k/mo:>5.1f} {wr:>5.1f}%")
    print("\n(if WR stays <80% even here, 80% is infeasible on price/volume data)")


if __name__ == "__main__":
    main()
