"""Replay runner for the 16:00 NY L2 divergence study.

Records one session at a time through the "ATRAPADOS Book Recorder" indicator,
over an afternoon window that the older runners could not express.

Deliberately separate from the LVN runner: that one owns its own speed/window
logic and must not be touched.

Usage:
    python -u 04_run_replay_divergence_1600ny.py                  # preview only
    python -u 04_run_replay_divergence_1600ny.py --run            # capture 2026-08-04
    python -u 04_run_replay_divergence_1600ny.py --run --date 2026-08-03
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import replay_sync_runner_common_after_sync as replay_sync

BOOK_FOLDER = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\book_recordings")
TARGET_DATE_FILE = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\target_trade_result_date.txt"
)

DEFAULT_DATE = "2026-08-04"
REPLAY_FROM_TIME = "15:40"   # 24-hour NY; the common module renders the meridiem
REPLAY_TO_TIME = "16:25"
REPLAY_SPEED = "X10"
# The recorder flushes every couple of seconds, so a running replay always grows
# the file. Stalled growth is therefore the reliable end-of-run signal; the status
# file is not, because it is now rewritten on every flush.
IDLE_TIMEOUT_SECONDS = 60
HARD_TIMEOUT_SECONDS = 1800


def stream_paths(date_iso: str) -> dict[str, Path]:
    return {
        "mbp": BOOK_FOLDER / f"mbp_{date_iso}_NY.csv",
        "mbo": BOOK_FOLDER / f"mbo_{date_iso}_NY.csv",
        "tape": BOOK_FOLDER / f"tape_{date_iso}_NY.csv",
    }


def status_path(date_iso: str) -> Path:
    return BOOK_FOLDER / f"bookrec_status_{date_iso}.txt"


def sizes(paths: dict[str, Path]) -> dict[str, int]:
    out = {}
    for name, path in paths.items():
        try:
            out[name] = path.stat().st_size
        except OSError:
            out[name] = 0
    return out


def archive_existing(date_iso: str) -> None:
    """Move any prior capture aside so byte growth is unambiguous.

    ATAS keeps its StreamWriter open on the CSV between replay runs, so the
    rename can fail. That is not fatal: the recorder simply appends, and the
    duplicate rows are removed downstream on exact timestamp+side+price+volume.
    """
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for path in list(stream_paths(date_iso).values()) + [status_path(date_iso)]:
        if not path.exists():
            continue
        backup = path.with_name(f"{path.stem}.pre_{stamp}{path.suffix}")
        try:
            path.rename(backup)
            print(f"  archivado {path.name} -> {backup.name}")
        except PermissionError:
            print(f"  AVISO {path.name} bloqueado por ATAS; se anexara y deduplicara")


def read_status(date_iso: str) -> dict[str, str] | None:
    path = status_path(date_iso)
    if not path.exists():
        return None
    out = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay 16:00 NY divergence capture")
    parser.add_argument("--date", default=DEFAULT_DATE, help="Session date, ISO")
    parser.add_argument("--run", action="store_true", help="Actually drive ATAS")
    parser.add_argument("--from-time", default=REPLAY_FROM_TIME)
    parser.add_argument("--to-time", default=REPLAY_TO_TIME)
    args = parser.parse_args()

    date_iso = args.date
    date_replay = replay_sync.date_replay_from_iso(date_iso)
    from_clock, from_suffix = replay_sync.format_replay_clock(args.from_time)
    to_clock, to_suffix = replay_sync.format_replay_clock(args.to_time)

    print("=" * 68)
    print("REPLAY DIVERGENCIA L2 16:00 NY")
    print(f"  fecha      : {date_iso}  ({date_replay})")
    print(f"  ventana NY : {args.from_time} -> {args.to_time}")
    print(f"  ATAS espera: {from_clock} {from_suffix} -> {to_clock} {to_suffix}")
    print(f"  velocidad  : {REPLAY_SPEED}")
    print(f"  salida     : {BOOK_FOLDER}")
    print("=" * 68)

    if not args.run:
        print("\nPREVIEW. Nada tocado. Usa --run para capturar de verdad.")
        return 0

    print(f"\n[1/6] target-date -> {date_iso}")
    TARGET_DATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TARGET_DATE_FILE.write_text(date_iso, encoding="utf-8")

    print("[2/6] archivando capturas previas de esta fecha")
    BOOK_FOLDER.mkdir(parents=True, exist_ok=True)
    archive_existing(date_iso)

    print("[3/6] tomando controles del Replay")
    replay, from_box, to_box, start_button, stop_button = replay_sync.get_replay_controls()

    print("[4/6] conectando Replay (desconecta datos en vivo mientras corre)")
    if not replay_sync.ensure_replay_connected(replay):
        print("FALLO: no pude conectar el Replay.")
        return 2
    from_box, to_box = replay_sync.refresh_replay_date_controls()

    print("[5/6] fijando rango y velocidad")
    replay_sync.configure_replay_range(
        from_box,
        to_box,
        date_iso,
        replay_from_time=args.from_time,
        replay_to_time=args.to_time,
    )
    try:
        replay_sync.set_replay_speed(REPLAY_SPEED)
    except Exception as exc:
        print(f"  aviso: no pude fijar velocidad ({exc}); sigo con la actual")

    _, _, _, start_button, stop_button = replay_sync.get_replay_controls()

    print("[6/6] Play")
    started_at = time.time()
    try:
        start_button.invoke()
    except Exception:
        start_button.click_input()

    paths = stream_paths(date_iso)
    last_sizes = sizes(paths)
    last_growth = time.time()

    while True:
        time.sleep(5)
        now = time.time()
        elapsed = now - started_at
        current = sizes(paths)
        grew = any(current[k] > last_sizes[k] for k in current)
        if grew:
            last_growth = now
        last_sizes = current

        total_kb = sum(current.values()) / 1024
        print(
            f"\r  t={elapsed:6.0f}s  mbp={current['mbp']/1024:9.0f}KB  "
            f"mbo={current['mbo']/1024:8.0f}KB  tape={current['tape']/1024:8.0f}KB  "
            f"total={total_kb:9.0f}KB",
            end="",
            flush=True,
        )

        if now - last_growth > IDLE_TIMEOUT_SECONDS:
            print(f"\n  sin crecimiento por {IDLE_TIMEOUT_SECONDS}s -> asumo fin")
            break
        if elapsed > HARD_TIMEOUT_SECONDS:
            print(f"\n  timeout duro {HARD_TIMEOUT_SECONDS}s")
            break

    print("  deteniendo replay")
    replay_sync.click_stop(stop_button)
    time.sleep(1.5)

    print("\n" + "=" * 68)
    print("RESULTADO")
    final = sizes(paths)
    for name, path in paths.items():
        print(f"  {name:5s} {final[name]:>12,d} B   {path.name}")
    status = read_status(date_iso)
    if status:
        print("  status:", status)
    else:
        print("  status: (sin archivo)")

    captured = sum(final.values())
    if captured == 0:
        print("\nVEREDICTO: NADA CAPTURADO.")
        print("  Causas posibles, en orden:")
        print("   1. 'ATRAPADOS Book Recorder' no esta en el chart")
        print("   2. su ventana NY no cubre 15:40-16:25")
        print("   3. el replay no tiene datos para esa fecha")
        return 3

    print("\nVEREDICTO: datos capturados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
