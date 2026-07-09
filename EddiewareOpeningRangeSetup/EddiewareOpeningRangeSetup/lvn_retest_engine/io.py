from __future__ import annotations

import glob
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ResearchConfig


ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "ts_event", "datetime", "date_time", "time_stamp", "bar_time", "time_ny", "time_utc"),
    "date": ("date", "fecha", "date_ny", "session_date"),
    "time": ("time", "hora", "clock", "time_of_day"),
    "price": ("price", "precio", "trade_price", "level", "price_level", "nivel_de_precio"),
    "volume": ("size", "qty", "quantity", "trade_size", "level_volume", "total_volume", "volume", "vol"),
    "bid_volume": ("bid_volume", "bidvol", "bid_vol", "bid_size", "bid"),
    "ask_volume": ("ask_volume", "askvol", "ask_vol", "ask_size", "ask"),
    "side": ("aggressor_side", "trade_side", "side", "direction"),
    "symbol": ("symbol", "instrument", "ticker", "raw_symbol"),
    "open": ("candle_open", "bar_open", "open"),
    "high": ("candle_high", "bar_high", "high"),
    "low": ("candle_low", "bar_low", "low"),
    "close": ("candle_close", "bar_close", "close"),
    "delta": ("delta", "footprint_delta", "bar_delta"),
    "is_big_trade": ("is_big_trade", "big_trade", "large_trade_flag"),
    "big_trade_volume": ("big_trade_volume", "large_trade_volume", "whale_volume"),
    "iceberg": ("iceberg", "iceberg_count", "is_iceberg"),
    "absorption": ("absorption", "absorption_count", "is_absorption"),
    "bar_trades": ("bar_trades", "ticks", "trade_count", "num_trades", "tick_count"),
}


def normalize_name(value: object) -> str:
    name = str(value).strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def find_column(frame: pd.DataFrame, canonical: str) -> str | None:
    for candidate in ALIASES[canonical]:
        if candidate in frame.columns:
            return candidate
    return None


def expand_inputs(patterns: list[str]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True)
        if not matches and Path(pattern).is_file():
            matches = [pattern]
        found.extend(Path(match).resolve() for match in matches if Path(match).is_file())
    unique = sorted(dict.fromkeys(found))
    if not unique:
        raise FileNotFoundError(f"Ningún archivo coincide con: {patterns}")
    return unique


def _read_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        for encoding in ("utf-8-sig", "utf-8", "latin1"):
            try:
                return pd.read_csv(path, encoding=encoding)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(path)
    if suffix in {".feather", ".arrow"}:
        return pd.read_feather(path)
    raise ValueError(f"Formato no soportado: {path}")


def _parse_timestamp(frame: pd.DataFrame, config: ResearchConfig) -> pd.Series:
    timestamp_col = find_column(frame, "timestamp")
    if timestamp_col is not None:
        source = frame[timestamp_col]
    else:
        date_col, time_col = find_column(frame, "date"), find_column(frame, "time")
        if date_col is None or time_col is None:
            raise ValueError("Falta timestamp o combinación date/time")
        source = frame[date_col].astype(str).str.strip() + " " + frame[time_col].astype(str).str.strip()

    if pd.api.types.is_numeric_dtype(source):
        clean = pd.to_numeric(source, errors="coerce")
        magnitude = float(clean.dropna().abs().median()) if clean.notna().any() else 0.0
        unit = "ns" if magnitude >= 1e17 else "us" if magnitude >= 1e14 else "ms" if magnitude >= 1e11 else "s"
        parsed = pd.to_datetime(clean, unit=unit, errors="coerce", utc=True)
        return parsed.dt.tz_convert(config.market_timezone)

    # ATAS exports often mix second and millisecond precision in the same file.
    parsed = pd.to_datetime(source, errors="coerce", format="mixed")
    if isinstance(parsed.dtype, pd.DatetimeTZDtype):
        return parsed.dt.tz_convert(config.market_timezone)
    localized = parsed.dt.tz_localize(config.input_timezone, ambiguous="NaT", nonexistent="shift_forward")
    return localized.dt.tz_convert(config.market_timezone)


def _number(frame: pd.DataFrame, canonical: str, default: float = math.nan) -> pd.Series:
    column = find_column(frame, canonical)
    if column is None:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _boolean_or_number(frame: pd.DataFrame, canonical: str) -> pd.Series:
    column = find_column(frame, canonical)
    if column is None:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    source = frame[column]
    if pd.api.types.is_bool_dtype(source):
        return source.astype(float)
    mapped = source.astype(str).str.strip().str.lower().map({
        "true": 1.0, "yes": 1.0, "y": 1.0, "si": 1.0, "sí": 1.0,
        "false": 0.0, "no": 0.0, "n": 0.0,
    })
    numeric = pd.to_numeric(source, errors="coerce")
    return numeric.fillna(mapped)


def normalize_input(frame: pd.DataFrame, path: Path, config: ResearchConfig) -> tuple[pd.DataFrame, dict[str, object]]:
    raw_rows = len(frame)
    frame = frame.copy()
    frame.columns = [normalize_name(column) for column in frame.columns]
    timestamp = _parse_timestamp(frame, config)
    price_col = find_column(frame, "price")
    if price_col is None:
        raise ValueError("Falta una columna price/level; OHLC sin volumen por precio no construye un footprint")
    price = pd.to_numeric(frame[price_col], errors="coerce")
    bid_col, ask_col = find_column(frame, "bid_volume"), find_column(frame, "ask_volume")
    volume_col = find_column(frame, "volume")
    bid = _number(frame, "bid_volume", 0.0).fillna(0.0)
    ask = _number(frame, "ask_volume", 0.0).fillna(0.0)
    explicit_volume = _number(frame, "volume", 0.0).fillna(0.0)

    side_col = find_column(frame, "side")
    side = frame[side_col].astype(str).str.strip().str.upper() if side_col else pd.Series("", index=frame.index)
    buy_side = side.isin({"B", "BUY", "ASK", "A", "1", "LONG"})
    sell_side = side.isin({"S", "SELL", "BID", "-1", "SHORT"})
    if bid_col is None and ask_col is None and volume_col is not None:
        ask = explicit_volume.where(buy_side, 0.0)
        bid = explicit_volume.where(sell_side, 0.0)
    level_volume = bid + ask
    volume = level_volume.where(level_volume > 0, explicit_volume)

    out = pd.DataFrame({
        "timestamp": timestamp,
        "price": price,
        "volume": volume,
        "bid_volume": bid,
        "ask_volume": ask,
        "open": _number(frame, "open"),
        "high": _number(frame, "high"),
        "low": _number(frame, "low"),
        "close": _number(frame, "close"),
        "delta_explicit": _number(frame, "delta"),
        "is_big_trade": _boolean_or_number(frame, "is_big_trade"),
        "big_trade_volume": _number(frame, "big_trade_volume"),
        "iceberg": _boolean_or_number(frame, "iceberg"),
        "absorption": _boolean_or_number(frame, "absorption"),
        "bar_trades": _number(frame, "bar_trades"),
        "trade_side": side,
        "source_file": str(path),
        "source_row": np.arange(raw_rows, dtype=np.int64),
    })
    symbol_col = find_column(frame, "symbol")
    out["symbol"] = frame[symbol_col].astype(str) if symbol_col else config.symbol
    has_ohlc = out[["open", "high", "low", "close"]].notna().any(axis=None)
    repeated_timestamps = bool(out["timestamp"].duplicated(keep=False).any())
    granularity = "FOOTPRINT_BAR" if has_ohlc or (bid_col is not None and ask_col is not None and repeated_timestamps) else "TICK"
    out["input_granularity"] = granularity
    out = out.dropna(subset=["timestamp", "price"])
    out = out.loc[out["volume"].fillna(0) >= 0].copy()
    out["session_date"] = out["timestamp"].dt.date
    off_tick = np.abs(out["price"] / config.tick_size - np.rint(out["price"] / config.tick_size)) > 1e-6
    manifest = {
        "source_file": str(path),
        "raw_rows": raw_rows,
        "accepted_rows": len(out),
        "dropped_rows": raw_rows - len(out),
        "granularity": granularity,
        "first_timestamp_et": out["timestamp"].min().isoformat() if not out.empty else "",
        "last_timestamp_et": out["timestamp"].max().isoformat() if not out.empty else "",
        "off_tick_price_rows": int(off_tick.sum()),
        "has_bid_ask": bid_col is not None and ask_col is not None,
        "has_ohlc": bool(has_ohlc),
        "has_big_trade_field": find_column(frame, "is_big_trade") is not None or find_column(frame, "big_trade_volume") is not None,
        "has_iceberg_field": find_column(frame, "iceberg") is not None,
        "has_absorption_field": find_column(frame, "absorption") is not None,
    }
    return out, manifest


def read_inputs(patterns: list[str], config: ResearchConfig) -> tuple[pd.DataFrame, list[dict[str, object]], list[dict[str, object]]]:
    frames: list[pd.DataFrame] = []
    manifest: list[dict[str, object]] = []
    debug: list[dict[str, object]] = []
    sequence_offset = 0
    for path in expand_inputs(patterns):
        try:
            normalized, info = normalize_input(_read_file(path), path, config)
            normalized["sequence"] = np.arange(sequence_offset, sequence_offset + len(normalized), dtype=np.int64)
            sequence_offset += len(normalized)
            frames.append(normalized)
            manifest.append(info)
        except Exception as exc:
            debug.append({
                "debug_type": "INPUT_FILE",
                "source_file": str(path),
                "status": "REJECTED",
                "reason": f"{type(exc).__name__}: {exc}",
            })
    if not frames:
        reasons = "; ".join(str(row["reason"]) for row in debug)
        raise ValueError(f"Ningún archivo produjo filas utilizables. {reasons}")
    data = pd.concat(frames, ignore_index=True)
    data.sort_values(["timestamp", "sequence"], inplace=True, kind="stable")
    data.reset_index(drop=True, inplace=True)
    return data, manifest, debug
