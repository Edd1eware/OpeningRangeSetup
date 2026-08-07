"""Multi-session sweep for the 16:00 NY divergence study over DST 2026.

Wraps the single-date runner so the capture logic stays in one place. Skips
sessions already captured, so the sweep is resumable after an interruption.

Usage:
    python -u 05_run_replay_divergence_dst2026.py                    # preview
    python -u 05_run_replay_divergence_dst2026.py --probe            # 4 spread dates
    python -u 05_run_replay_divergence_dst2026.py --run              # full season
    python -u 05_run_replay_divergence_dst2026.py --run --limit 20   # newest 20
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
BOOK_DIR = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\book_recordings")
SINGLE = BASE / "04_run_replay_divergence_1600ny.py"
NY = ZoneInfo("America/New_York")

SEASON_START = date(2026, 3, 8)      # DST 2026 begins
SEASON_END = date(2026, 8, 4)        # capped at the reference session
MIN_MBP_BYTES = 500_000              # below this the session did not really record

# NYSE holidays inside the window; CME equity futures also close or shorten.
HOLIDAYS = {date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3)}


def session_dates() -> list[str]:
    out = []
    d = SEASON_START
    while d <= SEASON_END:
        if d.weekday() < 5 and d not in HOLIDAYS:
            noon = dt.datetime(d.year, d.month, d.day, 12, tzinfo=NY)
            if noon.utcoffset() == timedelta(hours=-4):
                out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def already_captured(date_iso: str) -> bool:
    """A session counts as captured only if it actually covers the 16:00 window.

    Older recordings on disk use the 09:25-15:35 opening window and are large
    enough to pass a size check, so the coverage has to be read from the file.
    """
    mbp = BOOK_DIR / f"mbp_{date_iso}_NY.csv"
    try:
        if mbp.stat().st_size < MIN_MBP_BYTES:
            return False
        with mbp.open("rb") as fh:
            fh.seek(max(0, mbp.stat().st_size - 65536))
            tail = fh.read().decode("utf-8", "ignore")
    except OSError:
        return False
    stamps = [ln.split(",", 1)[0] for ln in tail.splitlines()[1:] if ":" in ln[:12]]
    return bool(stamps) and max(stamps) >= "16:00:00"


def capture(date_iso: str) -> tuple[bool, int, int, float]:
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, "-u", str(SINGLE), "--run", "--date", date_iso],
        cwd=str(BASE), capture_output=True, text=True, errors="replace",
    )
    mbp = BOOK_DIR / f"mbp_{date_iso}_NY.csv"
    tape = BOOK_DIR / f"tape_{date_iso}_NY.csv"
    mbp_b = mbp.stat().st_size if mbp.exists() else 0
    tape_b = tape.stat().st_size if tape.exists() else 0
    ok = proc.returncode == 0 and mbp_b >= MIN_MBP_BYTES
    if not ok:
        tail = (proc.stdout or "")[-400:]
        print(f"      rc={proc.returncode} salida: {tail.strip()[-200:]}")
    return ok, mbp_b, tape_b, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--probe", action="store_true", help="4 dates spread over the season")
    ap.add_argument("--limit", type=int, default=0, help="newest N sessions only")
    args = ap.parse_args()

    dates = session_dates()
    if args.probe:
        n = len(dates)
        dates = [dates[0], dates[n // 3], dates[2 * n // 3], dates[-2]]
    elif args.limit:
        dates = dates[-args.limit:]

    pending = [d for d in dates if not already_captured(d)]
    done = len(dates) - len(pending)

    print("=" * 70)
    print("BARRIDO DIVERGENCIA L2 16:00 NY - DST 2026")
    print(f"  sesiones objetivo : {len(dates)}")
    print(f"  ya capturadas     : {done}")
    print(f"  pendientes        : {len(pending)}")
    print(f"  estimado          : {len(pending) * 7 / 60:.1f} h a ~7 min/sesion")
    print("=" * 70)
    if not args.run:
        print("\nPREVIEW. Usa --run para capturar.")
        for d in pending[:10]:
            print("   ", d)
        if len(pending) > 10:
            print(f"    ... +{len(pending)-10} mas")
        return 0

    results = []
    t_start = time.time()
    for i, d in enumerate(pending, 1):
        elapsed = time.time() - t_start
        eta = (elapsed / max(i - 1, 1)) * (len(pending) - i + 1) if i > 1 else 0
        print(f"\n[{i}/{len(pending)}] {d}   transcurrido {elapsed/60:.1f} min   ETA {eta/60:.1f} min")
        ok, mbp_b, tape_b, secs = capture(d)
        results.append((d, ok, mbp_b, tape_b))
        flag = "OK  " if ok else "VACIO"
        print(f"      {flag} mbp={mbp_b:>10,} B  tape={tape_b:>9,} B  [{secs:.0f}s]")

    print("\n" + "=" * 70)
    good = [r for r in results if r[1]]
    print(f"RESUMEN: {len(good)}/{len(results)} sesiones con datos")
    for d, ok, m, t in results:
        if not ok:
            print(f"  SIN DATOS: {d}")
    print(f"tiempo total: {(time.time()-t_start)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
