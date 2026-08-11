"""Full DST-season featsweep with a SECOND-BY-SECOND global progress bar.

Wraps the proven runner `04_run_replay_featsweep_after_sync.py` as a subprocess
(so all its sync guards / X10 config / backups run UNCHANGED) and renders one
global bar that refreshes every second across all dates, with a live ETA:

    Featsweep ██████░░░░  42.3% | 12.5 min restantes | 104/246 | 2026-05-02

- The per-date "Esperando CSV terminal ..." spam from the child is suppressed;
  only key events (Guardado / Saltado / errores / versión) are echoed.
- The bar interpolates WITHIN the current date (elapsed / avg-per-date), so it
  moves every second instead of jumping once per ~90 s date.
- Child stdin is inherited: if X10 auto-config fails and the child asks for
  ENTER, you can still answer in the terminal (run this with `!`).

Usage (from the project dir):
    python -u 06_run_featsweep_full_bar.py            # full season, no --limit
    python -u 06_run_featsweep_full_bar.py --force    # re-run even if saved
    python -u 06_run_featsweep_full_bar.py --limit 5  # quick sanity

Any extra args are passed straight through to the 04 script.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from pathlib import Path

# make the bar glyphs survive a cp1252 stderr
try:
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

FILL, EMPTY = "█", "░"  # full / light block
CHILD = "04_run_replay_featsweep_after_sync.py"
SEED_DATE_SECONDS = 90.0          # ETA seed until we have a real measurement

# ----- child log patterns -------------------------------------------------
RE_TOTAL = re.compile(r"\((\d+)\s+sesiones\)")
RE_START = re.compile(r"Iniciando .* para (\d{4}-\d{2}-\d{2})")
RE_DONE = re.compile(r"^(Guardado|Saltado):")
# lines worth echoing to the user (everything else from the child is hidden)
RE_ECHO = re.compile(
    r"^(Guardado|Saltado|INICIANDO|Plan|Version|WARNING|ERROR|Replay no|"
    r"Configura|Configurando|Balance|Fecha NY|Ultima fecha|Resultados)"
)


class GlobalBar:
    """Thread-safe global progress with sub-date interpolation + ETA."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.total = 0            # 0 = still unknown (parsing the header)
        self.done = 0
        self.durations: list[float] = []
        self.active_date: str | None = None
        self.active_start = 0.0
        self.active_counted = True
        self.finished = False
        self.start = time.time()
        self._tty = getattr(sys.stderr, "isatty", lambda: False)()

    # -- events fed from the log reader -----------------------------------
    def set_total(self, n: int) -> None:
        with self.lock:
            if self.total == 0:
                self.total = max(n, 1)

    def date_started(self, date: str) -> None:
        with self.lock:
            # previous date ended without an explicit Guardado/Saltado (failure)
            if self.active_date is not None and not self.active_counted:
                self.done += 1
            self.active_date = date
            self.active_start = time.time()
            self.active_counted = False

    def date_done(self, saved: bool) -> None:
        with self.lock:
            if self.active_date is not None and not self.active_counted:
                self.done += 1
                if saved:  # only real replays feed the average (skips are ~0 s)
                    self.durations.append(time.time() - self.active_start)
                self.active_counted = True

    def finish(self) -> None:
        with self.lock:
            if self.active_date is not None and not self.active_counted:
                self.done += 1
            self.finished = True
        self.render(force=True)

    # -- rendering --------------------------------------------------------
    def _avg(self) -> float:
        return sum(self.durations) / len(self.durations) if self.durations else SEED_DATE_SECONDS

    def render(self, force: bool = False) -> None:
        with self.lock:
            total = self.total
            done = self.done
            avg = self._avg()
            active = self.active_date
            elapsed_cur = (time.time() - self.active_start) if (active and not self.active_counted) else 0.0
            finished = self.finished

        if total == 0:
            line = f"Featsweep {EMPTY * 10}   0.0% | arrancando... (leyendo plan)"
        else:
            frac_cur = min(elapsed_cur / avg, 0.98) if avg > 0 else 0.0
            eff_done = min(done + (frac_cur if active else 0.0), total)
            frac = min(max(eff_done / total, 0.0), 1.0)
            filled = round(frac * 10)
            bar = FILL * filled + EMPTY * (10 - filled)
            remaining = max(total - done, 0)
            eta_sec = max(avg * remaining - elapsed_cur, 0.0)
            eta_min = eta_sec / 60.0
            date_txt = active or "-"
            done_txt = "✓" if finished else ""
            line = (f"Featsweep {bar} {frac * 100:5.1f}% | "
                    f"{eta_min:5.1f} min restantes | {done}/{total} | {date_txt} {done_txt}")

        try:
            if self._tty and not finished:
                sys.stderr.write("\r\033[K" + line)
            else:
                sys.stderr.write(line + "\n")
            sys.stderr.flush()
        except Exception:
            pass


def ticker(bar: GlobalBar) -> None:
    """Repaint the bar every second until the run finishes."""
    while not bar.finished:
        bar.render()
        time.sleep(1.0)


def main() -> int:
    here = Path(__file__).resolve().parent
    child = here / CHILD
    if not child.exists():
        print(f"ERROR: no encuentro {CHILD} junto a este script.", file=sys.stderr)
        return 1

    passthrough = sys.argv[1:]
    cmd = [sys.executable, "-u", str(child), *passthrough]

    bar = GlobalBar()
    t = threading.Thread(target=ticker, args=(bar,), daemon=True)
    t.start()

    # stdin inherited so the child's ENTER fallback still works in a terminal.
    proc = subprocess.Popen(
        cmd,
        cwd=str(here),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )

    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip("\n")

        m = RE_TOTAL.search(line)
        if m:
            bar.set_total(int(m.group(1)))

        m = RE_START.search(line)
        if m:
            bar.date_started(m.group(1))

        if RE_DONE.match(line):
            bar.date_done(saved=line.startswith("Guardado:"))

        # echo only meaningful lines; hide the per-second "Esperando CSV" spam
        if RE_ECHO.match(line):
            # clear the bar line first so echoes don't collide with \r
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()
            print(line, flush=True)

    proc.wait()
    bar.finish()
    print(f"\nFeatsweep terminado. Exit code del runner: {proc.returncode}", flush=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
