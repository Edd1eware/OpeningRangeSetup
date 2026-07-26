"""LUCID100K-V2 - RR 1:1 bracket family, era-blind design selection.

Frozen by PREREGISTRO_LUCID100K_V2.md (SHA-256 c63857a8...).
Selection of (bracket, size) happens ONLY on DEV. FRESH decides once.
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
PREREG_SHA = "c63857a8e6fc3198c739920566af8e2f0bd195730ef8a36bb652ad91b8952473"

TICK, TICK_USD, COMMISSION = 0.25, 5.0, 2.0
OR_START, OR_END, SCAN_START = "13:30:00", "13:31:00", "13:31:00"
BRACKETS = [40, 60, 80, 100]
SIZES = [1, 2, 3]
TARGET, MLL, MAX_DAYS, N_ATT = 6000.0, 3000.0, 120, 10000
SEED = 0x22f9cadf098b1625
DEV_Y, FRESH_Y = {2022, 2023}, {2024, 2025, 2026}
G1_PPASS, G4_YEARS = 0.30, 2


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
        ["open", "high", "low", "close"]].sort_index()


def up_breakout_outcomes(date: str):
    """First UP breakout; outcome for every RR-1 bracket. Pessimistic ties."""
    df = load_session(date)
    if df is None or df.empty:
        return None
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
    if t_up is None:
        return None
    if t_dn is not None and t_dn < t_up:
        return None                       # DOWN first -> not our trade
    fwd = post.loc[post.index >= t_up]
    entry = or_high
    highs, lows = fwd["high"].to_numpy(), fwd["low"].to_numpy()
    row = {"date": date}
    for b in BRACKETS:
        tp, sl = entry + b * TICK, entry - b * TICK
        res = None
        for h, l in zip(highs, lows):
            if l <= sl:
                res = -b
                break
            if h >= tp:
                res = b
                break
        row[f"b{b}"] = res if res is not None else 0.0   # EOD -> flat
    return row


def attempt(pool_usd: np.ndarray, rng) -> bool:
    equity = peak = 0.0
    for _ in range(MAX_DAYS):
        equity += rng.choice(pool_usd)
        peak = max(peak, equity)
        if equity <= peak - MLL:
            return False
        if equity >= TARGET:
            return True
    return False


def p_pass(net_ticks: np.ndarray, size: int, seed: int) -> float:
    pool = net_ticks * TICK_USD * size
    rng = np.random.default_rng(seed)
    return float(np.mean([attempt(pool, rng) for _ in range(N_ATT)]))


def metrics(net: np.ndarray, months: int, tp: int) -> dict:
    if net.size == 0:
        return {"trades": 0}
    gl = -net[net < 0].sum()
    return {"trades": int(net.size),
            "trades_mes": round(net.size / max(months, 1), 2),
            "wr": round(float((net > 0).mean() * 100), 2),
            "breakeven_wr": round(100 * (tp + COMMISSION) / (2 * tp), 2),
            "pf": round(float(net[net > 0].sum() / gl), 3) if gl > 0 else None,
            "ev_net": round(float(net.mean()), 3)}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    if sha256_file(BASE / "PREREGISTRO_LUCID100K_V2.md") != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")

    lab = OUT / "RR1_LABELS.csv"
    if lab.exists():
        d = pd.read_csv(lab)
    else:
        dates = sorted(p.name for p in DBN_ROOT.iterdir() if p.is_dir())
        rows = []
        for dt in track(dates, label="brackets RR 1:1"):
            try:
                r = up_breakout_outcomes(dt)
            except Exception:  # noqa: BLE001
                r = None
            if r:
                rows.append(r)
        d = pd.DataFrame(rows)
        d.to_csv(lab, index=False)

    d["date"] = pd.to_datetime(d["date"])
    d["year"] = d["date"].dt.year
    dev = d[d["year"].isin(DEV_Y)]
    fresh = d[d["year"].isin(FRESH_Y)]

    # ---- selection ON DEV ONLY
    grid = []
    for b in BRACKETS:
        net_dev = dev[f"b{b}"].to_numpy(float) - COMMISSION
        for s in SIZES:
            grid.append({"tp": b, "size": s,
                         "p_pass_dev": round(p_pass(net_dev, s, SEED), 4)})
    grid_df = pd.DataFrame(grid).sort_values(
        ["p_pass_dev", "size", "tp"], ascending=[False, True, True])
    win = grid_df.iloc[0]
    tp_w, size_w = int(win["tp"]), int(win["size"])

    # ---- FRESH: single shot with the frozen choice
    net_fresh = fresh[f"b{tp_w}"].to_numpy(float) - COMMISSION
    months = fresh["date"].dt.to_period("M").nunique()
    m = metrics(net_fresh, months, tp_w)
    per_year = {}
    for y, g in fresh.groupby("year"):
        nn = g[f"b{tp_w}"].to_numpy(float) - COMMISSION
        per_year[int(y)] = metrics(nn, g["date"].dt.to_period("M").nunique(),
                                   tp_w)
    pp = p_pass(net_fresh, size_w, SEED)
    pos = sum(1 for v in per_year.values()
              if v.get("ev_net") is not None and v["ev_net"] > 0)
    gates = {"G1_ppass_ge_30": bool(pp >= G1_PPASS),
             "G2_ev_net_pos": bool(m.get("ev_net", 0) > 0),
             "G3_wr_gt_breakeven": bool(m.get("wr", 0) > m.get("breakeven_wr",
                                                               100)),
             "G4_anios_pos_ge2": bool(pos >= G4_YEARS)}
    res = {"estudio": "LUCID100K-V2", "prereg_sha256": PREREG_SHA,
           "seleccion_en_DEV": grid_df.to_dict(orient="records"),
           "combinacion_congelada": {"TP_SL_ticks": tp_w,
                                     "contratos": size_w,
                                     "p_pass_dev": float(win["p_pass_dev"])},
           "FRESH_metricas": m, "FRESH_por_anio": per_year,
           "FRESH_P_pass": round(pp, 4),
           "intentos_esperados": round(1 / pp, 2) if pp > 0 else None,
           "gates": gates,
           "VERDICT": "PASS" if all(gates.values()) else "FAIL"}
    (OUT / "LUCID100K_V2_RESULT.json").write_text(json.dumps(res, indent=2),
                                                  encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
