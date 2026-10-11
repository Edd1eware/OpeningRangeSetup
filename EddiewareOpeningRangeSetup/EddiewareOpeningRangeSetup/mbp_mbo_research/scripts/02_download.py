"""Download Databento GLBX.MDP3 NQ data for the opening-range window, day by day.

One .dbn.zst file per (schema, session day): resumable, cheap to re-run, and
each file is independently loadable. Prints the metered cost BEFORE spending
anything; the actual download needs --yes.

Examples
--------
  python -u scripts/02_download.py --schema ohlcv-1s --start 2021-01-04 --end 2026-10-10
  python -u scripts/02_download.py --schema mbp-10 --start 2024-01-02 --end 2026-10-10 --yes
"""
from __future__ import annotations

import argparse
import csv
import gc
import sys
import time as _time
from datetime import date, datetime
from pathlib import Path

import databento as db

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (DATASET, LOGS, MANIFEST, STYPE_IN, SYMBOL, WINDOWS,
                    load_api_key, ny_window_utc, out_path, session_days)
from progress import track

MIN_BYTES = 200  # a DBN file with only metadata and no records


def release(path: Path, unlink: bool = False, tries: int = 8) -> None:
    """Wait for Windows to drop a lingering handle on `path`, then optionally delete.

    The Databento SDK memory-maps what it writes, so a rename or unlink right
    after a download can still hit WinError 32 for a few milliseconds.
    """
    for i in range(tries):
        try:
            if unlink:
                path.unlink(missing_ok=True)
            elif path.exists():
                with path.open("rb"):
                    pass
            return
        except PermissionError:
            gc.collect()
            _time.sleep(0.25 * (i + 1))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--schema", required=True, choices=sorted(WINDOWS))
    p.add_argument("--start", required=True, help="first session day, YYYY-MM-DD")
    p.add_argument("--end", required=True, help="last session day, YYYY-MM-DD")
    p.add_argument("--yes", action="store_true", help="actually download")
    p.add_argument("--cost-samples", type=int, default=5)
    p.add_argument("--include-est", action="store_true",
                   help="also take EST days (default: EDT only)")
    return p.parse_args()


def iso(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def estimate(client: db.Historical, schema: str, days: list[date], n: int) -> tuple[float, float]:
    """Mean USD and MB per day, measured on `n` evenly spaced sample days."""
    t0, t1 = WINDOWS[schema]
    step = max(len(days) // max(n, 1), 1)
    picks = days[::step][:n] or days[:1]
    usd = mb = 0.0
    for d in picks:
        start, end = ny_window_utc(d, t0, t1)
        kw = dict(dataset=DATASET, symbols=SYMBOL, stype_in=STYPE_IN,
                  schema=schema, start=start, end=end)
        usd += client.metadata.get_cost(**kw)
        mb += client.metadata.get_billable_size(**kw) / 1e6
    return usd / len(picks), mb / len(picks)


def log_row(row: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    new = not MANIFEST.exists()
    with MANIFEST.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def main() -> int:
    a = parse_args()
    days = session_days(iso(a.start), iso(a.end), dst_only=not a.include_est)
    todo = [d for d in days
            if not (out_path(a.schema, d).exists()
                    and out_path(a.schema, d).stat().st_size > MIN_BYTES)]
    t0, t1 = WINDOWS[a.schema]

    print(f"schema={a.schema}  window={t0}-{t1} ET  {'EDT only' if not a.include_est else 'EDT+EST'}  sessions={len(days)}  "
          f"missing={len(todo)}  symbol={SYMBOL}")
    if not todo:
        print("nothing to download.")
        return 0

    load_api_key()
    client = db.Historical()
    try:
        usd_day, mb_day = estimate(client, a.schema, todo, a.cost_samples)
    except Exception as exc:
        msg = str(exc)
        if "auth_account_locked" in msg:
            print("\nDATABENTO ACCOUNT LOCKED (403 auth_account_locked)."
                  "\nNothing can be downloaded until it is unlocked at"
                  "\n  https://databento.com/portal  (login -> Security / Billing)."
                  "\nThe key is well-formed, so this is account-side.")
            return 2
        if "auth" in msg or "403" in msg:
            print(f"\nAUTH PROBLEM: {msg}\nCheck credentials/databento.env")
            return 2
        raise
    print(f"per session: ~{mb_day:,.1f} MB  ~${usd_day:,.4f}")
    print(f"TOTAL for {len(todo)} sessions: ~{mb_day*len(todo)/1000:,.2f} GB  "
          f"~${usd_day*len(todo):,.2f}")
    if not a.yes:
        print("\ndry run. re-run with --yes to download.")
        return 0

    empty = failed = 0
    for d in track(todo, label=f"{a.schema} download"):
        start, end = ny_window_utc(d, t0, t1)
        dest = out_path(a.schema, d)
        tmp = dest.with_suffix(".part")
        t_begin = _time.time()
        try:
            store = client.timeseries.get_range(
                dataset=DATASET, symbols=SYMBOL, stype_in=STYPE_IN,
                schema=a.schema, start=start, end=end, path=tmp)
            size = tmp.stat().st_size
            # DBNStore keeps the file mapped; on Windows the handle must be
            # released before the rename or we get WinError 32.
            del store
            gc.collect()
            if size <= MIN_BYTES:
                release(tmp, unlink=True)
                empty += 1
                status = "empty"
            else:
                release(tmp)
                tmp.replace(dest)
                status = "ok"
        except Exception as exc:                      # keep the loop alive
            gc.collect()
            release(tmp, unlink=True)
            failed += 1
            status = f"error: {type(exc).__name__}: {exc}"[:200]
            size = 0
        log_row({"ts": datetime.now().isoformat(timespec="seconds"),
                 "schema": a.schema, "day": d.isoformat(), "status": status,
                 "bytes": size, "secs": round(_time.time() - t_begin, 2)})

    print(f"\ndone. empty={empty} failed={failed} manifest={MANIFEST}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
