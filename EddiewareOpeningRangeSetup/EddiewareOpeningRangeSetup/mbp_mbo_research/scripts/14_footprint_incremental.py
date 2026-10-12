"""Does the footprint condition select BETTER directional opportunities?

PROTOCOL — designed by Codex, agreed by both, frozen before running
-------------------------------------------------------------------
Testing the whole rule at once (filter + structural stop + "keep waiting") makes
any positive result impossible to attribute. This isolates one question: does
the footprint carry incremental DIRECTIONAL information?

* One observation per session: the FIRST body break, same event for everybody,
  whether or not the footprint passes.
* A fixed 60/60-tick bracket over a 30-minute horizon, for BOTH directions on
  every event. This bracket is a diagnostic control, not a proposal, and it was
  never selected by its returns.
* For each event:      D = (PnL_follow - PnL_fade) / 2
  That is follow's advantage over the coin flip on that exact event, so the
  path's own generosity cancels out. A trending day inflates both sides equally.
* The statistic:  Delta = mean(D | passes) - mean(D | fails)
* Reported alongside: the pass rate, mean(D | passes) on its own, the net EV of
  the passing group, and a session-level bootstrap interval.

A positive Delta is NOT enough. If the passing group still has a negative
directional advantage, the filter is only less bad, not good. And directional
advantage alone is not profitability, so net EV is reported too.

NOTHING IS TUNED AFTER SEEING DELTA. Not the ratio, not the cell grouping, not
the R:R, not the horizon. The footprint parameters are the trader's own ATAS
settings, fixed before any of this: ratio 3, volume filter 70, grouping 5 ticks,
offset 1 tick, minimum difference 0.

LIMITS, STATED UP FRONT
* 2026 has already been inspected many times, so these results are exploratory,
  not confirmatory.
* This tests the FIRST break only. A null here does not rule out an effect that
  lives on later qualifying candles, which is a separate protocol.
* Footprint rows, trades and overlapping candles are NOT independent samples.
  The unit is the session, and the interval is bootstrapped over sessions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from config import DATA, ENTRY_FROM, ENTRY_TO, OR_OPEN
from progress import track

_spec = importlib.util.spec_from_file_location("l2", HERE / "05_l2_features.py")
L2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L2)

_spec2 = importlib.util.spec_from_file_location("fs", HERE / "12_full_spec.py")
sys.argv = ["x"]
FS = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(FS)

TICK = 0.25
BARS = DATA / "bars"
TRADES = DATA / "trades"
OUT = DATA / "reports"
BRACKET = 60.0        # diagnostic control, fixed in advance, 60/60 ticks
HORIZON_MIN = 30
COST = 1.8


def walk(path: pd.DataFrame, side: int, entry: float, sl: float, tp: float) -> float:
    """Ticks for one direction. Stop first on ties; gap-through fills at the open."""
    stop = entry - side * sl * TICK
    targ = entry + side * tp * TICK
    p = path[path.ts_utc <= path.ts_utc.iloc[0] + pd.Timedelta(minutes=HORIZON_MIN)]
    for b in p.itertuples(index=False):
        hit_sl = (b.low <= stop) if side > 0 else (b.high >= stop)
        hit_tp = (b.high >= targ) if side > 0 else (b.low <= targ)
        if hit_sl:
            gap = min(b.open, stop) if side > 0 else max(b.open, stop)
            return float(side * (gap - entry) / TICK)
        if hit_tp:
            return float(tp)
    last = p.iloc[-1]
    return float(side * (last.close - entry) / TICK)


def main() -> int:
    files = sorted(BARS.glob("bars_1s_*.parquet"))
    if not files:
        print(f"no hay barras en {BARS}")
        return 1
    bars = pd.concat((pd.read_parquet(f) for f in files),
                     ignore_index=True).sort_values("ts_utc")
    have = {p.name.split("_")[-1].replace(".dbn.zst", "")
            for p in TRADES.glob("NQ_trades_*.dbn.zst")}
    print(f"bracket diagnostico {BRACKET:.0f}/{BRACKET:.0f} ticks, "
          f"horizonte {HORIZON_MIN} min, coste {COST} ticks")
    print(f"footprint: ratio {L2.IMB_RATIO}, volfilter {L2.IMB_MIN_VOL}, "
          f"group {L2.IMB_GROUP}t, offset {L2.IMB_GROUP_OFF}t\n")

    rows = []
    for sess, day in track(list(bars.groupby("session")), label="primer break"):
        sess = str(sess)
        if sess not in have:
            continue
        day = day.reset_index(drop=True)
        m1 = FS.m1_and_vwap(day)
        t = m1.minute_ny.dt.time
        orb = m1[(t >= OR_OPEN) & (t < ENTRY_FROM)]
        win = m1[(t >= ENTRY_FROM) & (t <= ENTRY_TO)]
        if orb.empty or win.empty:
            continue
        or_hi, or_lo = float(orb.high.max()), float(orb.low.min())

        hit = None
        for r in win.itertuples(index=False):
            if r.close > or_hi:
                hit = (r, 1)
                break
            if r.close < or_lo:
                hit = (r, -1)
                break
        if hit is None:
            continue
        r, side = hit
        nxt = day[day.ts_ny >= r.minute_ny + pd.Timedelta(minutes=1)]
        if nxt.empty:
            continue
        entry = float(nxt.iloc[0].open)

        td = db.DBNStore.from_file(
            TRADES / f"NQ_trades_{sess}.dbn.zst").to_df(price_type="float",
                                                        tz="UTC").reset_index()
        td["size"] = td["size"].astype("int64")
        td["ny"] = td.ts_event.dt.tz_convert(day.ts_ny.dt.tz)
        ct = td[(td.ny >= r.minute_ny)
                & (td.ny < r.minute_ny + pd.Timedelta(minutes=1))]
        imb = FS.imbalance_rows(ct)
        want = "buy" if side > 0 else "sell"
        passes = (not imb.empty) and bool((imb.kind == want).any())

        pnl_follow = walk(nxt, side, entry, BRACKET, BRACKET)
        pnl_fade = walk(nxt, -side, entry, BRACKET, BRACKET)
        rows.append({"session": sess, "side": side,
                     "minute": int(r.minute_ny.minute),
                     "or_ticks": round((or_hi - or_lo) / TICK),
                     "passes": passes,
                     "follow": pnl_follow, "fade": pnl_fade,
                     "D": (pnl_follow - pnl_fade) / 2.0})

    d = pd.DataFrame(rows)
    if d.empty:
        print("sin eventos")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "footprint_incremental.csv", index=False)

    a, b = d[d.passes], d[~d.passes]
    delta = a.D.mean() - b.D.mean()
    rng = np.random.default_rng(11)
    boots = []
    for _ in range(5000):
        s = d.sample(len(d), replace=True, random_state=int(rng.integers(1 << 31)))
        ga, gb = s[s.passes], s[~s.passes]
        if len(ga) and len(gb):
            boots.append(ga.D.mean() - gb.D.mean())
    lo, hi = np.percentile(boots, [2.5, 97.5]) if boots else (np.nan, np.nan)

    pd.set_option("display.width", 200)
    print(f"\neventos: {len(d)}  |  pasan el footprint: {len(a)} "
          f"({100*len(a)/len(d):.1f}%)  |  no pasan: {len(b)}")
    tab = pd.DataFrame([
        {"grupo": "pasa footprint", "n": len(a),
         "D medio": round(a.D.mean(), 2),
         "follow EV": round(a.follow.mean(), 2),
         "fade EV": round(a.fade.mean(), 2),
         "follow EV neto": round(a.follow.mean() - COST, 2),
         "WR follow %": round(100 * (a.follow > 0).mean(), 1)},
        {"grupo": "no pasa", "n": len(b),
         "D medio": round(b.D.mean(), 2),
         "follow EV": round(b.follow.mean(), 2),
         "fade EV": round(b.fade.mean(), 2),
         "follow EV neto": round(b.follow.mean() - COST, 2),
         "WR follow %": round(100 * (b.follow > 0).mean(), 1)},
        {"grupo": "TODOS", "n": len(d),
         "D medio": round(d.D.mean(), 2),
         "follow EV": round(d.follow.mean(), 2),
         "fade EV": round(d.fade.mean(), 2),
         "follow EV neto": round(d.follow.mean() - COST, 2),
         "WR follow %": round(100 * (d.follow > 0).mean(), 1)},
    ])
    print(tab.to_string(index=False))
    print(f"\nDelta = D(pasa) - D(no pasa) = {delta:+.2f} ticks")
    print(f"intervalo bootstrap 95% por sesion: [{lo:+.2f}, {hi:+.2f}]")

    print("\nlectura:")
    if lo <= 0 <= hi:
        print("  el intervalo cruza cero: el footprint NO muestra informacion")
        print("  direccional incremental en el primer break.")
    elif delta > 0:
        print("  Delta positivo con intervalo que no cruza cero.")
        if a.D.mean() <= 0:
            print("  PERO D(pasa) sigue siendo negativo: el filtro es menos malo,")
            print("  no bueno. No alcanza para operar.")
        elif a.follow.mean() - COST <= 0:
            print("  PERO el EV neto del grupo que pasa es negativo: hay ventaja")
            print("  direccional sin rentabilidad.")
        else:
            print("  grupo que pasa con ventaja direccional Y EV neto positivo.")
            print("  Sigue siendo exploratorio: 2026 ya fue inspeccionado.")
    else:
        print("  Delta negativo: el footprint selecciona PEORES oportunidades")
        print("  direccionales que las que descarta.")

    # contextual check, prespecified: is the filter just picking later signals
    # or a different volatility regime?
    print("\ncontrol de contexto (no es el resultado, es para interpretarlo):")
    ctx = d.groupby("passes").agg(minuto_medio=("minute", "mean"),
                                  or_ticks_medio=("or_ticks", "mean"),
                                  n=("D", "size")).round(1)
    print(ctx.to_string())
    print(f"\n-> {OUT/'footprint_incremental.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
