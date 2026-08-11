"""Univariate AUC of each Volume-Profile distance feature vs the +60t label.

For every VP feature (distance_to_*, position_vs_*, profile_confluence_count) it
computes directional AUC (max(auc, 1-auc), so a feature that predicts by being
LOW is not penalized) overall AND per year. Prints a table sorted by overall AUC
and flags features that are (a) weak (<0.55) or (b) unstable across years.

This is the CHEAP filter run BEFORE CatBoost: kill the noise so the model only
sees features that carry standalone signal that is stable year-over-year.

Label (continuation): price ran >=60t in the break direction before adverse.
    y = (break_dir==up & hit60_up) | (break_dir==down & hit60_dn)
Use --fade for the opposite (fade) label.

Usage:
    python -u 11_univariate_vp.py
    python -u 11_univariate_vp.py --data merged_slide.parquet --fade
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


def build_label(df: pd.DataFrame, fade: bool) -> pd.Series:
    up = df["break_dir"].astype(str).str.lower().eq("up")
    if fade:
        y = (up & df["hit60_dn"].astype(bool)) | (~up & df["hit60_up"].astype(bool))
    else:
        y = (up & df["hit60_up"].astype(bool)) | (~up & df["hit60_dn"].astype(bool))
    return y.astype(int)


def vp_feature_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns
            if c.startswith(("distance_to_PD", "distance_to_ON", "distance_to_PREOPEN",
                             "position_vs_"))
            or c == "profile_confluence_count"]


def dir_auc(y: np.ndarray, x: np.ndarray) -> float:
    m = ~np.isnan(x)
    if m.sum() < 30 or len(np.unique(y[m])) < 2:
        return np.nan
    try:
        a = roc_auc_score(y[m], x[m])
    except Exception:  # noqa: BLE001
        return np.nan
    return max(a, 1 - a)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="merged_slide.parquet")
    ap.add_argument("--fade", action="store_true", help="use fade label instead of continuation")
    ap.add_argument("--min-auc", type=float, default=0.55)
    args = ap.parse_args()

    df = pd.read_parquet(args.data)
    df["y"] = build_label(df, args.fade)
    feats = vp_feature_cols(df)
    years = sorted(df["year"].dropna().unique().astype(int))
    label = "FADE" if args.fade else "CONTINUATION"
    print(f"Label: {label} | filas={len(df):,} | base rate y={df['y'].mean():.3f} | "
          f"features VP={len(feats)} | años={years}")

    rows = []
    for c in feats:
        overall = dir_auc(df["y"].to_numpy(), df[c].to_numpy(dtype=float))
        per_year = {}
        for yr in years:
            sub = df[df["year"] == yr]
            per_year[yr] = dir_auc(sub["y"].to_numpy(), sub[c].to_numpy(dtype=float))
        vals = [v for v in per_year.values() if not np.isnan(v)]
        spread = (max(vals) - min(vals)) if len(vals) >= 2 else np.nan
        rows.append({"feature": c, "auc_all": overall,
                     **{f"auc_{yr}": per_year[yr] for yr in years},
                     "spread": spread})

    res = pd.DataFrame(rows).sort_values("auc_all", ascending=False)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 100)
    print("\n=== AUC univariada (direccional) por feature ===")
    print(res.round(3).to_string(index=False))

    strong = res[(res["auc_all"] >= args.min_auc) & (res["spread"] <= 0.10)]
    print(f"\n=== SOBREVIVEN (auc_all>={args.min_auc} y spread<=0.10): {len(strong)} ===")
    if strong.empty:
        print("NINGUNA. Señal univariada débil o inestable -> prior 'aporte marginal' confirmado.")
    else:
        print(strong[["feature", "auc_all", "spread"]].round(3).to_string(index=False))
        strong["feature"].to_csv("vp_survivors.txt", index=False, header=False)
        print("\nLista -> vp_survivors.txt (input para CatBoost)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
