#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import pandas as pd
import numpy as np

EXCELS_DIR = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\footprints_generados"
)

ONLY_FILE_NAME = "metric results.xlsx"
OUTPUT_FILE = "metric_results_noLookAhead_output.xlsx"

TARGET_PASS_RATE = 0.80


def normalize_columns(df):
    df.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for c in df.columns
    ]
    return df


def find_column(df, possible_names):
    for c in df.columns:
        for p in possible_names:
            if p in c:
                return c
    return None


def safe_numeric(series):
    return pd.to_numeric(series, errors="coerce")


def main():
    target_file = EXCELS_DIR / ONLY_FILE_NAME

    if not target_file.exists():
        raise FileNotFoundError(f"\nNo existe el archivo:\n{target_file}")

    print("\nLEYENDO:", target_file)

    xls = pd.ExcelFile(target_file)

    if "Detail" in xls.sheet_names:
        df = pd.read_excel(target_file, sheet_name="Detail")
    else:
        df = pd.read_excel(target_file)

    print(f"Rows originales: {len(df)}")

    df = normalize_columns(df)

    range_col = find_column(df, ["range_ticks", "or_ticks", "range"])
    breakout_body_col = find_column(df, ["breakout_body", "body_breakout", "body_ticks", "breakout_ticks"])
    volume_col = find_column(df, ["volume_breakout", "breakout_volume", "volume"])
    delta_col = find_column(df, ["delta_breakout", "breakout_delta", "abs_delta", "delta"])
    signal_time_col = find_column(df, ["signal_time", "breakout_time", "time"])
    vwap_col = find_column(df, ["vwap", "vwap_side", "vwap_context"])

    required = {
        "range_ticks": range_col,
        "breakout_body": breakout_body_col,
        "vwap": vwap_col,
    }

    missing = [k for k, v in required.items() if v is None]

    if missing:
        print("\nCOLUMNAS DETECTADAS:")
        for c in df.columns:
            print(" -", c)

        raise ValueError(f"\nFaltan columnas necesarias: {missing}")

    df[range_col] = safe_numeric(df[range_col])
    df[breakout_body_col] = safe_numeric(df[breakout_body_col])

    if volume_col:
        df[volume_col] = safe_numeric(df[volume_col])

    if delta_col:
        df[delta_col] = safe_numeric(df[delta_col])

    if signal_time_col:
        df["_signal_time"] = df[signal_time_col].astype(str).str.strip()
    else:
        df["_signal_time"] = ""

    def vwap_ok(v):
        s = str(v).lower()

        bad_words = [
            "against",
            "wrong",
            "below_short",
            "above_long",
            "invalid",
            "false",
            "no",
        ]

        return not any(b in s for b in bad_words)

    df["_vwap_ok"] = df[vwap_col].apply(vwap_ok)

    # =====================================================
    # SCORE FLEXIBLE
    # =====================================================

    df["_score"] = 0

    df["_range_ok"] = (
        (df[range_col] >= 40) &
        (df[range_col] <= 350)
    )

    df["_body_ok"] = df[breakout_body_col] >= 10

    df["_volume_ok"] = True
    if volume_col:
        df["_volume_ok"] = df[volume_col] >= 800

    df["_delta_ok"] = True
    if delta_col:
        df["_delta_ok"] = df[delta_col].abs() >= 25

    df["_time_ok"] = True
    if signal_time_col:
        df["_time_ok"] = df["_signal_time"] <= "09:50"

    df.loc[df["_vwap_ok"], "_score"] += 2
    df.loc[df["_range_ok"], "_score"] += 1
    df.loc[df["_body_ok"], "_score"] += 1
    df.loc[df["_volume_ok"], "_score"] += 1
    df.loc[df["_delta_ok"], "_score"] += 1
    df.loc[df["_time_ok"], "_score"] += 1

    # =====================================================
    # CORTE AUTOMATICO PARA PASAR AL MENOS 80%
    # =====================================================

    total_rows = len(df)
    target_count = int(np.ceil(total_rows * TARGET_PASS_RATE))

    df_sorted = df.sort_values(
        by="_score",
        ascending=False
    ).copy()

    cutoff_score = df_sorted.iloc[target_count - 1]["_score"]

    df["_valid_trade"] = df["_score"] >= cutoff_score

    # Si pasan más de 80% por empate de score, está bien.
    # La idea es no filtrar más del 20%.

    df["FILTER_SCORE"] = df["_score"]
    df["FILTER_RESULT"] = np.where(
        df["_valid_trade"],
        "VALID TRADE",
        "NO TRADE"
    )

    valid_df = df[df["_valid_trade"]].copy()
    no_trade_df = df[~df["_valid_trade"]].copy()

    summary = pd.DataFrame({
        "metric": [
            "total_rows",
            "target_pass_rate",
            "target_min_valid_trades",
            "actual_valid_trades",
            "actual_no_trade",
            "actual_valid_pct",
            "auto_cutoff_score",
            "range_min",
            "range_max",
            "body_min",
            "volume_min",
            "abs_delta_min",
            "time_max",
        ],
        "value": [
            total_rows,
            TARGET_PASS_RATE,
            target_count,
            len(valid_df),
            len(no_trade_df),
            round(len(valid_df) / total_rows * 100, 2),
            cutoff_score,
            40,
            350,
            10,
            800,
            25,
            "09:50",
        ]
    })

    diagnostic = pd.DataFrame({
        "filter": [
            "vwap_ok",
            "range_ok",
            "body_ok",
            "volume_ok",
            "delta_ok",
            "time_ok",
        ],
        "passed": [
            int(df["_vwap_ok"].sum()),
            int(df["_range_ok"].sum()),
            int(df["_body_ok"].sum()),
            int(df["_volume_ok"].sum()),
            int(df["_delta_ok"].sum()),
            int(df["_time_ok"].sum()),
        ],
        "passed_pct": [
            round(df["_vwap_ok"].mean() * 100, 2),
            round(df["_range_ok"].mean() * 100, 2),
            round(df["_body_ok"].mean() * 100, 2),
            round(df["_volume_ok"].mean() * 100, 2),
            round(df["_delta_ok"].mean() * 100, 2),
            round(df["_time_ok"].mean() * 100, 2),
        ]
    })

    temp_output = EXCELS_DIR / ("TEMP_" + OUTPUT_FILE)
    final_output = EXCELS_DIR / OUTPUT_FILE

    with pd.ExcelWriter(temp_output, engine="openpyxl") as writer:
        valid_df.to_excel(writer, sheet_name="VALID_TRADES", index=False)
        no_trade_df.to_excel(writer, sheet_name="NO_TRADE", index=False)
        summary.to_excel(writer, sheet_name="SUMMARY", index=False)
        diagnostic.to_excel(writer, sheet_name="DIAGNOSTIC", index=False)

    temp_output.replace(final_output)

    print("\n" + "=" * 60)
    print("RESULTADO FINAL")
    print("=" * 60)
    print(f"Total rows     : {total_rows}")
    print(f"Valid trades   : {len(valid_df)}")
    print(f"NO TRADE       : {len(no_trade_df)}")
    print(f"Valid %        : {round(len(valid_df) / total_rows * 100, 2)}%")
    print(f"Cutoff score   : {cutoff_score}")
    print("\nArchivo generado:")
    print(final_output)


if __name__ == "__main__":
    main()