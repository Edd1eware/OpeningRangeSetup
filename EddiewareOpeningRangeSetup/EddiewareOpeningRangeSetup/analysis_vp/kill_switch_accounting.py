"""Contabilidad del kill-switch sobre la secuencia canonica de trades (Python).

Decision 2026-07-07: la validacion de integracion NO se puede cerrar dentro de ATAS
(Market Replay no llena CurrentPosition y para en el terminal del exporter antes de que
la strategy cierre su trade virtual; ver PROGRESO_06). El SIZING del kill-switch SI quedo
probado en ATAS (ENTER_VIRTUAL contracts = tier del kill-switch). La CONTABILIDAD de la
secuencia (equity/tier/DD por trade) se hace aqui, con el MISMO motor `run_csharp` que ya
paso parity byte-identico contra el sim y contra el C# desplegado (12_KillSwitchSizer.cs).

Produce:
  1. Log per-trade: fecha, ticks, contratos, tier, pnl, equity, peak, dd  -> CSV
  2. Tabla ano x metrica (trades, WR, contratos medios, net$, dias) + TOTAL
  3. Veredicto: net, maxDD del path, quema vs cojin $4,500

Uso: python -u kill_switch_accounting.py --base 3
"""
from __future__ import annotations

import argparse
import glob
import os

import numpy as np
import pandas as pd

from kill_switch_parity import CUSHION, TICK_USD, run_csharp

try:
    from progress import track
except Exception:  # pragma: no cover
    def track(seq, total=None, label="", width=10):
        return seq

# Secuencia canonica completa (misma fuente que kill_switch_parity).
DEFAULT_FOLDER = (
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
    r"\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs\X10_R1"
)
TIER_NAME = {0: "full", 1: "half", 2: "min"}


def load_trades(folder: str) -> pd.DataFrame:
    """Carga 1 fila por fecha desde los score_trade_result_*.csv (dedup por fecha)."""
    files = sorted(glob.glob(os.path.join(folder, "score_trade_result_*_NY.csv")))
    rows = []
    for f in track(files, label="Cargando score CSVs"):
        try:
            d = pd.read_csv(f)
            if d.empty:
                continue
            d = d.iloc[0]
            lbl = str(d["Result_Label"]).upper()
            t = str(d["result TP SL BE"]).replace("+", "")
            tk = float(t) if t not in ("", "nan") else 0.0
            traded = lbl in ("TP", "SL", "BE")
            rows.append((str(d["fecha"]), traded, tk if traded else 0.0))
        except Exception:  # noqa: BLE001
            pass
    df = pd.DataFrame(rows, columns=["fecha", "traded", "ticks"]).drop_duplicates("fecha")
    df["date"] = pd.to_datetime(df["fecha"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def build_log(df: pd.DataFrame, base: int) -> pd.DataFrame:
    """Corre el kill-switch y arma el log per-trade con equity/peak/dd path."""
    traded = df["traded"].to_numpy()
    ticks = df["ticks"].to_numpy()
    eq, _dd, sizes, tiers = run_csharp(traded, ticks, base)

    pnl = np.where(traded, ticks * sizes * TICK_USD, 0.0)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak  # <=0

    out = pd.DataFrame({
        "fecha": df["date"].dt.date.astype(str),
        "traded": traded,
        "ticks": ticks,
        "contracts": sizes,
        "tier": [TIER_NAME.get(t, t) for t in tiers],
        "pnl_usd": pnl,
        "equity": eq,
        "peak": peak,
        "dd": dd,
    })
    return out


def year_table(log: pd.DataFrame) -> pd.DataFrame:
    """Tabla ano x metrica sobre los trades TOMADOS (traded=True)."""
    t = log[log["traded"]].copy()
    t["year"] = pd.to_datetime(t["fecha"]).dt.year
    recs = []
    for year, g in t.groupby("year"):
        wins = int((g["pnl_usd"] > 0).sum())
        losses = int((g["pnl_usd"] < 0).sum())
        n = len(g)
        gross_win = g.loc[g["pnl_usd"] > 0, "pnl_usd"].sum()
        gross_loss = -g.loc[g["pnl_usd"] < 0, "pnl_usd"].sum()
        pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
        recs.append({
            "year": year, "trades": n,
            "WR": f"{wins/n*100:.1f}%" if n else "N/A",
            "avg_contracts": f"{g['contracts'].mean():.2f}",
            "PF": f"{pf:.2f}" if np.isfinite(pf) else "inf",
            "net_usd": f"{g['pnl_usd'].sum():+,.0f}",
        })
    tbl = pd.DataFrame(recs)
    total = {
        "year": "TOTAL", "trades": len(t),
        "WR": f"{(t['pnl_usd']>0).sum()/len(t)*100:.1f}%" if len(t) else "N/A",
        "avg_contracts": f"{t['contracts'].mean():.2f}",
        "PF": (f"{(t.loc[t['pnl_usd']>0,'pnl_usd'].sum() / max(1e-9, -t.loc[t['pnl_usd']<0,'pnl_usd'].sum())):.2f}"),
        "net_usd": f"{t['pnl_usd'].sum():+,.0f}",
    }
    return pd.concat([tbl, pd.DataFrame([total])], ignore_index=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=int, default=3)
    ap.add_argument("--folder", default=DEFAULT_FOLDER)
    ap.add_argument("--out", default=None, help="CSV del log per-trade (default junto al folder).")
    args = ap.parse_args()

    df = load_trades(args.folder)
    n_trades = int(df["traded"].sum())
    if len(df) == 0:
        print(f"Sin datos en {args.folder}")
        return 1

    log = build_log(df, args.base)
    maxDD = float(log["dd"].min())
    net = float(log["equity"].iloc[-1])
    quema = maxDD <= -CUSHION

    out_path = args.out or os.path.join(args.folder, f"kill_switch_accounting_base{args.base}.csv")
    log.to_csv(out_path, index=False)

    print(f"Secuencia: {df.date.min().date()} -> {df.date.max().date()} | "
          f"dias={len(df)} | trades={n_trades} | base={args.base} | cojin=${CUSHION:.0f}\n")

    print("Tabla ano x metrica (trades tomados, sizing kill-switch):")
    print(year_table(log).to_string(index=False))

    vals, cnts = np.unique(log.loc[log["traded"], "tier"], return_counts=True)
    print("\nUso de tiers (trades tomados): " +
          " ".join(f"{v}={c}" for v, c in zip(vals, cnts)))

    print(f"\nVEREDICTO kill-switch base={args.base}:")
    print(f"  net       ${net:+,.0f}")
    print(f"  maxDD     ${maxDD:+,.0f}   -> {'QUEMA' if quema else 'SEGURO'} vs cojin ${CUSHION:.0f}")
    print(f"  log per-trade -> {out_path}")
    print("  (motor run_csharp == C# 12_KillSwitchSizer.cs, parity byte-identico previo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
