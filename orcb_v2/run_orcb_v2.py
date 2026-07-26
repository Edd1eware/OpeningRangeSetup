"""OR-CB-V2 - regenerate and freeze the ORB CatBoost filter.

Frozen by PREREGISTRO_ORCB_V2.md (SHA-256 cdfa8bbf...).
Step 1: recompute the TP120/SL55 bracket label from 1s bars.
Step 2: train on DEV, pick threshold by the declared rule on inner-validation.
Step 3: FREEZE model + config (persisted) BEFORE touching FRESH.
Step 4: single shot on FRESH, evaluate gate.
"""

from __future__ import annotations

import glob
import hashlib
import json
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

from progress import track

BASE = Path(__file__).resolve().parent
OUT = BASE / "output"
DBN_ROOT = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
                r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_2")
FEAT_CSV = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs"
                r"\orb_bigmove_1s\orb_features_labels_1s.csv")
PREREG_SHA = "cdfa8bbfbb1118ff7cc9bbab6c93cde7e0abc7f22c99d11805abe52534d24588"

TICK = 0.25
OR_START, OR_END, SCAN_START = "13:30:00", "13:31:00", "13:31:00"
TP_T, SL_T = 120, 55
COMMISSION = 2.0
DEV_Y, FRESH_Y = {2022, 2023}, {2024, 2025, 2026}
INNER_FRAC = 0.20
PREC_TARGET = 0.40
CB = dict(iterations=300, depth=4, learning_rate=0.05,
          loss_function="Logloss", random_seed=20260725, verbose=0)
C2_PF, C3_YEARS, C4_TPM = 1.15, 2, 3.0


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


def bracket_120_55(date: str):
    """Return (y, direction_up) for the first OR breakout, TP120/SL55."""
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
    if t_up is None and t_dn is None:
        return None
    if t_dn is None or (t_up is not None and t_up <= t_dn):
        entry, sign, bt = or_high, 1, t_up
    else:
        entry, sign, bt = or_low, -1, t_dn
    fwd = post.loc[post.index >= bt]
    if sign == 1:
        tp, sl = entry + TP_T * TICK, entry - SL_T * TICK
        for h, l in zip(fwd["high"].to_numpy(), fwd["low"].to_numpy()):
            if l <= sl:
                return 0, 1.0            # pessimistic: SL wins same-bar ties
            if h >= tp:
                return 1, 1.0
    else:
        tp, sl = entry - TP_T * TICK, entry + SL_T * TICK
        for h, l in zip(fwd["high"].to_numpy(), fwd["low"].to_numpy()):
            if h >= sl:
                return 0, 0.0
            if l <= tp:
                return 1, 0.0
    return None                          # timeout -> excluded


def pnl_ticks(y: int) -> float:
    return (TP_T if y == 1 else -SL_T) - COMMISSION


def metrics(net: np.ndarray, months: int) -> dict:
    if net.size == 0:
        return {"trades": 0}
    gl = -net[net < 0].sum()
    return {"trades": int(net.size),
            "trades_mes": round(net.size / max(months, 1), 2),
            "wr": round(float((net > 0).mean() * 100), 2),
            "pf": round(float(net[net > 0].sum() / gl), 3) if gl > 0 else None,
            "ev_net": round(float(net.mean()), 3)}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    if sha256_file(BASE / "PREREGISTRO_ORCB_V2.md") != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")

    # ---- Step 1: regenerate the TP120/SL55 label
    lab_path = OUT / "ORCB_V2_LABELS.csv"
    if lab_path.exists():
        labels = pd.read_csv(lab_path)
    else:
        dates = sorted(p.name for p in DBN_ROOT.iterdir() if p.is_dir())
        rows = []
        for d in track(dates, label="etiqueta TP120/SL55"):
            try:
                r = bracket_120_55(d)
            except Exception:  # noqa: BLE001
                r = None
            if r is not None:
                rows.append({"date": d, "y120": r[0], "dir_up": r[1]})
        labels = pd.DataFrame(rows)
        labels.to_csv(lab_path, index=False)

    feats = pd.read_csv(FEAT_CSV)
    data = feats.merge(labels, on="date", how="inner", validate="one_to_one")
    data["date"] = pd.to_datetime(data["date"])
    data["year"] = data["date"].dt.year
    drop = {"date", "y", "year", "y120", "dir_up"}
    fcols = sorted(c for c in data.columns if c not in drop)

    dev = data[data["year"].isin(DEV_Y)].sort_values("date")
    fresh = data[data["year"].isin(FRESH_Y)].sort_values("date")
    n_inner = max(int(len(dev) * INNER_FRAC), 20)
    tr, inner = dev.iloc[:-n_inner], dev.iloc[-n_inner:]

    # ---- Step 2: train + threshold by the declared rule
    model = CatBoostClassifier(**CB)
    model.fit(tr[fcols].to_numpy(float), tr["y120"].to_numpy(int))
    p_inner = model.predict_proba(inner[fcols].to_numpy(float))[:, 1]
    y_inner = inner["y120"].to_numpy(int)
    thr, prec_at_thr, n_sel_inner = 0.50, None, 0
    for cand in np.round(np.arange(0.05, 0.951, 0.0025), 4):
        sel = p_inner >= cand
        if sel.sum() < 5:
            continue
        prec = float(y_inner[sel].mean())
        if prec >= PREC_TARGET:
            thr, prec_at_thr, n_sel_inner = float(cand), prec, int(sel.sum())
            break

    # ---- Step 3: FREEZE before touching FRESH
    model_path = OUT / "orcb_v2_model.cbm"
    model.save_model(str(model_path))
    config = {"threshold": thr, "features_ordered": fcols,
              "catboost_params": CB, "tp_ticks": TP_T, "sl_ticks": SL_T,
              "commission_ticks": COMMISSION,
              "prec_target": PREC_TARGET,
              "inner_precision_at_thr": prec_at_thr,
              "inner_n_selected": n_sel_inner,
              "n_train": int(len(tr)), "n_inner": int(len(inner)),
              "prereg_sha256": PREREG_SHA}
    cfg_path = OUT / "orcb_v2_config.json"
    cfg_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    frozen = {"orcb_v2_model.cbm": sha256_file(model_path),
              "orcb_v2_config.json": sha256_file(cfg_path)}
    (OUT / "FROZEN_HASHES.sha256").write_text(
        "\n".join(f"{v}  {k}" for k, v in frozen.items()) + "\n",
        encoding="utf-8")

    # ---- Step 4: single shot on FRESH
    p_fresh = model.predict_proba(fresh[fcols].to_numpy(float))[:, 1]
    sel = fresh[p_fresh >= thr].copy()
    sel["net"] = sel["y120"].map(pnl_ticks)
    months = sel["date"].dt.to_period("M").nunique() if len(sel) else 1
    m = metrics(sel["net"].to_numpy(float), months)
    per_year = {int(y): metrics(g["net"].to_numpy(float),
                                g["date"].dt.to_period("M").nunique())
                for y, g in sel.groupby("year")}
    base = fresh.copy()
    base["net"] = base["y120"].map(pnl_ticks)
    base_m = metrics(base["net"].to_numpy(float),
                     base["date"].dt.to_period("M").nunique())

    pos = sum(1 for v in per_year.values()
              if v.get("ev_net") is not None and v["ev_net"] > 0)
    gates = {"C1_ev_net_pos": bool(m.get("ev_net") is not None
                                   and m["ev_net"] > 0),
             "C2_pf_gt_115": bool(m.get("pf") is not None and m["pf"] > C2_PF),
             "C3_anios_pos_ge2": bool(pos >= C3_YEARS),
             "C4_freq_ge_3": bool(m.get("trades_mes", 0) >= C4_TPM)}
    res = {"estudio": "OR-CB-V2", "prereg_sha256": PREREG_SHA,
           "nota": "NO es reproduccion de F7; estudio nuevo, resultado propio",
           "n_eventos_total": int(len(data)),
           "breakeven_wr_pct": round(100 * SL_T / (TP_T + SL_T), 2),
           "threshold_elegido": thr,
           "precision_inner_en_thr": prec_at_thr,
           "n_train": int(len(tr)), "n_inner": int(len(inner)),
           "FRESH_sin_filtro": base_m, "FRESH_filtrado": m,
           "por_anio": per_year, "gates": gates,
           "VERDICT": "PASS" if all(gates.values()) else "FAIL",
           "frozen": frozen}
    (OUT / "ORCB_V2_RESULT.json").write_text(json.dumps(res, indent=2),
                                             encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
