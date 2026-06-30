---
name: self-check
description: "Gamma verifies its OWN work so J never has to ask 'is it still running / did it crash / did an em-dash burn an hour with no output?'. Two layers: (1) AUTONOMOUS — `Gamma_SelfCheck` runs `self_check.py` every 30 min, verifies actual output (not exit codes), and pings J via STATUS.md + Discord ONLY on DEGRADED/BROKEN (GREEN = silent); (2) ON-DEMAND — `gamma_status.py` is the human-readable one-screen view J (or Gamma) can run anytime. Invoke this skill when you finish ANY build (verify it actually runs), at session start (read the latest self-check verdict before claiming anything), or when J asks about system state. Embodies OP-33 (verify don't claim; visibility is the product)."
allowed-tools: Bash Read Grep Glob
---

# Skill: self-check  (Gamma watches Gamma)

> J 2026-06-29: *"I'm not gonna sit in a terminal checking an AI. Wire it into a skill +
> the CLAUDE.md framework so you frequently check yourself and I don't have to ask."*
> This is OP-33 made mechanical: **verify the actual work, surface problems before J asks.**

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
