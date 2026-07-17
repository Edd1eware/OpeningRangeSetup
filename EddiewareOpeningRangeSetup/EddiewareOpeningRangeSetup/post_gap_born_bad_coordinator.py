"""Retoma la coordinación desde un relleno X10 ya activo, con ETA Telegram."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from post_run_born_bad_coordinator import (
    RESULTS_FOLDER,
    _format_eta,
    _missing_dates,
    _run_research,
    _timed,
    _wait_existing,
)
from telegram_run_summary_after_sync import send_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gap-runner-pid", type=int, required=True)
    parser.add_argument("--gap-supervisor-pid", type=int, required=True)
    parser.add_argument("--gap-stdout", type=Path, required=True)
    parser.add_argument("--gap-stderr", type=Path, required=True)
    parser.add_argument("--initial-missing", type=int, required=True)
    return parser.parse_args()


def _current_eta(args: argparse.Namespace) -> tuple[int, float]:
    missing = len(_missing_dates())
    completed = max(0, args.initial_missing - missing)
    elapsed = max(1.0, time.time() - args.gap_stdout.stat().st_ctime)
    seconds_per_date = elapsed / completed if completed else 390.0
    return missing, missing * seconds_per_date


def main() -> int:
    args = parse_args()
    missing, eta = _current_eta(args)
    send_text(
        RESULTS_FOLDER,
        _timed(
            "ANALISIS  FAMILIAS A, B, C, ETC.\n"
            f"Relleno histórico X10 activo: {missing} sesiones terminales pendientes.",
            eta,
        ),
    )
    print(f"POST_GAP_COORDINATOR_READY missing={missing} eta={_format_eta(eta)}", flush=True)

    runner_code = _wait_existing(args.gap_runner_pid)
    supervisor_code = _wait_existing(args.gap_supervisor_pid)
    time.sleep(0.5)
    stderr = args.gap_stderr.read_text(encoding="utf-8", errors="replace").strip()
    if runner_code or supervisor_code or stderr:
        send_text(
            RESULTS_FOLDER,
            _timed(
                "GRUPO D NO EJECUTADO\nEl relleno X10 se detuvo; no se abrió el holdout. "
                f"runner={runner_code}, supervisor={supervisor_code}, stderr_vacio={not bool(stderr)}.",
                status="DETENIDA",
            ),
        )
        return 2

    remaining = _missing_dates()
    if remaining:
        send_text(
            RESULTS_FOLDER,
            _timed(
                f"GRUPO D NO EJECUTADO\nPersisten {len(remaining)} sesiones sin terminal; "
                "no se publicará una conclusión parcial.",
                status="DETENIDA",
            ),
        )
        return 3

    send_text(
        RESULTS_FOLDER,
        _timed(
            "ANALISIS  FAMILIAS A, B, C, ETC.\nETAPA GRUPO D INICIADA: estadística, modelos y reporte causal.",
            15 * 60,
        ),
    )
    research_code, research_stdout, research_stderr = _run_research()
    print(
        f"RESEARCH_EXIT code={research_code} stdout={research_stdout} stderr={research_stderr}",
        flush=True,
    )
    if research_code or research_stderr.stat().st_size:
        send_text(
            RESULTS_FOLDER,
            _timed(
                f"GRUPO D - ERROR DE INVESTIGACION\nLog: {research_stderr}",
                status="DETENIDA",
            ),
        )
        return 4
    if not send_text(RESULTS_FOLDER, _timed("ya termine todos mis procesos", 0)):
        return 5
    print("ALL_POST_RUN_PROCESSES_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
