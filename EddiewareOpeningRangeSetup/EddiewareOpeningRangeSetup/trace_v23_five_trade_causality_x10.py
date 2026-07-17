"""Captura no invasiva de estados intermedios para la regresion v23.

Este script NO implementa Replay ni cambia su logica. Orquesta exclusivamente
``replay_sync_runner_common_after_sync.run_one_date`` en X10 y conserva cada
version observable de los artefactos que ATAS reescribe durante el calculo.

Todo archivo operacional tocado por ATAS se respalda en memoria y se restaura
byte por byte (incluyendo timestamps) al finalizar, aun ante una excepcion.
Telegram se silencia temporalmente agregando las fechas a
``telegram_sent_dates.txt``; el archivo original se restaura al terminar.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import replay_sync_runner_common_after_sync as replay
from pywinauto import Desktop


PROJECT_FOLDER = Path(__file__).resolve().parent
DEFAULT_OUTPUT = (
    PROJECT_FOLDER
    / "contexto_features_atas"
    / "regressions"
    / "OR_ABSORPTION_TEST_2026_V23_REPORT_X10_20260716_FAILED"
    / "causal_trace_x10"
)
DEFAULT_DATES = [
    "2026-03-30",
    "2026-04-20",
    "2026-05-26",
    "2026-06-02",
    "2026-07-15",
]


@dataclass(frozen=True)
class FileState:
    exists: bool
    data: bytes
    atime_ns: int | None
    mtime_ns: int | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_state(path: Path) -> FileState:
    try:
        stat = path.stat()
        return FileState(True, path.read_bytes(), stat.st_atime_ns, stat.st_mtime_ns)
    except FileNotFoundError:
        return FileState(False, b"", None, None)


def restore_state(path: Path, state: FileState) -> None:
    if not state.exists:
        path.unlink(missing_ok=True)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(state.data)
    if state.atime_ns is not None and state.mtime_ns is not None:
        os.utime(path, ns=(state.atime_ns, state.mtime_ns))


class ArtifactWatcher:
    def __init__(self, targets: dict[str, Path], output_folder: Path, poll_seconds: float):
        self.targets = targets
        self.output_folder = output_folder
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_hash: dict[str, str | None] = {name: None for name in targets}
        self._sequence = 0
        self._manifest: list[dict[str, object]] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._run, name="artifact-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> list[dict[str, object]]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._scan_once()
        manifest_path = self.output_folder / "capture_manifest.json"
        manifest_path.write_text(
            json.dumps(self._manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return list(self._manifest)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._scan_once()
            self._stop.wait(self.poll_seconds)

    def _scan_once(self) -> None:
        with self._lock:
            for label, path in self.targets.items():
                try:
                    data = path.read_bytes()
                    stat = path.stat()
                except (FileNotFoundError, PermissionError, OSError):
                    continue

                digest = sha256(data)
                if self._last_hash[label] == digest:
                    continue

                self._last_hash[label] = digest
                self._sequence += 1
                suffix = path.suffix or ".bin"
                capture_name = (
                    f"{self._sequence:06d}_{label}_{time.time_ns()}_{digest[:12]}{suffix}"
                )
                capture_path = self.output_folder / capture_name
                capture_path.write_bytes(data)
                self._manifest.append(
                    {
                        "sequence": self._sequence,
                        "captured_at_utc": utc_now(),
                        "label": label,
                        "source_path": str(path),
                        "source_mtime_ns": stat.st_mtime_ns,
                        "bytes": len(data),
                        "sha256": digest,
                        "capture_path": str(capture_path),
                    }
                )


class ReplayStartSupervisor:
    """Invoca Start una vez si el click fisico del runner no surte efecto.

    El supervisor no configura fechas, velocidad ni instrumentos. Espera el
    marcador que el runner escribe inmediatamente antes de su propio click y
    ejecuta el mismo comando WPF mediante UI Automation ``Invoke``.
    """

    def __init__(self):
        self.started_after_epoch = time.time()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.invoked = False
        self.error = ""

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="replay-start-supervisor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def _run(self) -> None:
        while not self._stop.wait(0.1):
            try:
                marker = float(replay.REPLAY_STARTED_FILE.read_text(encoding="utf-8").strip())
            except (FileNotFoundError, OSError, ValueError):
                continue
            if marker < self.started_after_epoch:
                continue

            # Give the runner's physical click enough time to transition WPF to
            # Loading/History playback. Without this grace both actions can land
            # in the same UI frame and the second one pauses playback.
            if self._stop.wait(1.5):
                return

            try:
                window = Desktop(backend="uia").window(title_re="Replay - .*")
                title = window.window_text()
                if "Loading modules" in title or "History playback" in title:
                    return
                start_button = window.child_window(title="Start", control_type="Button")
                if not start_button.exists(timeout=0.1):
                    continue
                if not start_button.is_enabled():
                    # The runner's own click already worked.
                    return
                start_button.invoke()
                self.invoked = True
                return
            except Exception as exc:  # best-effort external UI action
                self.error = str(exc)


class ReplayTerminalStopSupervisor:
    """Detiene History sólo después de que exista un exit canónico terminal."""

    def __init__(self, date_iso: str):
        self.date_iso = date_iso
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.invoked = False
        self.error = ""

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="replay-terminal-stop-supervisor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def _run(self) -> None:
        snapshot_path = replay.sync_result_path(self.date_iso)
        while not self._stop.wait(0.02):
            try:
                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                result = str(payload.get("Result", "")).strip().upper()
            except (FileNotFoundError, PermissionError, OSError, ValueError, TypeError):
                continue
            if result in {"", "OPEN"}:
                continue

            try:
                window = Desktop(backend="uia").window(title_re="Replay - .*")
                stop_button = window.child_window(title="Stop", control_type="Button")
                if stop_button.exists(timeout=0.1) and stop_button.is_enabled():
                    stop_button.invoke()
                    self.invoked = True
                return
            except Exception as exc:
                self.error = str(exc)


def ensure_replay_stopped_via_uia(wait_seconds: float = 15.0) -> bool:
    """Confirma Stop por UIA cuando el click fisico del runner no se registra."""

    deadline = time.monotonic() + wait_seconds
    invoked = False
    while time.monotonic() < deadline:
        try:
            window = Desktop(backend="uia").window(title_re="Replay.*")
            title = window.window_text()
            if "playback is stopped" in title.lower() or title == "Replay":
                return invoked
            stop_button = window.child_window(title="Stop", control_type="Button")
            if stop_button.exists(timeout=0.1) and stop_button.is_enabled():
                stop_button.invoke()
                invoked = True
        except Exception:
            pass
        time.sleep(0.25)
    return invoked


def volatile_paths(dates: list[str]) -> list[Path]:
    paths = [
        replay.RESULTS_FOLDER / "trade_inputs.csv",
        replay.RESULTS_FOLDER / "trade_results.csv",
        replay.RESULTS_FOLDER / "telegram_balance.json",
        replay.RESULTS_FOLDER / "telegram_sent_dates.txt",
        replay.RESULTS_FOLDER / "telegram_message_ids.txt",
        replay.RESULTS_FOLDER / "telegram_challenge_passed.flag",
        replay.RESULTS_FOLDER / "exporter_lifecycle_diagnostics.csv",
        replay.TARGET_FILE,
        replay.REPLAY_STARTED_FILE,
    ]
    for date_iso in dates:
        paths.extend(
            [
                replay.result_path(date_iso),
                replay.timeline_path(date_iso),
                replay.sync_signal_path(date_iso),
                replay.sync_result_path(date_iso),
                replay.RESULTS_FOLDER / f"market_feed_diagnostics_{date_iso}_NY.csv",
            ]
        )
    return list(dict.fromkeys(paths))


def suppress_telegram(dates: list[str]) -> None:
    sent_dates = replay.RESULTS_FOLDER / "telegram_sent_dates.txt"
    existing: list[str] = []
    if sent_dates.exists():
        existing = [line.strip() for line in sent_dates.read_text(encoding="utf-8").splitlines()]
    merged = list(dict.fromkeys([line for line in existing if line] + dates))
    sent_dates.parent.mkdir(parents=True, exist_ok=True)
    sent_dates.write_text("".join(f"{date_iso}\n" for date_iso in merged), encoding="utf-8")


def trial_targets(date_iso: str) -> dict[str, Path]:
    return {
        "score_result": replay.result_path(date_iso),
        "dynamic_timeline": replay.timeline_path(date_iso),
        "sync_signal": replay.sync_signal_path(date_iso),
        "sync_result": replay.sync_result_path(date_iso),
        "trade_inputs": replay.RESULTS_FOLDER / "trade_inputs.csv",
        "trade_results": replay.RESULTS_FOLDER / "trade_results.csv",
        "market_feed": replay.RESULTS_FOLDER / f"market_feed_diagnostics_{date_iso}_NY.csv",
        "telegram_balance": replay.RESULTS_FOLDER / "telegram_balance.json",
    }


def copy_final_artifacts(date_iso: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for label, source in trial_targets(date_iso).items():
        if not source.exists():
            continue
        target = destination / f"{label}{source.suffix}"
        shutil.copy2(source, target)


def run_trace(
    dates: list[str],
    cycles: int,
    output_folder: Path,
    poll_seconds: float,
    timeout_seconds: float,
) -> int:
    output_folder.mkdir(parents=True, exist_ok=True)
    states = {path: save_state(path) for path in volatile_paths(dates)}
    run_manifest: list[dict[str, object]] = []
    active_watcher: ArtifactWatcher | None = None
    active_start_supervisor: ReplayStartSupervisor | None = None
    active_terminal_stop_supervisor: ReplayTerminalStopSupervisor | None = None

    try:
        suppress_telegram(dates)
        replay.set_replay_speed("X10")

        for cycle in range(1, cycles + 1):
            for date_iso in dates:
                ensure_replay_stopped_via_uia()
                # Fresh canonical state for every trial. Exact paths only; all are
                # restored from ``states`` in the outer finally block.
                replay.sync_signal_path(date_iso).unlink(missing_ok=True)
                replay.sync_result_path(date_iso).unlink(missing_ok=True)

                trial_name = f"cycle_{cycle:02d}_{date_iso}"
                trial_folder = output_folder / "trials" / trial_name
                capture_folder = trial_folder / "captures"
                active_watcher = ArtifactWatcher(
                    trial_targets(date_iso), capture_folder, poll_seconds
                )
                active_watcher.start()
                active_start_supervisor = ReplayStartSupervisor()
                active_start_supervisor.start()
                active_terminal_stop_supervisor = ReplayTerminalStopSupervisor(date_iso)
                active_terminal_stop_supervisor.start()

                started = time.monotonic()
                ok = False
                reason = ""
                try:
                    ok, reason = replay.run_one_date(
                        date_iso,
                        "X10_TRACE",
                        timeout_seconds,
                        trial_folder,
                        force=True,
                        replay_from_time="09:30",
                        replay_to_time="10:30",
                        keep_global_result=False,
                    )
                    ensure_replay_stopped_via_uia()
                    # Allow late exporter recalculations to become observable.
                    time.sleep(2.0)
                    copy_final_artifacts(date_iso, trial_folder / "final_observed")
                finally:
                    active_terminal_stop_supervisor.stop()
                    active_start_supervisor.stop()
                    captures = active_watcher.stop()
                    active_watcher = None

                entry = {
                    "cycle": cycle,
                    "date": date_iso,
                    "mode": "Historia X10 únicamente",
                    "replay_x1": "DESHABILITADO",
                    "ok": ok,
                    "reason": reason,
                    "duration_seconds": round(time.monotonic() - started, 6),
                    "capture_count": len(captures),
                    "uia_start_supervisor_invoked": active_start_supervisor.invoked,
                    "uia_start_supervisor_error": active_start_supervisor.error,
                    "uia_terminal_stop_invoked": active_terminal_stop_supervisor.invoked,
                    "uia_terminal_stop_error": active_terminal_stop_supervisor.error,
                    "trial_folder": str(trial_folder),
                    "completed_at_utc": utc_now(),
                }
                run_manifest.append(entry)
                active_start_supervisor = None
                active_terminal_stop_supervisor = None
                (output_folder / "run_manifest.json").write_text(
                    json.dumps(run_manifest, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(json.dumps(entry, ensure_ascii=False), flush=True)

                # Do not let a just-written snapshot become canonical input for
                # another independent trial of the same date.
                replay.sync_signal_path(date_iso).unlink(missing_ok=True)
                replay.sync_result_path(date_iso).unlink(missing_ok=True)

        return 0 if all(bool(item["ok"]) for item in run_manifest) else 2
    finally:
        ensure_replay_stopped_via_uia()
        if active_watcher is not None:
            active_watcher.stop()
        if active_start_supervisor is not None:
            active_start_supervisor.stop()
        if active_terminal_stop_supervisor is not None:
            active_terminal_stop_supervisor.stop()
        for path, state in states.items():
            restore_state(path, state)

        verification = []
        for path, state in states.items():
            current = save_state(path)
            verification.append(
                {
                    "path": str(path),
                    "expected_exists": state.exists,
                    "actual_exists": current.exists,
                    "expected_sha256": sha256(state.data) if state.exists else None,
                    "actual_sha256": sha256(current.data) if current.exists else None,
                    "bytes_restored": current.exists == state.exists and current.data == state.data,
                }
            )
        (output_folder / "restoration_verification.json").write_text(
            json.dumps(verification, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--dates", nargs="+", default=DEFAULT_DATES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--poll-ms", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=replay.X10_TIMEOUT_SECONDS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.cycles < 1:
        raise SystemExit("--cycles debe ser >= 1")
    if args.poll_ms <= 0:
        raise SystemExit("--poll-ms debe ser > 0")
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds debe ser > 0")
    return run_trace(
        args.dates,
        args.cycles,
        args.output.resolve(),
        args.poll_ms / 1000.0,
        args.timeout_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
