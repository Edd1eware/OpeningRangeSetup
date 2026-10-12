"""Independent search for an edge, with the protocol fixed before looking.

WHY THIS EXISTS
The trader's setup, measured over 150 EDT sessions, loses after costs in every
bracket. Rather than keep tuning it, this script asks a different question: does
the 09:30 opening range carry ANY tradeable asymmetry, in any direction?

THE PROTOCOL, FIXED IN ADVANCE
1. CANDIDATES ARE PRE-REGISTERED, below, in code, and all of them are reported.
   The list is short and each entry is there because a measurement already
   pointed at it, not because it was found by searching.
2. MECHANICAL SPLIT. In-sample is the first 100 sessions by date, out-of-sample
   the last 50. The split is the calendar, not the profit.
3. ONE SELECTION, ONE TEST. The best candidate on IS is chosen, then tested on
   OOS exactly once. Every other candidate's OOS number is printed too, so the
   selection cannot be hidden after the fact.
4. PLACEBO. The winner is compared against drawing the same number of trades at
   random from the same pool.
5. REQUIRED n. For each result, the sample needed to call it real at 80% power.
   If the required n exceeds what exists, the honest answer is "not yet known".

WHAT POINTED HERE
Measured on the 145 breakout signals of 2026:
  MAE median 639 ticks vs MFE median 581      -> adverse move is the bigger one
  84.8% return to the entry after reaching +120 -> reversion, not trend
  signals at 09:31: WR 43.3% vs 60.0% later    -> the first minute is the trap
  far from VWAP 59.6% vs near 43.1%            -> extension gets paid back
  all 7 market brackets at PF < 1.0            -> following the break loses
Every one of those says fade, not follow. So the candidates are mostly fades.
"""
from __future__ import annotations

import sys
from datetime import time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA, OR_OPEN
from progress import track

TICK = 0.25
BARS = DATA / "bars"
OUT = DATA / "reports"
COST = 1.8
IS_SESSIONS = 100          # in-sample = the first 100 sessions by date
ENTRY_FROM, ENTRY_TO = time(9, 31), time(9, 39)
LAST_EXIT = time(16, 0)
TIMEOUT_MIN = 60

# (nombre, que hace, por que esta en la lista)
CANDIDATES = [
    ("fade_break",
     "vender la ruptura al alza y comprar la ruptura a la baja",
     "MAE > MFE y 84.8% vuelve al entry: el adverso manda"),
    ("fade_far_vwap",
     "lo mismo, solo si el cierre esta lejos del VWAP (> mediana)",
     "lejos del VWAP dio WR 59.6% contra 43.1% cerca"),
    ("fade_late_only",
     "lo mismo, solo si la senal es de 09:32 o despues",
     "las senales de 09:31 dieron WR 43.3% contra 60.0% las posteriores"),
    ("follow_late_only",
     "seguir la ruptura, solo si la senal es de 09:32 o despues",
     "control: separa 'fade' de 'evitar el minuto 09:31'"),
    ("mean_rev_or_edges",
     "sin ruptura: vender en el alto del rango OR, comprar en el bajo",
     "si el rango contiene al precio, los extremos son el borde"),
    ("follow_break",
     "seguir la ruptura (el setup original, sin imbalances)",
     "linea base obligatoria: todo se compara contra esto"),
]


def net_be_wr(rr: float, sl_ticks: float) -> float:
    """WR que solo paga los costos, para un R:R dado."""
    return (sl_ticks + COST) / (sl_ticks * (1.0 + rr))


def required_n(wr: float, be: float, p: float = 0.8) -> float:
    """Trades needed to call `wr` better than `be` at 80% power, alpha 5%."""
    d = wr - be
    if d <= 0:
        return np.inf
    z_a, z_b = 1.645, 0.8416
    return float((z_a + z_b) ** 2 * wr * (1 - wr) / (d * d))


def build_signals(bars: pd.DataFrame) -> pd.DataFrame:
    """One row per session: the break, its context, and the forward path arrays."""
    rows = []
    for sess, day in track(list(bars.groupby("session")), label="senales"):
        day = day.reset_index(drop=True)
        rth = day.ts_ny.dt.time >= OR_OPEN
        pv = np.where(rth, day.close * day.volume, 0.0)
        vol = np.where(rth, day.volume, 0.0)
        cv = np.cumsum(vol)
        day = day.assign(vwap=np.where(cv > 0, np.cumsum(pv) / np.maximum(cv, 1e-9),
                                       np.nan))
        g = day.set_index("ts_ny").resample("1min")
        m1 = pd.DataFrame({"open": g.open.first(), "high": g.high.max(),
                           "low": g.low.min(), "close": g.close.last(),
                           "volume": g.volume.sum(),
                           "vwap": g.vwap.last()}).dropna(subset=["close"])
        m1 = m1.reset_index().rename(columns={"ts_ny": "minute_ny"})
        t = m1.minute_ny.dt.time
        orb = m1[(t >= OR_OPEN) & (t < ENTRY_FROM)]
        if orb.empty:
            continue
        or_hi, or_lo = float(orb.high.max()), float(orb.low.min())
        win = m1[(t >= ENTRY_FROM) & (t <= ENTRY_TO)]
        if win.empty or or_hi <= or_lo:
            continue

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
        nxt = day[(day.ts_ny >= r.minute_ny + pd.Timedelta(minutes=1))
                  & (day.ts_ny.dt.time <= LAST_EXIT)]
        if nxt.empty:
            continue
        rows.append({
            "session": sess,
            "minute": int(r.minute_ny.minute),
            "side": side,
            "or_hi": or_hi, "or_lo": or_lo,
            "or_ticks": round((or_hi - or_lo) / TICK),
            "entry_px": float(nxt.iloc[0].open),
            "vwap_dist": abs(r.close - r.vwap) / TICK if r.vwap == r.vwap else np.nan,
            "high": nxt.high.to_numpy(float),
            "low": nxt.low.to_numpy(float),
            "close": nxt.close.to_numpy(float),
            "ts": nxt.ts_utc.to_numpy(),
        })
    return pd.DataFrame(rows)


def walk(sig: pd.Series, side: int, entry: float, sl_t: float, rr: float) -> float:
    """P&L in ticks. Stop first on ties; a gap-through fills at the open."""
    tp = entry + side * sl_t * rr * TICK
    sl = entry - side * sl_t * TICK
    deadline = sig.ts[0] + np.timedelta64(TIMEOUT_MIN, "m")
    n = int(np.searchsorted(sig.ts, deadline, side="right"))
    hi, lo, cl = sig.high[:n], sig.low[:n], sig.close[:n]
    if len(hi) == 0:
        return 0.0
    hit_sl = (lo <= sl) if side > 0 else (hi >= sl)
    hit_tp = (hi >= tp) if side > 0 else (lo <= tp)
    i_sl = int(np.argmax(hit_sl)) if hit_sl.any() else 10 ** 9
    i_tp = int(np.argmax(hit_tp)) if hit_tp.any() else 10 ** 9
    if i_sl <= i_tp and i_sl < 10 ** 9:
        return -sl_t
    if i_tp < 10 ** 9:
        return sl_t * rr
    return float(side * (cl[-1] - entry) / TICK)


def apply_candidate(sigs: pd.DataFrame, name: str, sl_t: float, rr: float,
                    vwap_median: float) -> pd.DataFrame:
    rows = []
    for s in sigs.itertuples():
        side = s.side
        entry = s.entry_px
        if name == "fade_break":
            side = -s.side
        elif name == "fade_far_vwap":
            if not (s.vwap_dist == s.vwap_dist and s.vwap_dist > vwap_median):
                continue
            side = -s.side
        elif name == "fade_late_only":
            if s.minute < 32:
                continue
            side = -s.side
        elif name == "follow_late_only":
            if s.minute < 32:
                continue
        elif name == "mean_rev_or_edges":
            # no break needed: short the OR high, long the OR low, whichever the
            # break touched, entering at the level itself
            side = -s.side
            entry = s.or_hi if s.side > 0 else s.or_lo
        elif name != "follow_break":
            raise ValueError(name)
        rows.append({"session": s.session,
                     "ticks": walk(s, side, entry, sl_t, rr)})
    return pd.DataFrame(rows)


def summarize(t: pd.DataFrame, sl_t: float, rr: float) -> dict:
    if t.empty:
        return {"trades": 0}
    wins = t.ticks > 0
    gw = t.loc[wins, "ticks"].sum()
    gl = -t.loc[~wins, "ticks"].sum()
    wr = float(wins.mean())
    be = net_be_wr(rr, sl_t)
    return {"trades": len(t),
            "WR %": round(100 * wr, 1),
            "BE neto %": round(100 * be, 1),
            "PF": round(gw / gl, 2) if gl else np.inf,
            "EV neto": round(t.ticks.mean() - COST, 2),
            "n req": (int(required_n(wr, be)) if np.isfinite(required_n(wr, be))
                      else -1)}


def main() -> int:
    files = sorted(BARS.glob("bars_1s_*.parquet"))
    if not files:
        print(f"no hay barras en {BARS}")
        return 1
    bars = pd.concat((pd.read_parquet(f) for f in files),
                     ignore_index=True).sort_values("ts_utc")
    sigs = build_signals(bars)
    sigs = sigs.sort_values("session").reset_index(drop=True)
    sessions = sigs.session.tolist()
    cut = sessions[min(IS_SESSIONS, len(sessions)) - 1]
    is_mask = sigs.session <= cut
    print(f"\n{len(sigs)} senales. IS: {int(is_mask.sum())} sesiones hasta {cut}, "
          f"OOS: {int((~is_mask).sum())} despues")

    # el SL y el R:R se fijan ANTES de mirar: el SL es el rango OR mediano / 2,
    # redondeado, y el R:R se prueba en una rejilla chica y declarada
    sl_t = float(np.round(sigs.or_ticks.median() / 2))
    vwap_med = float(sigs.loc[is_mask, "vwap_dist"].median())
    print(f"SL fijado en {sl_t:.0f} ticks (mediana del rango OR / 2), "
          f"umbral VWAP {vwap_med:.0f} ticks (mediana IN-SAMPLE)")

    rr_grid = (1.0, 1.5, 2.0)
    pd.set_option("display.width", 220)
    rows = []
    for name, what, why in CANDIDATES:
        for rr in rr_grid:
            t_is = apply_candidate(sigs[is_mask], name, sl_t, rr, vwap_med)
            t_oos = apply_candidate(sigs[~is_mask], name, sl_t, rr, vwap_med)
            s_is = summarize(t_is, sl_t, rr)
            s_oos = summarize(t_oos, sl_t, rr)
            rows.append({"candidato": name, "R:R": f"1:{rr:g}",
                         **{f"IS {k}": v for k, v in s_is.items()},
                         **{f"OOS {k}": v for k, v in s_oos.items()}})
    tab = pd.DataFrame(rows)
    print("\n=== candidatos pre-registrados: in-sample y out-of-sample ===")
    print(tab.to_string(index=False))

    print("\n--- que hace cada uno y por que esta en la lista ---")
    for name, what, why in CANDIDATES:
        print(f"  {name:18s} {what}\n{'':20s}-> {why}")

    # UNA seleccion, hecha solo con IS, y UNA lectura de su OOS
    pick = tab.loc[tab["IS EV neto"].idxmax()]
    print(f"\n=== seleccion hecha SOLO con in-sample ===")
    print(f"ganador IS: {pick.candidato} a {pick['R:R']}  "
          f"IS EV neto {pick['IS EV neto']:+.2f}  WR {pick['IS WR %']}%")
    print(f"su OOS:     EV neto {pick['OOS EV neto']:+.2f}  "
          f"WR {pick['OOS WR %']}%  PF {pick['OOS PF']}  "
          f"n {pick['OOS trades']}")
    if pick["OOS EV neto"] <= 0:
        print("  -> el ganador in-sample NO sobrevive fuera de muestra. "
              "Eso es la respuesta, no un paso intermedio.")

    rr_pick = float(str(pick["R:R"]).split(":")[1])
    t_oos = apply_candidate(sigs[~is_mask], pick.candidato, sl_t, rr_pick, vwap_med)
    base = apply_candidate(sigs[~is_mask], "follow_break", sl_t, rr_pick, vwap_med)
    if len(t_oos) and len(base):
        rng = np.random.default_rng(23)
        tgt = t_oos.ticks.mean()
        pool = base.ticks.to_numpy()
        draws = [rng.choice(pool, size=min(len(t_oos), len(pool)),
                            replace=False).mean() for _ in range(2000)]
        p = float(np.mean(np.array(draws) >= tgt))
        print(f"\nplacebo OOS (misma cantidad al azar del pool base): p = {p:.3f}")
        if p > 0.05:
            print("  -> no le gana a una seleccion aleatoria del mismo tamanio.")

    OUT.mkdir(parents=True, exist_ok=True)
    tab.to_csv(OUT / "edge_search.csv", index=False)
    print(f"\n-> {OUT/'edge_search.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
