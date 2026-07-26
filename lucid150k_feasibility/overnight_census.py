"""
Overnight session census on NQ 1-minute bars.

Every test in this project so far lives inside the RTH session, and the RTH
surface came back flat: gross EV of essentially zero across triggers, times of
day and opening order flow. The Globex session has never been tested as
something to trade, only as a feature for a single 09:35 decision.

It is the one remaining surface that is both large and already paid for, and
unlike adding correlated instruments it can add genuine independent throughput
because it is a different clock and a different liquidity regime.

Two passes, same machinery as the RTH censuses:
    drift    enter LONG or SHORT at a fixed offset into the overnight session
    trigger  momentum / fade on a lookback of W minutes past K ticks

Session definition: 18:00 NY through 09:29 NY the following day. Sessions that
contain a continuous-contract roll are dropped, since a roll gap is not a
tradeable move. Cost stays at 4 ticks for comparability with the RTH work, which
is if anything generous overnight, so any positive result here should be
re-checked at a wider cost before being believed.
"""

import itertools
import json
import time

import numpy as np
import pandas as pd
import databento as db

from progress import track

SRC = (r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
       r"\lucid150k_sniper_v14_overnight\nq_es_1m_20220424_20260630.dbn.zst")
TICK = 0.25
COST_TICKS = 4
CACHE = "nq_overnight_1m.parquet"

ROLL_DATES = ["2022-06-19", "2022-09-18", "2022-12-18", "2023-03-19", "2023-06-18",
              "2023-09-17", "2023-12-17", "2024-03-17", "2024-06-23", "2024-09-22",
              "2024-12-22", "2025-03-23", "2025-06-22", "2025-09-21", "2025-12-21",
              "2026-03-22", "2026-06-19"]

DEV_END = "2023-12-31"
S_GRID = [20, 30, 40, 60]
RR_GRID = [1.0, 2.0]
W_GRID = [5, 15, 30, 60]        # minutes
K_GRID = [10, 20, 30, 40]       # ticks


def load():
    if pd.io.common.file_exists(CACHE):
        return pd.read_parquet(CACHE)
    t0 = time.time()
    df = db.DBNStore.from_file(SRC).to_df()
    df = df[df["symbol"] == "NQ.c.0"].copy()
    df.index = df.index.tz_convert("America/New_York")
    df = df[["open", "high", "low", "close", "volume"]]
    for c in ("open", "high", "low", "close"):
        df[c] = np.rint(df[c] / TICK).astype(np.int64)
    # the overnight session that ends on day D starts at 18:00 on D-1
    ny = df.index
    session = np.where(ny.hour >= 18, (ny + pd.Timedelta(days=1)).date, ny.date)
    df["session"] = pd.to_datetime(session).astype(str)
    mins = ny.hour * 60 + ny.minute
    df["mins_in"] = np.where(mins >= 18 * 60, mins - 18 * 60, mins + 6 * 60)
    df = df[(mins >= 18 * 60) | (mins < 9 * 60 + 30)]
    df.to_parquet(CACHE)
    print(f"loaded {len(df):,} overnight bars [{time.time()-t0:.1f}s]")
    return df


def bracket(close, high, low, i, direction, s, tgt):
    entry = close[i]
    if direction > 0:
        sl, tp = low[i + 1:] <= entry - s, high[i + 1:] >= entry + tgt
    else:
        sl, tp = high[i + 1:] >= entry + s, low[i + 1:] <= entry - tgt
    j_sl = int(np.argmax(sl)) if sl.any() else 10**9
    j_tp = int(np.argmax(tp)) if tp.any() else 10**9
    if j_sl == 10**9 and j_tp == 10**9:
        return int(direction * (close[-1] - entry)) - COST_TICKS, 10**9
    if j_sl <= j_tp:
        return -s - COST_TICKS, j_sl
    return tgt - COST_TICKS, j_tp


def era(day):
    return "DEV 22-23" if day <= DEV_END else ("2024" if day <= "2024-12-31" else "2025-26")


def summarize(rows, label):
    df = pd.DataFrame(rows)
    if df.empty:
        print(f"{label}: no trades")
        return df
    out = []
    for key, g in df.groupby(["cfg", "era"]):
        a = g["pnl"].to_numpy(float)
        gl = -a[a < 0].sum()
        out.append(dict(cfg=key[0], era=key[1], n=len(a), ev=a.mean(),
                        wr=(a > 0).mean(),
                        pf=(a[a > 0].sum() / gl) if gl > 0 else np.nan))
    return pd.DataFrame(out)


def main():
    t0 = time.time()
    df = load()
    sessions = []
    for day, g in df.groupby("session"):
        if day in ROLL_DATES or len(g) < 300:
            continue
        g = g.sort_index()
        sessions.append((day, g["close"].to_numpy(), g["high"].to_numpy(),
                         g["low"].to_numpy(), g["mins_in"].to_numpy()))
    print(f"overnight sessions: {len(sessions)} "
          f"[{sessions[0][0]} .. {sessions[-1][0]}]")

    # ---------------- pass 1: drift ----------------
    entry_mins = list(range(0, 15 * 60 + 1, 60))     # every hour of the session
    cells = list(itertools.product(entry_mins, (1, -1), S_GRID, RR_GRID))
    rows = []
    for off, d, s, rr in track(cells, label="overnight drift"):
        tgt = int(round(s * rr))
        cfg = f"m{off}_{'L' if d > 0 else 'S'}_{s}x{rr}"
        for day, c_, h_, l_, mi in sessions:
            k = int(np.searchsorted(mi, off))
            if k >= len(c_) - 30:
                continue
            pnl, _ = bracket(c_, h_, l_, k, d, s, tgt)
            rows.append(dict(cfg=cfg, era=era(day), pnl=pnl))
    drift = summarize(rows, "drift")

    dev = drift[drift["era"] == "DEV 22-23"].sort_values("ev", ascending=False)
    print(f"\n--- overnight drift, top 10 DEV cells with their later eras ---")
    print(f"{'cfg':>16} {'era':>10} {'n':>4} {'WR':>6} {'EV':>8} {'PF':>6}")
    for cfg in dev["cfg"].head(10):
        for e in ["DEV 22-23", "2024", "2025-26"]:
            r = drift[(drift["cfg"] == cfg) & (drift["era"] == e)]
            if r.empty:
                continue
            r = r.iloc[0]
            print(f"{cfg:>16} {e:>10} {r['n']:>4.0f} {r['wr']:>6.3f} "
                  f"{r['ev']:>8.2f} {r['pf']:>6.3f}")

    # ---------------- pass 2: triggers ----------------
    rows = []
    combos = list(itertools.product(W_GRID, K_GRID, S_GRID, RR_GRID, ("CONT", "FADE")))
    for w, k, s, rr, dname in track(combos, label="overnight triggers"):
        tgt = int(round(s * rr))
        cfg = f"W{w}_K{k}_{s}x{rr}_{dname}"
        for day, c_, h_, l_, mi in sessions:
            n = len(c_)
            if n <= w + 30:
                continue
            move = np.zeros(n, dtype=np.int64)
            move[w:] = c_[w:] - c_[:-w]
            i = w
            while i < n - 30:
                if abs(move[i]) < k:
                    i += 1
                    continue
                d = int(np.sign(move[i]))
                if dname == "FADE":
                    d = -d
                if d == 0:
                    i += 1
                    continue
                pnl, j = bracket(c_, h_, l_, i, d, s, tgt)
                rows.append(dict(cfg=cfg, era=era(day), pnl=pnl))
                i = n if j == 10**9 else i + j + 2
    trig = summarize(rows, "triggers")

    trig.to_csv("OVERNIGHT_TRIGGERS.csv", index=False)
    drift.to_csv("OVERNIGHT_DRIFT.csv", index=False)

    dev = trig[trig["era"] == "DEV 22-23"].sort_values("ev", ascending=False)
    print(f"\n--- overnight triggers: DEV positives = "
          f"{int((dev['ev'] > 0).sum())}/{len(dev)} ---")
    print(f"{'cfg':>22} {'era':>10} {'n':>6} {'WR':>6} {'EV':>8} {'PF':>6}")
    for cfg in dev["cfg"].head(8):
        for e in ["DEV 22-23", "2024", "2025-26"]:
            r = trig[(trig["cfg"] == cfg) & (trig["era"] == e)]
            if r.empty:
                continue
            r = r.iloc[0]
            print(f"{cfg:>22} {e:>10} {r['n']:>6.0f} {r['wr']:>6.3f} "
                  f"{r['ev']:>8.2f} {r['pf']:>6.3f}")

    print(f"\ntotal elapsed {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
