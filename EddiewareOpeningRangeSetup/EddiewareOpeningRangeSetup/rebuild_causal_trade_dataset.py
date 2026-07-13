from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from causal_feature_audit import (
    ALLOWED_FEATURE_COLUMNS,
    audit_feature_columns,
    audit_timestamp_order,
    classify_column,
    forbidden_reason,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LEGACY_DIR = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
    r"\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs\X10_R1"
)
DEFAULT_AUDIT_SUMMARY = BASE_DIR / "outputs" / "adversarial_audit_20260711_222029" / "audit_summary.json"
NY_TZ = ZoneInfo("America/New_York")

INPUT_FIELDS = [
    "trade_id",
    "Input_VERSION",
    "fecha",
    "decision_timestamp",
    "feature_timestamp",
    "entry_timestamp",
    "EntryBar",
    "Side",
    "Signal_Source",
    "Speed_Profile",
    "Side_AtEntry",
    "Signal_Source_AtEntry",
    "Speed_Profile_AtEntry",
    "Entry_price",
    "SL_price_AtEntry",
    "TP_price_AtEntry",
    "SL_ticks_AtEntry",
    "TP_ticks_AtEntry",
    "or_low",
    "or_high",
    "range",
    "OR_Low_AtEntry",
    "OR_High_AtEntry",
    "OR_Range_AtEntry",
    "VWAP_AtEntry",
    "Body_AtEntry",
    "Volume_AtEntry",
    "Delta_AtEntry",
    "Cumulative_Delta_AtEntry",
    "Cumulative_Delta_Source_AtEntry",
    "Cvd_Current_AtEntry",
    "Cvd_Peak_AtEntry",
    "Cvd_Pullback_Pct_AtEntry",
    "Cvd_Label_AtEntry",
    "Cvd_Total_Samples_AtEntry",
    "Previous_Volume_AtEntry",
    "Previous_Delta_AtEntry",
    "Volume_Increasing_AtEntry",
    "Delta_Change_AtEntry",
    "Delta_With_Side_AtEntry",
    "Price_Accepted_After_Imbalance_AtEntry",
    "Price_Rejected_After_Imbalance_AtEntry",
    "BreakOut_SPEED_AtEntry",
    "BreakOut_TICKS_PER_SEC_AtEntry",
    "Speed_Elapsed_SECONDS_AtEntry",
    "Speed_Replay_Fallback_AtEntry",
    "Speed_Timing_Source_AtEntry",
    "Range_OK_AtEntry",
    "Body_OK_AtEntry",
    "Volume_OK_AtEntry",
    "Delta_OK_AtEntry",
    "Time_OK_AtEntry",
    "VWAP_OK_AtEntry",
    "Speed_OK_AtEntry",
    "Score_AtEntry",
    "Raw_Speed_Label_AtEntry",
    "APlus_Structure_AtEntry",
    "APlus_Absorption_AtEntry",
    "APlus_Speed_AtEntry",
    "APlus_Speed_Setup_Confirmed_AtEntry",
    "Buy_Imbalance_Count_AtEntry",
    "Sell_Imbalance_Count_AtEntry",
    "Execution_Side_Imbalance_Count_AtEntry",
    "Imbalance_Group_3_AtEntry",
    "Imbalance_Group_Price_AtEntry",
    "Imbalance_Count_AtEntry",
    "Speed_Ignored_By_Structure_AtEntry",
    "feature_timestamp_utc",
    "entry_timestamp_utc",
]

RESULT_FIELDS = [
    "trade_id",
    "Result_VERSION",
    "fecha",
    "entry_timestamp",
    "outcome_timestamp",
    "ExitTime_NY",
    "Trade_Duration",
    "EntryBar",
    "Side",
    "Entry_price",
    "Result_Label",
    "Exit_price",
    "result_ticks",
    "MAE_ticks",
    "MFE_ticks",
    "Largest_MAE_pullback_ticks",
    "Largest_MFE_pullup_ticks",
    "Number_of_Pullbacks_during_Trade",
    "Number_of_PullUps_during_Trade",
    "Max_Speed_MAE_during_trade",
    "Max_Speed_MFE_during_trade",
    "SL_price_Final",
    "TP_price_Final",
    "SL_ticks_Final",
    "TP_ticks_Final",
    "Cvd_Current_Final",
    "Cvd_Peak_Final",
    "Cvd_Pullback_Pct_Final",
    "Cvd_Label_Final",
    "Cvd_Worst_Label_Final",
    "Cvd_Excelente_Count_Final",
    "Cvd_Normal_Count_Final",
    "Cvd_Advertencia_Count_Final",
    "Cvd_Riesgo_Reversion_Count_Final",
    "Cvd_Total_Samples_Final",
    "Cvd_Excelente_Pct_Final",
    "Cvd_Negative_Episodes_Final",
    "Cvd_Label_Changes_Final",
    "Dynamic_Alarm_Triggered",
    "TP_And_SL_Hit_Same_Update",
    "Result_After_Slippage_Ticks",
    "Volume_Increased_During_Trade",
    "Volume_Increase_Samples",
    "Volume_Observed_Samples",
    "Volume_Increasing_Pct_During_Trade",
    "Max_Delta_during_trade",
    "Min_Delta_during_trade",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Split legacy ORB rows into causal inputs and outcomes.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_LEGACY_DIR)
    parser.add_argument("--audit-summary", type=Path, default=DEFAULT_AUDIT_SUMMARY)
    parser.add_argument("--out-dir", type=Path, default=None)
    return parser.parse_args()


def fnum(value, default=np.nan):
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if text.startswith("+"):
        text = text[1:]
    if not text or text.upper() in {"OPEN", "TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def clean(value):
    return str(value or "").strip()


def is_trade(row):
    return bool(clean(row.get("Side")) and clean(row.get("Entry_price")))


def result_ticks(row):
    direct = fnum(row.get("result TP SL BE"))
    if math.isfinite(direct):
        return direct
    label = clean(row.get("Result_Label")).upper()
    if label == "BE":
        return 0.0
    if label == "TP":
        return abs(fnum(row.get("TP_ticks"), 0.0))
    if label == "SL":
        return -abs(fnum(row.get("SL_ticks"), 0.0))
    return 0.0


def normalize_time_text(text):
    text = clean(text)
    if not text:
        return ""
    if "." not in text:
        return text + ".000"
    main, frac = text.split(".", 1)
    return main + "." + (frac + "000")[:3]


def parse_ny_datetime(date_text, time_text):
    time_text = normalize_time_text(time_text)
    if not time_text:
        return None
    return datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=NY_TZ)


def iso_utc(dt):
    return dt.astimezone(timezone.utc).isoformat() if dt else ""


def trade_id(date_text, entry_timestamp):
    return f"{date_text}|{entry_timestamp}"


def read_legacy_rows(source_dir):
    rows = []
    for path in sorted(source_dir.glob("score_trade_result_*_NY.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            row = next(csv.DictReader(handle), {})
        match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
        row["source_file"] = path.name
        row["source_date"] = match.group(1) if match else clean(row.get("fecha"))
        if not clean(row.get("fecha")):
            row["fecha"] = row["source_date"]
        rows.append(row)
    return rows


def input_from_legacy(row):
    date_text = clean(row.get("fecha"))
    entry_time = normalize_time_text(row.get("EntryTime_NY_Milliseconds") or row.get("EntryTime_NY"))
    entry_dt = parse_ny_datetime(date_text, entry_time)
    tid = trade_id(date_text, entry_time)
    side = clean(row.get("Side"))
    signal_source = clean(row.get("Signal_Source"))
    speed_profile = clean(row.get("Speed_Profile")) or "Unknown"
    or_low = clean(row.get("or_low"))
    or_high = clean(row.get("or_high"))
    or_range = clean(row.get("range"))
    cumulative_delta = clean(row.get("Cumulative_Delta_entry"))
    out = {
        "trade_id": tid,
        "Input_VERSION": "reconstructed-causal-v1-from-legacy-v11",
        "fecha": date_text,
        "decision_timestamp": entry_time,
        "feature_timestamp": entry_time,
        "entry_timestamp": entry_time,
        "EntryBar": clean(row.get("EntryBar")),
        "Side": side,
        "Signal_Source": signal_source,
        "Speed_Profile": speed_profile,
        "Side_AtEntry": side,
        "Signal_Source_AtEntry": signal_source,
        "Speed_Profile_AtEntry": speed_profile,
        "Entry_price": clean(row.get("Entry_price")),
        "SL_price_AtEntry": clean(row.get("SL_price")),
        "TP_price_AtEntry": clean(row.get("TP_price")),
        "SL_ticks_AtEntry": clean(row.get("SL_ticks")),
        "TP_ticks_AtEntry": clean(row.get("TP_ticks")),
        "or_low": or_low,
        "or_high": or_high,
        "range": or_range,
        "OR_Low_AtEntry": or_low,
        "OR_High_AtEntry": or_high,
        "OR_Range_AtEntry": or_range,
        "VWAP_AtEntry": clean(row.get("VWAP_entry")),
        "Body_AtEntry": clean(row.get("Body")),
        "Volume_AtEntry": clean(row.get("Volume_entry")),
        "Delta_AtEntry": clean(row.get("Delta_entry")),
        "Cumulative_Delta_AtEntry": cumulative_delta,
        "Cumulative_Delta_Source_AtEntry": clean(row.get("Cumulative_Delta_Source")),
        "Cvd_Current_AtEntry": cumulative_delta,
        "Cvd_Peak_AtEntry": cumulative_delta,
        "Cvd_Pullback_Pct_AtEntry": "0",
        "Cvd_Label_AtEntry": "Excelente",
        "Cvd_Total_Samples_AtEntry": "1",
        "Previous_Volume_AtEntry": clean(row.get("Previous_Volume")),
        "Previous_Delta_AtEntry": clean(row.get("Previous_Delta")),
        "Volume_Increasing_AtEntry": clean(row.get("Volume_Increasing")),
        "Delta_Change_AtEntry": clean(row.get("Delta_Change")),
        "Delta_With_Side_AtEntry": clean(row.get("Delta_With_Side")),
        "Price_Accepted_After_Imbalance_AtEntry": clean(row.get("Price_Accepted_After_Imbalance")),
        "Price_Rejected_After_Imbalance_AtEntry": clean(row.get("Price_Rejected_After_Imbalance")),
        "BreakOut_SPEED_AtEntry": clean(row.get("BreakOut_SPEED")),
        "BreakOut_TICKS_PER_SEC_AtEntry": clean(row.get("BreakOut_TICKS_PER_SEC")),
        "Speed_Elapsed_SECONDS_AtEntry": clean(row.get("Speed_Elapsed_SECONDS")),
        "Speed_Replay_Fallback_AtEntry": clean(row.get("Speed_Replay_Fallback")),
        "Speed_Timing_Source_AtEntry": clean(row.get("Speed_Timing_Source")),
        "Range_OK_AtEntry": clean(row.get("Range_OK")),
        "Body_OK_AtEntry": clean(row.get("Body_OK")),
        "Volume_OK_AtEntry": clean(row.get("Volume_OK")),
        "Delta_OK_AtEntry": clean(row.get("Delta_OK")),
        "Time_OK_AtEntry": clean(row.get("Time_OK")),
        "VWAP_OK_AtEntry": clean(row.get("VWAP_OK")),
        "Speed_OK_AtEntry": clean(row.get("Speed_OK")),
        "Score_AtEntry": clean(row.get("score total")),
        "Raw_Speed_Label_AtEntry": clean(row.get("Raw_Speed_Label")),
        "APlus_Structure_AtEntry": clean(row.get("APlus_Structure")),
        "APlus_Absorption_AtEntry": clean(row.get("APlus_Absorption")),
        "APlus_Speed_AtEntry": clean(row.get("APlus_Speed")),
        "APlus_Speed_Setup_Confirmed_AtEntry": clean(row.get("APlus_Speed_Setup_Confirmed")),
        "Buy_Imbalance_Count_AtEntry": clean(row.get("Buy_Imbalance_Count")),
        "Sell_Imbalance_Count_AtEntry": clean(row.get("Sell_Imbalance_Count")),
        "Execution_Side_Imbalance_Count_AtEntry": clean(row.get("Execution_Side_Imbalance_Count")),
        "Imbalance_Group_3_AtEntry": clean(row.get("Imbalance_Group_3")),
        "Imbalance_Group_Price_AtEntry": clean(row.get("Imbalance_Group_Price")),
        "Imbalance_Count_AtEntry": clean(row.get("Imbalance_Count")),
        "Speed_Ignored_By_Structure_AtEntry": clean(row.get("Speed_Ignored_By_Structure")),
        "feature_timestamp_utc": iso_utc(entry_dt),
        "entry_timestamp_utc": iso_utc(entry_dt),
    }
    return out


def result_from_legacy(row, input_row):
    exit_time = normalize_time_text(row.get("ExitTime_NY_Milliseconds") or row.get("ExitTime_NY"))
    return {
        "trade_id": input_row["trade_id"],
        "Result_VERSION": "reconstructed-causal-v1-from-legacy-v11",
        "fecha": input_row["fecha"],
        "entry_timestamp": input_row["entry_timestamp"],
        "outcome_timestamp": exit_time,
        "ExitTime_NY": exit_time,
        "Trade_Duration": clean(row.get("Trade_Duration")),
        "EntryBar": input_row["EntryBar"],
        "Side": input_row["Side"],
        "Entry_price": input_row["Entry_price"],
        "Result_Label": clean(row.get("Result_Label")),
        "Exit_price": clean(row.get("Exit_price")),
        "result_ticks": f"{result_ticks(row):g}",
        "MAE_ticks": clean(row.get("MAE_ticks")),
        "MFE_ticks": clean(row.get("MFE_ticks")),
        "Largest_MAE_pullback_ticks": clean(row.get("Largest_MAE_pullback_ticks")),
        "Largest_MFE_pullup_ticks": clean(row.get("Largest_MFE_pullup_ticks")),
        "Number_of_Pullbacks_during_Trade": clean(row.get("Number_of_Pullbacks_during_Trade")),
        "Number_of_PullUps_during_Trade": clean(row.get("Number_of_PullUps_during_Trade")),
        "Max_Speed_MAE_during_trade": clean(row.get("Max_Speed_MAE_during_trade")),
        "Max_Speed_MFE_during_trade": clean(row.get("Max_Speed_MFE_during_trade")),
        "SL_price_Final": clean(row.get("SL_price")),
        "TP_price_Final": clean(row.get("TP_price")),
        "SL_ticks_Final": clean(row.get("SL_ticks")),
        "TP_ticks_Final": clean(row.get("TP_ticks")),
        "Cvd_Current_Final": clean(row.get("Cvd_Current")),
        "Cvd_Peak_Final": clean(row.get("Cvd_Peak")),
        "Cvd_Pullback_Pct_Final": clean(row.get("Cvd_Pullback_Pct")),
        "Cvd_Label_Final": clean(row.get("Cvd_Pullback_Label")),
        "Cvd_Worst_Label_Final": clean(row.get("Cvd_Worst_Label")),
        "Cvd_Excelente_Count_Final": clean(row.get("Cvd_Excelente_Count")),
        "Cvd_Normal_Count_Final": clean(row.get("Cvd_Normal_Count")),
        "Cvd_Advertencia_Count_Final": clean(row.get("Cvd_Advertencia_Count")),
        "Cvd_Riesgo_Reversion_Count_Final": clean(row.get("Cvd_Riesgo_Reversion_Count")),
        "Cvd_Total_Samples_Final": clean(row.get("Cvd_Total_Samples")),
        "Cvd_Excelente_Pct_Final": clean(row.get("Cvd_Excelente_Pct")),
        "Cvd_Negative_Episodes_Final": clean(row.get("Cvd_Negative_Episodes")),
        "Cvd_Label_Changes_Final": clean(row.get("Cvd_Label_Changes")),
        "Dynamic_Alarm_Triggered": clean(row.get("Dynamic_Alarm_Triggered")),
        "TP_And_SL_Hit_Same_Update": clean(row.get("TP_And_SL_Hit_Same_Update")),
        "Result_After_Slippage_Ticks": clean(row.get("Result_After_Slippage_Ticks")),
        "Volume_Increased_During_Trade": clean(row.get("Volume_Increased_During_Trade")),
        "Volume_Increase_Samples": clean(row.get("Volume_Increase_Samples")),
        "Volume_Observed_Samples": clean(row.get("Volume_Observed_Samples")),
        "Volume_Increasing_Pct_During_Trade": clean(row.get("Volume_Increasing_Pct_During_Trade")),
        "Max_Delta_during_trade": clean(row.get("Max_Delta_during_trade")),
        "Min_Delta_during_trade": clean(row.get("Min_Delta_during_trade")),
    }


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def max_dd(values):
    values = np.asarray(values, dtype=float)
    curve = np.cumsum(values)
    peaks = np.maximum.accumulate(np.r_[0.0, curve])[:-1]
    return float(np.max(peaks - curve)) if len(values) else 0.0


def profit_factor(values):
    values = np.asarray(values, dtype=float)
    gross_win = values[values > 0].sum()
    gross_loss = -values[values < 0].sum()
    return float(gross_win / gross_loss) if gross_loss > 0 else (math.inf if gross_win > 0 else math.nan)


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


def summarize(values, months):
    values = np.asarray(values, dtype=float)
    months = list(months)
    if len(values) == 0:
        return {"trades": 0, "wr": math.nan, "pf": math.nan, "expectancy": math.nan, "profit": 0.0, "dd": 0.0}
    max_w, max_l = streaks(values)
    month_count = len(set(months))
    return {
        "trades": int(len(values)),
        "months": month_count,
        "trades_per_month": float(len(values) / month_count) if month_count else math.nan,
        "wr": float((values > 0).mean() * 100),
        "pf": profit_factor(values),
        "expectancy": float(values.mean()),
        "profit": float(values.sum()),
        "dd": max_dd(values),
        "max_w_streak": max_w,
        "max_l_streak": max_l,
    }


def simulate_tp_sl(results, tp=100.0, sl=40.0):
    actual = np.array([fnum(row.get("result_ticks"), 0.0) for row in results], dtype=float)
    mfe = np.array([fnum(row.get("MFE_ticks"), np.nan) for row in results], dtype=float)
    mae = np.array([fnum(row.get("MAE_ticks"), np.nan) for row in results], dtype=float)
    out = np.clip(actual, -sl, tp)
    both = (mfe >= tp) & (mae >= sl)
    hit_tp = (mfe >= tp) & ~both
    hit_sl = (mae >= sl) | both
    out[hit_tp] = tp
    out[hit_sl] = -sl
    return out


def comparison_rows(inputs, results, audit_summary_path):
    result_by_id = {row["trade_id"]: row for row in results}
    joined = [(row, result_by_id[row["trade_id"]]) for row in inputs if row["trade_id"] in result_by_id]
    months = [inp["fecha"][:7] for inp, _ in joined]
    sim = simulate_tp_sl([res for _, res in joined])
    final_cvd_mask = np.array([res.get("Cvd_Label_Final") == "Excelente" for _, res in joined], dtype=bool)
    entry_cvd_mask = np.array([inp.get("Cvd_Label_AtEntry") == "Excelente" for inp, _ in joined], dtype=bool)

    rows = []
    if audit_summary_path.exists():
        audit = json.loads(audit_summary_path.read_text(encoding="utf-8"))
        current = audit.get("current_summary", {})
        rows.append({"case": "before_leaky_final_CVD_Excelente_TP100_SL40", **current})

    rows.append({"case": "recomputed_legacy_final_CVD_Excelente_TP100_SL40", **summarize(sim[final_cvd_mask], np.array(months)[final_cvd_mask])})
    rows.append({"case": "after_causal_Cvd_Label_AtEntry_Excelente_TP100_SL40", **summarize(sim[entry_cvd_mask], np.array(months)[entry_cvd_mask])})
    rows.append({"case": "after_causal_all_entry_trades_TP100_SL40", **summarize(sim, months)})
    return rows


def lifecycle_rows(legacy_rows):
    header = list(legacy_rows[0].keys()) if legacy_rows else []
    variables = sorted(set(header) | set(INPUT_FIELDS) | set(RESULT_FIELDS))
    rows = []
    for variable in variables:
        classification, reason = classify_column(variable)
        in_input = variable in INPUT_FIELDS
        in_result = variable in RESULT_FIELDS
        if in_input and not in_result:
            birth = "CreateTrade / ScoreTradeSignal snapshot"
            updates = "No despues de entry"
            frozen = "SI"
        elif in_result:
            birth = "Trade lifecycle / close"
            updates = "Si, durante o al cierre"
            frozen = "NO como feature"
        else:
            birth = "Legacy monolithic CSV"
            updates = "Revisar en codigo"
            frozen = "NO verificado"
        usable = "SI" if variable in ALLOWED_FEATURE_COLUMNS else "NO"
        rows.append(
            {
                "Variable": variable,
                "Nacimiento": birth,
                "Actualizaciones": updates,
                "Congelada": frozen,
                "Usable": usable,
                "Clasificacion": classification,
                "Motivo": reason,
            }
        )
    return rows


def suspected_rows(legacy_rows):
    rows = []
    seen = set()
    for column in (legacy_rows[0].keys() if legacy_rows else []):
        reason = forbidden_reason(column)
        classification, class_reason = classify_column(column)
        if reason or classification in {"DYNAMIC", "LEAKED", "SUSPECT"}:
            rows.append(
                {
                    "source_type": "legacy_csv_column",
                    "source": "score_trade_result_*_NY.csv",
                    "line": "",
                    "name": column,
                    "classification": classification,
                    "reason": reason or class_reason,
                }
            )
            seen.add(("legacy_csv_column", column))

    skip_parts = {"bin", "obj", "outputs", "audit_snapshot", "__pycache__", "catboost_info"}
    for pattern in ("*.py", "*.cs"):
        for path in BASE_DIR.rglob(pattern):
            if any(part in skip_parts for part in path.parts):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for line_no, line in enumerate(lines, 1):
                reason = forbidden_reason(line)
                if reason:
                    key = ("code_match", str(path), line_no)
                    if key in seen:
                        continue
                    rows.append(
                        {
                            "source_type": "code_match",
                            "source": str(path.relative_to(BASE_DIR)),
                            "line": line_no,
                            "name": line.strip()[:180],
                            "classification": "SUSPECT",
                            "reason": reason,
                        }
                    )
                    seen.add(key)
    return rows


def markdown_metric_table(rows):
    cols = ["case", "trades", "months", "trades_per_month", "wr", "pf", "expectancy", "profit", "dd", "max_w_streak", "max_l_streak"]
    out = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in rows:
        cells = []
        for col in cols:
            val = row.get(col, "")
            if isinstance(val, float):
                if math.isnan(val):
                    cells.append("")
                elif math.isinf(val):
                    cells.append("inf")
                else:
                    cells.append(f"{val:.2f}")
            else:
                cells.append(str(val))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def write_report(out_dir, comparison, input_count, result_count, suspected_count):
    before = next((row for row in comparison if row["case"].startswith("before_")), {})
    after = next((row for row in comparison if row["case"].startswith("after_causal_Cvd_Label")), {})
    pf_drop = None
    if before and after:
        pf_drop = fnum(before.get("pf")) - fnum(after.get("pf"))
    report = [
        "# LOOKAHEAD FIX REPORT",
        "",
        "## Veredicto",
        "",
        "El resultado anterior queda invalidado como edge causal porque `Cvd_Pullback_Label` era un estado final/intratrade. El pipeline ahora separa inputs congelados de outcomes y el optimizador aborta si intenta usar columnas futuras.",
        "",
        "## Donde estaba el bug",
        "",
        "- `ATASScoreTradeResultExporter.cs:348`: nace el trade en `CreateTrade(...)`.",
        "- `ATASScoreTradeResultExporter.cs:447`: el nuevo `TradeInputSnapshot` congela CVD/Delta/VWAP/OR/ranking al entry.",
        "- `ATASScoreTradeResultExporter.cs:1005`: `UpdateCvdPullback(...)` actualiza CVD durante la vida del trade.",
        "- `ATASScoreTradeResultExporter.cs:2482`: se escribe `trade_inputs.csv` sin reescribir features.",
        "- `ATASScoreTradeResultExporter.cs:2676`: se escribe `trade_results.csv` con outcomes y estados finales.",
        "",
        "## Correccion aplicada",
        "",
        "- `Cvd_Label_AtEntry` se congela en `Excelente` al crear el trade, igual que el estado real disponible en ese instante.",
        "- `Cvd_Label_Final` queda en `trade_results.csv` y no puede entrar al optimizador.",
        "- MFE, MAE, exit, profit, resultado, alarmas dinamicas y campos `*_Final` se tratan como outcome o variables dinamicas.",
        "- `edge_optimization_fast.py` ya solo carga `trade_inputs.csv` + `trade_results.csv` y pasa por `audit_feature_columns()`.",
        "",
        "## Comparacion antes/despues",
        "",
        markdown_metric_table(comparison),
        "",
        f"Caida estimada de PF al quitar el CVD final: {pf_drop:.2f}" if pf_drop is not None and math.isfinite(pf_drop) else "Caida de PF no disponible.",
        "",
        "## Entregables generados",
        "",
        f"- Dataset causal: `{out_dir}`",
        f"- Inputs: `{out_dir / 'trade_inputs.csv'}` ({input_count} trades)",
        f"- Results: `{out_dir / 'trade_results.csv'}` ({result_count} trades)",
        f"- Comparacion: `{out_dir / 'causal_backtest_comparison.csv'}`",
        f"- Variables sospechosas: `{BASE_DIR / 'SuspectedLeakageVariables.csv'}` ({suspected_count} filas)",
        f"- Ciclo de vida: `{BASE_DIR / 'feature_lifecycle.csv'}`",
        "",
        "## Riesgo restante",
        "",
        "La reconstruccion usa CSV legacy para separar columnas, pero la prueba definitiva debe venir de una corrida nueva de ATAS con el DLL actualizado escribiendo `trade_inputs.csv` y `trade_results.csv` nativos. No se optimizo nada despues de ver el resultado corregido.",
    ]
    (BASE_DIR / "LOOKAHEAD_FIX_REPORT.md").write_text("\n".join(report), encoding="utf-8")


def main():
    args = parse_args()
    out_dir = args.out_dir or (BASE_DIR / "outputs" / f"causal_dataset_{datetime.now():%Y%m%d_%H%M%S}")
    legacy_rows = read_legacy_rows(args.source_dir)
    inputs, results = [], []
    for row in legacy_rows:
        if not is_trade(row):
            continue
        input_row = input_from_legacy(row)
        result_row = result_from_legacy(row, input_row)
        inputs.append(input_row)
        results.append(result_row)

    audit_timestamp_order(inputs)
    audit_feature_columns(sorted(ALLOWED_FEATURE_COLUMNS & set(INPUT_FIELDS)))

    write_csv(out_dir / "trade_inputs.csv", inputs, INPUT_FIELDS)
    write_csv(out_dir / "trade_results.csv", results, RESULT_FIELDS)

    comparison = comparison_rows(inputs, results, args.audit_summary)
    comparison_fields = sorted({key for row in comparison for key in row.keys()})
    write_csv(out_dir / "causal_backtest_comparison.csv", comparison, comparison_fields)

    lifecycle = lifecycle_rows(legacy_rows)
    write_csv(BASE_DIR / "feature_lifecycle.csv", lifecycle, list(lifecycle[0].keys()))
    write_csv(out_dir / "feature_lifecycle.csv", lifecycle, list(lifecycle[0].keys()))

    suspected = suspected_rows(legacy_rows)
    write_csv(BASE_DIR / "SuspectedLeakageVariables.csv", suspected, list(suspected[0].keys()))
    write_csv(out_dir / "SuspectedLeakageVariables.csv", suspected, list(suspected[0].keys()))

    summary = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_dir": str(args.source_dir),
        "out_dir": str(out_dir),
        "legacy_rows": len(legacy_rows),
        "trade_inputs": len(inputs),
        "trade_results": len(results),
        "comparison": comparison,
        "feature_audit": "PASS",
    }
    (out_dir / "causal_dataset_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(out_dir, comparison, len(inputs), len(results), len(suspected))
    print(out_dir)


if __name__ == "__main__":
    main()
