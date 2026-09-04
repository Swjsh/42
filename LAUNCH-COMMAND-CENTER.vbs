' LAUNCH-COMMAND-CENTER.vbs
' Double-click: open the Gamma Command Center (Next.js dashboard, /cockpit route).
' Data comes from gamma-companion/public/payload.json, which setup/scripts/gamma_home.py
' rewrites every 30 min (Gamma_Home). The server on :3000 is kept alive by
' Gamma_DashboardKeepalive; if it is down we kick that task and wait, hidden (no window flash).

Option Explicit

Dim oShell, oHttp, sUrl, i, bUp

Set oShell = CreateObject("WScript.Shell")
sUrl = "http://localhost:3000/cockpit"

Function PageUp()
    On Error Resume Next
    Set oHttp = CreateObject("WinHttp.WinHttpRequest.5.1")
    oHttp.Open "GET", "http://localhost:3000/api/cockpit", False
    oHttp.SetTimeouts 800, 800, 800, 1500
    oHttp.Send
    PageUp = (Err.Number = 0 And oHttp.Status = 200)
    On Error GoTo 0
End Function

bUp = PageUp()
If Not bUp Then
    oShell.Run "schtasks /Run /TN Gamma_DashboardKeepalive", 0, True
    For i = 1 To 30
        WScript.Sleep 1000
        If PageUp() Then bUp = True : Exit For
    Next
End If

If bUp Then
    oShell.Run "explorer """ & sUrl & """", 1, False
Else
    MsgBox "Command center did not come up on :3000 within 30 s. Run 'npm run build' in dashboard/ then retry.", vbExclamation, "Gamma Command Center"
End If
