"""UPBIAS-V2 Parte A - caracterizacion del sesgo UP (NO validatoria).

Frozen by PREREGISTRO_UPBIAS_V2.md (SHA-256 80d219ba...).
A1: survives management choice?  A2: survives across time?  A3: sizing on a
positive base (the question H4 never answered).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from progress import track

BASE = Path(__file__).resolve().parent
SRC = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")
OUT = BASE / "output"
PREREG_SHA = "80d219ba25ae585773f49ffefd9e2ec88cd5750d00dbb4bff70037b2f138181f"

COMMISSION = 2.0
TICK_VALUE = 5.0
FRESH_Y = {2024, 2025, 2026}
CONFIGS = ["trail_50_20_40", "trail_50_30_50", "trail_50_20_30",
           "trail_40_20_40", "trail_30_20_30", "trail_60_30_50",
           "fixed_60_60", "fixed_60_30"]
FORWARD_CONFIG = "trail_50_20_40"

# Lucid 150k
TARGET, MAXLOSS, DLL = 9000.0, 4500.0, 2700.0
BASE_CONTRACTS, MIN_CONTRACTS = 4, 1
N_ACCOUNTS, MAX_DAYS = 10000, 250

# frozen criteria
A1_C1_MIN, A1_C2_MIN = 7, 6
A2_C1_FRAC, A2_C2_MAX_SHARE = 0.60, 0.50
A3_PAYOUTS, A3_BURN = 0.5, 0.50


def sha256_file(p: Path) -> str:
    d = hashlib.sha256()
    with p.open("rb") as s:
        for c in iter(lambda: s.read(1 << 20), b""):
            d.update(c)
    return d.hexdigest()


def ev_net(x: np.ndarray) -> float:
    return float((x - COMMISSION).mean()) if x.size else float("nan")


def pf(x: np.ndarray) -> float:
    n = x - COMMISSION
    gl = -n[n < 0].sum()
    return float(n[n > 0].sum() / gl) if gl > 0 else float("inf")


def load() -> pd.DataFrame:
    p = pd.read_csv(SRC / "orb_trailing_pnl.csv")
    p["date"] = pd.to_datetime(p["date"])
    return p.sort_values("date").reset_index(drop=True)


def run_a1(data: pd.DataFrame) -> dict:
    rows = []
    up = data[data["direction"] == "UP"]
    dn = data[data["direction"] == "DOWN"]
    for c in CONFIGS:
        u, d = up[c].to_numpy(float), dn[c].to_numpy(float)
        rows.append({"config": c, "ev_net_UP": round(ev_net(u), 3),
                     "ev_net_DOWN": round(ev_net(d), 3),
                     "pf_UP": round(pf(u), 3),
                     "UP_gt_DOWN": bool(ev_net(u) > ev_net(d)),
                     "UP_pos": bool(ev_net(u) > 0)})
    n_gt = sum(r["UP_gt_DOWN"] for r in rows)
    n_pos = sum(r["UP_pos"] for r in rows)
    return {"detalle": rows, "n_UP_gt_DOWN": n_gt, "n_UP_positivo": n_pos,
            "A1_C1_pass": bool(n_gt >= A1_C1_MIN),
            "A1_C2_pass": bool(n_pos >= A1_C2_MIN)}


def run_a2(data: pd.DataFrame) -> dict:
    up = data[data["direction"] == "UP"].copy()
    up["win"] = up["date"].dt.to_period("Q")
    # 6-month windows = pairs of quarters
    up["w"] = up["date"].dt.year.astype(str) + "-H" + \
        ((up["date"].dt.month > 6).astype(int) + 1).astype(str)
    rows = []
    for w, sub in up.groupby("w"):
        x = sub[FORWARD_CONFIG].to_numpy(float)
        rows.append({"ventana": w, "n": int(x.size),
                     "ev_net": round(ev_net(x), 3),
                     "pnl_total": round(float((x - COMMISSION).sum()), 1)})
    total = sum(r["pnl_total"] for r in rows)
    pos = sum(1 for r in rows if r["ev_net"] > 0)
    shares = [abs(r["pnl_total"]) / abs(total) if total else 0 for r in rows]
    return {"ventanas": rows, "n_ventanas": len(rows), "n_positivas": pos,
            "frac_positivas": round(pos / max(len(rows), 1), 3),
            "max_share_pnl": round(max(shares) if shares else 0, 3),
            "A2_C1_pass": bool(pos / max(len(rows), 1) >= A2_C1_FRAC),
            "A2_C2_pass": bool((max(shares) if shares else 0)
                               <= A2_C2_MAX_SHARE)}


def simulate(pool: np.ndarray, dynamic: bool, rng) -> tuple[int, bool]:
    equity = peak = 0.0
    payouts, contracts, losses = 0, BASE_CONTRACTS, 0
    for _ in range(MAX_DAYS):
        start = equity
        t = rng.choice(pool) - COMMISSION
        equity += t * TICK_VALUE * contracts
        if dynamic:
            if t < 0:
                losses += 1
                if losses >= 2:
                    contracts = max(MIN_CONTRACTS, contracts - 1)
            else:
                losses, contracts = 0, BASE_CONTRACTS
        peak = max(peak, equity)
        if equity <= peak - MAXLOSS or (start - equity) >= MAXLOSS:
            return payouts, True
        if equity >= TARGET:
            payouts += 1
            equity = peak = 0.0
            contracts = BASE_CONTRACTS
    return payouts, False


def run_mc(pool: np.ndarray, dynamic: bool, seed: int, label: str) -> dict:
    rng = np.random.default_rng(seed)
    pay = np.empty(N_ACCOUNTS)
    burn = np.empty(N_ACCOUNTS, dtype=bool)
    for i in track(range(N_ACCOUNTS), label=f"MC {label}"):
        pay[i], burn[i] = simulate(pool, dynamic, rng)
    return {"payouts_esperados": round(float(pay.mean()), 4),
            "p_quema": round(float(burn.mean()), 4),
            "p_quema_sin_payout": round(float((burn & (pay == 0)).mean()), 4),
            "payouts_p95": float(np.percentile(pay, 95))}


def main() -> int:
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    if sha256_file(BASE / "PREREGISTRO_UPBIAS_V2.md") != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")
    data = load()

    a1 = run_a1(data)
    a2 = run_a2(data)

    fresh_up = data[(data["date"].dt.year.isin(FRESH_Y))
                    & (data["direction"] == "UP")]
    pool = fresh_up[FORWARD_CONFIG].to_numpy(float)
    dyn = run_mc(pool, True, 20260725, "dinamico")
    fix = run_mc(pool, False, 20260725, "fijo")
    a3 = {"pool_ev_neto": round(ev_net(pool), 3), "n_pool": int(pool.size),
          "dinamico": dyn, "fijo": fix,
          "A3_C1_pass": bool(dyn["payouts_esperados"] > A3_PAYOUTS),
          "A3_C2_pass": bool(dyn["p_quema_sin_payout"] < A3_BURN),
          "A3_C3_pass": bool(dyn["payouts_esperados"]
                             > fix["payouts_esperados"])}

    checks = {
        "A1_C1_UP_gt_DOWN_7de8": a1["A1_C1_pass"],
        "A1_C2_UP_pos_6de8": a1["A1_C2_pass"],
        "A2_C1_60pct_ventanas_pos": a2["A2_C1_pass"],
        "A2_C2_ninguna_ventana_gt50pct": a2["A2_C2_pass"],
        "A3_C1_payouts_gt_05": a3["A3_C1_pass"],
        "A3_C2_quema_sin_payout_lt50": a3["A3_C2_pass"],
        "A3_C3_dinamico_gt_fijo": a3["A3_C3_pass"],
    }
    verdict = "PASS" if all(checks.values()) else "FAIL"
    result = {"parte": "A", "titulo": "Caracterizacion sesgo UP (NO validatoria)",
              "prereg_sha256": PREREG_SHA, "A1": a1, "A2": a2, "A3": a3,
              "checks": checks, "VERDICT_PARTE_A": verdict,
              "significado": ("PASS solo autoriza correr la Parte B forward; "
                              "NO valida el edge"),
              "elapsed_s": round(time.time() - t0, 1)}
    (OUT / "PARTE_A_RESULT.json").write_text(json.dumps(result, indent=2),
                                             encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
