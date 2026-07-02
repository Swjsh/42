# 03 — EXECUTION: how to ship changes that stay shipped

> Task type: implement / apply / wire / fix. The failure mode this chapter prevents: a correct change that breaks something else, collides with a parallel worker, edits the live engine mid-session, or ships unguarded and silently regresses next week.

## E1 — The live-engine airlock (inviolable)
NEVER edit a file the running engine reads during 09:30–15:55 ET (params*.json, heartbeat_core.py, filters.py, setup_dispatch.py, fleet_live.py, exit_actuator.py, gates.py). During RTH: diagnose read-only, then STAGE. After 16:00: apply, verify, live before next open.
**The staging pattern (copy it exactly — see markdown/audits/ENTRY-FLOOR-FIX-PLAN / TZ-QUALITY-LOCK-FIX-PLAN):**
1. A `git apply --check`-verified `.patch` in markdown/audits/ (state which tree it was generated against and the required apply ORDER vs other staged patches);
2. Guard tests committed NOW but inert: evidence-pins that pass on the broken tree + fix-guards marked skip-until-applied + ONE strict-xfail sentinel that REDs if the patch lands without arming the guards;
3. A PLAN.md with exact file:line old→new and the 16:00 sequence;
4. Pre-validate: apply the patch to scratch COPIES, run the full guard suite against them, quote the green.

## E2 — Guard patterns (a fix without these is a band-aid)
- **RED-proof**: temporarily revert the fix, run the guard, watch it FAIL, restore. A guard never seen red proves nothing (the G14 exit bug hid for weeks behind a VACUOUS guard that re-implemented the buggy logic inline instead of importing the real function — always test the REAL import).
- **Vary-and-assert** for any config knob: change the value, assert behavior changes. Kills the dead-knob class.
- **Non-vacuity bite** for any negative/blocking assertion: show the guard WOULD pass if the condition were legitimately met (e.g., "this cohort isn't proposable" guards must flip to PROPOSE when fed a clean cohort — proving the reject is real, not hardcoded).
- **Ratchets** for classes: params↔consumer reconciliation, proposal-id uniqueness, registry-count drift — one test that catches every FUTURE instance, with an explicit documented baseline for legacy debt.

## E3 — Parallel-agent orchestration (how the 3-day burst actually ran)
- **Disjoint file ownership per agent, stated explicitly in the prompt** ("YOU OWN: … DO NOT EDIT: …"). The one collision we had (two agents sharing a git index) cost a soft-reset; the fix is `git commit --only <files>` and ownership lists.
- **Self-contained prompts**: paths, evidence, constraints, expected-return schema baked in — the agent must never need the parent conversation. Include the platform gotchas (backtest/.venv python, never Bash TZ, ONE long process for grinds — the reaper kills project python >5min outside the venv).
- **Agents return DATA, orchestrator writes the story.** Demand quoted command output for every claim ("verified" without a quoted line = unverified). Structured returns: changes / guards-with-quoted-results / verified / UNVERIFIED / skipped.
- **Default agents to `model: "sonnet"`** (J's quota; Fable-class only for judgment-heavy audits, and rarely).
- **Coordination warnings** when another session/agent may touch the same tree: check git log before each commit; absorb foreign commits, never redo or revert them.
- Background agents that die at usage limits usually finished their disk work — CHECK the tree/commits before relaunching; resume with context (SendMessage) rather than restarting.

## E4 — Commit discipline
One logical change per commit, conventional format, body = why + evidence + revert path. The pre-commit safety gate must PASS — **never `--no-verify`**; if the gate reds, the gate just did its job: fix the drift it caught (the "58 registered vs 66" catch was real). Trading-path changes end with a REVOKE line (revert = git revert <hash>) and a STATUS/Discord report. Push after-hours only; run github_audit.py (public repo) before any push.

## E5 — State files & Windows realities
State jsonl/json churn from daemons: never `git add -A`; add named files. Scheduled tasks: DailyTrigger (one-shots go dark), hidden wscript→pythonw chain (bare powershell flashes windows), verify NextRunTime populated after registering, keep SCHEDULED-TASKS.md counts reconciled (guard enforces). PS 5.1: no `&&`, no `Out-String -NoNewline`. ASCII-or-BOM for run-*.ps1. Kill zombies by PID via Win32_Process CommandLine match; always re-verify broker-flat after any order-touching test (finally-block flatten).

## E6 — Sequencing under uncertainty
When a prerequisite may arrive from elsewhere (J's parallel task, another agent): do the independent pieces now, defer the dependent piece with an explicit fallback deadline ("if X hasn't landed by 20:00, do X yourself — it must be live before open"). Never block silently; never race the same files.

## E7 — After any apply: prove the plane still flies
Boot check (heartbeat_core prints "skipped (not RTH)" off-hours, exit 0) + the affected suites + the parity suites if scoring was touched. Then write the UNVERIFIED list honestly — what only the next live session can prove (a fill, a live veto, a detector firing on real tape) — and make sure an INSTRUMENT (funnel/self_check/rehearsal) will auto-report it, so verification doesn't depend on anyone remembering.
