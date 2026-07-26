"""MULTIINST-V1 Stage 1 - does the first-breakout-UP edge transfer to ES?

Frozen by PREREGISTRO_MULTIINST_V1.md (SHA-256 7a9b5620...).
Trade logic copied verbatim from orb_trailing_sim.py. Trailing scaled by median
OR size ratio computed on DEV only. Cost: $0 (ES already on disk).
"""

from __future__ import annotations

import glob
import hashlib
import json
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from progress import track

BASE = Path(__file__).resolve().parent
OUT = BASE / "output"
ROOTS = {
    "NQ": Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
               r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_2"),
    "ES": Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
               r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_es"),
}
TICK = {"NQ": 0.25, "ES": 0.25}
PREREG_SHA = "7a9b562040927da1330b4bd989ae73fac9f381ac6eba2bead68d741d7d0c2e8a"

OR_START, OR_END, SCAN_START = "13:30:00", "13:31:00", "13:31:00"
SL0, ACT0, DIST0 = 40, 20, 40
COMMISSION = 2.0
DEV_Y, FRESH_Y = {2022, 2023}, {2024, 2025, 2026}
E3_PF = 1.15


def sha256_file(p: Path) -> str:
    d = hashlib.sha256()
    with p.open("rb") as s:
        for c in iter(lambda: s.read(1 << 20), b""):
            d.update(c)
    return d.hexdigest()


def load_session(root: Path, date: str):
    hits = glob.glob(str(root / date / "ohlcv-1s-full" / "*.dbn.zst"))
    if not hits:
        return None
    return db.DBNStore.from_file(hits[0]).to_df()[
        ["open", "high", "low", "close"]].sort_index()


def find_up_breakout(df: pd.DataFrame, tick: float):
    """First UPWARD pierce of the OR high. Returns (or_ticks, entry, fwd)."""
    day = df.index[0].strftime("%Y-%m-%d")
    orw = df.between_time(OR_START, OR_END, inclusive="left")
    if orw.empty:
        return None
    or_high, or_low = float(orw["high"].max()), float(orw["low"].min())
    or_ticks = (or_high - or_low) / tick
    post = df.loc[df.index >= pd.Timestamp(f"{day} {SCAN_START}", tz="UTC")]
    if post.empty:
        return None
    up = post.index[post["high"] > or_high]
    dn = post.index[post["low"] < or_low]
    t_up = up[0] if len(up) else None
    t_dn = dn[0] if len(dn) else None
    if t_up is None:
        return or_ticks, None, None           # no UP breakout that day
    if t_dn is not None and t_dn < t_up:
        return or_ticks, None, None           # DOWN came first -> not our trade
    return or_ticks, or_high, post.loc[post.index >= t_up]


def trail_pnl(fwd, entry, tick, sl, act, dist) -> float:
    stop = entry - sl * tick
    best, activated, close = entry, False, entry
    for h, l, c in zip(fwd["high"].to_numpy(), fwd["low"].to_numpy(),
                       fwd["close"].to_numpy()):
        close = c
        if l <= stop:
            return (stop - entry) / tick
        best = max(best, h)
        if not activated and (best - entry) / tick >= act:
            activated = True
        if activated:
            stop = max(stop, best - dist * tick)
    return (close - entry) / tick


def scan(inst: str) -> pd.DataFrame:
    root, tick = ROOTS[inst], TICK[inst]
    dates = sorted(p.name for p in root.iterdir() if p.is_dir())
    rows = []
    for d in track(dates, label=f"{inst} primer breakout UP"):
        try:
            df = load_session(root, d)
            if df is None or df.empty:
                continue
            bo = find_up_breakout(df, tick)
            if bo is None:
                continue
            or_ticks, entry, fwd = bo
            rows.append({"date": d, "year": int(d[:4]), "or_ticks": or_ticks,
                         "entry": entry, "fwd": fwd})
        except Exception:  # noqa: BLE001
            continue
    return pd.DataFrame(rows)


def metrics(net: np.ndarray, months: int) -> dict:
    if net.size == 0:
        return {"trades": 0}
    gl = -net[net < 0].sum()
    return {"trades": int(net.size),
            "trades_mes": round(net.size / max(months, 1), 2),
            "wr": round(float((net > 0).mean() * 100), 2),
            "pf": round(float(net[net > 0].sum() / gl), 3) if gl > 0 else None,
            "ev_net": round(float(net.mean()), 3)}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    if sha256_file(BASE / "PREREGISTRO_MULTIINST_V1.md") != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")

    scans = {i: scan(i) for i in ("NQ", "ES")}
    med = {}
    for i, s in scans.items():
        dev = s[s["year"].isin(DEV_Y)]
        med[i] = float(dev["or_ticks"].median())
    k_es = med["ES"] / med["NQ"]
    sl, act, dist = (max(1, round(SL0 * k_es)), max(1, round(ACT0 * k_es)),
                     max(1, round(DIST0 * k_es)))
    params = {"NQ": (SL0, ACT0, DIST0), "ES": (sl, act, dist)}

    results = {}
    for i, s in scans.items():
        p = params[i]
        rows = []
        for r in s.itertuples(index=False):
            if r.entry is None or r.fwd is None:
                continue
            pnl = trail_pnl(r.fwd, r.entry, TICK[i], *p) - COMMISSION
            rows.append({"date": r.date, "year": r.year, "net": pnl})
        f = pd.DataFrame(rows)
        f["date"] = pd.to_datetime(f["date"])
        fresh = f[f["year"].isin(FRESH_Y)]
        m = metrics(fresh["net"].to_numpy(float),
                    fresh["date"].dt.to_period("M").nunique())
        m["por_anio"] = {
            int(y): metrics(g["net"].to_numpy(float),
                            g["date"].dt.to_period("M").nunique())
            for y, g in fresh.groupby("year")}
        results[i] = m
        f.to_csv(OUT / f"STAGE1_{i}_TRADES.csv", index=False)

    es = results["ES"]
    pos = sum(1 for v in es["por_anio"].values()
              if v.get("ev_net") is not None and v["ev_net"] > 0)
    gates = {"E1_ev_net_pos": bool(es.get("ev_net", 0) > 0),
             "E2_anios_pos_ge2": bool(pos >= 2),
             "E3_pf_gt_115": bool(es.get("pf") is not None
                                  and es["pf"] > E3_PF)}
    res = {
        "etapa": 1, "prereg_sha256": PREREG_SHA, "coste_usd": 0.0,
        "mediana_OR_ticks_DEV": {k: round(v, 2) for k, v in med.items()},
        "k_ES": round(k_es, 4),
        "params_ES_escalados": {"SL": sl, "ACT": act, "DIST": dist},
        "NQ_referencia_FRESH": results["NQ"], "ES_FRESH": es,
        "gates": gates,
        "VERDICT": "PASS" if all(gates.values()) else "FAIL",
        "consecuencia": ("PASS -> autorizada descarga YM+RTY (~$139.29); "
                         "FAIL -> edge NQ-especifico, no se descarga nada"),
    }
    (OUT / "STAGE1_RESULT.json").write_text(json.dumps(res, indent=2),
                                            encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
