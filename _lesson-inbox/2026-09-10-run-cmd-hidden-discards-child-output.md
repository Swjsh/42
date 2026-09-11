---
kind: lesson
date: 2026-09-10
source: GOAL-WHY-THIS-WEEK-2026-09-10 W10 -> W14
---

# 92 of 195 scheduled tasks have no evidence channel — this is the C7 class's root enabler

**Symptom.** `Gamma_RefusedSetupLedger`'s 14:20 ET fire logged `launching:` then `exit=0` in
8 seconds having written **zero** output. A dedicated investigation lane could not root-cause
it — not for lack of effort (it ruled out the 5-minute reaper, `__file__`/cwd anchoring, and
SYSTEM-context with evidence) but because **the one channel that would have explained it did
not exist**: the child process's own stdout/stderr had been discarded.

**Root cause.** `setup/scripts/run_cmd_hidden.py` redirects the launched process's combined
stdout+stderr **only when the task action passes `--log`**. Without it, the launcher records
`proc.returncode` and nothing else. Measured against the live registry:

```
Gamma tasks total: 195
  via run_cmd_hidden WITH --log : 12
  via run_cmd_hidden NO --log   : 92   <-- no evidence channel
  not via run_cmd_hidden        : 91
```

**Why this matters more than any single producer.** Cluster C7 ("silent success is failure —
audit outputs, not exit codes") is the largest in the lessons index at ~90 entries. Nearly
every one of them is a producer that exited 0 while doing nothing, discovered late and
diagnosed by inference rather than evidence. **That is not 90 independent bugs; it is one
missing evidence channel, 92 times over.** A rig cannot root-cause what it never recorded.

**Fix.** Change the LAUNCHER DEFAULT, not the 92 task registrations — one file versus 92
re-registrations is a blast-radius difference of two orders of magnitude. When `--log` is
absent, default to a per-command log. Non-negotiable conditions:

- **FAIL OPEN.** This launcher starts the engine's own tasks. A logging bug that prevents a
  command from running is far worse than the problem it solves.
- **Retention cap** (OP-22). `automation/state/logs/` was already **746 MB / 8,054 files**
  before adding 92 new daily producers.
- **Unchanged exit-code contract**, so existing `LastTaskResult` guards keep working.
- **No console windows** — this file exists to keep them hidden.

**Generalisable rule.** When a producer's failure cannot be diagnosed, ask first whether the
evidence was ever captured. **"We could not root-cause it" is usually a statement about
instrumentation, not about the bug.** Before writing another per-producer guard, check whether
the generic evidence channel exists — a guard on a producer whose output is discarded can only
ever detect the absence of a file, never the reason for it.
