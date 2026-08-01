## [2026-08-01 12:57 ET] OK -- WS7 (WEEKEND): LIVE WATCH shipped -- the "are we in a trade / what's it doing" surface

**One canonical state surface + two renderers, registered and smoke-fired.** J never has
to ask again: `automation/state/live-watch.json` (rewritten every 1 min, 09:25-16:10 ET
wd) carries, per arm across all 5 active SPY accounts: position (symbol/qty/entry/current
mid), unrealized P&L $ + %, distance to stop AND to the current TP target (from the
engine's own `exit-state.json` -- TP1 flips to runner target after `tp1_filled`),
high-water mark + profit-lock flag, time in trade, last decision verdict+reason+age,
kill-switch state (all 3 breaker vocabularies normalized -- C9), and a READ-ONLY
`theta-clock.json` link-in (the theta lane owns that file; guard asserts mtime untouched).

- **Watcher:** `setup/scripts/live_watch.py` -- standalone, fail-open (raising broker ->
  arm `degraded:`, crashed build -> loud `errors[]`, ALWAYS exit 0), atomic writes,
  market-closed = ONE `state=CLOSED` marker then silence (no-spam RED-proofed live:
  2nd run printed `snapshot already CLOSED -- no write`).
- **Task:** `Gamma_LiveWatch` registered (install-live-watch.ps1): `State=Ready`, weekly
  Mon-Fri trigger + real `PT1M` repetition x6h45m, NextRun 2026-08-03 09:25 ET.
  Smoke-fired through the REAL wscript->pythonw chain, verified by OUTPUT artifact
  (stdout log 0->67 bytes, correct no-spam line), not by `LastTaskResult`.
- **Renderers:** dashboard **Live Watch panel** (`LiveWatchPanel.tsx` + `/api/live-watch`,
  SWR 5s, STALE>3min flag) -- BOTH branches verified rendering in the running dashboard
  (CLOSED live; IN-TRADE via the labeled synthetic snapshot, then restored + re-verified
  CLOSED); `tsc --noEmit` clean. Plus `live_watch.py --brief` compact text for
  Discord/brief use.
- **Proof:** `--dry-run-synthetic` PASS -- all 18 required fields populate on both the
  direct view AND the full assemble_arm path. Guards `backtest/tests/test_live_watch.py`
  23/23 green; 3 RED-proofs executed (CLOSED no-spam, C9 aggressive-breaker mapping,
  broker fail-open: mutate -> FAIL -> revert -> green).
- **MONDAY-VERIFY (2026-08-03):** during the first RTH session with a REAL open position,
  confirm live-watch.json shows non-null mid/uPnL/dist-to-stop/dist-to-TP/HWM/
  time-in-trade for that arm within 2 min of fill, dashboard panel flips to IN TRADE, and
  `--brief` renders the row; if `entry time unknown` appears in arm status, the orders
  lookup needs the fix. $0, no LLM, places nothing.

## [2026-08-01 13:0x ET] NEEDS-J (one click only) -- WS12 (WEEKEND): RESET PREP + TIER NORMALIZATION complete; recommendation = $2,500/arm

**Everything except the dashboard click landed tonight.** The Alpaca paper reset is
dashboard-only (no API); J signs in, the `alpaca-paper-reset` skill drives the clicks.

- **Brief + runbook:** `analysis/deep-research/RESET-PLAN-2026-08-01.md` — live REST
  equities of all 6 accounts (12:35-12:47 ET: safe-2 $1,160.30 / safe-3 $1,967.81 /
  bold-2 $1,197.52 / risky-1 $1,756.87 / risky-3 $2,121.61 / twin $9,826.97, all SPY arms
  FLAT), per-arm tier + floor-clearance + ceiling tables, and the post-reset runbook with
  EVERY verification command dry-run tonight (accounts_status, sizing_deadlock_diag live +
  `--equity 2000/2500`, daily_loss_guard `--rearm --dry-run` both accounts, forced-rearm
  mechanics proven on breaker COPIES).
- **Recommendation: $2,500 per SPY arm, NOT the $2,000 default** — $2,000.00 sits EXACTLY
  ON the half-open [$2K,$10K) tier boundary ($1,999.99 vs $2,000.00 flips ATM→OTM-2 on
  bold_core) and its $2.00 ceiling refuses the $2.01-2.50 top of the typical ATM band;
  $2,500 = every arm cleanly inside [2K,10K), ceiling $2.50, $500 tier-flap buffer.
  Crypto twin NOT reset (evidence continuity + concurrent latency-drill lane).
- **Disclosures (in the brief):** ATM-under-$2K prereg evidence clocks PAUSE (nothing
  waived); full-send fill-rate covariate shifts (annotate reset date); broker-side history
  destroyed per account (local ledgers are the record); kill-switch $ anchors roughly
  double with the fresh SoD; bold-2 multiplier reads 1 again (reconcile pdt_gate_mode
  post-reset, runbook step 5).
- **Guard:** `backtest/tests/test_reset_plan_tier_boundaries_2026_08_01.py` — 10/10 green;
  RED-proofed (mutated the 2K boundary → 3 fails → byte-identical restore → green). A
  future tier edit invalidates the plan loudly.
- **Skill updated** with the chosen targets + runbook pointer.
- **BLOCKED-ON-J:** the dashboard reset click itself, nothing else. Runbook §7 step 1.

## [2026-08-01 12:37 ET] OK -- theta_clock (WEEKEND): THETA COCKPIT built (J directive, verbatim tonight), commit `a363bd5f`

**Signal J wakes to (OP-25).** Built the in-trade Greeks visibility instrument J ordered:
"We can't just be getting in options trades and have Theta kick our ass without us knowing."
VISIBILITY ONLY -- no exit-rule change, no new gate. `heartbeat_core.py` is byte-for-byte
untouched; zero new network calls on the 1-min trading hot path.

**What shipped:**
1. `setup/scripts/theta_clock.py` -- standalone watcher, registered as `Gamma_ThetaClock`
   (every 1 min, 09:30-16:00 ET weekdays, `wscript -> run_exe_hidden.vbs -> backtest-venv
   pythonw`, OP-27 headless stdio redirect, no lock file -- Task Scheduler's own
   `-MultipleInstances IgnoreNew` is the sole overlap guard). Reads open SPY option
   positions for all 5 active accounts (core safe-2/bold-2 + fleet safe-3/risky-1/risky-3)
   via `automation/state/fleet/fleet_broker.py` -- the SAME credential-loading + REST module
   `heartbeat_core.py` itself already depends on (read-only: get_positions,
   get_option_greeks). Writes `automation/state/theta-clock.json` (current snapshot) +
   `automation/state/theta-clock/theta-clock-YYYY-MM-DD.jsonl` (daily time series) +
   `automation/state/theta-clock/position-state.json` (per-position frozen entry snapshot).
   ALERT: when estimated theta burn over the last 15 min exceeds estimated delta gain by
   more than $5, ONE line fires to STATUS.md's NEW "## Live watch" section (created on
   first use -- deliberately not "## Known broken", a stall isn't a breakage), latched
   per-position forever (never repeats). NEVER auto-exits anything.

2. **Empirical finding that changed the design.** Grepped `core-decisions.jsonl` before
   building: the EXISTING G8 per-entry greeks capture (`heartbeat_core._capture_greeks`,
   live since 2026-07-07) has returned `"greeks": {}` on **29/29 real ENTER rows checked,
   zero exceptions**. Its snapshots endpoint is documented as "UNVERIFIED" in
   `fleet_broker.py` and, per this evidence, still is. Rather than build the alert on a feed
   with a 0/29 track record, the headline numbers run on a documented closed-form ESTIMATE
   (model-free intrinsic-value delta component + a textbook sqrt(time-remaining)
   extrinsic-decay heuristic for theta, both labeled `_est` with a `basis` string) computed
   from sources already PROVEN live: the `/v2/positions` payload itself, plus the same
   `/v1beta1/options/quotes/latest` endpoint the live placement path already prices real
   fills with. Real broker greeks are still attempted every tick and preferred when present
   -- zero code change needed the day Alpaca's feed starts returning data.

3. **delta_at_entry / iv_at_entry / theta_at_entry backfill (GO-FORWARD only, as scoped).**
   `fleet_journal_bridge.py` (the `journal/trades.csv` writer, confirmed via grep -- the
   OTHER live writer, `j_intent_journal.py`, already reads the header dynamically and needed
   no change) now populates these three cells at journal-write time: PRIMARY = the G8
   broker-greeks capture threaded through `core-decisions.jsonl`'s `exec.greeks` (for the day
   it's ever non-empty), FALLBACK = `theta_clock.py`'s own first-observation snapshot (within
   ~1 min of fill, per the brief's documented convention). `theta_at_entry` is a NEW 44th
   column (SCHEMA was 43) appended at the END (never inserted mid-schema -- every real
   consumer greps by column NAME, never position) via a one-time, idempotent header-only
   migration (`_ensure_schema_header`); verified old rows keep their original 43 raw values
   and `csv.DictReader` fills the new trailing cell with `None` for them, no misalignment.
   Neither field is ever fabricated -- both stay blank (unchanged from today) when neither
   source has data, rather than writing a model estimate into a column named as if it were
   real broker data (the cited downstream blocker, perps leverage calibration, expects real
   greeks there).

**Weekend limitation handled honestly (market closed, cannot verify against a live
position):**
  (a) 22 guard tests in `backtest/tests/test_theta_clock.py` + 11 new tests in
      `test_fleet_journal_bridge.py` + 6 in the new `test_firm_brief_theta_clock_section.py`
      -- 282/282 green across the full blast-radius set (every test file importing
      `fleet_journal_bridge`/`firm_brief`/`theta_clock`), plus a 6063-test full-repo
      collection-only pass confirms zero NEW import breakage (the 3 pre-existing collection
      errors are unrelated archived/missing-data tests). RED-proofed twice: the alert
      spam-latch (disabled -> fires 8x instead of 1x over the same fixture) and the
      greeks-fallback precedence (disabled -> 4 tests correctly fail).
  (b) A full OFFLINE dry-run against a SYNTHETIC injected position (16+5 simulated 1-min
      ticks, flat underlying) proved the entire pipeline end-to-end: entry snapshot frozen
      on tick 1, 21 daily-JSONL rows written, exactly ONE "THETA STALL" STATUS.md line fired
      (at t+8min, theta burn -$5.60 vs delta gain +$0.00) and never repeated across 12 more
      ticks. Math cross-checked by hand (residual_est = real premium change - delta_est -
      theta_est, verified exact).
  (c) `Gamma_ThetaClock` registered for REAL via `install-theta-clock.ps1` (not just
      written) -- `Get-ScheduledTask`: `State=Ready`, real trigger (`DaysOfWeek=62` =
      Mon-Fri, `Repetition Interval=PT1M Duration=PT6H30M`), action chain verified.
      Smoke-fired via `Start-ScheduledTask` for real -- `LastTaskResult=0`, AND (wscript
      fire-and-forget masks the child's true exit code per the `Gamma_EodFlattenCore`
      lesson, so this alone is never trusted) independently confirmed via the REAL written
      `automation/state/theta-clock.json`: `accounts_checked=[safe-3,safe-2,risky-1,
      bold-2,risky-3]` (all 5 LIVE Alpaca paper accounts queried successfully),
      `accounts_failed=[]`, `n_positions=0` (correct -- market closed), `spot_source=
      sight_beacon` (746.79). stderr log empty.
  (d) MONDAY-VERIFY (checklist, not a hope):
      [ ] `Get-ScheduledTaskInfo Gamma_ThetaClock` shows real fires through the 09:30 ET
          open (`LastRunTime` advancing every ~1 min).
      [ ] `automation/state/theta-clock.json` updates every ~1 min once a real position is
          open, and its `positions[].qty`/`entry_premium` match the broker fill.
      [ ] Confirm whether the Alpaca options-snapshots greeks feed is STILL empty on a real
          fill, or -- if it finally returns data -- confirm
          `theta_per_contract_per_day_source` flips to `broker_snapshot` and
          `journal/trades.csv`'s `delta_at_entry`/`iv_at_entry` populate from the PRIMARY
          path on the next `fleet_journal_bridge.py` run (fires via `firm_brief.py`, twice
          daily).
      [ ] If a real trade genuinely stalls, eyeball the STATUS.md "## Live watch" line for
          sanity (does the $ magnitude look right for the real qty/premium) and confirm it
          fired once, not repeatedly.

**Rail-4 note:** visibility-only. `heartbeat_core.py` is byte-for-byte unchanged -- no
network call added to the hot path, no new gate, no exit-rule change. A theta-based EXIT
class remains a separate, un-built, pre-registered study per J's explicit instruction not to
build one here. Revert: `git revert <this commit>` (additive-only: new script, new
scheduled task, new STATUS.md section; `fleet_journal_bridge.py`'s SCHEMA/`build_row` change
is also additive/backward-compatible -- reverting just stops populating the 3 new-ish cells,
never un-migrates the header, which is harmless since no reader ever depended on column
count).

---

## [2026-08-01 12:00 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (8/4 fires used today), zero model work this fire per rail-0. Next fire: whenever the daily counter resets.

## [2026-08-01 10:00 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (7/4 fires used today), zero model work this fire per rail-0. Next fire: whenever the daily counter resets.

## [2026-08-01 08:00 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (6/4 fires used today), zero model work this fire per rail-0. Next fire: whenever the daily counter resets.

## [2026-08-01 06:00 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (5/4 fires used today), zero model work this fire per rail-0. Next fire: whenever the daily counter resets.

## [2026-08-01 05:30 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (4/4 fires used today), zero model work this fire per rail-0. Next fire: 07:30 ET or later once budget window resets.

## [2026-08-01 05:10 ET] OK -- conductor (WEEKEND): G2-TRENDLINE-BYPASS-INVERTS-PRIORITY decided (NEITHER arm ships, stays default), commit `dbd35729`

**Signal J wakes to (OP-25).** Budget gate PASS ($1.44 of $30, 3/4 fires used before this one),
market-hours gate PASS (Saturday, weekend mode). `TWIN-DOCTRINE-FIRST-DEPLOY` still pending
J's Discord reply on `gp-2026-07-23-twin-doctrine-001` -- nothing new to do there.
`task_scorer.py`'s own priority regex doesn't recognize the `CRITICAL` tag (falls back to LOW
base) so `G2-TRENDLINE-BYPASS-INVERTS-PRIORITY` didn't surface via `--top`, but reading
`queue.md` directly found it: CRITICAL/engine-edge, filed 2026-07-27, a real structural finding
about the live entry gate -- picked it over the scorer's own ranking.

**The finding:** filters.py's 2026-05-09 TRENDLINE-CHOP-ZONE relaxation strips filters
5(ribbon)/8(VIX)/9(volume) ONLY when trendline_rejection fires as the SOLE level-tied trigger --
so a level_rejection/confluence setup (stronger evidence) gets held to the FULL filter set while
the weakest trigger class gets a free pass. Measured 89% of every bear ENTER over 33 sessions
came through this bypass; a live 07-27 example lost $162 on a trendline-only entry that would
have HELD as level_rejection+trendline together.

**What shipped:** pre-registered A/B (`prereg-g2-trendline-bypass-2026-08-01.json`, frozen
BEFORE running) testing 3 scopes via a new `trendline_bypass_scope` flag on
`evaluate_bearish_setup` (filters.py) -- `trendline_only` (default, byte-identical),
`all_level_tied` (ARM_EXTEND -- relief extends to level-tied triggers), `none` (ARM_REMOVE --
bypass deleted). Full-history real-OPRA-fills replay via the real exit_manager
(`backtest/tools/g2_trendline_bypass_ab_2026_08_01.py`, 2025-01-02..2026-07-31, reusing
yesterday's filter5-ribbon-2026-07-31.json scaffold). **Verdict: NEITHER arm clears all 5
frozen gates -- `trendline_bypass_scope` stays at the CONTROL default.** ARM_EXTEND: recent25
delta +$1,616.15 but G1 UNDETERMINED (8/26 recent added entries have no cached OPRA contract --
per the frozen pre-reg, UNDETERMINED = NOT PASS). ARM_REMOVE: recent25 +$279.60 but fails G4
(runner-cohort anchor regression) outright. The asymmetry is CONFIRMED real (verified in the new
guard test's own assertions) but NOT actionable without more OPRA coverage in the exact window
that matters -- same coverage gap `filter5-ribbon-2026-07-31.json` flagged the prior night.

**Process catch (OP-33, disclosed not swept under the rug):** the study's FIRST run scored
ARM_EXTEND as `SHIP_CANDIDATE` -- a bug in `relabel_g1_measurability` changed the G1 STATUS
LABEL to "UNDETERMINED" without forcing the underlying `pass` boolean to False, so the raw
measured-sign delta (positive) let it clear `all_gates_pass` despite the frozen pre-reg
explicitly saying UNDETERMINED=NOT-PASS. Caught before any downstream action (re-reading the
pre-reg's own ship-rule text against the printed gate table), fixed same-session, re-derived
from the SAME already-computed per-trade JSON (no re-run of the ~3.5min backtest) -- final
verdict flipped `ARM_EXTEND_SHIPS` -> `NEITHER_SHIPS_STAYS_TRENDLINE_ONLY`. Lesson filed:
`strategy/candidates/_lesson-inbox/2026-08-01-gate-status-label-vs-boolean-drift.md`.

**Validated:** new guard test `backtest/tests/test_g2_trendline_bypass_scope.py` (6/6 green),
RED-proofed (2/6 fail when the filters.py branch is reverted to the old unconditional
computation, confirming they exercise the new logic, not just the untouched default path).
Wider regression: 158/158 related tests green (trendline/filter5/entry_floor/engine_score_parity
subset, zero new failures). Scorecard: `analysis/recommendations/g2-trendline-bypass-2026-08-01.{json,md}`.

**Rail-4 N/A** -- the new `trendline_bypass_scope` flag stays at its inert default
(`'trendline_only'`, byte-identical to pre-fire production); zero live behavior change. Ships
as ordinary engine-benefit research (analysis + a default-inert flag + guard test + graveyard
scorecard), no J ratification needed. Revert: `git revert <this commit>` (additive-only -- new
flag param defaults unchanged, new test/tool/scorecard/lesson files, nothing else depends on
them; `queue.md`'s checkbox flip is the only edit to a pre-existing file besides `filters.py`
itself).

**Not yet resolved / follow-up (out of THIS fire's lane, named in the pre-reg):** an OPRA cache
backfill for 2026-07-23..07-31 is the single highest-leverage next input to re-deciding BOTH
this study and filter5-ribbon-2026-07-31.json -- neither can get a clean recent-window signal
without it.

---

## [2026-08-01 02:20 ET] OK -- conductor (WEEKEND): FLEET-PARITY-TESTS-READ-LIVE-STATE closed, commit `dea5b2e2`

**Signal J wakes to (OP-25).** Budget gate PASS ($0.33/$30, 2/4 fires used before this one),
market-hours gate PASS (Saturday, weekend mode). `task_scorer.py` top item
(`TWIN-DOCTRINE-FIRST-DEPLOY`) is still pending J's Discord reply on `gp-2026-07-23-twin-
doctrine-001` -- nothing new to do there. Picked the next-ranked ready MED item:
`FLEET-PARITY-TESTS-READ-LIVE-STATE` (filed 2026-07-27, a live-state test-integrity flake
this same fire's predecessor's own commit message referenced twice tonight).

**What shipped:** de-flaked `test_fleet_arm_parity.py` -- was 15/25 green, now 25/25.
Investigating "9 fail because of the live recency verdict" (the ticket's own diagnosis)
surfaced it was actually **3 independent bugs in the same 10 failures**: (1) the diagnosed
live-recency-read (fixed with an autouse fixture pinning the verdict to GREEN + a new
section explicitly exercising RED/GREEN/YELLOW branches via monkeypatch); (2) a STALE
FIXTURE the ticket didn't mention -- GATE-TIERS-IMPLEMENT (2026-07-23) added
`score_peak_passed`/`hard_skip_action` fields the test's synthetic signal blocks never
populated, silently HOLD-ing risky-3/RISKY_LOOSE on every test regardless of signal shape;
(3) a STALE ASSERTION against a deliberate redesign -- risky-1 became the FULL-SEND
learning arm 2026-07-31 (J directive, commit e28d210c), so its old "requires confluence,
HOLDs on non-elite" test was asserting retired behavior; rewrote it to document + assert
the current ungated reality instead.

**Validated:** RED-proofed via `git checkout HEAD --` baseline (reproduces the exact
original 10 failures) + restore -- never `git stash` in this repo (C34/L214/L228/L238).
Wider related suite (fleet_executor.py + full_send_arm.py) 80/80 green, zero regressions.
Curated safety gate 59/59 PASS.

**Rail-4 N/A** -- test-only change, zero production/trading-path code touched. Revert:
`git revert dea5b2e2` (additive/test-only, nothing else depends on this file).

**Lesson (not filed separately -- same class already indexed):** a queue ticket's own
diagnosis of "why N tests fail" can itself be stale/incomplete by the time it's picked
up -- always re-diagnose from the actual pytest output before applying the filed fix,
even when the filed fix sounds plausible and partially correct (this is C7/C14's
existing shape, no new L# needed).

**Autonomy metric:** `conductor_outcome.py metric` reports `trend: regressing`
(net_improvement 13/20 fires, cost/drained $2.08). This is driven by the tracked
`function_score_avg` (trading-function proxy: enters/orders/fills on the last trading
day, 2026-07-31 -- 3 enters, 3 accepted, 5 fills, 1 distinct setup), NOT by this fire's
own work (this fire closed a loop, 0 regressions, +5 net test count). Next AFTERHOURS/
WEEKEND fire should prefer another loop-closing item (per the standing instruction) over
a fresh artifact until the trend recovers.

---

## [2026-08-01 01:13 ET] OK -- conductor (AFTERHOURS): FLEET-STRIKE-TIER-ATM-EXTENSION armed on paper (pre-registered), commit `43bb979d`

**Signal J wakes to (OP-25).** Budget gate PASS ($0.33 of $30, 1/4 fires), market-hours gate
PASS (Saturday). `task_scorer.py --top` surfaced `TWIN-DOCTRINE-FIRST-DEPLOY` (still pending J's
Discord reply on `gp-2026-07-23-twin-doctrine-001`, nothing new to do there), so picked the
next-ranked ready HIGH item: `FLEET-STRIKE-TIER-ATM-EXTENSION`.

**What shipped:** risky-1/risky-3 (fleet_rest, PAPER, real_fills) repointed from
`V15_BOLD_TIERS` (OTM-2/OTM-3 under $2K) to `V15_BOLD_CORE_TIERS` (ATM under $2K) -- the SAME
table core Bold was validated+wired to on 2026-07-17/18. Mechanism: risky-1 alone lost 15 of
16 named-setup ticks to the $0.30 `min_entry_premium` floor on 2026-07-31 (2026-07-15 study:
OTM-3 clears that floor on only 33.76% of afternoon signals vs ATM's 96.88%). The queue item
explicitly said "pre-register, do NOT hand-wire" -- so pre-registered the n>=20-fill gates
BEFORE arming: `analysis/recommendations/fleet-strike-tier-atm-extension-prereg-2026-08-01.json`
(OOS_positive, WF>=0.70-or-disclosed-null, sub_window_stable, anchor_no_regression, all frozen
before any evidence exists). safe-3 explicitly EXCLUDED -- its OTM choice has its own documented
$600-notional-cap reason, out of scope.

**Mechanism:** `fleet_executor._tiers_for_arm` gained a third table string `'bold_core'` ->
`strike_selection.V15_BOLD_CORE_TIERS` (previously only `'safe'`/anything-else->`'bold'`).
`accounts.json` sets `params_patch.strike_tier_table='bold_core'` on risky-1 and risky-3 only.
Both arms' rescue lanes (`_full_send_plan`/`_ladder_plan`) price via `PROBE_STRIKE_TIERS`
directly and never call `_tiers_for_arm`, so this only affects each arm's NORMAL (gated) lane --
documented explicitly in each arm's new `strike_tier_table_doc` field.

**Validated + RED-proofed:** updated/added guard tests across 3 files
(`test_bold_core_strike_tier_2026_07_15.py`, `test_fleet_strike_tier_floor_collision_2026_07_31.py`,
`test_fleet_arm_parity.py`). Confirmed the fix introduces ZERO new failures: backed up all 4
touched files, `git checkout HEAD --` to get pristine baseline copies, ran the full targeted
suite (10 pre-existing failures -- `FLEET-PARITY-TESTS-READ-LIVE-STATE`, filed 2026-07-27, live
recency-state test rot, unrelated to this change), restored my edits, re-ran -- identical 10
failures, 99 additional passes including the new pins. Curated safety gate 59/59 PASS.

**Process note (honest disclosure):** an initial `git stash` attempt during the RED-proof step
got interrupted by a chained `&&` short-circuiting on pytest's nonzero exit code, leaving my
edits stashed while unrelated live-daemon-written files (gym log, prospector ledger, twin
journal, etc.) had moved on underneath. Recovered cleanly via `git stash pop` (partial apply,
my 4 files restored) + `git stash drop` (the conflicting daemon files were correctly left at
their newer state, never regressed) -- verified `STATUS.md`/`queue.md` content matched HEAD
before and after, no data lost. Switched to backup+checkout+restore for the rest of the
RED-proof, per C34/L214/L228/L238 (never bare `git stash` in this repo). Noted for the record,
not swept under the rug (OP-33). Two PRE-EXISTING unrelated stashes (`stash@{0}`, `stash@{1}`,
predating this fire) were left untouched -- out of scope, risk of harm from touching someone
else's WIP exceeds the benefit of tidying them this fire.

**Rail-4 (PAPER trading-path, guard+revert+REVOKE, J ratified 2026-07-01):** ships now, no J
pre-approval needed. Revert: delete `'strike_tier_table':'bold_core'` from risky-1/risky-3's
`params_patch` in `automation/state/fleet/accounts.json` (one line each, byte-identical) --
or `git revert 43bb979d`.

**Not yet resolved:** the change needs n>=20 real fleet fills to accumulate (next trading week,
market is closed this weekend) before the pre-registered gates can be scored. Follow-up item
queued: `FLEET-STRIKE-TIER-ATM-EXTENSION-EVAL-2026-08-01` (blocked on fill count, not time).

---

## [2026-08-01 00:09 ET] OK -- conductor (WEEKEND): PMH-IS-FABRICATED-IEX-PREMARKET closed, 2 rotted guards repaired, commits `155ab21e` + `7837db7e`

**Signal J wakes to (OP-25).** Budget gate PASS ($0 of $30), market-hours gate PASS (Saturday,
weekend mode). `task_scorer.py --top` surfaced `PMH-IS-FABRICATED-IEX-PREMARKET` (HIGH, ready,
score 6.0) as the top HIGH-priority ready item. Before executing it, checked git history first
(per the standing stale-checkbox lesson) -- **the fix was already shipped same-day it was filed**
(commit `7b4aa3f4`, 2026-07-27: SIP feed + degeneracy guard + provenance, all three sub-fixes
verified present verbatim in `refresh_levels_intraday.py`). Checkbox was just never flipped
(5-day lag) -- 4th confirmed instance of the stale-queue-checkbox class.

**What this fire actually shipped:** verifying "is this really done?" surfaced that the ticket's
OWN guard suite (`test_level_compiler_v2_guards.py` + `test_refresh_levels_intraday.py`) had gone
silently RED on 2026-07-28 with **zero code regression** -- two independent test-rot mechanisms:
(1) a fixture `expires_at` hardcoded to the day the test was authored, compared against real
wall-clock `_et_now()` inside `heartbeat_core._level_expired()` -- expired the instant the date
rolled over, making the "byte-identical" assertion pass vacuously on two empty lists; (2) a test
never isolated from `daily_context.py`'s REAL live shelf-zone union, so a synthetic PMH fixture
collided with an actual live SPY shelf zone and lost the dedup tie. Fixed both (far-future
constant date; `monkeypatch.setattr(rli, "daily_context", None)` in the shared `_state` fixture),
**RED-proofed** (scoped `git stash` reproduced the identical 3 failures pre-fix, restored, 38/38
green post-fix), curated safety gate 59/59 PASS both commits. Test-only change -- zero production
code touched.

**Closed the loop:** `queue.md` checkbox flipped `[ ]`->`[x]` with the verification evidence
inline; existing stale-checkbox lesson-inbox item updated with this 4th instance; new lesson-inbox
item filed for the two guard-rot mechanisms (fold target C6/C7). No J ratification needed --
test/observability-only, rail-4 not invoked (nothing on the trading path touched).

**Revert:** `git revert 7837db7e` then `git revert 155ab21e` (both additive-only, no other file
depends on these two test files or the queue.md text).

---

## [2026-07-31] LICENSE-MONITOR (deploy-timing for WP-5/6/8/0)

> - #1 ATM (Safe-2)=YELLOW(ELIGIBLE); #1 ATM (Bold)=YELLOW(ELIGIBLE); #2 ATM=YELLOW(ELIGIBLE); #4 ATM=YELLOW(ELIGIBLE)
> - **Trade-to-learn cumulative (since arm, real fills, Rule-9 visibility-only):**
> -   bollinger_squeeze (armed 2026-07-02): since-arm 6tr $+36.00 ($+6.00/tr, 50.0% WR) [4d/4 day+side buckets -- 6 rows are NOT independent trials]
> -   double_bottom_base_quiet (armed 2026-07-01, 30d ago): 0 fills since arm — no live signal yet
> -   vwap_reclaim_failed_break (armed 2026-07-01): since-arm 2tr $-15.00 ($-7.50/tr, 50.0% WR)
> -   WARNING CORRELATED: 2026-07-28 side=P fired in BOTH bollinger_squeeze+vwap_reclaim_failed_break -- same underlying day-call, not independent
> - Files: `automation/state/license-monitor-last.json`, `backtest/autoresearch/license_monitor.py`.

---

## [2026-07-31] RECENCY-CONFIRMATION (confirm-before-capital gate) — RED-BLOCKED on the freshest 25 trading days (2026-06-26..2026-07-31), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-07-31). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=YELLOW; #1 ATM (Bold)=YELLOW; #2 ATM=YELLOW; #4 ATM=YELLOW
> - **Books:** Safe2_ATM_1+2+4=RED ($-276.48); Bold_ATM_1+2=YELLOW ($-166.9)
> - **edges_confirmed_on_recent = False** (any RED=True). All live tiers still small-n / not-yet-confirmed on the freshest weeks — full-OOS-2026 base remains the larger-n companion read; HOLD capital scaling until an edge CONFIRMs. RED-BLOCKED: Safe2_ATM_1+2+4 — no live flip on these.
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## Known broken
- [2026-07-31 18:00 ET] shadow_signal_audit (NEW nightly instrument, baseline run): 1 true ORPHAN -- `detect_candlestick_pattern_bullish` (backtest/lib/filters.py:334) has ZERO references tree-wide incl. tests, while its bearish twin is wired. Flagged, not deleted. Full inventory + the shadow-signal edge measurement (verdict: promote NOTHING) -> analysis/deep-research/SHADOW-SIGNAL-INVENTORY-2026-07-31.md _(RESTAMPED 2026-07-31 19:03 ET: this line originally read "16:00 ET" -- bare MOUNTAIN local time mislabeled as ET by the instrument's own TZ bug, now fixed + guarded. True ET of the baseline run was 18:00.)_

- [2026-07-31T15:30:22] GATE-EXPIRY RED :: block_elite_bull :: refused cohort would have EARNED $13.15/tr, n=97 >= floor 10 -- COSTING money :: re-check: backtest\.venv\Scripts\python.exe backtest\autoresearch\gate_expiry_check.py --gate block_elite_bull
_Standing OP-25 flag surface. Producers append ONE loud line here on a transition into a broken/RED state (never re-spam a persisting flag) -- see `setup/guard_runner_slow.py::_flag_status_md` and `backtest/autoresearch/gate_expiry_check.py::flag_status_md` for the exact pattern. STRUCTURAL NOTE (found + fixed 2026-07-31, gate-expiry-instrument build): this header used to live INSIDE individual dated `## [...]` entries, so `setup/scripts/status_retention.py`'s byte-budget rolling (which only ever preserves the file's PREAMBLE -- everything before the first `## [` entry -- forever) carried it off to the monthly archive the moment the entry containing it aged out. Every producer targeting this marker was silently no-op'ing (marker not found -> fail-open no-write) for an unknown span before this fix. Moving it into the permanent preamble makes it immune to retention rolls going forward. If this section grows large, prune resolved lines by hand (OP-22 consolidation) rather than letting status_retention.py touch it -- it never will._

---

## [2026-07-31 ~20:30-21:15 ET] OK -- conductor (AFTERHOURS): FLEET-LIVENESS-IN-ENGINE-HEALTH closed, commit `8a598064`

**Signal J wakes to (OP-25).** The 2-of-6 fleet-account blind spot J caught twice (2026-06-25,
then again 2026-07-27) now has a structural guard, not just a memory note. `engine_health.py`
watches the fleet_rest arms (safe-3, risky-1, risky-3) the same way it already watches the
mcp_heartbeat core engines -- a silent arm now RED's `fleet_ticked` by name.

**Built:** new `setup/scripts/fleet_liveness_check.py`, mirroring `engine_liveness_check.py`'s
day-not-moment pattern -- `check_day(day)` reads `accounts.json`, watches every
`status=='active' AND execution=='fleet_rest'` arm, requires >=1 `decisions.jsonl` row dated
today per watched arm. mcp_heartbeat arms (safe-2/bold-2) excluded -- already covered by
`check_engine_core`/`check_heartbeat`. Retired (safe-1)/dormant/pending_build (mes-*) arms
excluded -- not expected to tick. Wired as `check_fleet_ticked` into `engine_health.py`'s
`build_report()`, NOT market_open-suppressed, evaluated only after 16:05 ET.

**Verified live, not just unit-tested:** `fleet_liveness_check.py --date 2026-07-31 --json` ->
`ALL_TICKED` (all 3 arms real fills today); `--date 2026-06-01` (pre-grid, arms didn't exist yet)
-> `SOME_SILENT`, correctly fires. Ran `engine_health.py` end-to-end: `fleet_ticked` GREEN in the
live-written `engine-health.json`, fused verdict unchanged (YELLOW, pre-existing unrelated
gex_archive RED).

**Guard: `backtest/tests/test_fleet_liveness_check.py`, 16/16 green, RED-PROOFED** -- moved the
new module aside + `git stash`'d the `engine_health.py` wiring, re-ran: collection
`ImportError`, confirming the tests actually fail without the fix. Restored, 16/16 green again.
Two pre-existing unrelated failures (`test_engine_health_gex_archive.py::test_live_archive_reads_green_or_yellow`,
`test_preopen_readiness.py::test_fetch_eod_flatten_reality_reads_real_tmp_files`) were confirmed
via the same stash technique to fail identically WITH and WITHOUT this change -- not a
regression from this fire, left untouched (out of scope for this task).

**Rail-4 note:** observability/monitor change only -- `engine_health.py` reads state, places no
orders, never touches params/heartbeat_core/filters/placement/exit code. Ships as ordinary
engine-benefit work, no J ratification needed. Revert: `git revert 8a598064` (additive-only,
byte-identical).

**Autonomy metric trend: REGRESSING** (`conductor_outcome.py metric`, 20-fire window,
net_improvement +10, cost/drained $2.18). Next fire should prefer a loop-closing item
(drain/promote/ratify/prune) over creating a new artifact.

## [2026-07-31 ~18:45-19:10 ET] OK -- shadow-signal lane CORRECTIONS landed: TZ bug fixed + 2 disclosure defects corrected. Verdicts UNCHANGED.

> **Signal J wakes to (OP-25).** The shadow-signal lane's own adversarial verifier caught three
> defects in the lane's own shipped work (commit `bc1263e4`). All three are now landed on the
> committed surfaces. **No verdict moved, nothing was armed or disarmed, no engine/params/exit
> /order file was touched.** The finding was never softened to match a sloppy write-up -- where
> the correction makes the signal look WORSE, it says so.

**1. TZ BUG (real bug, the repo's most-scarred class) -- FIXED + GUARDED + RED-PROOFED.**
`setup/scripts/shadow_signal_audit.py` stamped every artifact with `dt.datetime.now()` -- bare
MOUNTAIN local time rendered with an " ET" suffix. This box is Mountain (ET = local + 2h), so the
machine state, the inventory AUTOGEN header and the STATUS.md line this instrument wrote were all
**2h early and mislabeled**. Fixed via a single `stamp_et()` helper backed by `et_clock.py`. The
identical bug at `backtest/tools/shadow_signal_edge_2026_07_31.py:338` was fixed in the same pass.
- Guard: `backtest/tests/test_shadow_signal_audit_2026_07_31.py::test_generated_stamp_is_real_ET`
  (+2 companions). Suite **12/12 green**.
- RED-PROOF: reverting `stamp_et()` to `dt.datetime.now()` fails with
  `generated_at_et=2026-07-31T16:50:05 is 7201s from et_clock ET (2026-07-31T18:50:05)`.
- RESTAMPED: the inventory + machine state were regenerated by firing the REAL scheduled task
  (`Gamma_ShadowSignalAudit`, LastTaskResult=0, empty stderr) -- header now reads
  `2026-07-31T19:03:23 ET`, matching `et_clock`. The mislabeled `## Known broken` line above is
  restamped 16:00 -> 18:00 ET with the reason inline.

**2. EXIT-FALLBACK DISCLOSURE -- corrected inline (verdict UNCHANGED, bias is CONSERVATIVE).**
The harness intended the validated structure cell (-50% catastrophe cap) but `ExitState.from_entry`
needs a `trigger_level`, which was missing on **144/160 trades (90.0%)** -- so those silently ran
the **-20% premium fallback**. Proof, re-derived this session: **87 premium-stop legs, all firing
between -20.9% and -19.0%, none near -50%**; the only 16 `structure_stop` legs are exactly the 16
trades that carried a `trigger_level`. Counterfactual at the true -50% cap, re-run and reproduced:
**wick_reclaim -$2,556 -> -$6,462; trendline_reclaim -$1,097 -> -$1,588.** Both worse => **the NULL
verdict survives and strengthens.** Now a first-class field in the committed JSON
(`exit_fallback_correction` + `counterfactual_true_cap`), not a footnote.

**3. `wick_reclaim` SIGNIFICANCE -- DOWNGRADED.** "BH-SIG NEGATIVE" was n-inflation: 133 firings
are not 133 independent draws (07-20 alone ran 52 trades across 8 distinct contracts; the detector
fires on 57% of RTH bars, so positions overlap near-continuously). The pre-reg promised day-level
blocks and none were ever computed. Computed now: **stat -0.649, p=0.516, 2/3 days negative ->
"negative point estimate, NOT significant at day level."** `trendline_reclaim` **stands
unqualified**: stat -3.401, p=0.00067, **3/3 days negative**. Also stated explicitly on every
surface: `pullback_hold` is **UNDERPOWERED with NO verdict issued (untested, not dead)**, and only
the **STANDALONE-TRIGGER** form was tested -- score-contributor / veto use is UNTESTED and must not
be swept into the graveyard (C15).

Baseline numbers are **byte-identical** to the original run (diffed field-by-field against
`git show bc1263e4:...json`); only disclosure fields and the stamp changed.

**REVERT PROCEDURE for `bc1263e4` -- `git revert` ALONE IS NOT ENOUGH.** The commit shipped an
untracked Windows scheduled task. Reverting deletes the script but leaves
`Gamma_ShadowSignalAudit` registered against a missing path, firing nightly into silent failure
(fails OPEN -- it cannot block trading -- but it is the exact C7 shape this lane exists to catch).
Both steps, in order:
```powershell
Unregister-ScheduledTask -TaskName Gamma_ShadowSignalAudit -Confirm:$false   # FIRST
git revert bc1263e4                                                          # THEN
Get-ScheduledTask -TaskName Gamma_ShadowSignalAudit -ErrorAction SilentlyContinue  # -> nothing
```
Task state verified 2026-07-31 19:03 ET: **State=Ready, LastTaskResult=0, LastRunTime 19:02:50 ET,
NextRunTime 2026-08-01 17:25 ET**, action = `wscript.exe //nologo run_exe_hidden.vbs
backtest\.venv\Scripts\pythonw.exe setup\scripts\shadow_signal_audit.py`. Re-register with
`setup/install-shadow-signal-audit.ps1` (idempotent). Full procedure + leftovers list:
`analysis/deep-research/SHADOW-SIGNAL-INVENTORY-2026-07-31.md` -> "REVERT PROCEDURE".

---

## [2026-07-31 ~17:30-18:30 ET] OK -- filter-5 (ribbon MA-stack) fate lane: MEASURED, **NULL**, gate STAYS, zero net hot-path change

> **Signal J wakes to (OP-25).** Filter 5 -- the ribbon MA-stack veto that blocked all 5 live
> arms on your 10:15 bounce Friday -- has now been **measured over 390 trading days on real
> OPRA fills**. Verdict: **NULL. It is not costing you money. It is also not earning any.**
> It stays, and three future re-litigations of it are now closed.

- **Provenance finding (stated before measuring):** filter 5 had **NO ratification scorecard**.
  `git log -S'blockers.append(5)'` returns one squashed snapshot commit; all 36 `ribbon-*` /
  `filter-*` scorecards tune ADJACENT knobs or test bypasses OF it -- none ever armed it. It was
  inherited doctrine, not evidence-armed. It now has a measurement either way.
- **Cohort A (what it blocks alone, `blockers == [5]`):** **173 bull bars / 77 days + 76 bear bars
  / 42 days** full history; **28 bull + 24 bear** bars over the recent 25 days.
  **[CORRECTED 2026-07-31 evening -- these were first reported at exactly 2x.** The capture
  monkeypatch patches both `lib.orchestrator` and `lib.engine.score`, and the per-bar parity
  cross-check drives every bar through both, so each bar was recorded twice. DAY counts were
  never wrong, which is why it survived review. Deduped at source (`Blockers5Capture`), guarded
  + RED-proofed by `backtest/tests/test_filter5_capture_no_double_count.py`. **Descriptive only
  -- no gate, delta or verdict depended on these numbers.]**
- **The measurement (pre-reg frozen 17:34 ET, before any run):** deleting filter 5 outright ->
  full-window **+$738.60**, recent-25-day **-$68.00**. G2 and G3 fail; G4 (runner-anchor) and G5
  (fire count) pass. **NULL -- the gate stays.**
- **G1 (the PRIMARY gate) is UNDETERMINED, not FAIL. [CORRECTED.]** OPRA coverage collapses after
  2026-07-22 -- ~22-30 cached contracts/day through 07-22, then **3 / 0 / 0 / 2 / 3 / 0 / 4**, with
  **three recent-window trading days (07-24, 07-27, 07-30) at ZERO coverage.** ARM_A adds **7 raw
  entries** in the decisive recent window and **only 3 are measurable**; all 4 unpriceable ones sit
  in the newest week -- exactly the days your dynamic-market directive weights hardest. G1 is a
  strict sign test on that sum, and the 4 missing entries would only need to average **+$17.00**
  each to flip it. **The verdict is unchanged either way** -- UNDETERMINED is not a PASS, G2/G3
  fail on measured data, so no arm passes and filter 5 stays. **This is a GAP in the evidence, not
  a refutation.** An OPRA backfill is the one input that would settle it. Window-stratified
  exclusion table is now in the scorecard JSON + MD.
- **The headline was an artifact, and the harness caught it.** Of that +$738.60, only **+$103.60**
  came from the 21 trades filter 5 was actually blocking (**+$4.93/trade, and -$437 once the
  single best trade is dropped**). The other **+$635 (86%)** is 8 CONTROL trades that merely
  VANISH because an unlocked earlier entry ate the one-position slot -- **6 of 6** dropped days
  also carry an added trade. That is sequencing luck, not evidence about the gate.
- **⭐ THE FINDING WORTH MORE THAN THE NULL -- filter 5 is largely REDUNDANT with the ribbon-flip
  EXIT.** **76.2% of the trades the deletion unlocks exit on `ribbon_flip_back` (n=16), against
  9.9% of the control book (n=19)** -- the control book's own dominant exit is `premium_stop` at
  48.7%. The entry veto and the exit rule read the SAME lagging ribbon, so a setup admitted
  against a non-stacked ribbon is closed by that ribbon within minutes; the block-set never gets
  a chance to be right or wrong, it gets round-tripped. **This PRE-REFUTES any future "loosen the
  ribbon" that moves only the entry gate** -- it will null the same way, for this mechanism, no
  matter how the entry gate is scoped. The only version worth running is the PAIRED one: relax
  the entry gate AND suppress the ribbon-flip exit for the same cohort, in ONE pre-registered
  change. **That paired arm has never been measured.** (L243's shape, on the exit side.)
- **Cross-lane fact: deleting filter 5 does NOT recover your 10:15 Friday long -- and here is the
  honest reason. [CORRECTED.]** The earlier line "zero trades on 2026-07-31 in ANY arm" was true
  only of the WALKED book. **ARM_A DID produce a 07-31 09:50 entry (`SPY260731P00742000`,
  level_rejection + confluence @ 742.45) -- it was dropped for a MISSING OPRA CONTRACT, not by a
  gate.** Reporting an excluded-for-missing-data entry as "blocked by gating" is the C7
  silent-success shape this rig keeps getting burned by. **The conclusion survives on better,
  actual gating evidence:** under ARM_A the 10:20 bar fires `BULLISH_RECLAIM_RIDE_THE_RIBBON`
  with triggers `[level_reclaim, confluence]` at level 738.85 and is refused with blockers
  `[BLOCK_ELITE_BULL]`, action `SKIP_ELITE_BULL_LEVEL_RECLAIM` -- one of **8 BLOCK_ELITE_BULL
  refusals on that single day** (11 named gate refusals total: 8 elite-bull, 2 level-rejection,
  1 bull-1100-1200). **Filter 5 was the first veto in a stack, not the binding one.**
  Whoever holds the `block_elite_bull` lane owns the rest of that chain. Walked-vs-excluded-vs-
  refused is now separated by construction in the scorecard (`day_forensics_2026_07_31`).
- **ARM_C (structure-shift replacing the ribbon) was NOT re-run** -- exactly that semantics
  already nulled on 2026-07-28 (`structure-shift-cascade-ab-2026-07-28.json`, delta -$46,
  g1/g3/g4/g5 FAIL). Cited, not silently skipped.
- **Net code change: ZERO.** A scoped level-anchored bypass flag (ARM_B) was built, guard-tested,
  RED-proofed against 3 mutants and run -- it measured **byte-identical to outright deletion**
  (229 entries, same 21 added / 8 dropped), because when the ribbon is not BULL-stacked
  `detect_ribbon_flip_bullish` cannot fire, so every filter-5-blocked bull setup is level-anchored
  BY CONSTRUCTION. Provably redundant + nulled -> **the flag was reverted out of `filters.py`**
  rather than left as a dead default-off knob in the repo's most consumer-heavy hot-path file
  (C14). `git diff backtest/lib/filters.py` is empty. ARM_A reproduces the whole finding using an
  existing production kwarg.
- **Artifacts:** pre-reg `analysis/recommendations/prereg-filter5-ribbon-2026-07-31.json` ·
  scorecard `analysis/recommendations/filter5-ribbon-2026-07-31.json` / `.md` ·
  runner `backtest/tools/filter5_ribbon_fate_2026_07_31.py` ·
  lesson inbox `strategy/candidates/_lesson-inbox/2026-07-31-gate-ab-delta-dominated-by-preemption-not-the-block-set.md`.

## [2026-07-31 ~09:12-09:35 ET] OK -- conductor (AFTERHOURS): LIVE TV-CDP outage fixed pre-open + self-heal blind-spot closed, commit `c941567c`

> **STAGE 0/1:** ET 09:12 Friday (pre-open, market closed until 09:30). Budget gate
> PROCEED ($11.44/$30, 2/4 fires). `self-check-last.json` showed `BROKEN`: TV-CDP
> unreachable on :9222, ~18 min before market open. Per STAGE-1 priority-1/2
> (function-first / Engine RED), investigated + fixed first before anything else.

> **LIVE-VERIFIED (OP-33), not guessed:** `curl :9222/json/version` confirmed CDP
> genuinely down. `Gamma_TvWatchdog` log showed it had ALREADY tried to self-heal twice
> (RELAUNCH_KILL at 09:05 and 09:10 ET, `CDP dead for 3896s` -> `4196s` -- growing, not
> shrinking) -- both attempts silently failed with no distinguishing signal from a
> successful relaunch. Manual `taskkill /F /IM TradingView.exe` + relaunch fixed it live
> (`curl` now returns a valid CDP payload, `self_check.py` flipped `BROKEN` -> `DEGRADED`).

> **ROOT GAP (C7 silent-success-is-failure):** `Invoke-TvLaunchSafe` (`_shared.ps1`)
> returned only `{skipped}` -- no signal whether the relaunch it just ran actually
> restored CDP. `run-tv-watchdog.ps1`'s 3 call sites logged the identical `relaunch_kill`
> shape whether the fix worked or not, so a genuinely-failing self-heal looked the same
> in STATUS.md as a working one for 70+ minutes until an unrelated producer
> (`self_check.py`) caught it independently.

> **FIX SHIPPED:** `Test-CdpReady` poll helper + `Invoke-TvLaunchSafe` now self-verifies
> post-launch and returns `{skipped, healed}`; the 3 watchdog call sites branch into
> `*_healed` / `*_FAILED` tvActions, and a `*_FAILED` outcome writes a distinct
> append-only `### BROKEN:` STATUS.md block instead of blending into routine noise.
> **Also closed a separate small gap while touching this file:** `test_tv_launch_safe_
> 2026_07_06.py` existed on disk (dated 2026-07-06) but had NEVER been `git add`-ed
> (L242-shape) -- committed it now alongside the new assertions it needed anyway.

> **Verified (OP-33):** 7/7 tv-launch-safe tests green (incl. 2 new), 40/40 related
> infra-watchdog suite green, 59/59 curated safety gate green. Live CDP re-confirmed up
> AFTER the code change (not just before). `git show c941567c --stat --name-status`
> confirms exactly the 3 intended files (L247 discipline).

> **Open question, logged not chased further (debugging-discipline discipline):** WHY
> the 09:05/09:10 production relaunches failed while 2 manual reproductions of the
> identical code path (same Interactive-logon task principal) both succeeded minutes
> later was not fully root-caused -- ruled out AppX-query flakiness (5/5 manual reps
> clean) and window-station mismatch (principal confirmed Interactive). The shipped fix
> makes a recurrence LOUD regardless of the underlying mechanism, which is the
> higher-leverage response; chasing the exact intermittent trigger further was not a
> good use of this fire's budget. Lesson filed:
> `_lesson-inbox/tv-selfheal-silent-failure-2026-07-31.md` (also flags
> `Invoke-LevelRefreshSafe` + `state_freshness_selfheal.py` as worth auditing for the
> same verify-the-effect-not-just-the-attempt gap).

> **Scope + revert:** 2 infra scripts + 1 test file. Zero params/heartbeat_core/filters/
> placement/exit/CLAUDE.md touched. Revert: `git revert c941567c`.

---

## [2026-07-31 ~05:30-05:57 ET] OK -- conductor (AFTERHOURS): 4 un-actioned self-audit batches triaged + closed, commit `aed731f2`

> **STAGE 0/1:** ET 05:30 Friday (market closed). Budget gate PROCEED ($10.78/$30, 1/4 fires).
> `engine-health.json` clean (14 GREEN, gex_archive 1-day interior-gap YELLOW non-critical,
> no RED). `self-check-last.json` GREEN. STAGE-1 priority order: function-first (fill-funnel)
> clean, no Engine RED -- landed on priority-3, self-audit gaps: `analysis/self-audit/
> new-gaps-flagged.md` had 4 CONSECUTIVE un-triaged daily-swarm batches (2026-07-26 through
> 2026-07-29, ~32 lines), the longest un-actioned backlog since this pipeline started
> (normal cadence closes same-day or next-day).

> **Live-verified every substantive claim rather than re-deriving (OP-33):** the recurring
> "conductor firing far more than max_fires" line (named in 3 of the 4 batches) was already
> root-caused and fixed 2026-07-29 (commit `631798f0`, cross-midnight substring bug in
> `conductor_budget.py::spend_today`) -- re-confirmed live this fire (`PROCEED $10.78/$30,
> 1/4 fires`, correct for today). "Claude-native task governance requires manual
> intervention / hard-stop risk" -- read `audit_scheduled_tasks.py` live: read-only,
> fail-open, surfaces to STATUS.md only, no hard-stop code path exists. "Auto-commit of
> strategy/candidates without validation creates noise" (appeared twice) -- read
> `auto_commit_candidates.py` live: scoped to `strategy/candidates/` only, pathspec (never
> `-A`), fail-open, fires at >=10 pending changes; live `git status --porcelain
> strategy/candidates` showed only 2 pending -- working as designed, not a noise source.
> "No live-to-paper shadow mode while RED-blocked" -- already built (TRADE-TO-LEARN,
> CLAUDE.md rail-4). "Git commits abused as a runtime config toggle (DO_NOT_ARM/FROZEN)" --
> grepped every hit across `setup/scripts`+`backtest/autoresearch`: all are `FROZEN_CONFIG`
> frozen-dataclasses (C1 no-repick discipline) or anchor-freeze comments -- no such code
> path exists, this was a misread. "Correlated arm signals not filtered" -- already
> detected+disclosed via `trade_to_learn_digest.py`'s `cross_setup_same_day_side` (confirmed
> live in the 2026-07-30 LICENSE-MONITOR STATUS entry's own "WARNING CORRELATED" line).

> **Disposition:** every substantive claim across all 4 batches was either already fixed,
> already built, or intentional doctrine -- zero new code needed. Wrote 4 `<!-- DONE -->`
> triage blocks (one per batch, citing the live evidence above) so the next fire doesn't
> re-derive this. Doc-only commit (`analysis/self-audit/new-gaps-flagged.md`, +132/-0),
> curated safety gate 59/59 PASS at commit time. No params/heartbeat_core/filters/placement/
> exit/CLAUDE.md touched -- outside rail-4's scope entirely (pure analysis-log append).
> Revert: `git revert aed731f2`.

---

## [2026-07-31 ~00:59-01:15 ET] OK -- conductor (AFTERHOURS): STATE-FRESHNESS-SILENT-TASK-STALL-SELFHEAL closed, commit `33a42102`

> **STAGE 0/1:** ET 01:00 Friday (market closed). Budget gate PROCEED ($0/$30, 0/4 fires).
> `engine-health.json` showed 1 RED at fire start: `state_freshness` -- 3/17 live-path state
> files STALE (`trade-today.json`, `pnl-statement.json`, `ema-snapshot.json`). Per STAGE-1
> priority-2 (Engine RED), investigated first.

> **FOUND, live-verified (OP-33, not guessed):** `Gamma_TradeToday` / `Gamma_BrokerFills` /
> `Gamma_EmaSnapshot` all last fired 2026-07-29 despite `Enabled=True`/`State=Ready`/
> `LastTaskResult=0` (their last run succeeded), no hung process anywhere on the box
> (`Win32_Process` sweep clean), no reboot (`LastBootUpTime` 2026-07-17), `Schedule` service
> `Running` the whole time, `NumberOfMissedRuns` nonzero (195/43/1 -- Task Scheduler itself
> knew it missed occurrences) and a manual `Start-ScheduledTask` succeeded immediately. A
> wider `Get-ScheduledTaskInfo` sweep found ~17 more `Gamma_*` tasks in the identical
> last-ran-2026-07-29 shape (trigger times spanning 07:46-15:30 local) while dozens of OTHER
> tasks -- including 1-min-cadence `Gamma_HeartbeatCore` -- fired normally all through
> 2026-07-30, ruling out a machine-wide sleep/reboot/AV cause. **Root cause of WHY Task
> Scheduler silently stopped dispatching these triggers was NOT determined** -- the
> `Microsoft-Windows-TaskScheduler/Operational` event log is disabled on this box, zero
> forensic trail available. Rather than over-invest chasing an unfalsifiable Windows mystery,
> filed the open question as a lesson with a queued (not executed) follow-up: re-enable that
> event log so a recurrence leaves evidence.

> **FIX SHIPPED (remediation, not the forensics):** `state_freshness_selfheal.py` -- for any
> RED `state_freshness_audit` entry, resolves the manifest's `task` field to a single
> `Gamma_*` task name and force-starts it via `Start-ScheduledTask` (cooldown-guarded 20min,
> fail-open, never guesses an ambiguous/manual/multi-writer field). Wired into the existing
> 5-min `Gamma_TvWatchdog` cadence (`run-tv-watchdog.ps1`, no new scheduled task) --
> structurally the SAME self-heal shape `Invoke-LevelRefreshSafe` established for
> `key-levels.json` on 2026-07-30, but for a genuinely different failure mode: there was no
> stuck process to kill here, the scheduled trigger itself silently never fired, so the fix
> is a direct force-start rather than kill-tree+relaunch. **Manually ran the real (non-dry-run)
> heal live tonight:** all 3 producers restored (`Start-ScheduledTask` returncode 0 each,
> output files' mtimes updated within seconds), `state_freshness_audit` verdict flipped
> RED -> GREEN, confirmed via a fresh audit re-run.

> **Verified (OP-33):** 20 new guard tests (`test_state_freshness_selfheal.py` -- resolve/
> skip-ambiguous/cooldown/dry-run/fail-open-on-audit-raise/logging), all green; full related
> suite (level-refresh, tv-launch-safe, engine-liveness, state-freshness) 87/87 green;
> curated safety gate 59/59 PASS. `git show 33a42102 --stat --name-status` confirms exactly
> the 3 intended files (L247 discipline): `state_freshness_selfheal.py` (new),
> `test_state_freshness_selfheal.py` (new), `run-tv-watchdog.ps1` (+33/-2 lines, one new
> wired section + a status-field addition).

> **Scope + revert:** 3 files, pure infra self-heal -- zero params/heartbeat_core/filters/
> placement/exit/CLAUDE.md touched. Revert: `git revert 33a42102`. Lesson filed:
> `_lesson-inbox/2026-07-31-scheduled-task-silent-stop-firing.md`.

---

## [2026-07-30 ~20:30-20:50 ET] OK -- conductor (AFTERHOURS): LEVEL-REFRESH-WATCHDOG-WINDOW-BUG closed, commit `d7774638` -- plus closing the visibility gap on 4 earlier undocumented fixes

> **STAGE 0/1:** ET 20:30 Thursday (market closed). Budget gate PROCEED ($1.98/$30, 1/4
> fires). `engine-health.json` showed 2 RED checks at fire start: `levels_blind` (0/770 RTH
> rows today carried an active key level) and `state_freshness` (3/17 live-path files
> stale). Per STAGE-1 priority-1/2 (function-first / Engine RED), investigated first.

> **FOUND: the whole `levels_blind` incident had ALREADY been root-caused, fixed, tested,
> and doc-synthesized by 4 earlier fires TONIGHT (commits `90a0e826`, `54b27c00`,
> `3a5d3246`, `9b25aa79`, `0d70b109`, between ~19:06-20:24 ET) -- but NONE of that work was
> ever reported to STATUS.md** (only `queue.md` and a standalone doc,
> `analysis/deep-research/BLIND-ENGINE-REPAIR-2026-07-30.md`, carried it). Closing that
> visibility gap now: `Gamma_LevelRefresh`'s Task Scheduler cadence silently stalled ~20h
> (last good run 07-29 22:43 ET, zero errors, zero self-recovery); every one of today's 770
> RTH decision rows carried `levels_active: []`; the engine fell through to its worst cohort
> (trendline-only) and fired 11 unanchored `ENTER_BEAR` verdicts at the day's low before SPY
> rallied 6.7pts -- only `RISK_DENY_RISK_CAP`/`RISK_DENY_PDT` stopped the fills. Fixed with
> THREE layers: (1) `SKIP_NO_LEVELS` entry-side rail in `heartbeat_core.py` -- an ENTER with
> no level anchor now refuses instead of trading blind; (2) `Invoke-LevelRefreshSafe`
> (`_shared.ps1`) -- kill-the-stuck-tree + relaunch self-heal, wired into the existing 5-min
> `Gamma_TvWatchdog` cadence; (3) `levels_blind_check.py` -- a day-scoped, RTH-ratio,
> non-market-hours-suppressed consumer+producer monitor. Lesson filed:
> `_lesson-inbox/level-refresh-silent-stall-2026-07-30.md`.

> **THIS FIRE'S OWN FINDING (re-verifying rather than trusting the prior work, OP-33):** the
> self-heal window guard in `run-tv-watchdog.ps1` read `$mins -ge 942 -and $mins -le 955`.
> `$mins` is `Hour*60+Minute` (minutes-since-midnight) -- the SAME convention the adjacent
> `hbFlag` window correctly uses via `575`/`955`. `942` minutes-since-midnight is **15:42
> ET, not 09:42 ET** -- so the safety net built to prevent tonight's exact incident from
> recurring only ever activated in the final **13 minutes** before the close (942-955), not
> the intended ~373-minute RTH window (582-955). Its own guard test asserted the literal
> substring `"942" in src`, which is true under BOTH readings, so it could not catch this by
> construction. **Fix:** `942 -> 582` (9*60+42); test rewritten to regex-extract the real
> `$mins` bound and assert on the DECODED wall-clock time (09:42/15:55) plus a width check
> (>300min). RED-proofed via `git stash` (fails with the predicted 15:42 readout
> pre-fix); 5/5 green post-fix; full related suite (blind-no-levels,
> levels-blind-detection, tv-launch-safe) 85/85 green; curated safety gate 59/59 PASS.
> `git show d7774638 --stat --name-status` confirms exactly the 2 intended files (L247).
> Lesson filed: `_lesson-inbox/substring-guard-cant-verify-magic-number-semantics-2026-07-30.md`
> (C14 family: a unit-bearing magic-number guard must assert the DECODED value, not the
> substring's presence).

> **Scope + revert:** 2 files, pure watchdog infra -- no params/heartbeat_core/filters/
> placement/exit/CLAUDE.md touched. Revert: `git revert d7774638`.

> **Left open for next fire (not this fire's scope):** the synthesis doc
> (`BLIND-ENGINE-REPAIR-2026-07-30.md`) flags a separate finding worth a follow-up look --
> "49 documented-Active scheduled tasks sat `State=Disabled`" -- and a sizing-deadlock
> per-arm ceiling table with 4 ranked remediation options left UNCHOSEN. Neither touched
> here; flagging so they don't silently age out of visibility the same way this whole chain
> almost did.

---


## Kitchen
Kitchen: alive, queue 36 pending, last cook 0 min ago, today $0.00, model=ollama::qwen3:14b

- [2026-08-01 04:00:01] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-08-01 04:00:01] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-08-01 04:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-08-01.md
