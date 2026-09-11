# SWARM CONSULT: AUDIT -- Audit Project Gamma (autonomous 0DTE SPY options trader + self-improvement engin

**Filed:** 2026-08-22T17:30:01 ET
**Mode:** `audit`
**Cost:** $0.0000
**Elapsed:** 79.4s
**Perspectives:** 2 / 5 succeeded

## Question

Audit Project Gamma (autonomous 0DTE SPY options trader + self-improvement engine) for what it is OBVIOUSLY missing or should already be doing AUTONOMOUSLY. List the top 6-8 concrete, ranked, actionable gaps Gamma should self-identify RIGHT NOW: better tools it isn't using, existing infrastructure not connected, next-order implications, and what the operator will point at NEXT. Be specific; avoid generic advice.

## Context (provided)

```
RECENT STATUS (top):
﻿## [2026-08-22T16:15:02 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-22 -- 1 GREEN / 0 YELLOW / 0 RED / 5 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | NOT_EXERCISED | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | no core-decisions.jsonl ticks dated 2026-08-22 -- no RTH session evidence (non-trading day or engine idle). |
| WS6 regime stamp | NOT_EXERCISED | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual reâ€¦ | 2026-08-22 is not a weekday -- Gamma_Premarket/Gamma_RegimeStamp do not fire on weekends. |
| WS3 level hysteresis | NOT_EXERCISED | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing wheneverâ€¦ | no core-decisions.jsonl ticks dated 2026-08-22. |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-22 window_end=2026-08-21 (baseline window_end=2026-07-31, advanced=True). bear now: RED n=31 (delta +21 vs baseline n=10) exp=$-16.71/tr, verdict_moved=False. bull now: GREEN n=31 exp=$2.45/tr. live refresh attempted=True ok=True. |
| Theta cockpit | NOT_EXERCISED | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STILâ€¦ | no core-decisions.jsonl ticks dated 2026-08-22 -- non-trading day. |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_corâ€¦ | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-22 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-22`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## [2026-08-22 04:13 ET] conductor: OK â€” CHEF-INBOX-BACKLOG-DRAIN: family-dedupe allowlist 2->31 families, 106->37 open items, commit `6209b0f3`

**Picked via STAGE 0 budget gate PROCEED ($25.19/$30, 2/4 fires used, WEEKEND mode) + STAGE 1a (`desk_allocator.py`: SPY 0DTE #1 "NEXT FIRE", nothing decision-rotting) + STAGE 1 priority-1/2 both clean (self-check GREEN 0 problems, `incident_fix_status.py --alert` ALL GREEN â€” the prior fire's conviction-c4-c5 fix held) + STAGE 1 priority-5 (author inboxes, oldest non-README first).** Engine health GREEN (19/19). `_chef-inbox` had 106 open items, oldest dated 2026-07-10 (43 days stale) â€” the largest un-actioned backlog of any inbox â€” a clear loop-closing target over a new artifact (OP-22 tiebreak).

**Root cause, precisely:** `strategy/candidates/_chef-log.jsonl`'s newest real work entry was dated 2026-07-23 â€” the chef author hasn't run in 30 days, purely because conductor STAGE 1's priority order (RED/incident-roster/self-audit/queue-HIGH all outrank tier-5 author inboxes) meant every fire since had a higher-priority item and never reached it. Separately, `prospector.py`'s `FAMILY_KEYWORDS` concept-family dedupe (built 2026-07-22, 2 families) was never extended as new duplicate families kept arriving weekly from the free-swarm beat â€” dedupe_key is exact-wording-stable only, so the same underlying concept re-promotes under fresh LLM phrasing every few days. 106 items reduced to ~27 real duplicate families (TRIN, NYSE TICK, DXY, ORB, gap-fill, turn-of-month, VWAP reversion, 10Y-2Y spread, max pain, PCR, IV skew, COT, market profile/TPO, FRED macro, WSB sentiment, auto S/R, harmonic patterns, order-flow/delta, FINRA short volume, credit spreads, EIA crude inventory, WTI price, CME open interest, futures curve/basis, lunch-lull, advance-decline, dealer gamma exposure, IEX Cloud).

**Fix:** extended `FAMILY_KEYWORDS` 2 -> 31 families in `prospector.py`, then applied it retroactively to the real backlog via `family_already_covered`: kept the oldest item per family as canonical, folded the rest to `.DONE` with a fold-note (matching the established 2026-07-23/2026-08-05 precedent notes), and annotated each canonical with its fold-in list. 106 open -> 37 (31 canonicals + 6 genuinely unique standalone ideas, e.g. Anchored VWAP, CME Order Imbalance, Auto Fibonacci, Quiver Quant, the full yield curve, DGS10 alone).

**QA caught 3 real false-positive keyword collisions BEFORE applying (verified, quoted):** bare `"trin"` matched inside "doc**trin**e" (fixed: require "arms index" or a TRIN-prefixed phrase); bare `"cme group"` matched a boilerplate "Data source: CME Group..." attribution line in an unrelated lunch-lull item (fixed: require "cme group daily open interest"); an over-broad `"10-year treasury yield"` phrase mis-pulled a generic FRED-macro item into the narrower 10Y-2Y-spread family (fixed: dropped the broad phrase, kept spread-specific ones). Also caught and fixed one Unicode non-breaking-hyphen (U+2011) miss (`"vwap meanâ€‘reversion"` vs the ASCII-hyphen-only keyword). Also deliberately did NOT merge "auto fibonacci" into "auto support/resistance" despite both being auto-drawn-level TV indicators â€” different testable hypothesis, kept separate.

**Verified, quoted:** `backtest/tests/test_prospector.py` 65/65 green (+28 new assertions in `test_idea_family_matches_new_2026_08_22_families`, spot-checking all 27 new families plus one un-family-able control string). Curated safety gate (`backtest/tests/run_safety_gate.py`): 59/59 PASS. `py_compile` clean on both touched files. Final dry-run before applying: 100/106 items matched into 31 families (69 dupes), 6 genuinely unmatched â€” manually eyeballed the full membership list twice before committing to the rename pass. `git show 6209b0f3 --stat --name-status` confirms exactly the intended 102 files (chef-inbox + chef-log + lesson-inbox + prospector.py + its test file) â€” `commit_scoped.py` used, not a bare `git add`, given 2505 unrelated dirty lines elsewhere in the shared checkout (L221/shared-index-absorption discipline).

**Rail 4 (infra/authoring-path fix, not a trading-path params/heartbeat_core/filters/placement edit â€” ships per OP-22/OP-26 engine-benefit authoring path):** guard tests are the regression check (a); revert is `git revert 6209b0f3`, one clean commit, 102 files (b); this STATUS entry is the REVOKE report (c). Zero live-money, secret, or CLAUDE.md surfaces touched.

**Lesson filed:** `strategy/candidates/_lesson-inbox/hand-curated-allowlist-drifts-stale-without-a-maintenance-trigger-2026-08-22.md` â€” a hand-curated allowlist that gates a recurring producer needs a maintenance trigger (drift check or owner+cadence), not just a doc comment asking nicely; also flags the structural tier-5 author-inbox starvation risk (30+ fires never reached this inbox because higher tiers were never simultaneously empty) as a still-open follow-up for a future fire.

**Not investigated further this fire (out of bounded scope):** the drift-detection/starvation-prevention guard itself (a `self_check.py` check warning when `_chef-inbox` open-item count exceeds a threshold) was named in the lesson as the natural next step but not built this fire â€” first violation, not yet re-violated, so OP-25's hard "must become a test" bar doesn't strictly apply yet; flagged for whoever next touches this inbox. The remaining 37 open chef-inbox items (31 canonical families + 6 unique) still need REAL chef research/backtesting â€” this fire only deduped the backlog, it did not advance any research question.

## [2026-08-22 02:00 ET] RED -- INCIDENT FIX ROSTER REGRESSED (1 RED, 0 unguarded)

- **conviction-c4-c5** -- closes: no entry-quality signal existed at all
  - code: C5 still None
  - guard: 17 passed in 1.66s

RECENT COMMITS:
20b74f4b chore: auto-commit 21 strategy/candidates/ changes (auto_commit_candidates.py, L242 prevention guard)
248eba4b chore: auto-commit 15 strategy/candidates/ changes (auto_commit_candidates.py, L242 prevention guard)
a44bc178 chore: auto-commit 20 strategy/candidates/ changes (auto_commit_candidates.py, L242 prevention guard)
c98dd6f3 status: log CHEF-INBOX-BACKLOG-DRAIN fire (commit 6209b0f3) + annotate PROSPECTOR-SEMANTIC-DEDUP-GAP with partial progress
6209b0f3 chef: family-dedupe allowlist 2->31 families + retroactive 106->37 chef-inbox backlog drain
fef70c06 chore: auto-commit 26 strategy/candidates/ changes (auto_commit_candidates.py, L242 prevention guard)
3abe1ecf docs: STATUS + lesson-inbox for the conviction-c4-c5 false-RED fix (6774b7cf)
6774b7cf fix: incident_fix_status.py conviction-
[truncated]
```

## Synthesis (actionable)

_Model: `nvidia/nemotron-3-super-120b-a12b:free`, elapsed 14.1s, cost $0.0000_

**1. Consensus points**  
- Both perspectives agree that Project Gamma must autonomously detect and remediate systemic operational drifts (e.g., stale author inboxes, unmaintained allowlists) without manual intervention.  
- Both acknowledge that existing guards and self-checks are insufficient to prevent recurrence of known failure modes (e.g., conviction‑c4‑c5 regression, chef‑inbox starvation).  

**2. Key disagreements**  
- Perspective 2 did not enumerate any concrete gaps; it only restated the audit instructions. Perspective 3 delivered a ranked, evidence‑based list of eight specific gaps with prescribed autonomous fixes.  
- Consequently, there is no disagreement on substance, but Perspective 2 lacks the rigor and specificity needed to prioritize remediation.  

**3. Synthesized recommendation**  
Project Gamma should immediately institute autonomous drift‑detecting guards for its highest‑leverage operational processes: (a) a self‑check that monitors `_chef-inbox` open‑item age and size, auto‑escalating tier‑5 author inbox work when thresholds are breached; (b) a weekly prospector‑drift validator that compares live concept‑family output against the curated `FAMILY_KEYWORDS` allowlist and triggers a RED if duplicate families exceed a small tolerance or coverage falls below 80%; and (c) a hardened C5 entry‑quality signal restoration (or formal deprecation) to eliminate the conviction‑c4‑c5 false‑positive loop. These actions directly address the two most severe, recurring failure modes highlighted in the evidence: author starvation and unchecked allowlist drift, which together starve the system of novel ideas and generate noise that obscures real incidents.  

**4. Confidence in synthesis**  
6/10 – Only one perspective supplied concrete, evidence‑based gaps; the other provided no substantive analysis. The synthesis leans heavily on Perspective 3, which is detailed and well‑sourced, but the lack of cross‑perspective validation reduces confidence.  

**5. Single most-important next action**  
Deploy a `self_check.py` guard that runs at each conductor fire: if the `_chef-inbox` open‑item count exceeds 50 **or** the most recent chef run is older than 14 days, automatically promote the next tier‑5 item to the highest priority queue for the upcoming fire and log a WARNING. This can be implemented in <2 hours using existing `incident_fix_status.py` patterns.  

**6. Watch-for signal**  
If, after deploying the guard, the `_chef-inbox` remains stale (>30 days since last chef run) or the open‑item count continues to grow unchecked for two consecutive weeks, the synthesis is invalidated – indicating the guard either failed to fire or the starvation root cause lies outside priority scheduling (e.g., a broken chef‑author trigger).

## Individual perspectives

### Perspective 1: `cerebras:zai-glm-4.7`

**FAILED** -- `all_lanes_failed (tried ['cerebras:zai-glm-4.7', 'meta-llama/llama-3.3-70b-instruct:free', 'qwen/qwen3-coder:free']): NotFoundError: Error code: 404 - {'error': {'message': 'This model is unavailable for free. The paid version is available now - use this slug instead: qwen/qwen3-coder', 'code': 404}, 'user_id': 'user_37luJnwxpk0HYbXnEZhUPm6TH2Q'}`

### Perspective 2: `nvidia/nemotron-3-super-120b-a12b:free`

_Elapsed 51.4s, 3958 in / 2500 out, cost $0.0000_

We need to audit Project Gamma for what it is obviously missing or should already be doing autonomously. List top 6-8 concrete, ranked, actionable gaps Gamma should self-identify right now: better tools it isn't using, existing infrastructure not connected, next-order implications, and what the operator will point at NEXT. Be specific; avoid generic advice.

We need to produce sections: Most likely failure mode, worst-case impact on J's environment, worst-case impact on Pilot/Heartbeat, Rule 9/10/OP violations, hidden second-order effects, risk score, single most-important question.

But the user asks: "Audit Project Gamma ... for what it is OBVIOUSLY missing or should already be doing AUTONOMOUSLY. List the top 6-8 concrete, ranked, actionable gaps Gamma should self-identify RIGHT NOW: better tools it isn't using, existing infrastructure not connected, next-order implications, and what the operator will point at NEXT."

Thus we need to output a list of gaps (6-8) with ranking, concrete, actionable. Then also produce the sections? The prompt says: "Produce these sections in order: 1. Most likely failure mode ... 7. Single most-important question". So we need to output those sections, but also list gaps? The task: "Your job: identify everything that could go WRONG with the proposed change. Be the harshest reviewer who would have caught the OP-32 lockout BEFORE it shipped." Wait, there is no explicit proposed change in the user message. The user gave context about recent status, conductor, incident fix roster regressed, etc. They ask to audit Project Gamma for what it is obviously missing or should already be doing autonomously. So we need to identify gaps (missing things) that could cause failures. Then produce the sections as per audit mode.

Thus we need to produce the sections, but also incorporate the gaps? The sections are about failure mode etc. Likely we need to identify the most likely failure mode based on missing gaps. So we need to list gaps then produce sections? The instruction: "Produce these sections in order: 1. Most likely failure mode ... 7. Single most-important question". So we should output those sections only. But the initial request: "List the top 6-8 concrete, ranked, actionable gaps Gamma should self-identify RIGHT NOW". So maybe we need to output that list first, then the sections? The user says: "Produce these sections in order:" after describing the task. So likely they want the sections as the answer, and within those sections we should reference the gaps. However the sections are about failure mode etc. The gaps are what we need to identify. So we can embed the gaps in the sections, especially in "Most likely failure mode" and "Hidden second-order effects". But they also explicitly ask to list top 6-8 gaps. So we should include that list somewhere. Perhaps we can start with a brief list of gaps, then go into the sections. The instruction: "Produce these sections in order:" suggests that is the required format. So we must output exactly those sections, no extra text. But the initial request also says "List the top 6-8 concrete, ranked, actionable gaps". Could be that the sections themselves should contain that list. For example, "Most likely failure mode" could describe a scenario arising from a gap. But they want a list of gaps. Might be we need to output a numbered list of gaps (6-8) and then the sections. However the instruction says "Produce these sections in order:" which seems to override. To be safe, we can include the gaps as part of the sections, maybe in "Most likely failure mode" we describe the gap leading to failure. But they ask for top 6-8 gaps, not just one failure mode.

Given the ambiguity, I think we should output a list of gaps (6-8) first, then the sections. The user explicitly asked for that list. The later instruction about sections might be for the audit mode, but the user gave both. I'll assume we need to output both: first the list of gaps, then the sections. However the instruction "Produce these sections in order:" is bold and seems to be the required output format. The earlier part: "Your job: identify everything that could go WRONG with the proposed change. Be the harshest reviewer who would have caught the OP-32 lockout BEFORE it shipped." Then they list sections. So likely they want the sections as the answer. The earlier request to list gaps might be part of the audit: we need to identify gaps, and then the sections will discuss them. So we can embed the gaps in the sections.

Thus I'll produce the sections, and within them mention the gaps. I'll ensure to cover 6-8 gaps across the sections.

Let's analyze the context to identify obvious missing things.

From the status:

- WS7 live watch: NOT_EXERCISED because no core-decisions.jsonl ticks dated 2026-08-22 (non-trading day or engine idle). So live watch not firing because no positions.

- WS6 regime stamp: NOT_EXERCISED because weekend.

- WS3 level hysteresis: NOT_EXERCISED same.

- WS11 core recency: GREEN, shows baseline frozen, etc.

- Theta cockpit: NOT_EXERCISED non-trading day.

- WS1 preview diff: NOT_EXERCISED date mismatch.

So the system is idle on weekend. But there are other issues:

- Conductor: CHEF-INBOX-BACKLOG-DRAIN: they drained backlog, but note that the chef author hasn't run in 30 days because conductor STAGE 1 priority order outranked tier-5 author inboxes. So author inbox starvation.

- Prospectors FAMILY_KEYWORDS extended to 31 families, deduped backlog.

- Incident fix roster regressed: conviction-c4-c5 RED because code: C5 still None. Guard passed but incident still RED? Actually they said INCIDENT FIX ROSTER REGRESSED (1 RED, 0 unguarded). The conviction-c4-c5 closes: no entry-quality signal existed at all; code: C5 still None; guard: 17 passed in 1.66s. So the fix for conviction-c4-c5 false-positive was applied earlier (commit 6774b7cf) but now regressed because C5 still None. So the incident fix is not robust.

- There is a lesson about hand-curated allowlist needing maintenance trigger.

- There is a note about self-check.py check warning when _chef-inbox open-item count exceeds a threshold not built yet.

- There is a note about OP-25's hard "must become a test" bar.

- There is a note about OP-22 tiebreak.

- There is a note about OP-26 engine-benefit authoring path.

- There is a note about OP-32 lockout (mentioned in instruction). Not in context but likely a past incident.

Thus obvious missing things:

1. Lack of automated trigger for chef-inbox maintenance (drift detection/starvation prevention). Should have a self-check that fires when backlog exceeds threshold, maybe auto-escalates priority.

2. No automated re-run of conviction-c4-c5 fix verification; the fix regressed because C5 still None; need a guard that ensures C5 is set after fix, maybe a unit test that runs on each commit.

3. Missing integration of prospector family dedup with auto-commit guard? The auto_commit_candidates.py has a prevention guard at L242; but maybe not checking for duplicate families.

4. No live watch validation on non-trading days? Actually WS7 expects live watch to fire on first real open position; but on weekends there are none, so NOT_EXERCISED is expected. However maybe they should simulate or have a fallback to ensure the mechanism works.

5. Missing continuous verification of regime stamp generation on weekdays; maybe need a heartbeat that ensures it fires even if missed.

6. Missing hysteresis validation: need to ensure level hysteresis is working; maybe need a test that simulates flips.

7. Missing theta cockpit validation: need to ensure greeks endpoint is working; maybe need to mock or use alternative source.

8. Missing preview diff applicability check: need to ensure preview diff is only run on appropriate dates; maybe need a date guard.

9. Missing auto-commit guard for candidate changes: they have auto_commit_candidates.py but maybe need to ensure it doesn't commit broken code.

10. Missing incident fix regression test: need to ensure that once a fix is applied, it stays fixed; maybe a test that checks the fix.

11. Missing self-healing for chef-inbox starvation: need to adjust priority or have a separate low-priority worker that runs regardless.

12. Missing documentation of OP numbers for each fix.

13. Missing monitoring of open-item count in chef-inbox with alerting.

14. Missing automated lesson generation for recurring issues.

15. Missing integration of prospector dedup with lesson-inbox to avoid duplicate lessons.

Given the context, the most obvious missing things are:

- Chef-inbox starvation due to priority ordering (no maintenance trigger).
- Conviction-c4-c5 regression (fix not robust).
- Lack of automated drift detection for allowlist.
- Lack of self-check for chef-inbox open-item count threshold.
- Lack of verification that live watch works (maybe need a test harness).
- Lack of verification that regime stamp fires on weekdays (maybe need a canary).
- Lack of verification that hysteresis works (need simulated flips).
- Lack of verification that theta cockpit gets greeks (need fallback or mock).
- Lack of verification that preview diff only runs on correct dates (need date guard).
- Lack of automated test for auto-commit guard.

We need to pick top 6-8.

Let's rank by impact and obviousness:

1. Chef-inbox starvation: author inbox never gets processed because higher priority items always present. This leads to stagnation of idea generation, missing new strategies. Impact: missing alpha, operator will notice stale ideas.

2. Conviction-c4-c5 regression: fix regressed, leading to false RED incidents, causing noise and possibly masking real issues. Impact: alert fatigue, operator may ignore real REDs.

3. Lack of automated drift detection for hand-curated allowlist (chef-inbox allowlist). Leads to stale allowlist, duplicate ideas, wasted effort.

4. Missing self-check for chef-inbox open-item count threshold (warning when backlog too high). Leads to unnoticed backlog growth.

5. Missing verification of live watch mechanism (WS7) on non-trading days: no way to confirm that the live watch would work when market opens; could fail silently on Monday.

6. Missing verification of regime stamp generation (WS6) on weekdays: could fail to fire, causing missing bias.

7. Missing verification of level hysteresis (WS3): could fail to suppress flips, causing noisy decisions.

8. Missing verification of theta cockpit (WS10): could rely on broken greeks source, leading to incorrect theta estimates.

That's 8.

Now produce sections:

1. Most likely failure mode: pick one scenario that could break. Perhaps the chef-inbox starvation leading to missing a profitable signal that causes a loss. Or conviction-c4-c5 regression leading to ignoring a real incident causing a large loss. Let's choose: Chef-inbox starvation prevents a new high-conviction idea from being researched, leading to missed opportunity and subsequent drawdown when market moves against existing positions. Who notices: J sees performance drift, operator sees stale chef-inbox.

2. Worst-case impact on

### Perspective 3: `nvidia/nemotron-3-ultra-550b-a55b:free`

_Elapsed 63.2s, 3958 in / 2500 out, cost $0.0000_

## Top 8 Ranked Gaps Gamma Should Self-Identify Right Now

| Rank | Gap | Evidence | Autonomous Action Required |
|------|-----|----------|---------------------------|
| 1 | **Tier-5 author inbox starvation** — chef hasn't run in 30 days because higher tiers never simultaneously empty | Lesson explicitly flags "structural tier-5 author-inbox starvation risk (30+ fires never reached this inbox)" | Add `self_check.py` guard: alert when `_chef-inbox` open count > threshold OR last chef run > 14 days; auto-promote tier-5 when tiers 1-4 empty for N consecutive fires |
| 2 | **No maintenance trigger for hand-curated allowlists** — `FAMILY_KEYWORDS` drifted 2→31 families over 30 days with zero automation | Lesson: "hand-curated allowlist that gates a recurring producer needs a maintenance trigger (drift check or owner+cadence), not just a doc comment" | Build `prospector_drift_check.py` scheduled weekly: compares live prospector output vs `FAMILY_KEYWORDS`, emits RED if new duplicate families > 3 or coverage < 80% |
3 | **C5 conviction signal entirely missing** — "no entry-quality signal existed at all", `C5 still None` | RED incident `conviction-c4-c5` closed but root cause unaddressed: C5 call site renamed, signal never rebuilt | Implement C5 signal (entry-quality filter) or formally deprecate C4/C5 gate with doctrine update; no middle ground |
4 | **Alpaca options greeks endpoint returns `{}` 100% of the time** — theta cockpit uses `sqrt_time_decay_model_est` fallback for 29/29 real ENTER rows | Monday verify: "Alpaca options-snapshots greeks endpoint has returned {} every time" | Switch theta source to IBKR/greeks cache or build synthetic greeks from IV surface; add alert if real greeks missing > 5 consecutive ENTERs |
5 | **Bull regime severely underpowered** — baseline n=1, exp=$-295/tr; now n=31 but only because window advanced, not new signal | WS11: "bull UNDERPOWERED n=1 exp=$-295.0/tr" → now GREEN n=31 exp=$2.45/tr but `verdict_moved=False` | Require minimum n=10 per regime before verdict trust; add `regime_sample_guard` to block bull entries when n < 10 |
6 | **Test isolation pollution** — `reload()` corrupts `setup_dispatch` across test suite | Commit 7a2edbf1: "stop test_gap_prior_close.py from reload()-corrupting setup_dispatch across the suite" | Enforce `pytest --forked` or module-scoped fixtures; add `conftest.py` guard detecting module-level mutation |
7 | **Auto-commit commits 2505 unrelated dirty lines** — `commit_scoped.py` required to avoid pollution | "2505 unrelated dirty lines elsewhere in the shared checkout (L221/shared-index-absorption discipline)" | Pre-commit hook: `git diff --stat` must show < 50 lines outside target paths; fail CI if violated |
8 | **No organic weekend regime stamp verification** — WS6 NOT_EXERCISED because "not a weekday" but no test proves Monday fire | WS6: "Gamma_RegimeStamp fires 08:22 ET weekdays... proving the first ORGANIC fire" — never verified on actual Monday | Add `monday_verify.py` check: "regime-stamp.json dated today exists by 08:25 ET"

### Perspective 4: `google/gemma-4-31b-it:free`

**FAILED** -- `all_lanes_failed (tried ['google/gemma-4-31b-it:free', 'cerebras:gpt-oss-120b']): APIStatusError: Error code: 402 - {'message': 'Payment required to access this resource. Visit your billing tab.', 'type': 'payment_required_error', 'param': 'quota', 'code': 'payment_required'}`

### Perspective 5: `qwen/qwen3-next-80b-a3b-instruct:free`

**FAILED** -- `all_lanes_failed (tried ['qwen/qwen3-next-80b-a3b-instruct:free', 'cerebras:gpt-oss-120b']): APIStatusError: Error code: 402 - {'message': 'Payment required to access this resource. Visit your billing tab.', 'type': 'payment_required_error', 'param': 'quota', 'code': 'payment_required'}`
