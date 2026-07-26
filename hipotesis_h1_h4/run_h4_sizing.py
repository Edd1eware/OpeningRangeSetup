"""H4 - dynamic sizing (kill-switch base-4c) under Lucid 150k rules.

Frozen by PREREGISTRO_H1_H4.md. Base = surviving base (H1 and H2 both failed
-> both directions). Monte Carlo over shuffled FRESH trades.

Gate: H4-G1 payouts esperados > 0.5 | H4-G2 P(quema antes de payout) < 50%
      H4-G3 supera al sizing fijo equivalente
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
PREREG_SHA = "f5fa1d4b4383fdd871b7667db78f24d14f7eac20219739cdc5e649c469182438"

COMMISSION_TICKS = 2.0
TICK_VALUE = 5.0            # NQ: USD 5 per tick per contract
FRESH_Y = {2024, 2025, 2026}

# Lucid 150k (frozen in memory: lucid_150k_rules)
TARGET = 9000.0
MAXLOSS_EOD = 4500.0
DLL_SOFT = 2700.0
BASE_CONTRACTS = 4          # kill-switch base-4c
MIN_CONTRACTS = 1
N_ACCOUNTS = 10000
TRADES_PER_DAY = 1          # one OR breakout per session
MAX_DAYS = 250

# H4 gate
G1_PAYOUTS, G2_BURN = 0.5, 0.50


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as s:
        for chunk in iter(lambda: s.read(1 << 20), b""):
            d.update(chunk)
    return d.hexdigest()


def simulate(pool_ticks: np.ndarray, dynamic: bool, rng: np.random.Generator):
    """One account until burn or MAX_DAYS. Returns (payouts, burned)."""
    equity = 0.0
    peak = 0.0
    payouts = 0
    contracts = BASE_CONTRACTS
    consec_losses = 0
    for _day in range(MAX_DAYS):
        day_start = equity
        for _t in range(TRADES_PER_DAY):
            ticks = rng.choice(pool_ticks) - COMMISSION_TICKS
            equity += ticks * TICK_VALUE * contracts
            if dynamic:
                # kill-switch: shrink after losses, restore on a win
                if ticks < 0:
                    consec_losses += 1
                    if consec_losses >= 2:
                        contracts = max(MIN_CONTRACTS, contracts - 1)
                else:
                    consec_losses = 0
                    contracts = BASE_CONTRACTS
        peak = max(peak, equity)
        # trailing drawdown limit (MaxLoss from peak) and EOD daily loss
        if equity <= peak - MAXLOSS_EOD or (day_start - equity) >= MAXLOSS_EOD:
            return payouts, True
        if equity >= TARGET:
            payouts += 1
            equity = 0.0        # payout taken, account resets its buffer
            peak = 0.0
            contracts = BASE_CONTRACTS
    return payouts, False


def run(pool: np.ndarray, dynamic: bool, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    payouts = np.empty(N_ACCOUNTS)
    burned = np.empty(N_ACCOUNTS, dtype=bool)
    label = "dinamico" if dynamic else "fijo"
    for i in track(range(N_ACCOUNTS), label=f"MC sizing {label}"):
        p, b = simulate(pool, dynamic, rng)
        payouts[i], burned[i] = p, b
    return {
        "payouts_esperados": round(float(payouts.mean()), 4),
        "p_cero_payouts": round(float((payouts == 0).mean()), 4),
        "p_quema": round(float(burned.mean()), 4),
        "p_quema_sin_payout": round(
            float((burned & (payouts == 0)).mean()), 4),
        "payouts_p50": float(np.percentile(payouts, 50)),
        "payouts_p95": float(np.percentile(payouts, 95)),
    }


def main() -> int:
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    if sha256_file(BASE / "PREREGISTRO_H1_H4.md") != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")

    feat = pd.read_csv(SRC / "orb_features_labels_1s.csv")
    pnl = pd.read_csv(SRC / "orb_trailing_pnl.csv")
    data = pnl.merge(feat[["date"]], on="date", how="left")
    data["date"] = pd.to_datetime(data["date"])
    data["year"] = data["date"].dt.year
    fresh = data[data["year"].isin(FRESH_Y)]
    pool = fresh["trail_50_20_40"].to_numpy(dtype=float)   # both directions

    dyn = run(pool, True, 20260725)
    fix = run(pool, False, 20260725)
    gates = {
        "H4_G1_payouts_gt_05": bool(dyn["payouts_esperados"] > G1_PAYOUTS),
        "H4_G2_quema_sin_payout_lt_50": bool(
            dyn["p_quema_sin_payout"] < G2_BURN),
        "H4_G3_supera_fijo": bool(
            dyn["payouts_esperados"] > fix["payouts_esperados"]),
    }
    result = {
        "hipotesis": "H4", "titulo": "Sizing dinamico kill-switch base-4c",
        "base_usada": "ambas direcciones (H1 y H2 fallaron)",
        "pool_ev_neto_ticks": round(float(pool.mean() - COMMISSION_TICKS), 3),
        "n_pool": int(pool.size), "n_cuentas": N_ACCOUNTS,
        "reglas": {"target": TARGET, "maxloss": MAXLOSS_EOD,
                   "dll_soft": DLL_SOFT, "base_contratos": BASE_CONTRACTS},
        "dinamico": dyn, "fijo": fix,
        "gates": gates,
        "VERDICT": "PASS" if all(gates.values()) else "FAIL",
        "elapsed_s": round(time.time() - t0, 1),
    }
    (OUT / "H4_RESULT.json").write_text(json.dumps(result, indent=2),
                                        encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
