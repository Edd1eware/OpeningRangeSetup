"""EB-V1: era-blind participation filter test (single shot).

Frozen by PREREGISTRO_EB_FILTER_V1.md (SHA-256 45bc2683...).
Thresholds come ONLY from DEV (2022-2023); FRESH (2024-2026) is opened once.
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
COMMISSION = 2.0
PNL_COL = "trail_50_20_40"
DEV_YEARS = {2022, 2023}
FRESH_YEARS = {2024, 2025, 2026}
PREREG_SHA = "45bc268309c7dba408624709e018271ab0bae8018c4ba2bd46900e47a4a77a43"

# frozen gate
G2_PF, G3_RET, G4_YEARS = 1.15, 0.40, 2


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as s:
        for chunk in iter(lambda: s.read(1 << 20), b""):
            d.update(chunk)
    return d.hexdigest()


def metrics(pnl: np.ndarray) -> dict:
    """Gross/net EV, WR, PF on a set of per-trade tick PnL."""
    if pnl.size == 0:
        return {"trades": 0, "wr": np.nan, "pf": np.nan,
                "ev_gross": np.nan, "ev_net": np.nan}
    net = pnl - COMMISSION
    wins, losses = net[net > 0], net[net < 0]
    gross_win, gross_loss = wins.sum(), -losses.sum()
    return {
        "trades": int(pnl.size),
        "wr": float((net > 0).mean() * 100),
        "pf": float(gross_win / gross_loss) if gross_loss > 0 else np.inf,
        "ev_gross": float(pnl.mean()),
        "ev_net": float(net.mean()),
    }


def year_table(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    rows = []
    for year, sub in frame.groupby("year"):
        m = metrics(sub[PNL_COL].to_numpy())
        months = max(sub["date"].dt.to_period("M").nunique(), 1)
        m.update({"bloque": label, "year": int(year),
                  "trades_mes": round(m["trades"] / months, 2)})
        rows.append(m)
    m = metrics(frame[PNL_COL].to_numpy())
    months = max(frame["date"].dt.to_period("M").nunique(), 1)
    m.update({"bloque": label, "year": "TOTAL",
              "trades_mes": round(m["trades"] / months, 2)})
    rows.append(m)
    cols = ["bloque", "year", "trades", "trades_mes", "wr", "pf",
            "ev_gross", "ev_net"]
    return pd.DataFrame(rows)[cols].round(3)


def main() -> int:
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    if sha256_file(BASE / "PREREGISTRO_EB_FILTER_V1.md") != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch - refusing to run")

    steps = ["cargar datos", "split era-blind", "umbrales DEV",
             "aplicar filtro", "metricas DEV", "disparo unico FRESH",
             "evaluar gate", "guardar"]
    bar = track(steps, label="EB-V1 filtro era-blind")
    it = iter(bar)

    next(it)                                          # cargar datos
    feat = pd.read_csv(SRC / "orb_features_labels_1s.csv")
    pnl = pd.read_csv(SRC / "orb_trailing_pnl.csv")
    data = pnl.merge(
        feat[["date", "dist_pdh", "dist_pdl", "vol_5", "vol_120"]],
        on="date", how="left", validate="one_to_one")
    data["date"] = pd.to_datetime(data["date"])
    data["year"] = data["date"].dt.year

    next(it)                                          # split
    dev = data[data["year"].isin(DEV_YEARS)].copy()
    fresh = data[data["year"].isin(FRESH_YEARS)].copy()

    next(it)                                          # umbrales SOLO de DEV
    with np.errstate(divide="ignore", invalid="ignore"):
        dev_ratio = dev["vol_5"] / dev["vol_120"].replace(0, np.nan)
    thr = {
        "C2_dist_pdl_q25_DEV": float(dev["dist_pdl"].quantile(0.25)),
        "C3_volratio_median_DEV": float(dev_ratio.median()),
    }

    next(it)                                          # aplicar filtro
    def apply_conditions(frame: pd.DataFrame) -> pd.DataFrame:
        f = frame.copy()
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = f["vol_5"] / f["vol_120"].replace(0, np.nan)
        f["C1"] = ((f["dist_pdh"] < 0) & (f["dist_pdl"] > 0)).fillna(False)
        f["C2"] = (f["dist_pdl"] <= thr["C2_dist_pdl_q25_DEV"]).fillna(False)
        f["C3"] = (ratio >= thr["C3_volratio_median_DEV"]).fillna(False)
        f["score_cond"] = (f["C1"].astype(int) + f["C2"].astype(int)
                           + f["C3"].astype(int))
        f["participar"] = f["score_cond"] >= 2
        return f

    dev, fresh = apply_conditions(dev), apply_conditions(fresh)

    next(it)                                          # metricas DEV
    dev_f = dev[dev["participar"]]
    tables = [year_table(dev, "DEV_baseline"),
              year_table(dev_f, "DEV_filtrado")]

    next(it)                                          # DISPARO UNICO FRESH
    fresh_f = fresh[fresh["participar"]]
    tables += [year_table(fresh, "FRESH_baseline"),
               year_table(fresh_f, "FRESH_filtrado")]
    table = pd.concat(tables, ignore_index=True)

    next(it)                                          # gate
    base_m = metrics(fresh[PNL_COL].to_numpy())
    filt_m = metrics(fresh_f[PNL_COL].to_numpy())
    retention = len(fresh_f) / max(len(fresh), 1)
    per_year_pos = sum(
        1 for _y, s in fresh_f.groupby("year")
        if metrics(s[PNL_COL].to_numpy())["ev_net"] > 0)
    gates = {
        "G1_ev_net_pos": bool(filt_m["ev_net"] > 0),
        "G2_pf_gt_115": bool(filt_m["pf"] > G2_PF),
        "G3_retencion_ge_40": bool(retention >= G3_RET),
        "G4_anios_pos_ge_2": bool(per_year_pos >= G4_YEARS),
        "G5_supera_baseline": bool(filt_m["ev_net"] > base_m["ev_net"]),
    }
    verdict = "PASS" if all(gates.values()) else "FAIL"

    next(it)                                          # guardar
    table.to_csv(OUT / "EB_YEAR_TABLE.csv", index=False)
    result = {
        "information_status": "EB_FILTER_OPENED_ONCE",
        "prereg_sha256": PREREG_SHA,
        "pnl_col": PNL_COL, "commission_ticks": COMMISSION,
        "thresholds_from_DEV": thr,
        "n_dev": int(len(dev)), "n_fresh": int(len(fresh)),
        "n_fresh_filtrado": int(len(fresh_f)),
        "retencion_fresh": round(retention, 4),
        "fresh_baseline": {k: (None if isinstance(v, float) and np.isnan(v)
                               else v) for k, v in base_m.items()},
        "fresh_filtrado": {k: (None if isinstance(v, float) and np.isnan(v)
                               else v) for k, v in filt_m.items()},
        "anios_fresh_ev_pos": int(per_year_pos),
        "gates": gates, "VERDICT": verdict,
        "breakeven_note": "EV neto ya descuenta 2.0 ticks de comision",
        "elapsed_s": round(time.time() - t0, 2),
    }
    (OUT / "EB_RESULT.json").write_text(json.dumps(result, indent=2),
                                        encoding="utf-8")
    for _ in it:
        pass
    print(json.dumps(result, indent=2))
    print()
    print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
