from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

from causal_feature_audit import audit_feature_columns, audit_timestamp_order
from edge_optimization_fast import CAUSAL_FEATURE_COLUMNS, simulate_tp_sl


BASE_DIR = Path(__file__).resolve().parent
TP_GRID = np.array([40, 60, 80, 100, 120, 150], dtype=float)
SL_GRID = np.array([30, 40, 50, 60, 70, 80], dtype=float)
OR_THRESHOLDS = [80, 100, 120, 140, 160, 180, 200, 240]
SCORE_THRESHOLDS = [6, 7, 8, 9]


def fnum(value, default=np.nan):
    text = str(value or "").strip().replace("+", "")
    if not text or text.upper() in {"OPEN", "TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def result_ticks(value):
    text = str(value or "").strip().upper()
    if text == "BE":
        return 0.0
    return fnum(value, 0.0)


def newest_causal_dir():
    candidates = sorted((BASE_DIR / "outputs").glob("causal_dataset_*"), reverse=True)
    for candidate in candidates:
        if (candidate / "trade_inputs.csv").exists() and (candidate / "trade_results.csv").exists():
            return candidate
    raise RuntimeError("No causal_dataset_* found. Run rebuild_causal_trade_dataset.py first.")


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def join_rows(causal_dir):
    inputs = read_csv(causal_dir / "trade_inputs.csv")
    results = read_csv(causal_dir / "trade_results.csv")
    audit_timestamp_order(inputs)
    audit_feature_columns(CAUSAL_FEATURE_COLUMNS)
    by_id = {row["trade_id"]: row for row in results}
    rows = []
    for inp in inputs:
        res = by_id.get(inp.get("trade_id"))
        if not res:
            continue
        date_text = inp["fecha"]
        year = int(date_text[:4])
        month = date_text[:7]
        rows.append(
            {
                "date": date_text,
                "year": year,
                "month": month,
                "quarter": f"{year}-Q{((int(date_text[5:7]) - 1) // 3) + 1}",
                "side": inp.get("Side_AtEntry") or inp.get("Side") or "",
                "speed": inp.get("Speed_Profile_AtEntry") or "Unknown",
                "score": fnum(inp.get("Score_AtEntry")),
                "or_range": fnum(inp.get("OR_Range_AtEntry") or inp.get("range")),
                "range_ok": str(inp.get("Range_OK_AtEntry")).upper() == "TRUE",
                "body_ok": str(inp.get("Body_OK_AtEntry")).upper() == "TRUE",
                "volume_ok": str(inp.get("Volume_OK_AtEntry")).upper() == "TRUE",
                "delta_ok": str(inp.get("Delta_OK_AtEntry")).upper() == "TRUE",
                "vwap_ok": str(inp.get("VWAP_OK_AtEntry")).upper() == "TRUE",
                "speed_ok": str(inp.get("Speed_OK_AtEntry")).upper() == "TRUE",
                "price_accepted": str(inp.get("Price_Accepted_After_Imbalance_AtEntry")).upper() == "TRUE",
                "price_rejected": str(inp.get("Price_Rejected_After_Imbalance_AtEntry")).upper() == "TRUE",
                "aplus_speed": str(inp.get("APlus_Speed_AtEntry")).upper() == "TRUE",
                "mfe": fnum(res.get("MFE_ticks")),
                "mae": fnum(res.get("MAE_ticks")),
                "actual": result_ticks(res.get("result_ticks")),
            }
        )
    if not rows:
        raise RuntimeError(f"No joined rows in {causal_dir}")
    return rows


def arrays(rows):
    return {key: np.array([row[key] for row in rows]) for key in rows[0]}


def max_dd(values):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return 0.0
    curve = np.cumsum(values)
    peak = np.maximum.accumulate(np.r_[0.0, curve])[:-1]
    return float(np.max(peak - curve))


def pf(values):
    values = np.asarray(values, dtype=float)
    wins = values[values > 0].sum()
    losses = -values[values < 0].sum()
    return float(wins / losses) if losses > 0 else (math.inf if wins > 0 else math.nan)


def streaks(values):
    max_w = max_l = cur_w = cur_l = 0
    for value in values:
        if value > 0:
            cur_w += 1
            cur_l = 0
        elif value < 0:
            cur_l += 1
            cur_w = 0
        else:
            cur_w = cur_l = 0
        max_w = max(max_w, cur_w)
        max_l = max(max_l, cur_l)
    return max_w, max_l


def summary(values, months=None):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return {"trades": 0, "wr": math.nan, "pf": math.nan, "expectancy": math.nan, "profit": 0.0, "dd": 0.0}
    max_w, max_l = streaks(values)
    month_count = len(set(months)) if months is not None else 0
    return {
        "trades": int(len(values)),
        "months": int(month_count),
        "trades_per_month": float(len(values) / month_count) if month_count else math.nan,
        "wr": float((values > 0).mean() * 100),
        "pf": pf(values),
        "expectancy": float(values.mean()),
        "profit": float(values.sum()),
        "dd": max_dd(values),
        "max_w_streak": max_w,
        "max_l_streak": max_l,
    }


def monthly_quality(data, mask, result):
    month_rows = []
    for month in sorted(set(data["month"][mask])):
        mm = mask & (data["month"] == month)
        s = summary(result[mm])
        month_rows.append(s)
    finite_pf = np.array([r["pf"] for r in month_rows if math.isfinite(r["pf"])], dtype=float)
    bad_months = sum(1 for r in month_rows if math.isfinite(r["pf"]) and r["pf"] < 1)
    return {
        "active_months": len(month_rows),
        "monthly_pf_median": float(np.median(finite_pf)) if len(finite_pf) else math.nan,
        "bad_months_pf_lt_1": bad_months,
    }


def candidate_masks(data):
    n = len(data["date"])
    out = [("ALL", np.ones(n, dtype=bool))]
    for side in sorted(set(data["side"])):
        out.append((f"side={side}", data["side"] == side))
    for speed in sorted(set(data["speed"])):
        out.append((f"speed={speed}", data["speed"] == speed))
    for score in SCORE_THRESHOLDS:
        out.append((f"score>={score}", data["score"].astype(float) >= score))
    for threshold in OR_THRESHOLDS:
        out.append((f"OR>={threshold}", data["or_range"].astype(float) >= threshold))
        out.append((f"OR<={threshold}", data["or_range"].astype(float) <= threshold))
    for flag in ["range_ok", "body_ok", "volume_ok", "delta_ok", "vwap_ok", "speed_ok", "price_accepted", "price_rejected", "aplus_speed"]:
        out.append((f"{flag}=TRUE", data[flag].astype(bool)))
    for score in SCORE_THRESHOLDS:
        for threshold in OR_THRESHOLDS:
            out.append((f"score>={score} AND OR>={threshold}", (data["score"].astype(float) >= score) & (data["or_range"].astype(float) >= threshold)))
            out.append((f"score>={score} AND OR<={threshold}", (data["score"].astype(float) >= score) & (data["or_range"].astype(float) <= threshold)))
    for side in sorted(set(data["side"])):
        for score in SCORE_THRESHOLDS:
            out.append((f"side={side} AND score>={score}", (data["side"] == side) & (data["score"].astype(float) >= score)))
    dedup = {}
    for name, mask in out:
        key = mask.tobytes()
        dedup.setdefault(key, (name, mask))
    return list(dedup.values())


def robust_score(train_summary, quality):
    if train_summary["trades"] < 50 or train_summary["expectancy"] <= 0:
        return -math.inf
    pf_cap = min(train_summary["pf"], 3.0) if math.isfinite(train_summary["pf"]) else 3.0
    penalty = 1.0 + quality["bad_months_pf_lt_1"] / max(quality["active_months"], 1)
    if math.isfinite(quality["monthly_pf_median"]) and quality["monthly_pf_median"] < 1:
        penalty += 0.75
    return train_summary["expectancy"] * math.sqrt(train_summary["trades"]) * pf_cap / penalty


def choose_on_train(data, train_mask, masks):
    best = None
    actual = data["actual"].astype(float)
    for mask_name, base_mask in masks:
        mask = train_mask & base_mask
        if int(mask.sum()) < 50:
            continue
        actual_row = summary(actual[mask], data["month"][mask])
        quality = monthly_quality(data, mask, actual)
        candidates = [("actual", "", "", actual, actual_row, quality)]
        for tp in TP_GRID:
            for sl in SL_GRID:
                if tp < sl:
                    continue
                simulated = simulate_tp_sl(data, base_mask, tp, sl)
                train_s = summary(simulated[mask], data["month"][mask])
                train_q = monthly_quality(data, mask, simulated)
                candidates.append(("sim", int(tp), int(sl), simulated, train_s, train_q))
        for mode, tp, sl, result, train_s, train_q in candidates:
            score = robust_score(train_s, train_q)
            if best is None or score > best["selection_score"]:
                best = {
                    "filter": mask_name,
                    "mode": mode,
                    "tp": tp,
                    "sl": sl,
                    "result": result,
                    "train_summary": train_s,
                    "train_quality": train_q,
                    "selection_score": score,
                }
    if best is None:
        raise RuntimeError("No candidate passed minimum training requirements.")
    return best


def walk_forward(data):
    masks = candidate_masks(data)
    years = sorted(set(data["year"].astype(int)))
    fold_rows = []
    oos_values = []
    oos_months = []
    selected = []
    for test_year in years[1:]:
        train_mask = data["year"].astype(int) < test_year
        test_mask = data["year"].astype(int) == test_year
        if int(train_mask.sum()) < 80 or int(test_mask.sum()) < 20:
            continue
        choice = choose_on_train(data, train_mask, masks)
        test_filter = dict(masks)[choice["filter"]]
        final_test_mask = test_mask & test_filter
        result = choice["result"]
        train_s = choice["train_summary"]
        test_s = summary(result[final_test_mask], data["month"][final_test_mask])
        fold = {
            "test_year": int(test_year),
            "filter": choice["filter"],
            "tp": choice["tp"],
            "sl": choice["sl"],
            "train_trades": train_s["trades"],
            "train_wr": train_s["wr"],
            "train_pf": train_s["pf"],
            "train_exp": train_s["expectancy"],
            "train_bad_months": choice["train_quality"]["bad_months_pf_lt_1"],
            "oos_trades": test_s["trades"],
            "oos_wr": test_s["wr"],
            "oos_pf": test_s["pf"],
            "oos_exp": test_s["expectancy"],
            "oos_profit": test_s["profit"],
            "oos_dd": test_s["dd"],
        }
        fold_rows.append(fold)
        selected.append(choice["filter"])
        if test_s["trades"]:
            oos_values.extend(result[final_test_mask].tolist())
            oos_months.extend(data["month"][final_test_mask].tolist())
    combined = summary(np.array(oos_values, dtype=float), oos_months)
    return fold_rows, combined, Counter(selected)


def section_plan(rows):
    sections = []
    grouped = {}
    for row in rows:
        grouped.setdefault(row["quarter"], []).append(row["date"])
    for quarter, dates in sorted(grouped.items()):
        sections.append(
            {
                "section": quarter,
                "from_date": min(dates),
                "to_date": max(dates),
                "sessions_with_trade_in_legacy": len(dates),
            }
        )
    return sections


def write_csv(path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value, digits=2):
    if value is None:
        return "N/A"
    if isinstance(value, int):
        return str(value)
    try:
        value = float(value)
        if math.isnan(value):
            return "N/A"
        if math.isinf(value):
            return "inf"
        return f"{value:.{digits}f}"
    except Exception:
        return str(value)


def md_table(rows, cols):
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(fmt(row.get(col)) for col in cols) + " |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--causal-dir", type=Path, default=None)
    args = parser.parse_args()

    causal_dir = args.causal_dir or newest_causal_dir()
    out_dir = BASE_DIR / "outputs" / f"causal_section_walkforward_{datetime.now():%Y%m%d_%H%M%S}"
    rows = join_rows(causal_dir)
    data = arrays(rows)
    folds, combined, selected_counts = walk_forward(data)
    sections = section_plan(rows)

    write_csv(out_dir / "walkforward_folds.csv", folds)
    write_csv(out_dir / "section_run_plan.csv", sections)

    gate_pass = (
        combined["trades"] >= 80
        and combined["pf"] >= 1.4
        and combined["expectancy"] > 5
        and sum(1 for fold in folds if fold["oos_exp"] <= 0 or fold["oos_pf"] < 1) <= 1
    )

    report = [
        "# Causal Section Walk-Forward",
        "",
        f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Causal dataset: `{causal_dir}`",
        "",
        "## Rule",
        "",
        "Selection is made only with prior years. The next year is out-of-sample and is not used to repair the model.",
        "",
        "## Combined OOS",
        "",
        md_table([{**combined}], ["trades", "months", "trades_per_month", "wr", "pf", "expectancy", "profit", "dd", "max_w_streak", "max_l_streak"]),
        "",
        f"Gate to launch full 2022-2026 replay: {'PASS' if gate_pass else 'FAIL'}",
        "",
        "## Folds",
        "",
        md_table(folds, ["test_year", "filter", "tp", "sl", "train_trades", "train_pf", "train_exp", "train_bad_months", "oos_trades", "oos_wr", "oos_pf", "oos_exp", "oos_profit", "oos_dd"]),
        "",
        "## Selected Pattern Stability",
        "",
        "\n".join(f"- `{name}`: {count} fold(s)" for name, count in selected_counts.most_common()) or "N/A",
        "",
        "## First Replay Section",
        "",
        "Use the earliest section first, then scale only if the fresh v12 causal files agree with the offline expectation.",
        "",
        md_table(sections[:8], ["section", "from_date", "to_date", "sessions_with_trade_in_legacy"]),
    ]
    (out_dir / "README.md").write_text("\n".join(report), encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "causal_dataset": str(causal_dir),
                "output_dir": str(out_dir),
                "gate_pass": gate_pass,
                "combined_oos": combined,
                "selected_patterns": dict(selected_counts),
                "first_section": sections[0] if sections else None,
            },
            indent=2,
            ensure_ascii=False,
            default=lambda x: None if isinstance(x, float) and math.isnan(x) else x,
        ),
        encoding="utf-8",
    )
    print(out_dir / "README.md")
    print(f"gate_pass={gate_pass}")


if __name__ == "__main__":
    main()
