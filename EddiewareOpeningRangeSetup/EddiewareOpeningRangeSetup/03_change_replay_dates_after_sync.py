from pywinauto import Desktop
import time
import pyperclip

FROM_VALUE = "08/05/2026 09:30 a. m."
TO_VALUE   = "08/05/2026 10:35 a. m."

replay = Desktop(backend="uia").window(title_re=".*Replay.*")
replay.set_focus()
time.sleep(1)

edits = replay.descendants(control_type="Edit")

from_box = edits[0]
to_box = edits[2]

def paste_text(control, value):
    control.click_input()
    time.sleep(0.2)
    control.type_keys("^a")
    time.sleep(0.2)
    pyperclip.copy(value)
    time.sleep(0.2)
    control.type_keys("^v")
    time.sleep(0.5)

paste_text(from_box, FROM_VALUE)
paste_text(to_box, TO_VALUE)

print("Fechas cambiadas correctamente.")