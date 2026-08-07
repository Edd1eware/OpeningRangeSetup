"""Replay each session in ATAS and screenshot the chart, for manual marking.

The point of this runner is the image, not the data. The operator reads the L2
structure off the ATAS chart itself and then takes the position on the CFD, so a
reconstruction plotted from the exported book is not a substitute: it cannot show
the footprint, the DOM or the indicators he is actually looking at.

The replay speed is never touched. Switching it is the operator's standing rule
number one, and this runner has no reason to break it: whatever ATAS is already
set to is what it runs at.

Completion is detected from the book recorder growing on disk when it is
attached, and falls back to a time budget derived from the window length when it
is not, because the chart may carry no recorder at all.

Usage:
    python -u 06_run_replay_screenshots_divergencia.py                 # preview
    python -u 06_run_replay_screenshots_divergencia.py --run --limit 20
    python -u 06_run_replay_screenshots_divergencia.py --run --dates 2026-08-04,2026-08-03
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import replay_sync_runner_common_after_sync as replay_sync   # noqa: E402

ANALYSIS = BASE / "context_divergencia" / "analysis"
sys.path.insert(0, str(ANALYSIS))
import tg                                                    # noqa: E402

BOOK_FOLDER = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
                   r"\book_recordings")
TARGET_DATE_FILE = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
                        r"\target_trade_result_date.txt")
SHOTS = Path(r"C:\Users\k_99_\Desktop\imagenes_IA\replay_atas")
CAPTURE = ANALYSIS / "capture_one.ps1"

# 45 minutes, because the chart shows about 45 one-minute bars at full screen and
# ATAS keeps the latest bar in view: a longer window simply scrolls the start of
# the structure off the left edge. Zooming out from code was tried and the chart
# ignores the keystroke.
REPLAY_FROM_TIME = "15:50"      # 24-hour NY; the common module renders the meridiem
REPLAY_TO_TIME = "16:35"
NY = ZoneInfo("America/New_York")

SEASON_START = date(2026, 3, 8)
SEASON_END = date(2026, 8, 4)
HOLIDAYS = {date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3)}

IDLE_TIMEOUT_S = 75             # no growth for this long means the replay ended
SETTLE_S = 6                    # let the chart finish drawing before the shot
BROKER_OFFSET_H = 7             # NY -> IC Markets broker clock, August


def session_dates() -> list[str]:
    out, d = [], SEASON_START
    while d <= SEASON_END:
        if d.weekday() < 5 and d not in HOLIDAYS:
            noon = dt.datetime(d.year, d.month, d.day, 12, tzinfo=NY)
            if noon.utcoffset() == timedelta(hours=-4):
                out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def to_minutes(hhmm: str) -> float:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def speed_multiple(text: str | None) -> float:
    """The replay speed ATAS reports, as a number. Never set, only read."""
    try:
        return max(1.0, float(str(text).strip().lower().rstrip("x")))
    except (TypeError, ValueError):
        return 2.0          # what ATAS was found on; a low guess only costs waiting


def budget_seconds(speed: float) -> float:
    """Wall-clock allowance for one replay at the speed ATAS is already set to."""
    a = dt.datetime.strptime(REPLAY_FROM_TIME, "%H:%M")
    b = dt.datetime.strptime(REPLAY_TO_TIME, "%H:%M")
    minutes = (b - a).total_seconds() / 60.0
    return max(180.0, minutes / speed * 60.0 * 1.6)      # 1.6x slack over nominal


CLOCK_RE = re.compile(r"\d{2}/\d{2}/\d{4}\s+(\d{1,2}):(\d{2}):(\d{2})\s*([ap])\.?\s*m",
                      re.IGNORECASE)


def replay_clock_minutes(replay) -> float | None:
    """Minutes-of-day of the clock the Replay panel is currently showing.

    This is the only completion signal that does not depend on an indicator being
    attached to the chart: the panel advances a real timestamp while it plays, so
    the replay is finished exactly when that timestamp reaches the TO bound. The
    book recorder cannot be relied on here — the chart the operator opened for
    these screenshots carries no recorder, so its files never grow.
    """
    for t in replay_sync.replay_texts(replay):
        m = CLOCK_RE.search(t)
        if not m:
            continue
        h, mi, _, ap = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4).lower()
        if ap == "p" and h != 12:
            h += 12
        elif ap == "a" and h == 12:
            h = 0
        return h * 60 + mi
    return None


def stream_sizes(date_iso: str) -> int:
    total = 0
    for kind in ("mbp", "mbo", "tape"):
        p = BOOK_FOLDER / f"{kind}_{date_iso}_NY.csv"
        if p.exists():
            total += p.stat().st_size
    return total


def atas_windows() -> list[tuple[int, str]]:
    """Visible top-level windows owned by ATAS, as (hwnd, title)."""
    import win32gui
    import win32process
    try:
        import psutil
        pids = {p.info["pid"] for p in psutil.process_iter(["pid", "name"])
                if (p.info["name"] or "").lower().startswith("oft.platform")}
    except Exception:
        pids = set()

    found: list[tuple[int, str]] = []

    def collect(hwnd: int, _ctx: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return
        if pids:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return
            if pid not in pids:
                return
        found.append((hwnd, title))

    win32gui.EnumWindows(collect, None)
    return found


def focus(needle: str) -> bool:
    """Bring an ATAS window to the front and un-minimise it.

    Necessary between every phase. Capturing the chart maximises it, which buries
    the Replay panel; a WPF window that is covered stops exposing its date
    pickers to UIA, and the next session then fails to set its range. So the
    Replay panel is raised before it is driven and the chart is raised before it
    is photographed, every time, rather than assuming the layout survived.
    """
    import win32con
    import win32gui
    for hwnd, title in atas_windows():
        if needle.lower() in title.lower():
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.BringWindowToTop(hwnd)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            time.sleep(0.8)
            return True
    return False


def chart_is_open() -> bool:
    """True when ATAS has a chart window open.

    Checked against top-level window titles, not the UIA panel tabs: ATAS keeps
    the chart in its own window, and its so-called main window is a 160x28 stub
    whose maximised form is the Accounts table. An earlier version photographed
    that table for every session and filed it as a deliverable.
    """
    from pywinauto import Desktop
    for w in Desktop(backend="uia").windows():
        try:
            t = (w.window_text() or "")
        except Exception:
            continue
        if "Chart" in t and "ATAS" not in t:
            return True
    return False


def shoot(date_iso: str) -> bool:
    if not chart_is_open():
        print("    captura OMITIDA: ATAS no tiene chart abierto")
        return False
    out = SHOTS / f"atas_{date_iso}.png"
    label = f"ATAS replay  ·  NQ  ·  {date_iso}  ·  {REPLAY_FROM_TIME}-{REPLAY_TO_TIME} NY"
    sub = (f"hora Nueva York.  equivalencia MT5: 16:00 NY = "
           f"{16 + BROKER_OFFSET_H - 24 if 16 + BROKER_OFFSET_H >= 24 else 16 + BROKER_OFFSET_H}"
           f":00 hora broker  (NY + {BROKER_OFFSET_H} h)")
    proc = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(CAPTURE),
         "-TitleMatch", "Chart", "-Out", str(out), "-Label", label, "-Sub", sub],
        capture_output=True, text=True, errors="replace",
    )
    ok = out.exists() and out.stat().st_size > 40_000
    print(f"    captura: {'ok' if ok else 'FALLO'}  {proc.stdout.strip()[-90:]}")
    return ok


def run_one(date_iso: str) -> bool:
    print(f"\n  [{date_iso}] preparando")
    TARGET_DATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TARGET_DATE_FILE.write_text(date_iso, encoding="utf-8")

    focus("Replay")
    replay, from_box, to_box, start_button, stop_button = replay_sync.get_replay_controls()
    if not replay_sync.ensure_replay_connected(replay):
        print("    FALLO: Replay no conecta")
        return False

    # Stop first, always. ATAS locks the date boxes while a replay is playing and
    # the setter then fails silently: the boxes keep the previous range and every
    # session replays the wrong day. A run that was interrupted leaves the replay
    # playing, so this is not a rare case.
    try:
        replay_sync.click_stop(stop_button)
        time.sleep(2.0)
    except Exception as exc:
        print(f"    aviso: no pude detener el replay previo ({exc})")

    # Stopping makes ATAS rebuild the Replay panel, and for a second or two the
    # FROM/TO pickers do not exist in the UIA tree at all. Asking once throws
    # "No encontré los campos FROM/TO de Replay" and loses the session.
    from_box = to_box = None
    for attempt in range(6):
        try:
            focus("Replay")
            from_box, to_box = replay_sync.refresh_replay_date_controls()
            break
        except Exception as exc:
            if attempt == 5:
                raise
            print(f"    panel Replay redibujandose ({attempt + 1}/6): {exc}")
            time.sleep(3.0)

    replay_sync.configure_replay_range(
        from_box, to_box, date_iso,
        replay_from_time=REPLAY_FROM_TIME, replay_to_time=REPLAY_TO_TIME,
    )
    # speed deliberately untouched: switching it is the operator's rule number one
    _, _, _, start_button, stop_button = replay_sync.get_replay_controls()

    print(f"    play  (velocidad actual: {replay_sync.get_replay_speed_text(replay)})")
    try:
        start_button.invoke()
    except Exception:
        start_button.click_input()

    t0 = time.time()
    budget = budget_seconds(speed_multiple(replay_sync.get_replay_speed_text(replay)))
    target = to_minutes(REPLAY_TO_TIME)
    last_clock, last_move = None, time.time()
    while True:
        time.sleep(5)
        now, elapsed = time.time(), time.time() - t0
        clock = replay_clock_minutes(replay)
        if clock is not None and clock != last_clock:
            last_clock, last_move = clock, now
        shown = f"{int(last_clock)//60:02d}:{int(last_clock)%60:02d}" if last_clock else "--:--"
        print(f"\r    t={elapsed:5.0f}s  reloj replay={shown}  meta="
              f"{REPLAY_TO_TIME}  presupuesto={budget:.0f}s", end="", flush=True)
        if last_clock is not None and last_clock >= target:
            print(f"\n    reloj alcanzo {REPLAY_TO_TIME} -> fin del replay")
            break
        if last_clock is not None and now - last_move > IDLE_TIMEOUT_S:
            print(f"\n    reloj detenido {IDLE_TIMEOUT_S}s en {shown} -> fin")
            break
        if elapsed > budget:
            print(f"\n    presupuesto agotado ({budget:.0f}s) -> fin")
            break

    time.sleep(SETTLE_S)
    focus("Chart")
    ok = shoot(date_iso)
    focus("Replay")
    replay_sync.click_stop(stop_button)
    time.sleep(1.5)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Screenshots del replay ATAS")
    ap.add_argument("--run", action="store_true", help="Ejecutar de verdad")
    ap.add_argument("--limit", type=int, default=20, help="Sesiones mas recientes")
    ap.add_argument("--dates", default="", help="Lista ISO separada por comas")
    ap.add_argument("--redo", action="store_true", help="Rehacer capturas existentes")
    args = ap.parse_args()

    explicit = [d.strip() for d in args.dates.split(",") if d.strip()]
    season = session_dates()
    dates = explicit or (season[-args.limit:] if args.limit > 0 else season)
    SHOTS.mkdir(parents=True, exist_ok=True)
    if not args.redo:
        dates = [d for d in dates if not (SHOTS / f"atas_{d}.png").exists()]

    print("=" * 70)
    print("SCREENSHOTS REPLAY ATAS - estudio divergencia 16:00 NY")
    print(f"  sesiones   : {len(dates)}")
    print(f"  ventana NY : {REPLAY_FROM_TIME} -> {REPLAY_TO_TIME}")
    try:
        spd = speed_multiple(replay_sync.get_replay_speed_text(
            replay_sync.get_replay_controls()[0]))
    except Exception:
        spd = 2.0
    print(f"  velocidad  : {spd:g}x (la que ya tenia ATAS, no se toca)")
    print(f"  presupuesto: {budget_seconds(spd):.0f}s por sesion  "
          f"(~{len(dates) * budget_seconds(spd) / 3600:.1f} h en el peor caso)")
    print(f"  salida     : {SHOTS}")
    print("=" * 70)
    if not args.run:
        print("\nPREVIEW. Nada tocado. Usa --run para capturar.")
        for d in dates:
            print(f"  {d}")
        return 0

    tg.msg(f"<b>Replay ATAS - inicio</b>\n{len(dates)} sesiones, ventana "
           f"{REPLAY_FROM_TIME}-{REPLAY_TO_TIME} NY. Aviso al terminar.")
    t0, ok = time.time(), 0
    for i, d in enumerate(dates, 1):
        try:
            if run_one(d):
                ok += 1
        except Exception as exc:
            print(f"\n    ERROR {d}: {exc}")
        done = time.time() - t0
        eta = done / i * (len(dates) - i)
        print(f"  progreso {i}/{len(dates)}  ok={ok}  "
              f"transcurrido {done/60:.1f} min  ETA {eta/60:.1f} min")

    tg.msg(f"<b>Replay ATAS - terminado</b>\n{ok}/{len(dates)} capturas en "
           f"{(time.time()-t0)/60:.0f} min.\nCarpeta: {SHOTS}")
    print(f"\n{ok}/{len(dates)} capturas -> {SHOTS}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
