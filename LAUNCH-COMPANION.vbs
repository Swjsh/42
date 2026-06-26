' Gamma companion launcher -- starts the local server with NO console window
' and opens it in your default browser. Double-click to run.
' (The always-on-top desktop-pet window is a later step; this is the v0 view.)

Set sh = CreateObject("WScript.Shell")
root = "C:\Users\jackw\Desktop\42"
sh.CurrentDirectory = root & "\gamma-companion"

' 0 = hidden window, so no black cmd box flashes on screen
sh.Run "node server.js", 0, False

' give the server a moment, then open the companion
WScript.Sleep 1400
sh.Run "http://localhost:4317", 1, False
