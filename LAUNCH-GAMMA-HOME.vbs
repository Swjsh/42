' LAUNCH-GAMMA-HOME.vbs
' Double-click: regenerate the Gamma command center, then open it.
' No server, no port, no keepalive -- one self-contained HTML file, so it can never be "down".
' Uses wscript + hidden run to avoid any PowerShell/cmd window flash
' (lesson: project_mcp_window_leak_fix -- a bare powershell/cmd flashes OpenConsole on Win11).

Option Explicit

Dim oShell, oFSO, sRepo, sPy, sScript, sPage, rc

Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")

sRepo   = oFSO.GetParentFolderName(WScript.ScriptFullName)
sScript = sRepo & "\setup\scripts\gamma_home.py"
sPage   = sRepo & "\analysis\home\index.html"

' Prefer the backtest venv (reaper-exempt, has the deps); fall back to system python.
sPy = sRepo & "\backtest\.venv\Scripts\pythonw.exe"
If Not oFSO.FileExists(sPy) Then
    sPy = oShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe")
End If
If Not oFSO.FileExists(sPy) Then sPy = "pythonw.exe"

' 0 = hidden window, True = wait, so the page is FRESH before the browser opens it.
On Error Resume Next
rc = oShell.Run("""" & sPy & """ """ & sScript & """", 0, True)
On Error Goto 0

' Open whatever we have. If regeneration failed, the previous page still opens and its
' own source-age badges will show it is stale -- fail open, never a blank screen.
If oFSO.FileExists(sPage) Then
    oShell.Run """" & sPage & """", 1, False
Else
    MsgBox "Gamma home page not found:" & vbCrLf & sPage & vbCrLf & vbCrLf & _
           "Run: python setup\scripts\gamma_home.py", 48, "Gamma"
End If
