from pywinauto import Desktop

desktop = Desktop(backend="uia")

print("\nVENTANAS DETECTADAS:\n")

for i, w in enumerate(desktop.windows()):
    title = w.window_text()
    if title.strip():
        print(i, "|", title)

print("\nBuscando ventana Replay...\n")

replay = desktop.window(title_re=".*Replay.*")
replay.set_focus()

print("Replay encontrado:")
print(replay.window_text())

print("\nControles de Replay:\n")
replay.print_control_identifiers()