"""Analiza el filtro Range >= MIN_RANGE sobre todas las sesiones sincronizadas.

No requiere replay. Lee score_trade_result_*_NY.csv existentes.

Uso:
  python analisis_filtro_range.py          # Range >= 140 (default)
  python analisis_filtro_range.py 120      # prueba otro umbral
"""

import csv
import sys
from pathlib import Path

import replay_sync_runner_common_after_sync as rs

MIN_RANGE  = int(sys.argv[1]) if sys.argv[1:] else 140
CONTRACTS  = 3
TICK_USD   = 5.0
BASE       = rs.RESULTS_FOLDER

def main():
    files = sorted(BASE.glob("score_trade_result_*_NY.csv"))
    print(f"Archivos encontrados: {len(files)}")
    print(f"Filtro: APlus_Speed=TRUE AND Range >= {MIN_RANGE} ticks\n")

    all_aplus, filtered, results = [], [], []

    for f in files:
        try:
            rows = list(csv.DictReader(open(f, encoding="utf-8-sig")))
            if not rows:
                continue
            r = rows[0]
            aplus = r.get("APlus_Speed", "").strip().upper()
            if aplus != "TRUE":
                continue
            date     = r.get("fecha", f.stem.replace("score_trade_result_","").replace("_NY",""))
            range_t  = int(float(r.get("range", 0) or 0))
            result   = r.get("Result_Label", "").strip()
            ticks    = float(r.get("result TP SL BE", 0) or 0)
            pnl      = ticks * CONTRACTS * TICK_USD
            side     = r.get("Side", "").strip()
            speed    = float(r.get("BreakOut_TICKS_PER_SEC", 0) or 0)

            all_aplus.append({"date": date, "range": range_t, "result": result,
                              "ticks": ticks, "pnl": pnl, "side": side, "speed": speed})

            if range_t >= MIN_RANGE:
                filtered.append({"date": date, "range": range_t, "result": result,
                                 "ticks": ticks, "pnl": pnl, "side": side, "speed": speed})
        except Exception as e:
            print(f"  ERROR {f.name}: {e}")

    def stats(trades, label):
        wins   = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] < 0]
        total  = sum(t["pnl"] for t in trades)
        gw     = sum(t["pnl"] for t in wins)
        gl     = abs(sum(t["pnl"] for t in losses))
        wr     = len(wins)/(len(wins)+len(losses))*100 if (wins or losses) else 0
        pf     = gw/gl if gl else float("inf")
        avg_w  = gw/len(wins) if wins else 0
        avg_l  = gl/len(losses) if losses else 0

        # Max drawdown
        equity, peak, maxdd = 0, 0, 0
        for t in sorted(trades, key=lambda x: x["date"]):
            equity += t["pnl"]
            if equity > peak: peak = equity
            dd = peak - equity
            if dd > maxdd: maxdd = dd

        print(f"=== {label} ===")
        print(f"Trades: {len(trades)} | Wins: {len(wins)} | Losses: {len(losses)}")
        print(f"WR: {wr:.1f}% | PF: {pf:.2f}")
        print(f"PnL total: ${total:,.0f} | Avg win: ${avg_w:.0f} | Avg loss: -${avg_l:.0f}")
        print(f"Max DD: ${maxdd:,.0f}")
        print()

    stats(all_aplus, f"TODOS A+ Speed ({len(all_aplus)} trades)")
    stats(filtered,  f"A+ Speed + Range >= {MIN_RANGE} ({len(filtered)} trades)")

    # Trades eliminados por el filtro
    skipped = [t for t in all_aplus if t["range"] < MIN_RANGE]
    sk_wins = sum(1 for t in skipped if t["pnl"] > 0)
    sk_loss = sum(1 for t in skipped if t["pnl"] < 0)
    print(f"Eliminados por Range < {MIN_RANGE}: {len(skipped)} trades "
          f"({sk_wins} TP / {sk_loss} SL)")

    # Distribución de range en perdedores filtrados
    print(f"\nPerdedores restantes con Range >= {MIN_RANGE}:")
    for t in sorted(filtered, key=lambda x: x["date"]):
        if t["pnl"] < 0:
            print(f"  {t['date']} {t['side']} Range={t['range']}t "
                  f"Speed={t['speed']:.1f}TPS {t['result']} ${t['pnl']:,.0f}")

if __name__ == "__main__":
    main()
