from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class StrategyConfig:
    min_score: int = 5
    min_or_range_ticks: int = 40
    max_or_range_ticks: int = 350
    min_body_breakout_ticks: int = 10
    min_volume: float = 800.0
    min_abs_delta: float = 25.0
    max_signal_minute_ny: int = 50
    risk_ticks: int = 60
    tick_size: float = 0.25
    signal_start: str = "09:31"
    opening_range_minute: str = "09:30"


@dataclass(frozen=True)
class SetupState:
    is_breakout: bool
    is_long: bool
    is_short: bool
    vwap: float
    or_range_ticks: int
    body_breakout_ticks: int
    range_ok: bool
    body_ok: bool
    volume_ok: bool
    delta_ok: bool
    time_ok: bool
    vwap_ok: bool
    score: int


DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def to_ticks(price_distance: float, tick_size: float) -> int:
    if tick_size <= 0 or pd.isna(price_distance):
        return 0
    return int(round(price_distance / tick_size))


def extract_date(path: Path) -> str | None:
    match = DATE_RE.search(path.name)
    return match.group(1) if match else None


def locate_csv(xlsx_path: Path, csv_root: Path) -> Path | None:
    date = extract_date(xlsx_path)
    if not date:
        return None
    direct = csv_root / f"footprint_atas_{date}_0930_1030_NY.csv"
    if direct.exists():
        return direct
    matches = sorted(csv_root.glob(f"*{date}*.csv"))
    return matches[0] if matches else None


def load_candles(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    required = {
        "date_ny",
        "time_ny",
        "bar_index",
        "candle_open",
        "candle_high",
        "candle_low",
        "candle_close",
        "candle_delta",
        "candle_volume",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path.name} no tiene columnas requeridas: {sorted(missing)}")

    candles = (
        df[
            [
                "date_ny",
                "time_ny",
                "bar_index",
                "candle_open",
                "candle_high",
                "candle_low",
                "candle_close",
                "candle_delta",
                "candle_volume",
            ]
        ]
        .drop_duplicates("bar_index")
        .copy()
    )
    candles["minute"] = candles["time_ny"].astype(str).str.slice(0, 5)
    candles = candles.sort_values(["date_ny", "time_ny", "bar_index"]).reset_index(drop=True)
    return candles


def session_vwap(candles: pd.DataFrame, idx: int) -> float:
    upto = candles.iloc[: idx + 1]
    volume = upto["candle_volume"].astype(float)
    valid = volume > 0
    if not valid.any():
        return 0.0
    typical = (
        upto.loc[valid, "candle_high"].astype(float)
        + upto.loc[valid, "candle_low"].astype(float)
        + upto.loc[valid, "candle_close"].astype(float)
    ) / 3.0
    return float((typical * volume.loc[valid]).sum() / volume.loc[valid].sum())


def calculate_setup(
    candle: pd.Series,
    candles: pd.DataFrame,
    idx: int,
    or_high: float,
    or_low: float,
    config: StrategyConfig,
) -> SetupState:
    close = float(candle["candle_close"])
    open_ = float(candle["candle_open"])
    volume = float(candle["candle_volume"])
    delta = float(candle["candle_delta"])
    minute = str(candle["minute"])

    vwap = session_vwap(candles, idx)
    long_breakout = close > or_high
    short_breakout = close < or_low
    or_range_ticks = to_ticks(or_high - or_low, config.tick_size)

    body_breakout_ticks = 0
    if long_breakout:
        body_breakout_ticks = to_ticks(close - max(open_, or_high), config.tick_size)
    if short_breakout:
        body_breakout_ticks = to_ticks(min(open_, or_low) - close, config.tick_size)
    body_breakout_ticks = max(body_breakout_ticks, 0)

    range_ok = config.min_or_range_ticks <= or_range_ticks <= config.max_or_range_ticks
    body_ok = body_breakout_ticks >= config.min_body_breakout_ticks
    volume_ok = volume >= config.min_volume
    delta_ok = abs(delta) >= config.min_abs_delta
    time_ok = int(minute.split(":")[1]) <= config.max_signal_minute_ny
    vwap_ok = (long_breakout and close >= vwap) or (short_breakout and close <= vwap)

    score = 0
    if vwap_ok:
        score += 2
    if range_ok:
        score += 1
    if body_ok:
        score += 1
    if volume_ok:
        score += 1
    if delta_ok:
        score += 1
    if time_ok:
        score += 1

    return SetupState(
        is_breakout=long_breakout or short_breakout,
        is_long=long_breakout,
        is_short=short_breakout,
        vwap=vwap,
        or_range_ticks=or_range_ticks,
        body_breakout_ticks=body_breakout_ticks,
        range_ok=range_ok,
        body_ok=body_ok,
        volume_ok=volume_ok,
        delta_ok=delta_ok,
        time_ok=time_ok,
        vwap_ok=vwap_ok,
        score=score,
    )


def evaluate_exit(
    candles: pd.DataFrame,
    entry_idx: int,
    side: str,
    tp: float,
    sl: float,
) -> tuple[str, str | None, float]:
    for _, row in candles.iloc[entry_idx + 1 :].iterrows():
        high = float(row["candle_high"])
        low = float(row["candle_low"])
        minute = str(row["minute"])

        if side == "BUY":
            tp_hit = high >= tp
            sl_hit = low <= sl
        else:
            tp_hit = low <= tp
            sl_hit = high >= sl

        if tp_hit and sl_hit:
            return "SL", minute, -abs(tp - sl) / 2.0
        if tp_hit:
            return "TP", minute, abs(tp - sl) / 2.0
        if sl_hit:
            return "SL", minute, -abs(tp - sl) / 2.0

    return "NO_HIT", None, 0.0


def backtest_file(xlsx_path: Path, csv_root: Path, config: StrategyConfig) -> list[dict]:
    csv_path = locate_csv(xlsx_path, csv_root)
    if not csv_path:
        return []

    candles = load_candles(csv_path)
    or_rows = candles[candles["minute"] == config.opening_range_minute]
    if or_rows.empty:
        return []

    opening = or_rows.iloc[0]
    or_high = float(opening["candle_high"])
    or_low = float(opening["candle_low"])
    date = str(opening["date_ny"])

    trades: list[dict] = []
    for idx, candle in candles.iterrows():
        minute = str(candle["minute"])
        if minute < config.signal_start:
            continue
        if not (minute.startswith("09:") and int(minute.split(":")[1]) <= config.max_signal_minute_ny):
            continue

        setup = calculate_setup(candle, candles, idx, or_high, or_low, config)
        if not setup.is_breakout or setup.score < config.min_score:
            continue

        entry = float(candle["candle_close"])
        risk = config.tick_size * config.risk_ticks
        side = "BUY" if setup.is_long else "SELL"
        if side == "BUY":
            tp = entry + risk
            sl = entry - risk
        else:
            tp = entry - risk
            sl = entry + risk

        result, exit_minute, pnl_points = evaluate_exit(candles, idx, side, tp, sl)
        trades.append(
            {
                "date": date,
                "file": xlsx_path.name,
                "csv_source": csv_path.name,
                "signal_time": minute,
                "side": side,
                "entry": entry,
                "tp": tp,
                "sl": sl,
                "result": result,
                "exit_time": exit_minute,
                "pnl_points": pnl_points,
                "score": setup.score,
                "or_low": or_low,
                "or_high": or_high,
                "or_range_ticks": setup.or_range_ticks,
                "body_breakout_ticks": setup.body_breakout_ticks,
                "volume": float(candle["candle_volume"]),
                "delta": float(candle["candle_delta"]),
                "vwap": setup.vwap,
            }
        )

    return trades


def summarize(trades: pd.DataFrame) -> dict:
    closed = trades[trades["result"].isin(["TP", "SL"])]
    wins = int((closed["result"] == "TP").sum())
    losses = int((closed["result"] == "SL").sum())
    gross_profit = float(closed.loc[closed["pnl_points"] > 0, "pnl_points"].sum())
    gross_loss = abs(float(closed.loc[closed["pnl_points"] < 0, "pnl_points"].sum()))
    profit_factor = math.inf if gross_loss == 0 and gross_profit > 0 else (gross_profit / gross_loss if gross_loss else 0.0)
    win_rate = wins / len(closed) if len(closed) else 0.0
    return {
        "total_trades": int(len(trades)),
        "closed_trades": int(len(closed)),
        "tp": wins,
        "sl": losses,
        "no_hit": int((trades["result"] == "NO_HIT").sum()),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "gross_profit_points": gross_profit,
        "gross_loss_points": gross_loss,
        "net_points": float(closed["pnl_points"].sum()) if len(closed) else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Traduccion a Python del indicador C# Metric No LookAhead Score TP SL Contracts."
    )
    parser.add_argument(
        "--xlsx-dir",
        default=r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\footprints_generados",
        help="Carpeta con los Excel generados.",
    )
    parser.add_argument(
        "--csv-root",
        default=r"C:\Users\k_99_\Desktop\codding\data_footprint_generator",
        help="Carpeta donde viven los CSV fuente con OHLC por vela.",
    )
    parser.add_argument("--output", default="metric_no_lookahead_results.csv")
    args = parser.parse_args()

    xlsx_dir = Path(args.xlsx_dir)
    csv_root = Path(args.csv_root)
    config = StrategyConfig()

    files = sorted(xlsx_dir.glob("MINI_ATAS_FOOTPRINT_*_V34_FILTER_ATAS_COMPARE_DIAG.xlsx"))
    all_trades: list[dict] = []
    for file in files:
        all_trades.extend(backtest_file(file, csv_root, config))

    trades = pd.DataFrame(all_trades)
    output_path = Path(args.output).resolve()
    if trades.empty:
        trades.to_csv(output_path, index=False)
        print(f"No se encontraron trades. Archivo generado: {output_path}")
        return

    trades = trades.sort_values(["date", "signal_time", "file"]).reset_index(drop=True)
    trades.to_csv(output_path, index=False)
    summary = summarize(trades)

    print(f"Archivos Excel evaluados: {len(files)}")
    print(f"Trades totales: {summary['total_trades']}")
    print(f"Trades cerrados: {summary['closed_trades']}")
    print(f"TP: {summary['tp']} | SL: {summary['sl']} | NO_HIT: {summary['no_hit']}")
    print(f"Win rate: {summary['win_rate']:.2%}")
    print(f"Profit factor: {summary['profit_factor']:.4f}")
    print(f"Net points: {summary['net_points']:.2f}")
    print(f"Detalle CSV: {output_path}")
    print()
    print(trades[["date", "signal_time", "side", "entry", "tp", "sl", "result", "exit_time"]].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
