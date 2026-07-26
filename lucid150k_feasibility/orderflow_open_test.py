"""
Does signed order flow at the open carry directional information that price
alone does not?

Motivation: the throughput census and the drift census both returned gross EV
of essentially zero across the entire OHLCV surface. NQ at 1-second resolution
is a martingale, so no timing rule built on bars can fund the evaluation. The
only untested information source with real coverage in this project is the
signed tape recorded for the opening window (684 sessions, 2022-04 to 2026-07,
roughly 09:29 to 09:40 NY).

Design, fixed before looking at any outcome:
  features  cumulative delta, delta/volume ratio, trade count, tape price move,
            all measured strictly inside 09:30:00 - 09:33:00
  entry     09:33:00, at the 1-second close
  direction CONT = sign of delta ratio, FADE = against it
  bracket   stop S ticks, target S * RR, 4 ticks of cost, stop wins intrabar ties
  eras      DEV 2022-04..2023-12 reported first, 2024 and 2025-26 reported
            separately so era instability is visible rather than averaged away

The question is not "is there a profitable rule" but "is the delta signal
monotone in outcome". A signal with no monotonicity across its own quantiles is
noise no matter how good the best bucket looks.
"""

import glob
import json
import os
import time

import numpy as np
import pandas as pd

from progress import track

TAPE_DIR = r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\book_recordings"
CACHE = "nq_1s_cache.npz"
COST_TICKS = 4
FEAT_END_SEC = 180          # 09:33:00, seconds from 09:30
ENTRY_SEC = 180


def build_features():
    files = sorted(glob.glob(os.path.join(TAPE_DIR, "tape_*_NY.csv")))
    recs = []
    for f in track(files, label="tape features"):
        day = os.path.basename(f)[5:15]
        try:
            d = pd.read_csv(f, on_bad_lines="skip")
        except Exception:
            continue
        if d.empty or "direction" not in d.columns:
            continue
        t = d["time_ny"].astype(str)
        hh = pd.to_numeric(t.str[0:2], errors="coerce")
        mm = pd.to_numeric(t.str[3:5], errors="coerce")
        ss = pd.to_numeric(t.str[6:8], errors="coerce")
        sec = hh * 3600 + mm * 60 + ss - (9 * 3600 + 30 * 60)
        ok = sec.notna() & (sec >= 0) & (sec < FEAT_END_SEC)
        w = d[ok.values]
        if len(w) < 200:
            continue
        # require the tape to actually reach the end of the feature window
        if float(sec[ok.values].max()) < FEAT_END_SEC - 20:
            continue
        vol = pd.to_numeric(w["volume"], errors="coerce").fillna(0).to_numpy()
        px = pd.to_numeric(w["price"], errors="coerce").to_numpy()
        buy = (w["direction"].astype(str).str.startswith("B")).to_numpy()
        signed = np.where(buy, vol, -vol)
        tot = vol.sum()
        if tot <= 0:
            continue
        cum = signed.cumsum()
        recs.append(dict(
            day=day,
            delta=float(signed.sum()),
            volume=float(tot),
            delta_ratio=float(signed.sum() / tot),
            n_trades=int(len(w)),
            tape_move=float(px[-1] - px[0]) if len(px) > 1 else 0.0,
            delta_max=float(cum.max()),
            delta_min=float(cum.min()),
            delta_end_vs_max=float(cum[-1] - cum.max()),
        ))
    return pd.DataFrame(recs)


def outcome_table(feat, s, rr):
    z = np.load(CACHE, allow_pickle=True)
    days = z["days"].astype(str)
    offsets = z["offsets"]
    close, high, low = z["close"], z["high"], z["low"]
    pos = {d: i for i, d in enumerate(days)}
    tgt = int(round(s * rr))

    out = []
    for r in feat.itertuples():
        i = pos.get(r.day)
        if i is None:
            continue
        a, b = offsets[i], offsets[i + 1]
        c_, h_, l_ = close[a:b], high[a:b], low[a:b]
        if len(c_) <= ENTRY_SEC + 60:
            continue
        e = ENTRY_SEC
        entry = c_[e]
        # long outcome; short is derived by symmetry below
        sl_hit = l_[e + 1:] <= entry - s
        tp_hit = h_[e + 1:] >= entry + tgt
        j_sl = int(np.argmax(sl_hit)) if sl_hit.any() else 10**9
        j_tp = int(np.argmax(tp_hit)) if tp_hit.any() else 10**9
        if j_sl == 10**9 and j_tp == 10**9:
            long_pnl = int(c_[-1] - entry) - COST_TICKS
        else:
            long_pnl = (-s - COST_TICKS) if j_sl <= j_tp else (tgt - COST_TICKS)

        sl_hit = h_[e + 1:] >= entry + s
        tp_hit = l_[e + 1:] <= entry - tgt
        j_sl = int(np.argmax(sl_hit)) if sl_hit.any() else 10**9
        j_tp = int(np.argmax(tp_hit)) if tp_hit.any() else 10**9
        if j_sl == 10**9 and j_tp == 10**9:
            short_pnl = int(entry - c_[-1]) - COST_TICKS
        else:
            short_pnl = (-s - COST_TICKS) if j_sl <= j_tp else (tgt - COST_TICKS)

        out.append(dict(day=r.day, delta_ratio=r.delta_ratio, delta=r.delta,
                        volume=r.volume, tape_move=r.tape_move,
                        long_pnl=long_pnl, short_pnl=short_pnl))
    return pd.DataFrame(out)


def era(day):
    if day <= "2023-12-31":
        return "DEV 22-23"
    if day <= "2024-12-31":
        return "2024"
    return "2025-26"


def report(df, s, rr):
    df = df.copy()
    df["era"] = df["day"].map(era)
    df["cont"] = np.where(df["delta_ratio"] > 0, df["long_pnl"], df["short_pnl"])
    df["fade"] = np.where(df["delta_ratio"] > 0, df["short_pnl"], df["long_pnl"])

    print(f"\n===== bracket stop {s} / target {int(s*rr)} (RR {rr}) =====")
    print(f"{'era':>10} {'n':>4} | {'CONT EV':>8} {'WR':>6} {'PF':>6} "
          f"| {'FADE EV':>8} {'WR':>6} {'PF':>6}")
    for e in ["DEV 22-23", "2024", "2025-26"]:
        sub = df[df["era"] == e]
        if len(sub) < 20:
            continue
        line = f"{e:>10} {len(sub):>4} |"
        for col in ("cont", "fade"):
            a = sub[col].to_numpy(float)
            gl = -a[a < 0].sum()
            pf = (a[a > 0].sum() / gl) if gl > 0 else float("nan")
            line += f" {a.mean():>8.2f} {(a > 0).mean():>6.3f} {pf:>6.3f} |"
        print(line)

    # monotonicity of the signal across its own quintiles, DEV only
    dev = df[df["era"] == "DEV 22-23"].copy()
    if len(dev) >= 50:
        dev["q"] = pd.qcut(dev["delta_ratio"], 5, labels=False, duplicates="drop")
        print(f"\n  DEV monotonicity by delta_ratio quintile (long side):")
        print(f"  {'q':>2} {'n':>4} {'dr_mid':>8} {'LONG EV':>8} {'WR':>6}")
        for q, g in dev.groupby("q"):
            a = g["long_pnl"].to_numpy(float)
            print(f"  {int(q):>2} {len(g):>4} {g['delta_ratio'].median():>8.3f} "
                  f"{a.mean():>8.2f} {(a > 0).mean():>6.3f}")


def main():
    t0 = time.time()
    if os.path.exists("OF_FEATURES.csv"):
        feat = pd.read_csv("OF_FEATURES.csv")
        print(f"features loaded: {len(feat)} sessions")
    else:
        feat = build_features()
        feat.to_csv("OF_FEATURES.csv", index=False)
        print(f"\nfeatures built: {len(feat)} sessions "
              f"[{feat.day.min()} .. {feat.day.max()}]  [{time.time()-t0:.1f}s]")

    for s, rr in [(40, 1.0), (40, 2.0), (60, 1.0), (60, 2.0), (30, 2.0)]:
        df = outcome_table(feat, s, rr)
        if s == 40 and rr == 1.0:
            print(f"joined sessions with 1s outcomes: {len(df)}")
            df.to_csv("OF_JOINED_40_1.csv", index=False)
        report(df, s, rr)

    print(f"\ntotal elapsed {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
