#!/usr/bin/env python3
"""Read-only performance report for the independent Codex candidate engine."""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_DATA = Path(__file__).resolve().parent / "research_data_codex"
DEFAULT_BASE = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA))
    parser.add_argument("--base-results", default=str(DEFAULT_BASE))
    parser.add_argument("--output", default="codex_strategy_report.json")
    return parser.parse_args()


def load_codex(data_dir: str) -> pd.DataFrame:
    frames = []
    for path in glob.glob(os.path.join(data_dir, "opening_range_candidates_*_codex.csv")):
        try:
            frames.append(pd.read_csv(path))
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
            continue
    if not frames:
        raise RuntimeError("No Codex candidate files found")
    data = pd.concat(frames, ignore_index=True, sort=False)
    data["fecha"] = data["fecha"].astype(str).str[:10]
    data["pnl_ticks"] = pd.to_numeric(data["pnl_ticks"], errors="coerce")
    data["would_trade"] = pd.to_numeric(data["would_trade"], errors="coerce").fillna(0).astype(int)
    return data.sort_values(["fecha", "entry_time_ny", "candidate_id"]).reset_index(drop=True)


def max_losing_streak(values: pd.Series) -> int:
    current = maximum = 0
    for value in values:
        if value < 0:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def summarize(data: pd.DataFrame) -> dict[str, object]:
    trades = data[data["would_trade"].eq(1) & data["pnl_ticks"].notna()].copy()
    profit = trades.loc[trades["pnl_ticks"] > 0, "pnl_ticks"].sum()
    loss = -trades.loc[trades["pnl_ticks"] < 0, "pnl_ticks"].sum()
    terminal = trades[trades["outcome"].isin(["WIN", "LOSS"])]
    months = max(1, trades["fecha"].str[:7].nunique())
    return {
        "candidate_rows": int(len(data)),
        "dates_logged": int(data["fecha"].nunique()),
        "trades": int(len(trades)),
        "trades_per_active_month": float(len(trades) / months),
        "wins": int(trades["outcome"].eq("WIN").sum()),
        "losses": int(trades["outcome"].eq("LOSS").sum()),
        "timeouts": int((~trades["outcome"].isin(["WIN", "LOSS"])).sum()),
        "terminal_wr": float(terminal["outcome"].eq("WIN").mean()) if len(terminal) else math.nan,
        "profit_factor": float(profit / loss) if loss else math.inf,
        "net_ticks_after_slippage": float(trades["pnl_ticks"].sum()),
        "net_dollars_3_nq": float(trades["pnl_ticks"].sum() * 15),
        "ticks_per_trade": float(trades["pnl_ticks"].mean()) if len(trades) else math.nan,
        "max_losing_streak": max_losing_streak(trades["pnl_ticks"]),
    }


def breakdown(data: pd.DataFrame, column: str) -> list[dict[str, object]]:
    output = []
    for value, group in data.groupby(column, dropna=False):
        row = summarize(group)
        row[column] = str(value)
        output.append(row)
    return output


def base_summary(base_results: str, dates: set[str]) -> dict[str, object]:
    frames = []
    for path in glob.glob(os.path.join(base_results, "score_trade_result_*_NY.csv")):
        try:
            frames.append(pd.read_csv(path))
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
            continue
    if not frames:
        return {}
    data = pd.concat(frames, ignore_index=True, sort=False)
    data["fecha"] = data["fecha"].astype(str).str[:10]
    data = data[data["fecha"].isin(dates) & data["Result_Label"].isin(["TP", "SL"])].copy()
    data["pnl_ticks"] = pd.to_numeric(data["Result_After_Slippage_Ticks"], errors="coerce")
    profit = data.loc[data["pnl_ticks"] > 0, "pnl_ticks"].sum()
    loss = -data.loc[data["pnl_ticks"] < 0, "pnl_ticks"].sum()
    return {
        "trades": int(len(data)),
        "wins": int(data["Result_Label"].eq("TP").sum()),
        "losses": int(data["Result_Label"].eq("SL").sum()),
        "win_rate": float(data["Result_Label"].eq("TP").mean()) if len(data) else math.nan,
        "profit_factor": float(profit / loss) if loss else math.inf,
        "net_ticks_after_slippage": float(data["pnl_ticks"].sum()),
    }


def clean(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    return value


def main() -> None:
    args = parse_args()
    data = load_codex(args.data_dir)
    report = {
        "codex": summarize(data),
        "by_setup": breakdown(data, "setup"),
        "by_month": breakdown(data.assign(month=data["fecha"].str[:7]), "month"),
        "base_same_dates": base_summary(args.base_results, set(data["fecha"])),
    }
    Path(args.output).write_text(json.dumps(clean(report), indent=2), encoding="utf-8")
    print(json.dumps(clean(report), indent=2))


if __name__ == "__main__":
    main()
