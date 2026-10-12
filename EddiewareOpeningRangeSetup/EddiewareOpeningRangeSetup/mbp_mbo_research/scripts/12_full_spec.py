"""The complete rule as the trader states it, with the SL taken from the imbalance.

RULE (his words, 2026-10-11)
---------------------------
"solo se toma trade si en velas de 1 minuto una rompe con cuerpo el rango de la
 vela de las 9:30am hora ny, el SL va detras del imbalance, y si la VWAP no
 cambio de color"

So:
1. The 09:30-09:31 M1 candle gives ONLY its high and low. No entry on it.
2. From 09:31 to 09:39, the first M1 candle whose CLOSE clears that range.
3. That candle must carry an imbalance in the direction of the break
   (diagonal, ratio 3, volume filter 70 - his ATAS settings).
4. The stop goes BEHIND that imbalance, so the bracket size is not a free
   parameter any more: it is measured per trade. The 30-120 tick band becomes a
   filter on the resulting distance, not a grid to search.
5. The VWAP must not have changed colour, i.e. its slope must not have flipped
   between 09:31 and the entry candle. ATAS colours the VWAP/TWAP line by
   direction, so a colour change is a slope sign change.
6. R:R is 1:1, so TP distance = SL distance.

WHY THIS NEEDS THE TRADES DATA
Until now the imbalance was an optional filter and the brackets were a grid, so
the 1s bars were enough. Now the imbalance sets the stop. No footprint means no
stop, which means there is no trade to simulate at all. This script therefore
only runs on sessions that have a `trades` file.

7. When the candle carries two or more imbalances, the stop goes behind the one
   FARTHEST from price. His rule, confirmed. `--pick near` stays only as a
   sensitivity check; it is not the spec.

8. The stop sits ONE FULL CELL behind the imbalance row. A cell is 5 ticks, which
   is the same price grouping recovered from his chart, so the two agree.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import timedelta
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from config import (DATA, ENTRY_FROM, ENTRY_TO, MOVE_MAX_TICKS,
                    MOVE_MIN_TICKS, OR_OPEN)
from progress import track

_spec = importlib.util.spec_from_file_location("l2", HERE / "05_l2_features.py")
L2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L2)

TICK = 0.25
BARS = DATA / "bars"
TRADES = DATA / "trades"
OUT = DATA / "reports"
# One full footprint cell behind the imbalance. His words: "es una celda... me
# parece que son 5 por celda". The cell size is a chart setting, and the 5 ticks
# were already recovered independently from his screenshot (see IMB_GROUP in
# 05_l2_features.py), so two separate routes agree on it.
BUFFER_TICKS = 5
TIMEOUT_MIN = 30


def m1_and_vwap(day: pd.DataFrame) -> pd.DataFrame:
    """M1 candles plus the 09:30-anchored VWAP (Close-weighted, as his ATAS)."""
    d = day.copy()
    rth = d.ts_ny.dt.time >= OR_OPEN
    pv = np.where(rth, d.close * d.volume, 0.0)
    vol = np.where(rth, d.volume, 0.0)
    cv = np.cumsum(vol)
    d["vwap"] = np.where(cv > 0, np.cumsum(pv) / np.maximum(cv, 1e-9), np.nan)
    g = d.set_index("ts_ny").resample("1min")
    m1 = pd.DataFrame({"open": g.open.first(), "high": g.high.max(),
                       "low": g.low.min(), "close": g.close.last(),
                       "volume": g.volume.sum(), "vwap": g.vwap.last()}).dropna(
                           subset=["close"])
    return m1.reset_index().rename(columns={"ts_ny": "minute_ny"})


def vwap_colour_held(m1: pd.DataFrame, i_entry: int, i_first: int) -> bool:
    """True if the VWAP slope never flipped sign from the first post-OR minute.

    ATAS colours the line by direction, so "the VWAP did not change colour"
    means the sign of its slope stayed the same up to the entry candle. Flat
    minutes (slope exactly 0) are ignored rather than counted as a flip.
    """
    # start one candle earlier: the 09:30 -> 09:31 leg sets the colour that a
    # later reversal would be measured against, and omitting it hides a flip
    seg = m1.vwap.iloc[max(i_first - 1, 0):i_entry + 1].to_numpy(float)
    if len(seg) < 2:
        return True
    slope = np.sign(np.diff(seg))
    slope = slope[slope != 0]
    return bool(len(slope) == 0 or np.all(slope == slope[0]))


def touched_since_fast(ts: np.ndarray, lvls: np.ndarray, sizes: np.ndarray,
                       lvl: int, t_from, t_to) -> int:
    """Same as touched_since, but on precomputed arrays.

    The slow version filtered the whole trades frame on every call, and it is
    called thousands of times per session. Here the timestamps are already
    sorted, so the window is two binary searches and the check runs only over
    that slice.
    """
    # everything is compared as int64 nanoseconds: mixing tz-aware and
    # tz-naive timestamps raises instead of comparing
    # inclusive at t_from: under half-open minutes a print stamped exactly at
    # the closing boundary belongs to the NEXT candle and must count as a touch
    i0 = int(np.searchsorted(ts, pd.Timestamp(t_from).value, side="left"))
    i1 = int(np.searchsorted(ts, pd.Timestamp(t_to).value, side="left"))
    if i1 <= i0:
        return 0
    seg = lvls[i0:i1]
    return int(sizes[i0:i1][seg == lvl].sum())


def touched_since(trades: pd.DataFrame, lvl: int, t_from, t_to) -> int:
    """Contracts traded inside one footprint row between two timestamps.

    "Para que sea un imbalance valido el precio no debe haberlo tocado" is
    measured from the CLOSE of the candle that formed the imbalance, not while it
    was forming. Measuring it during formation is meaningless: a 1-minute NQ
    candle spans 100+ ticks and crosses any 5-tick row dozens of times on its
    way through - the real data showed 20 to 42 crossings per imbalance, which
    would reject every single one.

    So an imbalance is born clean when its candle closes, and it dies the moment
    price trades back into it. That is also exactly what "si lo toca seguimos
    esperando" describes: you wait, and while you wait a revisit invalidates the
    level you were going to hide the stop behind.

    Only trades strictly before the entry are ever looked at.
    """
    if trades.empty:
        return 0
    w = trades[(trades.ts_event > t_from) & (trades.ts_event < t_to)]
    if w.empty:
        return 0
    inside = ((np.round(w.price / TICK).astype("int64") - L2.IMB_GROUP_OFF)
              // L2.IMB_GROUP) == lvl
    return int(w.loc[inside, "size"].sum())


def imbalance_rows(candle_trades: pd.DataFrame) -> pd.DataFrame:
    """The imbalance rows of one M1 candle, with their price edges."""
    fp = L2.footprint(candle_trades, L2.IMB_GROUP, L2.IMB_GROUP_OFF)
    if fp.empty:
        return pd.DataFrame()
    ask, bid = fp.ask_vol.to_dict(), fp.bid_vol.to_dict()
    lo_l, hi_l = int(fp.index.min()), int(fp.index.max())
    rows = []
    for lvl in fp.index:
        a, b = ask.get(lvl, 0), bid.get(lvl, 0)
        a_ref, b_ref = bid.get(lvl - 1, 0), ask.get(lvl + 1, 0)
        row_lo = (lvl * L2.IMB_GROUP + L2.IMB_GROUP_OFF) * TICK
        row_hi = row_lo + (L2.IMB_GROUP - 1) * TICK
        buy_ok = (lvl < hi_l and a >= L2.IMB_MIN_VOL
                  and a - a_ref >= L2.IMB_MIN_DIFF
                  and a >= L2.IMB_RATIO * max(a_ref, 1))
        sell_ok = (lvl > lo_l and b >= L2.IMB_MIN_VOL
                   and b - b_ref >= L2.IMB_MIN_DIFF
                   and b >= L2.IMB_RATIO * max(b_ref, 1))
        if buy_ok:
            rows.append({"lvl": lvl, "kind": "buy", "row_lo": row_lo,
                         "row_hi": row_hi, "ratio": a / max(a_ref, 1), "vol": a})
        if sell_ok:
            rows.append({"lvl": lvl, "kind": "sell", "row_lo": row_lo,
                         "row_hi": row_hi, "ratio": b / max(b_ref, 1), "vol": b})
    return pd.DataFrame(rows)


def resolve(path: pd.DataFrame, side: int, entry: float, sl_ticks: float,
            rr: float = 1.0) -> dict:
    """Bracket with the stop at `sl_ticks` and the target at rr x that.

    The stop distance is fixed by the imbalance; `rr` only moves the target. Ties
    inside one second go to the stop, and a second that opens beyond the stop
    fills at its open, not at the stop price.
    """
    dist_ticks = sl_ticks * rr
    tp = entry + side * dist_ticks * TICK
    sl = entry - side * sl_ticks * TICK
    p = path[path.ts_utc <= path.ts_utc.iloc[0] + timedelta(minutes=TIMEOUT_MIN)]
    for b in p.itertuples(index=False):
        hit_tp = (b.high >= tp) if side > 0 else (b.low <= tp)
        hit_sl = (b.low <= sl) if side > 0 else (b.high >= sl)
        if hit_sl:
            gap = min(b.open, sl) if side > 0 else max(b.open, sl)
            return {"exit": "ambiguous" if hit_tp else "sl",
                    "ticks": round(side * (gap - entry) / TICK, 2)}
        if hit_tp:
            return {"exit": "tp", "ticks": float(dist_ticks)}
    last = p.iloc[-1]
    return {"exit": "timeout",
            "ticks": round(side * (last.close - entry) / TICK, 2)}


COST = 1.8      # 0.8 ticks de comision + 1.0 de slippage
RR_GRID = (1.0, 1.5, 2.0, 2.5, 3.0)


def report_by_rr(taken: pd.DataFrame) -> pd.DataFrame:
    """R:R x metrica. El breakeven cambia con el R:R y es lo que decide todo.

    Bruto: BE = 1/(1+rr). A 1:1 es 50%, a 1:2 es 33.3%, a 1:3 es 25%.
    Neto:  BE = (SL + coste) / (SL*(1+rr)), que depende del SL de cada trade,
    asi que se reporta su promedio.
    """
    rows = []
    for rr, g in taken.groupby("rr"):
        wins = g.ticks > 0
        gw = g.loc[wins, "ticks"].sum()
        gl = -g.loc[~wins, "ticks"].sum()
        be_g = 1.0 / (1.0 + rr)
        be_n = ((g.SL_ticks + COST) / (g.SL_ticks * (1.0 + rr))).mean()
        rows.append({
            "R:R": f"1:{rr:g}",
            "trades": len(g),
            "WR %": round(100 * wins.mean(), 1),
            "BE bruto %": round(100 * be_g, 1),
            "BE neto %": round(100 * be_n, 1),
            "margen pp": round(100 * (wins.mean() - be_n), 1),
            "PF": round(gw / gl, 2) if gl else np.inf,
            "SL med": round(g.SL_ticks.median(), 0),
            "TP med": round(g.TP_ticks.median(), 0),
            "EV bruto": round(g.ticks.mean(), 2),
            f"EV neto": round(g.ticks.mean() - COST, 2),
            "n ok": "" if len(g) >= 30 else "<30",
        })
    out = pd.DataFrame(rows)
    print("\n=== regla completa: R:R x metrica ===")
    print(out.to_string(index=False))
    print("  margen pp = WR menos el breakeven NETO. Negativo = pierde.")
    return out


def report(taken: pd.DataFrame) -> pd.DataFrame:
    """Mes x metrica, mas TOTAL, segun el estandar de reporte del proyecto.

    El SL cambia por trade, asi que el R multiple (ticks / SL) es la unidad
    comparable y el breakeven NETO tambien varia: 0.5 + coste/(2*SL). Se reporta
    el promedio de ese umbral junto al WR, porque el 50% bruto no es el listón.
    """
    t = taken.copy()
    t["mes"] = pd.to_datetime(t.sesion).dt.to_period("M").astype(str)
    t["R"] = t.ticks / t.SL_ticks
    t["be_net"] = 0.5 + COST / (2.0 * t.SL_ticks)
    rows = []
    for mes, g in list(t.groupby("mes")) + [("TOTAL", t)]:
        wins = g.ticks > 0
        gw = g.loc[wins, "ticks"].sum()
        gl = -g.loc[~wins, "ticks"].sum()
        meses = 1 if mes != "TOTAL" else max(t.mes.nunique(), 1)
        rows.append({
            "mes": mes,
            "trades": len(g),
            "trades/mes": round(len(g) / meses, 1),
            "WR %": round(100 * wins.mean(), 1),
            "BE neto %": round(100 * g.be_net.mean(), 2),
            "R:R": 1.0,
            "PF": round(gw / gl, 2) if gl else np.inf,
            "SL med": round(g.SL_ticks.median(), 0),
            "EV bruto": round(g.ticks.mean(), 2),
            f"EV neto (-{COST}t)": round(g.ticks.mean() - COST, 2),
            "EV en R": round(g.R.mean(), 3),
            "n ok": "" if len(g) >= 30 else "<30",
        })
    out = pd.DataFrame(rows)
    print("\n=== regla completa: mes x metrica ===")
    print(out.to_string(index=False))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pick", choices=["far", "near"], default="far",
                    help="FAR is the rule: with several imbalances the stop goes "
                         "behind the one farthest from price. NEAR is only a "
                         "sensitivity check.")
    a = ap.parse_args()

    files = sorted(BARS.glob("bars_1s_*.parquet"))
    if not files:
        print(f"no bars in {BARS}; run 03_build_bars.py first.")
        return 1
    bars = pd.concat((pd.read_parquet(f) for f in files),
                     ignore_index=True).sort_values("ts_utc")

    have = sorted(p.name.split("_")[-1].replace(".dbn.zst", "")
                  for p in TRADES.glob("NQ_trades_*.dbn.zst"))
    print(f"config ATAS: ratio={L2.IMB_RATIO} volfilter={L2.IMB_MIN_VOL} "
          f"mindiff={L2.IMB_MIN_DIFF} group={L2.IMB_GROUP}t off={L2.IMB_GROUP_OFF}t")
    print(f"sesiones con `trades`: {len(have)} de {bars.session.nunique()} con barras",
          flush=True)
    print(f"banda de movimiento: {MOVE_MIN_TICKS}-{MOVE_MAX_TICKS} ticks, "
          f"buffer tras el imbalance: {BUFFER_TICKS} ticks, "
          f"imbalance elegido: {a.pick}\n")
    if not have:
        print("sin `trades` no hay footprint, sin footprint no hay SL, y sin SL "
              "no hay trade que simular. Esta regla no se puede medir todavia.")
        return 1

    rows = []
    for sess in track(have, label="regla completa"):
        day = bars[bars.session.astype(str) == sess].reset_index(drop=True)
        if day.empty:
            continue
        m1 = m1_and_vwap(day)
        t = m1.minute_ny.dt.time
        or_bar = m1[(t >= OR_OPEN) & (t < ENTRY_FROM)]
        win = m1[(t >= ENTRY_FROM) & (t <= ENTRY_TO)]
        if or_bar.empty or win.empty:
            continue
        or_hi, or_lo = or_bar.high.max(), or_bar.low.min()

        td = db.DBNStore.from_file(
            TRADES / f"NQ_trades_{sess}.dbn.zst").to_df(price_type="float",
                                                        tz="UTC").reset_index()
        td["size"] = td["size"].astype("int64")
        td["ny"] = td.ts_event.dt.tz_convert(day.ts_ny.dt.tz)
        td["min"] = td.ny.dt.floor("1min")
        td = td.sort_values("ts_event")
        td_ts = td.ts_event.astype("int64").to_numpy()
        td_lvls = ((np.round(td.price.to_numpy() / TICK).astype("int64")
                    - L2.IMB_GROUP_OFF) // L2.IMB_GROUP)
        td_sizes = td["size"].to_numpy()

        # one pass over the session's candles: the footprint of each minute from
        # 09:30 up to the end of the entry window, computed once
        per_minute: dict[pd.Timestamp, pd.DataFrame] = {}
        for mj in m1.loc[(t >= OR_OPEN) & (t <= ENTRY_TO), "minute_ny"]:
            rj = imbalance_rows(td[td["min"] == mj])
            if not rj.empty:
                per_minute[mj] = rj

        i_first = int(win.index[0])
        rec = {"sesion": sess, "or_ticks": round((or_hi - or_lo) / TICK)}
        skipped: list[dict] = []
        for i in win.index:
            r = m1.loc[i]
            side = 1 if r.close > or_hi else (-1 if r.close < or_lo else 0)
            if side == 0:
                continue
            rec["minuto"] = r.minute_ny.strftime("%H:%M")
            rec["dir"] = "LONG" if side > 0 else "SHORT"

            want = "buy" if side > 0 else "sell"
            entry_ts = (r.minute_ny + pd.Timedelta(minutes=1)).tz_convert("UTC")

            # Imbalances from THIS candle and from every earlier candle of the
            # session are eligible. One from an earlier candle only counts if
            # price has not traded back into it since that candle closed.
            pool = []
            for mj, rj in per_minute.items():
                if mj > r.minute_ny:
                    continue
                close_j = (mj + pd.Timedelta(minutes=1)).tz_convert("UTC")
                for q in rj[rj.kind == want].itertuples():
                    hit = touched_since_fast(td_ts, td_lvls, td_sizes,
                                             q.lvl, close_j, entry_ts)
                    pool.append({"lvl": q.lvl, "row_lo": q.row_lo,
                                 "row_hi": q.row_hi, "ratio": q.ratio,
                                 "vol": q.vol, "from": mj.strftime("%H:%M"),
                                 "touched": hit})
            allp = pd.DataFrame(pool)
            mine = allp[allp.touched == 0] if not allp.empty else pd.DataFrame()
            rec["imb_a_favor"] = len(mine)
            rec["imb_tocados"] = (len(allp) - len(mine)) if not allp.empty else 0
            rec["vwap_color_ok"] = vwap_colour_held(m1, int(i), i_first)

            # "si lo toca seguimos esperando": a failed candle does not end the
            # session, the scan moves on to the next minute inside the window.
            if mine.empty:
                rec["motivo"] = ("imbalance tocado, sigo esperando"
                                 if not allp.empty else "sin imbalance a favor")
                skipped.append(dict(rec))
                continue
            if not rec["vwap_color_ok"]:
                rec["motivo"] = "la VWAP cambio de color"
                skipped.append(dict(rec))
                continue

            # the stop goes behind the imbalance: below it for a long, above for
            # a short, plus a buffer
            if side > 0:
                edge = mine.row_lo.min() if a.pick == "far" else mine.row_lo.max()
                stop = edge - BUFFER_TICKS * TICK
            else:
                edge = mine.row_hi.max() if a.pick == "far" else mine.row_hi.min()
                stop = edge + BUFFER_TICKS * TICK

            nxt = day[day.ts_ny >= r.minute_ny + pd.Timedelta(minutes=1)]
            if nxt.empty:
                rec["motivo"] = "sin camino despues de la senial"
                skipped.append(dict(rec))
                continue
            entry = float(nxt.iloc[0].open)
            # The stop must sit on the ADVERSE side of the actual entry. Price
            # moves between the M1 close and the next second, so a structural
            # stop can end up on the wrong side; abs() would silently reflect it
            # into a healthy looking distance and invent a trade that could
            # never be placed. Reject it instead, and count how often it happens.
            signed = side * (entry - stop)
            if signed <= 0:
                rec["motivo"] = "stop quedo del lado equivocado de la entrada"
                skipped.append(dict(rec))
                continue
            dist = signed / TICK
            rec.update({"entry": entry, "stop": round(stop, 2),
                        "SL_ticks": round(dist, 1)})
            if not (MOVE_MIN_TICKS <= dist <= MOVE_MAX_TICKS):
                rec["motivo"] = f"SL fuera de la banda ({dist:.0f} ticks)"
                skipped.append(dict(rec))
                continue
            # the signal and the stop are fixed; only the target moves, so one
            # pass over the path per R:R is all the extra work
            for rr in RR_GRID:
                res = resolve(nxt, side, entry, dist, rr)
                rows.append({**rec, "rr": rr, "motivo": "TRADE",
                             "exit": res["exit"], "ticks": res["ticks"],
                             "TP_ticks": round(dist * rr, 1),
                             "velas_descartadas": len(skipped)})
            break
        else:
            if skipped:
                rows.append({**skipped[-1],
                             "motivo": skipped[-1]["motivo"] + " (sin trade)",
                             "velas_descartadas": len(skipped)})
            else:
                rows.append({**rec, "motivo": "no rompio con cuerpo 09:31-09:39"})

    t = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    cols = [c for c in ("sesion", "minuto", "dir", "or_ticks", "imb_a_favor",
                        "vwap_color_ok", "entry", "stop", "SL_ticks", "motivo",
                        "exit", "ticks") if c in t.columns]
    print(t[cols].to_string(index=False))

    taken = t[t.motivo == "TRADE"] if "motivo" in t else pd.DataFrame()
    print(f"\nsesiones evaluadas: {len(t)}  |  trades tomados: {len(taken)}")
    if "motivo" in t:
        print("\npor que se descartaron:")
        print(t.motivo.value_counts().to_string())
    if len(taken):
        w = taken.ticks > 0
        print(f"\nWR {100*w.mean():.0f}%  EV bruto {taken.ticks.mean():+.1f} ticks  "
              f"EV neto {taken.ticks.mean()-1.8:+.1f}  "
              f"SL mediano {taken.SL_ticks.median():.0f} ticks")
        print("n diminuto: esto describe la mecanica, no mide un edge.")
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / f"full_spec_{a.pick}.csv", index=False)
    print(f"\n-> {OUT/f'full_spec_{a.pick}.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
