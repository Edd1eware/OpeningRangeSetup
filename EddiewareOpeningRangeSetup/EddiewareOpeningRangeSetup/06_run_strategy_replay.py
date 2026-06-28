"""Recorre fechas en Replay X10 con el Execution Manager (strategy) ACTIVO.

El exporter publica la senal A+ Speed -> la ChartStrategy entra y gestiona. Este
runner solo MANEJA el Replay (configura rango, Play, espera, Stop) reusando el
motor existente. Los trades reales los coloca la estrategia en ATAS.

Requisitos antes de correr:
  1. ATAS abierto, chart con: Exporter + Visual + Strategy en "Started".
  2. Replay visible y al frente. Manos fuera del mouse/teclado.

Uso:
  python 06_run_strategy_replay.py              # solo las fechas A+ Speed (39, donde opera)
  python 06_run_strategy_replay.py --all        # todas las sesiones sincronizadas
  python 06_run_strategy_replay.py --dates 2026-05-15 2026-06-23
"""

import argparse
import csv
import re
from pathlib import Path

import replay_sync_runner_common_after_sync as rs
import telegram_run_summary_after_sync as telegram

LADDER_ROOT = (
    rs.RESULTS_FOLDER / "visual_tests" / "sync_ladder_runs" / "sync_v11_ladder_001_resume"
)
OUTPUT = rs.RESULTS_FOLDER / "visual_tests" / "strategy_tester_results"
OPER = rs.OPERATIVA_COMPARISON_FIELDS


def _row(path):
    try:
        return next(csv.DictReader(open(path, encoding="utf-8-sig")), None)
    except Exception:
        return None


def synced_dates(aplus_only):
    """Fechas sincronizadas (X1==X10). Si aplus_only, solo las A+ Speed."""
    out = []
    for x1 in LADDER_ROOT.glob("*/X1_R1/score_trade_result_*_NY.csv"):
        d = re.search(r"(\d{4}-\d{2}-\d{2})", x1.name).group(1)
        if d in out:
            continue
        x10 = x1.parent.parent / "X10_R1" / x1.name
        if not x10.exists():
            continue
        r1, r10 = _row(x1), _row(x10)
        if not r1 or not r10:
            continue
        if not all(str(r1.get(f, "") or "").strip() == str(r10.get(f, "") or "").strip() for f in OPER):
            continue
        if aplus_only and str(r10.get("APlus_Speed", "")).strip().upper() != "TRUE":
            continue
        out.append(d)
    return sorted(set(out))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Todas las sesiones (no solo A+ Speed).")
    parser.add_argument("--dates", nargs="*", help="Fechas especificas YYYY-MM-DD.")
    parser.add_argument("--prepare-only", action="store_true", help="Muestra las fechas sin correr.")
    args = parser.parse_args()

    if args.dates:
        dates = sorted(set(args.dates))
    else:
        dates = synced_dates(aplus_only=not args.all)

    print(f"Fechas a recorrer en Replay X10 (estrategia activa): {len(dates)}")
    for d in dates:
        print(" ", d)
    if args.prepare_only:
        print("\nPREPARE-ONLY. No se inicio Replay.")
        return 0

    OUTPUT.mkdir(parents=True, exist_ok=True)
    # Solo X10 (la estrategia opera en X10). force=True -> re-corre cada fecha.
    run_plan = [("X10_R1", "X10", rs.X10_TIMEOUT_SECONDS)]
    # progress_meta -> Telegram con ETA exacto por fecha (mediana de la X10 medida)
    # y alerta de error si fallan varias seguidas. Sin meta de 500 (no aplica).
    progress_meta = {
        "stage_index": 1,
        "stage_total": 1,
        "stage_label": "Strategy A+Speed replay",
        "stage_period": f"{dates[0]} -> {dates[-1]}" if dates else "",
        "global_target": None,
        "session_roots": None,
        "run_label": "Execution Manager",
    }

    telegram.send_text(
        rs.RESULTS_FOLDER,
        "EW Opening Range | Execution Manager - inicio del recorrido\n"
        f"{len(dates)} fechas en Replay X10 con la estrategia activa.\n"
        "Recibiras ETA por fecha. Si algo se atora, te avisare para reiniciar.",
    )

    try:
        passed, failures = rs.run_replay_period(
            dates,
            output_folder=OUTPUT,
            run_plan=run_plan,
            report_prefix="strategy_replay_test",
            force=True,
            replay_to_time=rs.DEFAULT_REPLAY_TO_TIME,
            progress_meta=progress_meta,
        )
    except KeyboardInterrupt:
        telegram.send_text(rs.RESULTS_FOLDER, "EW Opening Range | Recorrido CANCELADO (Ctrl+C).")
        raise
    except Exception as exc:
        telegram.send_text(
            rs.RESULTS_FOLDER,
            "EW Opening Range | ERROR FATAL en el recorrido\n"
            f"{exc}\nREINICIA ATAS/Replay, ventana al frente, y relanza el runner.",
        )
        raise

    fail_n = len(failures)
    msg = [
        "EW Opening Range | Execution Manager - recorrido TERMINADO",
        f"Fechas: {len(dates)} | con problemas: {fail_n}",
    ]
    if fail_n:
        msg.append("Fechas con error (re-corre solo esas relanzando):")
        msg += [f"- {d} {run}: {reason}" for d, run, reason in failures[:10]]
        if fail_n > 10:
            msg.append(f"... y {fail_n - 10} mas.")
        msg.append("Si muchas fallaron juntas: reinicia el Replay/ATAS.")
    msg.append("Revisa el P&L / trades de la estrategia en ATAS.")
    telegram.send_text(rs.RESULTS_FOLDER, "\n".join(msg))

    print("\nRecorrido terminado. Revisa el P&L / trades de la estrategia en ATAS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
