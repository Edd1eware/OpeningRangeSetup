"""BRACKET-120/55-V1 Parte A - caracterizacion (NO validatoria).

Frozen by PREREGISTRO_BRACKET_12055.md (SHA-256 c756e20b...).
A1: DEV 2022-23 (unseen for this config). A2: half-year stability.
A3: Monte Carlo under Lucid 150k rules.
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
LABELS = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\orcb_v2"
              r"\output\ORCB_V2_LABELS.csv")
PREREG_SHA = "c756e20baafacbfd82ec63dad670baea8ccbb9d251ec7572a3a1358f49709c54"

TP_T, SL_T, COMMISSION, TICK_USD = 120, 55, 2.0, 5.0
DEV_Y = {2022, 2023}
TARGET, MAXLOSS = 9000.0, 4500.0
BASE_C, MIN_C, N_ACC, MAX_DAYS = 4, 1, 10000, 250
SEED = 0x22f9cadf098b1625
A1_PF, A2_FRAC, A2_SHARE, A3_PAY, A3_BURN = 1.15, 0.60, 0.50, 0.5, 0.50


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


def simulate(pool: np.ndarray, per_day: float, rng) -> tuple[int, bool]:
    equity = peak = 0.0
    payouts, contracts, losses = 0, BASE_C, 0
    for _ in range(MAX_DAYS):
        start = equity
        for _ in range(max(int(rng.poisson(per_day)), 0)):
            t = rng.choice(pool)
            equity += t * TICK_USD * contracts
            if t < 0:
                losses += 1
                if losses >= 2:
                    contracts = max(MIN_C, contracts - 1)
            else:
                losses, contracts = 0, BASE_C
            peak = max(peak, equity)
            if equity <= peak - MAXLOSS:
                return payouts, True
        if (start - equity) >= MAXLOSS:
            return payouts, True
        if equity >= TARGET:
            payouts += 1
            equity = peak = 0.0
            contracts = BASE_C
    return payouts, False


def main() -> int:
    OUT.mkdir(exist_ok=True)
    if sha256_file(BASE / "PREREGISTRO_BRACKET_12055.md") != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")

    d = pd.read_csv(LABELS)
    d["date"] = pd.to_datetime(d["date"])
    d["year"] = d["date"].dt.year
    d["net"] = np.where(d["y120"] == 1, TP_T, -SL_T) - COMMISSION

    # A1 - DEV, unseen for this configuration
    dev = d[d["year"].isin(DEV_Y)]
    a1 = metrics(dev["net"].to_numpy(float),
                 dev["date"].dt.to_period("M").nunique())
    a1["por_anio"] = {int(y): metrics(g["net"].to_numpy(float),
                                      g["date"].dt.to_period("M").nunique())
                      for y, g in dev.groupby("year")}
    a1_pass = {"A1_C1_ev_pos": bool(a1.get("ev_net", 0) > 0),
               "A1_C2_pf_gt_115": bool(a1.get("pf") is not None
                                       and a1["pf"] > A1_PF)}

    # A2 - half-year stability over the whole period
    d["w"] = (d["date"].dt.year.astype(str) + "-H"
              + ((d["date"].dt.month > 6).astype(int) + 1).astype(str))
    wins = []
    for w, s in d.groupby("w"):
        x = s["net"].to_numpy(float)
        wins.append({"ventana": w, "n": int(x.size),
                     "ev_net": round(float(x.mean()), 3),
                     "pnl": round(float(x.sum()), 1)})
    total = sum(v["pnl"] for v in wins)
    pos = sum(1 for v in wins if v["ev_net"] > 0)
    shares = [abs(v["pnl"]) / abs(total) if total else 0 for v in wins]
    a2_pass = {"A2_C1_60pct_pos": bool(pos / len(wins) >= A2_FRAC),
               "A2_C2_sin_ventana_dominante":
                   bool(max(shares) <= A2_SHARE)}

    # A3 - Monte Carlo, whole period
    pool = d["net"].to_numpy(float)
    per_day = len(d) / d["date"].dt.date.nunique()
    rng = np.random.default_rng(SEED)
    pay = np.empty(N_ACC)
    burn = np.empty(N_ACC, dtype=bool)
    for i in track(range(N_ACC), label="MC bracket 120/55"):
        pay[i], burn[i] = simulate(pool, per_day, rng)
    a3 = {"payouts_esperados": round(float(pay.mean()), 4),
          "p_quema": round(float(burn.mean()), 4),
          "p_quema_sin_payout": round(float((burn & (pay == 0)).mean()), 4),
          "payouts_p95": float(np.percentile(pay, 95)),
          "entradas_por_dia": round(per_day, 3)}
    a3_pass = {"A3_C1_payouts_gt_05": bool(a3["payouts_esperados"] > A3_PAY),
               "A3_C2_quema_sin_payout_lt50":
                   bool(a3["p_quema_sin_payout"] < A3_BURN)}

    checks = {**a1_pass, **a2_pass, **a3_pass}
    res = {"estudio": "BRACKET-120/55-V1 Parte A",
           "prereg_sha256": PREREG_SHA,
           "nota": "caracterizacion, NO validacion; FRESH 2024-26 esta quemado",
           "breakeven_wr_pct": round(100 * SL_T / (TP_T + SL_T), 2),
           "A1_DEV_2022_2023": a1, "A2_ventanas": wins,
           "A2_frac_positivas": round(pos / len(wins), 3),
           "A2_max_share": round(max(shares), 3),
           "A3_monte_carlo": a3, "checks": checks,
           "VERDICT_PARTE_A": "PASS" if all(checks.values()) else "FAIL",
           "contexto_ya_visto_FRESH": {
               "n": 402, "trades_mes": 18.27, "wr": 34.83,
               "pf": 1.106, "ev_net": 3.945,
               "aviso": "no otorga PASS, solo contexto"}}
    (OUT / "BRACKET_PARTE_A.json").write_text(json.dumps(res, indent=2),
                                              encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
