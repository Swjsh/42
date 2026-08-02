## [2026-08-02T13:46:42 ET] session: OK -- FLEET-STRIKE-TIER-ATM-EXTENSION-SAFE3 + FLEET-SHRINK-NOT-DENY -- commits `9b6a3e35`, `c2cb9f72`

**Signal J wakes to (OP-25).** ET verified via `et_clock.py` before touching anything
(Sunday 13:24-13:46, market_hours=False -- the task brief's own "Monday pre-dawn" framing was
WRONG against the real clock; flagged, not acted on, since Sunday afternoon is not a
market-hours weekday violation either way). Read `analysis/deep-research/ARM-PARTICIPATION-
AND-GROWTH-2026-08-03.md` (commit `642ce211`) per the brief; shipped the two cheap, already-
half-built fixes it named as the engine's own next actions. Both PAPER, both guarded,
both RED-proofed, zero live-arming action.

**FIX 1 -- safe-3 ATM strike-tier extension (commit `9b6a3e35`).**
Routing verified BY EXECUTION before touching anything: `fleet_executor._tiers_for_arm(safe-3)`
resolved `V15_BOLD_TIERS` (OTM-3, confirmed via `accounts.json`'s explicit
`params_patch.strike_tier_table="bold"`), exactly as the brief said. Repointed to
`"bold_core"` -> `V15_BOLD_CORE_TIERS` (ATM under $2K), mirroring risky-1/risky-3's
2026-08-01 extension. AFTER, re-verified by execution: safe-3 -> `V15_BOLD_CORE_TIERS`
(ATM, offset=0 @ safe-3's live equity $1,967.81); risky-1/risky-3 unaffected (still
`bold_core`); safe-1 (retired) unaffected (still `bold`/OTM-3, preserved as the shared
table's live regression witness).
**HONEST FRAMING (verbatim, not oversold):** PARTICIPATION/machinery fix, not a validated
P&L edge -- `bold-strike-axis-2026-07-15.json` verdicts ALL 6 strike cells including ATM
`ship_ready:false` / "WATCH -- NOT ship-ready" (fails the walk-forward gate, structurally
null for this cohort). risky-1/risky-3's own fix landed **2026-08-01, a Saturday** -- 2026-07-31
is the last real trading day in the participation study's dataset, so there are **ZERO LIVE
TRADING DAYS OF EVIDENCE** on that precedent as of this ship, let alone on safe-3's own copy.
Pre-registered before arming: `analysis/recommendations/fleet-strike-tier-atm-extension-safe3-
prereg-2026-08-03.json` (n>=20-fill gates, mirrors the risky-1/risky-3 prereg, discloses the
UNTESTED $600-notional-cap tension this fix could trade one blocker for another).
**Blast radius:** grepped every `safe-3` + strike-tier hit across `backtest/tests/`, found and
updated 4 guard files that pinned safe-3 to the old OTM table (`test_bold_core_strike_tier_
2026_07_15.py`, `test_fleet_strike_tier_floor_collision_2026_07_31.py`, `test_fleet_arm_parity.py`,
`test_fleet_arm_replay.py`) plus one stale comment (`test_reset_plan_tier_boundaries_2026_08_01.py`).
**RED-proofed:** reverted `accounts.json` to `"bold"`, ran the 4 files -- exactly 4 tests failed
(the ones asserting safe-3 resolves `bold_core`), 59 others stayed green; restored, 63/63 green.
**Revert:** delete/set-back `params_patch.strike_tier_table` to `"bold"` on safe-3 in
`accounts.json` (byte-identical, no code change -- the `bold_core` branch already existed).
**Kill criterion:** first 10-15 real sessions must show a material drop in safe-3's
`SKIP_MIN_PREMIUM_FLOOR` rate (baseline ~1.9/day) without net real-fill P&L reading worse than
the pre-fix -$22/13-day baseline, else revert.

**FIX 2 -- shrink-not-deny in fleet_executor's qty resolution (commit `c2cb9f72`).**
Real function name confirmed to be `_qty_for` exactly as the brief named it -- but it is a
phase-A pure-gating function (runs before any premium is resolved), so the shrink cannot live
inside it. Added `_shrink_qty_to_affordable`, wired into `finalize()` (phase B) immediately
before `risk_gate.check_order` -- the first point in the call chain where a tiered qty and a
resolved premium both exist. Shrinks a too-big qty DOWN to `risk_gate.max_affordable_qty`
(the exact cap math `check_order` itself uses) instead of letting `check_order` deny the
full tiered qty outright. Floor is structurally immovable: `max_affordable_qty` only ever
returns 0 (genuine deadlock, passes through unshrunk, still denies -- no regression) or a
value `>= min_contracts` (Rule 6's floor, J's rule).
**DEFECT FIX, NOT NEW ARMING:** `position_sizing_tiers` already drives every fleet_rest order
today (live since inception per `accounts.json`'s own `grid.sizing_profiles` doc) -- this only
changes deny-on-breach to shrink-on-breach for an ALREADY-ARMED mechanism. Whether to EVER wire
CORE (safe-2/bold-2) onto `position_sizing_tiers` is untouched and remains explicitly J's call
(`SIZING-SCALING-DECISION-2026-08-03.md`'s own recommendation #2).
**Verified by execution at risky-3's REAL live equity** ($2,121.61, fetched fresh this session
via `fleet_broker.get_account`, read-only `GET /v2/account`, matched `accounts.json`'s account
number `PA31WIU8X15Q` to the penny): qty=8 @ premium $1.50 --
  BEFORE (`risk_gate.check_order` on the unshrunk qty, byte-identical to pre-fix `finalize()`):
  `allowed=False code=RISK_CAP reason='risky-3-TEST: notional $1,200 exceeds per-trade cap
  $1,061 (50% of $2,122)'`
  AFTER (the real, current `fleet_executor.finalize()`):
  `action=ENTER_BEAR risk_code=ALLOW reason='clean P entry (BASE); qty shrunk 8->7: RISK_CAP
  shrink-not-deny (was DENY pre-2026-08-03)'`
A genuine-deadlock case (elite qty=12 @ $3.00, even min_contracts=5 doesn't fit) HOLDs both
before and after (`action=HOLD risk_code=RISK_CAP`) -- proves no risk loosening. A parallel
Safe-side proof at the $2,000 boundary confirms the fix isn't Bold-only.
**RED-proofed:** reverted the `finalize()` wiring to a no-op passthrough (`_qty, _shrink_note =
plan.qty, None`), ran the new suite -- exactly the 3 finalize()-dependent tests failed (the 8
pure-function tests on `_shrink_qty_to_affordable` stayed green, correctly, since that function
itself was untouched by the mutation); restored, 40/40 green (11 new + 29 existing
`test_fleet_executor.py`, unchanged -- vary-and-assert that the existing risk-cap-denies test
still denies when the shrink is a no-op).
**Revert (one line, byte-identical):** in `finalize()`, change
`_qty, _shrink_note = _shrink_qty_to_affordable(plan.qty, equity, premium, _fleet_params)`
back to `_qty, _shrink_note = plan.qty, None`.
**Kill criterion:** over the first n>=10 real fleet fills whose `decisions.jsonl` reason
carries a shrink note, or 10 trading sessions post-ship (whichever first), if that shrunk-qty
cohort's realized net P&L reads negative, revert per above.

**Suite counts (both fixes together):** curated safety gate (`run_safety_gate.py`) 6 suites,
**59/59 PASS**. Full `automation/state/fleet/` suite (pytest, includes both new/updated files):
**348/348 PASS**. The 5 strike-tier-specific `backtest/tests/` files together: **73/73 PASS**.

**What evidence exists vs does not, stated plainly:** BOTH fixes are unit/integration-tested
and execution-verified against real current equity/params -- that is real, fresh evidence this
session. NEITHER fix has ANY live P&L evidence yet (zero fills have occurred under either
change as of this commit) -- the kill criteria above are the forward gates, not yet cleared or
failed. Fix 1's underlying strike table (ATM) additionally has NO validated P&L edge at all,
on ANY population, per bold-strike-axis-2026-07-15.json's own disclosed WF-gate failure --
this was true before this ship and remains true after it.

Artifacts: `analysis/recommendations/fleet-strike-tier-atm-extension-safe3-prereg-2026-08-03.json`.
`automation/state/fleet/test_shrink_not_deny_2026_08_03.py`.

---

## [2026-08-02T12:00:04 ET] conductor: QUIET -- nightly budget EXHAUSTED (8 fires today >= max_fires 4) -- zero model work this fire, gate exited immediately

## [2026-08-02T10:00:04 ET] conductor: QUIET -- nightly budget EXHAUSTED (7 fires today >= max_fires 4) -- zero model work this fire, gate exited immediately

## [2026-08-02T08:00:06 ET] conductor: QUIET -- nightly budget EXHAUSTED (6 fires today >= max_fires 4) -- zero model work this fire, gate exited immediately

## [2026-08-02T04:16:33 ET] conductor: OK -- EXIT-HYBRID-PRETP1-FLOOR iteration 4 -- ARM_NOTHING, but the profit-lock-mechanism axis is now CLOSED (4/4 iterations tested)

**Signal J wakes to (OP-25).** Budget PASS ($8.80/$30, 3/4 fires before this one), market-hours
gate PASS (Sunday 04:00 ET). Engine health GREEN. Self-audit gaps: nothing new since 2026-08-01
(already fully triaged). Priority scan (task_scorer.py) surfaced TWIN-DOCTRINE-FIRST-DEPLOY as
top-ranked but it is already DRAFTED + proposed to J (gp-2026-07-23-twin-doctrine-001, pending
J's `ship`/`shelve` reply) -- nothing autonomous left to do there. Picked the queue's other
CRITICAL item instead: **EXIT-HYBRID-PRETP1-FLOOR**, the isolated 4th candidate on the exit-leak
arm axis (filed 2026-07-29, 3 prior nulls).

**Built exactly what the item specced:** a NEW, structurally independent knob
(`pre_tp1_be_floor_arm_pct` on `exit_manager.ExitState`/`plan_exit_actions`, commit `ad675965`)
that arms a BE-floor-ONLY scratch pre-TP1 -- never trails, never sets `profit_lock_armed` --
while `profit_lock_mode` stays `"trailing"` throughout, so the post-TP1 chandelier (the
+$15,774.05/35-for-35 runner engine) is provably untouched. This fixes iteration 3's confound:
`profit_lock_mode="fixed"` was read by BOTH the pre-TP1 AND post-TP1 branches, so 25 of 27
iteration-3 "degraded" trades were actually the post-TP1 trailing protection silently
disappearing, not the pre-TP1 whipsaw the hypothesis targeted.

**Froze a pre-reg BEFORE building the runner** (`prereg-pretp1-be-floor-isolated-2026-08-02.json`,
commit `5dda3acf`, git-provably predates the runner commit `6ae876bc`) with 3 cells
(P1=0.30/P2=0.50/P3=0.70 arm_pct, ascending, each a ONE-key change vs CONTROL -- cleaner than
iteration 3's 3-key cells) and ran it on the SAME frozen 191-trade population, entries UNCHANGED,
exits re-derived through the REAL `exit_manager.plan_exit_actions` core (never
`simulate_trade_real`, 2026-07-09 sim-parity scar). CONTROL reconciled byte-for-byte (0
mismatches vs source), runner-cohort anchor matched exactly (n=35, $15,774.05).

**RESULT: ARM_NOTHING (G4 runner-cohort veto fails uniformly), but the confound-fix is
empirically VALIDATED -- zero knob-isolation violations across all 191 trades x 3 cells.** Every
degraded runner-cohort trade was mechanism (a) pretp1_roundtrip_to_entry (the hypothesis's own
predicted failure mode); ZERO were mechanism (b) post-TP1 lost-trailing-protection -- proving
this knob genuinely cannot leak into post-TP1, unlike iteration 3. Damage is far smaller than
every prior iteration and dose-response is cleanly monotonic-improving: P1(0.30)=-$3,650.45,
**P2(0.50, the named prediction-to-beat cell)=-$905.45** (much closer to neutral than every prior
cell, but the "roughly NEUTRAL-to-positive" prediction was NOT met -- still a real loss),
P3(0.70)=-$459.00. G6 (today's 2026-07-28 Bold incident trade) PASSES for P1/P2 (+$305 swing,
scratch at $0 vs the real -$305 loss) but FAILS for P3 (that trade's +56.5% HWM never reached the
0.70 arm level). G1 aggregate stays negative at every threshold tested.

**This closes the profit-lock-mechanism axis for good, per the pre-reg's own arming_rule.** Four
iterations (1-2 trailing-mode, 3 confounded-fixed-mode, 4 cleanly-isolated-BE-floor) have now
tested every meaningful pre-TP1 profit-lock shape and all four fail the runner-cohort veto at
every threshold tried. The queue item's own fallback fires: **next candidate is
THETA-NOT-GIVEBACK** (hold-time/underlying-stall class, already filed alongside this item) -- a
premium-space mechanism cannot beat theta decay on a still-live 0DTE thesis; the next axis must
be TIME-space or UNDERLYING-space, not another profit-lock variant.

**Guard + RED-proof:** 8 new tests in `automation/state/fleet/test_exit_manager.py` (RED-proofed
by hand -- temp-disabled the mechanism with a literal `False and`, 3 tests failed with the exact
expected assertion, restored, 63/63 green). 21 new tests in
`backtest/tests/test_pretp1_be_floor_isolated_ab_2026_08_02.py`, including a hard
`total_knob_isolation_violations == 0` RED-proof pinned directly against the shipped scorecard.
Full regression sweep (`test_be_floor_ab_2026_07_29.py` + `test_exit_armscope_ab.py` +
`test_exit_manager_replay.py` + `test_exit_manager_walk_stage_labels.py` +
`test_exit_manager_walk_entry_bar_convention.py` + the new file): 98/98 PASS. Curated safety gate
(`run_safety_gate.py`): 59/59 PASS post-ship.

**Zero live-arming action taken.** `pre_tp1_be_floor_arm_pct` stays undeclared in
`strategies.py`'s `RIBBON_RIDE` shape -- fully inert on the live path (same posture as
`profit_lock_arm_scope="full"` before it: expressible, never armed, per the pre-reg's own
arming_rule since no cell cleared G4). Zero `params.json`/`heartbeat_core.py`/`filters.py`/
`strategies.py`/placement edits.

**Commits:** `ad675965` (mechanism + guards), `5dda3acf` (frozen prereg), `6ae876bc` (runner +
guards + scorecard). **Revert (mechanism, if ever wanted):** `git revert ad675965` -- the knob
is purely additive and unreferenced by any live ExitShape, so reverting is a no-op removal, not
a behavior change.

Artifacts: `analysis/recommendations/pretp1-be-floor-isolated-ab-2026-08-02.{json,md}`. Full
narrative + prior-iteration history: `automation/overnight/queue.md`
EXIT-HYBRID-PRETP1-FLOOR entry (closed this fire).

---

## Known broken

- [2026-08-02T03:58:00 ET] DST-FRAME-AUDIT YELLOW :: re-violated 2026-07-02 DST-frame lesson found (fleet_arm_replay.py's first draft independently re-hit it, self-fixed before commit `151123a2`); shared OPRA loader still un-normalized, several consumers (simulator_credit.py/simulator_debit.py/exit_manager_walk.py, no `frame` param) trust callers blindly. PIVOT-PREMIUM-SELLING-SCORECARD.md LEAD-cell OOS expectancy overstated +$23.03 vs corrected +$15.30/tr (-33.6%) -- verdict unchanged (already DEAD/LEAD-not-EDGE, reinforced not flipped). bold_fullhist_replay.py anchor validation mechanism confirmed live but 0/7 current anchors are winter-dated (no numeric corruption today; will bite the first winter real fill). No live knob touched. Guard shipped + RED-proofed (3 new tests, test_graduated_guards.py). Full detail: analysis/deep-research/DST-FRAME-BLAST-RADIUS-2026-08-02.md :: re-run: cd backtest && python -m pytest tests/test_graduated_guards.py -k dst_frame -v

## [2026-08-02T03:52:00 ET] conductor: OK -- ENTRY-CROSS-BUFFER-REDUCTION-SHIP -- commit `415c2f9a`

**Signal J wakes to (OP-25).** Shipped the validated `entry_cross_buffer` reduction (0.03 ->
0.015) that `analysis/deep-research/ENTRY-EXECUTION-COST-2026-08-02.md` measured and
pre-registered (`analysis/recommendations/entry-buffer-reduction-prereg-2026-08-02.json`,
commit `78979314`, git-provably predates its own runner commit `cb30dcd2`) but could not
apply -- that lane's own DO-NOT-TOUCH scope explicitly excluded `params.json` /
`aggressive/params.json`. This lane owned exactly the ship: inheritance trace, the 2-file
edit, guard + RED-proof, execution verification, and a real display bug the ship's own
regeneration caught and fixed en route.

**Inheritance trace (traced by reading the actual code, not assumed -- this was the whole
reason this was its own separate task):** core safe-2/bold-2 load params RAW off disk
(`heartbeat_core.py:1143-1144`, `json.loads(cfg["params"].read_text())`, NO merge layer) --
safe-2 reads `automation/state/params.json`, bold-2 reads
`automation/state/aggressive/params.json`. Fleet arms (safe-3/risky-1/risky-3) resolve via
`fleet_executor._params_for(arm)` = the SAME two base files (`_base_params_for`, routed by
id prefix: `bold`/`risky*` -> aggressive params, else -> safe params) with the arm's own
`accounts.json` `params_patch` shallow-merged on top -- confirmed programmatically that NONE
of the 6 arms' `params_patch` blocks set `entry_cross_buffer`, so every arm inherits the base
file unpatched. `build_shared_signal.py` does NOT read this key (grepped clean across the
whole repo -- it's a signal PRODUCER, never a price consumer; `entry_manager.py` mentions the
mechanism in its own docstring but is SHADOW-ONLY, not imported by either live placement
path). Net: exactly 2 files cover all 6 arms (5 active + retired safe-1) -- matching the
research lane's own stated recommendation, now confirmed correct by tracing every hop.

**Shipped:** `entry_cross_buffer: 0.015` + a full-provenance `_entry_cross_buffer_doc`
sibling (prior-value history, measured $1,422 cost, every A/B gate, why 0.01 was tested and
rejected, frozen kill criterion, one-line revert) into BOTH `automation/state/params.json`
and `automation/state/aggressive/params.json`.

**Verified BY EXECUTION, not assertion** -- loaded every active arm's REAL resolved params
through the REAL production functions and fed the REAL `fleet_broker.marketable_limit_price`
(only the network boundary stubbed):

| arm | execution | source | buffer | entry_px (ask=$1.00) |
|---|---|---|--:|--:|
| safe-2 | mcp_heartbeat | params.json | 0.015 | 1.01 |
| bold-2 | mcp_heartbeat | aggressive/params.json | 0.015 | 1.01 |
| safe-3 | fleet_rest | fleet_executor._params_for | 0.015 | 1.01 |
| risky-1 | fleet_rest | fleet_executor._params_for | 0.015 | 1.01 |
| risky-3 | fleet_rest | fleet_executor._params_for | 0.015 | 1.01 |

All 5 active arms confirmed shipped; retired safe-1 also resolves 0.015 (informational only
-- `status=retired` gates it out of live dispatch everywhere). ZERO arms still resolve the
stale bare 0.03 default.

**Bug found and fixed en route (OP-0 -- fix then report, don't ask):** the FIRST
`engine-contract.md` regeneration rendered `entry_cross_buffer ($0.01)` -- wrong. Root cause
in one sentence: `f"{0.015:.2f}"` formats off the binary float's TRUE value (0.015's nearest
IEEE-754 double is ~0.01499999999999999944, a hair under 0.015), so naive 2-decimal
formatting rounds DOWN to "$0.01," silently understating a genuine half-cent buffer by a full
cent on the one human-facing "what is the engine actually doing" card. Verified this is
COSMETIC ONLY, not a pricing bug: spot-checked all 4 real 0.015-buffer `candidate_limit`
values (plus all 13 real 0.01-buffer ones) in `entry-buffer-reduction-results-2026-08-02.json`
against `round(ask_decision + buffer, 2)` -- 17/17 exact matches, proving production's
`marketable_limit_price` uses the IDENTICAL `round()` idiom as the pre-registered study, so
the measured $853/$678 evidence already reflects this exact rounding behavior; nothing about
the shipped economics changed. Fix: added `engine_contract._money()` (builds a `Decimal` from
`str(x)`, sidestepping the binary-float artifact) and repointed the one call site that renders
this key (`setup/scripts/engine_contract.py`). 2 new guard tests pin it.

**Guard + RED-proof:** new `backtest/tests/test_entry_cross_buffer_shipped_2026_08_02.py`
(10 tests) -- pins 0.015 in both files, asserts the doc siblings exist with before/after
values + an explicit revert instruction, asserts 0.01 is NOT shipped (tested and rejected --
would have missed the 2026-07-31 anchor trade), asserts no arm's `params_patch` silently
overrides the key, the per-arm execution-mechanism proof above, the absent-key-falls-back-
to-0.03 one-line-revert contract, the `build_shared_signal` non-consumer check, and the 2
`engine_contract._money()` formatting-bug tests. RED-PROOFED BY HAND (never `git stash` --
L238): reverted both keys via Edit back to their exact pre-ship bytes, re-ran the suite --
**4/8 failed with the exact expected mechanism-level errors** (e.g. `bold-2:
marketable_limit_price returned 1.03, expected 1.01 ... Resolved buffer for this arm was
0.03`), re-applied the edits, back to green (now 10/10 with the 2 formatting tests added).

**Suites run:**
- Curated safety gate (`backtest/tests/run_safety_gate.py`): **59/59 PASS**.
- `test_params_consumer_reconciliation.py`: 3/4 PASS. The 1 failure
  (`test_known_dead_allowlist_shrinks_only`, re: an UNRELATED key `bid_ask_spread_max_cents`)
  is PRE-EXISTING and NOT caused by this ship -- traced directly to `setup/scripts/
  heartbeat_core.py` sitting dirty with a DIFFERENT concurrent lane's uncommitted 156-line
  WIP (confirmed via `git diff --stat`, and explicitly this lane's own DO-NOT-TOUCH file).
  `test_no_new_dead_params_knob` -- the specific sub-test that would catch MY key if it were
  a new dead knob -- **PASSED**. Not fixed here: not mine to fix, belongs to whichever lane
  owns that WIP when it commits. Flagged below, not silently swallowed.
- `test_engine_contract_drift.py`: 5/5 PASS after regeneration (the regen also silently
  absorbed an UNRELATED pre-existing drift -- `accounts.json`'s risky-1 `gate_override`
  changed to `full_send` on 2026-07-31 without a card regen since; both fixed by the same
  deterministic regenerate, verified neither touches the dirty `heartbeat_core.py`'s WIP --
  only its untouched `_SETUP_EXIT_OVERRIDES` constant is read, confirmed via diff).
- `test_entry_execution_cost_2026_08_02.py` + `test_entry_buffer_reduction_ab_2026_08_02.py`
  (the research lane's own 38 guards), `test_money_path_2026_07_01.py`,
  `test_min_entry_premium_floor.py`: all PASS, zero regressions.
- `test_nbbo_capture_2026_07_20.py`: 2 tests broke on first run (hardcoded the bare 0.03
  default via a module-level params load, computed BEFORE this ship existed) -- fixed by
  pinning those 2 tests to an explicit local `entry_cross_buffer=0.03` override, matching the
  file's own established pattern (`test_nbbo_respects_custom_entry_cross_buffer`). 5/5 PASS
  after the fix.
- Full `automation/state/fleet/` test directory: **330/330 PASS**, zero regressions.
- Full `backtest/tests/` (minus 5 pre-existing collection errors traced to a DIFFERENT
  concurrent lane's dirty `backtest/lib/option_pricing_real.py` + `exit_manager_walk.py` --
  both also DO-NOT-TOUCH): kicked off as bonus due diligence beyond this task's explicit
  ask, running in the background: will fold in a follow-up note if it surfaces anything the
  targeted sweeps above missed (unlikely given the scope of this change).

**Kill criterion (frozen in the doc siblings):** over the next n>=10 real fills OR 10 trading
sessions post-ship, if the buffer's realized net P&L reads worse than the 0.03 baseline,
REVERT.

**Revert (one line, byte-identical):** delete `entry_cross_buffer` + `_entry_cross_buffer_doc`
from both params files -- `params.get()`'s bare code default (0.03) takes over immediately,
next tick, no restart needed.

**Out of scope, correctly left alone:** `setup/scripts/heartbeat_core.py`,
`backtest/lib/option_pricing_real.py`, `backtest/lib/exit_manager_walk.py` -- all 3 carry a
DIFFERENT concurrent lane's uncommitted WIP; touching any would clobber that lane's work.
`exit_manager.py`, `exit_actuator.py`, `crypto/lib/strike_selection.py`,
`backtest/lib/filters.py`, `journal/gex-archive/` -- untouched per this task's own
DO-NOT-TOUCH list (none are consumers of this key anyway, confirmed by grep). `entry_manager.py`
read-only (shadow-only tool, not a live consumer).

**Validation:** `git status --porcelain` on the touched set shows exactly 6 files: 2 params
JSON, 1 regenerated doc, 1 renderer fix, 1 existing test file fixed, 1 new guard test file.
Revert: `git revert <this commit>` (single pathspec commit).

## [2026-08-02T02:05:14 ET] conductor: OK -- WF-GATE-QUEUE-CLOSURE-AND-ESCALATION -- commit pending

**Signal J wakes to (OP-25).** Budget PASS ($8.03/$30, 2/4 fires before this one), market-hours
gate PASS (Sunday 02:05 ET). Engine health GREEN (all critical checks green, weekend-quiet).
Self-check GREEN 0 problems. Self-audit gaps: nothing new since 2026-08-01 batch (already
fully triaged by the 01:07 ET fire). Priority-4 queue scan found two stale HIGH items.

**Found:** `WF-GATE-STRUCTURALLY-NULL` (filed 2026-07-15) and `WF-GATE-REDESIGN-METHODOLOGY`
(filed same week) were both fully **shipped the SAME NIGHT they were filed** (2026-07-16 --
`WF-GATE-METHODOLOGY-2026-07-16.md`, the Option-B A/B-delta-WF methodology note, plus both
named retro-application consumers run that night: Bold ATM strike cell and risky-3 nearer
strike table, both `bold-strike-axis-deltawf-readjudication-2026-07-16.{json,md}`) but were
**never marked done in queue.md** -- same "shipped but the ticket stayed open" class as prior
J-INTENT-EXECUTOR / TRENDLINE-FIXES closures, and a lesson (`2026-07-23-stale-queue-checkbox-
work-done-ticket-open.md`) already exists for this pattern. Closed both with evidence-quoted
`CLOSED ... status:done, superseded by WF-GATE-METHODOLOGY-2026-07-16.md` notes (verified the
artifacts exist and reproduce, not re-derived) rather than leaving them to keep re-surfacing
as "not started."

**Also found, while closing the loop:** a genuine still-open item underneath these two --
`WEEKEND-METHODOLOGY-REVIEW` (filed 2026-07-17, "regime-matched vs calendar-year IS window for
delta-WF", explicitly flagged by its own filing as needing adversarial review to avoid
methodology-shopping) sat **16 days unactioned and un-escalated**. Per this prompt's own rule
("hard calls escalate, they don't get guessed") this should never have been left as a plain
bullet for a Sonnet-tier fire to quietly decide or ignore. Filed it properly as
`## FABLE-ESCALATION: WF-GATE-REGIME-MATCHED-IS-WINDOW` in queue.md with the full carried-
forward evidence (the 3 same-shape INSUFFICIENT_REGIME_SHIFT parks, the methodology note's own
"folds too thin" rejection of rolling-origin at the time, and the specific ruling question) so
the next top-tier/interactive session has a running start, not a blank page. Cross-referenced
the stale `BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL` item's now-dangling "still-open WF-GATE-
STRUCTURALLY-NULL" citation to point at the correct current artifact instead.

**Validation:** zero trading-path files touched (pure `automation/overnight/queue.md` prose
edits + this STATUS.md entry). Ran the queue-parser guard suite
(`test_task_scorer.py` + `test_task_scorer_multiline_status.py`, 20/20 green) and
`task_scorer.py --top` live against the edited file to confirm the multi-paragraph edits
don't trip the known multiline-status/paren-drop parser foot-guns (L245/L246) -- parses clean,
top pick unchanged (`TWIN-DOCTRINE-FIRST-DEPLOY`, a separate pending-J CLAUDE.md doctrine
proposal, untouched this fire). Revert: `git revert <this commit>` (additive prose only,
nothing depends on the new closure/escalation text).

## [2026-08-02T01:07:00 ET] conductor: OK -- SELF-AUDIT-GAP-EXTRACTION-TRUNCATION-FIX -- commit `5e4cd6e2`

**Signal J wakes to (OP-25).** Budget gate PASS ($0.77/$30, 1/4 fires used before this one),
market-hours gate PASS (Sunday 01:07 ET). Engine health GREEN (all critical checks green,
weekend-quiet as expected). Priority order: fill-funnel check clean (self-check-last.json
GREEN, no session expected), no Engine RED, checked self-audit gaps next (priority-3) --
found the organ itself was broken.

**Root cause named in one sentence:** `self_audit.py`'s SYNTHESIS-bullet harvest (unlike
the perspective bold-lead-in harvest) grabbed the whole bullet line verbatim -- including
markdown bold LABEL prefixes like `**Most rigorous view:**` -- then hard-truncated at a raw
`[:120]` character slice, cutting mid-word/mid-sentence. The last two self-audit batches
(2026-07-31, 2026-08-01, both un-triaged) landed in `new-gaps-flagged.md` as unreadable
fragments ("Dashboard WS8 trendline data", "No alert fires", synthesis bullets cut off
mid-sentence) -- exactly the C7 silent-noise-in-a-self-improvement-loop class this organ
exists to prevent.

**Fix:** strip a leading bold-label prefix (`_strip_bold_label`) and soft-truncate at the
last word boundary <=240 chars with an explicit `[...]` marker (`_soft_truncate`), replacing
the raw mid-word 120-char slice. 3 new guard tests in `test_self_audit_extract.py` reproduce
the exact observed fragments; RED-proofed by temporarily stashing the fix (both new tests
fail without it, confirmed via `git stash`/`pop` on just that file) -- 63/63 green with the
fix applied. Zero trading-path files touched (pure tooling fix to the gap-finder script).

**Disposition of the 2 stale un-triaged batches:** both (2026-07-31 6 gaps, 2026-08-01 7
gaps) are now understood as a MIX of genuinely terse-but-real perspective gaps (survive
unaffected -- e.g. "OPRA backfill completeness", "FleetExecutor idempotency guard") and
truncation artifacts from the now-fixed synthesis path (no action needed on the historical
lines themselves -- they're already logged/deduped by hash in `gap-log.jsonl`; the fix only
prevents recurrence on the NEXT self-audit run). No further action needed this fire on those
two specific batches -- marked triaged below in `new-gaps-flagged.md`.

Committed via `commit_scoped.py` (pathspec-scoped: `setup/scripts/self_audit.py` +
`backtest/tests/test_self_audit_extract.py` only -- did NOT touch the large set of unrelated
already-modified state/analysis files sitting dirty in the tree from other autonomous
processes). Revert: `git revert 5e4cd6e2` (additive-only fix + tests, nothing else depends
on the changed truncation/label behavior).

## [2026-08-02T00:08:02 ET] conductor: OK -- ZERO-FOR-TWELVE-POSTMORTEM -- closed the historical-OOS(2026) day-cluster half. Re-ran vwap_continuation + vix_regime_dayside's own byte-identical detectors over the 2026 OOS window (through 2026-07-22, detection-only, $0, 1.8s): vix_regime_dayside's 34 OOS signals are 94.1% (32/34) the SAME (date,side) as vwap_continuation's 61 OOS signals -- confirms + quantifies a caveat already on record (vix_regime_dayside.json "L174 NOT INDEPENDENT ... subset of vwap_continuation") but never measured until now. Pooling by (date,side) collapses the naive 95-signal sum to 63 distinct trials (-33.7%). Reframes (does not reverse) the 07-25 disarm: the live 0-for-12 was never 12 independent trials, at BOTH the live-sample layer (closed 07-25, 4 distinct day+side buckets) and now the OOS-validation layer. Artifacts: `backtest/tools/zero_for_twelve_oos_day_cluster_2026_08_02.py` + `analysis/recommendations/zero-for-twelve-oos-day-cluster-2026-08-02.json` + guard `backtest/tests/test_zero_for_twelve_oos_day_cluster.py` (3/3 green, golden-pinned). Lesson filed: `_lesson-inbox/2026-08-02-oos-signal-populations-can-silently-overlap-across-setups.md` (candidate graduation: canonical `pooled_distinct_trials` helper next to probe_stats.py, flagged not built). Zero trading-path touched. Curated safety gate 59/59 PASS. Revert: `git revert <this commit>`. **Autonomy metric: trend=regressing** (function_score_avg 23.7 over 20 fires -- `enters_last_trading_day`/`fills`/`orders_accepted` all 0 on 2026-08-01, a Saturday with no session; the metric's own `function_latest` is date-anchored to the last CALENDAR day not the last TRADING day, so a weekend read always looks regressed -- next weekday fire should confirm whether this is a metric-scope artifact or a real funnel gap (STAGE 1 fill-funnel check takes priority next fire either way).
## [2026-08-01] LICENSE-MONITOR (deploy-timing for WP-5/6/8/0)

> - #1 ATM (Safe-2)=YELLOW(ELIGIBLE); #1 ATM (Bold)=YELLOW(ELIGIBLE); #2 ATM=YELLOW(ELIGIBLE); #4 ATM=YELLOW(ELIGIBLE)
> - **Trade-to-learn cumulative (since arm, real fills, Rule-9 visibility-only):**
> -   bollinger_squeeze (armed 2026-07-02): since-arm 6tr $+36.00 ($+6.00/tr, 50.0% WR) [4d/4 day+side buckets -- 6 rows are NOT independent trials]
> -   double_bottom_base_quiet (armed 2026-07-01, 31d ago): 0 fills since arm — no live signal yet
> -   vwap_reclaim_failed_break (armed 2026-07-01): since-arm 2tr $-15.00 ($-7.50/tr, 50.0% WR)
> -   WARNING CORRELATED: 2026-07-28 side=P fired in BOTH bollinger_squeeze+vwap_reclaim_failed_break -- same underlying day-call, not independent
> - Files: `automation/state/license-monitor-last.json`, `backtest/autoresearch/license_monitor.py`.

---

## [2026-08-01] RECENCY-CONFIRMATION (confirm-before-capital gate) — RED-BLOCKED on the freshest 25 trading days (2026-06-26..2026-07-31), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-07-31). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=YELLOW; #1 ATM (Bold)=YELLOW; #2 ATM=YELLOW; #4 ATM=YELLOW
> - **Books:** Safe2_ATM_1+2+4=RED ($-370.08); Bold_ATM_1+2=YELLOW ($-166.9)
> - **edges_confirmed_on_recent = False** (any RED=True). All live tiers still small-n / not-yet-confirmed on the freshest weeks — full-OOS-2026 base remains the larger-n companion read; HOLD capital scaling until an edge CONFIRMs. RED-BLOCKED: Safe2_ATM_1+2+4 — no live flip on these.
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## [2026-08-01T22:00:28 ET] conductor: QUIET -- nightly budget spent (13 fires today >= max_fires 4, conductor_budget.py exit 3). Zero model work this fire per rail-0. Next fire (per schedule) resumes normally once the daily counter resets.

## [2026-08-01T20:30:43 ET] conductor: QUIET -- nightly budget spent (12 fires today >= max_fires 4, conductor_budget.py exit 3). Zero model work this fire per rail-0. Next fire (per schedule) resumes normally once the daily counter resets.

## [2026-08-01T18:00:05 ET] conductor: QUIET -- nightly budget spent (11 fires today >= max_fires 4, conductor_budget.py exit 3). Zero model work this fire per rail-0. Next fire (per schedule) resumes normally once the daily counter resets.

## [2026-08-01T16:15:02 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-01 -- 0 GREEN / 0 YELLOW / 0 RED / 6 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | NOT_EXERCISED | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | no core-decisions.jsonl ticks dated 2026-08-01 -- no RTH session evidence (non-trading day or engine idle). |
| WS6 regime stamp | NOT_EXERCISED | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | 2026-08-01 is not a weekday -- Gamma_Premarket/Gamma_RegimeStamp do not fire on weekends. |
| WS3 level hysteresis | NOT_EXERCISED | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | no core-decisions.jsonl ticks dated 2026-08-01. |
| WS11 core recency | NOT_EXERCISED | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-01 window_end=2026-07-31 (baseline window_end=2026-07-31, advanced=False). bear now: RED n=10 (delta +0 vs baseline n=10) exp=$-60.9/tr, verdict_moved=False. bull now: UNDERPOWERED n=1 exp=$-295.0/tr. live refresh attempted=True ok=True. |
| Theta cockpit | NOT_EXERCISED | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | no core-decisions.jsonl ticks dated 2026-08-01 -- non-trading day. |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-01 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-01`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## [2026-08-01T15:14:40 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-01 -- 0 GREEN / 0 YELLOW / 0 RED / 6 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | NOT_EXERCISED | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | no core-decisions.jsonl ticks dated 2026-08-01 -- no RTH session evidence (non-trading day or engine idle). |
| WS6 regime stamp | NOT_EXERCISED | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | 2026-08-01 is not a weekday -- Gamma_Premarket/Gamma_RegimeStamp do not fire on weekends. |
| WS3 level hysteresis | NOT_EXERCISED | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | no core-decisions.jsonl ticks dated 2026-08-01. |
| WS11 core recency | NOT_EXERCISED | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-01 window_end=2026-07-31 (baseline window_end=2026-07-31, advanced=False). bear now: RED n=10 (delta +0 vs baseline n=10) exp=$-60.9/tr, verdict_moved=False. bull now: UNDERPOWERED n=1 exp=$-295.0/tr. live refresh attempted=True ok=True. |
| Theta cockpit | NOT_EXERCISED | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | no core-decisions.jsonl ticks dated 2026-08-01 -- non-trading day. |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-01 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-01`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## [2026-08-01 14:43 ET] NULL (deliverable) -- WEEKEND-TWELVE Next-Twelve #7: shelf bistability SOURCE-FIX A/B -- hysteresis-only STANDS

**All 3 source-fix arms unanimously FAIL the pre-registered steady-state-fidelity gate; WS3's
hysteresis (`114a7a6b`) is not just a stopgap -- on this evidence it is currently BETTER
calibrated than any of the three natural source-level alternatives.** `daily_context.py` /
`refresh_levels_intraday.py` untouched (git diff empty, guard-pinned).

- **Mechanism named + reproduced:** `daily_context._merge_shelf_candidates` re-derives shelf
  zones every 5-min refresh with today's still-forming daily bar as both seed and
  touch-counter; concrete flip quoted (2026-07-31 09:43->09:48 ET, forming-bar low
  $742.79->$741.98, ONE ordinary 5m bar, no level broken) with exact candidate touch counts,
  validated 81.8% (63/77 fires) against the real observed production A/B sequence.
- **Prereg-first, git-provable:** prereg `07697c7d` (et_clock 14:23:21, BEFORE runner) ->
  runner `52a26e91`. Full 391-day population, real SIP daily bars (fetched fresh) + real
  5m SPY/OPRA, 77 simulated fires/day, REAL unmodified `_hysteresis_carry` driven over each
  arm. $0, pure Python, 63.5s runtime.
- **All 3 arms (ARM_A incumbent-tie-break, ARM_B exclude-forming-bar, ARM_AB both) cut
  flicker hard** (written flips -25% to -83% full-pop, -41% to -91% recent-25) **and improve
  proxy entry-population real-OPRA P&L** (+$1,438 to +$4,442 full-pop, all positive
  recent-25) **-- but ALL THREE fail steady-state fidelity:** 198-276/391 days (51-71%) show a
  level whose end-of-session identity permanently differs from baseline, median $0.52-0.58.
  By 15:53 ET today's forming bar is real, completed price action -- baseline legitimately
  uses it as a tie-break; every tested arm's "stability" mechanism resolves the same contested
  regions toward a DIFFERENT stable point instead. Structural trade-off, not a single-arm bug.
- **Guard suite (6 tests, RED-proofed) caught a real bug before any number was trusted:**
  ARM_A's first-draft incumbent match used band-overlap (too loose in a contested region --
  every candidate overlaps every other there by definition), silently defeating the tie-break;
  fixed to mid-within-$0.10 identity (reuses `HYSTERESIS_MATCH_EPS`, zero new magic numbers),
  full population re-run post-fix.
- Artifacts: `analysis/recommendations/shelf-bistability-2026-08-01.{md,json}` + prereg.
  Runner: `backtest/tools/shelf_bistability_source_fix_2026_08_01.py`. Guards:
  `backtest/tests/test_shelf_bistability_2026_08_01.py` (6/6 green).

---

## [2026-08-01 14:32 ET] SHIPPED -- WEEKEND-TWELVE Next-Twelve #3: shared-index absorption guard + 2 WS4 lessons (Next-Twelve #12 lesson half)

**Guard shipped, not just proposed.** 5 confirmed shared-index-absorption incidents in one
night (`482a662a`, `da18da34`, `a363bd5f`, `be9c1b58`, `90fd1e40` -- full per-incident detail
in `strategy/candidates/_lesson-inbox/2026-08-01-shared-index-absorption-between-parallel-lanes.md`)
close with a helper + a fail-open hook tripwire, both guard-tested and RED-proofed.

- **`setup/scripts/commit_scoped.py "<message>" <path> [<path>...]`** -- pathspec-scoped
  add+commit (`git add -- <paths>` then `git commit -m <msg> -- <paths>`). Empirically
  VERIFIED, not assumed: `git commit -- <paths>` makes git build a TEMPORARY, pathspec-scoped
  index for the duration of the commit (hooks included -- confirmed by inspecting
  `GIT_INDEX_FILE` in an isolated sandbox repo: it points at a `.git/next-index-*.lock`
  file, and `git diff --cached` inside the hook sees ONLY the named paths), so a foreign
  staged file is structurally invisible to a scoped commit, not just conventionally
  excluded. A bare `git commit` has no such scoping -- confirmed the same sandbox reproduces
  the absorption bug on demand when no pathspec is given.
- **`setup/git-hooks/pre-commit` extended** (found via `setup/install-git-hooks.ps1` +
  `backtest/tests/run_safety_gate.py` -- did NOT replace either), new WARN-ONLY, fail-open
  tripwire: if the staged set at commit time spans more than one top-level directory group,
  print a loud stderr warning pointing at `commit_scoped.py` and append a line to
  `automation/state/commit-scope-warnings.jsonl`. Never blocks -- verified exit 0 in every
  tested scenario. Adds negligible time (pure shell/git-plumbing, no python startup); full
  curated gate re-measured 7.3-8.8s before and after this addition, consistent with normal
  run-to-run noise.
- **Guard test `backtest/tests/test_commit_scoped.py`** -- 9 tests, real throwaway-git-repo
  fixtures (same pattern as `test_verify_committed.py`). RED-proofed by hand: temporarily
  reverted the helper's commit step to a bare `git commit` -- 5/9 tests failed with the
  foreign file visibly swept into the commit (the exact bug, reproduced on demand);
  restored, 9/9 green. **Deliberately excluded from the curated per-commit gate** (measured
  cost across 2 A/B runs: 7.3-8.5s -> 12.6-13.1s with it added, +4.5-5s -- breaks the gate's
  own "keep FAST, every commit" contract even though it is the same shape as the
  already-curated `test_verify_committed.py`). Still runs under `--full` / CI. Documented
  inline in `run_safety_gate.py` with the measured numbers so a future session doesn't add
  it reflexively without re-measuring.
- **Real bug caught mid-build, before it ever touched the live repo:** the hook's first
  draft used a shell variable literally named `GROUPS` for the top-level-directory count --
  collides with bash's special read-only `GROUPS` builtin (the current user's Unix group-id
  list). Assignments to it silently no-op per the bash manual, so the count always read back
  as a constant (197609 on this box, the real GID) regardless of actual input, which would
  have made the tripwire fire on EVERY commit unconditionally -- noise indistinguishable
  from signal, worse than not shipping it. Caught via isolated sandbox-repo testing (4
  scenarios: bare 1-dir no-warn, bare 2-dir warn, pathspec-scoped multi-dir
  warn-but-no-foreign-sweep, live absorption repro) before touching the real hook; fixed by
  renaming to `N_TOPDIRS` and switching to pure `set --`/`$#` shell builtins (no `wc` /
  second `sort` at all), re-verified correct across all 4 scenarios against the actual
  installed hook.
- **3 lesson-inbox items filed:**
  `2026-08-01-shared-index-absorption-between-parallel-lanes.md` extended from its original
  1 incident to all 5 + the shipped fix (was "candidate for a graduated guard," now built);
  plus WS4's 2 lessons named in the WEEKEND-TWELVE synthesis (Next-Twelve #12) --
  `2026-08-01-filters-py-demerit-vanishes-under-raw-disable-filters.md` (`filters.py:1653-1664`'s
  trendline demerit only charges `if 5 in blockers`, so a raw `disable_filters=[5]` silently
  un-demerits a trendline-only setup -- disclosed in WS4's own output, verdict unaffected)
  and `2026-08-01-frozen-cache-view-required-during-concurrent-backfill.md` (WS4's
  `freeze_contract_cache` fix for a concurrent OPRA backfill mutating the shared contract
  cache mid-study -- same shared-mutable-state-race family as the git absorption bug, one
  layer down the stack).
- **Known limitation, disclosed not hidden:** incident 4 (`be9c1b58`) is a same-FILE
  concurrent-edit case (two lanes editing different lines of `SCHEDULED-TASKS.md` inside the
  same commit) -- pathspec-scoped commit does NOT fully close this sub-case, since the
  working-tree file itself may already carry both edits before either session stages it.
  Documented as an open gap in the extended lesson item, not oversold as solved.
- **Doctrine pointer added:** `markdown/doctrine/fable-judgment/03-EXECUTION.md` E3 (already
  named this class of bug from an earlier collision, pointed only at a bare
  `git commit --only` flag with no standing tooling behind it -- now points at the concrete
  helper + hook).

Zero trading-path files touched. Rail: doctrine/tooling only (a git hook + a repo-ops
script + its guard test + 3 lesson-inbox docs + one markdown doctrine pointer) -- no
`params.json` / `heartbeat_core.py` / `filters.py` production semantics changed (the
filters.py demerit finding is DISCLOSED-ONLY per WS4's own already-NULL verdict, nothing
touched here). Revert: `git revert <this commit>` (single pathspec commit, made via
`commit_scoped.py` itself as this fire's own smoke test).

## [2026-08-01 13:21 ET] NULL (deliverable) -- WS4 (WEEKEND): PAIRED RIBBON A/B -- the ribbon question is now CLOSED BOTH WAYS

**The only honest "loosen the ribbon" left -- relax filter 5 at ENTRY + suppress ribbon_flip_back
at EXIT for level-anchored setups, ONE paired pre-registered change -- is NULL.** Prereg frozen
12:43 ET + committed `e5e323f2` BEFORE the runner existed (git-provable); runner `4814e6bb`;
results `96ae89bb`. Population 394 frame dates (= 391 full sessions + 3 half days, disclosed),
real OPRA only, entry+1, real exit_manager walks.

- **Gates:** G1 recent25 **+$57.00 PASS-but-UNDETERMINED** (4 of 7 recent added entries
  unpriceable -- sign not fully measured) | **G2 FAIL** (recent 1 improved/1 worsened; full-window
  7/14 -- the majority of changed days get WORSE) | **G3 FAIL** (recent delta minus best single
  contribution = **-$498.50**; the entire recent positive is ONE +$555.50 trade) | G4 PASS
  (runner cohort 42/$20,184 vs control 39/$18,330 -- grew, zero-tolerance met) | G5 PASS
  (23 added, 3 recent, **16 exit-lever fires** -- both levers fired; L243 satisfied).
- **The mechanism answer (the real payload):** the filter-5 block-set **loses money even under
  its best-shot exit regime** -- added cohort n=23, WR 26.1%, -$21.30/trade (-$489.85 total).
  The suppression itself nets **-$109.45 over its 16 fires**: 11 freed trades die BIGGER at the
  structure stop (-$982) vs 3 that become runners (+$1,339). The +$500.65 full-window delta is
  pre-emption luck again (unlocked entries occupy the slot and skip -$990.50 of control losers)
  -- same artifact shape as 07-31. p one-sided: 0.39 full / 0.50 recent.
- **GRAVEYARD (both ways, do NOT retest):** entry-only filter-5 deletion NULL (07-31, round-
  tripped by the ribbon exit) + paired relax-entry-AND-suppress-exit NULL (08-01, the blocked
  cohort is genuinely bad). **Filter 5 -- provenance-free until 07-31 -- now EARNS its keep on a
  two-study evidence trail.** No further ribbon-loosening variants without genuinely NEW
  information (regime break or a structural change to the exit stack).
- **By-catch (disclosed in the JSON):** (a) prereg's primary entry mechanism tripped its own
  HARD INVARIANT twice -> pre-registered fallback (scoped per-bar bypass) engaged; the repro
  under pure production semantics PROVED the invariant-breaker was a sequencing KNOCK-ON
  (2 trendline-only entries reachable only because the book upstream changed), not a gate leak.
  (b) filters.py:1654-57 really does un-demerit trendline-only setups under raw
  disable_filters=[5] -- a crack in the 07-31 ARM_A==ARM_B narrative (verdict unaffected).
  (c) the concurrent OPRA backfill grew the cache 14225->14400 MID-SESSION and use_real_fills
  reads cached premiums at ENTRY (simulator_real:420) -- control drifted 211->212 raw entries
  from coverage alone; fixed with a process-wide frozen cache view so both arms share one truth.
  Guards: `backtest/tests/test_paired_ribbon_suppression_2026_08_01.py` 4/4 green, RED-proofed
  (mutant A exit-core `if True`, mutant B trendline-in-cohort).

## [2026-08-01 13:15 ET] NULL (deliverable) -- WS5 (WEEKEND MAIN EVENT): SHELF_HOLD_RECLAIM full-population study -- "enter on the defense" CLOSED with numbers

**All 4 admission geometries NULL over the verified 391-day population; 0 of 96 cells survive
BH-FDR q=0.10. J's question is answered: entering the DEFENDED TOUCH of a w5 shelf early does
NOT beat the late close-cross, and the dose-response is INVERTED** (exp: C_cross +$0.47 >=
A_wick +$0.29 >> B_hold -$14.79/tr; the grid's strongest raw p, 0.045, belongs to B's LOSS).
Nothing ships, nothing arms; graveyard entry filed in the results doc.

- **Prereg-first, git-provable:** prereg `96a85efc` (et_clock 12:45:56, BEFORE runner) ->
  runner `21b6ba99` -> results. Real OPRA only, entry+1, qty=3, structure stop at zone floor,
  CONTROL(registry byte-asserted)-vs-ZONE-RIDE paired lanes. Frame: et-v2 opt-in (wall-v1
  would inject winter VIX look-ahead + clip the last true hour on 129 EST days; decided
  pre-run, disclosed).
- **Harness fidelity proven, so the NULL is believable:** 3/3 tape anchors live-fire at J's
  exact Friday moments; e1 re-walks to the PENNY vs the broker-validated n=4 tool
  (+$550.75, runner_stop 3.53); on 07-31 itself the lane made +$1,175 -- Friday was real,
  the population says it is not a standing edge.
- **Data completed mid-study:** 117 missing OPRA contracts (30% of July-2026 signals!)
  backfilled via canonical fetch conventions -> re-ran on ZERO exclusions. Pass-1 preserved
  (`.pass1-precache.json`); verdicts identical, but pass-1's recent-25 was materially
  distorted (A: -$137 -> +$1,035) -- the missing contracts were exactly J's called-day class.
- **The one real structure (post-hoc, NOT shipped):** F5 ribbon-stack -- the filter the spec
  demoted -- is the strongest separator, monotone drop<htf<require for A/C
  (C|require: +$5,447/168tr, positive in held-out AND recent-25, p=0.187, BH x). That cell IS
  the `block_elite_bull`-refused ELITE class -> converges with WS1's gap finding: the money
  lane is the GATE RE-QUAL (`bull_gate_atm_ssb_requalification.py`), not a new detector.
  B_hold is negative under every filter mode (mechanism: buys chop at zone floors, theta
  bleeds into ribbon_flip_back exits ~63%).
- **ZONE-RIDE (trail .20) loses to CONTROL (trail .15) on every primary combo** (-$380..-$550)
  -- the n=4 anecdote's ZONE-RIDE edge does not generalize.
- Artifacts: `analysis/recommendations/shelf-hold-reclaim-2026-08-01.{md,json,pass1-precache.json}`
  + prereg. Side-finds: `exit_manager.py` hardcodes label `time_stop_15:50` while enforcing the
  configured 15:40 (mechanism verified; label-only; chip task_30a7b291 filed);
  SCHEDULED-TASKS stated-count 99->100 reconciled in passing (gate fix-forward). Runner-cohort
  untouched by construction (entry-additive; registry exit shape byte-asserted). $0 LLM.


[2026-08-02 05:30 ET] conductor: QUIET — nightly budget spent (4/4 fires used)

### DEGRADED: self-check 2026-08-02T05:39:56
- CANDIDATES-UNTRACKED: 31 untracked files under strategy/candidates/ (threshold 20) -- live chef/kitchen/prospector pipeline state accumulating with no commit history / no disk-loss recovery path. Batch `git add --pathspec-from-file` + commit to clear (see STRATEGY-CANDIDATES-UNTRACKED-BACKFILL precedent, 2026-07-22).


## Kitchen
Kitchen: alive, queue 26 pending, last cook 0 min ago, today $0.00, model=grinder-python
