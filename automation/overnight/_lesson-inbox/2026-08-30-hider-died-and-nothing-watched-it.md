# The popup fix ran for 18 days, died, and nothing on the box noticed for 20 more

**Date:** 2026-08-30 (J: "first priority is stopping all popups tho i am seeing cmd or
poewrshell popups that must not happen")
**Theme:** C7 monitor-of-monitors — the THIRD instance on this one subsystem

## Symptom

J reported console/PowerShell windows flashing while gaming. `audit_window_leak_compliance.py`
was RED on two unrelated flags; fixing those would have turned it GREEN while the flashing
continued. Task Scheduler was clean (~141 Gamma_* actions on the hidden wscript→pythonw
chain), `HKCU\Console\%%Startup` was already delegated, MCP launchers were shimmed.

## Root cause

Two hiders defend this box, and only one of them was being kept alive:

| hider | mechanism | latency | keepalive |
|---|---|---|---|
| `window-leak-detector.py` | 0.5s `EnumWindows` poll | hides up to 500ms LATE | yes |
| `window_leak_hook.py` | `SetWinEventHook(EVENT_OBJECT_SHOW)` | hides within a frame | **none** |

The hook died 2026-08-10. Verified 2026-08-30: `window-leak-hook.pid` named pid 9036 which
was not running, the last `window-leak-hook-*.log` was dated 08-10, and `Get-ScheduledTask
'Gamma*'` had **zero** actions referencing `window_leak_hook` — nothing had ever been
responsible for restarting it. For 20 days the only defence was the poller, which that day
logged 29 leaks, every one `mitigated: true`: hidden, but only after being visible.

The audit could not see this because checks 1–5 all ask *"could a popup be spawned?"* and
none asked *"is anything still awake to hide one?"*

## What made it the third instance

The detector itself went dark ~2 months (2026-05-23 → 2026-07-14) with nothing flagging it —
which is exactly why it got a keepalive. The hook then shipped 2026-07-23 for J's "STOP ALL
POPUPS NOW" **without one**, and repeated the failure verbatim. The fix for instance #2 was
never generalised into a rule, so instance #3 was written by the same hands that fixed #2.

## Fix

1. `Gamma_WindowLeakHookKeepalive` (5 min, 24/7), same flash-free chain as its sibling.
2. Audit check (6) `HIDER_NOT_RUNNING` / `HIDER_NO_KEEPALIVE` — a hider that is down, **or
   alive with no keepalive registered**, is RED. The second half is the class fix: a live
   hider with nothing to restart it is a future outage, flagged now rather than in 20 days.
3. Guards in `test_window_leak_hider_liveness_2026_08_30.py`, including RED-proofs.

## Two corrections this turned up

- **`CREATE_NO_WINDOW` does not prevent a console.** `run_ps1_hidden.py` carried a comment
  claiming it "guarantees Windows does not allocate a console/conhost". Measured A/B, same
  command, counting conhost children: `CREATE_NO_WINDOW` → 1 conhost, stdout captured;
  `DETACHED_PROCESS` → 0 conhost, stdout **empty** (even redirected to a real file handle).
  The flag suppresses the *window*, not the console — and on Win11 that console still goes
  through the default-terminal broker, which is what emits `WindowsTerminal -Embedding`.
  DETACHED_PROCESS was therefore **tested and rejected**: it would trade a visible flash for
  9 blinded production task logs.
- **A popup fix can break the thing it ships in.** Adding `creationflags=CREATE_NO_WINDOW` to
  `commit_msgfile.py` silently swallowed `commit_scoped.py`'s entire pre-commit safety-gate
  report — the commit was correctly BLOCKED and printed nothing, which reads exactly like a
  successful no-op. Gating on "does this process have a console" does not save it either
  (`GetConsoleWindow()` returns 0 under a piped shell that can still receive output). The
  working shape is keep the flag, stop relying on inheritance: capture and re-emit.

## Generalisation

The 2026-08-09 entry predicted "the next recurrence will be surface #6 — likely plugin- or
marketplace-supplied hooks." **That was correct** and is now closed: installed-plugin
`hooks/hooks.json` is scanned (resolved from `installed_plugins.json`'s own installPath, so
marketplace catalogs that never run are excluded). It immediately caught
`ralph-loop@claude-plugins-official`'s Stop hook running bare `bash`, and the 20:00Z process
capture showed `btsc`'s PostToolUse hook spawning `bash.exe` + `conhost.exe` on every Bash
tool call — i.e. the surface is not merely latent, it is the highest-frequency one on the box.

The next prediction, stated so it can be checked: **surface #7 is a spawn surface that is not
a file at all.** Every surface enumerated so far is something readable — `.ps1` text, `.py`
subprocess calls, MCP configs, Task Scheduler actions, settings hooks, plugin hooks. The one
this session could not close is the Windows *default-terminal delegation broker*, which turns
an ordinary console allocation into a painted window with no repo artifact anywhere in the
chain. A fix class that only ever audits files will keep missing it.
