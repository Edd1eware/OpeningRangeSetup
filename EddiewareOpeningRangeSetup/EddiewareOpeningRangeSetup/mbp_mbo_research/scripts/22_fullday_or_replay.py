"""Replay the opening-range detector across its FULL-DAY eligibility window.

This is the second use of already-owned data that Codex named: the 1s bars cover
the whole RTH session for all 150 sessions, while every study so far has been
confined to 09:30-10:30. The question is NOT "which hour is best" -- that would
be a search, and the project has enough of those. The question is whether
restricting the entry window to 09:31-09:39 DISCARDS opportunities or truncates
the strategy's economics.

What is held fixed (the trader's spec, unchanged)
-------------------------------------------------
* Opening range = the single M1 candle 09:30-09:31 ET. It contributes only its
  high and low. No entry is analysed inside it.
* Break by BODY: an M1 whose CLOSE clears the OR high (long) or low (short).
  A wick does not count.
* VWAP anchored at 09:30, built from Close as the trader's ATAS is configured,
  and required to be on the side of the trade.

What is deliberately changed (the thing under test)
---------------------------------------------------
* The entry window is extended from 09:31-09:39 to the whole RTH session.

A fresh-cross rule is needed once the window is the whole day, because price
can sit beyond the level for an hour and that is one opportunity, not sixty.
A signal fires on an M1 that closes beyond the level when the PREVIOUS M1 close
was not beyond that same level. One position at a time; conflicting signals are
skipped and counted.

What this CANNOT establish, stated up front
-------------------------------------------
* The aggressor / footprint condition cannot be applied outside 09:25-10:30,
  because the `trades` tape does not exist there. The imbalance stop and the
  "imbalance not touched" rule are therefore ABSENT from this replay. That is a
  real gap, not a silent simplification: this measures the price/VWAP skeleton
  of the setup over the full day, not the complete rule.
* 1s OHLC cannot order two barriers inside one second. Every such case is
  reported as a BOUND (optimistic = target first, pessimistic = stop first),
  never as an invented sequence. Codex measured the truly-unresolvable share as
  26.2% at an 8-tick bracket and 0% from 16 ticks up, so the bounds matter at
  tight brackets and vanish at wide ones.
* It is not a validated strategy and not a search for the best hour. Hourly
  numbers are printed as description only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATA, NY  # noqa: E402
from progress import track  # noqa: E402

BARS = DATA / "bars" / "bars_1s_2026.parquet"
OUT = DATA / "reports" / "fullday_or_replay.csv"
OUT_HOUR = DATA / "reports" / "fullday_or_by_hour.csv"

TICK = 0.25
BRACKETS = (8, 12, 20, 40, 60)     # symmetric, in ticks
COSTS = (1.8, 2.8, 3.8)
HORIZON_MIN = 30
ENTRY_FROM_MIN = 9 * 60 + 31       # 09:31 ET, first eligible M1 close
ENTRY_TO_MIN = 15 * 60 + 29        # 15:29, so a 30 min horizon fits before 15:59
RTH_END_MIN = 15 * 60 + 59
N_BOOT = 20_000
SEED = 20261012


def session_frame(g: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Build the M1 frame and keep the 1s frame, both indexed by ET minute."""
    g = g.sort_values("ts_ny")
    ny = g["ts_ny"]
    mins = (ny.dt.hour * 60 + ny.dt.minute).to_numpy()
    rth = (mins >= 9 * 60 + 30) & (mins <= RTH_END_MIN)
    s = g[rth].copy()
    if len(s) < 600:
        return None
    s["min_of_day"] = mins[rth]

    # VWAP anchored at 09:30 from Close, as the trader's ATAS is configured
    v = s["volume"].to_numpy().astype("float64")
    c = s["close"].to_numpy()
    cv = np.cumsum(c * v)
    cvol = np.cumsum(v)
    s["vwap"] = np.where(cvol > 0, cv / np.maximum(cvol, 1e-9), c)

    m1 = s.groupby("min_of_day").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"),
        vwap=("vwap", "last"),
    ).reset_index()
    return s, m1


def walk_bars(s1: pd.DataFrame, i0: int, d: int, k: int,
              end_min: int) -> tuple[float, float, str]:
    """Walk 1s bars from index i0. Returns (pessimistic, optimistic, kind) ticks.

    * A bar whose OPEN is already beyond a barrier fills at the OPEN, so gaps
      are paid rather than assumed away.
    * If a single bar contains BOTH barriers, the order is unknowable from OHLC:
      pessimistic books the stop, optimistic books the target. Both are carried
      to the report; neither is presented as the truth.
    """
    o = s1["open"].to_numpy()
    h = s1["high"].to_numpy()
    l = s1["low"].to_numpy()
    cl = s1["close"].to_numpy()
    mn = s1["min_of_day"].to_numpy()

    entry = o[i0]
    up = entry + k * TICK
    dn = entry - k * TICK

    n = len(o)
    for j in range(i0, n):
        if mn[j] > end_min:
            break
        oj = o[j]
        # gap through a barrier at the open: that is the fill
        if d > 0:
            if oj <= dn:
                return d * (oj - entry) / TICK, d * (oj - entry) / TICK, "gap_sl"
            if oj >= up:
                return d * (oj - entry) / TICK, d * (oj - entry) / TICK, "gap_tp"
            hit_tp = h[j] >= up
            hit_sl = l[j] <= dn
        else:
            if oj >= up:  # for a short, `up` is the adverse side
                return d * (oj - entry) / TICK, d * (oj - entry) / TICK, "gap_sl"
            if oj <= dn:
                return d * (oj - entry) / TICK, d * (oj - entry) / TICK, "gap_tp"
            hit_tp = l[j] <= dn
            hit_sl = h[j] >= up

        if hit_tp and hit_sl:
            return -float(k), float(k), "ambiguous"
        if hit_tp:
            return float(k), float(k), "tp"
        if hit_sl:
            return -float(k), -float(k), "sl"

    j = min(n - 1, max(i0, int(np.searchsorted(mn, end_min, side="right")) - 1))
    mk = d * (cl[j] - entry) / TICK
    return mk, mk, "timeout"


def main() -> None:
    print("loading 1s bars (full day)...", flush=True)
    b = pd.read_parquet(BARS, columns=["ts_ny", "session", "open", "high",
                                       "low", "close", "volume"])
    print(f"  {len(b):,} bars, {b['session'].nunique()} sessions", flush=True)

    rows = []
    groups = list(b.groupby("session", sort=True))

    for sess, g in track(groups, label="full-day OR replay"):
        built = session_frame(g)
        if built is None:
            continue
        s1, m1 = built

        orb = m1[m1["min_of_day"] == 9 * 60 + 30]
        if orb.empty:
            continue
        or_hi = float(orb["high"].iloc[0])
        or_lo = float(orb["low"].iloc[0])

        cand = m1[(m1["min_of_day"] >= ENTRY_FROM_MIN)
                  & (m1["min_of_day"] <= ENTRY_TO_MIN)].reset_index(drop=True)
        if cand.empty:
            continue

        cl = cand["close"].to_numpy()
        vw = cand["vwap"].to_numpy()
        mn = cand["min_of_day"].to_numpy()

        above = cl > or_hi
        below = cl < or_lo
        prev_above = np.concatenate([[False], above[:-1]])
        prev_below = np.concatenate([[False], below[:-1]])
        # fresh cross only: sitting beyond the level is one opportunity, not sixty
        fresh_long = above & ~prev_above
        fresh_short = below & ~prev_below

        # VWAP must be on the side of the trade
        ok_long = fresh_long & (cl > vw)
        ok_short = fresh_short & (cl < vw)

        sig_idx = np.flatnonzero(ok_long | ok_short)
        if len(sig_idx) == 0:
            continue
        sides = np.where(ok_long[sig_idx], 1, -1)

        s1_min = s1["min_of_day"].to_numpy()
        for k in BRACKETS:
            busy_until_min = -1
            for si, d in zip(sig_idx, sides):
                m = int(mn[si])
                if m <= busy_until_min:
                    continue
                # entry at the first 1s bar of the NEXT minute
                i0 = int(np.searchsorted(s1_min, m + 1, side="left"))
                if i0 >= len(s1_min):
                    continue
                end_min = min(m + 1 + HORIZON_MIN, RTH_END_MIN)
                pes, opt, kind = walk_bars(s1, i0, int(d), k, end_min)
                busy_until_min = end_min if kind == "timeout" else m + 1
                rows.append(dict(session=sess, bracket=k, minute=m, side=int(d),
                                 pes=pes, opt=opt, kind=kind,
                                 hour=m // 60,
                                 window="0931_0939"
                                 if m <= 9 * 60 + 39 else "rest_of_day"))

    res = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT, index=False)

    rng = np.random.default_rng(SEED)

    def boot(vals: np.ndarray, keys: np.ndarray) -> tuple[float, float]:
        u = np.unique(keys)
        sums = np.array([vals[keys == s].sum() for s in u])
        cnts = np.array([float((keys == s).sum()) for s in u])
        idx = rng.integers(0, len(u), size=(N_BOOT, len(u)))
        sm = sums[idx].sum(axis=1)
        cn = cnts[idx].sum(axis=1)
        mm = sm / np.maximum(cn, 1)
        return float(np.quantile(mm, 0.025)), float(np.quantile(mm, 0.975))

    print("", flush=True)
    print("=" * 104, flush=True)
    print("OPORTUNIDADES: la ventana 09:31-09:39 vs el resto del dia", flush=True)
    print("(el filtro de footprint NO se aplica: el tape no existe fuera de "
          "09:25-10:30)", flush=True)
    print("", flush=True)
    print("| bracket | ventana | n | trades/sesion | WR pes | EV bruto pes | "
          "EV bruto opt | EV neto pes (1.8) | IC95 pes | ambiguo % |", flush=True)
    print("|---|---|---|---|---|---|---|---|---|---|", flush=True)
    summary = []
    for k in BRACKETS:
        for w in ("0931_0939", "rest_of_day"):
            t = res[(res["bracket"] == k) & (res["window"] == w)]
            if len(t) < 30:
                continue
            pes = t["pes"].to_numpy()
            opt = t["opt"].to_numpy()
            lo, hi = boot(pes - 1.8, t["session"].to_numpy())
            n_sess = t["session"].nunique()
            print(f"| {k} | {w} | {len(t):,} | {len(t) / 150:.2f} | "
                  f"{(pes > 0).mean():.1%} | {pes.mean():+.2f} | "
                  f"{opt.mean():+.2f} | **{pes.mean() - 1.8:+.2f}** | "
                  f"[{lo:+.2f}, {hi:+.2f}] | "
                  f"{(t['kind'] == 'ambiguous').mean():.1%} |", flush=True)
            summary.append(dict(bracket=k, window=w, n=len(t), n_sessions=n_sess,
                                trades_per_session=len(t) / 150,
                                wr_pes=float((pes > 0).mean()),
                                ev_gross_pes=float(pes.mean()),
                                ev_gross_opt=float(opt.mean()),
                                ev_net_pes=float(pes.mean() - 1.8),
                                lo95=lo, hi95=hi,
                                pct_ambiguous=float((t["kind"] == "ambiguous").mean())))
    pd.DataFrame(summary).to_csv(OUT_HOUR, index=False)

    print("", flush=True)
    print("DESCRIPTIVO por hora (bracket 20). NO es una busqueda de la mejor hora:",
          flush=True)
    print("", flush=True)
    t20 = res[res["bracket"] == 20]
    print("| hora ET | n | WR pes | EV bruto pes | EV neto pes |", flush=True)
    print("|---|---|---|---|---|", flush=True)
    for hh, g in t20.groupby("hour"):
        if len(g) < 20:
            continue
        p = g["pes"].to_numpy()
        print(f"| {hh:02d}:00 | {len(g):,} | {(p > 0).mean():.1%} | "
              f"{p.mean():+.2f} | {p.mean() - 1.8:+.2f} |", flush=True)

    print("", flush=True)
    print("LECTURA DE OPORTUNIDAD (lo que esta medicion existe para contestar):",
          flush=True)
    for k in (20,):
        a = res[(res["bracket"] == k) & (res["window"] == "0931_0939")]
        r = res[(res["bracket"] == k) & (res["window"] == "rest_of_day")]
        print(f"  bracket {k}: la ventana original da {len(a):,} trades "
              f"({len(a) / 150:.2f}/sesion); el resto del dia da {len(r):,} "
              f"({len(r) / 150:.2f}/sesion)", flush=True)
        if len(a) and len(r):
            print(f"    restringir a 09:31-09:39 descarta "
                  f"{len(r) / (len(a) + len(r)):.0%} de las oportunidades "
                  f"del esqueleto precio/VWAP", flush=True)
    print("", flush=True)
    print(f"wrote {OUT}", flush=True)
    print(f"wrote {OUT_HOUR}", flush=True)


if __name__ == "__main__":
    main()
