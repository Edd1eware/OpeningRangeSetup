"""MULTIENTRY-V1 - attack edge magnitude via frequency.

Frozen by PREREGISTRO_MULTIENTRY_V1.md (SHA-256 a784adf3...).
Anti-absorption threshold from DEV only (fixes the full-sample defect of the
original script). Single shot on FRESH.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from progress import track

BASE = Path(__file__).resolve().parent
SRC = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")
OUT = BASE / "output"
PREREG_SHA = "a784adf35c6fca236489b9d167a22b4259ec5b80085afd3f3058e659eed32bf7"

COMMISSION, TICK_USD = 2.0, 5.0
DEV_Y, FRESH_Y = {2022, 2023}, {2024, 2025, 2026}
TARGET, MAXLOSS = 9000.0, 4500.0
BASE_C, MIN_C = 4, 1
N_ACC, MAX_DAYS = 10000, 250
SEED = 0x22f9cadf098b1625

G2_PF, G4_TPM, G5_PAY, G6_BURN = 1.15, 20.0, 0.5, 0.50


def sha256_file(p: Path) -> str:
    d = hashlib.sha256()
    with p.open("rb") as s:
        for c in iter(lambda: s.read(1 << 20), b""):
            d.update(c)
    return d.hexdigest()


def metrics(net_ticks: np.ndarray, months: int) -> dict:
    if net_ticks.size == 0:
        return {"trades": 0}
    n = net_ticks
    gl = -n[n < 0].sum()
    return {"trades": int(n.size),
            "trades_mes": round(n.size / max(months, 1), 2),
            "wr": round(float((n > 0).mean() * 100), 2),
            "pf": round(float(n[n > 0].sum() / gl), 3) if gl > 0 else None,
            "ev_net": round(float(n.mean()), 3)}


def block(df: pd.DataFrame) -> dict:
    m = df["date"].dt.to_period("M").nunique() if len(df) else 1
    out = metrics(df["net_ticks"].to_numpy(float), m)
    out["por_anio"] = {
        int(y): metrics(s["net_ticks"].to_numpy(float),
                        s["date"].dt.to_period("M").nunique())
        for y, s in df.groupby("year")}
    return out


def simulate(pool: np.ndarray, per_day: float, rng) -> tuple[int, bool]:
    equity = peak = 0.0
    payouts, contracts, losses = 0, BASE_C, 0
    for _ in range(MAX_DAYS):
        start = equity
        k = rng.poisson(per_day)
        for _ in range(max(int(k), 0)):
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


def run_mc(pool: np.ndarray, per_day: float, label: str) -> dict:
    rng = np.random.default_rng(SEED)
    pay = np.empty(N_ACC)
    burn = np.empty(N_ACC, dtype=bool)
    for i in track(range(N_ACC), label=f"MC {label}"):
        pay[i], burn[i] = simulate(pool, per_day, rng)
    return {"payouts_esperados": round(float(pay.mean()), 4),
            "p_quema": round(float(burn.mean()), 4),
            "p_quema_sin_payout": round(float((burn & (pay == 0)).mean()), 4),
            "payouts_p95": float(np.percentile(pay, 95))}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    if sha256_file(BASE / "PREREGISTRO_MULTIENTRY_V1.md") != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")

    d = pd.read_csv(SRC / "orb_multientry.csv")
    d["date"] = pd.to_datetime(d["date"])
    d["year"] = d["date"].dt.year
    d["net_ticks"] = d["net"] - COMMISSION

    dev = d[d["year"].isin(DEV_Y)]
    thr = float(dev["vpt"].quantile(2 / 3))          # DEV ONLY
    d["keep"] = d["vpt"] <= thr

    fresh = d[d["year"].isin(FRESH_Y)]
    fresh_f = fresh[fresh["keep"]]
    dev_f = dev[dev["vpt"] <= thr]

    b = block(fresh_f)
    pos_years = sum(1 for v in b["por_anio"].values()
                    if v.get("ev_net") is not None and v["ev_net"] > 0)
    per_day = len(fresh_f) / fresh_f["date"].dt.date.nunique()
    pool = fresh_f["net_ticks"].to_numpy(float)
    mc = run_mc(pool, per_day, "multientry")

    gates = {
        "G1_ev_net_pos": bool(b.get("ev_net") is not None and b["ev_net"] > 0),
        "G2_pf_gt_115": bool(b.get("pf") is not None and b["pf"] > G2_PF),
        "G3_anios_pos_ge2": bool(pos_years >= 2),
        "G4_freq_ge_20_mes": bool(b.get("trades_mes", 0) >= G4_TPM),
        "G5_payouts_gt_05": bool(mc["payouts_esperados"] > G5_PAY),
        "G6_quema_sin_payout_lt50": bool(mc["p_quema_sin_payout"] < G6_BURN),
    }
    res = {
        "estudio": "MULTIENTRY-V1", "prereg_sha256": PREREG_SHA,
        "umbral_vpt_DEV_p66": round(thr, 4),
        "n_total": int(len(d)), "n_dev_filtrado": int(len(dev_f)),
        "n_fresh_sin_filtro": int(len(fresh)),
        "n_fresh_filtrado": int(len(fresh_f)),
        "entradas_por_dia_fresh": round(per_day, 2),
        "DEV_filtrado": block(dev_f),
        "FRESH_sin_filtro": block(fresh),
        "FRESH_filtrado": b,
        "monte_carlo": mc,
        "gates": gates,
        "VERDICT": "PASS" if all(gates.values()) else "FAIL",
    }
    (OUT / "MULTIENTRY_RESULT.json").write_text(
        json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
