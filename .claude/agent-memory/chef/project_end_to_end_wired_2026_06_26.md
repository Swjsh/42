---
name: project-end-to-end-wired-2026-06-26
description: Full end-to-end loop map + autonomy scorecard (75%); the exact remaining blockers to 100% autonomous, with verified file evidence
metadata:
  type: project
---

End-to-end wired map written to `markdown/planning/PROJECT-END-TO-END-WIRED-2026-06-26.md`. The loop = eye(sight_beacon)→brain(heartbeat_core+engine_cli 15 gates + Gate16 structure-veto)→hand(_execute+fleet_broker+exit_actuator)→ledger(core-decisions.jsonl)→presence(discord-watcher→bridge→J ~45s)→learn(kitchen+conductor)→APPLY(discord-responder ship<id>→autonomy_actuator commit).

**Why:** J asked for the strung-together autonomy picture + blunt scorecard after a 5-subsystem audit + a fix pass.

**How to apply:** ~75% runs unattended today. The missing 25% is:
- **G1 FIXED this pass** (was the P0 blocker): `run-heartbeat-core.ps1` lines 8+12 now set GAMMA_CORE_ARMED=1 + GAMMA_CORE_MANAGES_EXITS=1 → simple_fallback=True → no more Alpaca OTO-bracket PLACE_FAIL (code 42210000). Guarded by test_engine_liveness_guards.py.
- **G2 FIXED this pass** (latent DST break): `setup/scripts/et_clock.py` shared DST-aware clock + 9 live-path migrations off hardcoded `timezone(timedelta(hours=-4))` + 3 task re-registers (SwarmPremarket/ContextGuard/SpendSummary were 2h late on the Ohio→Colorado Mountain move). Guard test_et_clock.py static-scans the banned pattern.
- **The 2 HARD blockers to 100%:** (1) ARM = J flips shadow→live; (2) APPLY hop NEVER fired — no conductor-approvals.jsonl, no autonomy-changelog.jsonl, all 17 proposals pending; needs J `ship <id>` or interactive batch-apply. The 26 L169-L187 CLAUDE.md index folds are rail-4 (actuator can't touch CLAUDE.md).
- **5 P1 wiring gaps queued for conductor** (queue.md Tier-1): G4 (vwap_cont+gap_and_go enabled=true but heartbeat_core never routes their WatcherSignals to _execute — DEAD KNOBS, verified line ~533 "NOT wired here yet"), G6 (VIX-intraday absent → vix_dayside SKIP_NO_FEED every tick), G5 (SwarmPremarket 10:15ET re-register to 08:15), G7 (EOD-flatten still LLM-fragile, no pure-Python backstop), G8 (companion approval bus dead — actuator never reads companion-decisions.jsonl).
- Gamma_SelfAudit LastRun=1999 (never fired) — autonomous gap-finder feed not actually running.

Verified file evidence this fire: run-heartbeat-core.ps1:8/12, heartbeat_core.py:540 extra_signals, conductor-approvals.jsonl ABSENT, 17 pending proposals, 0 vix_intraday refs. Related: [[project_research_kitchen_subsystem_map]].
