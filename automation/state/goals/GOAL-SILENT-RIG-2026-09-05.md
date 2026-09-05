# GOAL: SILENT-RIG-2026-09-05

> Opened by Fable 2026-09-05 13:44 ET on J's order: "this is a recurring thing it has to stop. everything must be
> silent, and it needs to be optimized, i can't have my pc bogged down." Evidence today: the window-leak
> hook hid 730 terminal windows (2,553 on 09-02) -- every one a flash on J's screen while he was in a
> fullscreen game (quiet-presence.json: r5apex_dx12.exe at 12:17 ET). Root cause of today's 2-minute
> flashes: Gamma_TickersLane runs its worker through `backtest\.venv\Scripts\pythonw.exe`, a launcher
> stub whose base executable is the CONSOLE python.exe (proven: GetConsoleWindow() != 0 under the stub, 0
> under the system pythonw); 23 registered tasks use that stub. Second source: the conductor's claude.exe
> + MCP children (node/bun) at 12:00 ET. Load: ~300 process launches per HOUR overnight on a Saturday,
> 500/hour in the morning (run-ps1/run-cmd hidden logs), plus 4-worker grinders 24/7.
> STATE AT OPEN: 158 Gamma tasks disabled by hand (automation/state/manual-hold-2026-09-05.json), quiet-
> mode enforcer disabled, 7 daemons killed; only the two window hiders run. NOTHING is re-enabled by a
> worker -- Fable re-enables after review, and J has the final say on the tickers lane before Tuesday.

## DONE-WHEN
(S1) Every task action that references `\.venv\Scripts\python.exe` or `pythonw.exe` (23 today, list in
automation/state/task-triggers-snapshot-2026-09-05.json) is re-registered to the system pythonw
(`C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe`) with
`--env PYTHONPATH=C:\Users\jackw\Desktop\42\backtest\.venv\Lib\site-packages` (and VIRTUAL_ENV where the
script reads it) through run_cmd_hidden.py -- the pattern the ~150 silent tasks already use; the tasks stay
DISABLED (Set-ScheduledTask edits the action only); every install-*.ps1 / registration script that built
those actions is updated to the same pattern so a re-install cannot bring the stub back. Proof: a fresh
scheduler export shows 0 actions matching the stub.
(S2) Guard: setup/scripts/audit_window_leak_compliance.py gains flag TASK_VENV_INTERPRETER (live registry
+ install scripts), and a pytest guard reads the live registry and fails on any match; RED-proofed
against a fixture action string.
(S3) Leak attribution: setup/scripts/window_leak_hook.py records, for every hide, the console-subsystem
processes created in the previous 3 s (WMI Win32_Process CreationDate, name, parent name, command line)
next to the HID line, and once per day when hides > 0 writes ONE Known-broken line
`WINDOW-LEAK: N windows hidden, top sources: <cmdline x count>` through the shared upsert helper. A leak
can never again be silent for days. Guard test with a fake hide event.
(S4) Conductor: explain with evidence why claude.exe and its MCP children opened windows at 12:00 ET
despite Invoke-Claude's CreateNoWindow=true (setup/scripts/_shared.ps1 ~line 155-175): read the hook log
at 10:00:0x local and the process tree captured in this session (claude.exe pid 4088 with its own
conhost, node tradingview launcher pid 28088, bun discord pid 17564); if the MCP servers are the leak,
wrap node/bun launches in the existing mcp_stdio_hidden.py shim (audit_window_leak_compliance already
knows the pattern) or set windowsHide via the launcher; no conductor fire to test -- the next enabled
fire's hook log is the verification and must be quoted then.
(L1) Load plan written to `markdown/infra/SILENT-RIG-2026-09-05.md` from the snapshot: for each task
with interval <= PT5M, the proposed trigger (SPY-engine tasks: Mon-Fri 09:20-16:10 ET only; futures
lane: its CME session only; keepalives: 15 min off-hours; CryptoTwin: unchanged 1-min by doctrine, say
so; grinders: presence-aware + BELOW_NORMAL priority + 2 workers), expected launches/hour before vs after
(today's logs = before), and an apply script `setup/scripts/apply_silent_rig_triggers.ps1` with -WhatIf
that edits triggers/settings ONLY (never enables). Task priority set to 7 (below normal) on every
Gamma_* task in the same script. Fable reviews the table before it is applied.
(L2) Grinders (kitchen_daemon.py GRINDER_MAX_WORKERS, crypto live_grinder keepalive): yield when
quiet-presence.json shows a fullscreen app in the last 10 min or the box is in use (last input < 5 min via
GetLastInputInfo); BELOW_NORMAL_PRIORITY_CLASS on the spawn; workers 4 -> 2; guard tests.
(L3) A launches-per-hour instrument: setup/scripts/launch_rate.py reads the two hidden-launcher logs and
writes automation/state/launch-rate.json {per_hour, top_scripts}; a Known-broken line when any
market-closed hour exceeds 60 launches. Registered later by Fable, not by the worker.

## OPERATING RULES
- Workers never enable a scheduled task, never Start-ScheduledTask, never launch a daemon, never spawn
  powershell.exe/cmd.exe/tasklist/schtasks from Bash (use the PowerShell tool), never commit; the
  orchestrator commits and re-enables.
- CONFIG FREEZE: no trading-path edits. Trigger windows for engine tasks are operational, not trading-
  path, but every engine task's window must still cover 09:25-16:05 ET Mon-Fri with the same cadence.
- Every stamp from `python setup/scripts/et_clock.py`; write Python files with the Write tool.
- Verify, don't claim: quote the scheduler export / test output for every DONE item.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] S1 (WIP 2026-09-05 13:44 ET, Fable session a16e320c worker S) -- 23 stub tasks re-registered to system pythonw + PYTHONPATH (still disabled); installers updated; export shows 0.
- [~] S2 (WIP 2026-09-05 13:44 ET, worker S) -- audit flag + pytest guard, RED-proofed.
- [~] S3 (WIP 2026-09-05 13:44 ET, worker S) -- hook attribution + daily Known-broken line + guard.
- [~] S4 (WIP 2026-09-05 13:44 ET, worker S) -- conductor/MCP window explanation + fix.
- [~] L1 (WIP 2026-09-05 13:44 ET, worker L) -- load plan + apply script with -WhatIf (not applied).
- [~] L2 (WIP 2026-09-05 13:44 ET, worker L) -- presence-aware, below-normal, 2-worker grinders + guards.
- [~] L3 (WIP 2026-09-05 13:44 ET, worker L) -- launch_rate.py instrument.
- [ ] R1 -- Fable: review L1 table, apply triggers, re-enable tasks in stages watching the hook log; J decides the tickers lane.

## J-DECISIONS
- Re-enable Gamma_TickersLane before Tuesday 07:35 MT? (It is the only lane that fires every 2 min all session.)

## PROGRESS LOG
- 2026-09-05 13:44 ET -- opened by Fable after J's stop order; 158 tasks disabled, 7 daemons killed, hiders left running.
## HONEST STATE
Open. Everything except the two window hiders is OFF until Fable re-enables after review.
