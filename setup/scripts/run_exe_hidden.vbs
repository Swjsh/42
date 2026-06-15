' run_exe_hidden.vbs - launch any executable fully hidden, bypassing Windows Terminal default
' Usage: wscript //nologo run_exe_hidden.vbs <exe-path> [args...]
' windowStyle=0 + WScript.Shell.Run bypasses the Windows 11 default-terminal handler.
Set args = WScript.Arguments
If args.Count = 0 Then WScript.Quit 1
Set shell = CreateObject("WScript.Shell")
cmd = """" & args(0) & """"
For i = 1 To args.Count - 1
    cmd = cmd & " """ & args(i) & """"
Next
shell.Run cmd, 0, False
