from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


CORE_FIELDS = (
    "EntryTime_NY",
    "Entry_price",
    "Side",
    "SL_price",
    "TP_price",
    "SL_ticks",
    "TP_ticks",
    "ExitTime_NY",
    "Exit_price",
    "Result_Label",
    "result TP SL BE",
    "MAE_ticks",
    "MFE_ticks",
    "Trade_Duration",
)

MILLISECOND_FIELDS = (
    "EntryTime_NY_Milliseconds",
    "ExitTime_NY_Milliseconds",
    "Trade_Duration_Milliseconds",
)

TRADE_RESULTS = {"TP", "SL", "BE"}


def read_row(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.DictReader(handle))


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def csv_result_rows(folder: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in sorted(folder.glob("score_trade_result_*_NY.csv")):
        row = read_row(path)
        rows[row["fecha"]] = row
    return rows


def tick_value(row: dict[str, str]) -> float:
    return float(row["result TP SL BE"].replace("+", ""))


def metrics(rows: list[dict[str, str]]) -> dict[str, float | int]:
    trades = [row for row in rows if row.get("Result_Label") in TRADE_RESULTS]
    ticks = [tick_value(row) for row in trades]
    wins = [value for value in ticks if value > 0]
    losses = [value for value in ticks if value < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "wr": 100.0 * len(wins) / len(trades),
        "pf": gross_win / gross_loss,
        "expectancy_ticks": mean(ticks),
        "net_ticks": sum(ticks),
        "average_win_ticks": mean(wins),
        "average_loss_ticks": mean(losses),
        "mae_average_ticks": mean(float(row["MAE_ticks"]) for row in trades),
        "mae_max_ticks": max(float(row["MAE_ticks"]) for row in trades),
        "mfe_average_ticks": mean(float(row["MFE_ticks"]) for row in trades),
        "mfe_max_ticks": max(float(row["MFE_ticks"]) for row in trades),
        "balance_150k_6_contracts": 150000.0 + 30.0 * sum(ticks),
    }


def monthly_metrics(rows: list[dict[str, str]]) -> list[dict[str, float | int | str]]:
    grouped: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("Result_Label") in TRADE_RESULTS:
            grouped[row["fecha"][:7]].append(row)

    output: list[dict[str, float | int | str]] = []
    for month, month_rows in sorted(grouped.items()):
        item = metrics(month_rows)
        item["month"] = month
        output.append(item)
    return output


def normalize_bool(value: str) -> str:
    return "true" if str(value).strip().lower() in {"true", "1", "yes"} else "false"


def normalize_number(value: str) -> str:
    text = str(value).strip().replace("+", "")
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    return f"{number:.12g}"


def current_trade_view(row: dict[str, str]) -> dict[str, str]:
    return {
        "entry_time": row["EntryTime_NY"],
        "entry_price": normalize_number(row["Entry_price"]),
        "direction": row["Side"],
        "initial_stop_price": normalize_number(row["Initial_SL_price"]),
        "initial_stop_ticks": normalize_number(row["Initial_SL_ticks"]),
        "initial_target_price": normalize_number(row["Initial_TP_price"]),
        "initial_target_ticks": normalize_number(row["Initial_TP_ticks"]),
        "planned_rr_at_entry": normalize_number(row["Initial_RR"]),
        "final_stop_price": normalize_number(row["Final_SL_price"]),
        "final_stop_ticks": normalize_number(row["Final_SL_ticks"]),
        "final_target_price": normalize_number(row["Final_TP_price"]),
        "final_target_ticks": normalize_number(row["Final_TP_ticks"]),
        "target_modification_reason": row["Target_Modification_Reason"] or "NONE",
        "exit_price": normalize_number(row["Exit_price"]),
        "exit_time": row["ExitTime_NY"],
        "exit_reason_reported": row["Exit_Reason"],
        "realized_ticks": normalize_number(row["result TP SL BE"]),
        "MFE_ticks": normalize_number(row["MFE_ticks"]),
        "MAE_ticks": normalize_number(row["MAE_ticks"]),
        "stop_was_moved": normalize_bool(row["Stop_Was_Moved"]),
        "target_was_moved": normalize_bool(row["Target_Was_Moved"]),
    }


def baseline_trade_view(row: dict[str, str]) -> dict[str, str]:
    numeric_fields = {
        "entry_price",
        "initial_stop_price",
        "initial_stop_ticks",
        "initial_target_price",
        "initial_target_ticks",
        "planned_rr_at_entry",
        "final_stop_price",
        "final_stop_ticks",
        "final_target_price",
        "final_target_ticks",
        "exit_price",
        "realized_ticks",
        "MFE_ticks",
        "MAE_ticks",
    }
    bool_fields = {"stop_was_moved", "target_was_moved"}
    output: dict[str, str] = {}
    for field in (
        "entry_time",
        "entry_price",
        "direction",
        "initial_stop_price",
        "initial_stop_ticks",
        "initial_target_price",
        "initial_target_ticks",
        "planned_rr_at_entry",
        "final_stop_price",
        "final_stop_ticks",
        "final_target_price",
        "final_target_ticks",
        "target_modification_reason",
        "exit_price",
        "exit_time",
        "realized_ticks",
        "MFE_ticks",
        "MAE_ticks",
        "stop_was_moved",
        "target_was_moved",
    ):
        value = row.get(field, "")
        if field in numeric_fields:
            value = normalize_number(value)
        elif field in bool_fields:
            value = normalize_bool(value)
        elif field == "target_modification_reason":
            value = value or "NONE"
        output[field] = value
    output["exit_reason_reported"] = row.get("exit_reason", "")
    return output


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--current-dir", type=Path, required=True)
    parser.add_argument("--baseline-trades", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    baseline = csv_result_rows(args.baseline_dir)
    current = csv_result_rows(args.current_dir)
    dates = sorted(set(baseline) | set(current))

    field_diffs: list[dict[str, object]] = []
    shared_diffs: list[dict[str, object]] = []
    for date in dates:
        base_row = baseline.get(date)
        current_row = current.get(date)
        if base_row is None or current_row is None:
            field_diffs.append(
                {
                    "date": date,
                    "category": "missing_file",
                    "field": "score_trade_result",
                    "baseline": "present" if base_row else "missing",
                    "current": "present" if current_row else "missing",
                }
            )
            continue

        for field in CORE_FIELDS:
            if base_row.get(field, "") != current_row.get(field, ""):
                field_diffs.append(
                    {
                        "date": date,
                        "category": "core",
                        "field": field,
                        "baseline": base_row.get(field, ""),
                        "current": current_row.get(field, ""),
                    }
                )
        for field in MILLISECOND_FIELDS:
            if base_row.get(field, "") != current_row.get(field, ""):
                field_diffs.append(
                    {
                        "date": date,
                        "category": "millisecond",
                        "field": field,
                        "baseline": base_row.get(field, ""),
                        "current": current_row.get(field, ""),
                    }
                )

        for field in sorted(set(base_row) & set(current_row)):
            if base_row[field] != current_row[field]:
                shared_diffs.append(
                    {
                        "date": date,
                        "field": field,
                        "baseline": base_row[field],
                        "current": current_row[field],
                    }
                )

    baseline_trades = {
        row["date"]: baseline_trade_view(row) for row in read_rows(args.baseline_trades)
    }
    current_trades = {
        date: current_trade_view(row)
        for date, row in current.items()
        if row.get("Result_Label") in TRADE_RESULTS
    }
    behavior_fields = (
        "entry_time",
        "entry_price",
        "direction",
        "initial_stop_price",
        "initial_stop_ticks",
        "initial_target_price",
        "initial_target_ticks",
        "planned_rr_at_entry",
        "final_stop_price",
        "final_stop_ticks",
        "final_target_price",
        "final_target_ticks",
        "target_modification_reason",
        "exit_price",
        "exit_time",
        "realized_ticks",
        "MFE_ticks",
        "MAE_ticks",
        "stop_was_moved",
        "target_was_moved",
    )
    trade_diffs: list[dict[str, object]] = []
    for date in sorted(set(baseline_trades) | set(current_trades)):
        base_row = baseline_trades.get(date, {})
        current_row = current_trades.get(date, {})
        for field in behavior_fields:
            if base_row.get(field, "") != current_row.get(field, ""):
                trade_diffs.append(
                    {
                        "date": date,
                        "field": field,
                        "baseline": base_row.get(field, ""),
                        "current": current_row.get(field, ""),
                    }
                )

    current_trade_rows = [row for row in current.values() if row.get("Result_Label") in TRADE_RESULTS]
    invalid_rr = [
        row["fecha"]
        for row in current_trade_rows
        if float(row["Initial_TP_ticks"]) < float(row["Initial_SL_ticks"])
    ]
    dynamic_rows = [row for row in current_trade_rows if normalize_bool(row["Target_Was_Moved"]) == "true"]

    baseline_metrics = metrics(list(baseline.values()))
    current_metrics = metrics(list(current.values()))
    summary = {
        "status": "FAILED" if field_diffs else "PASSED",
        "baseline_files": len(baseline),
        "current_files": len(current),
        "missing_dates": sorted(set(baseline) - set(current)),
        "extra_dates": sorted(set(current) - set(baseline)),
        "terminal_labels_baseline": dict(Counter(row["Result_Label"] for row in baseline.values())),
        "terminal_labels_current": dict(Counter(row["Result_Label"] for row in current.values())),
        "baseline_metrics": baseline_metrics,
        "current_metrics": current_metrics,
        "metric_deltas": {
            key: current_metrics[key] - baseline_metrics[key]
            for key in current_metrics
            if isinstance(current_metrics[key], (int, float))
        },
        "core_diff_count": sum(row["category"] == "core" for row in field_diffs),
        "core_diff_dates": sorted({row["date"] for row in field_diffs if row["category"] == "core"}),
        "millisecond_diff_count": sum(row["category"] == "millisecond" for row in field_diffs),
        "millisecond_diff_dates": sorted(
            {row["date"] for row in field_diffs if row["category"] == "millisecond"}
        ),
        "shared_field_diff_count": len(shared_diffs),
        "shared_field_diff_dates": sorted({row["date"] for row in shared_diffs}),
        "trade_behavior_diff_count": len(trade_diffs),
        "trade_behavior_diff_dates": sorted({row["date"] for row in trade_diffs}),
        "minimum_initial_rr": min(float(row["Initial_RR"]) for row in current_trade_rows),
        "invalid_initial_rr_dates": invalid_rr,
        "dynamic_target_events": [
            {
                "date": row["fecha"],
                "initial_target_ticks": float(row["Initial_TP_ticks"]),
                "final_target_ticks": float(row["Final_TP_ticks"]),
                "reason": row["Target_Modification_Reason"],
                "exit_reason": row["Exit_Reason"],
                "realized_ticks": tick_value(row),
            }
            for row in dynamic_rows
        ],
    }

    write_csv(
        args.output_dir / "required_field_diff.csv",
        field_diffs,
        ["date", "category", "field", "baseline", "current"],
    )
    write_csv(
        args.output_dir / "shared_field_diff.csv",
        shared_diffs,
        ["date", "field", "baseline", "current"],
    )
    write_csv(
        args.output_dir / "trade_behavior_diff.csv",
        trade_diffs,
        ["date", "field", "baseline", "current"],
    )
    write_csv(
        args.output_dir / "monthly_metrics_baseline.csv",
        monthly_metrics(list(baseline.values())),
        [
            "month",
            "trades",
            "wins",
            "losses",
            "wr",
            "pf",
            "expectancy_ticks",
            "net_ticks",
            "average_win_ticks",
            "average_loss_ticks",
            "mae_average_ticks",
            "mae_max_ticks",
            "mfe_average_ticks",
            "mfe_max_ticks",
            "balance_150k_6_contracts",
        ],
    )
    write_csv(
        args.output_dir / "monthly_metrics_current.csv",
        monthly_metrics(list(current.values())),
        [
            "month",
            "trades",
            "wins",
            "losses",
            "wr",
            "pf",
            "expectancy_ticks",
            "net_ticks",
            "average_win_ticks",
            "average_loss_ticks",
            "mae_average_ticks",
            "mae_max_ticks",
            "mfe_average_ticks",
            "mfe_max_ticks",
            "balance_150k_6_contracts",
        ],
    )
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary["status"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
