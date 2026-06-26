' Gamma desktop app (Electron) -- double-click to launch. No browser, no tabs,
' own window + taskbar entry. The microphone is auto-granted so voice just works.

Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\jackw\Desktop\42\gamma-companion"
' window style 0 = hidden console; the Electron GUI window appears on its own.
sh.Run "cmd /c npx electron .", 0, False
