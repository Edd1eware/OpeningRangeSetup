"""Envia el cierre solicitado cuando runner y supervisor terminan correctamente."""

from __future__ import annotations

import argparse
import ctypes
import time
from pathlib import Path

from telegram_run_summary_after_sync import send_text


SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WAIT_OBJECT_0 = 0x00000000
INFINITE = 0xFFFFFFFF
RESULTS_FOLDER = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
)


def open_process(pid: int):
    handle = ctypes.windll.kernel32.OpenProcess(
        SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        pid,
    )
    if not handle:
        raise OSError(f"No pude abrir PID {pid} para esperar su salida.")
    return handle


def wait_exit_code(handle) -> int:
    status = ctypes.windll.kernel32.WaitForSingleObject(handle, INFINITE)
    if status != WAIT_OBJECT_0:
        raise OSError(f"WaitForSingleObject fallo: status={status}")
    code = ctypes.c_ulong()
    if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
        raise OSError("GetExitCodeProcess fallo.")
    return int(code.value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-pid", type=int, required=True)
    parser.add_argument("--supervisor-pid", type=int, required=True)
    parser.add_argument("--runner-stdout", type=Path, required=True)
    parser.add_argument("--runner-stderr", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runner_handle = open_process(args.runner_pid)
    supervisor_handle = open_process(args.supervisor_pid)
    try:
        runner_code = wait_exit_code(runner_handle)
        supervisor_code = wait_exit_code(supervisor_handle)
    finally:
        ctypes.windll.kernel32.CloseHandle(runner_handle)
        ctypes.windll.kernel32.CloseHandle(supervisor_handle)

    # Deja que los buffers de los dos procesos terminen de vaciarse.
    time.sleep(0.5)
    stdout = args.runner_stdout.read_text(encoding="utf-8", errors="replace")
    stderr = args.runner_stderr.read_text(encoding="utf-8", errors="replace").strip()
    terminal_marker = "TERMINO LA PRUEBA DE TEMPORADAS DST COMPLETAS"

    if runner_code == 0 and supervisor_code == 0 and not stderr and terminal_marker in stdout:
        if not send_text(RESULTS_FOLDER, "ya termine todos mis procesos"):
            print("COMPLETION_TELEGRAM_FAILED", flush=True)
            return 3
        print("COMPLETION_TELEGRAM_SENT", flush=True)
        return 0

    print(
        "COMPLETION_TELEGRAM_NOT_SENT "
        f"runner_exit={runner_code} supervisor_exit={supervisor_code} "
        f"stderr_empty={not bool(stderr)} terminal_marker={terminal_marker in stdout}",
        flush=True,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
