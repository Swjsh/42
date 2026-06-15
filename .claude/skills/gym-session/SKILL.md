---
name: gym-session
description: Unified daily chart-reading audit "physical exam" for the SPY engine. Aggregates 7 audits (crypto-gym 42 validators, chart-data-verify, heartbeat-tick-audit, pin-chain-verify, heartbeat-mcp-self-test, heartbeat-pulse-check, watcher-state-inspector) into ONE GREEN/YELLOW/RED scorecard. Re-runs stale (> 2h) audits in-process. Writes `analysis/gym/{date}.md` + `automation/state/gym-scorecard-{date}.json`. Pure Python — $0 cost. Auto-fires at 17:00 ET via Gamma_GymSession; manually invocable for ad-hoc audit.
context: session
allowed-tools: Bash Read
---

# gym-session — unified chart-reading scorecard

## When to invoke

- After EOD pipeline finishes (16:30 ET) and before Manager runs (17:30 ET) — production cadence.
- Ad-hoc when J asks "is the engine green?" or "any chart-reading audits red today?"
- Before promoting a candidate strategy — must be GREEN to merge.

## How to invoke

- **Slash:** `/gym-session` (this skill — runs Python orchestrator + prints scorecard)
- **Cron (production):** `Gamma_GymSession` task at 17:00 ET → `setup/scripts/run-gym-session.ps1`
- **Direct:** `python -m autoresearch.gym_session [--date YYYY-MM-DD] [--rerun-all]`

## What it does

1. Reads existing audit scorecards from `automation/state/` and `crypto/data/scorecards/latest.json`.
2. Re-runs any audit whose output is missing or > 2 hours stale (`chart_data_verify`, `pin_chain_verify`, `heartbeat_tick_audit`).
3. Classifies each of the 7 audits as GREEN / YELLOW / RED / NOT_APPLICABLE / MISSING.
4. Aggregates a single overall verdict: RED if ANY audit is RED or MISSING; YELLOW if any YELLOW (no RED); GREEN otherwise.
5. Writes `analysis/gym/{date}.md` (narrative) + `automation/state/gym-scorecard-{date}.json` (machine-readable).
6. Appends one-line summary to `automation/overnight/STATUS.md`.
7. If overall RED → appends a HIGH task to `automation/overnight/queue.md` for next wake fire.

## Output

- `automation/state/gym-scorecard-{date}.json` — machine-readable: `{"overall_verdict": "GREEN", "audits": [...]}`
- `analysis/gym/{date}.md` — narrative table + suggested next actions
- `analysis/gym/_gym-log.jsonl` — append-only fire log
- `automation/overnight/STATUS.md` — appended one-line summary

## Cost

$0 — pure Python orchestration of existing diagnostic scripts. No LLM call.

## Invocation steps (when J runs `/gym-session`)

1. Run `python -m autoresearch.gym_session` from project root.
2. Read the printed JSON scorecard.
3. Report back to J:
   ```
   GYM SESSION {date}
     overall:           GREEN | YELLOW | RED
     crypto-gym:        {N}/{M} pass
     chart-data-verify: {verdict}
     tick-audit:        {N} ticks, {M} MISALIGNED-CRITICAL
     pin-chain:         {verdict}
     mcp-self-test:     {verdict}
     pulse-check:       {verdict}
     watcher-state:     {verdict}
     scorecard: analysis/gym/{date}.md
   ```
4. If RED, list the failing audits and suggested next-actions from the markdown.

## Per OP-26 + OP-27

- Production trade doctrine modifications BLOCKED if `overall_verdict != GREEN` — gym session is the merge gate.
- New scheduled task `Gamma_GymSession` registered per OP-27 protocol (wscript+run_hidden.vbs hidden window pattern). See `automation/state/SCHEDULED-TASKS.md`.
