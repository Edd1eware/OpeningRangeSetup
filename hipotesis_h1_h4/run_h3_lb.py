"""H3 - Liquidity Burst as a DAY filter.

Frozen by PREREGISTRO_H1_H4.md + ADDENDUM_H3_001.md.
Universe: systematically replayed 2025-2026 window only (2022-24 excluded for
selection bias). Base = both directions (original chaining). UP-only reported as
declared descriptive cut with no verdict authority.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")
VT = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
          r"\trade_results_score\visual_tests")
OUT = Path(__file__).resolve().parent / "output"
COMMISSION = 2.0
PNL = "trail_50_20_40"
YEARS = {2025, 2026}
G2_PF, G4_TPM = 1.15, 4.0


def metrics(x: np.ndarray, months: int) -> dict:
    if x.size == 0:
        return {"trades": 0, "trades_mes": 0.0, "wr": None, "pf": None,
                "ev_net": None}
    n = x - COMMISSION
    gl = -n[n < 0].sum()
    return {"trades": int(x.size), "trades_mes": round(x.size / max(months, 1), 2),
            "wr": round(float((n > 0).mean() * 100), 2),
            "pf": round(float(n[n > 0].sum() / gl), 3) if gl > 0 else None,
            "ev_net": round(float(n.mean()), 3)}


def block(df: pd.DataFrame) -> dict:
    m = df["date"].dt.to_period("M").nunique() if len(df) else 1
    out = metrics(df[PNL].to_numpy(float), m)
    out["por_anio"] = {
        int(y): metrics(s[PNL].to_numpy(float),
                        s["date"].dt.to_period("M").nunique())
        for y, s in df.groupby("year")}
    return out


def lb_labels() -> tuple[set, set]:
    lb, rep = set(), set()
    for f in glob.glob(str(VT / "*lb*/observational/burst_events.csv")):
        d = pd.read_csv(f, usecols=["Timestamp_NY"])
        lb |= set(pd.to_datetime(d["Timestamp_NY"], errors="coerce",
                                 format="mixed").dt.date.dropna())
    for st in glob.glob(str(VT / "*lb*/run_state.json")):
        ds = json.loads(Path(st).read_text()).get("dates", [])
        rep |= set(pd.to_datetime(pd.Series(ds), format="%d/%m/%Y",
                                  errors="coerce").dt.date.dropna())
    return lb, rep


def gate(sel: pd.DataFrame, base: pd.DataFrame) -> tuple[dict, str]:
    b, bb = block(sel), block(base)
    pos = sum(1 for y in b["por_anio"].values()
              if y["ev_net"] is not None and y["ev_net"] > 0)
    g = {"G1_ev_net_pos": bool(b["ev_net"] is not None and b["ev_net"] > 0),
         "G2_pf_gt_115": bool(b["pf"] is not None and b["pf"] > G2_PF),
         "G3_anios_pos_2de2": bool(pos >= 2),
         "G4_freq_ge_4_mes": bool(b["trades_mes"] >= G4_TPM),
         "G5_supera_sin_filtro": bool(
             b["ev_net"] is not None and bb["ev_net"] is not None
             and b["ev_net"] > bb["ev_net"])}
    return g, ("PASS" if all(g.values()) else "FAIL")


def main() -> int:
    lb, rep = lb_labels()
    pnl = pd.read_csv(SRC / "orb_trailing_pnl.csv")
    pnl["date"] = pd.to_datetime(pnl["date"])
    pnl["year"] = pnl["date"].dt.year
    pnl["d"] = pnl["date"].dt.date

    uni = pnl[pnl["year"].isin(YEARS) & pnl["d"].isin(rep)].copy()
    uni["has_lb"] = uni["d"].isin(lb)

    base = uni                                   # both directions, no filter
    sel = uni[uni["has_lb"]]
    gates, verdict = gate(sel, base)

    up = uni[uni["direction"] == "UP"]
    up_lb = up[up["has_lb"]]

    res = {
        "hipotesis": "H3", "titulo": "Liquidity Burst como filtro de DIA",
        "universo": "2025-2026 replay sistematico (2022-24 excluido por sesgo)",
        "n_universo": int(len(uni)),
        "n_con_LB": int(uni["has_lb"].sum()),
        "n_sin_LB": int((~uni["has_lb"]).sum()),
        "PRIMARIO_base_ambas": {
            "sin_filtro": block(base), "con_LB": block(sel),
            "sin_LB": block(uni[~uni["has_lb"]])},
        "DESCRIPTIVO_solo_UP": {
            "sin_filtro": block(up), "con_LB": block(up_lb),
            "sin_LB": block(up[~up["has_lb"]])},
        "gates": gates, "VERDICT": verdict,
        "nota": ("caracterizacion, no validacion: sin era-split dentro de "
                 "2025-2026. El corte solo-UP es descriptivo, sin autoridad "
                 "de veredicto."),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "H3_RESULT.json").write_text(json.dumps(res, indent=2, default=str),
                                        encoding="utf-8")
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
