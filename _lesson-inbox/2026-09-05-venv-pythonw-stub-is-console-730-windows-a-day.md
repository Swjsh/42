# Lesson inbox: the venv pythonw stub is a console interpreter -- 730 hidden windows a day

**Date:** 2026-09-05 (Saturday), J: "STOP THE POPUPS IMMEDIATELY" / "everything must be silent ... i cant have my pc bogged down"

**Symptom:** Windows Terminal windows flashing on J's screen every 2 minutes (odd minutes, HH:MM:01-03), 3-5 at a time, plus a pythonw.exe dialog. J was in a fullscreen game. The window-leak hook log (`automation/state/logs/window-leak-hook-2026-09-04.log`) shows 730 HID lines that day and 2,553 on 2026-09-02 -- the hider had been hiding hundreds of windows a day and no surface said so.

**Root cause (one sentence):** `backtest\.venv\Scripts\pythonw.exe` is a Python 3.13 venv launcher stub whose base executable is the CONSOLE `python.exe` (pyvenv.cfg `executable = ...\python.exe`), so any task that runs a worker through it from a windowless parent allocates a new console -- proven by `ctypes.windll.kernel32.GetConsoleWindow()` returning a handle under the stub and 0 under the system pythonw. 23 registered tasks used the stub; `Gamma_TickersLane` (every 2 min, all session) made it visible.

**Confounders that cost time:** (1) my own `powershell -Command` / `tasklist` calls from the Bash tool were blamed first; (2) `CREATE_NO_WINDOW` on the stub does not reach the stub's child; (3) the hook's `img=windowsterminal.exe` names the host, never the client, so the leak was un-attributable from the log; (4) copying the real pythonw over the stub "fixed" the probe but a task fired under it and threw a dialog -- never test a window fix by firing a task on J's desktop.

**Fix:** re-register every stub task to the system pythonw + `PYTHONPATH` through run_cmd_hidden.py (the pattern ~150 silent tasks already use); audit flag TASK_VENV_INTERPRETER + pytest guard on the live registry and the installers; window_leak_hook attributes each hide to processes created in the prior 3 s and upserts ONE Known-broken line per day when hides > 0; launch_rate.py flags any market-closed hour over 60 launches; SPY engine tasks narrowed to Mon-Fri market window; grinders presence-aware, below-normal, 2 workers. Goal: GOAL-SILENT-RIG-2026-09-05.

**Theme rows:** C8 (headless Windows spawn = system pythonw), C7 (a hider that hides 700 windows a day and says nothing is silent failure), C34/C35 (built != shipped: the guard must read the LIVE registry).

**Afternoon addenda (same day):**
- The task-ACTION sweep was not enough: 12 launcher scripts (run-discord-responder.ps1, run-autoapply.ps1, run-tv-watchdog.ps1, ensure-discord-bridge-alive.ps1, ...) pick the stub INSIDE the script (`$venvPythonW = Join-Path ... .venv\Scripts\pythonw.exe`), so the 16:15 / 16:30 ET fires flashed 12 more windows after the actions were clean. Guard must scan every launcher, not only task actions and installers.
- quiet_mode's restore re-enabled two tasks a human had turned off on purpose (CryptoTwin, TickersLane) -> `quiet-mode-never-restore.json`.
- A window-leak hook that hides windows and says nothing is a silent failure (730/day for days): the hook now writes a daily Known-broken line and attributes each hide via an event-driven process-creation tracer (proc_trace).
- A Bash-tool heredoc python from an early worker hung for 8.4 CPU-hours (pid 22036, `python3.exe -`), unreaped because the >5-min reaper does not match the WindowsApps python3 image. Workers: never leave a heredoc waiting on stdin; orchestrator: `Get-Process python*` CPU column is a cheap daily check.
