"""Diagnostico: aisla y cronometra la interaccion pywinauto con la ventana Replay
de ATAS para ver DONDE se cuelga el runner. Corre con ATAS abierto y el panel
Replay visible:  python -u diag_replay_window.py
"""
import time
from pywinauto import Desktop


def timed(label, fn):
    t = time.time()
    try:
        result = fn()
        print(f"[{time.time() - t:6.1f}s] OK  {label}", flush=True)
        return result
    except Exception as exc:
        print(f"[{time.time() - t:6.1f}s] ERR {label}: {exc}", flush=True)
        return None


print("1) Enumerando ventanas Replay (UIA)...", flush=True)
wins = timed(
    "Desktop.windows(Replay)",
    lambda: Desktop(backend="uia").windows(title_re=".*Replay.*", visible_only=True),
)

if not wins:
    print("No hay ventanas Replay visibles. Abre el panel Replay en ATAS y reintenta.")
    raise SystemExit(1)

print(f"   ventanas encontradas: {len(wins)}", flush=True)
for i, w in enumerate(wins):
    try:
        print(f"   win[{i}] text={w.window_text()!r}", flush=True)
    except Exception as exc:
        print(f"   win[{i}] err {exc}", flush=True)

w = wins[0]
timed("set_focus", w.set_focus)

edits = timed("descendants(control_type=Edit)", lambda: w.descendants(control_type="Edit"))
print(f"   edits={len(edits) if edits else 0}", flush=True)

buttons = timed("descendants(control_type=Button)", lambda: w.descendants(control_type="Button"))
print(f"   buttons={len(buttons) if buttons else 0}", flush=True)

print("\nListo. El paso con mas segundos es el cuello de botella / cuelgue.", flush=True)
