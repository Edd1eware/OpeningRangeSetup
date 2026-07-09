#!/usr/bin/env python3
"""Paridad ventana corta vs completa para el contexto 08:30-09:30.

Uso:
  1) Captura ventana COMPLETA:  python -u lvn_OR_strategy_replay.py --run --replay-from 08:29 --dates YYYY-MM-DD
  2) Respalda:                  copy lvn_research_raw_YYYY-MM-DD_NY.csv lvn_research_raw_YYYY-MM-DD_NY_FULL.csv
  3) Captura ventana CORTA:     python -u lvn_OR_strategy_replay.py --run --force --dates YYYY-MM-DD
  4) Compara:                   python compare_context_parity.py --date YYYY-MM-DD

PASS = mismos POC/VAH/VAL/total y probabilidades de shape en ambos archivos.
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime
from pathlib import Path

from lvn_retest_engine.config import ResearchConfig
from lvn_retest_engine.io import read_inputs
from lvn_retest_engine.profile_builder import build_profile
from lvn_retest_engine.shape_classifier import classify_shape

RAW_DIR = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\lvn_research_raw")
SHAPES = ("D", "P", "b", "double", "trend_up", "trend_down", "unknown")


def context_metrics(csv_path: Path, config: ResearchConfig) -> dict[str, float]:
    data, _, _ = read_inputs([str(csv_path)], config)
    session_date = data["session_date"].iloc[0]
    frame = data.loc[data["session_date"] == session_date]
    profile = build_profile(frame, session_date, "CONTEXT_0830_0930",
                            config.context_profile_start, config.context_profile_end, config)
    profile.shape = classify_shape(profile, config)
    out = {
        "price_levels": float(profile.metrics.get("price_level_count", math.nan)),
        "total_volume": float(profile.metrics.get("total_volume", math.nan)),
        "poc": float(profile.metrics.get("poc", math.nan)),
        "vah": float(profile.metrics.get("vah", math.nan)),
        "val": float(profile.metrics.get("val", math.nan)),
    }
    for shape in SHAPES:
        out[f"prob_{shape}"] = float(profile.shape.get(f"prob_{shape}", math.nan))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--tolerance", type=float, default=1e-9, help="Tolerancia absoluta para comparar")
    args = parser.parse_args()
    datetime.strptime(args.date, "%Y-%m-%d")

    short_path = RAW_DIR / f"lvn_research_raw_{args.date}_NY.csv"
    full_path = RAW_DIR / f"lvn_research_raw_{args.date}_NY_FULL.csv"
    for path in (short_path, full_path):
        if not path.exists():
            print(f"ERROR: falta {path}", file=sys.stderr)
            return 2

    config = ResearchConfig()
    short = context_metrics(short_path, config)
    full = context_metrics(full_path, config)

    print(f"{'metric':24} {'FULL(08:29)':>16} {'SHORT(09:29)':>16} {'delta':>12}  status")
    failures = 0
    for key in full:
        a, b = full[key], short[key]
        both_nan = math.isnan(a) and math.isnan(b)
        delta = 0.0 if both_nan else abs(a - b)
        ok = both_nan or delta <= args.tolerance
        failures += 0 if ok else 1
        print(f"{key:24} {a:16.6f} {b:16.6f} {delta:12.6f}  {'OK' if ok else 'MISMATCH'}")

    print()
    if failures:
        print(f"PARIDAD: FAIL ({failures} métricas difieren). La historia pre-replay NO reproduce "
              "el contexto: quedarse con --replay-from 08:29.")
        return 1
    print("PARIDAD: PASS. Ventana corta 09:29 reproduce el contexto exacto -> adoptar default corto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
