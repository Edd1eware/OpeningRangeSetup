"""Empirical path statistics, so the trailing parameters come from the data.

Guessing a grid of trail distances and picking the best cell is curve fitting.
This script measures the five distributions that actually determine what a
trailing rule can and cannot do, and prints the parameter each one implies:

1. CONTINUATION CURVE   P(reach +2K | reached +K). If a move that got to +80
   almost always gets to +160, letting it run is justified. If not, it is not.
2. PULLBACK DEPTH       inside a run, how deep does it retrace from the running
   high before going on? The trail distance has to clear the p75/p90 of this or
   it gets knocked out by ordinary noise.
3. HEAT BEFORE THE RUN  how far does a trade that eventually reaches +120 go
   AGAINST first? That is the minimum stop that keeps those trades alive.
4. RETURN TO ENTRY      P(price touches entry again | reached +K). Below ~10%
   is where moving the stop to breakeven stops costing more than it saves.
5. TIME TO THE PEAK     when the MFE actually happens. If it is early, a clock
   exit beats a trail.

Everything is measured on the market entry and the path to 16:00 ET, with no
selection on outcome, so these are the unconditional facts of the setup.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA
from progress import track

TICK = 0.25
EVENTS = DATA / "events" / "or_events.parquet"
BARS = DATA / "bars"
OUT = DATA / "reports"
SESSION_CLOSE = pd.Timestamp("16:00").time()

K_GRID = (20, 30, 40, 60, 80, 120, 160, 200, 300)


def favourable(path: pd.DataFrame, side: int, entry: float):
    hi = path.high.to_numpy(float)
    lo = path.low.to_numpy(float)
    if side > 0:
        return (hi - entry) / TICK, (lo - entry) / TICK
    return (entry - lo) / TICK, (entry - hi) / TICK


def describe(x: pd.Series, name: str) -> dict:
    x = x.dropna()
    if x.empty:
        return {"stat": name, "n": 0}
    return {"stat": name, "n": len(x), "mediana": round(x.median(), 1),
            "p25": round(x.quantile(.25), 1), "p75": round(x.quantile(.75), 1),
            "p90": round(x.quantile(.90), 1), "max": round(x.max(), 1)}


def main() -> int:
    ev = pd.read_parquet(EVENTS)
    ev = ev[(ev.entry_mode == "market") & ev.filled]
    sigs = ev.drop_duplicates("session")[["session", "side", "entry_ts", "entry_px"]]
    bars = pd.concat((pd.read_parquet(f) for f in sorted(BARS.glob("bars_1s_*.parquet"))),
                     ignore_index=True).sort_values("ts_utc")
    by_session = {s: g.reset_index(drop=True) for s, g in bars.groupby("session")}
    print(f"{len(sigs)} market entries, path measured to 16:00 ET\n")

    cont, pull, heat, back, peak = [], [], [], [], []
    for r in track(list(sigs.itertuples(index=False)), label="path stats"):
        day = by_session.get(r.session)
        if day is None:
            continue
        t_in = pd.Timestamp(r.entry_ts)
        path = day[(day.ts_utc >= t_in) & (day.ts_ny.dt.time <= SESSION_CLOSE)]
        if len(path) < 2:
            continue
        fav_hi, fav_lo = favourable(path, r.side, r.entry_px)
        mins = ((pd.DatetimeIndex(path.ts_utc) - t_in)
                .total_seconds().to_numpy() / 60.0)

        run_max = np.maximum.accumulate(fav_hi)
        i_peak = int(np.argmax(fav_hi))
        mfe = float(fav_hi.max())
        peak.append({"session": r.session, "mfe": mfe,
                     "mins_to_peak": float(mins[i_peak]),
                     "mae": float(-fav_lo.min())})

        for k in K_GRID:
            i_k = np.flatnonzero(fav_hi >= k)
            reached = i_k.size > 0
            row = {"session": r.session, "K": k, "reached": reached}
            if reached:
                i0 = int(i_k[0])
                # 1. continuation: does it double from here?
                row["reached_2k"] = bool((fav_hi[i0:] >= 2 * k).any())
                # 3. heat: worst adverse excursion BEFORE first touching +K
                row["heat_before"] = float(-fav_lo[:i0 + 1].min())
                # 4. does price come back to the entry after reaching +K?
                row["back_to_entry"] = bool((fav_lo[i0:] <= 0).any())
                # 2. deepest retrace from the running high, after +K
                dd = run_max[i0:] - fav_lo[i0:]
                row["pullback_max"] = float(dd.max())
                # the retrace that happened BEFORE the peak, i.e. one a trail
                # would have had to survive to stay in the move
                if i_peak > i0:
                    row["pullback_pre_peak"] = float(
                        (run_max[i0:i_peak] - fav_lo[i0:i_peak]).max())
            cont.append(row)

    c = pd.DataFrame(cont)
    pk = pd.DataFrame(peak)
    OUT.mkdir(parents=True, exist_ok=True)
    c.to_parquet(OUT / "path_stats_raw.parquet", index=False)
    pd.set_option("display.width", 220)

    n = pk.shape[0]
    print("=== 1. curva de continuacion ===")
    t1 = []
    for k in K_GRID:
        g = c[c.K == k]
        hit = g[g.reached]
        t1.append({"K ticks": k,
                   "llega a +K": int(g.reached.sum()),
                   "% llega": round(100 * g.reached.mean(), 1),
                   "y sigue a +2K": int(hit.reached_2k.sum()) if len(hit) else 0,
                   "% continua": round(100 * hit.reached_2k.mean(), 1) if len(hit) else np.nan})
    print(pd.DataFrame(t1).to_string(index=False))
    print("  lectura: si '% continua' se mantiene alto, dejar correr tiene base;")
    print("  si cae por debajo de ~50% el movimiento se agota y conviene objetivo fijo.")

    print("\n=== 2. profundidad del retroceso (ticks desde el maximo corrido) ===")
    rows = []
    for k in (60, 80, 120, 160):
        g = c[(c.K == k) & c.reached]
        if g.empty:
            continue
        rows.append({**describe(g.pullback_pre_peak, f"retroceso antes del pico (K={k})")})
        rows.append({**describe(g.pullback_max, f"retroceso maximo tras +{k}")})
    print(pd.DataFrame(rows).to_string(index=False))
    print("  lectura: la distancia del trailing tiene que superar el p75-p90 de")
    print("  'retroceso antes del pico' o el trail sale en ruido normal.")

    print("\n=== 3. calor antes de llegar a +K (stop minimo que los deja vivos) ===")
    rows = [describe(c[(c.K == k) & c.reached].heat_before, f"calor antes de +{k}")
            for k in (60, 80, 120, 160)]
    print(pd.DataFrame(rows).to_string(index=False))
    print("  lectura: un SL por debajo de la mediana mata la mitad de los trades")
    print("  que SI iban a llegar a +K.")

    print("\n=== 4. regresa al entry despues de llegar a +K ===")
    t4 = []
    for k in K_GRID:
        g = c[(c.K == k) & c.reached]
        if g.empty:
            continue
        t4.append({"K ticks": k, "n": len(g),
                   "% regresa al entry": round(100 * g.back_to_entry.mean(), 1)})
    print(pd.DataFrame(t4).to_string(index=False))
    print("  lectura: el K donde esto baja de ~10% es donde mover el stop a")
    print("  breakeven deja de costar mas de lo que salva.")

    print("\n=== 5. cuando ocurre el maximo del movimiento ===")
    print(pd.DataFrame([describe(pk.mins_to_peak, "minutos hasta el MFE"),
                        describe(pk.mfe, "MFE ticks"),
                        describe(pk.mae, "MAE ticks")]).to_string(index=False))
    early = 100 * (pk.mins_to_peak <= 30).mean()
    print(f"  {early:.1f}% de los maximos ocurren en los primeros 30 min.")

    print(f"\n-> {OUT/'path_stats_raw.parquet'}  (n={n} entradas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
