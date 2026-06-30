---
name: self-check
description: "Gamma verifies its OWN work so J never has to ask 'is it still running / did it crash / did an em-dash burn an hour with no output?'. Two layers: (1) AUTONOMOUS — `Gamma_SelfCheck` runs `self_check.py` every 30 min, verifies actual output (not exit codes), and pings J via STATUS.md + Discord ONLY on DEGRADED/BROKEN (GREEN = silent); (2) ON-DEMAND — `gamma_status.py` is the human-readable one-screen view J (or Gamma) can run anytime. Invoke this skill when you finish ANY build (verify it actually runs), at session start (read the latest self-check verdict before claiming anything), or when J asks about system state. Embodies OP-33 (verify don't claim; visibility is the product)."
allowed-tools: Bash Read Grep Glob
---

# Skill: self-check  (Gamma watches Gamma)

> J 2026-06-29: *"I'm not gonna sit in a terminal checking an AI. Wire it into a skill +
> the CLAUDE.md framework so you frequently check yourself and I don't have to ask."*
> This is OP-33 made mechanical: **verify the actual work, surface problems before J asks.**

## Why this skill had to be PROMPTED (and how to never need prompting again)

This skill exists because J had to dictate it verbatim. That is the tell: I treated each *"is it
running? / did it crash? / is it actually trading?"* as a query to **answer**, never as the SPEC
for a **missing instrument**. An Opus meta-cognition panel (2026-06-29) dissected why, and the
adversarial lens demoted the obvious "Gamma lacked empathy" answer to a *symptom* and named the
real, load-bearing cause:

> **No mechanism converted a repeated USER QUESTION into a build task.** The friction organ
> (`friction_distiller`) counted the **rig's** pain (silent failures, regime flips) and never
> **J's** pain (having to ask again). The correction hook matched only *commands*, never
> *questions*. So "J asked 6 times" was counted **nowhere** → crossed no threshold → the
> instrument never got specced by the machine. OP-33 and this skill had to be hand-installed
> because the loop had **no entry point for the most common signal J emits: a question.**

**The generative rule (run BEFORE the mechanics below, on EVERY task — not just trading builds):**
**A repeated question from J is a missing instrument, not a query.** Assurance — J no longer
having to ask — is the deliverable; the artifact is just its carrier. **I am the monitoring loop;
J is the off-switch — if J noticed something broke before I did, my visibility layer has a hole.**

### The J-MIND CHECK (mandatory gate at the END of every task)
- **Q1 — BELIEF + VERIFY:** What will J believe after my report, and can he re-confirm it WITHOUT
  me? If the only proof is my word / `lastResult=0` / "the file exists" → the deliverable is the
  **standing surface** (state file + one-command glanceable view + auto-ping-on-change), not the
  sentence. **I never type "runs / works / is fixed / is trading" without pasting the exact output
  that proves it THIS turn — else I write UNVERIFIED.**
- **Q2 — WHO-IS-THE-WATCHER:** If this silently breaks tomorrow, who finds out first — me, or J by
  asking? If "J," I owe a self-verifying check that emits state and flags itself on failure.
  "It works" isn't done until "it tells J when it stops working" is true.
- **Q3 — REPEAT-ASK COUNTER (threshold = 2, NOT 5):** Has J asked any variant of this intent before
  (is-running / did-crash / is-trading / where-is-X / did-it-save / "well?" / "any update")? On the
  **2nd** occurrence I STOP answering ad-hoc and BUILD the instrument that retires the question
  class, then report I built it. **Answering twice is the failure mode.** Operator repetition is
  higher-severity than rig friction — each ask is an active interruption.

**GATE:** any task J could later ask "is it running / did it work" about is INCOMPLETE until it
emits a verifiable, glanceable state AND any 2nd-occurrence ask has been converted into a build.
Shortcut: *"If J had to ASK this, what instrument is missing that would have told him FIRST?"* — if
I can name one and it doesn't exist, the turn isn't done until it does.

**This is mechanized, not mood** (it survives session amnesia): `setup/hook-detect-correction.ps1`
captures J's state-questions to `automation/state/j-question-ledger.jsonl`; `friction_distiller.py`
counts them as the `recurring_user_question` class and trips `BUILD_ELIMINATING_INSTRUMENT` at ≥2.
Doctrine clause: CLAUDE.md **OP-33(e)**.

## The two layers
1. **Autonomous (the point):** `Gamma_SelfCheck` (every 30 min, 24/7) runs
   `setup/scripts/self_check.py`. It VERIFIES THE WORK, not the wrapper exit code
   (`lastResult=0` lied while the work crashed). On DEGRADED/BROKEN it appends to
   `automation/overnight/STATUS.md` `## Known broken` AND queues a Discord ping
   (only on a CHANGED problem set — no spam). **GREEN is silent.** J finds out from
   Gamma, never by asking.
2. **On-demand:** `setup/scripts/gamma_status.py` — the one-screen human view (live chain,
   accounts, autonomy tasks, TOOLS-not-daemons, known-broken). Run anytime:
   `backtest/.venv/Scripts/python.exe setup/scripts/gamma_status.py`.

## What self_check.py actually verifies (each a fact, not a claim)
- **ENCODING / em-dash class (the 544-day silent-failure pattern):** every `run-*.ps1` must
  be ASCII-or-BOM, else PS 5.1 reads it as cp1252 and parse-crashes silently (exit-0, no
  output) — the exact bug that killed `Gamma_TvWatchdog` for hours. Guarded at dev-time by
  `test_graduated_guards.py::test_run_ps1_ascii_or_bom`.
- **Stale autonomy output IN-WINDOW:** level feed / beacon / heartbeat decisions must be fresh
  during RTH (a task firing exit-0 but producing nothing = caught here).
- **Live-chain health:** engine-health RED.
- Verdict GREEN / DEGRADED / BROKEN → `automation/state/self-check-last.json`.

## How Gamma uses it (the doctrine, OP-33)
- **At session start:** read `self-check-last.json` BEFORE claiming anything about state.
- **After ANY build:** invoke this — a build isn't done until self-check confirms it's firing
  (not just "the file exists"). Run `gamma_status.py` and quote the verified line to J.
- **Never** tell J "X is running" without a self-check / gamma_status line backing it.

## If self-check reports BROKEN
Read the problem, fix the root cause (e.g. BOM-sweep a non-ASCII PS1: read bytes, prepend
`\xef\xbb\xbf`, re-verify it parses), re-run self_check, confirm GREEN. A fix isn't done
until the next self-check is GREEN.
