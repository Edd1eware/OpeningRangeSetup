from pywinauto import Desktop

replay = Desktop(backend="uia").window(title_re=".*Replay.*")
replay.set_focus()

print("\nEDIT CONTROLS:\n")
for e in replay.descendants(control_type="Edit"):
    print("TEXT:", e.window_text())
    print("RECT:", e.rectangle())
    print("AUTO_ID:", e.element_info.automation_id)
    print("CLASS:", e.element_info.class_name)
    print("-" * 50)

print("\nBUTTONS:\n")
for b in replay.descendants(control_type="Button"):
    print("TEXT:", b.window_text())
    print("RECT:", b.rectangle())
    print("AUTO_ID:", b.element_info.automation_id)
    print("CLASS:", b.element_info.class_name)
    print("-" * 50)