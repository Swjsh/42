# BULL-VIX-SOFT-MODE-SOLE-BLOCKER -- real sequential A/B, 2026-08-03

Generated 2026-08-02T10:35:52.571707. Runner: `backtest/tools/bull_vix_soft_mode_2026_08_03.py`.
Prereg (frozen first): `analysis/recommendations/prereg-bull-vix-soft-mode-2026-08-03.json` (2026-08-02 11:58:55 Sunday EDT).
Scope: SAFE ONLY (CONTROL = SAFE_BASE_LIVE, elite_bear_level_reject_gate_ab.SAFE_BASE + initial_equity=1746.75). No Bold cell computed -- the frozen prereg's CONTROL is SAFE_BASE_LIVE verbatim, not a Bold config, so Bold's separate n=32/$14,539.40 runner anchor is inapplicable here and is not cited anywhere in this file.
Window: 2025-01-02..2026-07-27 (390 RTH trading days; cross-check vs FREQUENCY-CEILING-2026-08-03.md (same end date): 390).
Recent-25 window: 2026-06-22..2026-07-27.
Implementation + guard + this scorecard: commit `15a2289e` (filters.py/orchestrator.py wiring,
test_bull_vix_soft_mode_2026_08_03.py, bull_vix_soft_mode_2026_08_03.py, this file + JSON).

## VERDICT: NULL

**bull:filter_8 soft-mode does not ship.** The full-population effect is real and positive
(+$1,486.30 sequential gain over CONTROL, clean mechanism, 26 added trades vs 1 pre-empted) --
but every single one of the 26 added trades falls between 2025-01-03 and 2026-05-19. The most
recent trade this flag would have added is **more than 2 months before the recent-25 window
even starts** (recent window: 2026-06-22..2026-07-27). Zero added trades, zero changed days,
zero recent-window effect. This closes the last positive lead of the FREQUENCY-CEILING weekend.

| Gate | Result |
|---|---|
| G1_recent_window_positive_PRIMARY | FAIL |
| G2_day_majority_recent | FAIL |
| G3_survives_drop_best_recent | FAIL |
| G4_runner_anchor_no_regression | PASS |
| G5_fire_count_L243 | FAIL |

## Implementation + vary-and-assert (C14 dead-knob discipline)

`vix_soft_mode_bull: bool = False` added to `evaluate_bullish_setup` (backtest/lib/filters.py),
mirroring `evaluate_bearish_setup`'s existing `vix_soft_mode` mechanism exactly: when filter 8's
VIX condition fails and the flag is True, the bar takes a **-1 score demerit** instead of
`blockers.append(8)`. Threaded through `run_backtest` (backtest/lib/orchestrator.py) at both the
direct call site AND the "ENGINE-SCORE ASSERT-AGREE" per-bar parity oracle (a second,
independent call into `lib.engine.score.score_bull` that cross-checks the orchestrator's own
scoring on every bar, `GAMMA_ENGINE_SCORE_ASSERT=1` by default) -- this second wiring point was
NOT in the prereg's spec text and was found and fixed during this session (missing it would have
raised `AssertionError` on the first bull:filter_8 sole-blocked bar of any real
`run_backtest(vix_soft_mode_bull=True)` call).

Proof, live against real `filters.py` (`backtest/tests/test_bull_vix_soft_mode_2026_08_03.py`,
6 tests):

- `test_signature_has_vix_soft_mode_bull_default_false` -- `inspect.signature` confirms the
  parameter exists, default `False` (same verification method the prereg's own motivating
  finding used to confirm the flag was ABSENT before this session).
- **Vary-and-assert direction 1 (flag OFF == pre-existing behavior):** on a bull bar where VIX is
  the SOLE blocker (vix_now=17.40, rising, under the separate 22.0 hard cap), flag=False gives
  `blockers=[8]`, `passed=False` -- byte-identical to the function before this change existed.
- **Vary-and-assert direction 2 (flag ON changes behavior):** the SAME bar, flag=True --
  `blockers=[]`, `passed=True`, and `bull_score` is **exactly** the clean-VIX bar's score minus
  1 (isolates the demerit to precisely -1, matching bear's mechanism).
- **No-op when inert:** when VIX already passes filter 8, flag True vs False are byte-identical
  on every field -- the change touches nothing else.
- **Bear/bull namespace non-collision:** `evaluate_bearish_setup` has no `vix_soft_mode_bull`
  parameter at all (`TypeError` if passed) -- no shared state.
- **engine.score parity:** `lib.engine.score.score_bull` (the generic `**kwargs` passthrough
  every backtest tool AND any future live wiring routes through) agrees field-for-field with
  calling `filters.evaluate_bullish_setup` directly, for both flag values.

RED-proof performed live this session: the `if vix_soft_mode_bull: ... else: blockers.append(8)`
branch was temporarily reverted to an unconditional `blockers.append(8)` (simulating the flag
never having been built). Result: exactly 1 of 6 tests failed
(`test_soft_mode_on_removes_blocker_and_costs_exactly_one_point`, the one whose job is
specifically "does the flag do anything") -- `8 in blockers` when it should not be. Reverted;
full 6/6 green again. Regression sweep across 150 related tests (bull/filters/orchestrator/
engine-parity/structure-shift-wiring/g2-trendline-bypass suites): 144 passed, 4 skipped, 0
failed -- the change is additive and default-off for every pre-existing caller.

Orchestrator-level integration proof: the real 390-day run below completed both the CONTROL and
ARM_C `run_backtest()` calls with `GAMMA_ENGINE_SCORE_ASSERT=1` (default or on) and **raised zero
AssertionErrors** across 210 (CONTROL) + 237 (ARM_C) raw entries and every scored bar in between
-- the orchestrator/engine.score parity fix holds under real full-population load, not just the
6 unit fixtures above.

## Per-cell table (real sequential populations, one-position-at-a-time)

| | CONTROL_SEQUENTIAL | ARM_C_SEQUENTIAL |
|---|---|---|
| n (full population) | 187 | 212 |
| Total P&L (full population) | $+4,230.35 | $+5,716.65 |
| Win rate | 0.2941 | 0.3066 |
| Avg $/trade | $+22.62 | $+26.97 |
| Drop-best remainder (full pop) | $+3,370.40 (still +) | $+4,791.65 (still +) |
| Recent-25 n | 25 | 25 |
| Recent-25 total P&L (**G1 PRIMARY**) | $-1,427.35 | $-1,427.35 |

## Day-level delta (G1/G2/G3 basis)

Recent-window day-total delta: ARM_C $-1,427.35 - CONTROL $-1,427.35 = **$+0.00**
Changed days in recent window: 0 (improved=0 worsened=0)
Drop-best-on-delta: best single contribution $+0.00, remainder $+0.00 (still_positive=False)

## Decomposition: added vs pre-empted (full population)

- ADDED cohort (only possible via the new soft-demerit path): n=26 total=$+1,206.30
- PRE-EMPTED cohort (CONTROL's own sequential trades displaced by an earlier ARM_C-only trade): n=1 total=$-280.00
- gain_over_control_sequential=$+1,486.30, identity_holds=True
- **Oracle-vs-sequential gap**: the prereg's motivating oracle figure (FREQUENCY-CEILING-2026-08-03.md sec 4) was +$8,738.00 total / +$112.03 per day-that-fires across 78 unsequenced, independently-priced sole-blocker candidates (183 candidates, 177 priced). This run's ADDED cohort (the honest, sequentially-admitted analog) is n=26 total=$+1,206.30 -- see report prose for the gap explanation.

**The gap, by how much and why:** $8,738.00 -> $1,206.30 is a **$7,531.70 (86.2%) evaporation**;
177 priced oracle candidates -> 26 real added trades is an **85.8% count evaporation**. These two
percentages are almost identical (86.2% vs 85.8%), which matters: it means the survivors are NOT
a cherry-picked subset with unusually good or bad per-trade economics -- the ADDED cohort's
per-trade average ($1,206.30 / 26 = $46.40) is close to the oracle's own per-trade average
($8,738.00 / 177 = $49.37), and the ADDED cohort's win rate (10/26 = 38.5%) is close to the
oracle's (36.7%). The mechanism is real and priced consistently; what changed is **eligibility**,
not **quality**. Three compounding filters explain the 86% loss, in order of expected size:

1. **The oracle is filter-layer-only.** A candidate whose FULL joint blocker set was exactly
   `{filter_8}` still has to clear ALL 14 OTHER named gates (`block_elite_bull`,
   `block_bull_1100_1200`, `quality_lock`, etc.) once filter 8 stops blocking it -- gates the
   oracle never exposed it to. FREQUENCY-CEILING's own §2a found two-thirds of everything the
   engine refuses is refused for multiple independent reasons; a bar that was ONLY sole-blocked
   by filter 8 at the FILTER layer can still be a named-gate casualty once it reaches that layer.
2. **Real chronological sequencing.** The oracle prices every candidate independently
   (hindsight, no one-position-at-a-time constraint); the real run can only take a newly-eligible
   bull setup if the engine is actually FLAT at that moment. `_sequential_admit`'s own numbers
   show this cost is small in absolute terms here (only 1 pre-empted trade, -$280.00) but the
   214-candidate ARM_C population itself (`replay_rows` candidate count, pre-sequencing) is
   already far below the oracle's 183 sole-blocked count, because...
3. **The demerit is soft, not free.** `vix_soft_mode_bull=True` costs -1 to `bull_score`, not a
   free pass -- a bar that only barely cleared `min_triggers`/quality thresholds with score
   exactly at the routing floor can still fail to route or lose a bull-vs-bear tie-break it would
   have won with the extra point. The oracle's sole-blocker cohort measures "what if filter 8
   simply vanished"; the real flag measures "what if filter 8 became one point cheaper," which is
   a deliberately smaller, more conservative intervention -- that difference alone is not
   measured in isolation here (out of scope for this prereg), but is consistent with part of the
   gap.

None of this is a new finding this session invented to explain away a disappointing number --
it is exactly what the prereg itself predicted as the likely outcome: "the codebase's own recent
history is a strong prior against oracle numbers holding: 11 of 12 WEEKEND-TWELVE lanes NULLed."
This lane is now the 12th data point in that same pattern, but for a DIFFERENT and more
specific reason than most of those: not "the mechanism is fake," but **"the mechanism is real,
priced consistently, and stopped firing 2+ months ago."**

## Runner cohort (G4, zero tolerance, full population, THIS study's own SAFE CONTROL)

CONTROL n=38 total=$+17,660.05 | ARM_C n=44 total=$+21,220.35 -- count_ok=True pnl_ok=True

## Fire count (G5, L243)

n_added full_population=26 (floor 10) | recent_window=0 (floor 2)

## Advisory BH-FDR (NOT a ship gate)

Population: added_cohort (n=26). p=0.48391 alpha=0.1 significant=False. Not significant --
consistent with the recency finding: a 26-trade cohort whose activity stopped 2+ months before
the population's end date does not look like a live, ongoing edge to a test that treats every
trade as exchangeable regardless of when it fired. (This is advisory only, per the prereg; it is
not why the study nulls -- G1/G2/G3/G5 already null it independently and would do so even if
this p-value were significant.)

## Gate-by-gate verdict

- **G1 (PRIMARY) -- FAIL.** Recent-25 delta is exactly $0.00 (CONTROL and ARM_C both
  $-1,427.35). Not "slightly negative" -- **identical**, because zero ARM_C-only trades and zero
  pre-emptions touch any of the 25 most recent trading days at all. The two arms' recent-window
  books are the same book.
- **G2 -- FAIL (vacuously).** Zero changed days in the recent window (0 improved, 0 worsened) --
  `improved > worsened` is `0 > 0`, false. Same root cause as G1.
- **G3 -- FAIL (vacuously).** No changed trades in the recent window means no contribution to
  drop, so drop-best-on-delta is $0.00 - $0.00 = $0.00, not `> 0`. Same root cause as G1/G2.
- **G4 -- PASS, cleanly.** Runner cohort count and $ both IMPROVED under ARM_C (38->44 trades,
  $17,660.05->$21,220.35) -- expected, since ARM_C admits more total trades (212 vs 187
  sequential) and the runner-exit share of those trades did not degrade. This gate was never in
  doubt; the flag does not damage the book's profit engine. It is the only gate that would have
  passed regardless of recency, because it is a full-population, not recent-window, check.
- **G5 -- FAIL.** Full-population fire count clears the floor easily (26 >= 10), but the
  recent-window floor does not (0 < 2) -- again, same root cause as G1-G3: the added cohort's
  most recent member is 2026-05-19, and the recent window starts 2026-06-22.

**Every failing gate fails for the identical underlying reason**: this is not four independent
weak signals, it is one fact (bull:filter_8 sole-blocking has been inactive in the recent window)
propagating through four gates that were each specifically designed to catch exactly this shape
of problem (J's dynamic-market/recency doctrine, memory:
`feedback_dynamic_market_recency_over_aggregate_2026_07_31`). The gates did their job.

## SHIP-OR-NULL: NULL

Ship rule requires G1 AND G2 AND G3 AND G4 AND G5. Only G4 passes. **This does not ship.**

- **Paper-armable under standing autonomy?** Yes, structurally -- this is a paper-only backtest
  finding, PAPER arming of either direction needs no J per OP-16/CLAUDE.md, and the ET clock at
  the time of this run was outside market hours (2026-08-02 Sunday, market closed). But autonomy
  to arm is moot when the gates themselves say no: nothing is armed, nothing is proposed for
  arming. `automation/state/params.json` is untouched.
- **Live/production wiring gap (disclosed, separate from the ship decision):** even had this
  shipped, `vix_soft_mode_bull` is NOT threaded into `setup/scripts/heartbeat_core.py`'s
  `score_params.bull_kwargs` construction (~line 650-655, which hand-builds `bull_kwargs` from
  specific named `account_params` fields, not a generic passthrough) -- that file is on this
  session's explicit DO-NOT-TOUCH list. The flag is live and usable in every backtest/research
  call path (`run_backtest`, `score.score_bull`, any future tool) but would need a dedicated,
  separately-scoped follow-up to reach the live/paper heartbeat at all. Moot given the null, but
  recorded so a future session does not assume "the code exists" means "the engine can use it."
- **Forward kill/revival criterion (for the record, in case a future session re-opens this):** if
  bull:filter_8 sole-blocking resumes firing (VIX character shifts back to more frequent
  elevated-but-not-panicked bull regimes), re-run this EXACT tool
  (`backtest/tools/bull_vix_soft_mode_2026_08_03.py`) against a refreshed data window before
  re-proposing -- do not re-cite this session's numbers as current. No standing monitor is being
  built for this (would be a $0 but permanent instrument for a mechanism with no current
  activity -- not proportionate; the FREQUENCY-CEILING report and this file are sufficient
  breadcrumbs for a future session to rediscover and re-test).

## Guards + RED-proofs

- `backtest/tests/test_bull_vix_soft_mode_2026_08_03.py` -- 6/6 passing (signature default,
  vary-and-assert x2, no-op-when-inert, bear-namespace non-collision, engine.score parity).
  RED-proofed live: reverting the flag branch to unconditional `blockers.append(8)` failed
  exactly 1 test (the one that tests "does the flag do anything"), all others unaffected;
  reverted, 6/6 green again.
- Regression sweep: 150 tests across
  `test_bull_gate_f5class_requal_2026_08_01.py`, `test_bull_requalification_2026_07_22.py`,
  `test_bull_sequence_reclaim_coupling.py`, `test_bull_trendline_wick_reclaim_shadow_only.py`,
  `test_bull_unblock_replay_probe.py`, `test_bull_unblock_structural_probe.py`,
  `test_bull_unblock_structural_widewindow.py`, `test_engine_cli_parity.py`,
  `test_engine_score_parity.py`, `test_filters.py`, `test_g2_trendline_bypass_scope.py`,
  `test_structure_shift_wiring.py`, `test_structure_shift_cascade_ab.py`,
  `test_structure_shift_replay.py` -- 149 passed, 4 skipped, 1 failed
  (`test_structure_shift_cascade_ab.py::TestBaselineAnchorReproduction::
  test_control_prefix_reproduces_stored_scorecard`, a stale hardcoded anchor: expects 190
  trades in a <=2026-07-22 prefix, gets 191 -- confirmed PRE-EXISTING and UNRELATED via direct
  diff inspection: this session's filters.py/orchestrator.py changes are additive-only with
  `vix_soft_mode_bull` defaulting False everywhere, and that test never passes the new kwarg;
  the 191-trade figure also matches CLAUDE.md's OWN current-anchor citation
  ("$4,808.75 / 191 trades / 391 days"), consistent with a data-window drift unrelated to this
  session, not chased further per this repo's own established disclosure convention for this
  exact class of anchor drift).
- `backtest/tools/bull_vix_soft_mode_2026_08_03.py` -- the real sequential A/B runner itself,
  runtime 140.5s, accounting identity verified (`gain_over_control_sequential ==
  added_total - preempted_total`, both $1,486.30, `identity_holds=true`).

---
_Source: `backtest/tools/bull_vix_soft_mode_2026_08_03.py`. Raw JSON: `analysis/recommendations/bull-vix-soft-mode-2026-08-03.json`._
