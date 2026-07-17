"""Espera la corrida activa, completa huecos X10 y ejecuta Grupo D."""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import replay_sync_runner_common_after_sync as replay_sync
from telegram_run_summary_after_sync import send_text


BASE_DIR = Path(__file__).resolve().parent
RESULTS_FOLDER = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
)
OUTPUT_FOLDER = RESULTS_FOLDER / "visual_tests" / "04_run_replay_score_trade_results_dst_2025_2026_runs"
LOG_FOLDER = RESULTS_FOLDER / "research_run_logs"
NUMBERED_RUNNER = BASE_DIR / "04_run_replay_score_trade_results_dst_2025_2026_after_sync.py"
RESUME_RUNNER = BASE_DIR / "resume_replay_x10_uia_failfast.py"
SUPERVISOR = BASE_DIR / "replay_start_ui_supervisor.py"
RESEARCH = BASE_DIR / "born_bad_trade_research.py"
SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WAIT_OBJECT_0 = 0
INFINITE = 0xFFFFFFFF
CREATE_NO_WINDOW = 0x08000000


def _format_eta(seconds: float | int | None) -> str:
    if seconds is None:
        return "CALCULANDO"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _timed(message: str, eta: float | int | None = None, status: str = "") -> str:
    timer = status or _format_eta(eta)
    return f"{message}\nTimer etapa: {timer}"


def _open_process(pid: int):
    handle = ctypes.windll.kernel32.OpenProcess(
        SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        raise OSError(f"No pude abrir PID {pid}.")
    return handle


def _wait_exit(handle) -> int:
    status = ctypes.windll.kernel32.WaitForSingleObject(handle, INFINITE)
    if status != WAIT_OBJECT_0:
        raise OSError(f"WaitForSingleObject fallo: {status}")
    code = ctypes.c_ulong()
    if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
        raise OSError("GetExitCodeProcess fallo.")
    return int(code.value)


def _wait_existing(pid: int) -> int:
    handle = _open_process(pid)
    try:
        return _wait_exit(handle)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _all_dates() -> list[str]:
    spec = importlib.util.spec_from_file_location("post_run_numbered_runner", NUMBERED_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No pude cargar {NUMBERED_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [replay_sync.date_iso_from_replay(value) for value in module.DATES_DST]


def _missing_dates() -> list[str]:
    return [
        date_iso
        for date_iso in _all_dates()
        if not replay_sync.is_saved_run_complete(OUTPUT_FOLDER, date_iso, "X10_R1")
    ]


def _run_gap_fill() -> tuple[int, int, Path, Path]:
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    runner_out = LOG_FOLDER / f"gap_fill_x10_{stamp}_stdout.log"
    runner_err = LOG_FOLDER / f"gap_fill_x10_{stamp}_stderr.log"
    supervisor_out = LOG_FOLDER / f"gap_fill_x10_{stamp}_supervisor_stdout.log"
    supervisor_err = LOG_FOLDER / f"gap_fill_x10_{stamp}_supervisor_stderr.log"
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    with runner_out.open("w", encoding="utf-8") as out, runner_err.open("w", encoding="utf-8") as err:
        runner = subprocess.Popen(
            [
                sys.executable, "-u", str(RESUME_RUNNER), "--x10-only",
                "--from-date", "2022-04-04", "--to-date", "2026-07-16",
                "--section-label", "HISTORICAL_GAP_FILL_FOR_GROUP_D",
                "--preserve-telegram-history", "--defer-research",
            ],
            cwd=BASE_DIR,
            stdout=out,
            stderr=err,
            env=environment,
            creationflags=CREATE_NO_WINDOW,
        )
        time.sleep(0.75)
        with supervisor_out.open("w", encoding="utf-8") as sup_out, supervisor_err.open("w", encoding="utf-8") as sup_err:
            supervisor = subprocess.Popen(
                [sys.executable, "-u", str(SUPERVISOR), "--runner-pid", str(runner.pid)],
                cwd=BASE_DIR,
                stdout=sup_out,
                stderr=sup_err,
                env=environment,
                creationflags=CREATE_NO_WINDOW,
            )
            runner_code = runner.wait()
            supervisor_code = supervisor.wait()
    return runner_code, supervisor_code, runner_out, runner_err


def _run_research() -> tuple[int, Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stdout = LOG_FOLDER / f"born_bad_research_{stamp}_stdout.log"
    stderr = LOG_FOLDER / f"born_bad_research_{stamp}_stderr.log"
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        process = subprocess.run(
            [
                sys.executable, "-u", str(RESEARCH),
                "--results-folder", str(RESULTS_FOLDER), "--telegram",
            ],
            cwd=BASE_DIR,
            stdout=out,
            stderr=err,
            env=environment,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    return process.returncode, stdout, stderr


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-pid", type=int, required=True)
    parser.add_argument("--supervisor-pid", type=int, required=True)
    parser.add_argument("--runner-stdout", type=Path, required=True)
    parser.add_argument("--runner-stderr", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("POST_RUN_COORDINATOR_READY", flush=True)
    runner_code = _wait_existing(args.runner_pid)
    supervisor_code = _wait_existing(args.supervisor_pid)
    time.sleep(0.5)
    stdout = args.runner_stdout.read_text(encoding="utf-8", errors="replace")
    stderr = args.runner_stderr.read_text(encoding="utf-8", errors="replace").strip()
    terminal = "TERMINO LA PRUEBA DE TEMPORADAS DST COMPLETAS" in stdout
    if runner_code or supervisor_code or stderr or not terminal:
        send_text(
            RESULTS_FOLDER,
            _timed("GRUPO D NO EJECUTADO\n"
            f"La corrida activa no termino limpiamente: runner={runner_code}, "
            f"supervisor={supervisor_code}, stderr_vacio={not bool(stderr)}, terminal={terminal}.", status="DETENIDA"),
        )
        return 2

    missing = _missing_dates()
    print(f"MISSING_BEFORE_GAP_FILL={len(missing)}", flush=True)
    if missing:
        send_text(
            RESULTS_FOLDER,
            _timed("ANALISIS  FAMILIAS A, B, C, ETC.\n"
            f"GRUPO D EN COLA: faltan {len(missing)} sesiones X10 históricas. "
            "Se completarán sin --force y sin reiniciar balance antes de abrir el holdout.",
            len(missing) * replay_sync.SPEED_DEFAULT_SECONDS["X10"]),
        )
        gap_runner, gap_supervisor, gap_stdout, gap_stderr = _run_gap_fill()
        print(
            f"GAP_FILL_EXIT runner={gap_runner} supervisor={gap_supervisor} "
            f"stdout={gap_stdout} stderr={gap_stderr}",
            flush=True,
        )
        if gap_runner or gap_supervisor or gap_stderr.stat().st_size:
            send_text(
                RESULTS_FOLDER,
                _timed("GRUPO D NO EJECUTADO\n"
                "El relleno histórico X10 se detuvo en el primer fallo; no se abrió el holdout. "
                f"Log: {gap_stdout}", status="DETENIDA"),
            )
            return 3

    remaining = _missing_dates()
    print(f"MISSING_AFTER_GAP_FILL={len(remaining)}", flush=True)
    if remaining:
        send_text(
            RESULTS_FOLDER,
            _timed("GRUPO D NO EJECUTADO\n"
            f"Persisten {len(remaining)} sesiones X10 sin terminal. No se publicará ciencia parcial.", status="DETENIDA"),
        )
        return 4

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
            _timed("GRUPO D - ERROR DE INVESTIGACION\n"
            f"El replay quedó completo, pero el análisis falló. Log: {research_stderr}", status="DETENIDA"),
        )
        return 5

    if not send_text(RESULTS_FOLDER, _timed("ya termine todos mis procesos", 0)):
        return 6
    print("ALL_POST_RUN_PROCESSES_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
