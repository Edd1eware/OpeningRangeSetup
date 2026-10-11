"""Reusable 10-block progress bar for long-running analysis scripts.

Renders:  label ██████░░░░  60.0% | 4.2 min restantes
- 10 squares filling up (█ filled, ░ empty)
- percent + ETA in minutes remaining
- writes to stderr, ALWAYS flushed (survives redirection to a log file)
- in-place update via \\r on a TTY; one line per tick when piped to a file

Usage A (wrap an iterable):
    from progress import track
    for date in track(dates, label="MBO build"):
        ...

Usage B (manual):
    from progress import ProgressBar
    bar = ProgressBar(len(dates), label="MBO build")
    for d in dates:
        ...
        bar.update()
    bar.close()
"""

from __future__ import annotations

import sys
import time

# make █/░ survive even when stderr is redirected to a file (cp1252 default)
try:
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

FILL, EMPTY = "█", "░"  # █ ░


class ProgressBar:
    def __init__(self, total: int, label: str = "", width: int = 10,
                 min_interval: float = 0.5):
        self.total = max(int(total), 1)
        self.label = label
        self.width = width
        self.min_interval = min_interval
        self.start = time.time()
        self._last = 0.0
        self.n = 0
        self._tty = getattr(sys.stderr, "isatty", lambda: False)()

    def update(self, n: int | None = None) -> None:
        self.n = (self.n + 1) if n is None else n
        now = time.time()
        if self.n < self.total and (now - self._last) < self.min_interval:
            return
        self._last = now
        self._render()

    def _render(self) -> None:
        frac = min(max(self.n / self.total, 0.0), 1.0)
        filled = round(frac * self.width)
        bar = FILL * filled + EMPTY * (self.width - filled)
        el = time.time() - self.start
        rate = self.n / el if el > 0 else 0.0
        rem_min = ((self.total - self.n) / rate / 60.0) if rate > 0 else 0.0
        done = self.n >= self.total
        line = (f"{self.label} {bar} {frac*100:5.1f}% | "
                f"{rem_min:4.1f} min restantes")
        try:
            if self._tty:
                sys.stderr.write("\r" + line + (" ✓\n" if done else ""))
            else:
                sys.stderr.write(line + (" ✓" if done else "") + "\n")
            sys.stderr.flush()
        except Exception:
            pass

    def close(self) -> None:
        self.n = self.total
        self._render()


def track(iterable, total: int | None = None, label: str = "", width: int = 10):
    """Wrap an iterable; yields items while rendering the bar."""
    if total is None:
        try:
            total = len(iterable)  # type: ignore[arg-type]
        except TypeError:
            total = 0
    bar = ProgressBar(total or 1, label=label, width=width)
    for item in iterable:
        yield item
        bar.update()
    bar.close()
