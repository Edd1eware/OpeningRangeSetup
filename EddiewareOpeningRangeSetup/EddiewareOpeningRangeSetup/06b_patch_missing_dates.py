"""Agrega fechas nuevas al CSV de la estrategia desde score_trade_result.

No requiere replay si el score_trade_result ya existe para la fecha.
Aplica filtro Range >= MIN_RANGE_TICKS (igual que el Exporter en vivo).

Uso:
  python 06b_patch_missing_dates.py 2026-07-10 2026-07-15
  python 06b_patch_missing_dates.py            # sin args: busca fechas A+ Speed sin entry en CSV
"""

import csv
import sys
from pathlib import Path

import replay_sync_runner_common_after_sync as rs

OUTPUT    = rs.RESULTS_FOLDER / "visual_tests" / "strategy_tester_results"
TRADES_LOG = OUTPUT / "strategy_tester_trades.csv"
CONTRACTS  = 3
TICK_USD   = 5.0
MIN_RANGE  = 140  # mismo filtro que ATASScoreTradeResultExporter


def _load_aplus_dates():
    """Devuelve todas las fechas A+ Speed conocidas del ladder."""
    from replay_sync_runner_common_after_sync import synced_dates
    return [str(d) for d in synced_dates(aplus_only=True)]


def _already_in_csv():
    if not TRADES_LOG.exists():
        return set()
    return {r.get("fecha", "").strip()
            for r in csv.DictReader(open(TRADES_LOG, encoding="utf-8-sig"))}


def _append_from_score(date_str):
    src = rs.RESULTS_FOLDER / f"score_trade_result_{date_str}_NY.csv"
    if not src.exists():
        print(f"  SKIP {date_str}: score_trade_result no existe (corre replay primero)")
        return False
    try:
        rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
        if not rows:
            return False
        r = rows[0]
        range_ticks = int(float(r.get("range", 0) or 0))
        if range_ticks < MIN_RANGE:
            print(f"  SKIP {date_str}: Range={range_ticks}t < {MIN_RANGE}t (filtro)")
            return False
        side      = r.get("Side", "").strip()
        entry     = r.get("Entry_price", "").strip()
        exit_p    = r.get("Exit_price", "").strip()
        ticks_raw = r.get("result TP SL BE", "").strip()
        result    = r.get("Result_Label", "").strip()
        if not side or not entry or not ticks_raw:
            print(f"  SKIP {date_str}: datos vacios")
            return False
        ticks  = float(ticks_raw)
        pnl    = ticks * CONTRACTS * TICK_USD
        motivo = "SL" if result == "SL" else "TP" if result in ("TP", "TRAIL") else "OPEN"
        OUTPUT.mkdir(parents=True, exist_ok=True)
        if not TRADES_LOG.exists():
            with open(TRADES_LOG, "w", encoding="utf-8") as f:
                f.write("fecha,side,contratos,entry_fill,exit_fill,ticks,pnl_usd,exit_motivo\n")
        with open(TRADES_LOG, "a", encoding="utf-8", newline="") as f:
            f.write(f"{date_str},{side},{CONTRACTS},{entry},{exit_p},"
                    f"{ticks:.2f},{pnl:.2f},{motivo}\n")
        print(f"  OK {date_str} | {side} | Range={range_ticks}t | {motivo} {ticks:+.0f}t ${pnl:+,.0f}")
        return True
    except Exception as e:
        print(f"  ERROR {date_str}: {e}")
        return False


def main():
    already = _already_in_csv()

    if sys.argv[1:]:
        dates = sys.argv[1:]
    else:
        try:
            all_aplus = _load_aplus_dates()
            dates = [d for d in all_aplus if d not in already]
            if not dates:
                print("No hay fechas A+ Speed pendientes de agregar.")
                return 0
            print(f"Fechas A+ Speed sin entry en CSV: {len(dates)}")
        except Exception:
            print("Pasa las fechas como argumentos: python 06b_patch_missing_dates.py YYYY-MM-DD ...")
            return 1

    added = 0
    for d in dates:
        if d in already:
            print(f"  YA EXISTE {d} en CSV")
            continue
        if _append_from_score(d):
            added += 1

    # Resumen
    if TRADES_LOG.exists():
        rows = list(csv.DictReader(open(TRADES_LOG, encoding="utf-8-sig")))
        wins   = sum(1 for r in rows if float(r.get("pnl_usd") or 0) > 0)
        losses = sum(1 for r in rows if float(r.get("pnl_usd") or 0) < 0)
        total  = sum(float(r.get("pnl_usd") or 0) for r in rows)
        wr     = wins / (wins + losses) * 100 if (wins + losses) else 0
        print(f"\nAgregados: {added} | CSV total: {len(rows)} trades | "
              f"WR {wr:.1f}% | PnL ${total:,.0f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
