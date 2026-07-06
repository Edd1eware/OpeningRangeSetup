# -*- coding: utf-8 -*-
"""Can a CatBoost filter push raw ORB (WR~50% @ 1:1) to WR>=80% OOS?

One pass per date: OR (09:30 min) -> first breakout -> CAUSAL pre-breakout 1s
features -> bracket outcome (TP/SL touched first). Then an expanding
walk-forward: train on all prior years, pick the probability threshold on TRAIN
that yields >=80% train precision, apply UNCHANGED to the held-out year, and
report WR / trades-per-month / PF on that out-of-sample year.

Target bracket 60/60 (R:R 1.0) because the goal fixes R:R>=1 and asks WR>=80%.
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
WINDOWS = [5, 10, 30, 60, 120]
TP_T, SL_T = 60, 60
COMMISSION_TICKS = 2.0
TARGET_TRAIN_PREC = 0.80

DBN_ROOT = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
    r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_2"
)
OUT_DIR = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")


def load_session(date: str) -> pd.DataFrame | None:
    hits = glob.glob(str(DBN_ROOT / date / "ohlcv-1s-full" / "*.dbn.zst"))
    if not hits:
        return None
    return db.DBNStore.from_file(hits[0]).to_df()[["open", "high", "low", "close", "volume"]].sort_index()


def window_features(win: pd.DataFrame, sign: int, w: int) -> dict:
    if win.empty:
        return {f"{k}_{w}": 0.0 for k in
                ("vol", "rng", "net", "dir", "vpt", "liq", "amh",
                 "vts", "vvs", "rvol", "m1v", "m1r")}
    vol = float(win["volume"].sum())
    rng = max((float(win["high"].max()) - float(win["low"].min())) / TICK, 1.0)
    net = (float(win["close"].iloc[-1]) - float(win["open"].iloc[0])) / TICK
    vd = max(vol, 1.0)
    ret = np.log(win["close"].to_numpy())
    ret = np.diff(ret) if len(ret) > 1 else np.array([0.0])
    return {
        f"vol_{w}": vol, f"rng_{w}": rng, f"net_{w}": net, f"dir_{w}": net * sign,
        f"vpt_{w}": vol / rng, f"liq_{w}": abs(net) / vd * 1000, f"amh_{w}": abs(net) / vd,
        f"vts_{w}": rng / w, f"vvs_{w}": vol / w, f"rvol_{w}": float(np.std(ret)),
        f"m1v_{w}": float(win["volume"].max()),
        f"m1r_{w}": float((win["high"] - win["low"]).max()) / TICK,
    }


def bracket_outcome(fwd: pd.DataFrame, entry: float, sign: int) -> int:
    if sign == 1:
        tp, sl = entry + TP_T * TICK, entry - SL_T * TICK
        for h, l in zip(fwd["high"].to_numpy(), fwd["low"].to_numpy()):
            if l <= sl:
                return 0
            if h >= tp:
                return 1
    else:
        tp, sl = entry - TP_T * TICK, entry + SL_T * TICK
        for h, l in zip(fwd["high"].to_numpy(), fwd["low"].to_numpy()):
            if h >= sl:
                return 0
            if l <= tp:
                return 1
    return -1  # timeout


def build_event(date: str, prev_hlc):
    df = load_session(date)
    if df is None or df.empty:
        return None, prev_hlc
    day = df.index[0].strftime("%Y-%m-%d")
    orw = df.between_time(OR_START, OR_END, inclusive="left")
    if orw.empty:
        return None, (float(df["high"].max()), float(df["low"].min()), float(df["close"].iloc[-1]))
    or_high, or_low = float(orw["high"].max()), float(orw["low"].min())
    post = df.loc[df.index >= pd.Timestamp(f"{day} {SCAN_START}", tz="UTC")]
    cur_hlc = (float(df["high"].max()), float(df["low"].min()), float(df["close"].iloc[-1]))
    if post.empty:
        return None, cur_hlc
    up = post.index[post["high"] > or_high]
    dn = post.index[post["low"] < or_low]
    t_up = up[0] if len(up) else None
    t_dn = dn[0] if len(dn) else None
    if t_up is None and t_dn is None:
        return None, cur_hlc
    if t_dn is None or (t_up is not None and t_up <= t_dn):
        direction, bt, entry, sign = "UP", t_up, or_high, 1
    else:
        direction, bt, entry, sign = "DOWN", t_dn, or_low, -1

    causal = post.loc[post.index < bt]
    out = bracket_outcome(post.loc[post.index >= bt], entry, sign)
    if out == -1:
        return None, cur_hlc  # no timeouts observed, but guard

    feats = {"date": date, "y": out, "direction_up": float(sign == 1)}
    for w in WINDOWS:
        win = causal.loc[causal.index >= bt - pd.Timedelta(seconds=w)]
        feats.update(window_features(win, sign, w))
    feats["or_range_ticks"] = (or_high - or_low) / TICK
    feats["breakout_delay_s"] = float((bt - pd.Timestamp(f"{day} {SCAN_START}", tz="UTC")).total_seconds())

    sofar = post.loc[post.index < bt]
    pv, vv = (sofar["close"] * sofar["volume"]).sum(), sofar["volume"].sum()
    vwap = pv / vv if vv > 0 else entry
    feats["dist_vwap"] = (entry - vwap) / TICK * sign
    if prev_hlc:
        ph, pl, pc = prev_hlc
        feats["dist_pdh"] = (entry - ph) / TICK
        feats["dist_pdl"] = (entry - pl) / TICK
        feats["dist_pdc"] = (entry - pc) / TICK
    for step, pts in (("25", 25.0), ("50", 50.0), ("100", 100.0)):
        feats[f"round_{step}"] = abs(entry - round(entry / pts) * pts) / TICK
    return feats, cur_hlc


def main() -> None:
    dates = sorted(p.name for p in DBN_ROOT.iterdir() if p.is_dir())
    rows, prev = [], None
    for d in track(dates, label="ORB+feat build"):
        try:
            r, prev = build_event(d, prev)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {d}: {exc}")
            r = None
        if r:
            rows.append(r)

    df = pd.DataFrame(rows)
    df["year"] = pd.to_datetime(df["date"]).dt.year
    df.to_csv(OUT_DIR / "orb_features_labels_1s.csv", index=False)
    feat_cols = [c for c in df.columns if c not in ("date", "y", "year")]
    print(f"\nEvents: {len(df)} | features: {len(feat_cols)} | base WR: {df.y.mean():.3f}\n")

    be = SL_T / (TP_T + SL_T)

    def stats(ys, n, mo):
        wins, losses = int(ys.sum()), int((ys == 0).sum())
        wr = wins / n * 100 if n else 0.0
        pf = (wins * TP_T) / (losses * SL_T) if losses else float("inf")
        ev = (wins * TP_T - losses * SL_T) / n - COMMISSION_TICKS if n else 0.0
        return wr, pf, ev, n / mo

    print("A) DEPLOYABLE: threshold from inner-validation (last 20% of train), applied to test")
    print(f"{'testY':>6} {'nte':>5} {'thr':>5} {'sel':>5} {'t/mo':>5} {'WR%':>6} {'PF':>6} {'EVnet':>7}")
    models = {}
    for ty in [y for y in sorted(df.year.unique()) if y > df.year.min()]:
        tr = df[df.year < ty].reset_index(drop=True)
        te = df[df.year == ty]
        if len(tr) < 100 or te.empty:
            continue
        cut = int(len(tr) * 0.8)
        fit, val = tr.iloc[:cut], tr.iloc[cut:]
        model = CatBoostClassifier(iterations=400, depth=4, learning_rate=0.03,
                                   l2_leaf_reg=6, loss_function="Logloss",
                                   verbose=False, random_seed=7)
        model.fit(fit[feat_cols], fit["y"])
        p_val = model.predict_proba(val[feat_cols])[:, 1]
        thr = None
        for t in np.round(np.arange(0.50, 0.91, 0.01), 2):
            s = p_val >= t
            if s.sum() >= 15 and val["y"].to_numpy()[s].mean() >= TARGET_TRAIN_PREC:
                thr = t
                break
        if thr is None:
            thr = 0.90
        # refit on full train, predict test
        full = CatBoostClassifier(iterations=400, depth=4, learning_rate=0.03,
                                  l2_leaf_reg=6, loss_function="Logloss",
                                  verbose=False, random_seed=7)
        full.fit(tr[feat_cols], tr["y"])
        models[ty] = (full, te)
        p_te = full.predict_proba(te[feat_cols])[:, 1]
        s = p_te >= thr
        mo = te["date"].str.slice(0, 7).nunique()
        if s.sum() == 0:
            print(f"{ty:>6} {len(te):>5} {thr:>5.2f} {0:>5} {'0':>5} {'-':>6} {'-':>6} {'-':>7}")
            continue
        wr, pf, ev, tmo = stats(te["y"].to_numpy()[s], int(s.sum()), mo)
        print(f"{ty:>6} {len(te):>5} {thr:>5.2f} {int(s.sum()):>5} {tmo:>5.1f} {wr:>5.1f}% {pf:>6.2f} {ev:>7.1f}")

    print("\nB) CEILING: best-possible WR if we could keep only the top-K% most confident test events")
    print(f"{'testY':>6} {'topK':>6} {'sel':>5} {'t/mo':>5} {'WR%':>6} {'PF':>6}")
    for ty, (full, te) in models.items():
        p_te = full.predict_proba(te[feat_cols])[:, 1]
        order = np.argsort(-p_te)
        y = te["y"].to_numpy()
        mo = te["date"].str.slice(0, 7).nunique()
        for frac in (0.30, 0.15, 0.05):
            k = max(int(len(te) * frac), 1)
            idx = order[:k]
            wr, pf, ev, tmo = stats(y[idx], k, mo)
            print(f"{ty:>6} {int(frac*100):>5}% {k:>5} {tmo:>5.1f} {wr:>5.1f}% {pf:>6.2f}")
    print(f"\nbreakeven WR @ {TP_T}/{SL_T} = {be*100:.1f}% | GOAL: WR>=80%, RR>=1, trades/mo>=4")


if __name__ == "__main__":
    main()
