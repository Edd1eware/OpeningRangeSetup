"""LUCID100K-V1 - can fixed 60/60 UP-only pass a Lucid 100k evaluation?

Frozen by PREREGISTRO_LUCID100K_V1.md (SHA-256 372249ff...).
Primary metric: P(pass) per attempt. Single shot on FRESH 2024-2026.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from progress import track

BASE = Path(__file__).resolve().parent
OUT = BASE / "output"
SRC = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")
PREREG_SHA = "372249ff507fda8da2637c8cd1a0225526da158fe168938306d545b96394b1d8"

PNL_COL = "fixed_60_60"
COMMISSION, TICK_USD, CONTRACTS = 2.0, 5.0, 2
TARGET, MLL = 6000.0, 3000.0
N_ATTEMPTS, MAX_DAYS = 10000, 120
SEED = 0x22f9cadf098b1625
DEV_Y, FRESH_Y = {2022, 2023}, {2024, 2025, 2026}
BREAKEVEN_WR = 100 * 62 / 120          # 51.67 %
G3_PPASS, G4_YEARS = 0.30, 2


def sha256_file(p: Path) -> str:
    d = hashlib.sha256()
    with p.open("rb") as s:
        for c in iter(lambda: s.read(1 << 20), b""):
            d.update(c)
    return d.hexdigest()


def metrics(net: np.ndarray, months: int) -> dict:
    if net.size == 0:
        return {"trades": 0}
    gl = -net[net < 0].sum()
    return {"trades": int(net.size),
            "trades_mes": round(net.size / max(months, 1), 2),
            "wr": round(float((net > 0).mean() * 100), 2),
            "pf": round(float(net[net > 0].sum() / gl), 3) if gl > 0 else None,
            "ev_net": round(float(net.mean()), 3)}


def block(df: pd.DataFrame) -> dict:
    m = df["date"].dt.to_period("M").nunique() if len(df) else 1
    out = metrics(df["net"].to_numpy(float), m)
    out["por_anio"] = {int(y): metrics(g["net"].to_numpy(float),
                                       g["date"].dt.to_period("M").nunique())
                       for y, g in df.groupby("year")}
    return out


def attempt(pool_usd: np.ndarray, rng) -> str:
    """One evaluation attempt: PASS, BURN or TIMEOUT."""
    equity = peak = 0.0
    for _ in range(MAX_DAYS):
        equity += rng.choice(pool_usd)
        peak = max(peak, equity)
        if equity <= peak - MLL:
            return "BURN"
        if equity >= TARGET:
            return "PASS"
    return "TIMEOUT"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    if sha256_file(BASE / "PREREGISTRO_LUCID100K_V1.md") != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")

    d = pd.read_csv(SRC / "orb_trailing_pnl.csv")
    d["date"] = pd.to_datetime(d["date"])
    d["year"] = d["date"].dt.year
    up = d[d["direction"] == "UP"].copy()
    up["net"] = up[PNL_COL] - COMMISSION

    dev = up[up["year"].isin(DEV_Y)]
    fresh = up[up["year"].isin(FRESH_Y)]
    dev_b, fresh_b = block(dev), block(fresh)

    pool_usd = fresh["net"].to_numpy(float) * TICK_USD * CONTRACTS
    rng = np.random.default_rng(SEED)
    outcomes = []
    for _ in track(range(N_ATTEMPTS), label="MC evaluacion Lucid 100k"):
        outcomes.append(attempt(pool_usd, rng))
    arr = np.array(outcomes)
    p_pass = float((arr == "PASS").mean())
    mc = {"P_pass": round(p_pass, 4),
          "P_burn": round(float((arr == "BURN").mean()), 4),
          "P_timeout": round(float((arr == "TIMEOUT").mean()), 4),
          "intentos_esperados_para_pasar":
              round(1 / p_pass, 2) if p_pass > 0 else None,
          "contratos": CONTRACTS, "target": TARGET, "mll": MLL,
          "max_dias": MAX_DAYS}

    pos = sum(1 for v in fresh_b["por_anio"].values()
              if v.get("ev_net") is not None and v["ev_net"] > 0)
    gates = {
        "G1_ev_net_pos": bool(fresh_b.get("ev_net", 0) > 0),
        "G2_wr_gt_breakeven": bool(fresh_b.get("wr", 0) > BREAKEVEN_WR),
        "G3_ppass_ge_30": bool(p_pass >= G3_PPASS),
        "G4_anios_pos_ge2": bool(pos >= G4_YEARS),
    }
    res = {"estudio": "LUCID100K-V1", "prereg_sha256": PREREG_SHA,
           "regla": "primer breakout OR, SOLO UP, bracket fijo 60/60 (RR 1:1)",
           "breakeven_wr_pct": round(BREAKEVEN_WR, 2),
           "DEV_2022_2023": dev_b, "FRESH_2024_2026": fresh_b,
           "monte_carlo_evaluacion": mc, "gates": gates,
           "VERDICT": "PASS" if all(gates.values()) else "FAIL"}
    (OUT / "LUCID100K_RESULT.json").write_text(json.dumps(res, indent=2),
                                               encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
