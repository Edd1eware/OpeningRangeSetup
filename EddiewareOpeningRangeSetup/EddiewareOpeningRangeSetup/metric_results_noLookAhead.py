#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
metric_results_noLookAhead.py

Aplica filtros cuantitativos NO-LOOKAHEAD sobre archivos Excel de métricas.

IMPORTANTE:
- Este script NO usa continuation_60t, TP, SL ni resultado futuro para decidir si opera.
- Solo usa features que deben existir antes/al momento del setup:
  VWAP, range_ticks, breakout_body_ticks, breakout_volume, breakout_delta y breakout_time.

Uso:
1) Cambia EXCELS_DIR por tu carpeta real.
2) Corre:
   python metric_results_noLookAhead.py

Salida:
- metric_results_noLookAhead_output.xlsx
  con pestañas:
  - All_Trades_Filtered
  - Valid_Trades
  - No_Trade
  - Summary
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


# =========================================================
# CONFIGURACIÓN PRINCIPAL
# =========================================================

EXCELS_DIR = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\footprints_generados")
ONLY_FILE_NAME = "metric results.xlsx"

# Si quieres probar solo un archivo específico, pon aquí el nombre exacto.
# Si lo dejas en None, lee todos los .xlsx de la carpeta.
ONLY_FILE_NAME = None

# Nombre esperado de la pestaña con datos por día/trade.
DETAIL_SHEET_NAME = "Detail"

# Archivo Excel donde se guardan los resultados.
OUTPUT_FILE = EXCELS_DIR / "metric_results_noLookAhead_output.xlsx"

# =========================================================
# FILTROS NO-LOOKAHEAD
# =========================================================

MIN_RANGE_TICKS = 75
MAX_RANGE_TICKS = 235
MIN_BREAKOUT_BODY_TICKS = 25
MIN_BREAKOUT_VOLUME = 1600
MIN_ABS_BREAKOUT_DELTA = 60
MAX_BREAKOUT_TIME = "09:45"

# Filtros activos para la decisión final.
USE_VWAP_FILTER = True
USE_RANGE_FILTER = True
USE_BODY_FILTER = True
USE_VOLUME_FILTER = True
USE_TIME_FILTER = True

# Lo dejo apagado por default porque delta fue filtro secundario.
# Si quieres hacerlo estricto, cámbialo a True.
USE_DELTA_FILTER = False

# =========================================================
# HELPERS
# =========================================================


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza nombres de columnas para evitar errores por espacios/mayúsculas."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def find_col(df: pd.DataFrame, candidates: List[str]) -> str | None:
    """Busca una columna por posibles nombres."""
    lower_map = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def parse_time_value(value) -> pd.Timestamp | pd.NaT:
    """Convierte breakout_time a timestamp comparable. Tolera strings, datetime y NaN."""
    if pd.isna(value):
        return pd.NaT

    # Si viene como datetime/time, pandas lo puede interpretar.
    try:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.notna(parsed):
            return parsed
    except Exception:
        pass

    text = str(value).strip()
    if not text:
        return pd.NaT

    # Si viene como HH:MM o HH:MM:SS
    try:
        parsed = pd.to_datetime(text, format="%H:%M", errors="coerce")
        if pd.notna(parsed):
            return parsed
        parsed = pd.to_datetime(text, format="%H:%M:%S", errors="coerce")
        return parsed
    except Exception:
        return pd.NaT


def time_leq(series: pd.Series, max_time: str) -> pd.Series:
    """Evalúa si una hora es <= max_time ignorando fecha."""
    max_t = pd.to_datetime(max_time, format="%H:%M").time()

    def check(x) -> bool:
        parsed = parse_time_value(x)
        if pd.isna(parsed):
            return False
        return parsed.time() <= max_t

    return series.apply(check)


def infer_vwap_alignment(df: pd.DataFrame) -> pd.Series:
    """
    VWAP alineada:
    - BUY/LONG/UP: breakout_body_price >= breakout_vwap
    - SELL/SHORT/DOWN: breakout_body_price <= breakout_vwap

    Si no se reconoce el lado, intenta usar el signo de breakout_body_ticks:
    - positivo: arriba de VWAP
    - negativo: abajo de VWAP
    """
    side_col = find_col(df, ["breakout_side", "side", "direction"])
    price_col = find_col(df, ["breakout_body_price", "entry_price", "close", "breakout_price"])
    vwap_col = find_col(df, ["breakout_vwap", "vwap", "VWAP"])
    body_ticks_col = find_col(df, ["breakout_body_ticks"])

    if price_col is None or vwap_col is None:
        return pd.Series(False, index=df.index)

    price = pd.to_numeric(df[price_col], errors="coerce")
    vwap = pd.to_numeric(df[vwap_col], errors="coerce")

    if side_col is not None:
        side = df[side_col].astype(str).str.lower().str.strip()
        is_long = side.str.contains("buy|long|up|bull|call|alto|high|break_up|arriba", regex=True)
        is_short = side.str.contains("sell|short|down|bear|put|bajo|low|break_down|abajo", regex=True)
    else:
        is_long = pd.Series(False, index=df.index)
        is_short = pd.Series(False, index=df.index)

    # Fallback si no detecta dirección por texto.
    unknown = ~(is_long | is_short)
    if body_ticks_col is not None:
        body_ticks = pd.to_numeric(df[body_ticks_col], errors="coerce")
        is_long = is_long | (unknown & (body_ticks >= 0))
        is_short = is_short | (unknown & (body_ticks < 0))

    aligned = ((is_long & (price >= vwap)) | (is_short & (price <= vwap)))
    return aligned.fillna(False)


def add_no_lookahead_filters(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    """Agrega columnas booleanas de filtro y decisión final."""
    df = normalize_columns(df)
    out = df.copy()
    out.insert(0, "source_excel", source_file)

    range_col = find_col(out, ["range_ticks", "or_range_ticks", "OR range ticks"])
    body_col = find_col(out, ["breakout_body_ticks", "body_out_ticks"])
    volume_col = find_col(out, ["breakout_volume", "Volume_breakout", "volume"])
    delta_col = find_col(out, ["breakout_delta", "Delta_breakout", "delta"])
    time_col = find_col(out, ["breakout_time", "signal_time", "entry_time"])

    if range_col is None:
        out["filter_range_ok"] = False
    else:
        range_ticks = pd.to_numeric(out[range_col], errors="coerce")
        out["filter_range_ok"] = range_ticks.between(MIN_RANGE_TICKS, MAX_RANGE_TICKS, inclusive="both")

    if body_col is None:
        out["filter_breakout_body_ok"] = False
    else:
        body_ticks = pd.to_numeric(out[body_col], errors="coerce").abs()
        out["filter_breakout_body_ok"] = body_ticks >= MIN_BREAKOUT_BODY_TICKS

    if volume_col is None:
        out["filter_volume_ok"] = False
    else:
        volume = pd.to_numeric(out[volume_col], errors="coerce")
        out["filter_volume_ok"] = volume >= MIN_BREAKOUT_VOLUME

    if delta_col is None:
        out["filter_delta_ok"] = False
    else:
        delta = pd.to_numeric(out[delta_col], errors="coerce").abs()
        out["filter_delta_ok"] = delta >= MIN_ABS_BREAKOUT_DELTA

    if time_col is None:
        out["filter_time_ok"] = False
    else:
        out["filter_time_ok"] = time_leq(out[time_col], MAX_BREAKOUT_TIME)

    out["filter_vwap_aligned"] = infer_vwap_alignment(out)

    active_filters: List[Tuple[str, bool]] = [
        ("filter_vwap_aligned", USE_VWAP_FILTER),
        ("filter_range_ok", USE_RANGE_FILTER),
        ("filter_breakout_body_ok", USE_BODY_FILTER),
        ("filter_volume_ok", USE_VOLUME_FILTER),
        ("filter_time_ok", USE_TIME_FILTER),
        ("filter_delta_ok", USE_DELTA_FILTER),
    ]

    active_filter_cols = [name for name, enabled in active_filters if enabled]
    out["active_filters_passed"] = out[active_filter_cols].sum(axis=1)
    out["active_filters_total"] = len(active_filter_cols)
    out["valid_trade_noLookAhead"] = out[active_filter_cols].all(axis=1)

    def reason(row) -> str:
        failed = [col.replace("filter_", "") for col in active_filter_cols if not bool(row[col])]
        return "VALID TRADE" if not failed else "NO TRADE: " + ", ".join(failed)

    out["noLookAhead_decision"] = np.where(out["valid_trade_noLookAhead"], "VALID TRADE", "NO TRADE")
    out["noLookAhead_reason"] = out.apply(reason, axis=1)

    return out


def read_excel_detail(path: Path) -> pd.DataFrame:
    """Lee la pestaña Detail; si no existe, usa la primera pestaña con más columnas."""
    xls = pd.ExcelFile(path)
    if DETAIL_SHEET_NAME in xls.sheet_names:
        return pd.read_excel(path, sheet_name=DETAIL_SHEET_NAME)

    # Fallback: elegir la hoja con más columnas.
    best_df = None
    best_cols = -1
    for sheet in xls.sheet_names:
        temp = pd.read_excel(path, sheet_name=sheet)
        if temp.shape[1] > best_cols:
            best_df = temp
            best_cols = temp.shape[1]
    if best_df is None:
        raise ValueError(f"No pude leer ninguna hoja de {path.name}")
    return best_df


def build_summary(all_df: pd.DataFrame) -> pd.DataFrame:
    total = len(all_df)
    valid = int(all_df["valid_trade_noLookAhead"].sum()) if total else 0
    no_trade = total - valid

    rows: List[Dict[str, object]] = [
        {"metric": "total_rows", "value": total},
        {"metric": "valid_trades_noLookAhead", "value": valid},
        {"metric": "no_trade", "value": no_trade},
        {"metric": "valid_trade_pct", "value": valid / total if total else 0},
        {"metric": "no_trade_pct", "value": no_trade / total if total else 0},
        {"metric": "USE_VWAP_FILTER", "value": USE_VWAP_FILTER},
        {"metric": "USE_RANGE_FILTER", "value": USE_RANGE_FILTER},
        {"metric": "USE_BODY_FILTER", "value": USE_BODY_FILTER},
        {"metric": "USE_VOLUME_FILTER", "value": USE_VOLUME_FILTER},
        {"metric": "USE_TIME_FILTER", "value": USE_TIME_FILTER},
        {"metric": "USE_DELTA_FILTER", "value": USE_DELTA_FILTER},
        {"metric": "MIN_RANGE_TICKS", "value": MIN_RANGE_TICKS},
        {"metric": "MAX_RANGE_TICKS", "value": MAX_RANGE_TICKS},
        {"metric": "MIN_BREAKOUT_BODY_TICKS", "value": MIN_BREAKOUT_BODY_TICKS},
        {"metric": "MIN_BREAKOUT_VOLUME", "value": MIN_BREAKOUT_VOLUME},
        {"metric": "MIN_ABS_BREAKOUT_DELTA", "value": MIN_ABS_BREAKOUT_DELTA},
        {"metric": "MAX_BREAKOUT_TIME", "value": MAX_BREAKOUT_TIME},
    ]

    filter_cols = [
        "filter_vwap_aligned",
        "filter_range_ok",
        "filter_breakout_body_ok",
        "filter_volume_ok",
        "filter_time_ok",
        "filter_delta_ok",
    ]
    for col in filter_cols:
        if col in all_df.columns and total:
            rows.append({"metric": f"{col}_pass_count", "value": int(all_df[col].sum())})
            rows.append({"metric": f"{col}_pass_pct", "value": float(all_df[col].mean())})

    # Si existe resultado futuro, lo resume solo para diagnóstico posterior, NO para decidir.
    result_candidates = ["continuation_60t", "final_result", "RESULT", "TP_SL", "result"]
    for col in result_candidates:
        if col in all_df.columns:
            counts = all_df[col].value_counts(dropna=False)
            for key, val in counts.items():
                rows.append({"metric": f"diagnostic_{col}_{key}", "value": int(val)})

            # Diagnóstico útil: cuántos TP/SL sobreviven por el filtro.
            temp = all_df.copy()
            grouped = temp.groupby([col, "noLookAhead_decision"], dropna=False).size().reset_index(name="count")
            for _, r in grouped.iterrows():
                rows.append({
                    "metric": f"diagnostic_{col}_{r[col]}_{r['noLookAhead_decision']}",
                    "value": int(r["count"]),
                })
            break

    return pd.DataFrame(rows)


def main() -> None:
    if not EXCELS_DIR.exists():
        raise FileNotFoundError(
            f"No existe EXCELS_DIR: {EXCELS_DIR}\n"
            "Cambia EXCELS_DIR = Path(r'tu ruta de excels aquí') por tu ruta real."
        )

    if ONLY_FILE_NAME:
        excel_files = [EXCELS_DIR / ONLY_FILE_NAME]
    else:
        excel_files = sorted(
            p for p in EXCELS_DIR.glob("*.xlsx")
            if not p.name.startswith("~$") and p.name != OUTPUT_FILE.name
        )

    if not excel_files:
        raise FileNotFoundError(f"No encontré archivos .xlsx en: {EXCELS_DIR}")

    filtered_frames: List[pd.DataFrame] = []
    for path in excel_files:
        print(f"Leyendo: {path.name}")
        df = read_excel_detail(path)
        filtered = add_no_lookahead_filters(df, source_file=path.name)
        filtered_frames.append(filtered)

    all_df = pd.concat(filtered_frames, ignore_index=True)
    valid_df = all_df[all_df["valid_trade_noLookAhead"]].copy()
    no_trade_df = all_df[~all_df["valid_trade_noLookAhead"]].copy()
    summary_df = build_summary(all_df)

    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        all_df.to_excel(writer, sheet_name="All_Trades_Filtered", index=False)
        valid_df.to_excel(writer, sheet_name="Valid_Trades", index=False)
        no_trade_df.to_excel(writer, sheet_name="No_Trade", index=False)
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

    print("\nLISTO ✅")
    print(f"Archivo generado: {OUTPUT_FILE}")
    print(f"Total filas: {len(all_df)}")
    print(f"Valid trades no-lookahead: {len(valid_df)}")
    print(f"NO TRADE: {len(no_trade_df)}")


if __name__ == "__main__":
    main()
