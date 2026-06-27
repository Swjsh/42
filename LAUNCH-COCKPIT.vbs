' LAUNCH-COCKPIT.vbs
' Double-click to start Gamma Cockpit v1 on http://localhost:4500
' Uses wscript to avoid any PowerShell/cmd window flash (lesson: project_mcp_window_leak_fix)

Option Explicit

Dim oShell, oFSO, sRepo, sNode, sScript, sPidFile
Dim oExec, sUrl, i

Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")

sRepo   = oFSO.GetParentFolderName(WScript.ScriptFullName)
sScript = sRepo & "\cockpit\server.js"

' Resolve node.exe
sNode = "C:\Program Files\nodejs\node.exe"
If Not oFSO.FileExists(sNode) Then
    sNode = oShell.ExpandEnvironmentStrings("%APPDATA%\..\Local\Programs\nodejs\node.exe")
End If
If Not oFSO.FileExists(sNode) Then
    MsgBox "node.exe not found. Please install Node.js.", vbCritical, "Gamma Cockpit"
    WScript.Quit 1
End If

' Check if already running on 4500
Dim oHttp
On Error Resume Next
Set oHttp = CreateObject("WinHttp.WinHttpRequest.5.1")
oHttp.Open "GET", "http://localhost:4500/api/tiles", False
oHttp.SetTimeouts 500, 500, 500, 500
oHttp.Send
If Err.Number = 0 And oHttp.Status = 200 Then
    ' Already up — just open the browser
    oShell.Run "explorer http://localhost:4500", 1, False
    WScript.Quit 0
End If
On Error GoTo 0

' Start the server hidden (no window flash)
Dim oSvr
Set oSvr = CreateObject("WScript.Shell")
oSvr.Run Chr(34) & sNode & Chr(34) & " " & Chr(34) & sScript & Chr(34), 0, False

' Wait up to 4s for it to be ready
WScript.Sleep 1500
For i = 1 To 6
    On Error Resume Next
    Set oHttp = CreateObject("WinHttp.WinHttpRequest.5.1")
    oHttp.Open "GET", "http://localhost:4500/", False
    oHttp.SetTimeouts 500, 500, 500, 500
    oHttp.Send
    If Err.Number = 0 And oHttp.Status = 200 Then
        Exit For
    End If
    On Error GoTo 0
    WScript.Sleep 500
Next

' Open browser
oShell.Run "explorer http://localhost:4500", 1, False
