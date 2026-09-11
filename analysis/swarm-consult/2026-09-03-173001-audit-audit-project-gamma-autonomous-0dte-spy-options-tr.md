# SWARM CONSULT: AUDIT -- Audit Project Gamma (autonomous 0DTE SPY options trader + self-improvement engin

**Filed:** 2026-09-03T17:30:01 ET
**Mode:** `audit`
**Cost:** $0.0000
**Elapsed:** 92.8s
**Perspectives:** 5 / 5 succeeded

## Question

Audit Project Gamma (autonomous 0DTE SPY options trader + self-improvement engine) for what it is OBVIOUSLY missing or should already be doing AUTONOMOUSLY. List the top 6-8 concrete, ranked, actionable gaps Gamma should self-identify RIGHT NOW: better tools it isn't using, existing infrastructure not connected, next-order implications, and what the operator will point at NEXT. Be specific; avoid generic advice.

## Context (provided)

```
RECENT STATUS (top):
## [2026-09-03T16:15:03 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-09-03 -- 5 GREEN / 0 YELLOW / 0 RED / 1 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | GREEN | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | 401 RTH fires logged (09:25-16:10 ET, vs ~405 expected), 81 tick(s) showed in_trade>0. 89 real fill(s) dated 2026-09-03: safe-2@09:41, bold-2@09:41, safe-2@09:42, bold-2@09:42, safe-3@09:42, risky-1@09:42, safe-2@09:43, bold-2@09:43, safe-2@09:44, bold-2@09:44, safe-2@09:45, bold-2@09:45, safe-2@09… |
| WS6 regime stamp | GREEN | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | regime-stamp.json date=2026-09-03, generated_at_et=2026-09-03T08:40:02-04:00 (hhmm=08:40, in 08:15-08:40 window=True). today-bias.json date=2026-09-03, regime_context.stamp_date=2026-09-03 (present=True, dates_match=True). one_liner='Yesterday 2026-09-02 (Wed) = range-chop (range 0.62%, gap +0.10%,… |
| WS3 level hysteresis | GREEN | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | 386 safe core ticks, 80 distinct near-price levels. Worst: 761.32 flipped 6x (vs Friday PRE-FIX worst 743.25 @ 14x, present 331/386). 172 level-refresh run(s) logged (172 ok), hysteresis_held fired 101 time(s) across 16 distinct level(s). |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-09-03 window_end=2026-09-02 (baseline window_end=2026-07-31, advanced=True). bear now: RED_CONCENTRATED n=31 (delta +21 vs baseline n=10) exp=$-1.77/tr, verdict_moved=True. bull now: GREEN_CONCENTRATED n=42 exp=$41.48/tr. live refresh attempted=True ok=True. |
| Theta cockpit | GREEN | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | snapshot ts_et=2026-09-03T16:00:00 (fresh_today=True) accounts_checked=['safe-3', 'safe-2', 'risky-1', 'bold-2']. 242 theta-clock row(s) dated 2026-09-03 across 6 position(s); sources seen=['sqrt_time_decay_model_est']. broker_snapshot=0, sqrt_time_decay_model_est=242, unavailable=0. still sqrt_tim… |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-09-03 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-09-03`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## Live watch

- [2026-09-03T10:35:01 ET] THETA STALL :: risky-1 SPY260903C00768000 qty=5 :: est theta burn -9.45 vs est delta gain -325.00 over last 15min (mid=1.005, unrealized=-24.43%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-09-03T10:35:01 ET] THETA STALL :: safe-2 SPY260903C00768000 qty=3 :: est theta burn -5.40 vs est delta gain -195.00 over last 15min (mid=1.005, unrealized=-28.57%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-09-03T10:35:01 ET] THETA STALL :: safe-3 SPY260903C00768000 qty=5 :: est theta burn -9.45 vs est delta gain -325.00 over last 15min (mid=1.005, unrealized=-23.66%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-09-03T09:55:00 ET] THETA STALL :: safe-2 SPY260903C00770000 qty=3 :: est theta burn -5.10 vs est delta gain +0.00 over last 15min (mid=0.945, unrealized=-5.1%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-09-03T09:50:01 ET] THETA STALL :: risky-1 SPY260903C00770000 qty=5 :: est theta burn -5.05 vs est delta gain +0.00 over last 15min (mid=0.985, unrealized=-8.33%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-09-03T09:50:01 ET] THETA STALL :: safe-3 SPY260903C00770000 qty=5 :: est theta burn -5.20 vs est delta gain +0.00 over last 15min (mid=0.985, unrealized=-11.71%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
_Standing visibility-only flag surface (THETA COCKPIT, 2026-08-01 J directive) -- NOT a breakage list, no auto-exit ever. Producers append ONE loud line here on a NEW stalled-position threshold crossing; never re-fired for the same position. Producer: setup/scripts/theta_clock.py._

---

## Known broken

- [2026-09-03 05:52 ET] FULL-SUITE RED :: 12677 passed, 1 failed, 16 skipped :: tests/test_shadow_board_nonterminal_2026_09_03.py::test_status_regexes_are_the_same_object_as_prereg_hygiene :: re-run: cd backtest && python -m pytest tests/ -q -m "not slow"
- [2026-09-03T09:50+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived): p::m. Roles are falling through to their next lane or the local floor. Repoint in automation/state/model-roster.json, then re-run setup/scripts/roster_liveness.py. See automation/state/roster-health.json.
- [2026-09-03T03:37:05 ET] MCP_AUDIT_YELLOW: safe=ok, bold=ok, tv=ok, mcp_procs=FAIL -- 0 alpaca-mcp-server process(es) found
- [2026-09-02T23:45:49] GATE-EXPIRY RED :: filter-8-bear-sole :: bear sole-[8] refused 106 bar-event(s), 44 >= floor 10 read cost_money via the day's own P1 WIN (NOT_REPLAYED proxy -- directional smoke alarm, not a dollar costing verdict; a full replay via backtest/tools/postfix_gate_costing.py is the ratifying instrument) :: re-check: backtest\.venv\Scripts\python.exe backtest\autoresearch\gate_expiry_check.py --gate filter-8-bear-sole
- [2026-09-02T23:45:49] GATE-EXPIRY RED :: filter-10-bull-sole :: bull sole-[10] refused 78 bar-event(s), 28 >= floor 10 read cost_money via the day's own P1 WIN (NOT_REPLAYED proxy -- directional smoke alarm, not a dollar costing verdict; a full replay via backtest/tools/postfix_gate_costing.py is the ratifying instrument) :: re-check: backtest\.venv\Scripts\python.exe backtest\autoresearch\gate_expiry_check.py --gate filter-10-bull-sole
- [2026-09-02T22:57:10] GRADUATED-GUARDS-SLOW FAIL :: 1 failed, 45 passed, 11866 deselected, 3 warnings in 1625.82s (0:27:05) :: re-run: cd backtest && python -m pytest tests/ -m slow -q
- [2026-09-03T01:14 ET] SCHEDULED-TASKS-DOC-GAP: `backtest/tests/test_scheduled_tasks_doc.py::test_every_installed_task_is_documented` failed pre-commit at ~01:10 ET (58/59) -- `Gamma_StateFreshnessRemediate` registered by `setup\scripts\install-state-freshness-remediate.ps1` is not in `SCHEDULED-TASKS.md`. Not this fire's work (another session's in-flight install script); by ~01:12 ET the gate read 59/59 again (resolved by that other session, not by me) -- flagged here in case it reappears. Not fixed by this fire.

> **This section is the PREAMBLE and must stay above the first `## [` entry.**

RECENT COMMITS:
ce7cbb00 docs(queue): RTH-SPY-PER-MINUTE-TAPE closed -- daemon restarted 16:01 ET, new pid carries underlying_rows_written
17a2cff6 chore: auto-commit 12 strategy/candidates/ changes (auto_commit_candidates.py, L242 prevention guard)
fe5754b7 fix(guards): allowlist money_profit_lock_scope.py in the DST-frame pattern guard as a classified false positive (both sides trust-naive ET, population all-EDT, numbers byte-identical); sklearn made optional in the day-type grinder (tree candidate SKIPPED_NO_SKLEARN, test importorskip)
06653790 feat(shadow): structure-classifier shadow (live classify_trend vs walk_structure on identical bars, forward-scored) + frozen swap prereg; Gamma_StructureClassifierShadow 17:25 ET registered (registry 169); naive swap already fails the bar (walk vetoes all of 08-06)
b1f9220a feat(kitchen): day-type classifier grinder module registered + enqueued (55c382d0); first run SHADOW_CANDIDATE on prior_day_range_dollars at the WF floor (n=32, exploratory); forward shadow filed
915291fa feat(shadow): fleet-gate-leak nightly shadow (real fills, not ticks) + frozen inheritance prereg; Gamma_FleetGateLeakShadow 17:20 ET registered (registry 168); ARCHITECTURE.md known-gaps bullet
936c6e0f research(fleet-gates): 20-agent audit of which entry gates bind each arm -- the safe-cohort leak is PARTIAL (5.6-15% of safe-gated ticks), bypass P&L is noise, designation text corrected, no trading-path change; decision recorded
ddb4e9d7 feat(instrument): quote recorder writes a per-minute SPY underlying row every RTH cycle (one stock-snapshot call, kind=underlying) so post-mortems have a 1-minute tape; option rows gain kind=option; reade
[truncated]
```

## Synthesis (actionable)

_Model: `nvidia/nemotron-3-super-120b-a12b:free`, elapsed 22.0s, cost $0.0000_

We need to synthesize 5 perspectives into a single actionable output.

We need to list consensus points (what all agree on), key disagreements (where they split, and which is most rigorous with reasoning), synthesized recommendation (one paragraph), confidence (1-10), single most-important next action (concrete, specific, executable today), watch-for signal (observation that would invalidate synthesis).

We must be direct, specific, rigorous, no filler.

Let's extract each perspective's main points.

Perspective 1 (minimax/minimax-m3:free):
- Main issue: NOT_EXERCISED = GREEN semantic poisoning monday-verify checklist; will mask regressions.
- Also mentions: SHADOW-CANDIDATE scorer promotes regressed candidate because guard-count delta ignores NOT_EXERCISED vs FAIL.
- Also: test failures routed through status-enum pipeline causing PASS-count unchanged.
- Also: Gamma_StateFreshnessRemediate scheduled task not documented.
- Also: roster liveness dead lane p::m.
- Also: gate-expiry RED not auto-replayed.
- Also: graduated-guards-slow test failure not triaged.
- Also: fleet-gate-leak shadow not applied.
- Also: quote recorder tape not linked to post-mortem.
- Also: scheduled task doc gap.

Perspective 2 (nvidia/nemotron-3-super-120b-a12b:free):
- Top 8 gaps:
  1. No autonomous restart of Alpaca-MCP server (MCP_AUDIT_YELLOW).
  2. No autonomous healing of dead lanes in model-roster (ROSTER-LIVENESS).
  3. No autonomous retry/resolution of gate-expiry RED failures.
  4. No autonomous documentation of installed scheduled tasks.
  5. No autonomous adjustment of live-watch tick expectations for early closes/holidays.
  6. Theta-stall alerts visibility-only (no auto-reduce size or tighten stops).
  7. Core-recency baseline only tracked, not used for strategy re-weighting.
  8. WS1 preview diff never auto-selects correct date-scoped preview.

Perspective 3 (minimax/minimax-m2.7:free):
- Top 8 gaps (ranked):
  1. THETA STALL → NO AUTONOMOUS EXIT (critical).
  2. MCP PROCESS DEATH → NO SELF-HEAL (MCP_AUDIT_YELLOW).
  3. DEAD LANE (p::m) — MANUAL REPOINT REQUIRED.
  4. GATE-EXPIRY RED — VIOLATIONS STILL FIRING.
  5. GRADUATED-GUARDS-SLOW FAIL — 1 TEST FAILING, NO AUTONOMOUS TRIAGE.
  6. FLEET-GATE-LEAK SHADOW FILED, NOT APPLIED.
  7. QUOTE RECORDER TAPE — NOT LINKED TO TRADE POST-MORTEM.
  8. SCHEDULED TASK DOC GAP — INSTALL SCRIPTS NOT TRACKED.

Perspective 4 (liquid/lfm-2.5-2.6b:free):
- Main points:
  - Active theta-stall positions with no automated exit mechanism.
  - Portfolio erosion due to theta bleed.
  - No automatic mitigation.
  - Operational blindness.
  - Rule violations: Rule 9 (mid-session rule changes if adding auto-exit), Rule 10 (allowing positions to remain exposed).
  - Self-healing > delayed J-flag: self-healing insufficient.
  - Hidden second-order effects: roster liveness -> gate failure cascade; safe-3 gate bypass; MCP silence -> data starvation; test instability -> regression accumulation.
  - Risk score 7/10.
  - Single most-important question: Has theta-stall auto-exit framework been independently validated and integrated?

Perspective 5 (inclusionai/ling-3.0-flash-fin:free):
- Top gaps:
  1. Broker greeks pipeline dead; theta cockpit flies on synthetic model.
  2. Fleet-gate-leak: safe-3 bypasses safe-only gates (HIGH, unfixed).
  3. MCP server process dead; 0 alpaca-mcp-server instances running.
  4. Two gate-expiry RED flags with no ratifying replay.
  5. Structure-veto lift built but not applied; decision lifecycle incomplete.
  (they stopped at 5? Actually they listed 5 items.)

Now we need consensus points: what all perspectives agree on.

Look for common themes across all 5:

- MCP server process dead / no autonomous restart: appears in Persp1 (Gamma_StateFreshnessRemediate? Actually Persp1 mentions MCP_AUDIT_YELLOW? It mentions "MCP_AUDIT_YELLOW (03:37 ET) — mcp_procs=FAIL, 0 alpaca-mcp-server process(es) found" as minor. Persp2: gap 1. Persp3: gap 2. Persp4: mentions MCP silence -> data starvation. Persp5: gap 3. So all mention MCP server dead and lack of self-heal.

- Dead lane (p::m) / model-roster dead lanes: Persp1 mentions dead lane p::m. Persp2: gap 2. Persp3: gap 3. Persp4: mentions roster liveness -> gate failure cascade. Persp5: not explicitly? Persp5 does not mention dead lane. It mentions broker greeks, fleet-gate-leak, MCP server, gate-expiry RED, structure-veto lift. So dead lane not in Persp5. So not all.

- Gate-expiry RED not auto-resolved: Persp1 mentions gate-expiry RED not auto-replayed. Persp2: gap 3. Persp3: gap 4. Persp4: not explicitly? Persp4 mentions safe-3 gate bypass but not gate-expiry RED. Persp5: gap 4. So Persp4 does not mention gate-expiry RED. So not all.

- Theta-stall alerts with no autonomous exit: Persp1? Not explicitly; Persp1 mentions NOT_EXERCISED semantic, but not theta stall. Persp2: gap 6. Persp3: gap 1 (critical). Persp4: main point. Persp5: not explicitly; Persp5 mentions broker greeks dead leading to theta cockpit synthetic model, but not theta stall exit. So not all.

- Fleet-gate-leak / safe-3 gate bypass: Persp1 mentions fleet-gate-leak shadow filed not applied. Persp2 not explicitly? Persp2 does not mention fleet-gate-leak. Persp3: gap 6. Persp4: mentions safe-3 gate bypass -> systemic P&L leakage. Persp5: gap 2. So Persp2 missing. So not all.

- Graduated-guards-slow test failure not triaged: Persp1 mentions. Persp2 not. Persp3: gap 5. Persp4 not. Persp5 not. So not all.

- Quote recorder tape not linked to post-mortem: Persp1 mentions. Persp2 not. Persp3: gap 7. Persp4 not. Persp5 not. So not all.

- Scheduled task doc gap: Persp1 mentions. Persp2: gap 4. Persp3: gap 8. Persp4 not. Persp5 not. So not all.

- Live-watch tick expectations adjustment: only Persp2 gap 5.

- Core-recency baseline used for re-weighting: only Persp2 gap 7.

- WS1 preview diff auto-select: only Persp2 gap 8.

- Structure-veto lift built not applied: Persp5 gap 5; others not.

- Broker greeks pipeline dead: Persp5 gap 1; others not.

Thus consensus seems limited. However, there are overlapping themes: MCP server dead, dead lane, gate-expiry RED, theta stall, fleet-gate-leak, test failure, quote recorder, scheduled task doc. But not all perspectives cover each.

Maybe consensus is that the system lacks autonomous self-healing / remediation for known failures, and relies on manual intervention. All perspectives mention some form of missing autonomous healing or self-remediation.

Let's see: Persp1: missing autonomous handling of NOT_EXERCISED semantics, missing auto-prune of failing candidates, missing auto-restart of MCP? Actually Persp1 mentions MCP_AUDIT_YELLOW as minor, but does not call for autonomous restart. It mentions that the remediation script is registered as Windows scheduled task but not in SCHEDULED-TASKS.md. So it's about documentation.

Persp2: explicitly lists autonomous restart of MCP server, autonomous healing of dead lanes, autonomous retry/resolution of gate-expiry RED, autonomous documentation of installed tasks, autonomous adjustment of live-watch tick expectations, autonomous action on theta-stall alerts, autonomous adjustment of strategy weights based on core-recency, autonomous selection of correct preview.

Persp3: autonomous exit on theta stall, autonomous MCP process supervisor, autonomous roster auto-repair, autonomous gate expiry auto-replay, autonomous test failure triage, autonomous shadow-to-production bridge, autonomous link quote recorder to post-mortem, autonomous scheduled task doc update.

Persp4: focuses on theta-stall auto-exit missing, also mentions MCP silence, dead lane, gate bypass, test instability.

Persp5: autonomous flag on missing broker greeks, autonomous patch for fleet-gate-leak, autonomous restart MCP server, autonomous queue postfix gate costing replay, autonomous apply structure-veto lift.

Thus consensus: all perspectives agree that the system lacks autonomous self-healing/remediation for known failure modes (MCP server dead, dead lanes, gate-expiry RED, theta stall alerts, fleet-gate-leak, etc.) and relies on manual intervention. They also agree that the system should have automated responses to these detected issues.

Thus consensus points: need for autonomous self-healing/remediation for: MCP server process, dead model-roster lanes, gate-expiry RED flags, theta-stall alerts, fleet-gate-leak (safe-3 gate bypass), test failures, quote recorder utilization, scheduled task documentation, live-watch tick expectations, core-recency baseline usage, preview diff date selection, structure-veto lift application, broker greeks validation.

But we need to list consensus points as bullet list of what all perspectives agree on. Since not all perspectives mention each item, we need to find the intersection.

Intersection of all 5 perspectives: what is mentioned by every perspective? Let's check each perspective for each candidate.

Candidate: MCP server dead and need for autonomous restart.
- Persp1: mentions MCP_AUDIT_YELLOW as minor, but does not explicitly call for autonomous restart. It mentions the remediation script not documented. It does not call for restart. So not explicit.
- Persp2: gap 1: explicit.
- Persp3: gap 2: explicit.
- Persp4: mentions MCP silence -> data starvation, implies need for data source, but does not explicitly call for restart. It mentions "MCP silence → data starvation" as hidden second-order effect, but not a direct call for autonomous restart.
- Persp5: gap 3: explicit.

Thus not all explicitly call for autonomous restart. Persp1 and Persp4 mention the issue but not the remedy.

Candidate: Dead lane (p::m) and need for autonomous healing.
- Persp1: mentions dead lane p::m and that it should be autonomous? It says "The roster liveness check detects the dead lane and tells you to manually repoint it... This is a Saturday-night task that should be autonomous." So yes, calls for autonomous.
- Persp2: gap 2: explicit.
- Persp3: gap 3: explicit.
- Persp4: mentions roster liveness -> gate failure cascade as hidden second-order effect, implying need to fix dead lane, but not explicit call for autonomous healing.
- Persp5: does not mention dead lane.

Thus not all.

Candidate: Gate-expiry RED not auto-resolved.
- Persp1: mentions gate-expiry RED not auto-replayed.
- Persp2: gap 3: explicit.
- Persp3: gap 4: explicit.
- Persp4: does not mention gate-expiry RED.
- Persp5: gap 4: explicit.

Thus not all.

Candidate: Theta-stall alerts with no autonomous exit/action.
- Persp1: does not mention theta stall.
- Persp2: gap 6: explicit.
- Persp3: gap 1: explicit.
- Persp4: main point: explicit.
- Persp5: does not mention theta stall (mentions broker greeks dead leading to synthetic theta model, but not stall exit).

Thus not all.

Candidate: Fleet-gate-leak / safe-3 gate bypass not applied.
- Persp1: mentions fleet-gate-leak shadow filed not applied.
- Persp2: does not mention.
- Persp3: gap 6: explicit.
- Persp4: mentions safe-3 gate bypass -> systemic P&L leakage.
- Persp5: gap 2: explicit.

Thus not all.

Candidate: Test failures not triaged autonomously.
- Persp1: mentions graduated-guards-slow fail.
- Persp2: does not mention.
- Persp3: gap 5: explicit.
- Persp4: mentions test instability -> regression accumulation as hidden second-order effect.
- Persp5: does not mention.

Thus not all.

Candidate: Quote recorder tape not linked to post-mortem.
- Persp1: mentions.
- Persp2: does not mention.
- Persp3: gap 7: explicit.
- Persp4: does not mention.
- Persp5: does not mention.

Thus not all.

## Individual perspectives

### Perspective 1: `minimax/minimax-m3:free`

_Elapsed 13.8s, 4145 in / 1880 out, cost $0.0000_

# AUDIT: Project Gamma Self-Improvement Gaps

## 1. Most Likely Failure Mode

**The "NOT_EXERCISED = GREEN" semantic is already poisoning the monday-verify checklist and will mask real regressions within 2-4 weeks.**

Concrete scenario: WS1 preview diff has been NOT_EXERCISED for ~21 sessions (preview dated 2026-08-03, all subsequent runs are date-scoped mismatches). The footer rule ("a check passing because nothing happened is not GREEN") is documented but the verdicts in the table still print "GREEN / YELLOW / RED / NOT_EXERCISED" as a flat enum — meaning downstream parsers (autoresearch queue pickers, weekly digest generators, the SHADOW-CANDIDATE scorer in `auto_commit_candidates.py`) will either (a) count NOT_EXERCISED as a pass because it's not RED, or (b) skip it entirely so its absence never trips anything. The `graduated-guards-slow` test failure (1625s, 45/46 pass) from 2026-09-02 and the `test_status_regexes_are_the_same_object_as_prereg_hygiene` failure from 09-03 05:52 ET are both ALREADY routed through this same status-enum pipeline — meaning if a slow guard flips from PASS→FAIL during a live session, the "PASS-count" appears unchanged because the failure gets bucketed identically to a skipped test.

What breaks, in order: (1) SHADOW-CANDIDATE scorer promotes a regressed candidate because guard-count delta ignores NOT_EXERCISED vs FAIL distinction; (3) J asks "why did Tuesday's candidates all graduate?" and discovers the verifier has been blind for weeks; (4) `automation/state/monday-verify.json` is the only record and it's overwritten weekly. Nobody notices until a losing day is traced back to a candidate that should have been vetoed.

## 2. Worst-Case Impact on J's Environment

**Zero direct disruption (this is the insidious part).** No popups, no lockouts, no Discord pings. The harm is silent: J sees a green dashboard, makes a doctrine change on weekend based on a false-positive evidence base, and the next 0DTE session eats the loss. The only user-visible artifact will be the eventual losing-day post-mortem — which by Rule 10 will trigger a J-flag AFTER the loss has already been realized, not before.

The one concrete second-order risk: `Gamma_StateFreshnessRemediate` was installed 01:14 ET and immediately failed the doc-gate (`test_every_installed_task_is_documented`). The remediation script is registered as a Windows scheduled task but NOT in `SCHEDULED-TASKS.md`. If this fires during market hours and touches state files, there's no human-readable audit trail of what it did or when. Low probability, high opacity if it occurs.

## 3. Worst-Case Impact on Pilot/Heartbeat

- **Direction is fine** — direction comes from J's anchor days (4/29 + 5/01 + 5/04 winners, 5/05-5/07 losers) which are frozen and not touched by any of the audit's proposed work.
- **Overfit risk is HIGH** in the new candidates filed: `day-type classifier grinder` on `prior_day_range_dollars` at WF floor n=32 is a textbook small-sample grinder. Three rejection-rounds already folded into STRUCTURE-STOP-ZONE-BAND. The veto-lift package was built-but-NOT-applied — this is the correct posture, but if J ratifies it on a weekend without checking the SHADOW-CANDIDATE track record, the next regime shift (Aug/Sept transitions historically churn) will hit untested veto-removal logic.
- **Missed-trade risk** from the `ROSTER-LIVENESS` lane being DEAD: `p::m` is 404/archived. "Roles are falling through to their next lane or the local floor" — if a shadow lane that Pilot currently depends on (for confidence weighting, veto inheritance, or fill-attribution) was previously routed through p::m, the fallback may be silently inactive rather than visibly degraded. The roster check should be promoted from daily-checklist to **pre-flight gate before any candidate promotion**.

## 4. Rule 9 / Rule 10 / OP Violations

- **Rule 9 NOT violated** — nothing in the proposed work touches `params*.json` or `heartbeat.md` mid-session. All candidate work is filed as SHADOW_CANDIDATE / SKIPPED_NO_SKLEARN / NOT_APPLIED. This is correct.
- **Rule 10 NOT violated** — no live trading path was modified. The veto-lift, day-type grinder, structure classifier, and fleet-gate-leak shadow are all observational. The safe-3-scope finding (FLEET-STRATEGIES-BYPASS-SAFE-GATES, HIGH) correctly identified that veto flip scope = safe-2 only, but **no flip was executed**.
- **Implicit OP violation risk: no documented OP for "what counts as a NOT_EXERCISED verdict in a pass/fail aggregate."** The footer note (`a check passing because nothing happened is not GREEN`) is a comment, not an enforceable rule. If an OP doesn't exist codifying "NOT_EXERCISED must reduce the denominator or be excluded with reason logged," this gap will recur every time someone adds a new check. **This is the gap that should become OP-33 or equivalent.**
- **Minor: `MCP_AUDIT_YELLOW` (03:37 ET) — `mcp_procs=FAIL, 0 alpaca-mcp-server process(es) found`** — if any Pilot decision path actually depends on the MCP server (which "mcp_procs" implies), this is a latent infrastructure dependency with no auto-restart.

## 5. Hidden Second-Order Effects

- **`auto_commit_candidates.py` L242 prevention guard** (commit fe5754b7) — the L242 guard exists because something has previously tried to auto-commit strategy changes from a non-ratified path. The guard is reactive. There is no proactive check that the candidate being committed has actually cleared SHADOW forward-evals for N sessions rather than just one.
- **The fleet-gate-leak finding ("5.6-15% of safe-gated ticks" bypass safe gates, bypass P&L is noise)** combined with FLEET-STRATEGIES-BYPASS-SAFE-GATES ("safe-3 does NOT inherit safe-only gates, veto flip scope = safe-2 only") means: if J ever ratifies the safe-3 promotion without first wiring safe-only gates into the fleet arm consumption path (`fleet_executor.py:933-935, build_shared_signal.py:293`), the doctrine will silently drift. The architecture documents the gap; nothing connects the gate inheritance fix to the candidate promotion gate.
- **Per-minute SPY underlying tape (commit ddb4e9d7)** — readers are verified tolerant, but no consumer is wired yet. This is a foundation for a future post-mortem tool that doesn't exist. Dead infrastructure is worse than no infrastructure because it suggests capability that isn't real.
- **`quote_recorder` writing `kind=option` rows** — option rows are now landing in the same stream as underlying rows. If any downstream consumer assumes `kind ∈ {underlying, ...}` and iterates without filtering, it'll start double-counting theta-clock rows or option-mid snapshots.
- **Structure-classifier shadow (commit 06653790) — `naive swap already fails the bar`** means the candidate has been pre-rejected by its own forward eval on 2026-08-06. It still got registered at registry slot 169. There's no auto-prune for candidates that fail their own preregistered test in the first replay.

## 6. Risk Score

**6/10** — no live-trading-path risk (correct posture maintained), but the NOT_EXERCISED-as-pass semantic is a slow poison that will corrupt the self-improvement evidence base within 2-4 weeks; combined with the small-sample grinder (n=32) and the un-wired fleet-gate inheritance fix, the system is one J-ratified weekend away from promoting a candidate that should have been vetoed.

## 7. Single Most-Important Question for the Human Reviewer

**"Show me the SHADOW-CANDIDATE graduation criteria: specifically, does NOT_EXERCISED in any weekly verifier reduce the denominator, and does a candidate that fails its own preregistered forward-eval on first replay get auto-pruned before it consumes a registry slot?"**

If the answer to either is "no" or "not sure," do not ratify any candidate this weekend — fix the verifier semantics first, then re-audit the graduation pipeline, then ratify.

### Perspective 2: `nvidia/nemotron-3-super-120b-a12b:free`

_Elapsed 29.5s, 4693 in / 3554 out, cost $0.0000_

**Top 8 concrete, ranked, actionable gaps Gamma should self‑identify now**

1. **No autonomous restart of the Alpaca‑MCP server** – MCP_AUDIT_YELLOW shows 0 alpaca‑mcp‑server processes; the system only logs the issue.  
2. **No autonomous healing of dead lanes in model‑roster** – ROSTER‑LIVENESS reports permanently DEAD lanes; lanes are left to fall through manually.  
3. **No autonomous retry/resolution of gate‑expiry RED failures** – filter‑8‑bear‑sole and filter‑10‑bull‑sole gate checks remain RED; no auto‑run of postfix_gate_costing.py to ratify.  
4. **No autonomous documentation of installed scheduled tasks** – SCHEDULED‑TASKS‑DOC‑GAP persists (though recently fixed by another session); new tasks can drift undocumented.  
5. **No autonomous adjustment of live‑watch tick expectations for early closes/holidays** – WS7 shows 401 vs ~405 expected RTH fires; deviation is logged but never triggers a self‑check or adaptive threshold.  
6. **Theta‑stall alerts are visibility‑only** – Multiple THETA STALL lines appear; the system never auto‑reduces size or tightens stops based on stall frequency.  
7. **Core‑recency baseline is only tracked, not used for strategy re‑weighting** – WS11 shows bear concentration shifting from n=10 to n=31; no auto‑adjustment of strategy weights or risk limits.  
8. **WS1 preview diff never auto‑selects the correct date‑scoped preview** – The item is NOT_EXERCISED because the preview file is for a different date; the system does not pick the appropriate preview for the current session.

---

### 1. Most likely failure mode
If the alpaca‑mcp‑server remains down, Gamma loses real‑time option‑snapshot Greeks. The theta clock then falls back exclusively to the sqrt‑time‑decay model, mis‑estimating theta burn for open positions. This leads to delayed or missed exits on deteriorating trades, causing incremental losses that accumulate unnoticed until the end‑of‑day P&L review shows a drift versus the model’s expectation. J would first notice the drift in the daily performance summary or via a manual check of automation/state/theta-clock.json.

### 2. Worst‑case impact on J's environment
No pop‑ups, lockouts, or Discord pings are triggered by design (self‑healing > delayed J‑flag). However, the failure would persist until J manually intervenes, resulting in a delayed J‑flag and potential manual restart of the MCP server, breaking the “no manual intervention during market hours” principle and eroding trust in the autonomous system.

### 3. Worst‑case impact on Pilot/Heartbeat
Stale or missing Greeks cause the heartbeat to mis‑calculate position‑level risk metrics (theta, delta, gamma). This can produce wrong‑direction entries (e.g., entering a bullish spread when the underlying is actually range‑chop) or premature exits, increasing slippage and reducing the edge that Pilot relies on for 0DTE SPY trades.

### 4. Rule 9 / Rule 10 / OP violations
- **Rule 9** – Not violated directly (no mid‑session rule change), but the lack of self‑healing forces a de‑ facto mid‑session manual change when J restarts the MCP server.  
- **Rule 10** – If missing Greeks cause a position to violate a risk rule (e.g., max theta burn), the trade should be blocked; without the data, the block cannot fire, so a trade proceeds that *should* have been blocked – a Rule 10 violation.  
- No specific OP number is cited in the context, but the pattern matches OP‑32‑class silent‑failure scenarios where a dependency outage leads to uncontrolled exposure.

### 5. Hidden second‑order effects
- **Dead model‑roster lanes** force fallback to lower‑confidence perception models, increasing variance in regime‑stamp and level‑hysteresis outputs, which propagates to noisy gate decisions.  
- **Unresolved gate‑expiry RED** leaves the system using potentially unvetted entry/exit filters, raising the probability of false signals and unintended leverage.  
- **Undocumented scheduled tasks** create ops debt; future upgrades may miss critical heartbeat or remediation steps, leading to cascading failures.  
- **Live‑watch tick mismatch** if left unchecked can hide data‑pipeline degradation (e.g., quote‑recorder lag) that later affects all downstream calculations.  
- **Theta‑stall visibility‑only** means the system never learns from stall events; repeated stalls could indicate a systematic mis‑pricing of short‑dated options that the model fails to capture.  
- **Static core‑recency baseline** prevents the strategy from adapting to shifting market regimes, causing gradual over‑fit to outdated performance assumptions.  
- **Wrong preview diff** wastes research effort on irrelevant analysis, slowing the feedback loop for strategy iteration.

### 6. Risk score
**8** – Multiple critical autonomous‑healing gaps (MCP server, model lanes, gate‑expiry) that can silently degrade data quality and risk controls, leading to measurable P&L loss if not self‑corrected. The score reflects high likelihood (daily occurrences) and moderate‑to‑high impact (potential for outsized losses on 0DTE SPY).

### 7. Single most‑important question the human reviewer should ask before shipping
*Does the system have a verified, tested watchdog that autonomously restarts critical services (e.g., alpaca‑mcp‑server) and heals known failure modes (dead lanes, gate‑expiry RED, task‑doc gaps) without any operator intervention or delayed J‑flag?*

### Perspective 3: `minimax/minimax-m2.7:free`

_Elapsed 70.7s, 4002 in / 3525 out, cost $0.0000_

# Project Gamma — Autonomous Gap Audit

## Top 8 Concrete Gaps (Ranked by Urgency)

---

### 1. THETA STALL → NO AUTONOMOUS EXIT (CRITICAL)

**The gap:** Multiple positions are generating THETA STALL alerts with 23-28% unrealized losses (safe-2, safe-3, risky-1 all on SPY260903C00768000). The system detects the stall, computes the ratio, writes the alert — then *does nothing*. The "ALERT ONLY, never auto-exits" design choice means a position burning theta at 5x the delta gain sits open until manual intervention or a hard stop.

**What should exist:**
- A `Gamma_ThetaStallExit` watcher that fires when `unrealized_pct < -20% AND est_theta_burn > 3x est_delta_gain` for N consecutive ticks (configurable, e.g., N=5)
- Autonomous close order via the same execution path used for entries
- Audit trail: writes a `stall-exit.json` event with timestamp, reason, fill price, vs-entry P&L

**Why it's not there:** The current system treats loss-cuts as a human judgment call. It isn't.

---

### 2. MCP PROCESS DEATH → NO SELF-HEAL (MCP_AUDIT_YELLOW STICKING)

**The gap:** `MCP_AUDIT_YELLOW: mcp_procs=FAIL -- 0 alpaca-mcp-server process(es) found` has been sitting since `2026-09-03T09:50+00:00` without remediation. The audit identifies the failure, writes the alert, and stops. No restart loop, no alert escalation path, no process supervision.

**What should exist:**
- `Gamma_McpProcessSupervisor`: a lightweight watchdog that attempts `Start-Process alpaca-mcp-server` if the process count drops to 0 during market hours
- Retry with backoff (3 attempts, 30s intervals)
- If still failing after retries → `MCP_AUDIT_RED` → operator alert via the established channel (not a popup — per Rule 9)
- Post-restart verification: re-run the MCP audit subset to confirm connectivity before declaring GREEN

**Current state:** The system knows its tools are broken and is doing nothing about it.

---

### 3. DEAD LANE (p::m) — MANUAL REPOINT REQUIRED

**The gap:** `1 lane(s) permanently DEAD (404/archived): p::m`. The roster liveness check detects the dead lane and *tells you to manually repoint it* (`Repoint in automation/state/model-roster.json, then re-run setup/scripts/roster_liveness.py`). This is a Saturday-night task that should be autonomous. Every other lane is failing through to "next lane or local floor" — meaning p::m strategies are silently dropped, not routed.

**What should exist:**
- `Gamma_RosterAutoRepair`: when a lane returns 404, fetch the archived resource, attempt to restore it, or reassign its strategy universe to the nearest alive sibling lane
- If restoration fails → write a `lane-degraded.json` event and continue operating without that lane
- Self-heal validation: re-run roster_liveness.py immediately post-repair and confirm GREEN

**Why this matters:** The system is running with a missing lane and no alarm. Trades that should have gone to p::m are being silently redistributed.

---

### 4. GATE-EXPIRY RED — VIOLATIONS STILL FIRING

**The gap:** Both `filter-8-bear-sole` and `filter-10-bull-sole` show GATE-EXPIRY RED with 106 and 78 bar-events refused respectively, both exceeding `floor 10` for `cost_money` via the day's own P1 WIN. The system flags this as "smoke alarm" and says "full replay via postfix_gate_costing.py is the ratifying instrument" — but that replay is NOT being triggered autonomously. The gates remain active in production with known violations accumulating.

**What should exist:**
- When GATE-EXPIRY hits RED for any gate on a given session → `Gamma_GateExpiryAutoReplay` fires at EOD (post-market) to run the ratifying replay
- If the ratifying replay confirms the P1 WIN cost was real → the offending gate is flagged for J review, not left in production
- If the gate is invalidated → it should be removed from the active gate set before the next session without requiring a manual commit

**Current behavior:** The smoke alarm fires, the fire burns, and nobody puts it out.

---

### 5. GRADUATED-GUARDS-SLOW FAIL — 1 TEST FAILING, NO AUTONOMOUS TRIAGE

**The gap:** `1 failed, 45 passed` in the slow test suite. This is a single test failure — the kind that often signals a regression. It was flagged at `2026-09-03T01:14 ET` and hasn't been touched. The system knows it failed; it doesn't know *why* or whether it blocks anything.

**What should exist:**
- `Gamma_TestFailureTriage`: on any test failure, immediately run `pytest --lf` (last-failed only) with verbose output and capture the traceback
- Parse the failure reason: if it's a missing fixture, try to regenerate; if it's an assertion, log the delta
- Write a `test-failure-digest.json` that categorizes: BLOCKING (stops production), DEGRADED (works but wrong), or INSTRUMENTATION (just a check)
- If BLOCKING → escalate to J review queue; if INSTRUMENTATION → mark for weekend fix and continue

**Current state:** A test is failing silently. Nobody knows if it matters.

---

### 6. FLEET-GATE-LEAK SHADOW FILED, NOT APPLIED

**The gap:** Commit `936c6e0f` states the safe-cohort leak is "PARTIAL (5.6-15% of safe-gated ticks), bypass P&L is noise, designation text corrected, no trading-path change." Commit `915291fa` calls the safe-3 gate bypass a "HIGH" priority item (FLEET-STRATEGIES-BYPASS-SAFE-GATES). These are *known* architectural issues with "ARCHITECTURE.md known-gaps bullet" — but they remain in shadow, not in production. The system generates research but doesn't act on validated findings.

**What should exist:**
- A shadow-to-production bridge: when a shadow run achieves `shadow_result=VALIDATED` with P&L delta below noise threshold and fix complexity = LOW → auto-file a PR with the fix
- For the safe-3 leak specifically: `Gamma_FleetGateFix` should validate the fix scope (safe-2 veto flip only), confirm no regressions in the 5.6-15% leak population, and apply the minimal fix
- The current workflow: shadow → research → more research → still in shadow. That loop needs an exit condition.

---

### 7. QUOTE RECORDER TAPE — NOT LINKED TO TRADE POST-MORTEM

**The gap:** Commit `ddb4e9d7` introduced a per-minute SPY underlying row to the quote recorder for post-mortem tape reconstruction. This is a solid addition. But nothing in the current system actually *uses* this tape to reconstruct trade decisions. The post-mortem still relies on whatever manual extraction exists.

**What should exist:**
- `Gamma_TradePostMortem`: at EOD, correlate fills to the per-minute tape for every trade that ended in loss (`realized_pnl < 0` or `unrealized_pnl < -10% at close`)
- Output: `postmortem/{date}/{position_id}.md` with: entry time, SPY price at entry, option price at entry, SPY tape for the next 15/30/60 minutes, exit time, SPY price at exit, P&L attribution (was it theta? was it delta? was it vol?)
- This turns the quote recorder from instrumentation into *actionable intelligence* for the next session's regime assessment

---

### 8. SCHEDULED TASK DOC GAP — INSTALL SCRIPTS NOT TRACKED

**The gap:** `Gamma_StateFreshnessRemediate` was registered by `install-state-freshness-remediate.ps1` but is not in `SCHEDULED-TASKS.md`. The test catches this, but it required a manual fix from another session. The install script silently adds a task that the system doesn't know about.

**What should exist:**
- Any install script that registers a scheduled task must also update `SCHEDULED-TASKS.md` in the same commit/atomic operation
- Or: a pre-commit hook that diffs the actual registered tasks against `SCHEDULED-TASKS.md` and fails if they diverge
- This is the meta-gap: the system's self-documentation is manually maintained and drifts from reality

---

## Response to Your Pre-Ship Review Prompt

**Most likely failure mode:** Gap #1 (theta stall) — a position sits at -28% unrealized while the system watches. The theta burn continues, gamma risk increases, and by 15:45 ET the position is -35%. J notices at end of day. The alert was there; the action wasn't.

**Worst-case impact on J's environment:** If Gap #2 (MCP process death) cascades — losing MCP means losing whatever tool control the MCP server provides. If that's the execution path, J can't trade. The MCP_AUDIT_YELLOW has been sitting for 10+ hours with no attempt to heal.

**Worst-case impact on Pilot/Heartbeat:** Gap #4 (gate-expiry RED) means filters are firing on bad data (P1 WIN cost violations). The directional bias for bear and bull arms is potentially corrupted by gates that are lying about their state. Heartbeat trades could be entering through gates that were supposed to be blocked.

**Rule 9 / Rule 10 / OP violations:**
- Rule 9: "NO mid-session rule changes" — Gap #6 (fleet-gate-leak) would require a mid-session fix if it were applied. The current state (shadow-only) defers it to weekend, which is compliant but leaves known bad code in production.
- Rule 10: Not violated — nothing is forcing a bad trade.
- OP-32 analog: The MCP process death has been sitting YELLOW for 10+ hours. This is the OP-32 pattern: known degraded state, no auto-remediation, waiting for human.

**Hidden second-order effects:**
- Gap #3 (dead lane): Silent strategy loss means the safe/bold/risky cohort split is now unbalanced. Safe-2 might be taking trades meant for p::m. The P&L attribution is corrupted.
- Gap #7 (quote recorder): If post-mortems aren't automated, J is manually reconstructing why trades lost. That's hours of work per losing session and defeats the self-improvement loop.

**Risk score: 8/10.** The system has multiple known-broken items that are accumulating without self-heal. The theta stall alone represents uncapped loss potential on positions that are visibly, quantifiably bad. The MCP process failure is a single point of dependency for tool execution. The gate-expiry violations are corruptng the filter logic on live money.

**Single most-important question the human reviewer should ask before shipping:**

> *"If all 5 of these 'known broken' items happened simultaneously during a high-volatility 0DTE session — theta stall on three positions, MCP process dead, gate-expiry RED on both arms, and the dead lane silently dropping trades — what is the exact autonomous response chain, and has it ever been tested?"*

### Perspective 4: `liquid/lfm-2.5-2.6b:free`

_Elapsed 17.1s, 4216 in / 2415 out, cost $0.0000_

# Audit Report: Project Gamma (Autonomous 0DTE SPY Options Trader)

## 1. Most Likely Failure Mode

**Active theta-stall positions with no automated exit mechanism.** As of 2026-09-03T10:35:01 ET, three positions—`risky-1`, `safe-2`, and `safe-3`—are showing severe negative theta burn (-9.45, -5.40, -9.45 respectively) while generating only "ALERT ONLY, never auto-exits" notifications. The theta-clock daemon (`automation/state/theta-clock.json`) continuously reports these stalls but contains no auto-liquidation, partial-exit, or hedging logic. The system is effectively blind to the fact that these positions are losing value rapidly due to theta decay, yet no action is taken. When the theta burn accelerates further (which is typical for short-dated SPY calls near expiration), the positions could become fully worthless while the alert remains dormant.

## 2. Worst-Case Impact on J's Environment

- **Portfolio erosion**: Positions like `risky-1` and `safe-2` are actively bleeding theta value. If held to expiration or exercised against adverse movement, the realized P&L could turn deeply negative (potentially 100%+ loss on those contracts alone) while the system continues to emit alerts without taking corrective action.
- **No automatic mitigation**: Unlike the "block_elite_bull" flag mentioned in the Monday-preview diff, there is no equivalent "liquidate_on_theta_stall" or "hedge_when_theta_accelerates" rule. The pilot has no defensive mechanism.
- **Operational blindness**: The operator receives alerts but cannot act because the warning system itself is designed to be silent until something catastrophic happens—but even then, only after the alpha has been lost.

## 3. Worst-Case Impact on Pilot/Heartbeat

- **Trade miss / wrong direction**: If the system were to rely on any heuristic to decide whether to close a stalling position (e.g., "close when theta < X"), the current design makes no such decision. The pilot would be effectively flying blind—the heartbeats continue (fail-open), but no intelligent response occurs to protect capital.
- **Overfit risk**: The lack of hard constraints around theta behavior creates a vacuum where the model might develop pathological behavior (e.g., accumulating more stalling positions as they degrade) without detection.
- **No escalation path**: When theta stalls persist beyond the alert window, there is no automated handoff to a higher-level controller or human override.

## 4. Rule Violations

- **Rule 9 (NO mid-session rule changes)**: The theta-clock daemon runs continuously; however, adding new auto-exit logic requires a rule change. If this modification was implemented mid-session without J-rating, it violates Rule 9. The current state suggests the code exists but lacks the actual execution path for exits.
- **Rule 10 (If anything violates rules, the trade does not happen)**: The absence of any exit mechanism for stalling positions directly contravenes this rule—the system is allowing positions to remain exposed to adverse theta without protection.
- **Self-healing > delayed J-flag**: The architecture claims self-healing takes precedence over delayed flagging. Here, the self-healing mechanism (theta-stall alerts) is functioning but is insufficient—it does not heal (i.e., reduce risk) by acting on the signal. The system is healed in name only.

## 5. Hidden Second-Order Effects

- **Roster liveness → gate failure cascade**: The permanent death of lane `p::m` means certain state-management functions (likely responsible for recording fills, updating position counts, and triggering the theta-alert logic) may never execute. Combined with MCP failures (see #6), this creates a situation where even if theta-stall alerts were fixed, the system would have no way to persist state or take action.
- **Safe-3 gate bypass → systemic P&L leakage**: The research finding that `safe-3 does NOT inherit safe-only gates exposes a fundamental flaw: the "safe" classification is not actually protective. If `safe-3` is being bypassed, the entire safety perimeter collapses. The system could start executing strategies that should have been restricted to the `safe` cohort, leading to unexpected drawdowns or even margin calls.
- **MCP silence → data starvation**: With zero MCP processes running, the AlphaCap (options-snapshot) feed is unreachable. Any position adjustments, theta calculations, or gate triggers that depend on live market data become stale. The system may be operating on cached or stale data indefinitely.
- **Test instability → regression accumulation**: The mixed bag of test results (1 failed, 16 skipped, many slow warnings) suggests the codebase is fragile. A change intended to fix theta handling could inadvertently break other components (e.g., the shadow classifier, fleet-gate logic) if dependencies aren't properly isolated.

## 6. Risk Score

**7/10** — The combination of active, unmitigated theta-stall positions, complete MCP failure, and a confirmed gate-bypass vulnerability represents a high-probability, high-severity failure mode. Even though the system is currently "fail-open," the net effect is that capital is sitting in positions that are actively deteriorating with no mechanism to defend or liquidate them.

## 7. Single Most-Important Question Before Shipping

**Has the theta-stall auto-exit framework been independently validated and integrated into the main execution loop, or is it merely a diagnostic layer?** The answer must be yes—with formal verification that the exit logic (partial liquidation, hedging, or forced closure) executes reliably and does not introduce new failure modes (e.g., cascading liquidations, feedback loops between theta calculation and position sizing). Until this is proven in a controlled manner, no further deployment is acceptable.

### Perspective 5: `inclusionai/ling-3.0-flash-fin:free`

_Elapsed 42.7s, 4643 in / 4000 out, cost $0.0000_

## Top 8 Gaps Project Gamma Should Self-Identify Right Now

---

### #1 — Broker greeks pipeline is dead; theta cockpit flies on synthetic model

**What's missing:** The Alpaca options-snapshots greeks endpoint has returned `{}` every time (29/29 real ENTER rows confirmed). Theta Clock runs exclusively on `sqrt_time_decay_model_est` — a synthetic decay approximation, not market-observed theta. Every position's theta-burn alert, stall detection, and exit timing is calibrated to a model that has never been validated against live broker greeks.

**Why it should be autonomous:** Gamma already detects this streak (it logs `sources seen=['sqrt_time_decay_model_est']`). It should auto-flag this as a **hard constraint** on position sizing and refuse to scale theta-dependent strategies until real greeks are confirmed present for ≥N consecutive sessions.

**Operator will point at:** "Why is Gamma trading 0DTE options on a theta model that has never seen a real greeks response?"

---

### #2 — Fleet-gate-leak: safe-3 bypasses safe-only gates (HIGH, unfixed)

**What's missing:** Commit `7d7d1dd6` established that safe-3 does NOT inherit safe-only gates. Fleet arms consume `sig['strategies']` built from whichever core perception passed, and the veto flip scope is safe-2 only. 5.6–15% of safe-gated ticks bypass the safety cohort gates. Filed as FLEET-STRATEGIES-BYPASS-SAFE-GATES (HIGH).

**Why it should be autonomous:** Gamma registered this as a shadow task (Gamma_FleetGateLeakShadow) but the remediation is NOT applied. The system should auto-patch the inheritance chain in `fleet_executor.py` and `build_shared_signal.py` to enforce safe-only gate inheritance for safe-3, then re-run the gate-costing replay to confirm the leak is closed.

**Operator will point at:** "You filed this as HIGH three commits ago and still haven't fixed the inheritance."

---

### #3 — MCP server process dead; 0 alpaca-mcp-server instances running

**What's missing:** `MCP_AUDIT_YELLOW` reports 0 alpaca-mcp-server processes. The canonical MCP data pipeline is down. The system keeps running on a secondary path, but the MCP layer (which should be the authoritative data source for quotes, greeks, and order state) is absent.

**Why it should be autonomous:** Gamma should auto-restart the MCP server process on detection. If restart fails within N seconds, it should escalate to a hard stop on new order submission. Currently it silently degrades — the system runs, but its primary data backbone is offline.

**Operator will point at:** "Your own audit says the MCP server is dead and you just... keep going?"

---

### #4 — Two gate-expiry RED flags with no ratifying replay

**What's missing:** `filter-8-bear-sole` refused 106 bar-events and `filter-10-bull-sole` refused 78 bar-events. Both have proxy verdicts via NOT_REPLAYED (directional smoke alarm), but the full replay via `backtest/tools/postfix_gate_costing.py` has NOT been executed. These are unresolved RED gates.

**Why it should be autonomous:** Gamma should auto-queue the postfix gate costing replay when a gate hits the RED expiry threshold, execute it, and either clear the gate or hard-block the associated strategy arm. Currently the smoke alarm fires but nobody (and nothing) follows up.

**Operator will point at:** "You've had two RED gates since 09-02 and the replay hasn't run."

---

### #5 — Structure-veto lift built but not applied; decision lifecycle incomplete

**
