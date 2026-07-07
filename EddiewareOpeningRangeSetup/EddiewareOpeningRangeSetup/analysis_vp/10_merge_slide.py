"""Merge all features_slide_*.csv into one dataset (X + y) for the VP analysis.

Reads every features_slide_YYYY-MM-DD_NY.csv, tags year/date, concatenates, and
writes a single parquet + a small summary. No look-ahead: each slide row already
carries only causal features (frozen VP at 09:30) plus its forward label
(fwd_mfe_up/dn, hit40/60_up/dn) measured after that bar.

Usage:
    python -u 10_merge_slide.py
    python -u 10_merge_slide.py --src "<folder>" --out merged_slide.parquet
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import pandas as pd

from progress import track

DEFAULT_SRC = r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC, help="folder with features_slide_*.csv")
    ap.add_argument("--out", default="merged_slide.parquet")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.src, "features_slide_*_NY.csv")))
    if not files:
        print(f"No features_slide_*_NY.csv en {args.src}", file=sys.stderr)
        return 1
    print(f"Encontrados {len(files)} archivos slide.")

    frames = []
    bad = 0
    for f in track(files, label="Merge slide"):
        try:
            df = pd.read_csv(f)
            if df.empty:
                continue
            df["src_file"] = os.path.basename(f)
            frames.append(df)
        except Exception as exc:  # noqa: BLE001
            bad += 1
            print(f"  skip {os.path.basename(f)}: {exc}", file=sys.stderr)

    if not frames:
        print("Ningún archivo válido.", file=sys.stderr)
        return 1

    data = pd.concat(frames, ignore_index=True)
    # fecha -> datetime -> year (fecha col is 'fecha' as yyyy-mm-dd or similar)
    data["date"] = pd.to_datetime(data["fecha"], errors="coerce")
    if data["date"].isna().all():
        # fallback: parse from filename
        data["date"] = pd.to_datetime(
            data["src_file"].str.extract(r"(\d{4}-\d{2}-\d{2})")[0], errors="coerce"
        )
    data["year"] = data["date"].dt.year

    data.to_parquet(args.out, index=False)
    print(f"\nGuardado: {args.out}  filas={len(data):,}  cols={data.shape[1]}  "
          f"fechas={data['date'].nunique()}  archivos_malos={bad}")

    # quick summary per year
    summary = (data.groupby("year")
               .agg(rows=("date", "size"),
                    dates=("date", "nunique"),
                    hit60_up=("hit60_up", "mean"),
                    hit60_dn=("hit60_dn", "mean"))
               .round(3))
    print("\nResumen por año:")
    print(summary.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
