# The popup audit never looked at the highest-frequency popup surface (Claude Code hooks)

**Date:** 2026-08-09 (J: "too many cmd and windows popups")
**Theme:** C7/L292 sibling — a monitor's coverage scope, not its logic, was the defect

## Symptom

J reported console popups. `audit_window_leak_compliance.py` had been reporting on this
exact class for weeks and its four checks were essentially clean. Task Scheduler was
clean too: all ~125 `Gamma_*` actions correctly use the `wscript -> pythonw` hidden chain,
and `HKCU\Console\%%Startup` was already delegated to conhost, so the usual suspects were
all exonerated. The audit could not see the thing causing the popups.

## Root cause

The GLOBAL Claude Code `PreToolUse` hook in `~/.claude/settings.json` was a bare
`npx -y block-no-verify@1.1.2`. On Windows `npx` resolves to a `.cmd`/`.ps1` shim, so
Claude Code's hook runner spawned a visible console **on every single tool call, in every
project, interactive and headless** — strictly the highest-frequency spawn surface on the
box, higher than any 1-minute scheduled task.

The audit's four checks were: `.ps1` text, `.py` text, MCP launcher configs, and the live
Task Scheduler registry. None read the `hooks` block of any settings file. The failure was
not a wrong classifier — every classifier it had was correct. It was **scope**: the
surface simply wasn't enumerated.

Aggravating detail: this repo's OWN project hooks (`.claude/settings.local.json`) were
already correctly wrapped through `run_hook_hidden.py`, whose docstring documents this
identical root cause from 2026-07-03. The fix was known, written down, and applied to the
project scope — and the global scope was never swept. Prior art existing is not coverage.

## Fix

1. `~/.claude/scripts/hidden_hook.py` — project-independent wrapper (deliberately NOT in
   this repo, since the hook is global): `CREATE_NO_WINDOW` + true stdin/stdout/stderr
   passthrough, resolving the package bin out of the npx cache and running `node <bin.js>`
   directly. A/B verified byte-identical under the real `pythonw` binary: exit 2 plus the
   same stderr text on a blocked payload, clean 0 otherwise — enforcement unchanged.
2. Check (5) `HOOK_BARE_CONSOLE_LAUNCHER` added to `audit_window_leak_compliance.py`,
   scanning project + global `settings.json`/`settings.local.json`, with an
   `EMPTY_SCAN_HOOKS` guard so a scan that looks at nothing can never read GREEN.
   RED-proofed against the pre-fix `settings.json` backup: it flags the exact `npx` line.

## Generalisation

This is popup recurrence ~#6 on this box (2026-06-20, 06-26, 07-03, 07-14, 07-29, 08-09).
Every previous fix corrected an *instance* on a surface someone happened to think of. The
recurring shape is not "we launch things wrong" — it is **"a new spawn surface appears and
nobody adds it to the audit."** When a fix class recurs this often, the durable question
stops being "where is this popup coming from" and becomes **"enumerate every place on this
box that can spawn a process, and prove the audit reads each one."** Surfaces known today:
`.ps1` text, `.py` subprocess calls, MCP launcher configs, Task Scheduler actions, Claude
Code hook commands. The next recurrence will be surface #6 — likely plugin- or
marketplace-supplied hooks, or an MCP server config outside the three paths currently
enumerated in `MCP_CONFIG_SOURCES`.
