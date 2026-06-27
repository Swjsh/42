' LAUNCH-GAMMA-FACE.vbs
' Double-click to open the Gamma face (the installable app) at http://localhost:4500/
' Starts cockpit/server.js hidden (no console flash) if :4500 isn't already serving,
' then opens the default browser to the face.
' Flash-free via wscript (lesson: project_mcp_window_leak_fix). Does NOT touch any
' existing LAUNCH-*.vbs.

Option Explicit

Dim oShell, oFSO, sRepo, sNode, sScript
Dim oHttp, i

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
    MsgBox "node.exe not found. Please install Node.js.", vbCritical, "Gamma"
    WScript.Quit 1
End If

' Already serving on 4500? Just open the browser to the face.
On Error Resume Next
Set oHttp = CreateObject("WinHttp.WinHttpRequest.5.1")
oHttp.Open "GET", "http://localhost:4500/api/tiles", False
oHttp.SetTimeouts 500, 500, 500, 500
oHttp.Send
If Err.Number = 0 And oHttp.Status = 200 Then
    oShell.Run "explorer http://localhost:4500/", 1, False
    WScript.Quit 0
End If
On Error GoTo 0

' Start the server hidden (no window flash)
oShell.Run Chr(34) & sNode & Chr(34) & " " & Chr(34) & sScript & Chr(34), 0, False

' Wait up to ~4.5s for it to be ready
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

' Open the default browser to the face
oShell.Run "explorer http://localhost:4500/", 1, False
