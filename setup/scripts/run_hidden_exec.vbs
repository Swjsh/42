' run_hidden_exec.vbs - launch a PowerShell .ps1 fully hidden via WshShell.Exec (CreateProcess).
' Unlike run_hidden.vbs (which uses Shell.Run/ShellExecute and can route through Windows Terminal
' DefaultTerminal handler), WshShell.Exec uses CreateProcess directly and inherits the parent
' wscript's no-console handles -- the child PowerShell never gets WT-embedded.
'
' Why this exists: OP-27 L41 + 2026-05-17 evening foot-gun detector confirmed that even
' shell.Run "powershell.exe ...", 0 leaks WindowsTerminal -Embedding flashes on Win11 11
' default-terminal config. WshExec is the CreateProcess path and bypasses that.
'
' Usage: wscript //nologo run_hidden_exec.vbs <ps1-path> [args...]
Set args = WScript.Arguments
If args.Count = 0 Then WScript.Quit 1
Set shell = CreateObject("WScript.Shell")
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File """ & args(0) & """"
For i = 1 To args.Count - 1
    cmd = cmd & " " & args(i)
Next
Set exec = shell.Exec(cmd)
' Wait for child to finish so the task scheduler sees the correct exit code.
Do While exec.Status = 0  ' WshRunning = 0
    WScript.Sleep 100
Loop
WScript.Quit exec.ExitCode
