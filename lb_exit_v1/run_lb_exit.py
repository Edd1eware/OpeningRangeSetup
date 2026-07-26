"""LB-EXIT-V1 - Liquidity Burst as an EXIT signal.

Frozen by PREREGISTRO_LB_EXIT_V1.md (SHA-256 d105142b...).
Trade reconstruction copied verbatim from the frozen orb_trailing_sim.py logic.
Paired comparison on trades where the LB fires while the position is open.
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
DBN_ROOT = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
                r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_2")
VT = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
          r"\trade_results_score\visual_tests")
PREREG_SHA = "d105142b3a968f1a3afed8ea6ac08533ac4471bd04a3ed612717b085eeb4156d"

TICK = 0.25
COMMISSION = 2.0
OR_START, OR_END, SCAN_START = "13:30:00", "13:31:00", "13:31:00"
SL, ACT, DIST = 50, 20, 40
SEED, N_BOOT = 0x22f9cadf098b1625, 10000
G1_MIN, G4_MIN_N = 2.0, 40
PRIMARY_YEARS = {2022, 2023, 2024}


def sha256_file(p: Path) -> str:
    d = hashlib.sha256()
    with p.open("rb") as s:
        for c in iter(lambda: s.read(1 << 20), b""):
            d.update(c)
    return d.hexdigest()


def load_session(date: str):
    hits = glob.glob(str(DBN_ROOT / date / "ohlcv-1s-full" / "*.dbn.zst"))
    if not hits:
        return None
    return db.DBNStore.from_file(hits[0]).to_df()[
        ["open", "high", "low", "close", "volume"]].sort_index()


def find_breakout(df: pd.DataFrame):
    day = df.index[0].strftime("%Y-%m-%d")
    orw = df.between_time(OR_START, OR_END, inclusive="left")
    if orw.empty:
        return None
    or_high, or_low = float(orw["high"].max()), float(orw["low"].min())
    post = df.loc[df.index >= pd.Timestamp(f"{day} {SCAN_START}", tz="UTC")]
    if post.empty:
        return None
    up = post.index[post["high"] > or_high]
    dn = post.index[post["low"] < or_low]
    t_up = up[0] if len(up) else None
    t_dn = dn[0] if len(dn) else None
    if t_up is None and t_dn is None:
        return None
    if t_dn is None or (t_up is not None and t_up <= t_dn):
        return "UP", or_high, 1, post.loc[post.index >= t_up]
    return "DOWN", or_low, -1, post.loc[post.index >= t_dn]


def trail_with_lb(fwd, entry, sign, t_lb):
    """Returns (pnl_hold, pnl_exit_lb, lb_was_open, exit_idx_hold).

    pnl_exit_lb is NaN when the LB does not fire while the position is open.
    Bar-by-bar rule identical to the frozen sim (stop carried from prior bar).
    """
    stop = entry - sign * SL * TICK
    best, activated, close = entry, False, entry
    idx = fwd.index
    highs, lows, closes = (fwd["high"].to_numpy(), fwd["low"].to_numpy(),
                           fwd["close"].to_numpy())
    pnl_lb, lb_open = np.nan, False
    for i, (h, l, c) in enumerate(zip(highs, lows, closes)):
        close = c
        # LB observed at the close of the bar containing t_lb, if still open
        if (t_lb is not None and np.isnan(pnl_lb) and idx[i] >= t_lb
                and idx[i] > idx[0]):
            pnl_lb = (c - entry) / TICK * sign
            lb_open = True
        if sign == 1 and l <= stop:
            return (stop - entry) / TICK, pnl_lb, lb_open, i
        if sign == -1 and h >= stop:
            return (entry - stop) / TICK, pnl_lb, lb_open, i
        best = max(best, h) if sign == 1 else min(best, l)
        if not activated and (best - entry) / TICK * sign >= ACT:
            activated = True
        if activated:
            new_stop = best - sign * DIST * TICK
            stop = max(stop, new_stop) if sign == 1 else min(stop, new_stop)
    return (close - entry) / TICK * sign, pnl_lb, lb_open, len(highs) - 1


def lb_first_times() -> dict:
    out: dict = {}
    for f in glob.glob(str(VT / "*lb*/observational/burst_events.csv")):
        d = pd.read_csv(f, usecols=["Timestamp_NY"])
        t = pd.to_datetime(d["Timestamp_NY"], errors="coerce", format="mixed")
        t = t.dropna()
        if t.empty:
            continue
        t = t.dt.tz_localize("America/New_York",
                             ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
        for day, v in t.groupby(t.dt.date).min().items():
            if day not in out or v < out[day]:
                out[day] = v
    return out


def boot_ci(diff: np.ndarray):
    rng = np.random.default_rng(SEED)
    stats = np.array([rng.choice(diff, diff.size, replace=True).mean()
                      for _ in range(N_BOOT)])
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def main() -> int:
    OUT.mkdir(exist_ok=True)
    if sha256_file(BASE / "PREREGISTRO_LB_EXIT_V1.md") != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")
    lb = lb_first_times()
    dates = sorted(p.name for p in DBN_ROOT.iterdir() if p.is_dir())
    rows = []
    for d in track(dates, label="LB-EXIT reconstruccion"):
        day = pd.to_datetime(d).date()
        if day not in lb:
            continue
        try:
            df = load_session(d)
            if df is None or df.empty:
                continue
            bo = find_breakout(df)
            if bo is None:
                continue
        except Exception:  # noqa: BLE001
            continue
        direction, entry, sign, fwd = bo
        hold, lbp, lb_open, _ = trail_with_lb(fwd, entry, sign, lb[day])
        rows.append({"date": d, "year": int(d[:4]), "direction": direction,
                     "t_entry": fwd.index[0].isoformat(),
                     "t_lb": lb[day].isoformat(),
                     "pnl_hold": hold, "pnl_exit_lb": lbp,
                     "lb_durante_trade": bool(lb_open)})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "LB_EXIT_TRADES.csv", index=False)

    aff = frame[frame["lb_durante_trade"] & frame["pnl_exit_lb"].notna()]
    prim = aff[aff["year"].isin(PRIMARY_YEARS)]
    conf = aff[~aff["year"].isin(PRIMARY_YEARS)]

    def summarize(sub: pd.DataFrame) -> dict:
        if sub.empty:
            return {"n": 0}
        d = (sub["pnl_exit_lb"] - sub["pnl_hold"]).to_numpy(float)
        return {"n": int(len(sub)),
                "ev_hold_neto": round(float(sub["pnl_hold"].mean()
                                            - COMMISSION), 3),
                "ev_exitlb_neto": round(float(sub["pnl_exit_lb"].mean()
                                              - COMMISSION), 3),
                "mejora_media": round(float(d.mean()), 3),
                "mejora_mediana": round(float(np.median(d)), 3),
                "pct_trades_mejorados": round(float((d > 0).mean() * 100), 1)}

    res_p = summarize(prim)
    per_year = {int(y): summarize(s) for y, s in prim.groupby("year")}
    gates, ci = {}, (None, None)
    if not prim.empty:
        diff = (prim["pnl_exit_lb"] - prim["pnl_hold"]).to_numpy(float)
        ci = boot_ci(diff)
        pos_years = sum(1 for v in per_year.values()
                        if v.get("mejora_media", 0) > 0)
        gates = {"G1_mejora_ge_2ticks": bool(diff.mean() >= G1_MIN),
                 "G2_ci95_excluye_0": bool(ci[0] > 0 or ci[1] < 0),
                 "G3_mejora_pos_2de3": bool(pos_years >= 2),
                 "G4_n_ge_40": bool(len(prim) >= G4_MIN_N)}
    verdict = "PASS" if gates and all(gates.values()) else "FAIL"
    result = {
        "estudio": "LB-EXIT-V1", "prereg_sha256": PREREG_SHA,
        "n_dias_con_LB_y_trade": int(len(frame)),
        "n_LB_durante_trade": int(len(aff)),
        "PRIMARIO_2022_2024": res_p, "por_anio": per_year,
        "ci95_mejora": [round(ci[0], 3) if ci[0] is not None else None,
                        round(ci[1], 3) if ci[1] is not None else None],
        "gates": gates, "VERDICT": verdict,
        "CONFIRMACION_2025_2026": summarize(conf),
        "nota": "comparacion pareada; 2025-26 es descriptivo, sin veredicto",
    }
    (OUT / "LB_EXIT_RESULT.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
