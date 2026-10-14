"""Feed del indicador de ATAS con las operaciones REALES de la cuenta Lucid aprobada.

Lee `lucid_account_passed100k/Lucid_account_passed_columns.xlsx`, agrupa los 50
fills en las 27 posiciones efectivas (misma fecha + misma hora de entrada) y
escribe el mismo CSV plano que consume 19_Inside_Control_Trade_Navigator.

Diferencias respecto al feed del control simulado:

- No hay SL ni TP: la cuenta solo registra entrada y salida. Esas columnas van en
  cero y el indicador pinta una sola caja de la entrada a la salida, en vez de
  las cajas de riesgo y objetivo.
- No hay vela del motor con la que comparar, asi que las columnas OHLC van en
  cero y el indicador omite el control de paridad.
- El rango de apertura se toma de la corrida calibrada, que lo tiene para 15 de
  las 16 sesiones.

Uso:
    python -u build_real_trades_feed.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXCEL = ROOT / "lucid_account_passed100k" / "Lucid_account_passed_columns.xlsx"
OR_SOURCE = Path(
    r"C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs"
    r"/calibrated_setup_replay_v1/candidates.csv"
)
OUT = Path(r"C:/Users/k_99_/Desktop/codding/data_footprint_generator/lucid_real_trades.csv")

COMMISSION_USD_PER_CONTRACT = 4.0

# La cuenta no registra SL ni TP, pero el bracket es fijo de 60 ticks por lado:
# lo confirman el panel de ATAS (TP 60 / SL 60), la captura del 12-oct
# (SL 30977.50 / TP 30947.50 sobre entrada 30962.50) y que 12 de los 38 fills
# ganadores caen en 59-62 ticks. Se marca como ASUMIDO en la columna warn.
BRACKET_TICKS = 60
TICK = 0.25

COLUMNS = [
    "n", "session", "minute", "candle_start", "signal_close", "dir",
    "or_high", "or_low", "o", "h", "l", "c", "raw_o", "raw_h", "raw_l", "raw_c",
    "vwap", "entry", "stop", "target", "exit", "risk_ticks",
    "result", "net_ticks", "net_r", "net_usd", "mae", "mfe", "duration_s",
    "entry_clock", "exit_clock", "source", "warn", "imb_rows",
]


def load_positions() -> pd.DataFrame:
    fills = pd.read_excel(EXCEL, sheet_name="Trades")
    fills["Date"] = pd.to_datetime(fills["Date"]).dt.strftime("%Y-%m-%d")

    key = ["Date", "OpenClock", "Side"]
    positions = fills.groupby(key, as_index=False).agg(
        fills_count=("#", "count"),
        qty=("Qty", "sum"),
        entry=("OpenPrice", "mean"),
        exit=("ClosePrice", "mean"),
        exit_clock=("CloseClock", "max"),
        n_exits=("CloseClock", "nunique"),
        gross_usd=("NetPnL", "sum"),
        duration=("DurationSec", "max"),
    )

    # Per-contract ticks must be weighted by size: a 2-lot fill carries twice the
    # weight of a 1-lot fill inside the same position.
    weighted = fills.groupby(key).apply(
        lambda d: (d["Ticks"] * d["Qty"]).sum() / d["Qty"].sum()
    )
    positions["ticks_pc"] = weighted.values

    positions["net_usd"] = positions["gross_usd"] - COMMISSION_USD_PER_CONTRACT * positions["qty"]
    positions["net_ticks"] = positions["ticks_pc"] - COMMISSION_USD_PER_CONTRACT / 5.0

    return positions.sort_values(["Date", "OpenClock"]).reset_index(drop=True)


def load_opening_ranges(sessions: list[str]) -> dict[str, tuple[float, float]]:
    if not OR_SOURCE.exists():
        print(f"AVISO: no existe {OR_SOURCE}; no habra rango de apertura.")
        return {}

    candidates = pd.read_csv(OR_SOURCE, usecols=["session", "or_high", "or_low"])
    first = candidates[candidates["session"].isin(sessions)].groupby("session").first()
    return {s: (row.or_high, row.or_low) for s, row in first.iterrows()}


def main() -> None:
    positions = load_positions()
    sessions = sorted(positions["Date"].unique())
    ranges = load_opening_ranges(sessions)

    missing = [s for s in sessions if s not in ranges]
    OUT.parent.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(COLUMNS)

        for i, row in enumerate(positions.itertuples(), start=1):
            open_clock = str(row.OpenClock)              # "09:33:10"
            minute = open_clock[:5]                      # "09:33"
            or_high, or_low = ranges.get(row.Date, (0.0, 0.0))

            offset = BRACKET_TICKS * TICK
            direction = 1 if row.Side == "Long" else -1
            stop = round(row.entry - direction * offset, 2)
            target = round(row.entry + direction * offset, 2)

            warn = ["BRACKET_ASUMIDO_60"]
            if row.n_exits > 1:
                warn.append(f"SALIDA_ESCALONADA_{row.n_exits}")
            if row.Date not in ranges:
                warn.append("SIN_RANGO_DE_APERTURA")

            writer.writerow([
                i, row.Date, minute, f"{minute}:00", f"{minute}:00",
                1 if row.Side == "Long" else -1,
                or_high, or_low,
                0, 0, 0, 0,          # OHLC agrupado: no aplica
                0, 0, 0, 0,          # OHLC nativo: no aplica
                0,                   # VWAP: no aplica
                round(row.entry, 2),
                stop, target,
                round(row.exit, 2),
                BRACKET_TICKS,
                "WIN" if row.net_ticks > 0 else "LOSS",
                round(row.net_ticks, 2),
                round(row.net_ticks / BRACKET_TICKS, 4),
                round(row.net_usd, 2),
                0, 0,                # MAE / MFE: no registrados
                row.duration,
                open_clock, str(row.exit_clock),
                "LUCID_REAL",
                ",".join(warn), "",
            ])

    wins = int((positions["net_ticks"] > 0).sum())
    print(f"fills: 50 -> posiciones: {len(positions)}")
    print(f"sesiones: {len(sessions)}  ({sessions[0]} -> {sessions[-1]})")
    print(f"WR {wins / len(positions):.2%} | neto {positions['net_usd'].sum():+,.0f} USD "
          f"| {positions['net_ticks'].mean():+.2f} ticks/posicion")
    if missing:
        print(f"sin rango de apertura: {missing}")
    print(f"escrito: {OUT}")


if __name__ == "__main__":
    main()
