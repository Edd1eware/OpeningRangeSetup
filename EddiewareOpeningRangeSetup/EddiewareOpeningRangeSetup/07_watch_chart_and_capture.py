"""Wait until a chart is open in ATAS, then run the 20-session capture.

Screenshotting ATAS while the workspace shows only the Accounts table produces a
picture of a table, which is worse than no picture: it looks like a deliverable
and contains nothing. So the capture does not start on a promise that the chart
is ready, it starts when the chart is actually there.

Detection is by elimination. ATAS exposes its dockable panels as UIA TabItems and
the ones that exist with no chart loaded are a fixed, known set; a chart adds a
tab named after the instrument. Anything outside the known set is a chart.

This exists because the alternative is asking the operator again and checking by
hand, and the operator has already said twice that the chart was ready when it
was not — not out of carelessness, but because opening the Replay window and
opening a chart are two different actions and only one of them is obvious.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "context_divergencia" / "analysis"))
import tg                                                        # noqa: E402

# every panel ATAS shows with no chart loaded; anything else is a chart
BASE_TABS = {
    "Accounts", "Home", "Market news", "Orders", "Positions", "Tables",
    "Trades", "Trading Activity", "Trading Journal", "Trading strategies",
    "Widgets", "Ribbon Tabs", "PanelHost", "Alerts", "Logs",
}
POLL_S = 20
LIMIT = 20


def chart_tabs() -> list[str]:
    from pywinauto import Desktop
    wins = [w for w in Desktop(backend="uia").windows()
            if "ATAS" in (w.window_text() or "")]
    if not wins:
        return []
    found = []
    for d in wins[0].descendants(control_type="TabItem"):
        try:
            name = (d.window_text() or "").strip()
        except Exception:
            continue
        if name and name not in BASE_TABS:
            found.append(name)
    return found


def main() -> int:
    print("esperando a que abras un chart en ATAS...")
    tg.msg("<b>Vigia activo</b>\nEspero a que abras un chart en ATAS. "
           "En cuanto lo detecte arranco solo las 20 capturas y te aviso.")
    waited = 0
    while True:
        try:
            tabs = chart_tabs()
        except Exception as exc:
            print(f"  aviso: no pude leer ATAS ({exc})")
            tabs = []
        if tabs:
            print(f"\nchart detectado: {tabs}")
            tg.msg(f"<b>Chart detectado</b>: {', '.join(tabs)}\n"
                   f"Arranco las {LIMIT} capturas del replay.")
            break
        waited += POLL_S
        print(f"\r  sin chart todavia  ({waited//60} min esperando)",
              end="", flush=True)
        time.sleep(POLL_S)

    return subprocess.run(
        [sys.executable, "-u", str(BASE / "06_run_replay_screenshots_divergencia.py"),
         "--run", "--limit", str(LIMIT)],
        cwd=str(BASE),
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
