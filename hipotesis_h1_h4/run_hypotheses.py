"""Run hypothesis battery H1..H4 era-blind, single shot each.

Frozen by PREREGISTRO_H1_H4.md (SHA-256 f5fa1d4b...).
Chaining rule fixed in advance: each hypothesis after H1 applies on top of the
surviving base (H1's rule if H1 passed, else both directions).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
SRC = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")
OUT = BASE / "output"
COMMISSION = 2.0
PNL = "trail_50_20_40"
DEV_Y, FRESH_Y = {2022, 2023}, {2024, 2025, 2026}
PREREG_SHA = "f5fa1d4b4383fdd871b7667db78f24d14f7eac20219739cdc5e649c469182438"
BASELINE_FRESH_EV = -0.577          # published in CIERRE_EB_FILTER_V1_FAIL.md

# common gate
G2_PF, G3_YEARS, G4_TPM = 1.15, 2, 4.0


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as s:
        for chunk in iter(lambda: s.read(1 << 20), b""):
            d.update(chunk)
    return d.hexdigest()


def metrics(pnl: np.ndarray, months: int) -> dict:
    if pnl.size == 0:
        return {"trades": 0, "trades_mes": 0.0, "wr": None, "pf": None,
                "ev_gross": None, "ev_net": None}
    net = pnl - COMMISSION
    gw = net[net > 0].sum()
    gl = -net[net < 0].sum()
    return {
        "trades": int(pnl.size),
        "trades_mes": round(pnl.size / max(months, 1), 2),
        "wr": round(float((net > 0).mean() * 100), 2),
        "pf": round(float(gw / gl), 3) if gl > 0 else None,
        "ev_gross": round(float(pnl.mean()), 3),
        "ev_net": round(float(net.mean()), 3),
    }


def block(frame: pd.DataFrame) -> dict:
    months = frame["date"].dt.to_period("M").nunique() if len(frame) else 1
    out = metrics(frame[PNL].to_numpy(), months)
    per_year = {}
    for year, sub in frame.groupby("year"):
        m = sub["date"].dt.to_period("M").nunique()
        per_year[int(year)] = metrics(sub[PNL].to_numpy(), m)
    out["por_anio"] = per_year
    return out


def common_gate(fresh_sel: pd.DataFrame) -> tuple[dict, str]:
    b = block(fresh_sel)
    pos_years = sum(1 for y in b["por_anio"].values()
                    if y["ev_net"] is not None and y["ev_net"] > 0)
    gates = {
        "G1_ev_net_pos": bool(b["ev_net"] is not None and b["ev_net"] > 0),
        "G2_pf_gt_115": bool(b["pf"] is not None and b["pf"] > G2_PF),
        "G3_anios_pos_ge_2": bool(pos_years >= G3_YEARS),
        "G4_freq_ge_4_mes": bool(b["trades_mes"] >= G4_TPM),
        "G5_supera_baseline": bool(b["ev_net"] is not None
                                   and b["ev_net"] > BASELINE_FRESH_EV),
    }
    return gates, ("PASS" if all(gates.values()) else "FAIL")


def load() -> pd.DataFrame:
    feat = pd.read_csv(SRC / "orb_features_labels_1s.csv")
    pnl = pd.read_csv(SRC / "orb_trailing_pnl.csv")
    data = pnl.merge(feat[["date", "net_60", "rng_60"]], on="date",
                     how="left", validate="one_to_one")
    data["date"] = pd.to_datetime(data["date"])
    data = data.sort_values("date").reset_index(drop=True)
    data["year"] = data["date"].dt.year
    return data


def run_h1(data: pd.DataFrame) -> dict:
    dev = data[data["year"].isin(DEV_Y)]
    fresh = data[data["year"].isin(FRESH_Y)]
    sel_fresh = fresh[fresh["direction"] == "UP"]
    gates, verdict = common_gate(sel_fresh)
    return {
        "hipotesis": "H1", "titulo": "Sesgo estructural UP",
        "regla": "direction == UP", "parametros_libres": 0,
        "dev_descriptivo": block(dev[dev["direction"] == "UP"]),
        "fresh_baseline": block(fresh),
        "fresh_seleccion": block(sel_fresh),
        "gates": gates, "VERDICT": verdict,
        "caveat": ("split UP/DOWN observado full-sample antes de preregistrar; "
                   "mitigado por cero parametros libres"),
    }


def run_h2(data: pd.DataFrame, base_mask) -> dict:
    d = data.copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        trend = (d["net_60"].abs() / d["rng_60"].replace(0, np.nan))
    # causal: mean of the K PREVIOUS sessions, today excluded
    # ERRATA H2-001: rng_60==0 in 154 sessions makes the ratio NaN; requiring
    # 20 valid observations left every window empty. Mean over valid ones.
    d["trendiness"] = trend.shift(1).rolling(20, min_periods=10).mean()
    thr = float(d.loc[d["year"].isin(DEV_Y), "trendiness"].median())
    d["regime_ok"] = (d["trendiness"] >= thr).fillna(False)
    fresh = d[d["year"].isin(FRESH_Y)]
    sel = fresh[base_mask(fresh) & fresh["regime_ok"]]
    gates, verdict = common_gate(sel)
    return {
        "hipotesis": "H2", "titulo": "Gate de regimen tendencial",
        "regla": f"base AND trendiness(K=20, causal) >= {thr:.5f} (mediana DEV)",
        "parametros_libres": 0,
        "K": 20, "umbral_DEV": round(thr, 5),
        "dev_descriptivo": block(d[d["year"].isin(DEV_Y)
                                   & base_mask(d) & d["regime_ok"]]),
        "fresh_base_sin_gate": block(fresh[base_mask(fresh)]),
        "fresh_seleccion": block(sel),
        "gates": gates, "VERDICT": verdict,
    }


def main() -> int:
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    if sha256_file(BASE / "PREREGISTRO_H1_H4.md") != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch - refusing to run")
    data = load()
    results = {}

    which = sys.argv[1] if len(sys.argv) > 1 else "H1"

    if which == "H1":
        results["H1"] = run_h1(data)
    elif which == "H2":
        prev = json.loads((OUT / "H1_RESULT.json").read_text())
        if prev["VERDICT"] == "PASS":
            base_mask = lambda f: f["direction"] == "UP"      # noqa: E731
            base_name = "solo UP (H1 sobrevivio)"
        else:
            base_mask = lambda f: pd.Series(True, index=f.index)  # noqa: E731
            base_name = "ambas direcciones (H1 fallo)"
        results["H2"] = run_h2(data, base_mask)
        results["H2"]["base_usada"] = base_name

    for name, res in results.items():
        (OUT / f"{name}_RESULT.json").write_text(
            json.dumps(res, indent=2, default=str), encoding="utf-8")
        print(json.dumps(res, indent=2, default=str))
    print(f"\nelapsed {time.time()-t0:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
