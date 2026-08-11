"""Diagnostico v3: envuelve la ventana Replay por HANDLE (win32), sin ningun
Desktop.windows()/app.windows() que enumere todo el desktop UIA (eso cuelga con
apps pesadas abiertas). Corre:  python -u diag_replay_by_handle.py
"""
import time
import win32gui
from pywinauto import Application


def timed(label, fn):
    t = time.time()
    try:
        result = fn()
        print(f"[{time.time() - t:6.1f}s] OK  {label}", flush=True)
        return result
    except Exception as exc:
        print(f"[{time.time() - t:6.1f}s] ERR {label}: {exc}", flush=True)
        return None


hwnds = []


def _cb(hwnd, _):
    if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd).lower().startswith("replay"):
        hwnds.append(hwnd)


print("0) HWND de la ventana Replay (win32, sin UIA)...", flush=True)
win32gui.EnumWindows(_cb, None)
print("   hwnds:", [(h, win32gui.GetWindowText(h)) for h in hwnds], flush=True)
if not hwnds:
    print("No hay ventana 'Replay' visible.")
    raise SystemExit(1)

hwnd = hwnds[0]

app = timed("Application.connect(handle=HWND)", lambda: Application(backend="uia").connect(handle=hwnd))
if app is None:
    raise SystemExit(1)

replay = timed("app.window(handle=HWND)", lambda: app.window(handle=hwnd))
if replay is None:
    raise SystemExit(1)

timed("wrapper_object()", replay.wrapper_object)

edits = timed("descendants(control_type=Edit)", lambda: replay.descendants(control_type="Edit"))
print(f"   edits={len(edits) if edits else 0}", flush=True)

buttons = timed("descendants(control_type=Button)", lambda: replay.descendants(control_type="Button"))
print(f"   buttons={len(buttons) if buttons else 0}", flush=True)

print("\nListo. Si esto fue rapido, el fix del runner es envolver por HANDLE.", flush=True)
