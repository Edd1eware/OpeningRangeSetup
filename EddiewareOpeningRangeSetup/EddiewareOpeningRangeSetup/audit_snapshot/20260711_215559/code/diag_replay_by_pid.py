"""Diagnostico v2: conecta a ATAS por PROCESO (evita enumerar todo el desktop UIA,
que se cuelga cuando hay apps pesadas abiertas: Chrome/Edge/webview2/Electron).

Auto-detecta el proceso OFT.Platform cuya ventana empieza con 'Replay'.
Corre:  python -u diag_replay_by_pid.py
"""
import time
import pywinauto
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


def find_atas_replay_pid():
    # win32 enumeration (rapida, no UIA) para hallar el PID con ventana 'Replay'.
    import win32gui
    import win32process

    found = {}

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if title.lower().startswith("replay"):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            found[pid] = title

    win32gui.EnumWindows(cb, None)
    return found


print("0) Buscando PID de la ventana Replay (win32, sin UIA)...", flush=True)
pids = find_atas_replay_pid()
print(f"   encontrados: {pids}", flush=True)
if not pids:
    print("No hay ventana 'Replay' visible. Abre el panel Replay en ATAS.")
    raise SystemExit(1)

atas_pid = next(iter(pids))
print(f"   usando PID {atas_pid}", flush=True)

print("1) Conectando a ATAS por proceso...", flush=True)
app = timed("Application.connect(process=PID)", lambda: Application(backend="uia").connect(process=atas_pid))
if app is None:
    raise SystemExit(1)

wins = timed("app.windows()", lambda: app.windows())
print(f"   ventanas ATAS: {len(wins) if wins else 0}", flush=True)

replay = None
for i, w in enumerate(wins or []):
    try:
        title = w.window_text()
        print(f"   win[{i}] {title!r}", flush=True)
        if title.lower().startswith("replay"):
            replay = w
    except Exception as exc:
        print(f"   win[{i}] err {exc}", flush=True)

if replay is not None:
    edits = timed("replay.descendants(Edit)", lambda: replay.descendants(control_type="Edit"))
    print(f"   edits={len(edits) if edits else 0}", flush=True)
    btns = timed("replay.descendants(Button)", lambda: replay.descendants(control_type="Button"))
    print(f"   buttons={len(btns) if btns else 0}", flush=True)

print("\nListo. Si esto fue rapido, el fix es conectar por proceso, no por Desktop.windows().", flush=True)
