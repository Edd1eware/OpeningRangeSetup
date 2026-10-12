"""Does a trailing stop beat the fixed 1:1 once a move clears 120 ticks?

THE TRAP THIS SCRIPT AVOIDS
---------------------------
"Trail on trending days" cannot be traded: whether a day trends is known only
afterwards. So every policy here is applied to EVERY signal, and the trending
days are what has to pay for the ones that give back the fixed target. Any
result that first selects the trending days is lookahead, not a strategy.

CONSERVATIVE PATH RESOLUTION
----------------------------
1s bars give OHLC per second, not the order inside the second. So:
* the trailing stop for second i is computed from the running maximum of
  seconds BEFORE i, never from second i's own high;
* when a second touches both the stop and the target, the stop wins.
Both choices cost EV. Reversing either one manufactures it.

POLICIES
--------
fixed      : TP = SL = N ticks. The baseline, 1:1, breakeven WR 50%.
hold       : SL = N, no TP, flat at the horizon. Isolates "just let it run"
             from the trailing itself.
trail      : SL = N, no TP; once the move has been ACTIVATE ticks in favour,
             the stop follows the high at DIST ticks.
half_trail : half off at +N (the 1:1 target), stop to breakeven on the rest,
             which then trails at DIST after ACTIVATE.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA, NY
from progress import track

TICK = 0.25
EVENTS = DATA / "events" / "or_events.parquet"
BARS = DATA / "bars"
OUT = DATA / "reports"

COST_1EXIT = 1.8      # 0.8 ticks commission + 1.0 tick slippage
COST_2EXIT = 2.2      # scaling out pays one more commission
ACTIVATE_GRID = (80, 120, 160)      # 120 is the spec; the others are sensitivity
DIST_GRID = (20, 30, 40, 60)
SL_GRID = (30, 40, 60)
HORIZONS = {"30min": 30, "60min": 60, "close": None}   # None = 16:00 ET
SESSION_CLOSE = pd.Timestamp("16:00").time()


def excursions(path: pd.DataFrame, side: int, entry: float
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-second favourable high, favourable low and close, all in ticks.

    Everything downstream works in "ticks in favour of the trade", so long and
    short share one code path and a stop is just a level on that axis.
    """
    hi = path.high.to_numpy(float)
    lo = path.low.to_numpy(float)
    cl = path.close.to_numpy(float)
    if side > 0:
        fav_hi = (hi - entry) / TICK
        fav_lo = (lo - entry) / TICK
    else:
        fav_hi = (entry - lo) / TICK
        fav_lo = (entry - hi) / TICK
    return fav_hi, fav_lo, (cl - entry) / TICK * side


def _first(mask: np.ndarray) -> int:
    idx = np.flatnonzero(mask)
    return int(idx[0]) if idx.size else -1


def sim_fixed(fav_hi, fav_lo, fav_cl, tp: float, sl: float) -> tuple[float, str, int]:
    i_tp = _first(fav_hi >= tp)
    i_sl = _first(fav_lo <= -sl)
    if i_sl >= 0 and (i_tp < 0 or i_sl <= i_tp):
        return -sl, ("ambiguous" if i_sl == i_tp else "sl"), i_sl
    if i_tp >= 0:
        return tp, "tp", i_tp
    return float(fav_cl[-1]), "timeout", len(fav_cl) - 1


def sim_trail(fav_hi, fav_lo, fav_cl, sl: float, activate: float, dist: float,
              start_stop: float | None = None) -> tuple[float, str, int]:
    """Stop at -sl, following the high at `dist` once `activate` is reached.

    `start_stop` overrides the initial stop level (0 = breakeven), which is what
    the second half of the scale-out policy runs with.
    """
    base_stop = -sl if start_stop is None else start_stop
    # running max of the PREVIOUS seconds only: shift the cummax by one
    prev_max = np.concatenate(([-np.inf], np.maximum.accumulate(fav_hi)[:-1]))
    live = prev_max >= activate
    stop = np.where(live, np.maximum(base_stop, prev_max - dist), base_stop)
    i = _first(fav_lo <= stop)
    if i >= 0:
        return float(stop[i]), ("trail" if live[i] else "sl"), i
    return float(fav_cl[-1]), "timeout", len(fav_cl) - 1


def sim_half_trail(fav_hi, fav_lo, fav_cl, tp: float, sl: float,
                   activate: float, dist: float) -> tuple[float, str, int]:
    first_half, kind, i = sim_fixed(fav_hi, fav_lo, fav_cl, tp, sl)
    if kind != "tp":
        return first_half, kind, i          # stopped or timed out before the target
    rest, kind2, j = sim_trail(fav_hi[i:], fav_lo[i:], fav_cl[i:],
                               sl=0.0, activate=activate, dist=dist,
                               start_stop=0.0)
    return 0.5 * tp + 0.5 * rest, f"half+{kind2}", i + j


def main() -> int:
    for p in (EVENTS, BARS):
        if not p.exists():
            print(f"missing {p}; run the earlier stages first.")
            return 1
    ev = pd.read_parquet(EVENTS)
    ev = ev[ev.filled & ev.entry_ts.notna()]
    if "entry_ts" not in ev.columns or ev.empty:
        print("events have no entry_ts; re-run 04_or_events.py.")
        return 1
    # one row per (session, entry_mode): the bracket does not change the entry
    sigs = ev.drop_duplicates(["session", "entry_mode"])[
        ["session", "entry_mode", "side", "entry_ts", "entry_px"]]

    bars = pd.concat((pd.read_parquet(f) for f in sorted(BARS.glob("bars_1s_*.parquet"))),
                     ignore_index=True).sort_values("ts_utc")
    by_session = {s: g.reset_index(drop=True) for s, g in bars.groupby("session")}
    print(f"{len(sigs)} entries over {sigs.session.nunique()} sessions, "
          f"{len(bars):,} 1s bars")
    print(f"costs: {COST_1EXIT} ticks (single exit), {COST_2EXIT} ticks (scale out)\n")

    rows, mfe_rows, race_rows = [], [], []
    for r in track(list(sigs.itertuples(index=False)), label="trailing policies"):
        day = by_session.get(r.session)
        if day is None:
            continue
        t_in = pd.Timestamp(r.entry_ts)
        path_all = day[(day.ts_utc >= t_in)
                       & (day.ts_ny.dt.time <= SESSION_CLOSE)]
        if path_all.empty:
            continue

        for hname, mins in HORIZONS.items():
            path = (path_all if mins is None
                    else path_all[path_all.ts_utc <= t_in + pd.Timedelta(minutes=mins)])
            if path.empty:
                continue
            fav_hi, fav_lo, fav_cl = excursions(path, r.side, r.entry_px)
            mfe, mae = float(fav_hi.max()), float(-fav_lo.min())
            if hname == "close":
                mfe_rows.append({"session": r.session, "entry_mode": r.entry_mode,
                                 "mfe_ticks": mfe, "mae_ticks": mae,
                                 "close_ticks": float(fav_cl[-1])})
            common = {"session": r.session, "entry_mode": r.entry_mode,
                      "horizon": hname, "mfe_ticks": mfe, "mae_ticks": mae}

            # The number that actually decides whether trailing has anything to
            # work with: did the move reach the activation level BEFORE the stop
            # was hit? An MFE of 120 that only happens after the stop is useless.
            if hname == "close":
                for act in ACTIVATE_GRID:
                    i_act = _first(fav_hi >= act)
                    for sl in SL_GRID:
                        i_sl = _first(fav_lo <= -sl)
                        reach = (i_act >= 0 and (i_sl < 0 or i_act < i_sl))
                        race_rows.append({"session": r.session,
                                          "entry_mode": r.entry_mode,
                                          "activate": act, "sl": sl,
                                          "reached_first": bool(reach)})

            for sl in SL_GRID:
                t, k, _ = sim_fixed(fav_hi, fav_lo, fav_cl, sl, sl)
                rows.append({**common, "policy": "fixed", "sl": sl,
                             "activate": np.nan, "dist": np.nan,
                             "ticks": t, "kind": k, "cost": COST_1EXIT})
                t, k, _ = sim_trail(fav_hi, fav_lo, fav_cl, sl,
                                    activate=np.inf, dist=np.inf)
                rows.append({**common, "policy": "hold", "sl": sl,
                             "activate": np.nan, "dist": np.nan,
                             "ticks": t, "kind": k, "cost": COST_1EXIT})
                for act in ACTIVATE_GRID:
                    for d in DIST_GRID:
                        t, k, _ = sim_trail(fav_hi, fav_lo, fav_cl, sl, act, d)
                        rows.append({**common, "policy": "trail", "sl": sl,
                                     "activate": act, "dist": d,
                                     "ticks": t, "kind": k, "cost": COST_1EXIT})
                        t, k, _ = sim_half_trail(fav_hi, fav_lo, fav_cl, sl, sl, act, d)
                        rows.append({**common, "policy": "half_trail", "sl": sl,
                                     "activate": act, "dist": d,
                                     "ticks": t, "kind": k, "cost": COST_2EXIT})

    res = pd.DataFrame(rows)
    mfe = pd.DataFrame(mfe_rows)
    res["net"] = res.ticks - res.cost
    OUT.mkdir(parents=True, exist_ok=True)
    res.to_parquet(OUT / "trailing_raw.parquet", index=False)

    pd.set_option("display.width", 230)

    # --- how often is there even a trend to trail? ---------------------------
    mk = mfe[mfe.entry_mode == "market"]
    print("=== maximum favourable excursion to 16:00 ET (market entry) ===")
    print(f"n = {len(mk)} entries")
    tab = []
    for thr in (30, 60, 80, 120, 160, 200, 300):
        tab.append({"MFE >= ticks": thr,
                    "sesiones": int((mk.mfe_ticks >= thr).sum()),
                    "%": round(100 * (mk.mfe_ticks >= thr).mean(), 1)})
    print(pd.DataFrame(tab).to_string(index=False))
    print(f"\nMFE mediana {mk.mfe_ticks.median():.0f} ticks, "
          f"p75 {mk.mfe_ticks.quantile(.75):.0f}, max {mk.mfe_ticks.max():.0f}")
    print(f"MAE mediana {mk.mae_ticks.median():.0f} ticks, "
          f"p75 {mk.mae_ticks.quantile(.75):.0f}")

    # --- does the move reach the activation level BEFORE the stop? -----------
    race = pd.DataFrame(race_rows)
    rk = race[race.entry_mode == "market"]
    print("\n=== llega a +ACTIVA ticks ANTES de que pegue el SL? (market) ===")
    piv = (rk.pivot_table(index="activate", columns="sl",
                          values="reached_first", aggfunc="mean") * 100).round(1)
    piv.columns = [f"SL {c}" for c in piv.columns]
    print(piv.to_string())
    print("  (% de entradas donde hay algo que trailear; el resto muere en el stop)")

    # --- policy comparison ---------------------------------------------------
    def summarize(g: pd.DataFrame) -> dict:
        wins = g.ticks > 0
        gw = g.loc[wins, "ticks"].sum()
        gl = -g.loc[~wins, "ticks"].sum()
        # Drop the single best trade. If the EV collapses, the policy is not an
        # edge, it is one lucky session carrying every other loss.
        trimmed = g.net.sort_values().iloc[:-1] if len(g) > 1 else g.net
        top_share = (g.ticks.max() / gw * 100) if gw > 0 else np.nan
        return {"trades": len(g),
                "WR %": round(100 * wins.mean(), 1),
                "PF": round(gw / gl, 2) if gl else np.inf,
                "EV bruto": round(g.ticks.mean(), 2),
                "EV neto": round(g.net.mean(), 2),
                "EV sin mejor": round(trimmed.mean(), 2),
                "% gan del top1": round(top_share, 1) if top_share == top_share else np.nan,
                "mejor": round(g.ticks.max(), 0),
                "peor": round(g.ticks.min(), 0)}

    for mode in ("market",):
        sub = res[res.entry_mode == mode]
        for hname in HORIZONS:
            h = sub[sub.horizon == hname]
            if h.empty:
                continue
            out = []
            for (pol, sl, act, d), g in h.groupby(
                    ["policy", "sl", "activate", "dist"], dropna=False):
                out.append({"policy": pol, "SL": int(sl),
                            "activa": "" if pd.isna(act) else int(act),
                            "trail": "" if pd.isna(d) else int(d),
                            **summarize(g)})
            t = pd.DataFrame(out).sort_values("EV neto", ascending=False)
            print(f"\n=== {mode} / horizonte {hname} (top 12 por EV neto) ===")
            print(t.head(12).to_string(index=False))
            base = t[t.policy == "fixed"]
            print(f"  baseline fijo 1:1: "
                  f"{', '.join(f'SL{int(r.SL)} EV neto {r._9}' for r in base.itertuples())}"
                  if not base.empty else "")

    # --- the honest summary --------------------------------------------------
    best = res[res.entry_mode == "market"].groupby(
        ["horizon", "policy", "sl", "activate", "dist"], dropna=False).net.mean()
    fixed_best = best.xs("fixed", level="policy").max()
    print(f"\nmejor EV neto de cualquier politica: {best.max():.2f} ticks")
    print(f"mejor EV neto del fijo 1:1:          {fixed_best:.2f} ticks")
    n_cells = best.size
    print(f"celdas probadas: {n_cells}. Con n={len(mk)} entradas, la mejor celda "
          "de un barrido asi se elige por ruido: hace falta validarla "
          "out-of-sample en anios que no se usaron para elegirla.")
    res.to_csv(OUT / "trailing_summary.csv", index=False)
    print(f"\n-> {OUT/'trailing_raw.parquet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
