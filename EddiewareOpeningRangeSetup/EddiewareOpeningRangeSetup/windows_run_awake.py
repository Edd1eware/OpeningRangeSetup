"""Mantiene Windows y la pantalla activos mientras una corrida siga viva.

Usa SetThreadExecutionState; no mueve mouse, no envía teclas y no modifica el
plan de energía persistente del usuario. Al salir restaura el estado normal.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import time
from collections.abc import Iterator, Sequence


ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def _set_execution_state(flags: int) -> None:
    result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
    if not result:
        raise ctypes.WinError()


@contextlib.contextmanager
def prevent_sleep() -> Iterator[None]:
    """Impide suspensión y apagado de pantalla durante el bloque activo."""

    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    _set_execution_state(flags)
    try:
        yield
    finally:
        # ES_CONTINUOUS sin requirements limpia las solicitudes de este thread.
        _set_execution_state(ES_CONTINUOUS)


def process_is_active(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return int(exit_code.value) == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def keep_awake_while_processes_run(
    pids: Sequence[int], heartbeat_seconds: float = 30.0
) -> int:
    watched = sorted({int(pid) for pid in pids if int(pid) > 0})
    if not watched:
        raise ValueError("Se requiere al menos un PID válido.")
    with prevent_sleep():
        print(f"KEEP_AWAKE_ACTIVE pids={watched}", flush=True)
        while any(process_is_active(pid) for pid in watched):
            # Renovar explícitamente la solicitud facilita auditar que el thread
            # protector sigue vivo durante corridas de muchas horas.
            _set_execution_state(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
            time.sleep(max(5.0, heartbeat_seconds))
    print("KEEP_AWAKE_RELEASED all_watched_processes_finished", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch-pid", type=int, action="append", required=True)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return keep_awake_while_processes_run(args.watch_pid, args.heartbeat_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
