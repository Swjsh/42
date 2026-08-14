# ENTRY-QUALITY HANDOFF — for the next Opus session

> **Mission in one line:** the engine's bull/bear "scores" are checklists that ADMIT trades
> being misread as RANKINGS — nothing in the live path grades a setup. Build the grading,
> evidence-first, shadow-first, without repeating this week's five scars.
>
> Written 2026-08-14 (Fable). Origin: J — *"the engine still can't tell a good bull setup
> from a bad one — what do we intend to do about it?"* after the −$1,569 wake-storm morning.
> Companion docs: `analysis/deep-research/DEEP-REVIEW-2026-08-13-MULTIAGENT.md` (36-agent
> review), `journal/2026-08-14.md` (causal chain + the 10 fixes already landed).

---

## 0. State of the world (verified 2026-08-14 midday — re-verify, don't trust)

- Engine health GREEN; ticking both accounts; keep-awake daemon live (`Gamma_MarketKeepAwake`).
- Shipped today, all guard-tested + RED-proofed: atomic entry claim (O_EXCL), cold-open guard
  (`SKIP_COLD_OPEN`), healer liveness gate, qty-aware exit coverage, per-account conviction k,
  wiring audit (`setup/scripts/pipeline_wiring_audit.py`, 11/12 GREEN).
- `min_contracts_equity_scaled` = **false** (disarmed after it doubled a bad signal). The
  revert commit pins the re-arm condition: a VALIDATED entry-quality gate. Do not re-arm on
  anything less.
- Free-model veto removed 2026-08-12 (31.2% accuracy). No LLM belongs on the hot path
  (standing doctrine). Nothing replaced it — these workstreams are the replacement.

## 1. The diagnosis, cited (do not re-derive; verify line numbers still hold)

| # | Mechanism | Code anchor |
|---|---|---|
| D1 | Score = deduction counter re-counting admission criteria; every ENTER scores 10–11 | `backtest/lib/filters.py:1273` `bull_score = 11 - len(blockers)`; blockers 1,5,6,7,8,9,10,11,12 ARE the entry conditions |
| D2 | Same disease on the bear side — **previously unmentioned** | `filters.py:1758` `bear_score = 10 - len(blockers)` |
| D3 | All components binary → distribution collapses at {10,11}, no threshold headroom (C13 class) | same functions |
| D4 | `conviction.py` (the intended positive-evidence layer) unsatisfiable: 3/7 components score, ceiling 4 < floor 5; C5 `structure_side=None` "not yet threaded off engine_cli"; C4 `range_extreme` degraded 41/41 unexplained; fleet rows uninstrumented 0/1,152 | deep review §4; per-account k FIXED 2026-08-14 |
| D5 | "ELITE" = substring check (`confluence` in a trigger name), constant on 903/903 rows, yet gates arm selectivity | `build_shared_signal.py:430` `_has_confluence`, `:390` quality field |
| D6 | Zero location/context features in `BarContext` — 08-14 loser and 08-13 winner byte-identical on every logged field at entry | entry-anatomy null, deep review |

## 2. Review of the already-proposed stack (my own critique)

| Step | Verdict | Weakness to respect |
|---|---|---|
| Location-gate study (prereg `ENTRY-LOCATION-GATE-2026-08-14`, frozen) | SOUND, run first | C20: proximity gates anti-correlate with breakouts — G3 forces blocked-winner pricing; keep it. Real-fills bull n is small; replay population carries the weight, so C1 discipline (real fills first-class, replay labelled) matters. "Running intraday high at entry time" must be reconstructed causally (bars strictly before entry — C6). |
| Shadow counter ≥5 sessions before any live veto | SOUND (V-d1 pattern) | Don't let it rot unconsumed — wire its output into `firm_brief` the day it ships (this week's lesson: an instrument nobody reads isn't coverage). |
| Conviction repair | SOUND but the biggest build | C4's degradation cause is UNKNOWN — root-cause before threading new inputs, or you're wiring features into a broken aggregator. |
| Tier from conviction total | Correct, blocked on repair | Enforce C13 explicitly: tiers must be REACHABLE and DIVERSE over n≥20 before anything consumes them. |
| Re-arm sizing last | Correct | Non-negotiable ordering. |

## 3. Fixes NOT yet mentioned (found this pass; each verified in code today)

**N1 — Bear side symmetry.** Everything in §1 applies to `bear_score` (`filters.py:1758`).
The location study should run BOTH directions from day one: bull cells vs intraday-high /
prior-day-high; bear cells vs intraday-low / prior-day-low. J's put question this morning is
the bear mirror of the bull failure. Cost: ~free (same runner, sign flip).

**N2 — Level QUALITY at the trigger is thrown away.** `key-levels.json` carries graded
metadata (`touches: 112/139/51`, sources, memory labels) and blocker #11 only checks that a
level-tied trigger EXISTS (binary). A `trigger_level_touches` / source-class feature is the
cheapest graded input available — the data is already on disk at entry time. CAUTION C25/C26:
touch count drives both stars AND eventual breaks; validate per ROLE (reaction-predictor vs
break-predictor) before letting it score.

**N3 — Trendline agreement is computed and unused.** `trendlines-live.json` publishes
respect-counted lines per family every 5 min (the engine independently found J's hand-drawn
line at ×26 respects on 08-13), but scoring consumes none of it, and the one existing gate
(`trendline_requires_ribbon_flip`) AND-gates it to near-zero fires (C28 class). Also: prereg
`TRENDLINE-BREAK-AT-LEVEL-2026-08-13` is FROZEN WITH ITS RUNNER NEVER RUN — running it is
both a study completion and the validation gate for this feature.

**N4 — Live chop/range context exists and is unconsumed by entries.** The 08-14 loser was
knowable as "1.1-pt range, 16 minutes into effective session" from bars already in
`BarContext.prior_bars`. A range-width-so-far feature (or the shipped chop meter's logic
inlined causally) is computable with zero new data. CAUTION C22: backward-looking regime
classifiers anti-correlate with recovery days — pre-register, expect a trade-off table, not
a free lunch.

**N5 — Chasing filter (entry EXECUTION quality ≠ setup quality).** Deep review: event C's
apparent MFE separation was partly a 17.5% ENTRY-PRICE spread on one price path (0.97 / 1.13
/ 1.14). No guard refuses an option that has already run X% from the trigger bar's premium.
A max-premium-vs-trigger-bar check is small, mechanical, and independent of all scoring work.
Candidate cells: refuse if premium > trigger-bar premium × {1.10, 1.15, 1.25}.

**N6 — Use the EXISTING probe lane to collect live evidence on gated cohorts.**
`build_shared_signal.py:827+` + `accounts.json "probe_arm"` (risky-3) already trade
gated-out cohorts at min size to turn counterfactuals into fills. When the location gate
validates in replay, add its SKIP verdict to `PROBE_ALLOWED_VERDICTS` → live evidence accrues
WHILE the shadow counter runs, instead of after. This machinery exists; nobody connected it
to the new gate. (Paper-only; still J-visible via REVOKE report.)

**N7 — evidence_n stamping is STILL not done** (deep-review tonight-item #3): every scorecard
touching 2026-08-13 must carry `evidence_n = 5` (realized-outcome clusters), loser-side
claims `n = 3`. Small, honest, unfinished.

**N8 — OPRA options-bars access is blocked** (`403 OPRA agreement is not signed`; trades
endpoint works only WITHOUT `end`). This throttles every per-minute option-context study.
**J action item** — signing the OPRA agreement on the data key unlocks bar-level studies.
Until then: the pagination-by-timestamp workaround in `journal/2026-08-13.md`.

**Consciously NOT proposed:** any LLM re-entry into the hot path (31% scar); naive
time-of-day sizing (J's 667-trade ledger inverts today's shape — deep review nulls);
re-litigating trailing/fixed/time exit grids (all null, documented — do not re-run).

## 4. Ordered workplan (with effort routing per §1 model doctrine)

| # | Work | Tier | Gate before it ships anything |
|---|---|---|---|
| 1 | Run `ENTRY-LOCATION-GATE` runner, BOTH directions (N1), after-hours, chunked around the 5-min reaper | Sonnet executes, Opus adjudicates verdict | prereg G1–G4; BH-FDR; blocked-winner column mandatory |
| 2 | N7 evidence_n stamps + N5 chasing-filter prereg (freeze only) | Sonnet | commit-before-runner |
| 3 | Conviction repair: root-cause C4 FIRST, then thread `structure_side`, then fleet instrumentation | Opus for C4 root-cause, Sonnet for threading | stays DISARMED; report would_block distribution weekly |
| 4 | N2 level-quality + N3 trendline features: run the frozen TRENDLINE-BREAK-AT-LEVEL runner, then a pre-registered feature-correlation pass on the SHADOW conviction totals | Sonnet | C25/C26 role validation; features enter conviction only as shadow components |
| 5 | N4 range-context cell added to the location study's second iteration | Sonnet | C22 trade-off table |
| 6 | N6 probe-lane wiring for whichever gate survives replay | Sonnet | paper-only, REVOKE report to J |
| 7 | Tier derivation + ELITE retirement | Opus decision | C13 reachable+diverse n≥20 |
| 8 | Re-arm `min_contracts_equity_scaled` | **J-visible REVOKE report** | only after a gate from #1/#5 is live-validated via #2-shadow + #6-probe |

## 5. Traps this week already paid for (do not re-pay)

1. **A claim and its retraction look identical to grep** — use positive markers / AST, never
   absence checks (5 instances this week).
2. **`schtasks /fo csv` truncates `Task To Run`** — task audits use `/xml` only.
3. **A docstring mention is not consumption** — the wiring audit strips comments for a reason.
4. **exit=0 / GREEN / "alive" mean "nothing raised," not "the work happened"** — six
   instances in two days; verify outputs, not exit codes (C7).
5. **STATUS.md has a retention producer** (`status_retention.py`, 45KB cap → archive). Content
   missing vs HEAD~1 is probably ROTATION — check `STATUS-archive-*.md` before "restoring".
6. **Fixes land on ALL call sites** — three half-landed fixes this week (vwap kill, recency
   clamp × full_send, Funnel double-reference). Grep for siblings, verify post-state per site.
7. **No bare `powershell`/venv-pythonw spawns** — console flash scar; system pythonw +
   PYTHONPATH (`run_py_venv_hidden.py`) or Python + CREATE_NO_WINDOW.
8. **Rule 9 / market hours** — studies and docs any time; live-path edits after 15:55 unless
   J explicitly directs (he did, twice, this week — cite it when you do).

## 6. Definition of done for the mission

Not "a score exists" — **a graded signal that separates winners from losers on data it has
never seen, validated at n≥30 per cell, consumed by at least one live surface (gate, sizing,
or brief), with its blocked-winner cost priced and accepted in writing.** Anything short of
that is another monitored-but-unread file.
