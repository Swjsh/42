' run_exe_hidden_exec.vbs - launch any executable fully hidden via WshShell.Exec (CreateProcess).
' Unlike run_exe_hidden.vbs (which uses Shell.Run/ShellExecute and CAN route through the
' Windows 11 DefaultTerminal handler for some targets -- confirmed live 2026-07-14 against
' backtest\.venv\Scripts\pythonw.exe direct-launches: ShellExecuteEx decides console/terminal
' hosting AT PROCESS-CREATION TIME, before the child ever runs a line of its own code, so no
' script-level fix (stdio redirection, etc.) can touch it -- same class of leak
' run_hidden_exec.vbs was built to fix for powershell.exe on 2026-05-17), WshShell.Exec uses
' CreateProcess directly and inherits the parent wscript's no-console handles -- the child
' never gets WT-embedded.
'
' Usage: wscript //nologo run_exe_hidden_exec.vbs <exe-path> [args...]
' BLOCKING by design (matches run_hidden_exec.vbs): WshShell.Exec redirects the child's
' stdio through PIPES owned by THIS wscript process. If wscript exited immediately (Shell.Run's
' fire-and-forget wait=False semantics), those pipes would close under the child while it's
' still running, and any stdout/stderr write after that point breaks. All current callers of
' this script wrap SHORT-LIVED, single-shot scripts (compute once, write state, exit -- the
' 24/7 cadence lives in the Task Scheduler repetition, not a long-running child process), so
' blocking wscript until the child exits is safe and correct here, and additionally lets Task
' Scheduler see the child's REAL exit code (Shell.Run's fire-and-forget always reports 0).
Set args = WScript.Arguments
If args.Count = 0 Then WScript.Quit 1
Set shell = CreateObject("WScript.Shell")
cmd = """" & args(0) & """"
For i = 1 To args.Count - 1
    cmd = cmd & " """ & args(i) & """"
Next
Set exec = shell.Exec(cmd)
Do While exec.Status = 0  ' WshRunning = 0
    WScript.Sleep 100
Loop
WScript.Quit exec.ExitCode
