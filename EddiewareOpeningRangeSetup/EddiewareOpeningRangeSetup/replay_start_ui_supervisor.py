"""Fallback externo para el botón Start de ATAS Replay.

No implementa ni modifica Replay. Observa el marcador que el runner ya escribe,
espera a que su clic físico tenga oportunidad de funcionar y, sólo si ATAS sigue
detenido, invoca el botón Start de la barra. No toca fechas, velocidad, Stop,
CSV, sincronización ni lógica de trading.
"""

from __future__ import annotations

import argparse
import ctypes
import time
from pathlib import Path

from pywinauto import Desktop


DEFAULT_MARKER = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
) / "replay_trade_result_started_at.txt"
STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def process_is_active(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def read_marker(path: Path) -> float | None:
    try:
        return float(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, ValueError):
        return None


def invoke_start_if_needed(marker: float, grace_seconds: float) -> str:
    time.sleep(grace_seconds)
    window = Desktop(backend="uia").window(title_re="Replay - .*")
    title = window.window_text()
    if "Loading modules" in title or "History playback" in title:
        return "RUNNER_CLICK_ALREADY_STARTED"
    start_button = window.child_window(title="Start", control_type="Button")
    if not start_button.exists(timeout=0.5):
        return "START_BUTTON_NOT_FOUND"
    if not start_button.is_enabled():
        return "START_ALREADY_DISABLED"
    start_button.invoke()
    return "START_INVOKED"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-pid", type=int, required=True)
    parser.add_argument("--marker", type=Path, default=DEFAULT_MARKER)
    parser.add_argument("--grace-seconds", type=float, default=1.5)
    parser.add_argument("--poll-seconds", type=float, default=0.1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    last_marker = read_marker(args.marker)
    print(
        f"SUPERVISOR_READY runner_pid={args.runner_pid} "
        f"last_marker={last_marker}",
        flush=True,
    )
    while process_is_active(args.runner_pid):
        marker = read_marker(args.marker)
        if marker is None or marker == last_marker:
            time.sleep(args.poll_seconds)
            continue
        last_marker = marker
        try:
            action = invoke_start_if_needed(marker, args.grace_seconds)
            print(f"marker={marker:.6f} action={action}", flush=True)
        except Exception as exc:
            print(f"marker={marker:.6f} action=ERROR error={exc}", flush=True)
    print("SUPERVISOR_EXIT runner_finished", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
