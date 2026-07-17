"""Fallback externo para el botón Start de ATAS Replay.

No implementa ni modifica Replay. Observa el marcador que el runner ya escribe,
espera a que su clic físico tenga oportunidad de funcionar y, sólo si ATAS sigue
detenido, invoca el botón Start de la barra. No toca fechas, velocidad, Stop,
CSV, sincronización ni lógica de trading.
"""

from __future__ import annotations

import argparse
import ctypes
import csv
import time
from pathlib import Path

from pywinauto import Desktop


DEFAULT_MARKER = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
) / "replay_trade_result_started_at.txt"
EXPORT_FOLDER = DEFAULT_MARKER.parent
RESULTS_FOLDER = EXPORT_FOLDER / "trade_results_score"
TARGET_FILE = EXPORT_FOLDER / "target_trade_result_date.txt"
EXPECTED_EXPORTER_VERSION = "score-exporter-2026-07-16-v23-liquidity-burst-entry"
TERMINAL_RESULTS = {"TP", "SL", "EXIT", "BE", "TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}
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


def read_target_date() -> str:
    try:
        return TARGET_FILE.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return ""


def result_path(date_iso: str) -> Path:
    return RESULTS_FOLDER / f"score_trade_result_{date_iso}_NY.csv"


def read_terminal_content(path: Path, marker: float) -> str | None:
    try:
        if path.stat().st_mtime < marker:
            return None
        content = path.read_text(encoding="utf-8-sig")
        row = next(csv.DictReader(content.splitlines()), None) or {}
    except (FileNotFoundError, PermissionError, OSError, UnicodeError, csv.Error):
        return None
    if str(row.get("Exporter_VERSION", "")).strip() != EXPECTED_EXPORTER_VERSION:
        return None
    if str(row.get("Result_Label", "")).strip().upper() not in TERMINAL_RESULTS:
        return None
    return content


def invoke_stop_after_stable_terminal(date_iso: str, marker: float, stable_seconds: float) -> str | None:
    path = result_path(date_iso)
    content_before = read_terminal_content(path, marker)
    if content_before is None:
        return None
    time.sleep(stable_seconds)
    content_after = read_terminal_content(path, marker)
    if content_after is None or content_after != content_before:
        return None
    window = Desktop(backend="uia").window(title_re="Replay.*")
    title = window.window_text().lower()
    if "playback is stopped" in title or title == "replay":
        return "REPLAY_ALREADY_STOPPED"
    stop_button = window.child_window(title="Stop", control_type="Button")
    if not stop_button.exists(timeout=0.5):
        return "STOP_BUTTON_NOT_FOUND"
    if not stop_button.is_enabled():
        return "STOP_ALREADY_DISABLED"
    stop_button.invoke()
    return "STOP_INVOKED_AFTER_STABLE_TERMINAL"


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
    active_marker: float | None = None
    stop_handled_for_marker = False
    print(
        f"SUPERVISOR_READY runner_pid={args.runner_pid} "
        f"last_marker={last_marker}",
        flush=True,
    )
    while process_is_active(args.runner_pid):
        marker = read_marker(args.marker)
        if marker is None or marker == last_marker:
            pass
        else:
            last_marker = marker
            active_marker = marker
            stop_handled_for_marker = False
            try:
                action = invoke_start_if_needed(marker, args.grace_seconds)
                print(f"marker={marker:.6f} action={action}", flush=True)
            except Exception as exc:
                print(f"marker={marker:.6f} action=ERROR error={exc}", flush=True)

        if active_marker is not None and not stop_handled_for_marker:
            date_iso = read_target_date()
            if date_iso:
                try:
                    stop_action = invoke_stop_after_stable_terminal(date_iso, active_marker, 1.25)
                    if stop_action is not None:
                        stop_handled_for_marker = True
                        print(
                            f"marker={active_marker:.6f} date={date_iso} action={stop_action}",
                            flush=True,
                        )
                except Exception as exc:
                    print(
                        f"marker={active_marker:.6f} date={date_iso} "
                        f"action=STOP_ERROR error={exc}",
                        flush=True,
                    )
        time.sleep(args.poll_seconds)
    print("SUPERVISOR_EXIT runner_finished", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
