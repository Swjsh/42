Set args = WScript.Arguments
If args.Count = 0 Then WScript.Quit 1
Set shell = CreateObject("WScript.Shell")
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File """ & args(0) & """"
For i = 1 To args.Count - 1
    cmd = cmd & " " & args(i)
Next
shell.Run cmd, 0, False
