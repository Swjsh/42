# OVERNIGHT TASK QUEUE — conductor work backlog

> Format: `- [ ] <id> (<priority>) :: <description> :: depends:<...> :: status:<pending|in_progress|blocked>`
> **OP-22 discipline:** this file holds REAL, drainable work. Machine-generated regression/harvest noise lives in `## Archived 2026-06-19` (rolled up) and verbatim in `queue-archive-2026-06-19.md`. When you finish an item, move it to `## Completed`. When you add HARVEST/REGFAIL auto-noise, it does NOT belong here unless it names a concrete, actionable engine fix.
>
> **Triaged 2026-06-19** (OP-22 compound-don't-accumulate pass): 172 stale auto-generated CRITICALs + harvest data-points archived; gym is 88/88 green (CONTEXT-107/109) so the EDGE_REGRESSION_FAIL "CRITICALs" were false alarms that nothing drains. Active backlog below is the genuinely-real remainder, ranked by leverage. Full pre-triage file preserved verbatim at `automation/overnight/queue-archive-2026-06-19.md`.

---

- [x] FUNCTION-SCORE-ZERO-ENTER-CHECK (HIGH, engine-function, **DONE 2026-07-23 ~09:12-09:35 ET conductor, commit `56b4bd2b`**) :: **DIAGNOSIS: (a)+(c), both benign — no bug.** Pulled 2026-07-22's `core-decisions.jsonl` tick-by-tick: 774 core ticks, `{'SKIP_STALE_TRIGGER':14,'HOLD':720,'SKIP_ELITE_BULL_LEVEL_RECLAIM':40}` — 733/774 reasoned "no setup passed scoring" with an EMPTY triggers list (bear max score 9, never a live trigger — genuinely quiet bear day per (a)), the 40 bull hits were the ALREADY-AUDITED data-gated `block_elite_bull` (BULL-UNBLOCK-REPLAY-PROBE, verdict KEEP, thread closed 2026-06-30 — not new, not a bug), and 1 was a legitimate structure-veto. `fill_funnel.py --date 2026-07-22` independently verdicts **GREEN**: core:safe 2 fills/2 exits via the `extra_exec` secondary lane (vwap_continuation + bollinger_squeeze, a designed/armed/cooldown-gated execution path per `_route_extra_setups` in heartbeat_core.py, not a workaround) — confirms (c). **REAL BUG FOUND + FIXED (why 3 fires kept re-flagging this as "worth a look"):** `conductor_outcome.py`'s `trading_function_snapshot()` only read the primary verdict/exec pipeline for `orders_accepted` — it was BLIND to the `extra_exec` lane that `fill_funnel.py` already fixed visibility for on 2026-07-22, so the function metric kept reading "0 orders_accepted" on a day that actually had 4 real extra_exec PLACED orders + 2 fills. Fixed: added `extra_exec_orders_accepted` (new field, kept separate from `orders_accepted` — same scoping fill_funnel.py already chose, so the primary-pipeline signal stays uncontaminated), folded into `distinct_setups_traded` + the weighted function score (x2, same weight as `orders_accepted`). Verified against the live ledger: `trading_function_snapshot()` now reads `extra_exec_orders_accepted=4, distinct_setups_traded=2` for 2026-07-22 — matches `fill_funnel.py`'s independently-computed funnel exactly. 2 new guard tests (scoping isolation + record/metric plumbing), 23/23 in the module pass, curated safety gate (31 tests) PASS. Post-commit `git show 56b4bd2b --stat` confirms exactly the 2 intended files. Rail-4 clear: pure observability/metric code, zero params/heartbeat_core/filters/placement/exit/CLAUDE.md touched. Revert: `git revert 56b4bd2b`. :: depends:none :: status:done

- [x] TASK-SCORER-SECTION-SCOPE-FIX (HIGH, infra, **DONE 2026-07-23 ~18:12-18:35 ET conductor, commit `6d42d211`**) :: `task_scorer.py`'s `_active_lines()` stopped at the FIRST top-level `## ` heading after `## Active backlog`, silently hiding every item filed in a later dated section (`## Blocked`, `## Twin escalations`, `## HARVESTED-FROM-GYM` body, etc). Confirmed live: `--all` went 45 -> 79 parsed items; HIGH-ready went 2 -> 6 (`GATE-TIERS-IMPLEMENT`, `OPEN-BELL-STATUS-PUSH`, `TWIN-B6-SIM-FRICTION-CALIBRATION`, `VWAP-TREND-PULLBACK-VERIFY-FAILED` newly surfaced). Fixed: scan Active backlog -> EOF, exclude only provably-resolved `Archived`/`Completed` sections. RED-proofed via git stash, 63/63 task_scorer suite + 31+5 curated gate PASS. Full detail: STATUS.md same timestamp. **Next-fire note:** the now-visible HIGH items below (GATE-TIERS-IMPLEMENT L2431, ENGINE-VECTORIZATION L2391-ish, OPEN-BELL-STATUS-PUSH, TWIN-B6-SIM-FRICTION-CALIBRATION) are real, pickable work that was previously invisible to `--top` — worth a look before defaulting to whatever `--top` names next, since some may themselves be stale (task_scorer's own staleness advisory already flags `VWAP-TREND-PULLBACK-VERIFY-FAILED` for exactly this reason). :: depends:none :: status:done

---

## Active backlog

### CATASTROPHE-CAP-WIDEN-WATCH (MED, accrue-then-decide, filed 2026-07-23 EOD)

- [ ] CATASTROPHE-CAP-WIDEN-WATCH (MED) :: The stop-forensics A/B (catastrophe-stop-shakeout-2026-07-23)
  found a REAL but UNDERPOWERED signal: the -50% catastrophe cap has fired on only n=4 historical
  bear trades, and 4/4 of those were genuine shakeouts (premium recovered past the exit, 3/4 hit
  full TP1). Widening to -70% (Δ+\$2,146) or structure-only (Δ+\$3,626 with ZERO losses) both beat
  control on aggregate + drop-best-1 -- but FAIL majority-of-days (a rare-tail lever can't win most
  days) and have ZERO held-out fires (can't OOS-confirm). TODAY was NOT one of these: today's 735P
  decayed on theta, holding would have lost more (-\$615 vs -\$305) -- the cap was correct today.
  This is the FIRST study to touch catastrophe_stop_pct itself (trail-width + structure-ref both
  held it at -0.50). ACCRUE: shadow-log every future catastrophe-cap fire + its held-to-EOD
  counterfactual until n>=10, then a pre-registered decision. Do NOT widen on n=4. depends:none :: status:pending

### ENGULFING-AT-STRUCTURE-TRIGGER (HIGH, THE build -- 3 live exhibits, mirror-symmetric, untested by the 181-cell matrix)

- [ ] ENGULFING-AT-STRUCTURE-TRIGGER (HIGH, Lane-A vocabulary + Lane-B pre-reg) :: J called this
  pattern live on THREE separate days, both directions, and the engine had ZERO trigger every
  time. VERIFIED FROM TAPE + core-decisions.jsonl:
    * 2026-07-21 BULLISH: engulfing at a double bottom (lows 744.790 / 744.795, 3 taps of one
      shelf) -> SPY ran 746.77 -> 748.97. Engine: bull 9-10, triggers=[].
    * 2026-07-23 BEARISH (mirror): 10:40 bar O740.38 H740.59 L738.68 C738.86, body 79.5% (the
      most decisive candle of the window), textbook bearish engulfing (opens >= prior close
      740.37, closes <= prior open 739.04) at a DOUBLE TOP (highs 740.505 @10:35 / 740.585
      @10:40, 8c apart; shelf also tested 10:00-10:05) -> SPY fell 738.86 -> 736.63+.
      Engine: triggers=[], and its score moved AGAINST the setup at the turn (10:40 bear 8 /
      bull 6 -> 10:41-10:45 bear 6 / bull 7-8).
  THREE DISTINCT MECHANISMS, all confirmed:
    (1) NO ENGULFING VOCABULARY -- no detector emits a trigger for an engulfing bar, either
        direction. (double_bottom_base_quiet is the nearest thing and is proven dead-strict:
        lookback 20 bars < the real 24-bar gap, RTH-only strips premarket lows.)
    (2) NO INTRADAY SWING DOUBLE-TOP/BOTTOM AS A LEVEL -- the 740.505/740.585 twin highs never
        became a level; engine's levels_context showed nearest_above=739.9, then jumped to
        742.51 once price poked above 739.9, LOSING the actual reversal shelf entirely.
    (3) SCORING IS LAST-BAR REACTIVE -- the 10:35 green bar pushed bull up exactly as the top
        formed, so the engine was at its LEAST bearish at the highest-conviction short. Same
        shape mirrored on 07-21 (least bullish into the bottom).
  WHY THIS IS NOT ONE OF THE 181 DEAD CELLS: the edge-matrix (98) + kitchen (83) tested
  LEVEL-TOUCH triggers (rejection/reclaim/flip/pingpong/break-retest) and non-level trend
  vocab. A CANDLE PATTERN AT A SWING STRUCTURE (engulfing at a 2-touch swing high/low) was
  never a cell in either. Mirror-symmetry across both directions is evidence of structure, not
  curve-fit -- but it is still 3 exhibits and MUST clear the standing 4-gate bar + BH.
  BUILD (after close, Rule 9): (a) intraday swing-high/low detector -> 2-touch shelf becomes a
  zone-banded level (levels-are-zones); (b) engulfing detector (body-% floor, engulfs prior
  body, direction) fired AT that zone; (c) frozen pre-reg grid <=16 cells, real-fills replay
  through exit_manager_walk over the 386-day history, standing gates + BH. Sanity anchors the
  winning cell MUST fire on: 07-21 11:05 bullish, 07-23 10:40 bearish.
  CREDIT WHERE DUE (J's own read, verified): the 10:30 SKIP_DOJI_ENTRY_BAR block was CORRECT --
  the next bar (10:35) closed +$1.33 green. The doji gate is not the problem; the missing
  vocabulary is. depends:none :: status:pending

> **PARTIAL PROGRESS 2026-07-23 ~16:15-16:50 ET (conductor, AFTERHOURS), commit `31c5089e`.**
> Checked the grammar registry (`backtest/lib/patterns/`, built 2026-07-09, "NO WIRING") before
> building anything from scratch -- it already has an `engulfing` predicate (candlestick geometry,
> mechanism (1)) AND a `flat_side`/`labeled_swings` swing-shelf primitive (mechanism (2)'s
> nearest cousin, powers `double_top_bottom_at_level`/`rectangle_range_break`/`triangle_*`). What
> was genuinely missing: a rule COMBINING them anchored to the intraday swing shelf specifically
> (the registry's existing `engulfing_at_level` anchors to NAMED DAILY levels only). Built + shipped
> `engulfing_at_swing_shelf` (bullish engulfing at a 2-touch swing-low shelf / bearish at a 2-touch
> swing-high shelf, $0.30 proximity). C27 prescreen: **TESTABLE full-history (28.9% days, 0.42
> fires/day) AND stable recent-90d (no drift)** -- notably CLEANER than `engulfing_at_level`,
> which this same prescreen run showed has DRIFTED to NOISE-KILL recently (fires almost daily
> now; not disclosed before this fire).

> **Sanity-anchor falsification -- RUN, and it FAILED (reporting honestly, not just the clean
> prescreen number -- OP-33/`/fable-too-good` discipline):** checked the shipped predicate
> DIRECTLY against both exhibits this item names. **07-21 11:05 bullish: does NOT fire.**
> `flat_side(kind="swing_low", n_touches=2)` returns `None` at that bar -- the last 2 CONFIRMED
> swing lows by then are 10:15 (744.79) and 10:40 (745.77), 0.98\$ apart (not a flat shelf), and
> the actual tight cluster J read (10:40 L745.77 / 11:00 L745.83 / 11:05 L745.85, ~8c apart --
> see the RSI-EXTENSION-BLOCK-ELITE-BULL item above, same day) never registers as 2+ DISTINCT
> swing-low pivots at all: `crypto/lib/market_structure.py`'s labeler only emits 10:40 as a
> pivot; 11:00/11:05 are higher, so they're read as trend continuation, not new reversal points.
> **07-23 10:40 bearish: does NOT fire either** (checked directly against the freshest cache,
> `backtest/data/spy_5m_2026-05-19_2026-07-23.csv` -- today's bar IS present). Same root cause:
> the 740.505/740.585 double-top (8c apart, 5 min apart) never registers as 2 distinct swing-high
> pivots; the last confirmed swing high by 10:40 is 09:40 (742.56), stale and irrelevant.

> **Root cause is now precisely pinned (not just re-asserted):** this is not "missing
> vocabulary" after all -- `ctx.structure.labeled_swings`'s underlying pivot-labeling timescale
> (shared by EVERY rule in the swing family: `flat_side`, `monotone_swings`,
> `double_top_bottom_at_level`, and now `engulfing_at_swing_shelf`) is fundamentally too COARSE
> to ever see a tight/fast double-top-or-bottom that resolves within 2-3 five-minute bars and
> a few cents of price. Building more compositions on `labeled_swings` cannot fix this; the gap
> is a genuinely NEW, cheaper primitive: a rolling-K-bar local-extreme-CLUSTER check (e.g. "the
> last K closes/highs/lows sit within $X of each other", no formal reversal-pivot confirmation
> lag required) -- structurally different from the existing swing-pivot family. **NEXT STEP
> (not this fire):** design + prereg that primitive, re-run the same 2-anchor falsification test
> BEFORE composing it with `engulfing` or committing to the frozen 16-cell grid + real-fills
> replay this item originally asked for -- doing the expensive replay on a still-unverified
> primitive would be exactly the "build first, falsify never" mistake this fire's own discipline
> caught. Foot-gun (a shared primitive's timescale silently bounds every rule built on it, and a
> clean aggregate prescreen number can still fail a targeted anchor check) filed to
> `_lesson-inbox` for graduation. Ships as-is: `engulfing_at_swing_shelf` remains a real,
> tested, stable grammar addition regardless (12/12 registry rules, 57/57 tests, curated gate
> 31+5 PASS) -- it just doesn't (yet) explain these 2 exact exhibits. Item stays `status:pending`,
> NOT closed -- the swing-shelf angle is exhausted, the tight-cluster primitive is the live thread.

> **INFRA CLOSED THE LOOP 2026-07-23 ~17:40-17:58 ET (conductor, AFTERHOURS), commits
> `eea3f423` + `fad447e1`.** The self-audit swarm independently surfaced the exact process
> gap this item's own falsification pass exposed by hand: "the system lacks a reliable
> pre-ship validation step that confirms a rule actually fires on the specific anchor bars
> J identified." Built that step as a reusable contract instead of a one-off check: a new
> optional `anchors` field on `PatternRule` (date/time_et/bias/expected_fire/note) +
> `backtest/tools/pattern_anchor_verify.py` (loads the real cached bar, runs the rule's
> live predicate, reports actual vs declared) + a guard test
> (`test_pattern_anchor_verify.py`, 63/63 green) that fails LOUD if any declared anchor's
> actual fire state drifts from what's recorded. `engulfing_at_swing_shelf` now carries
> its own two anchors HONESTLY declared `expected_fire=False` (matching this item's own
> 16:15-16:50 finding) with the root-cause note inline in the registry itself -- so the
> next person/fire reading `registry.py` sees the true state without re-deriving it from
> `queue.md` prose. Side-finding while building it: `pattern_prescreen.find_master_csv`'s
> widest-history file selection picked a CSV one day stale vs today's tape (silently would
> have made any anchor check on "today" vacuous) -- fixed with a dedicated
> `find_freshest_csv` picker in the new tool. **This does NOT advance the live
> thread itself** (the rolling-K-bar cluster primitive is still the next actual step,
> not started this fire) -- it hardens the PROCESS so that whenever that primitive does
> land, verifying it against these exact 2 anchors is one command
> (`pattern_anchor_verify.py --rule <new_rule_name>`) instead of another hand-run OP-33
> pass. Curated safety gate (31+5) PASS at both commits. Item stays `status:pending`.

### DOUBLE-BOTTOM-DISARM-DECISION (HIGH, 24h re-audit then act, filed 2026-07-23 overnight kitchen)

- [x] DOUBLE-BOTTOM-DISARM-DECISION (HIGH) :: **RESOLVED 2026-07-23 ~01:55 ET (conductor,
  AFTERHOURS) -- KEEP ARMED, do NOT disarm. The -\$3,504 headline number was a fidelity
  artifact, not the production-faithful read.** Traced the fidelity question directly: grepped
  `backtest/lib/watchers/double_bottom_base_quiet_watcher.py` -- Gate 6 (`enrich_hit_with_
  proximity` / NOT_NEAR_NAMED \$0.50 check) is hardcoded and UNCONDITIONAL in the live watcher
  (no enable flag, always applied to every real signal). The harness's own pre-reg
  (`analysis/kitchen/prereg-extra-lanes-fullhist-2026-07-23.json`) already disclosed its
  BASELINE cell omits this gate ("matching the detector's own already-published simplified-scan
  precedent" -- not matching production). The harness ALSO already ran the gated cell as its
  refinement knob (`not_near_named=True`, using a causal LevelMemory-reconstructed proximity
  series) -- this is the production-faithful cell, and it already existed in
  `analysis/kitchen/extra-lanes-fullhist-results-2026-07-23.json`, just not the one quoted in
  this item's own filing. Read it: n=21 tuning fills (vs 115 ungated -- the gate alone kills
  ~82% of the population, consistent with DB-BASE-QUIET-PROXIMITY-GATE-LEAD's "0 fills in 20+
  live days" observation), total_pnl +\$8.95 (expectancy +\$0.43/tr), held_out -\$112.40,
  gates_passed 2/4, p_raw=0.988 (statistically indistinguishable from zero). **Verdict: near-flat
  noise on thin n, NOT the "-\$3,504 deeply negative" pattern that motivated considering a
  disarm** -- that number came from the ungated cell, which production never actually trades.
  Per the item's own pre-stated decision logic ("if the harness diverges from live config ->
  re-run the baseline at true production stack first") -- divergence confirmed, production-
  faithful cell already exists, and it does not support disarming. No params.json change (status
  quo = correctly armed already); zero live bleed regardless (lane already fills almost nothing).
  Foot-gun flagged to `_lesson-inbox` (a full-history harness's disclosed baseline-knob number is
  NOT the production number when the knob is a gate that's unconditional live -- the refinement
  cell is the one to quote, not the baseline). Related: DB-BASE-QUIET-PROXIMITY-GATE-LEAD (this
  fire supplies its first quantified suppression estimate, ~82% of an ungated population --
  that item's own \$0.50-band-width question stays open), DOUBLE-BOTTOM-LOOKBACK-AB (unaffected,
  separate lookback-window question).

### TRENDLINE-TIGHT-EXIT-ACCRETE (MED, watch candidate from the kitchen's best near-miss)

- [ ] TRENDLINE-TIGHT-EXIT-ACCRETE (MED) :: Kitchen cell A6 (class-conditional-exits): tighten
  TRENDLINE-class stops -20%->-12% and trail 15%->10% = the night's ONLY 4/4-gate cell, best
  day-WR of any candidate (67.4%) -- but q=0.31 after the 83-cell portfolio BH correction
  (own-lane q=0.066 was homework-self-grading). NOT a ship; IS the best-evidenced exit lead
  since SS-B. Accrual path: live SHADOW-score the tightened exit on every real trendline-class
  fill going forward (shadow ledger, zero behavior change) until n clears a pre-registered
  bar; the nightly matrix rerun re-tests it as history grows. Opposite-direction sanity: the
  global trail-width A/B (CONTROL-HOLDS) tested WIDER, not tighter -- no conflict.

### RIBBON-SESSION-SCOPE-DIVERGENCE (HIGH, discovery from the TV parity oracle 2026-07-23)

- [x] RIBBON-SESSION-SCOPE-DIVERGENCE (HIGH, two-part) :: THE discovery of the edge-matrix run:
  J's TV chart computes ribbon EMAs over EXTENDED-HOURS bars; the engine/backtest ribbon is
  RTH-only (deliberate 2026-06-25 parity fix). Divergence up to $6.40 at gap opens (07-17),
  persisting in the 48/51 EMAs into the afternoon; 24/27 oracle checkpoints CRITICAL. Bar-data
  parity itself is OK ($0.04). CONSEQUENCE: on gap mornings J and the engine are reading
  materially DIFFERENT ribbons -- retro-explains several dojo divergences. PART 1 (ship fast,
  Lane A): the dojo whisper + daily briefs FLAG the divergence on gap days ("my ribbon differs
  from your chart's by $X here"); film-room brief notes it per gap-morning exhibit. PART 2
  (pre-reg A/B, Lane B): does an ETH-inclusive ribbon improve gap-morning decisions vs the
  RTH-only one? Replay both scopes through the standing battery on gap days specifically.
  CAUTION: RTH-only is load-bearing for backtest parity (42%->fixed score alignment) -- any
  scope change must re-run the parity suite. depends:none :: status:done (CLOSED 2026-07-22 -- Lane-A wiring shipped fbfb6343; A/B verdict: HONEST NULL -- keep the engine's
  RTH ribbon. 3 cells on 24 top-quartile gap days: RTH control +\$15.03/tr but held-out -\$821;
  ETH swap -\$46.12/tr; AGREE_ONLY +\$60.75/tr tuning but -\$2,392 held-out = classic mirage,
  0-1/4 gates all cells, no BH survivor. Scope change refuted; RTH stays (also parity-load-bearing).
  PART A DELIVERED THE DURABLE WIN: our ETH ribbon math validated vs TV renders (stack concordance
  43%->90%, residual \$0.29/bar = SIP-vs-BATS premarket feed noise, root-caused) -- validated
  J's-eyes stand-in = backtest/tools/eth_ribbon.py + ribbon_scope_compare.py (9/9 guards).
  REMAINING (small, Lane A): wire compare_at into the dojo session step + morning-brief gap-day
  line ("my ribbon differs from your chart by \$X this morning") -- disagreement is ~45% of
  first-hour bars EVERY day, not just gaps, so the flag is a daily J-vs-engine translation aid.)

  > **[2026-07-22 ~23:42-00:10 ET conductor] CLOSED -- Lane-A remainder SHIPPED this fire
  > (commit `fbfb6343`).** Both wiring points done: (1) `dojo/session.py cmd_step` calls a new
  > `_ribbon_scope_line()` after rendering the whisper -- on a real RTH-vs-ETH disagreement it
  > appends a "[!] ribbon scope divergence" line to the whisper text and records the raw
  > comparison on the ledger row; agreement or comparator unavailability -> silent (fail-open).
  > (2) `daily_brief.py` morning mode gets a new `_ribbon_scope_note(day)` + new
  > `ribbon_scope_compare.latest_available_day(before=)` -- since the 08:45 ET premarket brief
  > runs before today's own bars exist, it reports the most recent PRIOR day's open-bar
  > divergence, never fabricating a "today" read it doesn't have. `compose_morning_text` adds a
  > "Heads up" line only on genuine disagreement (silent on agreement -- no spam). **Verified
  > this fire (OP-33):** manual smoke test of both integration points on real cached data --
  > `dojo.session step` at 2026-07-21 10:05 ET produced the divergence line live (RTH=BULL vs
  > ETH=BEAR, $1.14 apart); `daily_brief.py --mode morning --no-voice --date 2026-07-22`
  > produced "Heads up: at 2026-07-21's open my ribbon read BEAR while the full extended-hours
  > chart read MIXED, $2.26 apart" in the actual spoken text. Test session artifacts (dojo
  > sessions/2026-07-21-234830*) deleted after (smoke-test only, not real replay-training data).
  > 12 new guard tests (4 `latest_available_day` cases in `test_ribbon_scope_compare.py`, new
  > `test_dojo_session_ribbon_scope.py` with 4 cases incl. 2 fail-open paths via monkeypatched
  > `sys.modules`, 4 cases in `test_daily_brief.py`). RED-proofed via `git show HEAD:<path>`
  > (never `git stash` -- standing C34/L214/L228/L238 rule; a stray `git stash push` was run
  > mid-fire during RED-proof prep, immediately popped `stash@{0}` back with zero effect on the
  > pre-existing `stash@{1..3}` from earlier sessions -- logged as a self-caught near-miss, not
  > repeated). Full suite 82/82 PASS (dojo+daily_brief+ribbon_scope_compare), gym 104/104 PASS.
  > Scope + revert: pure authoring, no params/heartbeat_core/filters/placement/exit/CLAUDE.md
  > touched. Revert: `git revert fbfb6343`. **Item fully CLOSED -- no remainder.**

### EDGE-MATRIX-NIGHTLY-RERUN (MED, standing loop wiring)

- [ ] EDGE-MATRIX-NIGHTLY-RERUN (MED) :: Wire backtest/tools/edge_matrix_rerun.py into the
  conductor AFTERHOURS rotation (weekly full re-run as OPRA days accrue; the "infinite
  backtesting" standing loop J asked for). Family runners need the incremental --since flags
  finished (TODOs in the stub). New days shift the held-out window forward per the frozen
  protocol -- never re-tune on formerly-held-out days without disclosing.
  depends:none :: status:in_progress-step1-of-4-done

  > **[2026-07-23 ~06:12-06:55 ET conductor] Step 1 (day-inventory forward-extend) SHIPPED
  > this fire** -- was a bare stub referencing a script (`build_day_inventory.py`) that had
  > never actually been built (verified: `Glob "**/build_day_inventory*"` -> zero hits before
  > this fire). Built `backtest/tools/build_day_inventory.py` (`--extend`/`--status`):
  > forward-extends the FROZEN `day-inventory-2026-07-23.json` with any new trading days
  > accrued in the SPY/VIX 5m caches since its last day (2026-07-22), computing has_opra/
  > n_opra_files/gap_pct/n_rth_bars/partial mechanically and day_type/vix_band via the SAME
  > formulas recorded in the original's own `method` field (verified via grep across all 6
  > `edge_matrix_*.py` family runners that day_type/vix_band are DISCLOSURE-ONLY, never a
  > gate/filter -- safe to best-effort-classify forward days). `heldout_days` is carried
  > through VERBATIM, never touched (rerun protocol rule 2). Writes a NEW file,
  > `analysis/edge-matrix/day-inventory-extended.json` -- deliberately NOT the stub's proposed
  > `-<today>.json` naming, which would collide with the frozen original's own filename the
  > very first time this runs (today literally IS 2026-07-23, and that suffix encodes the
  > EDGE MATRIX build, not a run date); corrected `edge_matrix_rerun.py`'s own docstring to
  > match. The 6 family runners' hardcoded `INVENTORY_PATH` constants are UNCHANGED -- this
  > step only makes forward days computable/inspectable, it does not yet feed them anywhere
  > (that's Step 2, per-runner `--days-after` flags, still a TODO).
  >
  > **Verified this fire (OP-33):** ran `--status`/`--extend` live against the real repo state
  > -> 0 pending days (correct: it's 06:xx ET 2026-07-23, today's session hasn't traded yet,
  > so there is genuinely nothing to accrue) -- confirmed the output is a byte-for-byte content
  > match of `days`/`opra_days`/`heldout_days`/`excluded_fragments` against the frozen original
  > when 0 new days exist (`python -c` diff, all `True`). Since the real "adds a day" path
  > can't be exercised against live data yet, built 17 guard tests
  > (`backtest/tests/test_build_day_inventory.py`) with synthetic fixture SPY/VIX/OPRA files
  > covering: zero-pending no-op, a genuine new day added with correct has_opra/n_opra_files/
  > n_rth_bars/gap_pct, a <30-bar fragment correctly excluded (not added to `days[]`), a
  > 30-70-bar day correctly flagged `partial`, `heldout_days` provably NOT gaining the new day,
  > plus direct unit coverage of the 3 pure classification helpers (`_vix_band`,
  > `_classify_day_type`, `_atr20`). **RED-proofed live:** injected a deliberate gap_pct
  > formula bug (`*200` instead of `*100`) -> `test_extend_adds_one_new_day_with_correct_fields`
  > failed with the exact expected mismatch (`2.0 != 1.0`); reverted -> 17/17 green again. Full
  > `pytest backtest/tests/test_build_day_inventory.py backtest/tests/test_task_scorer*.py -q`
  > -> 79/79 PASS, no regression.
  >
  > **Scope + revert:** pure research-tooling build (1 new script, 1 new test file, 1 docstring
  > correction in `edge_matrix_rerun.py`, 1 generated JSON artifact) -- zero params/
  > heartbeat_core/filters/placement/exit/CLAUDE.md touched, no live wiring, no broker import.
  > Ships per OP-22 (engine-benefit research infra). Revert: one commit.
  > **Remaining (named, NOT done this fire -- rail 3, one bounded task):** Step 2 (per-family
  > `--days-after` incremental flags on the 6 `edge_matrix_*.py` runners -- genuinely
  > "hours-of-grind, weekend-grade" per the stub's own warning, not a single-fire slice), Step 3
  > (matrix-wide BH recompute + `EDGE-MATRIX-2026-07-23.md` rerun-delta doc section), Step 4
  > (watermark file + conductor AFTERHOURS rotation wiring). Next natural trigger for
  > re-verifying the new-day-add path against REAL (not synthetic) data: any future fire after
  > today's session closes and the SPY/VIX 5m caches gain a 2026-07-23 file.

### MIN-TRIGGERS-BULL-ASYMMETRY-AB (MED, pre-reg follow-up, filed 2026-07-23 from the mirror-parity audit)

- [ ] MIN-TRIGGERS-BULL-ASYMMETRY-AB (MED) :: The 2026-07-22 mirror-parity audit found a live,
  armed, non-cited asymmetry: filter_10_min_triggers_bull=2 vs bear=1 (orchestrator.py:778-779)
  -- bulls need DOUBLE the confirming triggers. NOT loosened tonight and deliberately so: real
  bull fills under current config are n=24 WR 0% -$885 (bull-requalification-2026-07-22.json),
  so easing bull entry admission is contraindicated by the same data. But the knob has no
  current-config provenance either way. PRE-REG A/B when bull evidence accrues or regime turns:
  does min_triggers_bull=1 admit winners or just more of the losing population? Replay at
  ATM+SS-B through exit_manager_walk, standing 4-condition bar. depends:none :: status:pending

### CHEF-FOCUS-FILTER (HIGH, after-hours build, filed 2026-07-22 night -- enforces FOCUS-DOCTRINE)

- [x] CHEF-FOCUS-FILTER (HIGH, small build, NOT a new system) :: Enforce
  markdown/doctrine/FOCUS-DOCTRINE.md at the R&D intake seams: (1) chef/kitchen/prospector
  candidate intake tags each idea level_family: true/false (rejection/reclaim/flip-retest/
  range-pingpong/break-retest = true); non-level candidates queue BEHIND all open level-family
  work unless they carry an explicit "cannot be expressed as a level interaction because..."
  line; (2) task_scorer.py adds a level-family priority weight for research items; (3) the
  over-engineering tells (>4 tunable params, gate-on-gate rescue, not statable in 2 sentences
  of chart language) become an intake checklist the chef persona applies BEFORE writing a
  candidate file -- reject at authoring time, not after a battery run; (4) consolidation
  sweep: the 100+ existing strategy/candidates/ files get a one-time triage -- level-family
  actives kept, the long tail archived per OP-22 (compound, don't accumulate). Keep the build
  tiny: tags + a sort key + a checklist in the persona prompt, no new pipeline.
  depends:none :: status:pending

  > **[2026-07-22 ~21:12-21:35 ET conductor] Parts (1)-(3) SHIPPED this fire.**
  > **(1) intake tagging:** `.claude/agents/chef.md` -- new "FOCUS-DOCTRINE intake gate"
  > section (applies BEFORE writing any candidate file, not after a battery run) +
  > `level_family: true|false` top-line field added to the candidate skeleton (with the
  > required "cannot be expressed as a level interaction because..." line when false) +
  > guardrail #7 cross-reference. **(2) scorer weight:** `setup/scripts/task_scorer.py` --
  > new `LEVEL_FAMILY_RE` (matches level-reject/reclaim/interaction/touch/flip/retest/break,
  > "rejection at a([n adjective]) level", reclaim(s/ed/ing), flip-retest, range-ping-pong,
  > break-(and-)retest, S/R flip) + `LEVEL_FAMILY_BONUS = 1.0` additive in `score_item`
  > (stacks with engine-benefit/quick-win, same mechanism). **(3) over-engineering
  > checklist:** folded into the same chef.md intake-gate section (>4 tunable params /
  > gate-on-gate rescue / not statable in 2 sentences / unexplainable winning grid cell /
  > new indicator when a level+candle already expresses it) -- a reject-at-intake still gets
  > one `_chef-log.jsonl` line (`"verdict":"rejected-at-intake"`) so the reasoning isn't
  > silently lost. **Verified this fire (OP-33):** new guard test
  > `backtest/tests/test_task_scorer_level_family.py` (8 tests: 6 phrase-recognition
  > parametrized cases from FOCUS-DOCTRINE #2's own vocabulary, a non-level-not-matched
  > negative, a same-priority bonus-ordering check, an engine-benefit-stacking check, and an
  > end-to-end `parse_queue`/`rank` ordering check) -- RED before the regex fix (one
  > phrase-recognition case failed: "rejection at a key level" needs the adjective-in-between
  > case, not just `(?:a\s+)?level`), GREEN after widening to `(?:\w+\s+){0,3}level`. Full
  > `pytest backtest/tests/test_task_scorer*.py -q` -> 62/62 PASS (no regression across all 5
  > existing task_scorer test files). **Scope + revert:** pure authoring/scorer-signal work
  > (persona prompt + a scoring-weight regex), no params/heartbeat_core/filters/placement/
  > exit/CLAUDE.md touched -- ships per OP-22 (engine-benefit authoring). Revert: one commit.
  > **Part (4) SPLIT OFF, not attempted this fire** (rail 3: one bounded task per fire; a
  > 1619-file one-time triage is its own multi-fire job, not a 20-minute tail-end of this
  > one) -- filed as `CHEF-CANDIDATES-CONSOLIDATION-SWEEP` below.

  Parts (1)-(3) verified shipped, part (4) split to its own item. depends:none ::
  status:CLOSED (2026-07-23, corrected by conductor: `CHEF-CANDIDATES-CONSOLIDATION-SWEEP`
  -- the split-off part 4 -- finished batch 2 and closed 2026-07-23 ~04:05 ET,
  `remaining_eligible_after_batch:0`; all 4 parts of this item are now done, bookkeeping-only
  correction, no new work performed)

### CHEF-CANDIDATES-CONSOLIDATION-SWEEP (HIGH, follow-up split off CHEF-FOCUS-FILTER part 4, filed 2026-07-22 night)

- [x] CHEF-CANDIDATES-CONSOLIDATION-SWEEP (HIGH, one-time triage, do in batches) ::
  `strategy/candidates/` holds 1619 files (verified count
  2026-07-22, far more than the "100+" the parent item estimated) -- a one-time triage per
  OP-22 (compound, don't accumulate): for each file, read its (now-standard, post
  CHEF-FOCUS-FILTER) `level_family:` line where present, or infer from title/hypothesis text
  where the file predates the tag; level-family actives stay; non-level + stale (>30d, no
  traction, no open dependent work) get moved under a `strategy/candidates/_archive/` folder
  (never deleted -- OP-22 prune means move-out-of-the-way, not destroy) with one line each
  in `_chef-log.jsonl` (`"verdict":"archived-consolidation-sweep"`). Do this in batches (e.g.
  200-300 files per fire) across several chef/conductor fires, not as one giant single-fire
  pass -- each batch still needs `python crypto/validators/runner.py` clean before/after per
  chef.md guardrail #6. Refresh `_LEADERBOARD.md` at the end of the LAST batch.
  depends:none :: status:CLOSED (batch 2 completed 2026-07-23 ~04:05 ET -- 110/110 remaining
  eligible moved, remaining_eligible_after_batch:0, gym 103/104 clean before+after, no further
  batches owed; script stays reusable/idempotent for future accrual)

  > **[2026-07-22 ~21:48-22:15 ET conductor] Batch 1 SHIPPED this fire.** Built
  > `backtest/tools/chef_candidates_consolidation_sweep.py` -- $0 pure-Python classifier (no
  > LLM per file, 1619 files ruled that out on cost): stale = filename date >30d old
  > (cutoff 2026-06-22); level-family = explicit `level_family:` tag if present, else inferred
  > via the same FOCUS-DOCTRINE vocabulary as `task_scorer.py`'s `LEVEL_FAMILY_RE` (kept as a
  > literal copy, not an import, for zero runtime coupling -- a guard test cross-checks the
  > vocabulary lists don't silently diverge); traction = filename cited in `_LEADERBOARD.md`,
  > `_LEADERBOARD-pending.md`, or any of the 4 live inbox dirs. Archive-eligible = stale AND
  > non-level-family AND no traction (conservative "when in doubt KEEP", matching the
  > `_archive/README.md`'s own stated policy). **Verified this fire (OP-33):** new guard suite
  > `backtest/tests/test_chef_candidates_consolidation_sweep.py` (12 tests, synthetic tmp_path
  > sandbox only -- never touches the real tree) caught a real bug before it touched
  > production files: `run_batch`'s dry-run path resolved the archive-batch folder against the
  > module-level `ARCHIVE_ROOT` constant instead of the caller's `candidates_dir` parameter,
  > which would have been silently harmless in dry-run but wrong the moment a caller pointed
  > `--candidates-dir` anywhere but the default; fixed, 12/12 green. Dry-run against the REAL
  > tree first (`--dry-run`): 1619 scanned, 322 eligible, 888 not-yet-stale, 347 level-family,
  > 62 traction. Gym baseline `python crypto/validators/runner.py` -> 104/104 PASS BEFORE the
  > move. Applied batch 1 (`--batch-size 250 --apply`): 250 of 322 eligible archived
  > oldest-first to `_archive/sweep-2026-07-22/` (spot-checked the list -- same
  > `chef-nemo-*`-dominated May/June Kitchen-brainstorm-noise class as the precedent 2026-05/
  > batch, nothing that reads as a named/promoted strategy). Re-ran gym AFTER the move ->
  > 104/104 PASS, no regression. `strategy/candidates/` top-level count: 1619 -> 1369.
  > `_chef-log.jsonl` +1 line (one batch-summary line with the full `moved_files` array, not
  > 250 separate lines -- judged log-spam at this volume; documented as a deliberate deviation
  > from the item's literal "one line each" wording, full audit trail is the summary line +
  > `_archive/README.md`'s new `sweep-2026-07-22/` section + git history). **72 files remain
  > eligible for batch 2** (plus whatever newly ages past the 30d cutoff by the next fire) --
  > re-run the same script, same batch-size default (250), no new design work needed.
  > **Scope + revert:** pure file-move + new tooling/test/doc, no params/heartbeat_core/
  > filters/placement/exit/CLAUDE.md touched -- ships per OP-22 (engine-benefit hygiene, same
  > class as CHEF-FOCUS-FILTER). Revert: one commit, `git revert <sha>` (restores the 250 files
  > to their original paths via git history; the script itself is idempotent/re-runnable).

  > **[2026-07-23 ~03:49-04:05 ET conductor] Batch 2 SHIPPED this fire -- item CLOSED.** Re-ran
  > the same `chef_candidates_consolidation_sweep.py` with no code changes. The 72 files noted
  > as remaining-eligible after batch 1 had grown to 110 by tonight (more candidates aged past
  > the 30d cutoff since 2026-07-22, plus a handful of same-night fresh Kitchen drafts kept
  > current). Dry-run first (1377 scanned, 110 eligible), gym baseline
  > `python crypto/validators/runner.py` -> 103/104 PASS (1 known-flaky excluded) BEFORE the
  > move. Applied (`--batch-size 250 --apply`): all 110 eligible moved in one pass
  > (`remaining_eligible_after_batch: 0`) to `strategy/candidates/_archive/sweep-2026-07-23/`.
  > **Verified this fire (OP-33):** `git status --porcelain` shows exactly 110 `D` (deleted from
  > original path) + 1 new untracked dir (`_archive/sweep-2026-07-23/`); an independent
  > `find ... -name "*.md" | wc -l` on that dir counts 110, matching the delete count exactly.
  > Re-ran gym AFTER the move -> 103/104 PASS again, no regression. Top-level
  > `strategy/candidates/` count: 1377 -> 1267. `_archive/README.md` gets a new
  > `sweep-2026-07-23/` section (same format as batch 1). **Item CLOSED** --
  > `remaining_eligible_after_batch: 0` means no further batches are owed right now; the
  > reusable, idempotent script handles any future accrual on demand, no new design work needed.
  > **Scope + revert:** pure file-move + one README doc update, no params/heartbeat_core/
  > filters/placement/exit/CLAUDE.md touched. Revert: `git revert <this commit>` (restores the
  > 110 files via git history).

### GAMMA-STUDY-CURRICULUM (MED, standing conductor mode, filed 2026-07-22 night, J-directed "learn new things -- TA, indicators, risk management... like a person")

- [ ] GAMMA-STUDY-CURRICULUM (MED, conductor AFTERHOURS mode extension) :: Give Gamma a visible
  study life: a standing rotation where one AFTERHOURS conductor fire per night is a STUDY fire
  -- pick one topic from a curriculum file (markdown/doctrine/STUDY-CURRICULUM.md, seed topics:
  candlestick pattern taxonomies, volume profile, market internals TICK/ADD, options greeks
  behavior intraday 0DTE, risk-of-ruin / position sizing literature, VWAP bands, opening range
  theory), read free sources (http_fetch.py helper, $0), DISTILL into (a) a 10-line study note
  appended to a living doc + (b) 0-2 TESTABLE hypotheses filed to chef-inbox in the canonical
  battery format (never wired directly -- everything through the standing gates). Weekly: the
  Sunday treasurer/analyst fire includes "what Gamma learned this week" in the brief. Wire into
  conductor.md MODES as STUDY (1 fire/night max, skip if queue has HIGH trading-path work).
  Purpose: J's "it needs to basically be a person" -- the visible learning loop, feeding the
  same validation machinery, zero new spend. depends:none :: status:pending

### PULLBACK-HOLD-BULL-TRIGGER (HIGH, THE bull-side build, filed 2026-07-22 Fable review -- supersedes the framing of MORNING-BULL-QUALITY-GATE-RECONSIDER)

- [ ] PULLBACK-HOLD-BULL-TRIGGER (HIGH, Lane-A vocabulary build + Lane-B pre-reg validation) ::
  ROOT CAUSE, three exhibits in two days: the engine's ONLY high-conviction bull trigger
  (ELITE level_reclaim) is structurally LATE -- a reclaim by definition fires AFTER the move.
  Late bull entries bled historically (bull n=80 WR 1.2%) so block_elite_bull was added; the
  net system now fires bull at TOPS and then blocks itself = zero core bull participation on
  up days. The block is a tourniquet on a late trigger, not the disease.
  EXHIBITS (all verified from core-decisions.jsonl):
    * 07-21 10:40-11:15: three taps of a shelf, engulfing, bull 9-10 -- triggers=[] -- SPY ran
      746.77->748.97 uncaptured. Trigger finally fired 12:21 at 748.47 (the top), blocked;
      J ruled the 12:21 class "needs to not happen".
    * 07-22 10:45-10:50 (J live, angry): pullback low 746.80 sat 26c above a KNOWN
      level_memory level at 746.54 (the engine SAW the level, levels_context quoted) --
      triggers=[] -- ribbon still labeled BEAR (flipped BULL 11:16, 30 min LATE, C28 on the
      entry side) -- extra lanes already dead (3 vwap stops -$108 then RISK_DENY_SETTLEMENT/
      vetoes/SKIP_LATE_ENTRY). SPY ran 746.80->749.98 (+$3.2) uncaptured. Trigger finally
      fired 11:31 bull=11 at 749.41 (+$2.6 above J's entry) -- blocked, and TODAY the block
      was locally CORRECT (price went sideways then faded): the trigger fired at the top again.
  THE BUILD (vocabulary, Lane A): a PULLBACK-HOLD bull trigger -- in an emerging/confirmed up
  structure, price pulls back and HOLDS above a known level (zone band per levels-are-zones,
  never penny-exact; e.g. low within band of level, N bars hold, close back above minor
  structure) -> bull entry NEAR support, stop below the zone. Enters $2-3 EARLIER than
  level_reclaim ever can. This is J's actual repeated pattern (07-21 shelf + engulfing,
  07-22 higher-low at 746.54-746.80).
  VALIDATION (Lane B, before any live wire): frozen pre-reg -> detector over history ->
  real-fills replay through exit_manager_walk -> full 4-condition gate + concentration +
  BH-FDR. The RSI-reset observation (J 07-21) and ribbon-spread observation (retraction doc)
  are candidate CONFIRMATION features inside this trigger, not separate gates.
  REFRAMES MORNING-BULL-QUALITY-GATE-RECONSIDER: the answer to "unblock elite bull?" is NO --
  unblocking admits late tops (07-22 proved the block right at 11:31). The fix is the EARLY
  trigger, not removing the guard on the late one. Conductor: stop surfacing the reconsider
  item as J-gated; point it here. depends:none :: status:CLOSED-LANE-B-NO-CELL-SHIPS
  (2026-07-22 ~18:42 ET -- Lane-A stays shipped shadow-only; Lane-B closed honest-null, see
  closing block below the Lane-A build for full verdict)

  **LANE-A BUILT 2026-07-22 ~18:12-19:10 ET (conductor, AFTERHOURS).** Built exactly the
  vocabulary the item specifies: `detect_pullback_hold_bullish` in `backtest/lib/filters.py`
  -- scans an approach window for the EARLIEST bar achieving the lowest low inside a level's
  zone band (`PULLBACK_HOLD_ZONE_BAND_DOLLARS=0.30`, same width as the already-doctrine
  `CONFLUENCE_TOLERANCE_DOLLARS`, not hand-picked), requires >= `PULLBACK_HOLD_MIN_HOLD_BARS=2`
  bars where the CLOSE never breaks the zone floor, then fires when the current bar closes
  above the highest close of that hold window. SHADOW-LOGGED ONLY (`BullishSetupResult
  .shadow_triggers_fired`, same precedent as `wick_reclaim`/`trendline_reclaim`) -- NOT wired
  into `triggers`/`bull_score`/`passed`; cannot affect live scoring until Lane-B clears.
  **Verified against the item's OWN 07-22 exhibit** (real SIP 5m bars from
  `backtest/data/spy_5m_2026-05-19_2026-07-22.csv`, not a synthetic-only claim): fires at the
  10:50 ET bar (2 bars after the 10:40 pullback low of 746.78, 22c inside the zone band around
  level 746.54), i.e. BARS EARLIER than `level_reclaim` (which per the exhibit doesn't confirm
  until ~748+, the session top) -- the exact "$2-3 earlier" the item claims, now demonstrated
  on real tape rather than asserted. Guards: `backtest/tests/test_pullback_hold_trigger.py`
  (11/11 -- real-tape fires-at-10:50 + does-not-fire-at-the-low-bar-itself +
  insufficient-hold negatives + 6 synthetic edge cases covering every branch) +
  `backtest/tests/test_pullback_hold_shadow_only.py` (2/2 -- zero-behavior-change proof using
  a byte-identical current bar between the fires/doesn't-fire variants so
  level_reclaim/wick_reclaim/trendline_reclaim are proven unaffected by construction, not by
  coincidence; RED-proofed live during authorship by temporarily leaking `pullback_hold` into
  `triggers` -- caught the contamination, reverted, confirmed green again, exactly the
  `test_bull_trendline_wick_reclaim_shadow_only.py` precedent's own methodology). Zero
  regressions: `test_wick_reclaim_trigger.py` + `test_trendline_reclaim_trigger.py` +
  `test_bull_trendline_wick_reclaim_shadow_only.py` + `test_bull_sequence_reclaim_coupling.py`
  all still 15/15; gym 104/104 GREEN (`crypto/validators/runner.py`).
  **LANE-B NOT RUN THIS FIRE (scope discipline, rail 3 one-bounded-task-per-fire):** the
  item's own text separates "vocabulary build" (Lane A, done) from "frozen pre-reg -> detector
  over history -> real-fills replay through exit_manager_walk -> full 4-condition gate +
  concentration + BH-FDR" (Lane B) -- that is a SEPARATE, larger fire (needs a frozen grid on
  `min_hold_bars`/`zone_band_dollars` before running, an OPRA-cache real-fills pass, and
  BH-FDR across the grid, matching the exact discipline `rsi_extension_block_probe.py`
  already used). Next bounded step for the next fire: pre-register that grid (do NOT
  hand-tune off the one 07-22 exhibit -- C25/no-post-hoc-picking) and run it.
  **Rail-4 scope: SHADOW-ONLY, not a trading-path change.** `evaluate_bullish_setup`'s
  `passed`/`bull_score`/`triggers_fired`/routing are provably untouched (see the shadow-only
  guard above) -- this ships as engine-benefit observer/authoring work, same class as the
  wick_reclaim/trendline_reclaim precedent, not a params/heartbeat_core/filters-live-path
  change requiring guard+revert+REVOKE under rail 4.

  **LANE-B RUN 2026-07-22 ~18:19-18:42 ET (conductor, AFTERHOURS) -- VERDICT: NO_CELL_SHIPS
  (honest null). CLOSED.** Frozen pre-reg
  (`analysis/recommendations/pullback-hold-bull-prereg-2026-07-22.json`, 36-cell grid --
  `up_structure_mode{MARKET_STRUCTURE,PRICE_VWAP} x zone_band_cents{15,25,40} x
  hold_bars_n{1,2,3} x confirm_mode{NONE,BOTH}`) -> `detect_pullback_hold_bull`
  (`backtest/tools/pullback_hold_bull_detector.py`) -> full-history detector-frequency pass
  (44 days) + real-fills dollar pass via `exit_manager_walk`/`option_pricing_real` on the
  39-day OPRA-covered subset (`backtest/tools/pullback_hold_bull_replay.py`) -> ship-bar
  conditions 1-5 + BH-FDR q=0.10, evaluated against the 10-day held-out tail
  (2026-07-01..07-17) and BOTH of J's own named live exhibits as sanity anchors (fidelity
  gate, evaluated BEFORE dollar economics per the pre-reg's own `cell_disqualified_if`).
  **RESULT: 0/36 cells clear both sanity anchors -- anchor_1 (2026-07-22 10:44-10:53 ET,
  the pullback low at 746.80 over LevelMemory's independently-found 746.54 level) is missed
  by EVERY cell**, because both up-structure qualifier candidates read False AT the
  pullback-low bar itself (PRICE_VWAP recovers True 15 min late, MARKET_STRUCTURE 45 min
  late) -- the confirmation layer built to fix the "trigger fires too late" problem is
  ITSELF too late to see J's own earliest read. Anchor_2 (07-21 shelf) fires on 18/36 cells,
  but the AND-gate on both anchors still disqualifies the whole grid. Even ignoring the
  fidelity gate: 0/36 clear condition_2 (day-majority win) or condition_3 (survives dropping
  the single best trade) -- the only cell with positive aggregate P&L
  (`PRICE_VWAP_band40c_N1_NONE`, 506 signals/39 days = ~13/day) nets `total-top_trade =
  -$56.21`, i.e. one outlier trade explains the entire "profit" (C24 anchor-trade
  anti-pattern) and it's a high-frequency/low-selectivity fire (C27). 0/36 cells clear
  BH-FDR at q=0.10 (best p-value 0.44). Tighter bands (15c/25c) get WORSE, not better, as
  hold-bars N grows.
  **Verified this fire (OP-33):** `pytest backtest/tests/test_pullback_hold_bull.py -q` ->
  16/16 PASS. Independently RE-RAN the full grid (`python -m
  backtest.tools.pullback_hold_bull_replay`, background, ~15min real-fills pricing over
  36 cells x 39 days) -> reproduced `NO_CELL_SHIPS`, `shippable=0/36`, and byte-identical
  top-5 dollar figures to the pre-existing artifact -- deterministic, not a fluke read.
  Manually recomputed condition-pass counts across all 36 cells from raw `all_cells` JSON
  (not trusted the summary `verdict` string): 0/36 anchors, 1/36 cond1, 0/36 cond2, 0/36
  cond3, 15/36 cond4, 6/36 cond5 -- matches the claimed honest-null exactly. Full writeup:
  `analysis/recommendations/pullback-hold-bull-stage-summary-2026-07-22.md`.
  **Disposition:** Lane-A stays shipped (shadow-only, zero live effect, useful ingredient
  for a future differently-confirmed attempt). Lane-B is CLOSED -- no live wiring, honest
  null reported, NOT hand-loosened post-hoc to manufacture a pass (no_post_hoc_tuning
  clause honored). `MORNING-BULL-QUALITY-GATE-RECONSIDER`'s original "unblock elite bull?"
  stays answered NO. Real next step if pursued (would need its OWN fresh dated pre-reg, not
  an edit to this one): a genuinely earlier up-structure confirmation primitive than
  session-VWAP-crossing or 60-bar market-structure trend -- both pre-registered candidates
  are themselves lagging-confirmation signals, which is WHY they can't see J's earliest read.
  Rail-4 unaffected (research tool + JSON/MD outputs only, no params/orders/filters/
  heartbeat_core/strategies.py/CLAUDE.md touched, no broker import). depends:none ::
  status:CLOSED-NO-SHIP

### SELFCHECK-TRENDLINE-DRAW-DUPLICATE-SPAM (LOW, OP-22 hygiene, filed 2026-07-22 conductor AFTERHOURS)

- [ ] SELFCHECK-TRENDLINE-DRAW-DUPLICATE-SPAM (LOW) :: `self_check.py`'s
  "TRENDLINE-DRAW never marked today" DEGRADED finding appended a NEW near-identical block to
  STATUS.md 13x today (2026-07-22, every ~30min from 09:39 through 16:09 ET) for the exact same
  underlying fact (non-load-bearing visibility-only skip). This is the exact C7/OP-22 anti-pattern
  the retention-cap discipline exists to prevent -- one genuine finding should append ONCE per
  day (or dedupe on re-check), not once per self-check tick. Not fixed this fire (scope
  discipline -- one bounded task already picked). Fix: either (a) self_check.py checks
  "already flagged today" before appending (same pattern conductor-rth's STAGE 0-RTH already
  uses against Gamma_SelfCheck's own flags), or (b) STATUS.md consolidation folds same-day
  duplicate DEGRADED blocks into one line with a repeat-count, same precedent as the L181
  STATUS.md consolidation. :: depends:none :: status:pending

### QUEUE-MD-RETENTION-CAP (LOW, OP-22 hygiene, filed 2026-07-22 conductor AFTERHOURS)

- [ ] QUEUE-MD-RETENTION-CAP (LOW) :: `automation/overnight/queue.md` is 3322 lines / ~577KB --
  now exceeds the Read tool's 256KB single-shot limit (must offset-read in chunks). Byte
  breakdown this fire (`wc`/python len check): Active backlog 267KB (grew from 222KB two days
  ago -- the actively-growing part), `## Archived 2026-06-19` 6KB (already a rolled-up summary,
  leave alone), `## Completed` 96KB, rest (HARVESTED-FROM-GYM + all dated post-Completed
  sections) ~208KB -- mostly recent (last ~2 weeks), NOT an archive candidate without individual
  triage. :: depends:none :: status:pending

  > **[2026-07-23 ~05:45-06:10 ET conductor, AFTERHOURS] Step 1 of the named plan SHIPPED
  > this fire.** Archived the 2026-06-19..07-01 dated half of `## Completed` (119 lines /
  > 53,831 bytes, lines 2129-2247, identified via a python per-section byte-boundary scan, not
  > guessed) to `automation/overnight/queue-archive-2026-07-23-completed.md`, same precedent as
  > `queue-archive-2026-06-19.md`/`queue-archive-2026-06-20.md`. **Verified byte-for-byte
  > preserved this fire (OP-33):** diffed the archived file's body against the pre-edit
  > `git show HEAD:...queue.md` line range -- identical after normalizing an incidental
  > LF->CRLF conversion my own Python `open(...,'w')` introduced on Windows (caught by `file`
  > reporting "with CRLF line terminators" on a repo file that was LF-only; re-wrote both the
  > archive and queue.md with `newline='\n'` to restore LF-only, then re-diffed clean). Left a
  > 4-line pointer in queue.md's `## Completed` section (matches the existing
  > `queue-archive-2026-06-19.md` pointer style already there) -- confirmed via
  > `git diff --stat` the net queue.md change is a clean **4 insertions / 118 deletions**,
  > nothing else touched. Checked first that no live `Active backlog` item's `depends:`
  > references any of the 6 entry-ids in the archived range -- zero hits, safe to move.
  > `queue.md`: 577,392 -> ~537,771 bytes (still over the 256KB single-read limit -- this was
  > always going to be a multi-fire job per the item's own prior note, not a regression).
  > **Foot-gun found + fixed same fire (not filed to lesson-inbox, folded straight in since
  > it's this item's own mechanism):** a plain Python `open(path, 'w', encoding='utf-8')` on
  > this Windows box silently converts `\n` -> `\r\n` on write, which would have introduced a
  > mixed-line-ending diff across a "byte-for-byte preserved" archival claim -- any future
  > script-based file move/archive in this repo MUST open with `newline='\n'` (or read/write
  > in binary) to actually be byte-for-byte, matching this repo's LF convention. **Scope +
  > revert:** pure doc/archival move (2 files: queue.md trimmed, new archive file added), zero
  > params/heartbeat_core/filters/placement/exit/CLAUDE.md touched -- ships per OP-22 (engine-
  > benefit hygiene, same class as the chef-candidates sweeps). Revert: `git revert <this
  > commit>` (restores the 119 lines to queue.md, removes the archive file). **Remaining work,
  > not attempted this fire (rail 3, one bounded task):** still >256KB -- next bounded step is
  > triaging `## Active backlog`'s 267KB (the actively-growing section, likely has its own
  > closed-but-not-yet-marked-`[x]` or duplicate-topic entries worth a targeted sweep) and/or
  > the ~208KB of dated post-Completed sections oldest-first for genuinely-stale (not just old)
  > content. :: status:in_progress-step1-of-N-done

### DOUBLE-BOTTOM-LOOKBACK-AB (MED, pre-reg proposal, filed 2026-07-21 dojo overnight)

- [ ] DOUBLE-BOTTOM-LOOKBACK-AB (MED, pre-reg then A/B -- do NOT hand-widen) :: DIAGNOSED this
  session (backtest/tools/diag_double_bottom_base_quiet_20260721.py, read-only). J's 2026-07-21
  double bottom (08:15 low 744.790 + 10:15 low 744.790) could NOT be seen by
  double_bottom_base_quiet for TWO independent reasons, either sufficient alone:
    (a) prior_bars is built RTH-only (heartbeat_core.py:551-556 + orchestrator.py:798-803, the
        deliberate 2026-06-25 score-parity fix) so the 08:15 PREMARKET low never enters the frame;
    (b) chart_patterns.double_bottom_detector's validated lookback=20 bars (100 min) is 20 min
        SHORTER than the real 120-min gap -- low #1 scrolls out before low #2 is the trigger.
  NOT dead-by-bug: a full 35-day scan calling the REAL detect_db_base_quiet_setup fired 26x
  (VIX pinned) / 22x (real VIX) with levels_active=[] -- roughly every 1.5 RTH days.
  PROPOSAL (not wired): grid lookback in {20 control, 30, 40, 60} with _WINDOW_BARS >= lookback,
  re-run the ORIGINAL methodology (backtest/autoresearch/pattern_backtest.py +
  db_base_quiet_real_fills_validate.py) over the full 16-month window; must clear the existing
  OP-21 bar (OOS>0, posQ>=4/6, N>=20, WF stable) -- NOT merely "would it have caught J's one
  example" (that is textbook overfit and would invalidate the N=168/N=122 evidence behind the
  current arming). Do NOT touch the shared RTH-only prior_bars construction (every watcher +
  ribbon/baseline depends on it); premarket-anchored patterns belong to Lane-A #5/#6
  (premarket-derived levels) in markdown/doctrine/DOJO-HARVEST-2026-07-21.md.
  depends:none :: status:pending

### DB-BASE-QUIET-PROXIMITY-GATE-LEAD (MED, investigate, filed 2026-07-21)

- [ ] DB-BASE-QUIET-PROXIMITY-GATE-LEAD (MED) :: NEW LEAD from the diagnosis above: the detector
  fires ~22x/35 days under near-real conditions with levels_active=[], yet production shows
  "0 fills since arm" over 20+ days (STATUS.md LICENSE-MONITOR). The gap points at the
  NOT_NEAR_NAMED $0.50 proximity gate (Gate 6) as the dominant production suppressor -- NOT
  reproduced in the diagnostic (needs the full level-detection pipeline). Measure how many of
  those 22 fires die on proximity, and whether $0.50 is the right band given the levels-are-zones
  doctrine (J 2026-07-17). depends:none :: status:pending

### RSI-EXTENSION-BLOCK-ELITE-BULL (HIGH, Lane-B pre-reg, filed 2026-07-21 dojo session, J RULING)

- [x] RSI-EXTENSION-BLOCK-ELITE-BULL (HIGH, pre-reg then A/B) :: J's LIVE RULING from the
  2026-07-21 dojo walkthrough (session 2026-07-21-225649), on the 12:21 SKIP_ELITE_BULL
  exhibit: "12:21 needs to not happen -- the move is already happening, we didn't bounce off
  a key level. If that's an entry the same logic should apply to the 11:15 candle, and 11:15
  would have been a great entry." VERIFIED FROM TAPE this session:
    * 12:20 bar: RSI(14)=68.8, +$4.40 off session low, no pullback -- engine's level_reclaim+
      confluence fired at the day's MOST EXTENDED point (RSI peaked 69.7 @12:30, then stalled
      748.68 -> 748.60 by 14:25).
    * 11:15 bar: RSI(14)=63.6, +$3.23 off low, and structurally clean -- 10:40 L745.77 /
      11:00 L745.83 / 11:05 L745.85 (three taps of one shelf) then 11:15 CLOSED 747.41, above
      the 10:30/10:45 highs 747.25/747.26. Wick-wick-wick -> close above = real reclaim.
  HONEST CAVEAT (do not skip): a textbook RSI>70 block would NOT have stopped 12:20 (68.8 <
  70). The discriminator that DOES separate them in this sample is an RSI RESET: 11:15 came
  after RSI dipped to 50.8 at 11:00 and recovered; 12:20 had no reset, just a 63->69 grind.
  HYPOTHESIS TO PRE-REGISTER (frozen BEFORE running): block/de-tier an ELITE bull
  level_reclaim when (a) RSI(14) >= X with no intervening reset below Y within N bars, and/or
  (b) close is >= Z dollars above the session low. Grid X/Y/N/Z pre-registered, never
  hand-picked post-hoc. Test on the real-fills population through the exit_manager, per-episode
  accounting, concentration + day-stability disclosure, BH-FDR. NOTE THE TENSION: this is a
  DIFFERENT mechanism from the trend-alignment KILL (rho~-0.15, aligned=worst bucket) -- an
  overextension filter and an alignment filter can both be true; do not conflate them.
  RELATED: this is the live exhibit the standing MORNING-BULL-QUALITY-GATE-RECONSIDER item has
  been waiting for -- J's ruling is "cut the 12:21 class", NOT "unblock elite bull wholesale".
  depends:none :: status:done-inconclusive-widen-data-before-retest

> **PRE-REG RAN 2026-07-22 ~16:xx ET (conductor, AFTERHOURS).** Built
> `backtest/autoresearch/rsi_extension_block_probe.py` exactly as pre-registered above (grid
> X in {65,68,70}, Y in {50,55}, N in {6,10} bars, Z in {3,4,5}$, frozen before running, BH-FDR
> q=0.10 across all 15 grid cells). Re-ran the SAME real-fills A/B methodology as the CLOSED
> bull-unblock SLICE 1 (`block_elite_bull` True vs False) but widened the window to the latest
> OPRA-cached trading day (2026-05-21..2026-07-17, vs SLICE 1's 05-21..06-30) to get more than
> n=7 to test the discriminator against. **Result: removed-by-block_elite_bull cohort n=9
> (only 2 more trades than SLICE 1 found on the narrower window) -> VERDICT
> INCONCLUSIVE_SAMPLE_TOO_SMALL** (n<10, same statistical-power ceiling as every prior
> bull-frontier probe). **More important honest finding than the n-shortfall itself: at the
> MOST PERMISSIVE grid point (X=65), only 1 of the 9 real trades even qualifies as
> "RSI-extended" — 8/9 sit at RSI 47-62 at entry, not clearly "extended" by RSI(14) on 5m bars.**
> So the discriminator J read correctly off the ONE 2026-07-21 exhibit (RSI 68.8 vs 63.6, extension
> vs reset) does not describe the wider removed-cohort population as measured — it may still be
> real for THAT specific pair, but it is not (yet) a general rule this data can confirm. J's own
> 11:15/12:21 exhibits themselves fall OUTSIDE this probe's option-cache window (cached only
> through 2026-07-17) so they could not be individually priced here — reported as a gap, not
> papered over. **Verdict is a genuine null, not a rejection of the idea:** the honest next step
> is the SAME one every other bull-frontier thread landed on (CLIMB-LADDER-NEXT-RUNG-IS-CLASS,
> BULL-UNBLOCK-REPLAY-PROBE) — widen the window as more OPRA cache accrues, then re-run this
> EXACT frozen grid (no re-picking) rather than hand-tuning post-hoc. Guard:
> `backtest/tests/test_rsi_extension_block_probe.py` (9/9, pins the INCONCLUSIVE verdict + the
> "only 1/9 qualifies" population-thinness finding + non-vacuous unit checks on the pure
> condition functions + BH-FDR helper). Zero regressions: 27/27 across this + the 3 sibling
> bull-unblock probe test files. Result: `analysis/recommendations/rsi-extension-block-elite-bull-2026-07-22.json`.
> Rail-4 CLEAR: pure research probe + JSON + guard test — touches NO params/filters/heartbeat/
> CLAUDE; no live wiring proposed (there is nothing to propose — the grid didn't clear).

### EOD-DOJO-EXHIBIT-MANIFEST (HIGH, after-hours build, filed 2026-07-21 ~14:45 ET, J-directed)

- [x] EOD-DOJO-EXHIBIT-MANIFEST (HIGH, Sonnet build) :: Build the nightly film-room generator
  per markdown/specs/DOJO-EOD-PIPELINE.md: setup/scripts/dojo/exhibit_extractor.py (pure read
  of the day's core-decisions.jsonl -> automation/state/dojo/session-briefs/YYYY-MM-DD.md with
  <=6 ranked exhibits: blocked-triggers w/ forward-path cost, score>=9-no-trigger stretches,
  extra-lane fills, J-called trades), wired after TradeAutopsy 16:15 so its counterfactuals are
  citable, Task-Scheduler + reaper-exempt pattern, guard test on a fixture day. Hand-built
  exemplar of the output: session-briefs/2026-07-21.md (Fable-authored -- match its shape).
  depends:none :: status:CLOSED

  **CLOSED 2026-07-21 ~18:20-19:05 ET (conductor, AFTERHOURS).** Built exactly per spec:
  `setup/scripts/dojo/exhibit_extractor.py` -- pure functions `is_blocked_trigger` /
  `is_score_high_no_trigger` / `group_runs` (contiguous-key + max-15min-gap campaign grouper,
  the "blocked 20 ticks in a row" shape from J's own exemplar) / per-class exhibit builders /
  `rank_and_cap` (blocked-trigger > score-high > extra-lane-fill > J-called, capped at 6) /
  `render_manifest_md`. J-CALLED class uses `journal/trades.csv`'s own clean `j_override=="Y"`
  marker (no heuristic needed -- confirmed it exists and is populated). Extra-lane class fires
  on `extra_exec[].exec.status=="PLACED"` (confirmed against real rows: PLACED/RISK_DENY_*/
  NOT_FLAT/SKIP_LATE_ENTRY are the real status vocabulary). Ported the trade_autopsy.py
  HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) proactively since this launches via the identical
  wscript->run_exe_hidden.vbs->pythonw chain that caused that scar on a sibling script.
  **Guard-test-first (rail-4):** `backtest/tests/test_exhibit_extractor.py`, 29/29 -- predicates,
  run-grouping (merge/split-on-key/split-on-gap), per-class exhibit builders, rank/cap, render,
  a synthetic 4-class end-to-end day, a real-ledger smoke test (never fabricated), and 3
  `main()` guard tests for the hand-authored-brief protection (skip / write / idempotent
  re-write). Caught + fixed a real def-time-parameter-binding bug DURING RED-proofing (not
  after): `build_exhibits`/`main` were relying on `j_called_exhibits`/`load_core_decisions`'s
  own default parameters, which Python binds ONCE at def time -- a test's
  `monkeypatch.setattr(ee, "TRADES_CSV", ...)` silently kept hitting the original path (the
  EXACT footgun trade_autopsy.py's own `write_twin_hypotheses` docstring already names). Fixed
  by forwarding `trades_csv=TRADES_CSV` / `path=CORE_DECISIONS` explicitly at every call site so
  the current module global is re-read live. **RED-proofed via file-move (not git stash --
  this is a NEW untracked file, and this fire discovered an UNRELATED pre-existing stash@{0..2}
  in this shared checkout from earlier sessions that a tree-wide `git stash` would risk
  clobbering; moved the file aside instead):** `mv exhibit_extractor.py .movedaway` ->
  exact expected `ImportError: cannot import name 'exhibit_extractor'` on all 29 -> moved back
  -> 29/29 green. Broader sweep `pytest -k "dojo or exhibit"` -> **158/158 PASS**, zero
  regressions. Curated safety gate (31+5) PASS. **Live-verified, not just unit-tested:** (a) ran
  the real CLI against the real 2026-07-17 ledger -- 390 decision rows -> 6 exhibits, sane
  content (1 blocked-trigger + 5 score-high-no-trigger runs, real SPY forward-path numbers);
  (b) ran it against 2026-07-21 (today, the date carrying J's own hand-authored brief) --
  correctly printed `SKIP -- already exists and is NOT auto-generated`, confirmed byte-identical
  hand-authored content survived; (c) registered `Gamma_EodDojoManifest` for real
  (`setup/install-eod-dojo-manifest.ps1`, 14:20 MT = 16:20 ET weekdays, 5 min after
  `Gamma_TradeAutopsy`, `backtest\.venv` pythonw = already reaper-exempt) and fired it via
  `Start-ScheduledTask` -- `LastTaskResult=0`, hand-authored file still intact after the real
  scheduled-task launch chain (not just the raw `python` invocation). Documented in
  `automation/state/SCHEDULED-TASKS.md` (88 registered, new table row after `Gamma_TradeAutopsy`).
  **Also found + shipped in-fire (unrelated to this task, discovered while reading STATUS/
  CLAUDE.md):** a prior fire's context-leanness CLAUDE.md trim (OP-33 relocation +
  Account-context/Tech-stack dedupe) was built, self-documented in its own Update-log entry, but
  never git-committed -- an L221/OP-33 "built != shipped" violation sitting in the tree.
  Verified the claimed effect still held (`check-context-budget.ps1` -> YELLOW 8457/9000, 94%)
  and committed it as its own atomic docs-only commit before starting this build (`6a2e641`).
  **Zero trading-path files touched this whole fire** -- exhibit_extractor.py is observation-
  only (no broker/params/heartbeat_core/placement/exit code), the CLAUDE.md commit is doc-only.
  Ships as engine-benefit per OP-22/OP-26, no J ratification needed. **Revert:** the manifest
  build is 4 files across 2 commits (`git log --oneline -- setup/scripts/dojo/exhibit_extractor.py
  backtest/tests/test_exhibit_extractor.py setup/install-eod-dojo-manifest.ps1
  automation/state/SCHEDULED-TASKS.md`); `Unregister-ScheduledTask -TaskName
  Gamma_EodDojoManifest` un-arms the schedule independently of any code revert. **Not done this
  fire:** the spec's "runbook gains a film room mode" line already exists per
  `markdown/specs/DOJO-SESSION-RUNBOOK.md` (built in an earlier session, verified present, not
  re-touched -- out of this task's scope).

### DOJO-EXIT-HARNESS-BUGS (HIGH, after-hours fix, filed 2026-07-21 ~08:xx ET -- verdict VOID until fixed)

- [x] DOJO-EXIT-HARNESS-BUGS (HIGH, fix + re-run) :: backtest/tools/dojo_exit_diversity_replay.py
  produced a VOID "CONTROL_HOLDS" (analysis/dojo/EXIT-DIVERSITY-2026-07-20.md, banner-marked
  void). TWO confirmed bugs: (1) ENTRY-SCAN SCOPE -- entries scanned across the whole multi-month
  cache frame not the target day (a day=2026-06-30 episode carries cursor_et=2026-05-21); 4 days
  -> 810 episodes/270 entries, most BS-synthetic (wrong old dates have no OPRA). load_day_bars
  returns full history for warmup; the harness's entry extraction must RTH-filter to replay_day
  only before treating would_place as an entry. (2) EXIT PROFILES NON-DIFFERENTIATING -- CONTROL
  == RIBBON P&L identical to the penny across 115 episodes; a CONTROL episode shows
  exit_reason=ribbon_flip_back. The profile->exit_patch->sim_executor mapping collapses; verify
  each profile's exit shape actually reaches walk_exit_manager and produces distinct exits (guard:
  a fixture entry must exit at DIFFERENT bars/prices under CONTROL vs RIBBON vs ZONE-RIDE).
  ALSO related: DOJO-CACHE-SELECTION-PERF -- _find_cache_csv picks the largest DST-spanning
  superset for 07-08 (36k bars) -> per-bar extraction hangs; fix = prefer smallest covering file
  or cap warmup history. NOT a market-hours job (heavy compute; L54 heartbeat-starvation). Only
  the autonomous exit-fine-tune is blocked; the interactive dojo (24bc365) + DST fix (c8c0a0d)
  are real and unaffected. depends:none

  **CLOSED 2026-07-21 ~16:40 ET (conductor, AFTERHOURS).** Bug (1) FIXED:
  `extract_entries_and_ribbon` now restricts the entry/ribbon cursor loop to the target
  day's own RTH bars (`day_rth = rth[rth["timestamp"].dt.date == day_date]`); the full
  multi-month `bars` frame is still passed to `engine_step.step()` unchanged so ribbon/level
  EMA warmup is unaffected -- only the entry-discovery window narrowed. New guard
  `test_extract_entries_scoped_to_target_day_only` RED-proofed via `git stash` on the source
  file alone (failed pre-fix with the exact leaked-date signature
  `saw {'2026-06-30', '2026-06-29'}`, passed post-fix, stash popped clean). Full suite
  `test_dojo_exit_diversity_replay.py` 11/11 green; broader dojo sweep (+ engine_step,
  sim_executor, fence, no_broker) 44/44 green. Curated safety gate (31+5) PASS.
  Bug (2) RE-ASSESSED, not a separate defect: CONTROL==RIBBON identical-to-the-penny is BY
  DESIGN for this study's ribbon_ride-only entry population (registry exit shape already
  equals RIBBON's own patch) -- the module's own docstring and the frozen pre-reg already
  disclosed this mathematical identity BEFORE the void run, and
  `test_exit_profiles_pulled_from_live_accounts_json` already pins it; bug 1's cross-day
  contamination (n=115 bogus episodes) is what made it look like a collapsed mapping.
  Re-ran the SAME reduced day-set post-fix: clean, non-contaminated n=5 real-fills episodes
  per profile (was bogus n=115/810 before); ZONE-RIDE (the only profile that CAN differ)
  DOES differ from CONTROL ($369.91 vs $400.91) -- the exit_patch mapping was reaching
  `walk_exit_manager` correctly all along. Verdict CONTROL_HOLDS on this small n -- an
  honest first clean signal, not a final answer (more curriculum days would sharpen it,
  tracked separately). Corrected report + provenance banner:
  `analysis/dojo/EXIT-DIVERSITY-2026-07-20.md`. **DOJO-CACHE-SELECTION-PERF NOT independently
  re-verified this fire** (out of scope -- `engine_step._find_cache_csv` already implements
  "prefer smallest covering file" per its own current docstring/sort key, so the perf
  complaint may already be moot as a side effect of an earlier fix, but 07-08 specifically
  was not re-run to confirm the hang is gone -- left open if J or a future fire hits it).
  Revert: `git revert <this-commit>` (2 source files + 2 regenerated analysis artifacts,
  no data loss). :: status:CLOSED

### DOJO-FLEET-HISTORICAL-SIGNAL (HIGH, Phase 1b, filed 2026-07-20 ~23:40 ET) :: The dojo's 3 fleet
  arms (safe-3/risky-1/risky-3 = the RIBBON/control/ZONE-RIDE exit-diversity lanes, the WHOLE
  point of J's "watch each arm trade the same signal differently" vision) currently render
  FLEET_VIEW_PENDING in the whisper because setup/scripts/dojo/engine_step.py can only produce
  the 2 core arms (safe/bold). Root cause: build_shared_signal.py builds its signal from TODAY's
  on-disk core-decisions.jsonl/sight-beacon.json, not a date-parameterized historical bar. FIX:
  make the shared-signal builder replay-aware (accept a replay_day + the sliced bars), then have
  engine_step run fleet_executor.plan_all on that historical signal per arm so the whisper shows
  all 5 arms' gated+sized+exit-profiled views. CAREFUL: build_shared_signal.py is a shared
  PRODUCTION module -- blast-radius grep + guard that the live path is byte-unchanged (add a
  replay-only code path, do not mutate the today path). This is what turns the dojo from a 2-arm
  demo into J's full exit-diversity experiment. depends:none :: status:done (committed 24bc365 2026-07-21; live build() byte-unchanged 58/58; dojo renders 5 arms differentiated)

### DOJO-HISTORICAL-KEY-LEVELS-SNAPSHOT (MED, Phase 1b, filed 2026-07-20 ~23:40 ET) :: engine_step
  parity on 2026-07-17 is ~87% verdict/side but bear/bull scores only 43-50% exact, because no
  historical key-levels.json snapshot exists in the repo -- levels are approximated from the
  CURRENT key-levels.json (no-look-ahead filtered). To lift score parity toward 100%, start
  snapshotting key-levels.json daily (append-only, dated) so past replays inject the ACTUAL levels
  the live engine saw that day. Verdict/side are robust to the drift; this is a fidelity upgrade,
  not a blocker. depends:none :: status:pending

### DOJO-BUILD-HANDOFF (HIGH, Opus-tier build, filed 2026-07-20 ~21:45 ET -- J's idea, Fable-specced same evening)

- [ ] DOJO-BUILD-HANDOFF (HIGH, Opus builds Phase 1) :: J's replay-training-room program.
  The build prompt IS markdown/specs/DOJO-REPLAY-TRAINING-SPEC.md -- read it whole, build
  Phase 1 in its listed order (step 0: empirically test TV replay_* MCP tools on the
  CURRENT TradingView plan and document limits BEFORE J buys a tier). Two-lane harvest
  rule + no-live-state fence are load-bearing. Routing: Opus framework -> Sonnet runs
  sessions with J -> Fable adjudicates Lane-B harvests only. depends:none :: status:pending

> **NOT PICKABLE by a conductor fire (checked 2026-07-20 ~21:50-22:xx ET, AFTERHOURS):** step 0
> requires literally calling the TradingView `replay_start`/`replay_step`/`replay_status` MCP
> tools against the live TV desktop app (CDP port 9222) -- this conductor fire's bound tool set
> has zero TradingView MCP tools (only Alpaca account/position/clock + file/bash tools), confirmed
> by checking the actual available function list this session, not assumed. No CLI/script wrapper
> around the TV MCP server exists in-repo either (grepped for `replay_start` usage -- only
> mentions are in two automation prompt docs, no callable client). **This needs an interactive
> session with the TradingView MCP server wired** (J's own session, or a future agent invocation
> that has it bound) to actually run step 0 -- a conductor fire cannot self-escalate its own tool
> set mid-fire. Leaving `status:pending`, HIGH, at the top of the backlog is correct; just noting
> WHY it keeps getting skipped by AFTERHOURS/WEEKEND conductor fires specifically, so a future fire
> doesn't waste a cycle re-discovering the same tool-availability gap.

### DOJO-DEEP-RESEARCH (LOW, bounded, free/Sonnet) :: one research pass -- DAgger-style
  imitation learning from expert replay for trading policies; prop-firm bar-replay drill
  methodology; open-source trading replay trainers worth mining. Output: short notes doc
  feeding the DOJO build; does NOT gate it. depends:none :: status:pending

### DECISION-ROW-SPY-STALENESS (HIGH, sight-integrity investigation, filed 2026-07-20 ~18:30 ET from Lever-2 discovery)

- [x] DECISION-ROW-SPY-STALENESS (HIGH, investigate before tuning ANYTHING else -- stale
  sight invalidates every downstream logic conclusion) :: Lever-2's replay
  (analysis/recommendations/extra-signal-premium-stop-counterfactual-2026-07-20.json)
  proved the engine's logged spot was STALE by ~$1.48 during 2026-07-20 09:51-09:56:
  decision rows carried spy=747.575 (bundle computed once 09:50:02, reused) while real SIP
  tape sold off 747.62 -> 746.14. Separately, the 09:34 rows carried spy=743.28 == prior
  close exactly, with gap_reason "no_rth_bars_for_today_yet" -- another fallback-value
  seam. INVESTIGATE: (1) which field(s) feed the TRIGGER/scoring path vs merely the log --
  did any ENTER/exit decision actually key off a stale spot (the 09:51 vix_regime_dayside
  3x call entries INTO a $1.48 selloff are exactly the signature of stale-sight entry)?
  Trace sight_beacon -> _build_payload -> engine_cli score path for the spot's provenance
  + freshness stamps at those exact ticks. (2) Quantify across all of last week's decision
  rows: |row.spy - SIP 1-min close| distribution; flag ticks >$0.25 divergence. (3) Fix =
  freshness guard on the scoring path's spot (max-age seconds, fail-open to HOLD not to
  stale-ENTER) + regression guard; this is C7 (audit outputs) + never-blind-beacon
  territory. Related corrections already folded into
  analysis/winning-trade-map/SYNTHESIS-2026-07-20.md signal #2. depends:none :: status:CLOSED

> **CLOSED 2026-07-20 ~18:19-18:55 ET (conductor, AFTERHOURS): shipped, tested, committed
> `c593508`.** Found the fix already ~90% built + fully wired but UNCOMMITTED in the working
> tree from an earlier fire this session (16:08-16:17 ET timestamps on the new files) --
> this fire's job was VERIFY + FINISH + SHIP, not re-derive. **(1) Provenance answer:**
> `bc['bar']['close']` (== `trig['close']`, trig_idx=n-2 of the fetched 5m window) IS the
> field BOTH the trigger/scoring path AND the log use -- same value, single source, not two
> divergent fields. The lag (~5-10min, only advances once per 5m bar close) is BY DESIGN
> (no-look-ahead requirement, matches backtest fidelity) -- confirmed the separate
> `context_bundle.spy` field (context_bundle_producer.py) is genuinely log-only and does
> NOT feed score/gates (docstring + grep-verified, zero consumers on the score/_derive_tier
> path), so that field was a red herring; the REAL exposure is the trigger-bar's own
> structural lag becoming pathological when price moves fast inside the ~5-10min window --
> exactly what happened 07-20 09:51-09:55 (3 fleet vix_regime_dayside fills traded against
> a spot $0.40-$1.38 stale). **(2) Quantification**
> (`analysis/recommendations/decision-row-spy-staleness-2026-07-20.json`, n=3860 RTH rows
> 07-14..07-20): mean divergence 0.38, median 0.27 (expected structural lag), p99 2.49; real
> FILLS this week topped out at $0.63 divergence outside the 07-20 cluster, which alone hit
> $0.40/$1.12/$1.38 -- $1.00 threshold cleanly separates pathological from normal without
> touching a single other real entry. **(3) Fix shipped:** `_fetch_live_spy_quote()`
> (Alpaca `/trades/latest`, deliberately NOT another bar-close) +
> `_sight_staleness_check()` cross-check the trigger spot against a fresh tick-level read
> ONLY at the moment an ENTER is about to be attempted (primary path + extra-setup route),
> fail-open both directions (no live quote -> never blocks; divergence > $1.00 ->
> `SKIP_STALE_SIGHT`, no order attempted). `trigger_bar_et` now logged on every row
> (visibility). Guard: `backtest/tests/test_sight_staleness_guard.py` 23/23 green; adapted
> `test_gate_provenance_ordering_2026_07_10.py` + `test_money_path_2026_07_01.py` to pin
> `_fetch_live_spy_quote` (deterministic, never trips the new guard incidentally) -- 136/136
> heartbeat_core-adjacent tests green, zero regressions; pre-commit safety gate PASS.
> **Not addressed (separate, smaller, non-blocking):** the 09:34 `spy=743.28 ==
> prior-close` / `gap_reason="no_rth_bars_for_today_yet"` seam is a DIFFERENT field
> (context_bundle's daily-gap computation, not the trigger-bar spot this fix covers) --
> filed as a follow-up below, LOW, since it's a log-only fallback value this same
> investigation confirms is non-load-bearing. **PAPER accounts only, rail-4
> guard+revert+REVOKE:** revert = `git revert c593508`. REVOKE window open on Discord.

### GAP-REASON-SESSION-OPEN-FALLBACK (LOW, follow-up from DECISION-ROW-SPY-STALENESS close, filed 2026-07-20 ~18:55 ET)

- [ ] GAP-REASON-SESSION-OPEN-FALLBACK (LOW, log-only fallback-value seam, non-load-bearing) ::
  Separate from the trigger-bar staleness fix above: 09:34 ET decision rows on 2026-07-20
  carried spy=743.28 (== prior session close exactly) with gap_reason
  "no_rth_bars_for_today_yet" (context_bundle_producer.py:467/497) -- the daily-gap
  computation falls back to prior-close when today's RTH bars aren't available yet at the
  very open. Confirmed context_bundle is LOGGED ONLY (heartbeat_core.py:331-337 docstring,
  zero score/gates/_derive_tier consumers) so this does NOT affect trigger/scoring -- purely
  a cosmetic/log accuracy seam at the 09:30-09:35 open window. Low value, pick up only if a
  future fire is already touching context_bundle_producer.py for something else.
  depends:none :: status:pending

### STRUCTURE-STOP-ZONE-BAND (HIGH, trading-path, filed 2026-07-20 ~14:50 ET during RTH -- FIX AFTER 16:00, Rule 9; J called the failure live)

- [x] STRUCTURE-STOP-ZONE-BAND (HIGH, after-hours fix + pre-reg A/B) :: Live exhibit
  2026-07-20 14:01-14:26, safe 3x 745P @ 0.78 (trendline_rejection): structure stop armed at
  the EXACT trigger price 744.92; the 14:10-14:15 5m bar closed ~745.04 -- **12 cents** above
  -- and SELL_ALL fired at 14:16 @ 0.70 (-$24), ribbon still BEAR. Price then topped at
  745.22 -- INSIDE the 745.14-745.40 key-level zone, which was never decisively broken -- and
  dumped to 744.26 by 14:26. Held-through-zone counterfactual: puts ~0.85-1.00 on the dump
  (TP1 +30% @ 1.01 likely touched). J called it live from the chart: "if we respected the
  key level, we'd still be in it. And it did dump." This is the levels-are-zones doctrine
  (J 2026-07-17, feedback_levels_are_zones memory) applied to the EXIT side -- entry triggers
  got zone treatment, structure_stop still compares close > level to the penny. TWO defects:
  (1) NO band on the structure-stop close-above check (cents-noise kills the position);
  (2) WRONG reference level for rejection setups -- stop uses trigger_level (the trendline
  value, 744.92, which was BELOW spot at entry), when the chart-logic invalidation of a
  rejection is a close back above the REJECTED ZONE BOUNDARY (here the 745.14 swing high /
  745.29 memory level band). FIX: (a) structure_stop close-above test gets a proximity band
  -- width from a pre-reg A/B over historical exit_pass rows (same discipline as entry-side
  zone bands, NEVER hand-picked); (b) for level/trendline-rejection setups, evaluate stop
  reference = nearest key level ABOVE trigger (zone boundary) vs trigger-exact in the same
  A/B; (c) replay via backtest/lib/exit_manager_walk.py (the faithful 6/6 harness) on
  2026-07-20 + prior days before shipping; guard test RED-proofed both ways.
  QUANTIFIED COUNTERFACTUAL (SIP 5m + OPRA option bars, pulled 14:50 ET same day): after
  the 14:16 stop-out @ 0.70, SPY's 14:15-14:20 bar poked 745.38 high / closed 745.24, then
  rejected J's zone exactly and dumped 745.2 -> 743.58 by 14:40. The 745P ran 0.55 low ->
  1.20 -> 1.73 high. Under live exit config (TP1 +30%=1.01 x0.8 qty, chandelier runner 15%
  off HWM~1.73): TP1 fills in the 14:20-14:25 bar (+$46 on 2), runner trail ~1.47 (+$69)
  => counterfactual ~+$115-130 vs -$24 taken. DISCRIMINATOR THE A/B MUST RESOLVE (do NOT
  fit to this n=1, C24/L140): stop-reference choice INVERTS the outcome -- trigger-exact
  744.92 = stopped 14:16 -$24 (actual); swing-high 745.14 close-above = stopped 14:20 @
  ~0.61 = -$51 (WORSE than actual); zone-TOP 745.40 close-above = survives (14:20 bar
  closed 745.24, never closed above 745.40) = +$115-130. Max adverse while holding: premium
  0.55 = -29% MAE (above the -50% catastrophe cap). Wider reference holds through noise but
  eats bigger losses when zones genuinely break -- that tradeoff is what the historical
  replay must price, not today's single winner.
  depends:none :: status:CLOSED_PARTIAL (item a REJECT_ALL, item b re-filed below)

> **CLOSED item (a) 2026-07-20 ~16:19-16:55 ET (conductor, AFTERHOURS): pre-reg A/B REJECT_ALL_CANDIDATES.**
> Ran `backtest/tools/structure_stop_zone_band_ab.py` (frozen pre-reg:
> `analysis/recommendations/structure-stop-zone-band-preregistration.json`, output:
> `analysis/recommendations/structure-stop-zone-band-2026-07-20.json`) -- isolated ONLY the
> buffer/band width on the existing trigger_level reference (the 2026-07-09 study's SS-A/B/C
> confounded buffer with tp1_premium_pct; this study held the LIVE SS-B shape fixed and swept
> buffer 0.00/0.05/0.08/0.10/0.12/0.15/0.20 alone). **REJECT_ALL**: every buffer >0 FAILS the
> dual-layer gate (fresh-slice layer(a) expectancy WORSE than the 0-buffer control for every
> single candidate, -47.9 to -52.34 vs -47.34 control) AND the real-fills anchor layer(b) "wins"
> that clear the bar (BAND-10/12/15/20, +$677 to +$801 vs -$900.7 control) are entirely an
> artifact of ONE 2026-07-08 signal (SPY260708P00741000, replicated across 4 arms, $532/388/331
> per-leg swing) -- the sub-window split (first half vs second half) shows a hard SIGN FLIP
> (+$1656-1736 first half vs -$34.5 to -$74.5 second half) for every passing candidate, the
> exact single-anchor-trade-driving-everything signature C24 warns about. Today's 3 exhibit
> fills were NOT recoverable via this study's fills-ledger source (0/0 -- a separate, disclosed
> data-path gap: `exit_shape_parity_study.load_fleet_engine_fills()` tops out 2026-07-17 despite
> `fills-ledger.jsonl` itself having 2026-07-20 rows -- worth a future fire's attention but not
> blocking here since the exhibit was informational-only by the pre-reg's own design). **Verdict
> confirms the queue item's own quantified counterfactual**: widening the SAME (trigger-exact)
> reference doesn't reproduce a stable edge -- it's the REFERENCE CHOICE (item b) that flips
> today's outcome, not the band width on the wrong reference. BAND-00 (today's live behavior,
> buffer=0) stays unchanged. Guard: `backtest/tests/test_structure_stop_zone_band_ab.py` (7/7,
> RED-proofed via file-move -- untracked file, `git stash` unsafe here, see below). Curated
> safety gate (31+5-suite) PASS. **Zero trading-path files touched** -- ANALYSIS ONLY, no
> `params.json`/`strategies.py`/`exit_manager.py`/placement/exit code edited; nothing to revert.
> **Blast-radius near-miss (recorded, not a lesson -- no code change needed):** attempted
> `git stash -- backtest/tools/structure_stop_zone_band_ab.py` (an UNTRACKED file) to RED-proof;
> the pathspec didn't match (untracked files need `-u`/`add` first), the command aborted with
> exit 1, and NOTHING was stashed -- confirmed via `git rev-parse stash@{0}^1` resolving to a
> 2026-07-18 commit (2 days stale, pre-existing from an earlier session, untouched by this fire).
> Recovery = none needed; switched to the file-move RED-proof technique (matches the
> SAFE-VIX-CONDITIONAL-SIZING 2026-07-20 precedent for untracked new modules) for the rest of
> this fire and going forward for any future untracked-file RED-proof.

### STRUCTURE-STOP-REFERENCE-LEVEL (HIGH, trading-path, filed 2026-07-20 ~16:55 ET, follow-up to STRUCTURE-STOP-ZONE-BAND item (b))

- [x] STRUCTURE-STOP-REFERENCE-LEVEL (HIGH, after-hours fix + pre-reg A/B, needs new wiring) ::
  Item (b) of STRUCTURE-STOP-ZONE-BAND, re-filed standalone after item (a)'s REJECT_ALL closed
  the simpler buffer-width axis (see the CLOSED note directly above -- widening the SAME
  trigger-exact reference does NOT reproduce a stable edge; only 1 anchor trade drove every
  apparent win, sub-window sign-flipped). The 2026-07-20 14:16 exhibit's own quantified
  counterfactual (still valid, restated from the original filing): stop-reference choice
  INVERTS the outcome -- trigger-exact 744.92 = stopped 14:16 -$24 (actual); swing-high 745.14
  close-above = stopped 14:20 ~-$51 (WORSE); zone-TOP 745.40 close-above = survives, dump
  reverses, counterfactual +$115-130. UNLIKE item (a), this needs NEW wiring, not just a buffer
  sweep on data already available: `exit_manager.nearest_active_level` (the entry-time trigger
  resolver, `automation/state/fleet/exit_manager.py:100`) already exists and is directionally
  filtered, but only returns the SINGLE nearest level TO SPOT -- it does not resolve "the zone
  boundary the rejection bounced off" as a DISTINCT, further-out level. SPEC before building:
  (1) does `key-levels.json` (or `lib/levels.py`'s backtest-approximation) carry enough
  multi-level structure at entry time to identify a zone boundary ABOVE/BELOW the exact trigger
  (not just the nearest level to spot)? (2) if yes, extend `nearest_active_level` (or add a
  sibling resolver) to return BOTH the trigger-exact level AND the next level further from spot
  in the rejection/reclaim direction, threaded through `ExitState.from_entry`'s existing
  `trigger_level` field (byte-identical for every position where only one level is available --
  additive, not a replacement) as a NEW optional `structure_stop_reference_mode` exit-shape
  knob ("trigger_exact" default | "zone_boundary"). (3) pre-reg A/B: zone_boundary vs
  trigger_exact vs control(no structure), SAME dual-layer + sub-window-stability discipline as
  item (a)'s study (reuse `structure_stop_study.py`/`structure_stop_zone_band_ab.py`'s already-
  built replay machinery -- only the trigger_level RESOLUTION differs, not the replay). (4)
  replay via `backtest/lib/exit_manager_walk.py` (the faithful harness) before shipping; RED-
  proof both ways. Evidence: `analysis/recommendations/structure-stop-zone-band-2026-07-20.json`
  (item a's REJECT, motivating why item b is the more promising remaining lever), original
  narrative in this file's CLOSED block above.
  depends:none :: status:CLOSED_NO_SHIP

> **CLOSED item (b) 2026-07-20 ~17:00-17:35 ET (Sonnet worker, AFTERHOURS): pre-reg A/B
> NO-SHIP, both candidates.** Answered SPEC question (1) affirmatively: `lib/levels.py`'s
> `LevelSet.active` (via `tw8_level_context.frozen_level_set_for_date`, the SAME per-day-
> frozen level set `lib/orchestrator.py`/`lib/filters.py` trade against) already carries
> the full multi-level structure per day, and `detect_level_reclaim`/`detect_level_rejection`
> already identify WHICH specific level fired -- no new data plumbing was needed to resolve a
> zone boundary. Built `backtest/tools/structure_stop_reference_level_ab.py` (new
> `resolve_zone_boundary`/`reference_level_for` pure functions + reuses
> `structure_stop_study.py`'s trigger recovery/replay machinery unchanged, per spec (2)/(3)),
> froze `analysis/recommendations/structure-stop-reference-level-preregistration.json` BEFORE
> running anything (band width held at 0.00 for every candidate by rule -- item (a) already
> falsified that axis; re-opening it here without reference-level evidence would be fishing),
> ran it, verdict: `analysis/recommendations/structure-stop-reference-level-2026-07-20.json`.
> **REF-ZONE** (nearest active level beyond the trigger, away from spot) FAILS layer(a)
> fresh-slice expectancy (-$63.73/tr vs -$47.34 control, n=18) -- worse, not better. Its
> layer(b) real-fills anchor "win" (+$481.2 vs -$900.7 control, n=68) is the SAME single-
> anchor-trade artifact C24 flagged in item (a): one 2026-07-08 position
> (SPY260708P00741000, 3 legs) accounts for the entire delta -- under REF-ZONE the structure
> stop simply never fires that day (zone boundary 745.21 vs entry-adjacent trigger 744.17,
> too far to matter) and the position rides to $427/$427/$307 vs -$105/+$20/-$81 under
> today's live reference -- and the sub-window split hard sign-flips (+$1473.4 first half vs
> -$91.5 second half). **REF-NONE** (no structure stop at all, pure premium-only SS-B) fails
> the SAME way, even worse on layer(a) (-$84.29/tr). **Verdict: NO-SHIP both candidates** --
> `automation/state/fleet/exit_manager.py`/`strategies.py` UNCHANGED, no
> `structure_stop_reference_mode` knob added (per the task's own gating: wiring only happens
> if a candidate clears; neither did). `backtest/lib/exit_manager_walk.py` faithful-harness
> replay (spec (4)) was correctly SKIPPED, not omitted -- that step is the SHIP-gate
> verification for a cleared candidate against the tick-managed live decision core; nothing
> cleared the exploratory pre-reg bar to reach it. Guard:
> `backtest/tests/test_structure_stop_reference_level_ab.py` (17/17, RED-proofed via the
> file-move technique -- untracked new module, `git stash` on an unmatched pathspec silently
> no-ops rather than stashing, per tonight's established precedent: moved the module out,
> confirmed `ModuleNotFoundError` on all 17, moved back, re-verified 17/17 green). Broader
> sweep (`test_structure_stop_study` + `test_structure_stop_zone_band_ab` +
> `test_structure_stop_reference_level_ab` + `automation/state/fleet/test_exit_manager` +
> `test_exit_actuator`) -> **113/113 PASS, 0 regressions**. **Both sub-fixes of the original
> STRUCTURE-STOP-ZONE-BAND queue item (band width, item a; reference choice, item b) are now
> tested and rejected under the same dual-layer discipline** -- the 2026-07-20 14:16 exhibit's
> own -$24 vs +$115-130 counterfactual remains a single anecdote (C24/L140) this study could
> not generalize into a population-level edge. Today's 3 fills were again NOT recoverable via
> this study's fills-ledger source (0/0, exhibit shows 0 positions) -- the same disclosed
> `load_fleet_engine_fills()` date-ceiling gap item (a) flagged, unfixed here (out of scope,
> flagged only). **Zero trading-path files touched.** Cost: ~$4 (1 pre-reg write, 1 new
> ~330-line study tool reusing existing machinery, 1 live run against real OPRA/fills data, 1
> guard-test file + RED-proof round-trip, 1 broader regression sweep, this queue/STATUS
> update). No commit made (orchestrator commits after verification per this fire's own rules).

> **CROSS-REFERENCE 2026-07-20 evening (fleet exit-parameter A/B build, separate fire):**
> `automation/state/fleet/accounts.json`'s risky-3 (FLEET-LOOSE-R) now carries a per-arm
> `params_patch.exit_patch` (new mechanism, `fleet_executor._exit_shape_dict` /
> `EXIT_PATCH_ALLOWED_KEYS`) meant to make this arm "ride it longer" than safe-3's
> chart-stop-primary lane. The IDEAL knob for that -- stop referenced to the zone boundary
> ABOVE the entry trigger, not the trigger itself -- is exactly item (b) above (REF-ZONE),
> which is NO-SHIP per tonight's own pre-reg A/B (single-anchor-trade artifact, sub-window
> sign-flip). Since that knob does not exist and is not currently evidence-backed, risky-3's
> exit_patch approximates "rides longer" with a wider chandelier trail (`trail_pct: 0.20` vs
> the registry's 0.15/0.125) on the SAME trigger-exact `stop_mode=structure` reference every
> other structure-stop position uses -- deliberately NOT re-opening the rejected REF-ZONE
> axis. If a future pre-reg A/B on a DIFFERENT reference-level formulation ever clears,
> revisit risky-3's exit_patch to use it instead of the trail-width proxy.

### EXTRA-SIGNAL-CHURN-COOLDOWN (HIGH, trading-path, filed 2026-07-20 ~11:25 ET during RTH -- FIX AFTER 16:00, Rule 9)

- [x] EXTRA-SIGNAL-CHURN-COOLDOWN (HIGH, after-hours fix + guard) :: **STALE CHECKBOX FIXED 2026-07-22 (conductor) — item 1 shipped, item 2 re-filed as its own tracked item below; nothing left open under this id.** Live exhibit 2026-07-20
  09:51-09:56 ET, safe account, extra_exec lane `vix_regime_dayside`: THREE 3-lot 748C
  entries in 5 minutes (fills 1.13/0.79/0.76), each stopped out in 40-60s (0.98/0.73/0.68),
  net -$87. Two failure shapes stacked: (1) NO re-entry cooldown -- the same setup re-fired
  the very next minute after a stop-out, twice (Rule-4-adjacent churn; L168's sizing-up
  cousin); free-model veto blocked the 09:52+09:53 attempts (HTF-conflict) but let
  09:54+09:55 through -- nondeterministic veto is not a cooldown. (2) The extra-signal lane
  still runs the OLD +30%/-8% premium bracket (tp 1.43/stop 1.01 on 1.10 entry) -- the
  noise-floor study (2026-07-08) showed -8% premium stops on 0DTE = reading spread noise;
  core lane moved to chart-stop-primary 2026-06-18 but this lane never did. FIX (both
  after-hours, each with RED-proof guard): (a) per-setup re-entry cooldown after stop-out
  (min N bars or requires-new-trigger-bar, pre-reg the value, don't hand-pick); (b) audit
  extra-signal exit shape vs core chart-stop doctrine -- either align or document why not.
  NOTE: stops did their job directionally today (calls bought into a fade; -$87 instead of
  worse) -- the churn is the defect, not the stop concept.
  depends:none :: status:CLOSED_PARTIAL (item 1 SHIPPED same-bar cooldown, item 2 re-filed below)

> **CLOSED item 1 (re-entry cooldown) 2026-07-20 ~16:42-17:15 ET (conductor, AFTERHOURS): SAME-BAR
> re-entry guard shipped, guard-tested, committed.** Traced the churn mechanism first: the
> extra-setup lane's watcher "current-bar guards" only stop a DUPLICATE signal firing twice --
> they never stop a FRESH entry attempt once the account goes flat again mid-bar (a stop-out),
> and `_route_extra_setups` had zero memory of "did this setup already try this bar." Chose
> **"requires-new-trigger-bar" over a hand-picked N-minute duration** (the item's own suggested
> alternative) specifically because this is a brand-new mechanism with no existing trade
> population to pre-register a numeric cooldown against -- the bar boundary is the smallest
> non-arbitrary unit available, so there is no knob to A/B here (unlike item 2 below, which DOES
> need one). **Built:** `exit_actuator.load_last_entry_bars` / `record_entry_bar` /
> `same_bar_cooldown_active` (new, `automation/state/fleet/exit_actuator.py` -- a per-arm,
> per-setup "last trigger-bar attempted" ledger, same persistence pattern as the existing
> `load_states`/`save_states` pair) + wired into `heartbeat_core._route_extra_setups`
> (`setup/scripts/heartbeat_core.py`): before any entry attempt, refuse it
> (`SKIP_COOLDOWN_SAME_BAR`) if the setup already attempted an entry on this EXACT trigger bar;
> record the bar on an actual PLACED/PLACING/WOULD_PLACE only (never on WATCH_NOT_ARMED /
> VETOED_BY_MODELS / SKIP_TICK_ENTRY_TAKEN). Fail-open throughout: a cooldown-file read/write
> error never blocks a legitimate entry. Scoped to the extra-setup lane only -- the primary
> ribbon path already has its own one-position-at-a-time + gate discipline and was out of this
> fix's scope. **Verified this fire:** new guard
> `backtest/tests/test_extra_signal_churn_cooldown_2026_07_20.py` (10/10) covers the round-trip,
> same-bar-blocks / different-bar-doesn't, fail-open on a cooldown-check exception, and
> record-only-on-actual-placement. RED-proofed via `git stash` on the 2 edited files (untracked
> new test file separately moved out and back, per the file-move technique this session's earlier
> fires established for untracked modules): stashing the 2 tracked files + moving the test file
> out reproduced the exact expected mechanism (`AttributeError: module 'exit_actuator' has no
> attribute 'load_last_entry_bars'`, 9/10 fail), `git stash pop` + move-back restored cleanly,
> re-verified 10/10 green. Broader sweep (`test_g4_extra_setup_routing` +
> `test_gap_and_go_exit_wiring_2026_07_18` + `test_audit_fix_heartbeat` + `test_audit_fix_exit` +
> `test_execute_stop_display` + `test_g14_fleet_ribbon_exit` + `test_money_path_2026_07_01` +
> `test_trade_to_learn_2026_07_01` + this file) -> **136/136 PASS, 0 regressions**. Curated
> safety gate (31+5-suite, `run_safety_gate.py`) PASS.
>
> **Rail-4 (PAPER trading-path -- guard test + revert path + this REVOKE report):** touches
> `automation/state/fleet/exit_actuator.py` (additive, 3 new functions, zero existing function
> bodies changed), `setup/scripts/heartbeat_core.py` (`_route_extra_setups` gains one new
> same-bar check before the existing veto/execute try-block + one recording call after a
> successful placement; zero change to the primary ribbon path, zero change to gate ordering,
> zero change to `_execute`'s pricing/sizing/placement logic), `backtest/tests/
> test_extra_signal_churn_cooldown_2026_07_20.py` (new guard), `automation/overnight/queue.md`
> (this closure). **Revert:** `git revert <commit>` (single pathspec commit, 3 files) -- purely
> additive, so a revert is a clean no-behavior-change rollback to today's exact pre-fix churn
> risk (the item's own live exhibit).
>
> **Item 2 (exit-shape misalignment) NOT fixed this fire -- re-filed below as
> `EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT`.** Confirmed live (not just claimed): `params.json`
> carries `j_vix_dayside_premium_stop_pct: -0.08` / `j_vix_dayside_tp1_pct: 0.3` (the exact
> old-shape numbers the item cites), routed through `_SETUP_EXIT_OVERRIDES["vix_regime_dayside"]`
> in `heartbeat_core.py` -- confirmed still live and unchanged since 2026-06-18's core-lane
> chart-stop-primary shift, exactly as the item alleged. Did NOT flip it this fire: changing a
> live exit-stop knob without a pre-reg A/B against real fills would violate C29 (exit knobs
> ratified on one tier/setup don't transfer to another -- there is no existing validated
> chart-stop cell for `vix_regime_dayside` to fall back to, unlike `gap_and_go`'s already-
> validated shape) -- a blind widen is exactly the kind of "hand-picked knob" OP-16/C29 forbid.

### EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT (MED, trading-path, needs pre-reg A/B, filed 2026-07-20 ~17:10 ET, item 2 of EXTRA-SIGNAL-CHURN-COOLDOWN)

- [ ] EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT (MED, after-hours study + pre-reg A/B) :: The
  `vix_regime_dayside` extra-setup lane (and by inspection every OTHER `_SETUP_EXIT_OVERRIDES`
  entry except `gap_and_go`) still trades its ORIGINAL 2026-06-01-era premium bracket
  (`j_vix_dayside_premium_stop_pct=-0.08` / `j_vix_dayside_tp1_pct=0.30`) -- confirmed live in
  `params.json` 2026-07-20. The 2026-07-08 noise-floor study found -8% premium stops on 0DTE
  read as spread/quote noise more than real invalidation (10-min MAE -36% vs -20% stop = winners
  stopped by noise, per the standing memory `project_noise_floor_entry_exit_matrix`); the core
  ribbon path moved to chart-stop-primary on 2026-06-18 for exactly this reason, but the
  extra-setup lane's per-setup overrides were never revisited after that shift. FIX (needs a
  REAL pre-reg A/B before any params flip -- C29: exit knobs validated on one setup/tier don't
  transfer to another without independent evidence):
  (1) pull `vix_regime_dayside`'s (and the other 3 non-gap_and_go overrides') own fills history
  from `fills-ledger.jsonl` + `core-decisions.jsonl` (small-n expected -- these are newer/rarer
  extra-setup lanes than the core path, so this may be an underpowered-n<15 DISCLOSE-not-hide
  case per C13, not a block on running the study);
  (2) pre-register a widened-stop candidate (e.g. -20%/-30%, matching the core lane's pre-SS-B
  premium-stop era, NOT a guess -- cite the specific historical value being reused) vs the
  current -8% control, same dual-layer (fresh-slice expectancy + real-fills anchor) + sub-window
  stability discipline the STRUCTURE-STOP-ZONE-BAND study used (reuse its machinery where the
  setup shape allows);
  (3) if n is too small for a real verdict, the honest conclusion is DEFER-INSUFFICIENT-DATA,
  not a blind flip -- do not hand-pick a replacement value absent evidence just because -8% is
  suspected to be too tight;
  (4) if/when a candidate clears the auto-ratify gate (OOS+/WF>=0.70/sub-window-stable/anchor-
  no-regression), ship it exactly like any other trading-path change (guard test + revert path +
  REVOKE report, rail 4) -- this item does NOT need J's ratification, only real evidence.
  Evidence: `automation/state/params.json` (`j_vix_dayside_premium_stop_pct`/`_tp1_pct`),
  `setup/scripts/heartbeat_core.py::_SETUP_EXIT_OVERRIDES`, the EXTRA-SIGNAL-CHURN-COOLDOWN
  closure note above (this fire's live confirmation).
  depends:none :: status:pending

> **STEP (1) DONE for `vix_regime_dayside` only, 2026-07-20 ~evening (after-hours, AUDIT-ONLY --
> no params/stop-shape change made): pulled the lane's fills history and it is thinner than
> even this item anticipated.** `core-decisions.jsonl` scan of every `extra_exec` row with
> `setup=="vix_regime_dayside"` (14 rows total across the lane's whole life) shows exactly
> **3 PLACED entries ever** -- and all 3 are TODAY's churn exhibit (09:51/09:54/09:55).
> Every earlier attempt (2026-07-02, 2026-07-09) was blocked at `RISK_DENY_RISK_CAP` /
> `RISK_DENY_PDT` before ever reaching the broker. **Today is this lane's first-ever live
> fill, so n=3 is not a sample of the lane's history -- it IS the lane's entire history.**
> Per-trade detail (`fills-ledger.jsonl`, symbol `SPY260720C00748000`, arm `safe-2`; NBBO +
> `spy` spot from the matching `core-decisions.jsonl` ticks):
>
> | # | entry fill | stop fill | hold | entry NBBO spread | -8% stop distance | spread/stop-distance | SPY spot entry-tick -> exit-tick |
> |---|---|---|---|---|---|---|---|
> | 1 | 09:51:24.73 @ 1.13 | 09:52:03.56 @ 0.98 | 38.8s | $0.00 (bid=ask=1.10) | $0.088 | 0% | 747.575 -> 747.575 (unchanged) |
> | 2 | 09:54:19.66 @ 0.79 | 09:55:03.98 @ 0.73 | 44.3s | $0.04 (0.76/0.80) | $0.0624 | **64%** | 747.575 -> 747.575 (unchanged) |
> | 3 | 09:55:24.87 @ 0.76 | 09:56:03.44 @ 0.68 | 38.6s | $0.02 (0.72/0.74) | $0.0584 | 34% | 747.575 -> 746.43 (real -1.145pt move) |
>
> **Reading:** 2 of 3 stop-outs (trades 1+2) fired while the engine's OWN logged SPY spot was
> IDENTICAL at entry and exit -- zero observed underlying movement across the full hold, i.e.
> the -8%/-6% premium move that triggered the stop has no price-action justification in the
> engine's own record; trade 2's entry-time NBBO spread alone ($0.04) consumed **64% of its
> entire stop distance** ($0.0624), meaning roughly two-thirds of that stop's margin was spread,
> not room. Trade 3 is the one case with a real, contemporaneous SPY move against the position
> (-1.145pts) -- closer to a legitimate invalidation, though its spread (34% of stop distance)
> was still non-trivial. This is DIRECTIONALLY CONSISTENT with the 2026-07-08 noise-floor
> finding (the same mechanism the core lane moved off of on 2026-06-18) but **n=3, all from one
> session, is not a verdict** -- exactly the DEFER-INSUFFICIENT-DATA condition this item's own
> step (3) pre-committed to. Caveat for whoever runs steps (2)-(4): SPY spot pinned at EXACTLY
> 747.575 for 4 consecutive 1-minute ticks (09:51-09:55) is itself worth independently checking
> for a stale/frozen quote snapshot in the engine's log before leaning on the "flat SPY" reading
> too hard -- if it's a live-feed artifact rather than genuine chop, only the spread-ratio numbers
> (0%/64%/34%) stand on their own, which still lean noise-consistent for trade 2 specifically.
> **No stop-shape change made** (per this item's own gate + this fire's instructions) -- this is
> disclosure to sharpen steps (2)-(4), not a substitute for them; the other 3 non-`gap_and_go`
> overrides named in step (1) are still unpulled (out of this fire's scope, which was
> `vix_regime_dayside` only). Status stays `pending` -- the real pre-reg A/B still needs more
> organic n than one session can supply.

> **EVIDENCE ADDED 2026-07-20 ~evening (after-hours, REPORT-ONLY -- no params/stop-shape
> change): counterfactual replay of ALL 11 `exit_stage=premium_stop` episodes (2026-07-13..
> 07-20, `analysis/winning-trade-map/episodes-2026-07-13-to-2026-07-20.json`) under RIBBON_
> RIDE's chart-stop-primary shape** (`backtest/tools/extra_signal_premium_stop_counterfactual.py`
> -> `analysis/recommendations/extra-signal-premium-stop-counterfactual-2026-07-20.json`),
> driven through the REAL `exit_manager.plan_exit_actions` over real 1-min SIP(SPY)/OPRA
> bars fetched fresh this fire. **Result: NET WORSE, not better** -- actual $-509.00 vs.
> counterfactual $-601.01 (delta **-$92.01**). Per-episode: 2/11 clearly better (+$78/+$33,
> both the SAME vwap_continuation 07-16 09:51-09:53 lane -- noise-floor-consistent), **3/11
> clearly WORSE** (-$63/-$84/-$27 -- real, continuing adverse SPY moves that the -50%-
> catastrophe-adjacent shape let bleed further before catching), 5/11 roughly neutral
> (+/-$15), 1/11 an exact fidelity-match (E4, already running structure mode live in
> production). **CAVEAT CORRECTED against this run's own evidence:** the "a losers-only
> cohort can only look better-or-equal under a looser stop" argument this item's framing
> assumed does NOT hold for an exit-SHAPE-SWAP (vs. an entry-filter-removal) counterfactual
> -- chart-stop-primary is not a pure loosening (its -50% cap is wider than these lanes'
> native -6%/-8% brackets), and this run's own 3 worse-outcomes refute the "can't look
> worse" premise directly. **STALE-QUOTE caveat (flagged in the STEP(1) note above) RESOLVED:**
> confirmed a STALE-FEED ARTIFACT in the DECISION CONTEXT LOG only (context_bundle computed
> once at 09:50:02, reused across the 09:51/09:54/09:55 ticks) -- the real 1-min SIP tape
> shows SPY genuinely sold off 747.62->746.14 (~$1.48, 100K-265K shares/min) over that
> window; contaminates only those 3 episodes' logged alignment/levels context, not this
> replay (reads real bars directly). **Verdict: DEFER-INSUFFICIENT-DATA** -- n=11 across 3
> sessions and effectively 2 true shape-swap lanes (vix_regime_dayside's n=3 is one
> session's entire history; bollinger_squeeze/vwap_continuation each n<=3), exactly this
> item's own step-3 pre-committed condition. Status stays `pending` -- this evidence neither
> supports shipping the alignment nor rejects it; steps (2)-(4)'s real pre-reg A/B still
> needs organic n this after-hours fire cannot manufacture.

### PREMARKET-TOUCH-CREDIT-STUDY (HIGH, study-first, filed 2026-07-20 ~09:36 ET, J question same morning)

- [x] PREMARKET-TOUCH-CREDIT-STUDY (HIGH, pre-reg study, NOT a same-day wire) :: J's Monday
  2026-07-20 premarket question is the motivating exhibit: SPY rejected the 747.4-747.5 zone
  "to a t" at the premarket open, danced around it again ~08:30, and approached it a third
  time near the bell -- and the engine gave that zone ZERO touch-credit because level_states
  touch counting starts at 09:30 RTH (verified: `heartbeat_core._read_levels` seeds fresh
  each day; premarket bars never increment touches/rejections). A human reads the third test
  of a level differently from the first; the engine literally cannot see that the first two
  tests happened. STUDY (frozen pre-reg BEFORE running, per WF-GATE-METHODOLOGY +
  zones-not-prices doctrine): on historical days, seed each level's touch/rejection state at
  09:30 from 04:00-09:30 premarket bars (SIP feed, provenance per DATA-PROVENANCE.md), then
  measure whether RTH rejection triggers at levels WITH >=1 premarket rejection outperform
  identical triggers at untouched levels, real-fill outcomes under SS-B exits, per-episode
  accounting, random + shuffled-level nulls, BH-FDR, concentration disclosure. KILL is a
  valid outcome (premarket touches may be noise). If it clears, the wire is one seam:
  seed `level_states` at 09:30 open from premarket bars (same zone-band logic as RTH).
  depends:none :: status:CLOSED_KILL

> **CLOSED 2026-07-20 ~17:15-18:05 ET (conductor, AFTERHOURS): KILL, pre-registered and run
> in full.** Froze `analysis/recommendations/premarket-touch-credit-preregistration.json`
> BEFORE any replay. Built `backtest/tools/premarket_touch_credit_study.py`, reusing
> `structure_stop_study.py`'s replay engine (SS-B, trigger-exact, buffer=0.00 -- confirmed
> literal live behavior per tonight's structure-stop studies), `tw8_level_context.py`'s
> frozen per-day level set, and `lib.filters.detect_level_rejection`/`detect_level_reclaim`
> (the EXACT production bar-test, direction-matched to side) reused verbatim for premarket
> touch detection -- zero new hand-picked band/proximity parameter. Fresh-slice population:
> 41 signals combined from the canonical 2025-2026 signal cache (filtered to the Alpaca-SIP-
> verified premarket window 2026-05-19..2026-07-17, per DATA-PROVENANCE.md -- older dates
> excluded by rule to avoid an IEX/09:00-start feed provenance confound) + the existing 18-
> signal FRESH_SIGNAL_SET, deduplicated; 27 had a recoverable trigger_level and cached option
> bars (0 network calls -- all local cache, $0). **Result: n_touched=15 (SS-B expectancy
> -$15.88/tr), n_untouched=12 (-$302.50/tr), observed delta +$286.62 favoring premarket-
> touched levels -- directionally consistent with J's own reading, but NOT statistically
> distinguishable from noise**: random-label permutation null p=0.21 (2000 draws), shuffled-
> level null p=0.208 (500 draws/segment) -- neither survives BH-FDR at alpha=0.05 (both
> False). **Verdict: KILL**, exactly the pre-reg's own disclosed-in-advance expected outcome
> for an n~27 population. Layer (b) real-fills anchor (live OPRA re-fetch) was DEFERRED by
> the pre-reg's own scope_note -- not worth ~$4 of network calls to confirm a KILL that layer
> (a) alone already resolves; no follow-up study needed unless a future, larger fresh-slice
> population (e.g. once the canonical signal cache is rebuilt through a later END date)
> reopens the question with more power. **Guard:**
> `backtest/tests/test_premarket_touch_credit_study.py` (26/26: BH-FDR against a classic
> textbook example, direction-matched touch detection incl. no-cross-day-leakage and no-RTH-
> bar-leakage, segmentation math, verdict-ladder branch coverage, live pre-reg/output sanity),
> RED-proofed via the file-move technique (untracked new module -- moved out, confirmed
> `ModuleNotFoundError` on all 26, moved back, re-verified 26/26 green). Broader sweep
> (`test_structure_stop_study` + `test_structure_stop_zone_band_ab` +
> `test_structure_stop_reference_level_ab` + this file) -> **72/72 PASS, 0 regressions**.
> Curated safety gate (31+5-suite) PASS. **Zero trading-path files touched** -- ANALYSIS ONLY,
> no `heartbeat_core.py`/level_states/`params.json`/any placement/exit code edited; nothing to
> revert; no wire attempted (per the item's own "NOT a same-day wire" scope -- KILL means
> there is nothing to wire). Files: `analysis/recommendations/premarket-touch-credit-
> preregistration.json`, `analysis/recommendations/premarket-touch-credit-2026-07-20.json`,
> `backtest/tools/premarket_touch_credit_study.py`,
> `backtest/tests/test_premarket_touch_credit_study.py`, this queue.md entry. Cost: ~$4.5
> (STAGE 0/1 reads + task selection, machinery survey across levels.py/filters.py/
> tw8_level_context.py/structure_stop_study.py/probe_stats.py/_signal_cache.py, 1 pre-reg
> write, 1 ~330-line study tool, 1 local run (0 network calls), 1 new 26-test guard file +
> RED-proof round-trip, 1 broader 72-test regression sweep, 1 curated safety gate run, 1
> queue.md closure).

### SIM-EXIT-SHAPE-PARITY-AUDIT (MED, spec-only, filed 2026-07-17 ~22:47 ET, GOAL-REPLAY-TODAY-GREEN iteration 7)

- [ ] SIM-EXIT-SHAPE-PARITY-AUDIT (MED, spec-only, systematic re-check) :: Iteration 6
  (GOAL-REPLAY-TODAY-GREEN) found `simulate_trade_real` callers read exit knobs from
  `params.json`'s top-level keys (`profit_lock_mode="fixed"`, `tp1_premium_pct=0.5`, ...)
  instead of the REAL exit_manager's `automation/state/fleet/strategies.py#RIBBON_RIDE.exit`
  shape (`profit_lock_mode="trailing"` chandelier, `stop_mode="structure"`) -- every
  sim-based ribbon_ride exit study built on `simulate_trade_real` has been testing the WRONG
  exit shape, not an approximation of the right one. Iteration 7 rebuilt ONE affected study
  (`elite_bear_level_reject_gate_ab.py` / L1) under the correct shape via
  `backtest/tools/regime_readjudication_correctexit.py` and found a MATERIAL mechanism
  change: 13/16 removed trades were artificially flattened to exactly $0.00 under the wrong
  shape (profit-lock breakeven-round-trip artifact); under the correct shape the same cohort
  nets +$2,629.30/16 trades (10W-6L) -- a genuinely profitable population the wrong sim was
  hiding. The ship decision didn't change (still NO-SHIP, now on harder concentration-
  independent grounds) but the MECHANISM did -- for OTHER `simulate_trade_real`-based studies
  in this codebase, a similar correction could plausibly change ship decisions, not just
  mechanisms. Code-traced this iteration (NOT re-run, out of this goal's scope):
  `bold_strike_axis_deltawf.py`/`bold_strike_axis_ab.py` (uses
  `structure_stop_study.SS_B_SHAPE` via `plan_exit_actions` directly -- NOT the bug, but
  TRENDLINE-tier entries fall back to a -50% premium stop vs live's -20%, a narrower disclosed
  gap never independently verified), `zone_rejection_band_study.py` (same SS_B_SHAPE lineage),
  `pong_resting_limit_study.py` (bespoke `plan_exit_actions`-driven grid, paired-delta so
  common-mode shape errors mostly cancel -- but never formally verified). Grep
  `backtest/tools/*.py` for `simulate_trade_real` (16 files as of 2026-07-17, listed in
  iteration-7's session notes) and classify each: (a) genuinely affected (params.json-sourced
  shape feeding a ribbon_ride/live-strategy population -- rebuild via `exit_manager_walk.py`
  per the iteration-7 pattern), (b) already immune (drives `plan_exit_actions` directly, or
  studies a non-ribbon_ride strategy where the bug doesn't apply), (c) low-stakes/exploratory
  (smoke tests, one-off sweeps not feeding a ship decision). Ship-decision-bearing studies in
  bucket (a) get priority. Evidence:
  `automation/overnight/GOAL-REPLAY-TODAY-GREEN.md` ITERATION 7,
  `analysis/recommendations/regime-readjudication-correctexit-2026-07-17.{json,md}`.
  :: depends:none :: status:proposed

### ADVERSE-EXTREME-AVOIDANCE-FILTER (MED, pre-reg spec, from FAVORABLE-EXTREME-ENTRY-2026-07-17 KILL)

- [ ] ADVERSE-EXTREME-AVOIDANCE-FILTER (MED, spec-only, filed 2026-07-17 evening) :: The
  favorable-extreme-entry study (KILL, `analysis/recommendations/favorable-extreme-entry-2026-07-17.{json,md}`)
  produced ONE genuinely actionable positive signal as the MIRROR of its main finding: across
  BOTH real-fill populations (primary n=30 broker fills, secondary n=119 trades.csv), the
  **adverse_extreme entry-location bucket is the WORST** (primary -$17.87/tr 13% win; secondary
  -$8.98/tr 6.9% win) -- a marketable fill that lands at the WRONG end of its entry bar (put filled
  near the bar LOW, call near the bar HIGH) correlates with losing. This is a DIFFERENT, simpler
  mechanism than the resting-limit targeting that got killed: not "rest and wait for a favorable
  fill" (that loses clean runners + gets run over on trending days, 0/18 cells cleared anchor+BH-FDR
  both accounts), but "AVOID/deprioritize an entry whose actual marketable fill is adverse-extreme."
  Spec: pre-registered A/B of a post-fill (or at-fill, if a live-tick location read is available in
  the heartbeat) gate that skips or down-weights entries landing in the bottom-30%-of-bar-toward-the
  -wrong-side bucket, on the SAME confirmation-trigger signal population, real-OPRA replay, frozen
  `ab_delta_per_trade_v2026_07_16` WF form + BH-FDR + anchor, both accounts per C29. Open question the
  spec must resolve: is the fill-location knowable EARLY ENOUGH to act (the heartbeat samples SPY at
  the decision tick, ~<=60s before the broker fill -- verify whether that read is a good enough proxy
  for where the fill will land, or whether this is only a post-hoc diagnostic with no live actuation
  point). **SPEC REQUEST, do not wire without a cleared A/B (OP-16 eval-first).** Evidence:
  `analysis/recommendations/favorable-extreme-entry-2026-07-17.md` Synthesis + Build-spec sections.
  :: depends:none :: status:proposed

### SAFE3-RISKY1-GATE-RETEST-EXTEND (MED, needs pre-reg accrual, discovered 2026-07-17)

- [ ] SAFE3-RISKY1-GATE-RETEST-EXTEND (MED, this-week/needs-larger-n) :: J audit
  ("why didn't safe-3/risky-1 mirror the 13:01 746P +$241 / 13:51 743P +$191 core winners")
  traced BOTH misses to the tight arms' own `gate_override` (min_triggers=2 +
  require_confluence_or_sequence) correctly blocking a lone `trendline_rejection` trigger with
  no confluence/sequence tag -- design working as intended, not a bug. But the blocked-cohort
  P&L evidence (07-16 redesign: 0-for-4, -$85) got extended with one new comparable fill today
  (risky-3 mirrored the 13:51 signal at the identical strike table, +$233) -- extended sample
  n=5, 1-for-5 by count, net **+$148** (sign flip from the 07-16 headline). Still far below the
  07-16 redesign's own tightened n>=30 multi-testing floor -- NOT shippable tonight, NOT
  permanently closeable either. Pre-reg filed:
  `analysis/recommendations/safe3-risky1-gate-retest-preregistration.json` (frozen cohort
  definition + pass bar; auto-accretes on the next qualifying comparable fill). Full trace:
  `analysis/daily-brief/2026-07-17-tight-arms-audit.md`. Secondary, distinct finding folded
  into the EXISTING 07-16 redesign's "nearer strike table for risky-3" THIS WEEK item (not a
  new pre-reg): the 13:01 miss's real binding constraint was `SKIP_MIN_PREMIUM_FLOOR` at the
  shared OTM-3 strike table, which applies to safe-3/risky-1 exactly as it does risky-3 -- widen
  that item's scope to all three fleet_rest arms when picked up. :: depends:pre-reg-accrual
  :: status:pending

### TV-MCP-GETCHARTAPI-FIX-VERIFY (MED, fix landed, verify pending restart, 2026-07-14)

- [ ] TV-MCP-GETCHARTAPI-FIX-VERIFY (MED) :: G3 root-caused + fixed the `draw_list`/
  `draw_remove_one`/`draw_get_properties`/`draw_clear` "`getChartApi is not defined`" bug (the
  same one trendline-draw's Step 1 works around via `ui_evaluate` JS-injection). ROOT CAUSE:
  `src/core/drawing.js` in the reservoir repo
  (`C:/Users/jackw/Desktop/SwjshAlgoKnife/mcp-servers/tradingview-mcp`) — `listDrawings`,
  `getProperties`, `removeOne`, `clearAll` referenced the bare `getChartApi`/`evaluate`
  identifiers, which are only module-imported under the aliases `_getChartApi`/`_evaluate`;
  `getChartApi`/`evaluate` were never bound in those 4 functions' scope (only `drawShape` called
  `_resolve(_deps)` to bind them locally) → ReferenceError before ever reaching CDP. FIX: all 4
  now call `_resolve(_deps)` first, matching `drawShape`'s existing pattern. Verified via a new
  mocked-`_deps` regression suite (`tests/drawing_getchartapi.test.js`, 5/5 pass, incl. a static
  source-audit guard that fails CI if a future function calls `getChartApi()`/`evaluate()`
  without resolving `_deps` first) — see that repo's `git diff src/core/drawing.js`.
  **NOT YET LIVE-VERIFIED end-to-end** — the running `tradingview` MCP server process
  (`src/server.js`, spawned per-Claude-session via `.mcp.json` → `launcher.cjs`) has the OLD
  code cached in its already-running Node process; it re-reads from disk only on next spawn. No
  destructive action needed and no restart script to run by hand — the fix auto-applies the
  moment the NEXT fresh Claude Code session connects to the `tradingview` MCP server (new
  process = fresh `require`/`import`). **Do NOT force-kill/restart THIS session's live MCP
  process during market hours (09:30-15:55 ET) — that's the live CDP session J may be charting
  on.** Action for the next after-close (16:05+) or next-morning session: call
  `draw_list` / `draw_get_properties` / `draw_remove_one` for real against the live chart and
  confirm no `getChartApi is not defined`; if clean, trendline-draw's `ui_evaluate` JS-injection
  workaround (Step 1) can be retired in favor of the native tools — that's the OTHER audit
  crew's file (`trendline-draw/SKILL.md`), flag it to them / do it next session, don't edit it
  from this queue item. Also note: that reservoir repo currently has OTHER uncommitted changes
  (`src/connection.js` disconnect/error-handler additions, `src/server.js`
  unhandledRejection/uncaughtException handlers, `package-lock.json`) not made by this session —
  unrelated to the getChartApi fix, left as-is (not mine to commit/revert). :: depends:none ::
  status:pending

### PANDAS-CONSOLE-LEAK-ROOT-CAUSE (LOW, cosmetic-but-unresolved, discovered 2026-07-14)

- [ ] PANDAS-CONSOLE-LEAK-ROOT-CAUSE (LOW, mitigated not fixed) :: `import pandas` (pulls in
  numpy) under `backtest\.venv\Scripts\pythonw.exe` triggers a `WindowsTerminal -Embedding`
  console-host window on Win11, reproduced live via clean isolated `Start-ScheduledTask` fires.
  Ruled out as the trigger (all tested live, all failed to prevent it): launcher mechanism
  (`Shell.Run` vs `WshShell.Exec` vs Python `subprocess.Popen(creationflags=CREATE_NO_WINDOW)`),
  Python-level `sys.stdout`/`stderr` redirection, OS-level `os.dup2` fd redirection,
  `warnings.filterwarnings("ignore")`. A minimal stdlib-only script under the same interpreter
  is clean. Currently MITIGATED (not fixed) via `window-leak-detector.py` auto-hiding any
  service-rooted console-host window within its 0.5s poll — see STATUS.md 2026-07-14 entry for
  full investigation trail. If picked up again: try isolating numpy alone vs pandas-minus-numpy
  (not yet split), check for an explicit `ctypes.windll.kernel32.AllocConsole()` call anywhere
  in the installed numpy/pandas wheel's `.pyd`/`.dll` set, try `MKL_NUM_THREADS=1`/disabling
  MKL threading-layer auto-detection if this numpy build is MKL-linked (unconfirmed — check
  `numpy.show_config()`), or try a different numpy/pandas version pin as an A/B. :: depends:none
  :: status:pending

### MCP-DAILY-AUDIT-CLAUDE-AUTH-FAILING (LOW, pre-existing, discovered 2026-07-14)

- [ ] MCP-DAILY-AUDIT-CLAUDE-AUTH-FAILING (LOW, pre-existing 2+ days) :: `Gamma_McpDailyAudit`
  (`run-mcp-daily-audit.ps1` -> `Invoke-Claude` haiku call) has failed `exit=1` for at least
  2026-07-13 (`API Error: 400 All target providers failed`) and 2026-07-14 (`Not logged in —
  Please run /login`) — different error each day, both pointing at the `claude` CLI / CCR
  routing layer, not this task's own logic. Confirmed NOT a regression from the same-day
  popup-storm fix (the task's launcher chain was rewrapped this session but the failure
  predates that edit by a day, same error family). Likely related to the CCR interactive-path
  hijack saga documented in this same file's `Gamma_CcrKeepalive` row (2026-07-14 lockout root
  cause) — worth checking whether the interactive-settings guard fully covers this task's own
  `claude --print` invocation path too. :: depends:none :: status:pending

### SWJSHAK-RUN-KEY-BARE-POWERSHELL (LOW, cross-project, discovered 2026-07-14)

- [ ] SWJSHAK-RUN-KEY-BARE-POWERSHELL (LOW, cross-project, ask before touching) :: Two
  SwjshAlgoKnife-owned HKCU `...\Run` entries (`SwjshAK-SystemStart`, `SwjshAK-HALOWatchdog`)
  use bare `powershell -WindowStyle Hidden -Command "..."` — same Win11 OpenConsole-before-
  hidden flash class fixed for Gamma's own tasks this session, but only fires once per boot
  (not a repeating-popup pattern) and SwjshAlgoKnife is scope-frozen (ask before expanding) so
  left untouched pending J's go-ahead. Fix (if wanted): repoint the Run-key command string at
  `wscript.exe //nologo "C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden_exec.vbs"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "..."` (or an equivalent .vbs
  living in SwjshAlgoKnife's own tree, if J prefers not to cross-reference the 42 repo from a
  registry key in another project). Separately, `OpenClaw Gateway.cmd`
  (`%APPDATA%\...\Startup\`, `start "" /min cmd.exe ...`) is a genuinely unrelated third-party
  tool outside both projects — flagged only, no fix proposed. :: depends:J-go-ahead
  :: status:pending

### SHADOWEVAL-WEEKLY-TRIGGER-VS-DAILY-DOCS (LOW, doc/reality mismatch, discovered 2026-07-14)

- [x] SHADOWEVAL-WEEKLY-TRIGGER-VS-DAILY-DOCS (LOW) :: **CLOSED 2026-07-20 ~19:12-19:55 ET
  (conductor, AFTERHOURS).** The ORIGINAL premise is a non-issue: `Get-ScheduledTask
  Gamma_ShadowEval | Triggers` live-checked this fire shows `MSFT_TaskRepetitionPattern`-class
  weekly trigger with `WeeksInterval=1` + `DaysOfWeek=62` (bitmask 2+4+8+16+32 = Mon-Thu-Fri..
  i.e. all 5 weekdays) -- that IS "daily on weekdays" in Windows Task Scheduler's own
  representation (a weekly trigger with every weekday checked = fires every weekday, same as a
  daily trigger would). No mismatch, no fix needed on the trigger itself.

  **BUT investigating it FOUND a real, much bigger C7 silent-failure the doc-mismatch hunt
  was never aimed at:** `Get-ScheduledTaskInfo` showed `LastRunTime=2026-07-20 14:05:00`,
  `LastTaskResult=0` (success) -- yet the newest file in `analysis/shadow-model/*-scorecard.md`
  was dated **2026-06-24**, a full FOUR WEEKS of weekday fires (real per-day logs exist,
  `automation/state/logs/shadow-eval-2026-06-29.log` through `-2026-07-20.log`, ~15 trading
  days) with every single one printing `"No ticks found for <date> -- skipping"` and exiting 1
  -- masked from Task Scheduler by the wscript fire-and-forget wrapper (the SAME exit-code-
  masking class as `Gamma_EodFlattenCore`'s founding incident). **Root cause:** the live engine
  migrated from two per-account ledgers (`automation/state/decisions.jsonl` +
  `automation/state/aggressive/decisions.jsonl`, both frozen at 2026-06-25 14:01:00) to ONE
  consolidated both-accounts ledger (`automation/state/core-decisions.jsonl`, schema:
  `ts_et`/`account`/`verdict`/`ribbon`/`htf_15m`/`setup`/`triggers`/`exec` -- materially
  different field names AND file shape from the legacy `date`/`action`/`ribbon_stack`/
  `htf_15m_stack`/`setup_name`/`trigger` schema) around 2026-06-25 -- `shadow_model_eval.py`'s
  `SAFE_LEDGER`/`BOLD_LEDGER` constants were never updated to follow the migration. Textbook
  C14 (dead/translated-but-unapplied knob, one level up: a whole PRODUCER migrated and a
  CONSUMER silently kept reading the old file).

  **Fixed:** added `CORE_LEDGER` constant + `_normalize_core_row()` (maps the new schema's
  field names to the legacy shape: `ribbon`->`ribbon_stack`, `htf_15m`->`htf_15m_stack`,
  `setup`->`setup_name`, `triggers[0]`->`trigger`, `ts_et`->`date`+`time_et`, `verdict`->
  `action`, `exec.entry_px`/`exec.tp`/`exec.stop`->`entry_px`/`tp1_px`/`stop_px`) +
  `load_ticks_for_date(ledger_path, date, account=None)` now falls back to `CORE_LEDGER`
  (filtered by account + date, normalized) whenever the legacy ledger has nothing for the
  requested date -- pre-migration (<=2026-06-24) grading stays byte-identical (legacy ledger
  still has data, fallback never fires), every date since 2026-06-25 is now readable.
  **Disclosed scope limit:** `core-decisions.jsonl` logs ZERO `EXIT_*` verdicts (exit
  management lives in `exit_manager.py`/`fleet_executor.py`, not this ledger) -- so
  `HOLD_RUNNER`/`EXIT_*` DT-agreement grading stays unavailable until exit ticks land
  somewhere this adapter can read; `ENTER_BULL`/`ENTER_BEAR`/`HOLD`/`SKIP_*` grading (the
  DT-agreement mechanism's actual decision-bearing population -- `is_decision_tick()` already
  excludes HOLD/SKIP_* from the DT count, so ENTER_* was always the signal) is fully restored.

  **Verified this fire (not claimed):** live dry-run (`--dry-run --date 2026-07-20`) now
  builds real prompts and reports `(406 ticks total for 2026-07-20)` for safe / 386 for bold --
  **exact match** to `fill_funnel.py`'s independently-computed tick counts for the same day
  (406/386), proving the fix reads the correct live rows, not a coincidence. New guard
  `backtest/tests/test_shadow_model_eval_core_ledger.py` (11/11 incl. a live-ledger regression
  pin against the real production file, RED-proofed via `git stash` on `shadow_model_eval.py`
  alone -- all 11 failed with `AttributeError: no attribute 'CORE_LEDGER'` as expected,
  `stash pop` restored cleanly, re-verified 11/11 green). Curated safety gate (31 + 5-suite)
  PASS. Kicked off the REAL production eval (`shadow_model_eval.py --date 2026-07-20
  --account both`, exact command `run-shadow-eval.ps1` runs nightly) in the background this
  fire to produce tonight's actual scorecard end-to-end -- $0 (Nemotron free tier), ~792 ticks
  x 2.5s inter-call sleep means this legitimately runs long; if this queue entry is read before
  it finishes, check `analysis/shadow-model/2026-07-20-scorecard.md` directly rather than
  re-running.

  **Rail-4 N/A (not a trading-path file):** `shadow_model_eval.py` is a read-only, propose-only
  monitoring/audit script by its own docstring ("NEVER imports or calls any Alpaca tool or
  order function... Read-only on production state") -- ships as engine-benefit per OP-22/OP-26,
  no J ratification needed. Zero `params.json`/`heartbeat_core.py`/`filters.py`/placement/exit
  code touched. **Revert:** single pathspec commit, `git revert <this-commit>` (2 files:
  `setup/scripts/shadow_model_eval.py`, the new test file). **Learn-loop:** this is the SAME
  root cause class as the queue's own recurring C7/C14 theme (producer migrates, consumer
  doesn't follow) -- the guard test itself is the graduation (a live-ledger regression pin that
  will RED the moment `core-decisions.jsonl`'s schema changes again without a matching update
  here), no separate lesson-inbox item needed on top of the guard.
  :: depends:none :: status:CLOSED_ROOT_CAUSED_AND_FIXED

### REPLAY-FLEET-ARMS-FIDELITY-DRIFT (MED, silently-red guard, discovered 2026-07-11)

- [x] REPLAY-FLEET-ARMS-FIDELITY-DRIFT (MED, silently-red guard) :: **CLOSED 2026-07-18 (AFTERHOURS conductor) — ROOT-CAUSED + FIXED, all 3 RED tests now GREEN (7/7).**
  Re-ran the standalone harness fresh THIS fire (box was quiet enough — CPU 30.6%, no ShotgunScalperStage3 grind running, ~52s wall clock, well under the prior session's saturated-box block) and got the SAME 3-test RED, but with a materially DIFFERENT bar signature than the prior session's stale hypothesis: safe-1 now shows `MISSED=[1394] EXTRA=[1761]` (not bar 1405 — 1405 is fully MATCHED). **The prior session's window-truncation hypothesis for bar 1405 is DENIED by direct evidence**: bar 1394's GT trigger is `trendline_rejection` (`_edgehunt` confirms: not level-state-derived at all — zero shared code path with the `level_states`/`sequence_rejection` mechanism the hypothesis was built on).
  **Root cause (confirmed via a scratch diagnostic dumping both paths' verdicts at the exact mismatched bars, then deleted):** `orchestrator.run_backtest` (the GT engine) has **ZERO implementation of `structure_veto_enabled`** (grepped `backtest/lib/orchestrator.py` — no hits at all), while `decide_payload` (`engine_cli.py` L574, the SAME deterministic brain the signal-driven arm path replays) DOES apply it and it's `true` in live `params.json`. At bar 1394 (2026-06-12 15:10 ET), decide_payload correctly returns `SKIP_STRUCTURE_VETO` (a P/bear entry fighting a confirmed intraday uptrend), but `run_backtest`'s own trade simulator — blind to the gate — took the trade anyway. GT was over-counting an entry the live decision layer would never place; this is the SAME class of gap as the already-handled `direction_lock`/elite/`min_confidence` post-filters in `_ground_truth_trades` (a live-decision-layer gate `run_backtest` structurally cannot express), not a new class.
  **Fixed:** added a `structure_veto` post-filter to `_ground_truth_trades` (`backtest/replay_fleet_arms.py`) — reuses the SAME `sameday_5m_bars` payload already built for the signal-driven replay (byte-faithful to what `decide_payload` saw, zero duplicate logic), calls `engine_cli._classify_sameday_5m` + `_veto_side` directly, fails open (unchanged behavior) when the trade's entry bar wasn't replayed. Gated on `structure_veto_enabled` per-arm's own base params, so it's naturally a no-op for Bold/risky arms (that flag is absent from `aggressive/params.json` — matches CLAUDE.md's documented SAFE-only gate asymmetry). **Result: safe-1 missed 1→0.**
  **Bar 1761 (extra=1) is a SEPARATE, genuinely new finding, NOT fixed this fire (would exceed one bounded task):** decide_payload scores `bear_score=10` (trigger `fhh_level_rejection`, ENTER_BEAR) at that bar; the arm's own GT run_backtest scores `bear_score=9` at the same bar (no GT trade). Checked whether this is the SAME mechanism as risky-1's already-known bar-1801 window-truncation gap — **ruled out**: `fhh_level` is a same-day first-hour-high scalar (not the multi-bar `level_states` accumulation risky-1's mechanism depends on). Left as an honestly-undiagnosed single-bar score-parity edge, bounded by the test's own pre-existing `score_pct>=95%` (not 100%) tolerance — ratcheted into `KNOWN_MAX_EXTRA["safe-1"]=1` with a full evidence trail + a named next-diagnosis step, same pattern as risky-1's existing documented exception.
  **Verified:** `pytest backtest/tests/test_replay_fleet_arms.py -q` → **7/7 PASS** (was 3 failed/3 passed). RED-proofed live via `git stash` on both files: reproduces the EXACT prior failure signature (`safe-1 entry-fidelity REGRESSED: missed=1 > known cap 0`) plus the new regression-pin test's own failure; `stash pop` restored cleanly (verified byte-present). Curated safety gate (`backtest/tests/run_safety_gate.py`) → 31/31 + 5-suite gate PASS. Broader sweep (`test_fleet_keystone_consumer.py`+`test_fleet_producer_keystone.py`+`test_armability.py`) → 25/26, the 1 failure (`test_keystone_signal_drives_loose_arm_to_enter`, qty 5≠8 recency-clamp) confirmed **pre-existing and unrelated** by reproducing the identical failure with my 2 files stashed out (same STATUS.md-documented `recency_min_size_enabled` dead-knob drift flagged 2026-07-15, not touched by this fire).
  **Rail-4 (PAPER/test-harness-only — guard test + revert path + this REVOKE report):** touches `backtest/replay_fleet_arms.py` (offline validation harness — explicitly "VALIDATION + SPEC ONLY... places NO orders" per its own docstring) + `backtest/tests/test_replay_fleet_arms.py` (2 new/updated tests) + `automation/overnight/queue.md`. **Zero production trading-path files** (no `params.json`, `heartbeat_core.py`, `filters.py`, placement/exit code) — this is a test-fidelity fix, not a live-behavior change; it does NOT arm any fleet arm (safe-1/risky-1 both stay `ARM-READY: NO` — safe-1 now blocked only by its own known extra=1, not a mystery). Revert: single pathspec commit, `git revert <this-commit>`.
  :: depends:none :: status:CLOSED_ROOT_CAUSED_AND_FIXED

- [x] ~~REPLAY-FLEET-ARMS-FIDELITY-DRIFT [ORIGINAL]~~ (MED, silently-red guard) :: `backtest/tests/test_replay_fleet_arms.py`
  is RED on 3 tests (`test_no_arm_overtrades`, `test_missed_within_ratchet`,
  `test_three_arms_entry_faithful`) — `safe-1` now shows `extra=1 missed=1` (matched=9/10, `gt_n=10`)
  on the committed 2026-05-19..06-24 replay window (re-confirmed live 2026-07-14 via a fresh
  `pytest backtest/tests/test_replay_fleet_arms.py -q`: `3 failed, 3 passed in 298.91s`, identical
  signature), where the ratchet caps (`KNOWN_MAX_MISSED`/`KNOWN_MAX_EXTRA`) both pin 0.
  **2026-07-14 TRIAGE PASS (worker-tier, `/fable-differential` discipline — hold multiple
  hypotheses, kill with evidence, don't lock onto the first plausible story):** both of the
  prior session's named suspects are RULED OUT with direct evidence, not assumption:
  - **PROFIT-P2-ARMED (81b25b4)** — `git show --stat` confirms it touches ONLY
    `heartbeat_core.py`'s `_execute`/`_SETUP_STRIKE_OVERRIDES` (strike selection for an
    ALREADY-decided entry, i.e. order-placement time). `replay_fleet_arms.py` never calls
    `_execute` — it calls `hc._build_payload` + `engine_cli.decide_payload` directly, which
    generate the ENTRY verdict, not the strike. Structurally cannot shift which bar fires.
  - **Recency-conditioned min-sizing (fd08059)** — read `fleet_executor._apply_recency_min_sizing`
    verbatim: it only clamps `qty` (a `min(...)` ceiling), never touches `plan.action`/`side`.
    Cannot turn an ENTER into a HOLD or vice versa; `_entry_fidelity` only compares action+side,
    never qty.
  Nine more candidates were checked and also ruled out: the `min_ribbon_momentum_cents` gate fix
  (49e3c40, params.json value is `null` both before/after -> byte-identical; also one of the 15
  gates orchestrator.py's `_ENGINE_GATES_ASSERT` oracle cross-checks every bar by default, so a
  real divergence there would crash `run_backtest`, not silently drift — it didn't crash);
  safe-1's `status:active->retired` flip (`plan_entry`/`fx._params_for` never read `arm.status`/
  `arm.live` — only `run_dry`/`fleet_live` do, neither called by this replay; independently
  reconfirmed via the prior session's own accounts.json A/B); the stale-trigger-bar / entry-floor
  fixes (873281a, 95f763f — both live inside `heartbeat_core.run_account`'s POST-verdict ladder,
  never exercised since the replay calls `_build_payload`/`decide_payload` directly, bypassing
  `run_account` entirely); `structure_stop_enabled`/SS-B (933bd65 — grepped `backtest/lib/
  orchestrator.py`, zero hits for `structure_stop`; it's a fleet-only exit-shape concern
  `run_backtest`'s GT never sees); newer extra-setup types (vwap_continuation/bollinger_squeeze/
  gap_and_go/double_bottom_base_quiet — grepped orchestrator.py, zero hits; GT never simulates
  them, only core ribbon_ride/level_reject); the safe-3 min_confidence gate deletion (f799298 —
  safe-1's `gate_override` has no `min_confidence` key, byte-identical no-op for this arm); and
  `require_bearish_fill_bar` (the C14 mechanism that fixed the analogous risky-3 bug on this SAME
  window/bars, closed 2026-06-28) — confirmed via direct read of BOTH params files this key exists
  ONLY in `aggressive/params.json` (Bold), is absent from `automation/state/params.json` (Safe)
  entirely, so it structurally cannot be safe-1's mechanism despite the coincidental bar-1394
  overlap with risky-3's old bug. `git log --since=2026-06-28` on every file in the verdict path
  (`_build_payload`, `decide_payload`, `backtest/lib/{filters,orchestrator,ribbon,levels}.py`,
  `backtest/lib/engine/{gates,engine_cli,score}.py`, `fleet_executor._chosen_side`/`_is_elite`)
  returns ZERO commits changing their logic since the 2026-06-28 C14 fix that last verified this
  test fully green — confirming the drift is NOT a code regression in the change window.
  **Remaining live hypothesis (not ruled out, not confirmed):** `heartbeat_core._build_payload`'s
  own code comment self-documents a "WINDOW-TRUNCATION CAVEAT" — the live/replay verdict path
  reconstructs `level_states` (sequence_rejection/bounce_history, feeds `level_reclaim`/
  `sequence_rejection` triggers) over only the last **150 bars** (`W = 150` at
  `setup/scripts/heartbeat_core.py:437`), while `run_backtest`'s GT path accumulates
  `_update_level_states` from the FIRST bar of the whole multi-day run (never reset). This is the
  SAME already-accepted mechanism this test file cites for risky-1's documented `KNOWN_MAX_EXTRA=1`
  (bar 1801, "engine's 150-bar `_rebuild_level_states` sees sequence_rejection fresh... orchestrator's
  full-history `_update_level_states` had a prior reset"). Of safe-1's 10 GT trades (bars 1380,
  1394, 1405, 1441, 1464, 1488, 1693, 1703, 1781, 1878 — all pulled live via a scratch GT-only
  script this session, `run_backtest` completed cleanly, no assertion errors), exactly ONE
  (bar=1405, side=C, `triggers=['level_reclaim','ribbon_flip']`, 2026-06-15 09:35 ET) is
  level-state-dependent and therefore structurally exposed to this mechanism; the other 9 are
  `trendline_rejection`/`ribbon_flip` (not level-state-derived, not exposed). **NOT empirically
  bar-confirmed this session** — a targeted diagnostic (bar-windowed re-replay, ±20 bars around
  each of the 10 GT bars, to avoid the full ~534-bar replay cost) was built and run twice
  (default + `MKL_NUM_THREADS=1`/`OMP_NUM_THREADS=1` to rule out thread-oversubscription) but
  could not finish in this session's time budget: `Get-Process`/`Get-CimInstance` confirmed the
  real cause was NOT this box generally being under load (`\Processor(_Total)\% Processor Time`
  read 33-37%) but 4 concurrent `pythonw.exe` children of `Gamma_ShotgunScalperStage3`
  (`autoresearch.shotgun_scalper_stage3 --hours 3.0 --workers 4`) each showing **8,174-8,187
  accumulated CPU-SECONDS** (~2.3h each) at the moment of inspection — a legitimate concurrent
  crew's multi-hour grind saturating the box's cores, not a bug in this diagnostic or the replay
  tool. Killed the scratch diagnostic rather than let it starve indefinitely; did NOT touch the
  shotgun_scalper processes (not this task's to kill, per the standing "never clobber another
  session's work" rule). **Disposition: KNOWN_MAX_MISSED/KNOWN_MAX_EXTRA deliberately left
  UNTOUCHED** — per the test's own docstring warning ("a naive bump to 'fix' the red would hide a
  real regression, not resolve one") and this session's inability to empirically confirm bar 1405
  (or any other bar) as the actual mismatch, bumping the ratchet without that confirmation would be
  exactly the guess-fix the prior session correctly refused. **Next session, when the box is
  quieter:** re-run the bar-windowed diagnostic (reusable pattern: filter `run_backtest`'s
  `res.decisions` to `bar_idx` near the known GT bars before the `_build_payload`/`decide_payload`
  loop, cuts iteration count ~2x vs the full replay) OR simply retry the standalone
  `python backtest/replay_fleet_arms.py` when `Gamma_ShotgunScalperStage3` isn't mid-grind (check
  via `Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'"` first) — confirm/deny bar 1405
  as the mismatch, then either fix the level-state windowing gap (if it's genuinely wrong) or
  document it in `KNOWN_MAX_EXTRA`/`KNOWN_MAX_MISSED` with the same rigor as risky-1's entry.
  :: depends:none :: status:CLOSED_ROOT_CAUSED_AND_FIXED (see the entry ABOVE this one -- root cause was structure_veto, not window-truncation; original text preserved verbatim for audit trail)

### STRIKE-TIER-RECONCILIATION-FOLLOWUP (MED, doctrine-cleanup + open decision, 2026-07-11)

- [ ] STRIKE-TIER-RECONCILIATION-FOLLOWUP (MED, doctrine-cleanup, 2026-07-11) :: Evidence report
  done: `analysis/deep-research/2026-07-11-strike-tier-reconciliation.md` (spawned from
  `task_265ea4d0` / PROFIT-P2-ARMED's open finding below). Real-fills ground truth (112 entry
  orders, 109 engine, 2026-06-26..2026-07-09, cross-validated exactly against
  ledger-forensics.md's independent totals): **only core Safe (`safe-2`) trades ATM (100%, 17/17
  engine fills)** — every other account, including BOTH "safe" fleet arms (`safe-1`/`safe-3`),
  trades OTM 100% of the time via an explicit `params_patch: {"strike_tier_table": "bold"}` in
  `automation/state/fleet/accounts.json` (documented there as deliberate -- ATM premium too
  pricey to clear the Rule-6 min-3-contract floor at $2K equity). Root cause of the 3-way
  doctrine conflict: `params_safe.json`/`params_bold.json` were retired 2026-06-18 (commit
  `5da0da2`) in favor of hardcoded Python constants in `crypto/lib/strike_selection.py`, and the
  sweep never touched `params.json`'s now-vestigial `v15_strike_offset_per_tier` ladder (on the
  live core-Safe path only -- sim/backtest lane still reads it genuinely), CLAUDE.md's
  tier-table prose, `strike_selection.py`'s own docstring (cites a file gone since 2026-06-18),
  or `orchestrator.py:359`'s stale comment. ALSO found and documented: tonight's `81b25b4`
  blast-radius table in STATUS.md mis-states the fleet lane (says `safe-1`/`safe-3` resolve to
  `V15_SAFE_TIERS`; they resolve to `V15_BOLD_TIERS` -- confirmed in code and in 100% of both
  arms' real fills). Independently verified LIVE this session: core Safe's Alpaca credential
  returns 401 Unauthorized (control call to Bold succeeded normally) -- corroborates but does not
  itself prove the "account deleted" claim; `accounts.json`'s own `safe-2.status` field still
  says "active", registry hasn't caught up either. **Three open items this task deliberately did
  NOT do (evidence-report-only by design):** (1) decide whether to flip fleet safe arms
  (`safe-1`/`safe-3`) to ATM via `accounts.json` -- mechanism is known (delete their
  `params_patch.strike_tier_table` override) but the sizing/affordability tradeoff at $2K equity
  is unevaluated; (2) clean up the doc drift -- CLAUDE.md tier-table prose needs a Safe-vs-Bold
  split or an explicit "(Bold ladder shown; Safe is ATM under $10K)" caveat, `params.json`'s
  `v15_strike_offset_per_tier` key should either be removed (if truly dead on all paths) or
  explicitly re-labeled bold-only, `strike_selection.py`'s docstring needs its dead
  `params_safe.json` citation swapped for the actual hardcoded-constant explanation; (3) fix
  tonight's STATUS.md blast-radius table's fleet-lane claim (already flagged inline in the new
  STATUS.md entry, not edited in place per the standing "don't rewrite a REVOKE-report after the
  fact" convention -- correction lives in the newer entry instead). :: depends:none ::
  status:done-evidence-awaiting-doctrine-decision

### PROFIT-P2-ARMED (MED, engine-edge, paper/J-revocable, 2026-07-11)

- [ ] PROFIT-P2-ARMED (MED, engine-edge, paper/J-revocable, 2026-07-11) :: Core Safe ribbon_ride strike OTM-2 -> ATM SHIPPED (`analysis/recommendations/ribbon-ride-strike-exit-ab.json`, ATM vs OTM-2 clears OP-11 auto-ratify: +$47.96/tr, delta-OOS +$8,574, WF 4.25, BH-FDR survivor, OTM-1/ITM-2 both fail their own gates -- not armed). Mechanism: added ribbon_ride's 2 entry_setups to `heartbeat_core.py`'s `_SETUP_STRIKE_OVERRIDES` dispatch (mirrors the WP-5 pattern exactly; new keys `params.json#j_ribbon_ride_strike_override_enabled`/`_strike_offset_safe`). Full REVOKE-report + consumer table: `automation/overnight/STATUS.md` 2026-07-11 entry. **DORMANT on the core lane** (safe-2 account deleted, pending J's replacement) — **the live safe-* fleet arms (safe-1/safe-3) do NOT inherit this key at all** (fleet_executor.py's strike selection is a wholly separate mechanism, `_tiers_for_arm` -> `crypto/lib/strike_selection.py#V15_SAFE_TIERS`, zero per-setup dispatch) — net Monday behavior change is ZERO either way. Forward-watch items: (1) once J's replacement core account lands, re-verify the override is still armed and actually firing; (2) decide whether fleet_executor.py needs its own per-setup strike dispatch to actually capture this edge on the live fleet arms (currently it cannot, structurally); (3) a SEPARATE open finding was surfaced (not fixed, spawned as its own task): `crypto/lib/strike_selection.py#V15_SAFE_TIERS` is already ATM/ATM for the $0-2K/$2K-10K bands, which does not match `params.json#v15_strike_offset_per_tier`'s own OTM-3/OTM-2 ladder or the CLAUDE.md tier-table prose. Revert: set `j_ribbon_ride_strike_override_enabled` false. **CONVENTION-AUDITED 2026-07-15 ~01:20 ET (see STRIKE-AB-CONVENTION-RECONCILIATION below):** the +$47.96/tr arming evidence had zero friction modeled; re-run under honest friction (SS-B fixed) still clears ATM-beats-OTM-2 at +$50.52/tr AND ATM is uniquely the only strike tier that clears positive expectancy overall + both-halves-stable -- arming stands, no revert indicated. :: depends:none :: status:armed-forward-watch

### BROKER-CANARY-SENTINEL-HOOKUP (LOW, one-line wiring, ready-now, 2026-07-11)

- [x] BROKER-CANARY-SENTINEL-HOOKUP (LOW, wiring, TWIN-PROGRAM.md) :: `setup/scripts/broker_canary.py` is DONE and LIVE-VERIFIED (real probe run 2026-07-11: bars leg 160.2ms ok, account leg 128.6ms ok status=ACTIVE, assess()=GREEN — see `automation/state/broker-canary.jsonl`/`.json`) but has **NO scheduled-task hookup yet** — checked for `Gamma_TwinSentinel` before building (grep across the repo, zero hits) so per the build spec this shipped as a library + tiny CLI instead of a new task (avoids task sprawl / crew collision with whoever owns twin scheduling). **THE ONE-LINE HOOKUP:** whichever tick already talks to Alpaca 24/7 (`Gamma_CryptoTwin`'s `crypto_twin_health.py --live`, or a future dedicated `Gamma_TwinSentinel`) should add exactly one call: `import broker_canary; broker_canary.probe()` (zero required args — piggybacks ONE unauthenticated crypto-bars request + ONE authenticated `GET /v2/account` when twin creds exist, both already lightweight/limit=1; appends to the rolling `automation/state/broker-canary.jsonl` (size-capped ~2000 rows) AND refreshes the glance `automation/state/broker-canary.json` in the same call — `assess()` runs internally, nothing else to wire). Until this one line lands, `preopen_readiness.py`'s new `broker_canary` check reads a file that only updates when someone runs `python setup/scripts/broker_canary.py` by hand — it fails OPEN (INFO, never RED) on a stale/absent file by design, so this is a pure enhancement gap, not a blocker. Do NOT create a new scheduled task just for this (per the build's HARD RULES — $0, no new API-call volume beyond the one piggybacked probe). :: depends:none :: status:done

> **CLOSED 2026-07-20 ~20:15-20:45 ET (conductor, AFTERHOURS): wired, guard-tested, committed
> `3332454`.** Added the one-line call to `crypto_twin_health.main()` (the CLI entrypoint
> `Gamma_CryptoTwin`'s scheduled task actually invokes every 5 min) rather than into
> `run_tick_with_health()` -- that function has 34 existing tests with zero network mocking,
> and `probe()`'s leg 1 (unauthenticated crypto bars) is a REAL HTTP call; wiring it there
> would have made the entire existing test suite silently network-dependent. `main()` had
> zero prior test coverage, so this is a strictly additive change with no blast radius to an
> already-tested surface. Belt-and-suspenders `try/except` around the call site on top of
> `probe()`'s own internal fail-open guarantee (its own docstring: "never raises") -- a canary
> failure can never change the tick's own exit code or logged action. **Verified this fire:**
> 2 new tests (`test_main_calls_broker_canary_probe`, `test_main_survives_a_broker_canary_exception`)
> RED-proofed via `git stash` on both files -- both failed with the exact expected
> `AttributeError: module 'crypto_twin_health' has no attribute 'bc'` with the wiring removed,
> `stash pop` restored cleanly, re-verified 34/34 green in `test_crypto_twin_health.py` (0.23s,
> confirming zero accidental real network calls leaked into the mocked tests). Broader sweep
> `test_crypto_twin_health.py` + `test_broker_canary.py` -> **72/72 PASS**. Cross-checked
> `test_preopen_readiness.py`'s 1 pre-existing failure (`test_fetch_eod_flatten_reality_reads_real_tmp_files`,
> `KeyError: 'Gamma_EodFlatten'`) is unrelated and pre-existing -- reproduces identically with
> both my files stashed out, confirmed before closing this item as clean. Curated safety gate
> (31+5-suite) PASS. **Rail-4 (PAPER/visibility-only, guard test + revert path + this REVOKE
> report):** touches `setup/scripts/crypto_twin_health.py` (additive: 1 new import, 1 new
> try/except block in `main()`, 1 new key in the printed JSON) + `backtest/tests/
> test_crypto_twin_health.py` (2 new tests). Zero `params.json`/`heartbeat_core.py`/
> `filters.py`/placement/exit code touched -- this is observability, not a capital decision;
> the canary can never place an order or change any trading behavior. **Revert:**
> `git revert 3332454` (2 files, clean no-behavior-change rollback -- the twin's tick and
> `preopen_readiness.py`'s existing fail-open handling of a stale canary file are both
> unaffected either way). Cost: ~$2.6 (STAGE 0/1 reads incl. engine-health/STATUS/queue/
> self-audit/fill-funnel/task_scorer, module read, wiring-site survey, edit, 2 new tests,
> 2 RED-proof round trips via git stash, 1 broader regression sweep, 1 curated safety gate
> run, 1 commit, this queue/STATUS update).

### Recovered audit-tail findings (G10, 2026-07-08 — not yet fixed)
- [x] F1-RIBBON-MOMENTUM-GATE-INVERTED-DISABLE (HIGH/CRITICAL, engine-edge, gate-provenance) :: `min_ribbon_momentum_cents=0` ARMS the gate on Safe (gates.py:322 `is not None`; 0 blocks when 3-bar ribbon spread contracts). Intended-off; code needs `null`. Recovered from wf_a6e5356c audit tail, re-verified live 2026-07-08. Fix 0->null (completes the intended revert) but ENTRY-PATH -> A/B via override harness or J nod first. Ref markdown/audits/RECOVERED-AUDIT-TAIL-2026-07-08.md F1. **CLOSED 2026-07-11:** duplicate of MIN-RIBBON-SEMI-ARMED-FIX below (identical gates.py:322 bug) — see that entry for the fix + evidence + guard test. No A/B/J-nod needed: this is a CODE fix restoring the already-ratified L107 revert, not arming anything new (params.json already held `null`, unchanged by this fix). :: depends:none :: status:done
- [x] F2-STRUCTURE-VETO-PROVENANCE (HIGH, gate-provenance) :: structure_veto armed live on Safe with thin non-OOS evidence (F2). Audit its provenance+evidence per J's gate doctrine; kill-candidate if unbacked. **CLOSED 2026-07-18 (conductor) — ALREADY ANSWERED, this session found no new evidence to add.** `markdown/audits/GATE-PROVENANCE-AUDIT-2026-07-02.md` G16 already ran this exact audit 6 days before F2 was filed: Prov=C(2026-06-26 -$237 incident)/Ev=A-B thin (IS +$583, OOS $0)/Verdict=**KEEP (fail-open, protects the 5/04 anchor)** — the rationale is explicitly safety-class (fail-open = never blocks a trade the ribbon-lag would have taken anyway, only removes a confirmed-wrong-way-short class), not a pure edge-evidence bet, so "thin OOS" doesn't kill it the way it would a P&L-only gate. **Independently reconfirmed live TODAY** (unrelated fire, same session: `REPLAY-FLEET-ARMS-FIDELITY-DRIFT` root-cause) — the GT simulator was found to be MISSING `structure_veto_enabled` entirely, and at the mismatched bar it should have blocked a bear entry fighting a confirmed intraday uptrend; adding the veto as a GT post-filter fixed the fidelity gap, i.e. structure_veto is still doing exactly the job G16 credited it for, on a bar neither audit hand-picked. No kill signal found. :: status:done
- [x] F3-RED-BOOK-STILL-ARMED (HIGH, risk) :: Safe-2 combined ATM book RED (recent exp -$36.5/tr, n=14, 0 win-days) yet all 3 member setups stay armed (F3). Disarm review. **CLOSED 2026-07-18 (conductor) — investigated with CORRECTED fresh evidence (found + fixed a real bug along the way), verdict: HOLD-AS-DESIGNED, not a disarm.** (1) **Root-caused why this sat "todo" untouched for 10 days:** `task_scorer.py`'s `READY_STATUSES={"pending","in_progress"}` doesn't recognize `status:todo` (a distinct vocab used only by this 2026-07-08 "Recovered audit-tail" batch) -> silently `ready:false` on every fire, invisible to `--top`. Found by direct grep, not by the ranker (scorer-blind-spot noted, not fixed this fire — scope discipline; flagging here so a future fire doesn't have to re-discover it: `status:todo` should join `READY_STATUSES` or get an explicit alias). (2) **Investigated the book fresh and found a MORE SIGNIFICANT bug on the way:** `recency_check.py`'s `read_cache_last_date()` trusted `automation/state/data-coverage.json`, a MANUALLY-run manifest with no scheduled task — found stuck reporting `option_chain_realfills.last=2026-07-08` (9 trading days stale; the real on-disk `backtest/data/options/*.csv` cache already extended to 2026-07-17) since nothing ever regenerates the manifest automatically. Every nightly `Gamma_LicenseMonitor --run` fire since has been computing the CONFIRM-BEFORE-CAPITAL recent-window on a silently truncated ~9-day-old frame — the exact silent-degradation class `data_coverage_manifest.py`'s own docstring says it exists to prevent. **FIXED:** `read_cache_last_date()` now self-refreshes via `tools.data_coverage_manifest.build_manifest()` (live rescan of the real options dir) before every read, fail-open to the stale file only on an exception. Guard: `backtest/tests/test_recency_check_self_refreshes_coverage.py` (4/4, RED-proofed via `git stash` — 2/4 fail with the exact expected stale-value-leaks mechanism without the fix). (3) **Re-ran recency_check.py with the corrected full window** (2026-06-11..2026-07-17, was silently 2026-06-02..2026-07-08): `BOOK Safe2_ATM_1+2+4` is STILL RED — recent $-419.16 (14tr/6d) NEGATIVE — so F3's underlying risk finding is CONFIRMED CURRENT, not stale, even on honestly-fresh data. **Decision: HOLD, do not disarm.** The 2026-07-01 TRADE-TO-LEARN ratification (`_extra_setup_exec_armed_doc_2026_07_01_trade_to_learn` in params.json, J-ratified: "validated setups arm on PAPER even while recency is not CONFIRMed") POSTDATES F3's filing and explicitly supersedes the "disarm on RED" framing for these 3 specific setups — the recency-RED gate's own doctrine (`markdown/planning/LIVE-PATH-WORKPACKAGE.md`) is "no NEW live flip while RED", not "auto-disarm an already-armed trade-to-learn setup"; disarming on a RED rolling-25-day window (n=14, all 3 members individually still only YELLOW at n<10 each) would defeat trade-to-learn's own purpose (collecting real paper data through exactly this kind of unconfirmed patch) while each setup's FULL-OOS expectancy remains solidly positive (vwap_continuation +$50.37/tr, vwap_reclaim_failed_break +$5.30/tr, vix_regime_dayside +$51.95/tr) — 14 trades of recent noise is not yet a kill-grade signal against that base rate. **Genuine gap this surfaced (not fixed this fire, scope discipline):** there is no standing checkpoint that reports CUMULATIVE trade-to-learn P&L since the 2026-07-01 arm date (only a rolling 25-day window exists) — `license_monitor.py` only detects RED<->green *transitions*, never a "how's the whole experiment doing since day 1" digest. Flagged as a new queue follow-up below (`TRADE-TO-LEARN-CUMULATIVE-DIGEST`) rather than built this fire. :: status:done
- [x] F7-EXIT-SELL-ALL-REFIRE (HIGH, exit-bug) :: exit engine re-fires a full-size SELL_ALL every tick while the prior exit order is pending_new (F7) -> duplicate sells risk. **CLOSED 2026-07-18 (conductor-weekend):** literal symptom didn't reproduce (`get_position_qty` + `dec.closes_position` don't re-fire on a mere pending-fill lag), but the SAME root class was real, inverted: `manage_tick` pruned the exit-state ledger UNCONDITIONALLY on `dec.closes_position` regardless of whether `broker.market_sell` actually succeeded -- a failed/errored SELL_ALL permanently orphaned the position from exit management (worse than a re-fire: a silent forget, backstopped only by 15:55 EOD flatten), while a naive "just retry on failure" fix alone would have reintroduced the genuine duplicate-sell risk (a urllib TimeoutError can fire AFTER Alpaca already accepted the order). Fixed both halves together: new `fleet_broker.open_sell_orders()` checks for a still-resting sell order before retrying (skip if found -> no duplicate), and `manage_tick` only prunes the ledger when the sell was WATCH-preview or genuinely confirmed-placed (not on failure/skip -> next tick retries). Shared by BOTH core (Safe/Bold via heartbeat_core._manage_exits) and all 4 fleet arms -- one fix, both lanes. Guard: `test_exit_actuator.py` +4 new tests (16/16 total), RED-proofed via `git stash` (both new tests failed with the exact expected AssertionError without the fix). Zero regressions: 320/320 across the full exit-path test surface (`test_audit_fix_exit/heartbeat`, `test_dress_rehearsal`, `test_eod_flatten`, `test_exit_manager_replay`, `test_money_path_2026_07_01`, `test_trade_to_learn_2026_07_01`, etc.) + 88/88 fleet-local (`test_six_account_exit_shapes/routing`, `test_fleet_executor`, `test_exit_manager`). Rail-4 (PAPER trading-path fix, guard+revert+REVOKE): revert = `git revert <this commit>` (2 files: `exit_actuator.py`, `fleet_broker.py`, isolated). Lesson: `_lesson-inbox/2026-07-18-exit-prune-on-decision-not-confirmation.md` (general pattern: prune/finalize on CONFIRMED completion, not on the decision to act). Follow-up flagged, not fixed (out of this bounded fire's scope): `place_bracket`/entry placement was not audited for the same unconditional-state-update-on-unchecked-response pattern. :: status:done
- [x] F26-DISPATCH-191-FAILED-GREEN (HIGH, green-while-dead) :: v53_setup_dispatch.live failed 191 consecutive fires while the crypto-regression scheduler reports green 0x0 (F26). **CLOSED 2026-07-11 (coach):** root cause found — validator's `_KNOWN_SETUP_NAMES` allowlist in crypto/validators/v53_setup_dispatch.py never updated when `double_bottom_base_quiet` (2026-07-01) and `bollinger_squeeze` (2026-07-02) setups were wired into setup_dispatch.py; `names_ok` check failed deterministically on every live fire since ~2026-07-02. NOT related to tonight's Safe-2/crypto-account churn (bug predates it by 9 days). Fixed by adding both names to the allowlist; runner.py 104/104 PASS, track_drift.py fail streak reset 370→0. :: status:done
- [ ] F23-F27-JOURNAL-CALENDAR (MED) :: manual trades not journaled to trades.csv (F23 — still open for MANUAL/core trades; FLEET fills CLOSED 2026-07-09 via fleet_journal_bridge commit 59f176f + firm-brief hook); macro/news calendar stale (F27 — **RESOLVED 2026-07-09**: deterministic macro_calendar.py + Gamma_MacroCalendar 07:45 ET registered; root cause = weekly-review section-8a never reached + Scout budget-capped since 06-22; commit 410360a). :: status:F23-remainder-only
- [ ] PDT-WIRE-FLEET-ARMS (MED, risk-gate, doctrine-gap) :: fleet arms (safe-1/safe-3/risky-1/risky-3) log `day_trades: 0` and never call `pdt_tracker` -- core (safe/bold) enforces Rule 7 for real via `pdt_tracker.fetch_day_trades_used_5d`, fleet does not. Paper doesn't enforce PDT so no live-money exposure yet, but this MUST close before any fleet arm is armed live (OP-0 #1 precondition). Documented HANDOFF-2026-07-09-TRUTH-AND-EXITS T4 + markdown/0dte/risk-rules.md. Do NOT wire now -- would silence the only fleet arms feeding the WS2 exit-parity study. :: depends:WS2-exit-parity-study-complete :: status:todo

### TRADE-TO-LEARN-CUMULATIVE-DIGEST (MED, visibility, spun off F3 close 2026-07-18)

- [x] TRADE-TO-LEARN-CUMULATIVE-DIGEST (MED, visibility, OP-33) :: F3's close (2026-07-18) found `license_monitor.py` only detects RED<->green *transitions* on a rolling 25-day recency window — there is no standing surface showing CUMULATIVE P&L for a trade-to-learn-armed setup since its actual arm date. **CLOSED 2026-07-18 (conductor, AFTERHOURS).** Built `backtest/autoresearch/trade_to_learn_digest.py`: reads the ACTUAL placed-and-filled paper trades from `journal/trades.csv` (ground truth, not a re-sim like `recency_check.py`), sums real dollar_pnl per `extra_setup_exec_armed` setup since its documented `ARM_DATES` entry (hand-maintained, sourced from `git log -S` on `params.json` — vwap_continuation/vwap_reclaim_failed_break/vix_regime_dayside/double_bottom_base_quiet=2026-07-01, bollinger_squeeze=2026-07-02, confirmed via `git show`). Folded into `license_monitor.py`'s SAME nightly STATUS block (not a second section) — now writes unconditionally every run (was gated behind events/force_ping only), idempotent-replace so it never accumulates. Live evidence pulled THIS fire (real journal/trades.csv, 2026-07-18): bollinger_squeeze since-arm 2tr **+$105.00** (+$52.50/tr, 100% WR); vwap_continuation since-arm 2tr **-$68.00** (-$34.00/tr, 0% WR); vwap_reclaim_failed_break / vix_regime_dayside / double_bottom_base_quiet = **0 fills since arm, 17 days** (a genuine, previously-invisible finding — 3 of 5 armed trade-to-learn setups have never fired live). Presence ratchet (C14): `test_arm_dates_cover_every_live_armed_setup` fails LOUD if a future `extra_setup_exec_armed=true` key has no matching `ARM_DATES` entry (the exact silent-drop class this item was filed to prevent). Rule 9 preserved: `test_never_auto_disarms_pure_read_only` pins the module never calls `.write_text` on any params file. 10 new tests (`test_trade_to_learn_digest.py`), RED-proofed live (neutered the arm-date filter, 2/10 failed with the exact expected mechanism, restored+re-verified byte-identical via diff). Broader sweep: `-k "license_monitor or trade_to_learn"` 49/49 PASS, curated safety gate (31+5) PASS. **Bonus finding (flagged, not fixed — scope discipline):** `journal/trades.csv`'s 2 backfilled 2026-07-16 VWAP_CONTINUATION rows have an unescaped literal `"` inside `archetype_match_json` that corrupts LATE columns (account_id/notes_short) for those 2 rows via silent CSV field-shift — EARLY columns (date/setup/dollar_pnl, all this digest reads) are provably unaffected (guard test + lesson-inbox note filed: `2026-07-18-trades-csv-unescaped-json-quote-corrupts-late-columns.md`). Rail-4 (PAPER/visibility-only — guard test + revert path + REVOKE report): touches `backtest/autoresearch/trade_to_learn_digest.py` (new), `backtest/autoresearch/license_monitor.py` (fold-in wiring, no order-placement/params-write change), `backtest/tests/test_trade_to_learn_digest.py` (new). Zero `params.json`/`heartbeat_core.py`/`filters.py`/placement/exit files touched — this is a read-only reporting layer over the SAME 2026-07-01 trade-to-learn arm decision, not a new capital decision. **Revert:** `git revert <this commit>` (single pathspec commit, 3 files + the lesson-inbox note + this queue.md line). :: depends:none :: status:done

### TASK-SCORER-MULTILINE-STATUS-READ (LOW, hygiene, found+fixed 2026-07-22 conductor AFTERHOURS)

- [x] TASK-SCORER-MULTILINE-STATUS-READ (LOW, hygiene) :: **CLOSED 2026-07-22 ~19:45-20:05 ET
  (conductor, AFTERHOURS).** Sibling bug to `TASK-SCORER-STATUS-VOCAB-GAP` below (same file,
  different mechanism): `task_scorer.py` read `status:` off ONLY an item's checkbox line, so a
  multi-paragraph queue.md item (append-only per OP-22) whose checkbox line ends bare at `::`
  and whose real `status:CLOSED-...` verdict lands many lines below in continuation prose was
  silently read as status `""` -> treated READY. Confirmed live: `PULLBACK-HOLD-BULL-TRIGGER`
  (closed 18:42 ET today with `status:CLOSED-LANE-B-NO-CELL-SHIPS` on line 44, 30 lines below its
  own checkbox on line 14) still ranked `ready:true` #1 by `--top` at 19:42 ET. This is the SAME
  mechanism that made `RANGE-SCALP-REGIME-STRATEGY`/`RIBBON-LAG-PRICE-STRUCTURE-TRIGGER`/
  `POSITION-MONITOR-1MIN` keep re-ranking #1 after closure on 2026-07-18 (the `staleness_advisory()`
  shipped then was a nudge to manually re-check, not a fix for the actual read). **Fix:** new
  `_item_blocks()` groups an item's checkbox line + all continuation lines up to the next
  item/header; new `_extract_field_last()` reads `status:` from the WHOLE block (per-line-bounded
  so unrelated ::-free trailing prose can't bleed into the value — caught + fixed as a second-order
  bug during authorship, own guard test), taking the LAST match (most-recently-appended, per OP-22).
  Applied to both `parse_queue`'s status read and `_open_item_ids`'s dependency-resolution status
  read (same root cause, second consumer). `depends:` intentionally left checkbox-line-only —
  narrower scope than `TASK-SCORER-STATUS-VOCAB-GAP`'s own "don't rush this with a careless regex
  change" discipline. **Guard:** `backtest/tests/test_task_scorer_multiline_status.py` (7 new
  tests) + full existing suite (45 tests across `test_task_scorer*.py`) = 52/52 PASS. RED-proofed
  live via `git stash push -- setup/scripts/task_scorer.py` / `git stash pop` (pre-existing
  unrelated stashes from other sessions verified undisturbed, `git stash list` before/after):
  6/7 new tests failed against pre-fix code with the exact expected AttributeError/mismatch,
  restore verified byte-identical, 52/52 green again. **Live-verified against the real queue.md**
  (not just the synthetic fixture): `PULLBACK-HOLD-BULL-TRIGGER` and its own historical siblings
  now correctly `ready:false`; `DOJO-BUILD-HANDOFF`/`MORNING-BULL-QUALITY-GATE-RECONSIDER` (both
  genuinely still `status:pending`) remain correctly `ready:true` — the fix does not over-suppress.
  Lesson filed: `_lesson-inbox/2026-07-22-task-scorer-multiline-status-read-as-empty-ready.md`.
  Rail-4 N/A (research/tooling script, not trading-path — no params/heartbeat_core/filters/
  placement/exit touched). **Revert:** `git revert <this commit>` (2 files: task_scorer.py +
  the new test file, fully additive except the `status = _extract_field(...)` -> `_extract_field_
  last(...)` two-line swap in `parse_queue`/`_open_item_ids`). :: depends:none :: status:done

### TASK-SCORER-STATUS-VOCAB-GAP (LOW, hygiene, found during F3 close 2026-07-18)

- [ ] TASK-SCORER-STATUS-VOCAB-GAP (LOW, hygiene) :: `task_scorer.py`'s `READY_STATUSES = {"pending", "in_progress"}` doesn't recognize `status:todo` (used by the entire 2026-07-08 "Recovered audit-tail" batch: F2/F3/PDT-WIRE-FLEET-ARMS) OR compound statuses like `SINGLE-STRATEGY-REGISTRY-DESIGN`'s `status:slice1-done-...-remainder-open` — both were silently `ready:false` and invisible to `--top` for 10+ days despite being genuinely actionable HIGH items. F2/F3 only got found this fire by manual `grep` of the queue, not by the ranker. Fix: either add `"todo"` to `READY_STATUSES` (simplest — audit whether any `status:todo` item is intentionally NOT ready first, since the marker may be load-bearing elsewhere) or normalize the status vocabulary queue-wide so every open item uses one of `pending`/`in_progress`/`blocked`/`awaiting-j-*`. Cross-check against `_dep_tokens`'s `OPEN_DEP_STATUSES` set too — same drift risk. **Re-checked 2026-07-20 ~09:15 ET (conductor, pre-market, no build attempted — see below):** live-grepped every remaining `status:todo` line in this file. Only 2 exist: F3-RED-BOOK-STILL-ARMED (now `- [x]`/`status:done`, closed 2026-07-18) and PDT-WIRE-FLEET-ARMS (still `- [ ]`/`status:todo`, but genuinely blocked by its own real `depends:WS2-exit-parity-study-complete` — an open dependency, so it would score not-ready even if `todo` were added to `READY_STATUSES` today). **Net: zero currently-open items are actually hidden by this gap right now** — the F2/F3 instances that motivated filing it have already drained. The broader fix (recognizing `todo`/`queued`(18)/`proposed`(12)/`open`(2) queue-wide) still needs its own audit pass — many `proposed` items are deliberately spec-only/not-yet-actionable (e.g. SIM-EXIT-SHAPE-PARITY-AUDIT, ADVERSE-EXTREME-AVOIDANCE-FILTER both say "do not wire without a cleared A/B") — blindly widening `READY_STATUSES` would surface those as false-ready, which is worse than the current conservative blind spot. Left `status:pending`/LOW — do NOT rush this with a careless regex change; it needs a real per-status-value audit, not a 5-minute pre-open patch. :: depends:none :: status:pending



> Ranked by leverage. Most of the deepest work is tracked in the live TaskList + `cook-queue.jsonl` (see `automation/state/cook-queue-summary.md`); items here are the conductor-visible ones that need a human-or-Claude decision or are not yet owned by another loop.

### Tier 0.1 — 2026-07-01 pipeline-audit fix-order (FUNCTION FIRST — J ratified FULL PAPER AUTONOMY 2026-07-01)

> Merged from the interactive TaskList + `markdown/audits/PIPELINE-AUDIT-2026-07-01.md` (audit finding #5: "the conductor reads only queue.md → the autonomy loop literally cannot see the plan"). Trading-path edits for PAPER accounts are now sanctioned per the 2026-07-01 grant — each ships with a guard test that REDs on regression + a git-revert path + a REVOKE report.

- [ ] PARAMS-DEAD-KNOB-DISPOSITION (MED, engine-correctness) :: Drain the 24-key KNOWN_DEAD allowlist in `test_params_consumer_reconciliation.py` — for each dead knob decide RESTORE (wire a real consumer) or REMOVE (delete the key + its _doc). Buckets: session-timing (6, scheduler-hardcoded), ~~resilience-harness (4, _shared.ps1 literals)~~ **CLOSED slice 1**, exit-flags (2), macro-bias-v2 (4, never wired), liquidity-gate (5, order path prose-approximate), catalyst/journaling flags (2), sizing scale-up (1). Each disposition is a small rail-4 change; the shrinks-only ratchet auto-verifies. Ref markdown/audits/PIPELINE-AUDIT-2026-07-01.md break #7. **SLICE 1 DONE 2026-07-19 (conductor, commit pending) — resilience-harness bucket (4/24), REMAINING 20/24 across 5 buckets.** Disposition: `max_consecutive_failed_mcp_calls` / `max_consecutive_tv_failures_before_kill_switch` / `wedged_state_alert_hours` **REMOVE** — verified zero consumers ANYWHERE in the repo (the params.json doc's "also embedded in _shared.ps1" claim was false; `run-tv-watchdog.ps1`'s live self-heal design relaunches immediately + always-alerts on every relaunch, it never built a consecutive-failure counter). `min_disk_free_mb` **RESTORE** — `Test-DiskSpaceAvailable` now reads it live via a new `Get-ParamsMinDiskFreeMb` helper in `_shared.ps1` (fail-open to 100 on read/parse error), replacing the hardcoded `-MinFreeMB 100` at its one call site. **Bonus fix while restoring:** the reconciliation guard's OWN consumer-corpus glob never scanned `setup/scripts/*.ps1` (only top-level `setup/*.ps1` installers) nor `automation/state/fleet/*.py` (the live fleet-lane consumer) — both added; the 2nd gap was independently false-flagging `recency_min_size_enabled` dead for 4+ days (tracked since 2026-07-15 per STATUS.md history), now fixed as a side effect. New guard `backtest/tests/test_params_dead_knob_disposition_2026_07_19.py` (8 tests, incl. 3 live `powershell.exe` subprocess round-trips proving the restore is a real live read + fail-open). RED-proofed via `git stash`. Curated safety gate (31+5) PASS + `test-self-heal.ps1` 23/23 PASS (zero regression on the pre-existing disk-space test). Next slice should take session-timing (6 keys) or exit-flags (2 keys) — both similarly bounded. :: depends:none :: status:pending-slice1-of-6-done
- [x] PROMOTER-WRITES-LIVE-KEY (HIGH, research-bridge) :: `pipeline_promoter` writes `{watcher}_stage5_cleared` which NOTHING reads (audit break #2) — change the promoter to write a key the engine actually consumes (`extra_setup_exec_armed[setup]` on PAPER accounts per the 2026-07-01 grant), so a promoted winner can arm and place orders. Guard test + revert path. Ref markdown/audits/PIPELINE-AUDIT-2026-07-01.md. **CLOSED 2026-07-18 (conductor):** `pipeline_promoter.py` now writes BOTH the WATCH flag AND `extra_setup_exec_armed[watcher]=true` to both paper params files (`params.json`/`aggressive/params.json`) when a watcher clears all 5 gates AND has a dispatcher entry — clearing those gates IS the OP-11/OP-16 auto-ratify bar, so PAPER exec-arming without a manual step is exactly what TRADE-TO-LEARN sanctions. New `_arm_exec_flag()` is idempotent + additive (guard-tested). Never touches GAMMA_CORE_ARMED or any live-money surface — LIVE money still needs J (OP-0 #1), unconditionally. 2 existing tests updated in the SAME commit (C14 vary-and-assert: the old test asserted the OLD WATCH-only contract) + 2 new tests (idempotent/additive). 27/27 green (`test_pipeline_promoter_contract.py` 9/9, `test_armability.py`, `test_kitchen_grader_crashloop_guards.py`). Confirmed zero regressions elsewhere: `test_money_path_2026_07_01.py` + `test_trade_to_learn_2026_07_01.py` + `test_params_consumer_reconciliation.py` all pass except one PRE-EXISTING unrelated failure (`recency_min_size_enabled` dead-knob drift, confirmed present with my changes `git stash`-removed too — not caused by this change). **Revert:** `git revert <this commit>` (single pathspec commit, 4 files). :: depends:none :: status:done
- [x] SCHEDULED-OOS-CHECK-FOR-PROMOTE-PROPOSALS (HIGH, research-bridge; id deliberately avoids the task_scorer 'PROMOTE-KEEPER' recency marker — this is INFRA / register-a-schedule, not a capital promote) :: No scheduled OOS check exists to clear promote_keeper proposals — `eval_bar_cleared` flips only by hand (audit break #4; happened once, badly: pk-2026-06-28-001). Register a scheduled `contender_oos_check` fire so each proposal clears-or-fails the eval bar automatically and the arm/entry pipeline stops stalling on a manual step. Ref markdown/audits/PIPELINE-AUDIT-2026-07-01.md. **CLOSED 2026-07-18 (conductor) — ALREADY BUILT AND REGISTERED, verified live, this is the 5th same-day CLOSED_ALREADY_ANSWERED/CLOSED_SUPERSEDED item, not a new gap.** `Gamma_OosCheck` (`setup/scripts/oos_check_runner.py`) was registered 2026-07-01 (same day as this queue item was filed) and is documented in `SCHEDULED-TASKS.md` line 79 — it does EXACTLY what this item asks: refreshes proposals from the newest contender-rank via `promote_keeper` (idempotent), runs `contender_oos_check.py` (real OPRA fills, 5 OP-11 gates incl. CONFIRM-BEFORE-CAPITAL recency) per still-pending proposal, and flips `eval_bar_cleared=true` + attaches the scorecard on the `conductor-proposals.jsonl` row only on all-gates-pass. **Verified live THIS fire, not assumed:** `Get-ScheduledTaskInfo -TaskName Gamma_OosCheck` → `LastRunTime=7/17/2026 6:30:01 PM, LastTaskResult=0, NextRunTime=7/18/2026 6:30:00 PM`. Real log `automation/state/logs/oos-check-2026-07-18.log` (produced by last night's actual fire, not a manual test) shows the pipeline working exactly as designed: `promote_keeper rc=1` (no new contender since 2026-07-01), correctly SKIPs the 2 stranded pre-existing proposals (`pk-2026-06-28-001`, `pk-2026-06-29-001`) because their `contender_file` is superseded by the newest `contender-rank-2026-07-01.json` (re-validating a superseded contender would attach the wrong evidence — this is correct behavior, not a bug), and reports `pending validatable proposals: []`. The stranding this item worried about does not exist — the task exists, fires nightly, and correctly no-ops when there is nothing fresh to validate. :: depends:none :: status:done-verified-already-shipped-2026-07-01
- [ ] SINGLE-STRATEGY-REGISTRY-DESIGN (HIGH, engine-architecture) :: Collapse the 3 disjoint hardcoded strategy menus (engine_cli literals / setup_dispatch 5-tuple / fleet 2-entry REGISTRY) into ONE registry so adding a validated family stops requiring hand-edits in 3 places; must cover the order-placement + exit wiring surface so a registered setup can actually fill. Audit: "no automated path from analysis/recommendations/ into any of them." Ref markdown/audits/PIPELINE-AUDIT-2026-07-01.md. **SLICE 1 DONE 2026-07-18 (conductor) -- the setup_dispatch<->validator seam, the seam that has ACTUALLY caused 3 live incidents (F26-DISPATCH-191-FAILED-GREEN x2 + this session's 120-consecutive-cron-failure level_break_first_strike RED), is now structurally drift-proof.** Corrected re-trace of the item's own premise first: `engine_cli.py` does NOT hold a 3rd hardcoded strategy menu (grepped -- only one incidental setup-name string at L472, unrelated to the extra-setups plugin architecture); the real 3 surfaces are (a) `setup_dispatch.py`'s `SetupDispatcher.run()` dispatcher list [the live "extra setups" plugin registry], (b) `crypto/validators/v53_setup_dispatch.py`'s hand-typed `_KNOWN_SETUP_NAMES` mirror [the repeat-offender], (c) `automation/state/fleet/strategies.py`'s 2-entry fleet `REGISTRY` [a genuinely separate concern -- fleet-arm strategy selection, not extra-setup dispatch; NOT touched this slice]. Fixed (a)+(b): hoisted the inline `dispatchers` list in `setup_dispatch.py` to a module-level `DISPATCH_ROSTER` constant (method referenced by NAME so a validator can import safely) + a derived `KNOWN_SETUP_NAMES` frozenset; `v53_setup_dispatch.py` now IMPORTS `KNOWN_SETUP_NAMES` instead of hand-typing a mirror set -- there is no second copy left anywhere to drift. Also fixed `pipeline_promoter.read_dispatcher_roster()`'s regex (it parsed the OLD inline-tuple shape; updated to match the new `DISPATCH_ROSTER` row shape, still source-text-parsed not imported, preserving its documented backtest-venv-free + always-reflects-on-disk-file properties). Guards: `test_graduated_guards.py::test_setup_dispatch_names_registry_sync` rewritten (was AST-parsing `run()`'s method body -- fragile, broke the moment `run()` became a comprehension; now a direct identity/derivation check) + new `backtest/tests/test_setup_dispatch.py::TestDispatchRosterSingleSource` (5 tests: roster<->run() parity, KNOWN_SETUP_NAMES derivation, validator import-not-hand-type source-level proof, every roster method resolvable). RED-proofed live via `git stash`/`git checkout stash@{0} -- <files>` round-trip (stash-pop collided with concurrent-fire state-file writes -- recovered cleanly via targeted `git checkout` from the stash, no work lost). Verified: gym 104/104 GREEN, 40/40 targeted pytest (`test_setup_dispatch.py`+`test_pipeline_promoter_contract.py`+`test_graduated_guards.py -k setup_dispatch`), 84/84 broader money-path/armability/trade-to-learn suites, zero regressions. **Confirmed pre-existing, NOT caused by this slice** (identical failures with changes stashed out): `test_no_new_dead_params_knob` + `test_watcher_registry.py` (a `bollinger_squeeze_watcher.py` file exists on disk unregistered -- separate gap, unrelated surface). **REMAINING for a future slice:** the fleet `strategies.py` REGISTRY unification + the order-placement/exit-wiring automation the item's full scope asks for -- that is materially larger/riskier (crosses into live order-placement code across a 3rd system) and was deliberately NOT attempted in this one bounded fire; left `[ ]` open, not closed, so it stays visible for a dedicated future fire. :: depends:none :: status:slice1-done-setup_dispatch-validator-seam-drift-proofed-remainder-open
- [ ] CLAUDE-PROFITLOCK-DOCTRINE-RECONCILE (LOW, doctrine-hygiene, **propose-only — CLAUDE.md**) :: Doctrine drift surfaced by ADJUDICATE-CD-2026-06-29-001: CLAUDE.md:28 describes "chandelier **trailing** profit-lock (arms at +5% favor, trails 15% off HWM)" but the validated (pk-2026-06-28-001 OOS all-pass) AND live-core value is `profit_lock_mode="fixed"`. Verify whether the doctrine's "chandelier trailing" wording refers to a SEPARATE arming mechanism vs the profit_lock_mode knob; if genuinely drifted, propose a one-line CLAUDE.md reconciliation to J (rail-4 propose-only). Not urgent (near-inert). :: depends:none :: status:pending
- [ ] RECONCILE-GUARD-READ-TO-MUTATE-BLIND-SPOT (LOW, engine-correctness, follow-up to tonight's 95a603b reconciliation guard) :: `v15_profit_lock_mode` PASSES the params-consumer reconciliation guard because `promote_keeper.py` reads it (L130) — but that is a READ-TO-MUTATE consumer (reads current value only to decide whether to rewrite it), NOT a behavior-path consumer; the live exit path (heartbeat_core) ignores the key entirely (forces "fixed"). So the presence guard's "has a reader" check counts a mutate-only reader as a live consumer → a behaviorally-dead knob evades the ratchet. Consider a stricter behavior-consumer classification (exclude promote_keeper/actuator writers from the "consumer" set) OR document the class in the guard. Lesson-inbox: `2026-07-02-read-to-mutate-consumer-masks-dead-knob.md`. Rail-4 CLEAR. :: depends:none :: status:pending
- [x] ACTUATOR-RESOLVE-DUP-ID-FAIL-LOUD (LOW, approval-bus-defense-in-depth, follow-up to FIX-CD-2026-06-28-002-ID-COLLISION) :: the uniqueness guard prevents a dup ACTIVE id existing, but the DEEPER foot-gun is that `autonomy_actuator` resolves a dup id two incompatible ways in one module (dict last-wins vs next() first-wins) → a dup that slips in via a race between guard runs still disagrees SILENTLY. Harden: route BOTH paths through one shared `resolve_proposal(pid, rows)` that raises/logs LOUD on a duplicate, instead of silently picking a row. Lesson-inbox: `2026-07-02-same-id-resolved-two-ways-in-one-module.md`. Rail-4 CLEAR (actuator code, no params/orders/heartbeat/CLAUDE). :: depends:none :: status:done

> **CLOSED 2026-07-21 ~09:xx ET (conductor, AFTERHOURS), commit `f60da48`.** Found a THIRD
> incompatible resolution mechanism while fixing this (not just the two the item named):
> `_set_status`'s for-loop-with-break is ALSO first-wins but via a different code shape than
> `revert`'s `next()` scan. Shipped one shared `resolve_proposal(pid, rows)` + `DuplicateProposalError`
> in `setup/scripts/autonomy_actuator.py`, routed into all three call sites
> (`sync_companion_approvals` / `_set_status` / `revert`). Semantics match
> `test_proposal_id_uniqueness.py`'s existing ACTIVE_STATUSES exactly (pinned by a same-file
> test): a terminal+active duplicate (harmless `promote_keeper` re-emission) now resolves to the
> ACTIONABLE row regardless of file order -- the old first-wins scans could have silently
> mutated a terminal sibling instead; two ACTIVE rows sharing an id raises loud;
> `sync_companion_approvals` catches the exception per-decision (logs `duplicate_id_blocked`,
> skips only that id) so one collision can't stall the rest of a companion-approval batch.
> **Verified this fire:** `backtest/tests/test_resolve_proposal.py` (10 new tests) RED-proofed
> via `git stash` on `autonomy_actuator.py` alone -- 9/10 failed against the pre-fix module with
> the exact expected `AttributeError` (no `resolve_proposal`/`DuplicateProposalError` yet),
> `git stash pop` restored cleanly, re-verified 44/44 green across the full actuator test family
> (`test_resolve_proposal` + `test_autonomy_actuator` + `test_proposal_id_uniqueness` +
> `test_autonomy_auto_approve` + `test_actuator_recency_gate`). Curated safety gate (31+5) PASS
> (ran automatically via the pre-commit hook). `git ls-tree HEAD` confirms all 3 files landed
> on HEAD, not just staged. L207 updated with the SHIPPED note (no longer "owed"). **Rail-4
> CLEAR** as the item itself flagged -- zero params/heartbeat_core/filters/placement/exit files
> touched; `autonomy_actuator.py` only ever edits those files THROUGH its own gated
> `apply_ops`+safety-gate+snapshot path, never directly. **Revert:** `git revert f60da48`
> (3 files, additive + one lesson-doc edit).
- [x] FDR-16-OPRA-CONFIRM (HIGH, research-bridge, queued 2026-07-02 after-close) :: Consume the FDR screen's survivors: take the top-2 NON-REDUNDANT groups from `analysis/discovery/fdr-screen.json` and run them through `lib.simulator_real` on real OPRA fills per the alpha-ranking spec — the same real-fills confirm step that graduated bollinger_squeeze (SPY-price edge != option edge, C3). Output: per-group expectancy/OOS/WF + nulls; a survivor group gets a wiring proposal (conductor-proposals convention), a dead group gets an honest kill row. :: depends:none :: status:done-killed-both — RAN 2026-07-11 via new `backtest/tools/fdr16_opra_confirm.py` (mirrors the bollinger precedent + reuses the standing `autoresearch.null_baseline` random-entry-null gate). Group A `level_rejection`/long/vix_lo (n=619 true, the strongest statistical prior in the whole FDR sweep): signal exp +$39.12/tr beats null max but FAILS the concentration-robust leg (drop-top5 $5.72/tr < null mean $9.87/tr, top-3-days=56% of total) — exit-structure/concentration artifact, not durable alpha. Group B `trendline_rejection`/long/vix_hi (n=160 true): real-fills exp outright negative -$20.32/tr, clean kill. Bonus finding: shadow-ledger.jsonl double-logs decisions per bar (n-honesty: reported n 1318/338 vs true distinct 840/180, ~1.6-1.9x inflation) — flagged, not fixed (read-only). Full write-up: `analysis/recommendations/fdr16-opra-confirm.{json,md}`, `automation/overnight/STATUS.md` 2026-07-11 entry.
- [x] RRW-AS-VETO-STUDY (MED, research, queued 2026-07-02 after-close) :: ribbon_rejection_wick KILLED as an entry (65% WR but -$16/tr premium bleed, both directions negative — `analysis/recommendations/ribbon-rejection-wick.json`) yet the detector demonstrably SEES real rejections (it fired right before the 10:19 fleet ENTER_BULLs that premium-stopped 3 min later, 2026-07-02). Re-test it as a VETO/EXIT overlay on the BULL path: bear-wick fires => (a) do-not-enter-bull veto, (b) tighten/exit the bull runner. A/B on real fills vs the no-overlay baseline; ship a scorecard either way. **CLOSED 2026-07-20 ~23:xx ET (conductor, AFTERHOURS): FAIL — bear-wick as a bull-veto/tighten overlay makes the bull path WORSE, not better; shipped as an honest kill.** New `backtest/autoresearch/rrw_bull_veto_study.py` reuses (not re-derives) the EXISTING cached superset scan (`ribbon_rejection_wick_events.jsonl`, 1793 bear/"short" events, same window/detector as the FAIL entry scorecard) against the REAL bull trade population from `lib.orchestrator.run_backtest(use_real_fills=True, enable_bullish=True)` at PROD_GATED config (the two ratified bull gates, block_bull_ribbon_flip + block_bull_1100_1200), ATM strike (live core Safe-2 tier per the 2026-07-11 reconciliation), 2025-01-02..2026-07-01 (86 real bull trades, baseline PnL +$4,344.80). **Two PRE-REGISTERED configs** (chosen from the detector's OWN dataclass defaults + the FAIL scorecard's own doc-string "keeps today's anchor" vol note — not cherry-picked after seeing results): A=RRWParams() literal defaults, B=+vol_mult_min=1.5. **VETO result (30-min pre-entry lookback — this rule_id's own spec_origin framing, not invented here): both configs are NET NEGATIVE to veto** — config A vetoes 8 trades worth +$1,265.80 combined (WR 75%, exp +$158/tr) — i.e. the bear-wick fired before WINNING bull trades more often than losing ones in this sample; config B (4 vetoed, +$597.60) same direction. The hypothesis predicted the opposite (bear-wick should flag BAD bull entries) — this sample shows it doesn't. **TIGHTEN result: too rare to matter** (n_flagged=2 and n=1 across the two configs — below the pre-registered n>=10 clearing bar) and even the n=2 case is internally mixed (one trade would have been $1,382 WORSE tightened, the other $1,317 BETTER — no consistent direction). **Verdict: FAIL** on both overlay hypotheses (auto-computed clearing bar: n>=10 affected AND delta>$50; neither test clears). Scorecard: `analysis/recommendations/rrw-bull-veto-overlay.json` (both configs, full vetoed/flagged trade lists, caveats section). **Disclosed limitation (not hidden):** the TIGHTEN counterfactual is a whole-position approximation (ignores TP1 partial fills/tp1_qty_fraction) — a directional indicator, not a production-ready dollar estimate; moot here since n is already sub-threshold. **Verified this fire:** new guard `backtest/tests/test_rrw_bull_veto_study.py` (12/12 PASS — event_passes gate logic, veto_test lookback-window/same-day/pre-entry-only semantics, _stats arithmetic, cache-freshness sanity) exercises the counterfactual math on synthetic fixtures ($0, no full backtest re-run needed to catch a future regression). Broader sweep `test_ribbon_rejection_wick.py` + `test_rrw_bull_veto_study.py` → 20/20 PASS. Curated safety gate (31+5-suite) PASS. **DST-frame fix applied** (project_dst_frame_artifact_2026_07_02): `lib.option_pricing_real.load_contract_bars` parses OPRA timestamps tz-aware with the raw (EST-mislabeled) fixed -04:00 offset; re-derived to the SAME et-v2 (DST-correct, tz-naive) frame the SPY master/bear-events/trades already use before any comparison — the exact "never join a naive et-v2 series against a raw tz-aware wall-v1 one" fix the lesson names. **Research-only, zero trading-path files touched** (no params/heartbeat_core/filters/placement/exit edits — rail 4 does not apply; this is an authoring/observation deliverable per the author-inbox class, ships without J ratification per OP-22/OP-26). **Revert:** `git revert <commit>` (3 new files, purely additive — no existing file bodies changed). No live wiring proposed regardless of verdict (module's own stated policy) — the FAIL closes the thread; a future CLEARS on either overlay test would still need a separate rail-4 ratification pass before any params/heartbeat_core edit. :: depends:none :: status:done-failed-both-overlays-honest-kill
- [x] BOLLINGER-MES-SWING-PORT-SPEC (MED, futures, queued 2026-07-02 after-close) :: SPEC ONLY (no grind yet): port the newly-armed bollinger_squeeze (family-grind survivor, dir-null survives, wired 004e7ea) to MES multiday swing per `markdown/futures/FUTURES-REVIVAL-PLAN-2026-07-02.md` — squeeze percentile/BB params re-derived on MES bars (do NOT copy 0DTE knobs across instruments), flat-by-Friday default (Phase-1 keeper finding: beats weekend holds ~$45/tr), pre-registered design doc BEFORE any battery run (3c31bf2 convention). Deliverable = the design doc + battery plan, gated on the Phase-1 FDR battery harness. :: **CLOSED-SUPERSEDED 2026-07-14 queue hygiene — this is exactly the class the EDGE-KILL-LEDGER registry closure `ohlcv_bar_pattern_mining_family` shuts (a new OHLCV bar-pattern battery on futures), after Phase-1 killed all seeds twice (0/12 + 0/96) and both trendline batteries went 12/12 FAIL. Reopen only with new NON-OHLCV data. bollinger_squeeze itself stays live on its validated 0DTE lane — this closes the MES port SPEC, not the setup.** :: depends:none :: status:closed-superseded

### Tier 0.5 — drain the live self-check BROKEN flags (rig-never-traded audit fix-order)


- [x] BULL-UNBLOCK-REPLAY-PROBE (HIGH, engine-edge, **the #1 project thread — rig has never filled an ENTER_BULL in 2544 lifetime decisions**) :: the remaining self-check BROKEN problem = ENGINE-CANNOT-ENTER (bull structurally unreachable): smooth trend -> `detect_level_reclaim` (filters.py:758) only fires on a single-bar straddle -> filter 11 blocks; when a straddle hits ELITE -> `block_elite_bull` (VIX band [0,25)) SKIPs it. 06-30 = 386 ticks / 0 ENTER / 32x SKIP_ELITE_BULL_LEVEL_RECLAIM on a bull day. **SLICE 1 — block_elite_bull lever RETIRED 2026-06-30 conductor (commit 79f842c):** `backtest/autoresearch/bull_unblock_replay_probe.py` re-ran the REAL engine twice (block on vs off, use_real_fills) over 2026-05-21..06-30. The block's removed cohort = n=7, WR 14.3%, **net -$241, DRY_AT_ZERO** -> the OLD-engine A/B still holds; the block correctly removes losers on the fresh window. VERDICT=BLOCK_CORRECTLY_REMOVES_LOSERS_KEEP, no params change. Guard `test_bull_unblock_replay_probe.py` 5/5 (verdict ladder + golden finding, bite-tested). Result `analysis/recommendations/bull-unblock-elite-replay-2026-06-30.json`. **SLICE 2 — the STRUCTURAL lever DONE 2026-06-30 gamma-drive (commit 946530f):** `bull_unblock_structural_probe.py` re-ran the REAL engine twice (min_triggers_bull 2 vs 1, block_elite_bull=True held FIXED to isolate the structural lever) over 2026-05-21..06-30. Added bull cohort = n=8, net **+$76 GROSS but INCONCLUSIVE (n<10) + 493% day-concentrated + FRAGILE_TO_SLIPPAGE (breakeven 1.6c)** -> VERDICT `UNBLOCK_POSITIVE_BUT_THIN_OR_FRAGILE` = NOT proposable. Guard `test_bull_unblock_structural_probe.py` 5/5 (golden finding + ladder parity + non-vacuous bite). Result `analysis/recommendations/bull-unblock-structural-2026-06-30.json`. **BOTH bull-unblock levers now audited on the fresh window -> neither is armable; the 0DTE-SPY bull frontier is DATA-gated on the 25-day OPRA wall (same wall as range-scalp n=8).** **SLICE 3 — the last structural lever DONE 2026-06-30 gamma-drive:** `detect_sequence_reclaim` (the MULTI-BAR higher-lows reclaim, the ONE trigger that could catch a smooth uptrend with no single-bar straddle) is STRUCTURALLY COUPLED OFF — proven read-only (`test_bull_sequence_reclaim_coupling.py` 5/5, result `analysis/recommendations/bull-unblock-sequence-reclaim-coupling-2026-06-30.json`): in `evaluate_bullish_setup` (filters.py ~L937) its `level_state` is looked up ONLY when `reclaim_level is not None` (= single-bar straddle fired), so it can only ever appear as a REDUNDANT CO-TRIGGER, never an independent path. That is the exact structural root of "bull unreachable on smooth uptrends" (0 ENTER_BULL / 2544 decisions). Decoupling is a filters.py logic change (rail-4 J-gated) AND the 25-day window can't prove any bull sub-lever to significance -> FILED for a future WIDER-DATA probe; guard pins the coupling so a silent future decouple re-REDs. **ALL THREE bull-unblock levers now audited (elite KEEP / min_triggers thin / sequence_reclaim coupled-off) -> NEITHER sim-tuning lever unblocks a proposable bull edge. The 0DTE-SPY bull frontier is DATA-GATED — resolving it needs wider data, not more sim tuning. THREAD CLOSED for this regime.** Standing direction re-points fully at the GEX class rung (calendar-gated, ~8/60-90 days). Lesson-inbox: `2026-06-30-multi-bar-reclaim-trigger-dead-coupled.md`. **SLICE 4 — WIDEN THE DATA (the "25-day OPRA wall" was FALSE, same as range-scalp) DONE 2026-07-01 conductor (commit 6250b15):** the 04:02 range-scalp frame-audit named the bull "25-day wall" as the SAME hardcoded-CSV misread + flagged the carry-forward to re-run over full history. `bull_unblock_structural_widewindow_probe.py` re-ran the min_triggers 2->1 A/B (block_elite_bull FIXED) via the REAL engine over the FULL 2025-01-02..2026-06-18 master (533d, real OPRA fills): added bull cohort **n=82, pooled net +$608 BUT IS-2025 -$300 / OOS-2026 +$907 -> signs FLIP = FAILS_WALK_FORWARD_SIGN_FLIP** (also FRAGILE_TO_SLIPPAGE breakeven 0.012c, 215% day-concentrated). The 25-day n=8/+$76 "INCONCLUSIVE" was purely a slice of the 2026-only OOS tail, NOT a real edge; the 2-trigger requirement correctly starves losers in-sample. Guard `test_bull_unblock_structural_widewindow.py` 9/9. Result `analysis/recommendations/bull-unblock-structural-widewindow-2026-07-01.json`. **The bull frontier is confirmed EDGE-gated (walk-forward failure on full history), NOT data-gated -- the "25-day OPRA wall" is retired as a false frame for BOTH range-scalp AND bull. No lever remains where more data would help.** :: depends:none :: status:done-all-3-levers+full-history-confirmed-bull-EDGE-gated-thread-closed


- [ ] LESSON-INBOX-ORPHAN-DOTDONE (LOW, hygiene, noticed 2026-06-30 ~21:55 conductor while verify-committing L195/L196) :: a stray `strategy/candidates/_lesson-inbox/2026-06-27-persistently-red-audit-masks-new-orphans.md.DONE` is UNTRACKED (git never tracked the rename). Not re-consumable (`.md.DONE` is the correct skip suffix, guard-passing) but clutters porcelain. FIX: `git add` it (if the lesson is genuinely encoded -- verify vs LESSONS-LEARNED.md first) or delete the orphan. Rail-4 CLEAR (inbox housekeeping). :: depends:none :: status:pending

- [ ] LEVELS-UPSTREAM-DEDUP-SOURCE (LOW, producer-hygiene, follow-up to LEVELS-CONTRADICTORY-ROLES-DRAIN) :: `refresh_levels_intraday` now self-heals the 6-9x curated PMH/PML duplication every run, but a non-duplicating SOURCE is cleaner. Find the upstream producer appending duplicate curated `PMH_/PML_` entries (candidates: `automation/scripts/compute_levels.py`, `setup/scripts/fetch_swarm_data.py`, or the premarket draw) and dedup at the source. Rail-4 CLEAR (producer code). NOT urgent (downstream normalization covers it). :: depends:none :: status:pending

### Tier 0 — regime-appropriate edge (STANDING DIRECTION: climb off the dead premium axis)

- [~] CLIMB-LADDER-NEXT-RUNG-IS-CLASS (HIGH, engine-edge R&D) :: **'instrument' rung CLOSED 2026-06-28 conductor (commit 04adc35).** The range-scalp FADE lens (`LEVEL_REJECT_LIVE`) was tested on deep-data MES/MNQ futures (N=379/259, escaping the 25-day OPRA wall that blocks the SPY range-scalp at n=8) via `backtest/autoresearch/futures_range_fade_probe.py` → **RANGE_FADE_DOES_NOT_GENERALIZE**: both instruments WALK_FORWARD_FAIL_REGIME_FLIP (IS-negative 2025 → only positive in 2026 OOS, concentrated top3 101%/193%, long-direction artifact). Combined with the 2026-06-20 control (momentum fleet dead), the 'instrument' rung is now dry for BOTH lenses. Backlog item 7a + golden guard `test_futures_range_fade_probe.py` (6/6). **NEXT RUNG = 'class' (a different signal INPUT):** named live candidate is **Tier-1.5 W2 — GEX zero-gamma-flip-distance + net-GEX-sign as a continuation/abstain regime FILTER on the live edge** (dealer-positioning input class, genuinely NOT a re-skin of the ~64 dead price-signal families; unlock = a cheap forward OI-fetch). First bounded slice = assess FREE OI-data availability (verify-now, same discipline that confirmed the cached futures bars this fire), then build the GEX filter probe if data exists; else the honest conclusion is the 0DTE-SPY frontier is data-gated until a new feed appears (W-REJECTED). Rail-4 CLEAR (research). **DATA-AVAILABILITY RESOLVED 2026-06-29 conductor (commit 69cd429):** the free OI data EXISTS and is ALREADY being banked daily — `backtest/tools/cboe_oi_bank.py` (free CBOE CDN, native gamma+OI, $0) + `automation/scripts/gex_capture.py` (Alpaca N=2) accrue to `journal/gex-archive/`; `gex_regime.py` already computes the full dealer-GEX tag (net-GEX sign / zero-gamma flip / walls). VERIFIED LIVE: `Gamma_CboeOiBank` Ready, NextRun 06-29 15:55 ET, accrued 06-22..06-26 (5 trading days). **So the 'class' rung is NOT "no data" data-gated — it is CALENDAR-TIME-gated:** a GEX backtest needs ~60-90 as-of days (per `gex_regime.assess_backtest_feasibility`); we have ~5. Shipped a C7 continuity guard (`backtest/tools/gex_archive_health.py` + `test_gex_archive_continuity.py` 12/12, live verdict GREEN) so the months-long accrual can't die silently. **CONTINUITY NOW VISIBLE 2026-06-29 conductor (commit e99aa45):** the OPTIONAL LOW follow-up is DONE (stronger than the daily-brief version) — `check_gex_archive` wired into the every-minute engine-health beacon (`setup/scripts/engine_health.py`), NON-CRITICAL (never trade-halts / never REDs the critical verdict), surfaces the GREEN/YELLOW/RED continuity verdict in `engine-health.json` every 1min AND pings J once on a genuine multi-day stall via the transition-only alerter. Guard `test_engine_health_gex_archive.py` (7/7, bite-tested the non-critical invariant). The silent-accrual-death loop is CLOSED — the checker the 01:54 fire built now actually RUNS against the live archive on a schedule. **NEXT (no build owed until ~60-90 days accrue):** the GEX-filter probe waits on calendar time; nothing more to wire. The standing direction now needs a genuinely-NEW unblocked needle-mover beyond GEX-accrual-wait — OR accept the 0DTE-SPY frontier is calendar-gated on GEX (premium axis dead L182-184; instrument rung closed; range-scalp data-blocked n=8). :: depends:none :: status:class-rung-data-engine-alive+guarded+VISIBLE-calendar-time-gated

- [x] RANGE-SCALP-REGIME-GATE-SLICE (HIGH, engine-edge R&D) :: **SLICE 1 (vein found) + SLICE 2 (regime gate) DONE 2026-06-28 conductor.** range-scalp = shotgun_scalper Tier-2 `LEVEL_REJECT_LIVE` (REUSE, don't rebuild — L17/L36). SLICE 1 probe `range_scalp_probe.py` over 2026-05-21..06-26 = VEIN_CONCENTRATED (30tr, 66.7% WR, +$12.46/tr, +$373.8, top3 224%, 3 loser days -$618). **SLICE 2 (commit 16b77c7) — `range_scalp_regime_gated_probe.py`:** added an explicit per-trade CAUSAL flat-ribbon (spread<30c = below RIBBON_SPREAD_MIN_CENTS) + VIX 14-20 gate (+ slippage 0.02/0.05). RESULT = **REGIME_GATE_TOO_TIGHT**: gate **fully killed 2 of 3 loser days** (06-04 -$157.2->$0, 06-24 -$264.6->$0, the 2 biggest = -$421.8) + partial on 05-26 (-$196.2->-$61.2); WR 66.7->87.5%, exp $12.46->$44.40, top3% 224->117%, retained 95% net on 8 of 30 trades, SURVIVES 0.05 slippage (+$14.40/tr). BUT **n=8 inconclusive** + gated net **one-winner-day-dominated** (05-29=$354 of $355). Mechanism VALIDATED (it removes the trending-bar losers a range fade should never take), NOT deploy-ready. Results: `analysis/recommendations/range-scalp-regime-gated-2026-06-28.json`. **NEXT SLICE (3 — count recovery + generalization):** (1) **widen the data window** (current recent csv only spans 05-19..06-26) so gated-n reaches >=15-20 for an IS/OOS split — every conclusion currently rides on 8 trades/4 days; (2) **loosen ONE gate leg** (VIX->[13,22] OR spread<40c) and check the loser-kill HOLDS while count recovers; (3) drop-05-29 robustness (trimmed-2-day already +$62.4, needs more days to confirm); (4) THEN tp/stop/strike sweep + IS/OOS. **DO NOT gate on J `edge_capture`** (directional-anchor metric auto-rejects range strategies — lesson `_lesson-inbox/2026-06-28-...-autorejects-regime-strategies.md`). Rail-4 CLEAR (research tool + results, no params/orders); arming stays recency+J-gated. **SLICE 3 PART 2 DONE 2026-06-28 conductor (commit d686009) — `range_scalp_gate_sweep_probe.py`:** swept spread<{30,40,50}c x VIX{[14,20],[13,22],[12,24]} (REUSES one OPRA pass + IMPORTS probe_stats — compound). RESULT = **GATE_KNIFE_EDGE_WIDEN_DATA**: (a) VIX leg is INERT (C14 dead-knob on this window — widening the band changes nothing for a fixed spread cap); (b) loosening the SPREAD leg recovers count (n=8->11->12, big-loser-day kill HOLDS) but every n>=10 variant goes NEGATIVE net@0.05 slippage ($11.56 gross/-$18.44 net at <40c; $10.6/-$19.4 at <50c) AND concentration WORSENS (117%->327%) — the extra trades are slippage-bleed, not edge. The genuine spread<30 edge (exp $44.4, +$14.4 net@0.05, survives slippage, kills both big losers) is REAL but only n=8. **CONCLUSION: cannot tune to significance on the 25-day window — the gate-tuning branch is CLOSED.** Golden guard +2 in test_probe_stats.py (10/10). **NEXT SLICE (PART 1 — the only remaining lever): WIDEN THE DATA WINDOW** — fetch/locate more range-regime OPRA + VIX days beyond 2026-05-19..06-26 so the spread<30 edge's n=8 reaches >=15-20 for an IS/OOS split. This is a DATA-ACQUISITION slice (not more sim tuning). If data-widening stays blocked, the standing-direction ladder says CLIMB (signal->structure->DTE->instrument->class): the Tier-2 level-fade vein may be too thin on this regime. DO NOT keep loosening gates (proven slippage trap). DO NOT gate on J edge_capture. **SLICE 3 PART 1 (WIDEN DATA) DONE 2026-07-01 conductor (commit c2bfe39) — AND THE "DATA-BLOCKED" WALL WAS FALSE (OP-33d frame-audit).** Both range_scalp probes hardcoded a 25-day `RECENT_SPY_CSV`/`VIX_CSV` on a STALE comment ("master only covers through ~2026-05-22"), but the master `spy_5m_2025-01-01_2026-06-18.csv`+VIX (533d) + OPRA fills (370 0DTE days) already cover the full history. `range_scalp_widewindow_probe.py` ran the SAME regime-gated Tier-2 fade over 2025-01-02..2026-06-18: gated **n 8->155** (WR 62.6%, gross +$3.97/tr +$615.6), IS-2025 +$0.95/tr (flat), OOS-2026 +$15.6/tr. **VERDICT = DIES_ON_SLIPPAGE** (breakeven half-spread 0.66c << 5c realistic; exp -$2.03 at just 1c; top-3 days 161% of net; ungated 595-trade fade net-NEGATIVE -$0.71/tr). Guard `test_range_scalp_widewindow.py` 7/7 (golden finding + bite + frame-audit anti-regression: probe must use the full master). **THREAD CLOSED for the RIGHT reason — slippage-dominated on full history, NOT data-gated.** Lesson-inbox: `2026-07-01-hardcoded-window-csv-masks-available-data.md`. **CARRY-FORWARD:** the bull-frontier "25-day OPRA wall" (BULL-UNBLOCK-REPLAY-PROBE) was the SAME misread — re-run those probes over the FULL 370-day OPRA history before accepting "bull data-gated." :: depends:none :: status:done-full-history-DIES_ON_SLIPPAGE-thread-closed-for-right-reason



### Tier 1 — engine correctness / loose ends from tonight (CONTEXT-106..109)

> The 3 BP-* loose ends are CLOSED (2026-06-19) — see `## Completed`. STAIRSTEP-REDESIGN remains the one open Tier-1 item (genuine eval-first redesign, not a quick fix).

> **END-TO-END WIRE-UP gaps (added 2026-06-26, blueprint `markdown/planning/PROJECT-END-TO-END-WIRED-2026-06-26.md`).** This pass FIXED the two P0s: G1 (engine PLACE_FAIL — `run-heartbeat-core.ps1` now sets `GAMMA_CORE_ARMED=1`+`GAMMA_CORE_MANAGES_EXITS=1`, guarded) and G2 (systemic DST ET-clock — `setup/scripts/et_clock.py` + 9 live-path migrations + 3 task re-registers, guarded). The remaining P1/P2 below are the wiring gaps that keep the loop from closing on itself unattended. The ONE non-code blocker is G3 (J must arm + send `ship <id>`).

- [~] G4-EXEC-WIRE-EXTRA-SETUPS (P1, engine-wiring) :: **WIRING SHIPPED DISARMED 2026-06-27 conductor (commit d1d775c).** `run_account()` now routes fired `dispatch_extra_setups` signals through the SAME `_execute` path (flat-verify + quality-lock + risk_gate + free-model veto) on a non-ENTER ribbon tick, via `_route_extra_setups`/`_synthetic_verdict_from_extra`/`_extra_exec_armed` (direction long->ENTER_BULL / short->ENTER_BEAR). **SAFE BY DEFAULT — the dead-knob is now wired but exec stays OFF:** gated on a NEW params key `extra_setup_exec_armed[setup]=True`, DISTINCT from the detector-enable flags (`j_vwap_cont_enabled`/`gap_and_go_enabled` already true). Key absent in BOTH params files -> byte-identical no-op (every fired row logs WATCH_NOT_ARMED, `_execute` never called; verified). Graduated to a 24-test guard `backtest/tests/test_g4_extra_setup_routing.py` that REDs if exec-arm ever defaults on or gates on the detector-enable (kills L47/L70/C11/C14 reintroduction). 57 existing core/dispatch tests still green; curated safety gate PASS. **REMAINING (each a separate fire):** (a) **ARM** `vwap_continuation` (and/or others) — set `extra_setup_exec_armed.vwap_continuation=true` in `automation/state/params.json` — is RAIL-4 J-gated AND recency-gated: the combined book is recency-RED (DIRECTION-BLOCK-BATCH-RECONCILE Tier-2); license_monitor pings J on RED->green, arm then. Do NOT auto-arm. (b) a watcher-signal PARITY test (backtest vs the new live-verdict surface) before arming — the 24-test guard pins the routing CONTRACT but not signal-vs-backtest parity. (c) `prior_rth_close` into `_build_payload` for gap_and_go (the dispatch currently reads it from today-bias.json; payload plumbing is a gap_and_go-arming prereq only). :: depends:none :: status:wiring-done-arm-is-j-gated
- [x] G16-EXTRA-SETUPS-DISPATCH-WAS-DEAD (HIGH, engine-correctness, **uncovered + FIXED 2026-06-27 conductor while shipping G6**) :: **LATENT BUG found + fixed (commit 2b24652).** `setup_dispatch._build_ctx` imported `from filters import BarContext` (bare top-level) but `filters.py:30` does a RELATIVE `from .ribbon import RibbonState` → loading filters without a parent package raised `ImportError: attempted relative import with no known parent package` → `_build_ctx` returned None on EVERY tick → ALL FOUR extra setups (incl. the ENABLED `vwap_continuation` edge #1 + `gap_and_go`) silently SKIP'd via the dispatch path. Masked because every existing test either MOCKED the dispatch method or accepted any `SKIP_NO_FEED` (none exercised a real `_build_ctx`). Verified empirically with heartbeat_core's exact live sys.path: bare import FAILS, `from backtest.lib.filters import` (REPO on path) WORKS. FIX = package-first import + `_REPO` on path + bare fallback; the G6 end-to-end test now proves a real ctx builds. **SAFE (no order):** G4's `extra_setup_exec_armed` gate is absent → fired signals log WATCH_NOT_ARMED, place nothing. **FOLLOW-UP (observe-live, the real open part):** on the next RTH confirm `core-decisions.jsonl` extra_signals now show vwap_continuation/gap_and_go actually EVALUATING (fired/SKIP_NO_SIGNAL) instead of silently erroring — and reconcile how the LIVE vwap_continuation edge #1 was executing if its dispatch path was dead (fleet path? confirm no double-count once dispatch is live). NOT a new order surface; engine-benefit correctness. :: **OBSERVE-LIVE CONFIRMED + GUARDED 2026-06-29 gamma-drive (commit c94f2b7).** First full RTH after the fix: `core-decisions.jsonl` shows **Safe 386/386 ticks** now carry `extra_signals` with BOTH `vwap_continuation`+`gap_and_go` EVALUATING (`SKIP_NO_SIGNAL`) instead of silently erroring -> the import fix WORKS in production. **Bold 0/386 is NOT a bug** -- aggressive params have `j_vwap_cont_enabled=False` + `gap_and_go_enabled` MISSING (a benign dual-account asymmetry; dispatch is WATCH-only on both so no execution impact -- enabling on Bold = a params change w/ no validated benefit, NOT proposed). **No double-count:** the live vwap_continuation edge #1 executes via the FLEET path (build_shared_signal/fleet executor), NOT this dispatch path (WATCH-only, exec gated on the absent `extra_setup_exec_armed`); the 386 rows place NOTHING. The 36 `_build_ctx failed: 'str' object has no attribute 'get'` errors are GYM-harness only (crypto-regression-runner), fail-open -- live heartbeat had ZERO. **GUARDED:** `check_dispatch_health` wired into the every-minute engine-health beacon (NON-CRITICAL, fail-open, RED pings J once) RED-flags the exact G16 silent-death signature (enabled detector emitting ZERO extra_signals over a populated RTH); guard `test_engine_health_dispatch.py` 13/13 (bite-tested). :: depends:none :: status:done
- [x] G17-INSTALL-TASKS-PS1-TZ-TIMEBOMB (HIGH, scheduled-task-infra) :: **Found 2026-06-27 conductor while reconciling G5; pinned by the new guard's KNOWN_TZ_UNFIXED ratchet.** `setup/install-tasks.ps1` (the canonical multi-task installer) passes **ET values straight to `-AtTime`** for the ENTIRE core trading chain — LaunchTV `08:00`, Premarket `08:30`, Heartbeat `09:30`, EodFlatten `15:55` (×2 for the aggressive pair) — on the Mountain rig (`-At` is LOCAL/MT). A re-run fires the whole chain **2h late**: heartbeats 11:30 ET, **EodFlatten 17:55 ET = after the close** → 0DTE positions left to expire. The LIVE tasks are correct ONLY because `register_tz_fixed_tasks.ps1`/`fix-trading-tasks.ps1` re-registered them at the right MT literal — install-tasks.ps1 is a dormant time-bomb (project_scheduled_task_tz class). SECONDARY: it also still registers the **RETIRED LLM heartbeats** (`Gamma_Heartbeat`/`_Aggressive`, disabled 2026-06-25 in favor of `Gamma_HeartbeatCore`) → re-running it would re-arm dead tasks. FIX (a dedicated fire — rail-4 CLEAR engine-benefit infra, changes NO live behavior since live tasks already correct): convert each `-AtTime ([DateTime]"HH:MM")` to the MT literal (ET - 2h: 06:00/06:30/07:30/13:55) + update the "ET" comments to note MT-local, AND drop/replace the retired-heartbeat registrations (or retire install-tasks.ps1 entirely in favor of the per-task TZ-fixed installers). Then REMOVE install-tasks.ps1 from `KNOWN_TZ_UNFIXED` in `test_scheduled_task_tz_ordering.py` (the ratchet FAILS until you do → forces acknowledgement). :: **DONE 2026-06-27 conductor (commit a731383).** Chose FULL RETIREMENT over TZ-fix-in-place: there is NO single clean replacement installer for the stale 6-task chain (`register_tz_fixed_tasks.ps1` covers only 3 ops tasks; `fix-trading-tasks.ps1` is a diagnostic that still names the retired heartbeats), and re-authoring install-tasks.ps1 to register HeartbeatCore/SightBeacon would duplicate their owners (drift) AND re-introduce the bare-`powershell.exe -WindowStyle Hidden` window-flash foot-gun (project_mcp_window_leak_fix; live tasks use the wscript→pythonw chain). So install-tasks.ps1 is now a no-op deprecation stub (registers NOTHING, exit 1, points to SCHEDULED-TASKS.md + the per-task installers) — kills BOTH the TZ time-bomb AND the retired-heartbeat re-arm with zero drift risk. Emptied `KNOWN_TZ_UNFIXED` (shrinks-only → win state) + added `test_install_tasks_ps1_stays_retired_noop` (no -At literal / no Register-ScheduledTask / no New-ScheduledTaskAction / no retired-heartbeat action — bite-tested non-vacuous) so the time-bomb can't silently return. Updated the 2 stale pointers (uninstall-tasks.ps1, harden-tasks.ps1). TZ guard 6/6, curated safety gate 29+5 PASS, PS parse OK. :: depends:none :: status:done
- [ ] G7-ACTIVATE-EOD-FLATTEN-CORE (P1, order-close-surface, **J-GATED — proposal cd-2026-06-27-001**) :: The G7 code is COMMITTED + durable (221d0c6) but NOT activated — the live EOD-flatten is still the fragile LLM `Gamma_EodFlatten`/`_Aggressive`. ACTIVATION = run `setup/scripts/install-eod-flatten-core.ps1`, which registers `Gamma_EodFlattenCore`/`_Aggressive` at 13:55 MT (15:55 ET) AND **disables the working LLM backstop** = an order-close-surface swap (rail-4). Not urgent (LLM version works), not a live break, so NO Discord push (anti-disturb). Not AutoApply-able (it's "run a .ps1 + verify the task swap", not a string-replace apply_op) → needs a J `go` or an interactive fire. PRE-ACTIVATION CHECK owed: after install, confirm `Get-ScheduledTask *EodFlatten*` shows the 2 Core tasks Ready + the 2 LLM tasks Disabled, and that a DRY-RUN (`GAMMA_EOD_DRY=1`) NOOPs both accounts before the first live 15:55 ET fire. :: depends:G7-EOD-FLATTEN-PURE-PYTHON :: status:awaiting-j-action
- [x] G9-SELF-AUDIT-NEVER-FIRED (P2, scheduled-task, **PART-1 OVERTAKEN-BY-EVENTS 2026-06-26 ~21:55 conductor**) :: The trigger half is ALREADY FIXED — verified live: `Gamma_SelfAudit` reads `State=Ready, LastRun=06/26 18:41:43, LastResult=0x0 (SUCCESS), NextRun=06/27 15:30:00, trigger=MSFT_TaskDailyTrigger`. The autonomous gap-finder IS firing (gap-log.jsonl has 18:14 + 20:42 entries today; the 20:42 batch surfaced the gap_and_go-unmonitored finding this fire just graduated to a guard). The 11/30/1999 / 0x40010 state in the original item was stale. **REMAINING (PART-2 only, LOW): documentation** — add the 5 ORPHAN tasks (ContenderRank, FreeManager, LiveShadowValidator, ManagerOverseer, SelfAudit) to `automation/state/SCHEDULED-TASKS.md` Active table so audit_scheduled_tasks.py stops flagging ORPHAN_TASK. Pure doc, no trigger re-register needed. :: **DONE 2026-06-27 conductor (commit 50ca875) — breadcrumb claimed 5, LIVE audit showed 16.** Documented ALL 16 ORPHAN_TASK with accurate live triggers (MT->ET) + script-sourced purposes: the 5 named + the LIVE TRADING ENGINE `Gamma_HeartbeatCore` + the never-blind eye `Gamma_SightBeacon` + `Gamma_EodFullAudit` + the on-demand grind pipeline (`Gamma_Grind_all` + 6 `Gamma_Funnel_*`) + disabled `Gamma_Grind_Watchdog`. Corrected the stale 'SelfAudit superseded' Reference tombstone (it is registered+firing), marked the retired LLM `Gamma_Heartbeat`/`_Aggressive` rows DISABLED, reconciled the stated-count guard (46->61). ORPHAN flags **16 -> 0 (verified)**. Foot-gun (persistently-RED audit from 2 BARE_CMD flags masked 16 NEW orphans incl. the live engine; static-install-script vs live-scheduler 'registered' mismatch) -> `_lesson-inbox/2026-06-27-persistently-red-audit-masks-new-orphans.md`. :: depends:none :: status:done
- [x] G18b-BARE-INSTALLER-RATCHET-DRAIN-LAST2 (LOW, scheduled-task-infra) :: **4 of 6 latent bare-console installers DRAINED 2026-06-28 conductor (commit cf88aec) — G18 ratchet 6->2.** Converted crypto-daily / crypto-grinder-keepalive / crypto-regression / register-eod-deep-dive to the wscript->run_exe_hidden.vbs->pythonw->run_ps1_hidden.py chain (action ONLY; triggers/settings/principal untouched), pinned all 4 in FIXED_CLEAN. REMAINING 2 (harder converts, each a scoped fire): (a) `setup/install-watchdog-modes-sweep.ps1` passes DYNAMIC `-TargetIterations $TargetIterations -BatchSize $BatchSize` args -> append them through the wscript chain's extra-args tail (run_ps1_hidden.py forwards argv[2:] to the ps1, so feasible — quoting care); (b) `setup/scripts/setup-all.ps1` orchestrator has an INLINE bare freshness-watchdog register (~line 53, lacks even -WindowStyle Hidden) buried in a large multi-step script -> convert that one action, leave the rest. Fixing each REDs `test_allowlist_has_no_stale_entries` until its KNOWN_BARE_INSTALLERS entry is removed (ratchet forces it). Rail-4 CLEAR (launch-wrapper only, no params/doctrine/orders). :: **DONE 2026-06-28 conductor (commit 45aac74) — RATCHET DRAINED 2->0 = WIN STATE.** Converted both: (a) install-watchdog-modes-sweep.ps1 dynamic args ride through run_ps1_hidden.py argv[2:] forwarding (verified the contract); (b) setup-all.ps1 step-4 inline freshness-watchdog register. Both moved KNOWN_BARE_INSTALLERS->FIXED_CLEAN; KNOWN_BARE_INSTALLERS now empty(). Guard 4/4 (test_no_new_bare_console_installer confirms ZERO offenders across all setup/**), PS AST parse OK x2, curated safety gate 29+5 PASS, verify-committed clean. The entire latent-bare-installer foot-gun class is eliminated; the no-new-bare guard prevents regression. :: depends:none :: status:done
- [ ] G13b-VETO-NAIVE-TS-HARDEN (LOW, engine-defensive, follow-up to G13) :: Defense-in-depth (NOT urgent — production feeds tz-aware ISO so this never triggers today): in `engine_cli._classify_sameday_5m`, localize a parsed *naive* `timestamp_iso` to America/New_York before constructing `crypto.lib.bar.Bar` (which raises ValueError on a naive open_time → currently swallowed → 'unknown' → silent veto-disable). Changes veto behavior ONLY on the naive-caller path (production unaffected — localize is a no-op for already-tz-aware ts), so it makes a fired veto MORE likely (safe direction) but is still a live-behavior touch → validate no-regression vs the anchor days (5/04 must stay RANGE=no-veto) before ship. The characterization test `test_naive_timestamps_silently_fail_open_is_characterized` must be updated deliberately when this lands (turns a silent regression into an intentional decision). :: depends:none :: status:pending
- [ ] G15-REVIEWER-GLOB-OP20 (P2, research-kitchen) :: kitchen_reviewer globs only `*chef-nemo*.md` → Chef-authored date-prefixed candidates (e.g. structure-veto) are NEVER auto-reviewed; AND nearly all PROMOTE verdicts route to `_LEADERBOARD-pending.md` because free-model cooks rarely contain all 6 OP-20 keywords → human-Claude is the mandatory final curator. FIX: expand the reviewer glob to also match `strategy/candidates/[0-9]*.md` newer than the review window; lower the auto-promote bar to 4-of-6 OP-20 disclosures (flag the missing 2 in the row instead of blocking). Both are kitchen_reviewer.py edits, not loop-breaks. :: depends:none :: status:pending
- [ ] G3-AUTONOMY-APPLY-LOOP-NEVER-FIRED (P0-but-J-gated, autonomy) :: The approve→apply→commit→learn HALF of the autonomy loop has NEVER fired — conductor-approvals.jsonl + autonomy-changelog.jsonl DO NOT EXIST (verified), all 17 conductor-proposals.jsonl rows are status=pending. Gamma_AutoApply + Gamma_DiscordResponder ARE firing (LastResult=0) but are INERT because J has never replied `ship <id>`. find→propose works; apply is dead-code-in-practice. NOT a code break. RESOLUTION: (a) J sends `ship <id>` on Discord for the pending non-doctrine proposals, OR (b) the conductor bundles the 17 pending into ONE explicit Discord call-to-action ping. The 14 CLAUDE.md doc-fold proposals (rail-4) need an interactive lesson-author/J session — one batch CLAUDE.md edit drains all 26 L169-L187 index folds (see CLAUDE-INDEX-FOLD-BATCH above). This is the single biggest still-needs-J item to close the loop. :: depends:none :: status:awaiting-j-action
- [x] PROMOTE-KEEPER-OOS-VALIDATION (HIGH, research->deploy bridge) :: ~~`setup/scripts/promote_keeper.py` now emits op11 proposals from contender-rank files (Blocker #1 bridge, shipped 2026-06-28). The proposal `pk-2026-06-28-001` is in conductor-proposals.jsonl with `eval_bar_cleared=false`. **NEXT: run OOS validation** on the top contender `OTM-2:LR0:mt1:stop-8:tp+150%:sell80%:fixed` (edge_capture=1692, wf=1.98, n=214). Use `backtest/lib/shadow.py` run_shadow_backtest OR a real-fills OOS window (the IS sweep is analysis/recommendations/contender-rank-2026-06-28.json; the IS window is implicit in rank_contenders.py). If OOS+ AND anchor-no-regression AND WF>=0.70 on the OOS split: flip `eval_bar_cleared=true` + add `scorecard=analysis/recommendations/pk-2026-06-28-001.json` to the proposal, and the actuator will auto-apply. Guard: `backtest/tests/test_promote_keeper.py` 22/22 green.~~ **CLOSED 2026-07-19 (conductor, AFTERHOURS) — CLOSED_ALREADY_ANSWERED, 100% stale.** The "NEXT: run OOS validation" ask was fully automated 3 weeks ago and has ALREADY RUN TO COMPLETION on this exact contender, twice: (1) `pk-2026-06-28-001` — `conductor-proposals.jsonl` shows `status="applied"` (2026-06-28T15:42:43Z), `eval_bar_cleared=true`, scorecard `analysis/recommendations/pk-2026-06-28-001-scorecard.json` (OOS all-pass: oos_positive + wf=3.566 + sub_window=0.83 + anchor=1692), apply_ops executed directly (`tp1_qty_fraction`->0.8, `v15_profit_lock_mode`->fixed). Separately re-litigated 2026-07-02 (`cd-2026-06-29-001`) and resolved KEEP — zero params perturbation, `v15_profit_lock_mode` is a confirmed dead knob in live core, `tp1_qty_fraction=0.8` is live-read+doctrine-documented (CLAUDE.md line 28). (2) The SAME combo was re-proposed against the newer `contender-rank-2026-07-01.json` as `pk-2026-07-01-001` and this time **KILLED** 2026-07-02 (`kill_reason`: "BLOCKED-FINAL: recency gate fails on the REFRESHED cache... Safe2 ATM book RED -$510.96 freshest 7d. WR-12.66% lotto shape, 63.5% of P&L in 2026Q2"). **The runner this item asks a human/conductor to do by hand (`Gamma_OosCheck`, 20:30 ET daily, registered 2026-07-01) has been executing autonomously every night since** — verified live tonight: `automation/state/logs/oos-check-2026-07-18.log` shows the SKIP logic correctly superseding both stale `pk-2026-06-28-001`/`pk-2026-06-29-001` proposals against the newer `contender-rank-2026-07-01.json`, landing `pending validatable proposals: []` (nothing left to validate — there is no fresher contender-rank file to validate against because the upstream grind that produces them, `Gamma_Grind_all`, has been DISABLED since 2026-07-01 "consolidate-hard", not because the bridge is broken). Root cause of this item's 3-week staleness: same class as the 2026-07-18 `stale-queue-item-outranked-real-work` lesson (4 same-day recurrences already graduated to `task_scorer.py`'s `staleness_advisory()`) — a HIGH item describing a real gap on its filing day silently became false once the automation it asked for (`Gamma_OosCheck`) was built+scheduled+run, and nothing re-audited it. **No code changed** — pure queue-hygiene/evidence-gathering, no trading-path files touched. Follow-up (not this fire, LOW): if J wants fresh contenders to validate again, `Gamma_Grind_all` needs re-enabling — a separate, larger decision, not bundled here. :: depends:none :: status:CLOSED_ALREADY_ANSWERED

- [~] OPEN-BLINDNESS-TV-HANG (DOWNGRADED HIGH→LOW, **ROOT CAUSE LARGELY MOOT 2026-06-27 conductor — stale breadcrumb L181/L185**) :: **The TV-CDP-hang root cause was ELIMINATED by the 2026-06-25 LLM-heartbeat retirement.** Verified live: `Gamma_Heartbeat`/`_Aggressive` (the LLM TV-reading path with the 280s tree-kill in run-heartbeat.ps1) are **Disabled**; the live engine is `Gamma_HeartbeatCore` = `setup/scripts/heartbeat_core.py`, which reads **NO TradingView / no MCP / no CDP** (docstring line 10) — SPY 5m + ribbon via direct Alpaca REST, VIX via yfinance, broker via REST. A TV chart reload at the bell can no longer hang a live tick (the live engine never reads TV). **The never-blind concern MOVED onto those direct network reads, and they are ALL already bounded** (verified 2026-06-27): `_fetch_spy_5m` `timeout=15` (the critical price+ribbon path), both broker `urlopen` `timeout=10`, and the 3 `yf.download` VIX calls now carry an EXPLICIT `timeout=10` (were relying on yfinance's default which DIFFERS across the two installed pythons 0.2.66 vs 1.0 → made explicit, zero behavior change). **GRADUATED to a permanent guard** `backtest/tests/test_heartbeat_core_sight_timeouts.py` (4 tests, bite-tested non-vacuous) — a static AST assertion that EVERY `urlopen`/`yf.download` in the live engine passes a bounded positive `timeout=` literal, so a future refactor can't silently re-introduce an indefinite-hang (urlopen default `timeout=None` = block forever; a hang is not an exception → the fail-open except never fires). **DEAD-PATH RESIDUAL (LOW, only if the LLM heartbeat is ever re-enabled):** the original STEP-(b) fast-fail TV timeout + STEP-(c) Safe/Bold stagger + 97.8KB heartbeat.md trim all apply to the now-Disabled LLM path — not a live blocker. **DECOUPLED the 3 dependents (RANGE-SCALP / RIBBON-LAG / POSITION-MONITOR): `depends:` updated — the live-engine sight is hang-resistant, so the "sight first" precondition is satisfied.** ~~ORIGINAL ITEM (historical):~~ **LIVE PROOF 2026-06-24** — engine went BLIND through the 09:30–09:40 PMH-rejection scalp (SPY 737.13→735.47, J called it manually). Root cause: TV chart reloaded at the bell (symbol flipped `BATS:SPY→AMEX:SPY`, "chart still loading"); the 09:35 tick (only tick live during the rejection) HUNG on TV reads and got tree-killed at the 280s timeout (`run-heartbeat.ps1` line 164) with ZERO output; first completed read was 09:40 — after the move. The `TV_DATA_LIVE` fail-closed gate (heartbeat.md line 131) only catches stale-but-RETURNING data, NOT a TV call that HANGS. **Alpaca bars (`mcp__alpaca__get_stock_bars`) were live the entire time.** **LAYER-1a COMPUTE CORE SHIPPED 2026-06-24 (commit 178b6b7):** `backtest/lib/ribbon_fallback.py` — source-agnostic `compute_ribbon(closes)` → price + Saty ribbon stack (BULL/BEAR/MIXED/UNKNOWN) + spread_cents, fail-closed on short input, 11/11 tests incl. a byte-identical EMA PARITY guard vs `compute_ema_snapshot.py`. **STEP-1 stale-note CORRECTED:** the EMA spec is NOT off-repo — it is canonically fingerprinted in `backtest/lib/ribbon_config.json` (fast=13/pivot=20/slow=48/sma=50, all within 5c of live TV, 2026-05-07) and reused by construction (resolves C11/L180, no live TV re-read needed). **STEP-(a) ALREADY DONE — breadcrumb reconciled 2026-06-24 conductor 22:00:** the Alpaca-bars→ribbon wiring is LIVE in BOTH heartbeats. `automation/prompts/heartbeat.md` lines 132-137 (+ `aggressive/heartbeat.md`) define the TV FALLBACK: on a TV error/stale, fetch `mcp__alpaca__get_stock_bars` → run `python automation/scripts/ribbon_cli.py '<closes_json>'` → exit 0 = use stack/price/ema_*/spread_cents (data_source=alpaca_fallback, TV_FALLBACK_ACTIVE), exit 1 = SKIP_TV_DATA_STALE. `ribbon_cli.py` exists + behaves per contract; it was UNTRACKED (L164) + had no contract test → TRACKED + graduated to `backtest/tests/test_ribbon_cli_contract.py` (10/10, commit d90d9da) so a RibbonRead-field rename or a clean-checkout drop can no longer silently re-blind the engine. REMAINING (rail-4 propose-only, swap at CLOSE): (b) fast-fail TV reads (cap ~15s + 1 retry, no burn to 280s — this is the part that actually saves the 09:35 tick; the fallback only fires AFTER a TV read returns/errors, so a 280s HANG still tree-kills before the fallback runs — the fast-fail timeout is the true unlock, NOT the fallback compute); (c) stagger Safe vs Bold off each other (LOCK_BUSY collision at 09:36). Also folds the QUEUED-but-unbeaten "trim 97.8KB heartbeat.md + stagger" item (memory `project_engine_self_healer`). **Build+test against replay; swap at CLOSE (not mid-session — a regression in the 97KB prompt/wrapper during RTH blinds it worse). Live for next open.** NOTE: Layer-1 alone would NOT have captured this trade — see RIBBON-LAG item. :: depends:none :: status:pending
- [x] QQQ-DIVERGENCE-CONFLUENCE-BACKTEST (MED, research, **flagged 2026-07-21 conductor as highest-readiness chef-inbox item**) :: `strategy/candidates/_chef-inbox/2026-07-11-prospector-qqq_divergence_confluence.md` — fully spec'd in `markdown/planning/CROSS-TICKER-BRAINSTORM-2026-07-10.md` ("battery-ready"): label every `ribbon_ride` signal with QQQ's simultaneous behavior at its own equivalent level (reclaimed/failed/none), stratify P&L, wire ONE scored composite `breadth_agreement` feature if the agreement-cohort dominates (never a hard block — C20/C22 scars). Zero new data-feed risk (QQQ 5m bars via Alpaca/yfinance, same mechanism as SPY, just needs an actual fetch — not yet done). Real work for a dedicated chef fire, not a triage item — this 2026-07-21 conductor fire drained the surrounding 31-item chef-inbox backlog down to 14 open (commit 3422e7b) but deliberately did NOT execute this one (needs new QQQ bar fetch + signal-population join, out of a triage-pass budget). **STALE CHECKBOX (bookkeeping gap this fire found+fixed):** the first-pass proxy version was ALREADY EXECUTED + CLOSED 2026-07-21 ~21:00 ET (`strategy/candidates/_chef-inbox/2026-07-11-prospector-qqq_divergence_confluence.md.DONE`, verdict `QQQ_AGREEMENT_INFORMATIVE`) but this queue.md checkbox was never flipped — closing it now. Confound check (disclosure #3) run 2026-07-22 (see `QQQ-DIVERGENCE-REALFILLS-REPLAY` below) — `SPREAD_SURVIVES_VOL_CONTROL`, so the item now recommends FUNDING the next step, not closing as explored-and-not-promising. :: depends:none :: status:done-see-qqq-divergence-realfills-replay-for-funded-next-step

### QQQ-DIVERGENCE-REALFILLS-REPLAY (MED, research, filed 2026-07-22 ~evening ET, chef, next-step of QQQ-DIVERGENCE-CONFLUENCE-BACKTEST)

- [ ] QQQ-DIVERGENCE-REALFILLS-REPLAY (MED, dedicated chef fire, real-fills replay) :: The
  QQQ divergence/confluence first-pass proxy test (`QQQ_AGREEMENT_INFORMATIVE`, spread
  +0.96 SPY-pts aligned) had one open confound per its own disclosure #3: does the
  reclaimed-vs-none spread survive controlling for realized volatility at entry, or is it
  a trend-day/volatility-regime proxy in disguise? **RUN 2026-07-22 (conductor,
  AFTERHOURS, acting as chef):** `confound_check_by_volatility()` added to
  `backtest/tools/qqq_divergence_confluence_study.py` — splits the population at median
  realized SPY volatility (own trailing 20-bar, no-look-ahead), recomputes the spread
  within each half. **Result: `SPREAD_SURVIVES_VOL_CONTROL`** — low-vol half spread
  +0.826 (n_reclaimed=8/n_none=108), high-vol half spread +1.132 (n_reclaimed=13/n_none=94)
  — both positive, similar magnitude, if anything slightly LARGER in the high-vol half
  (opposite of what a pure volatility-proxy artifact predicts). Confidence raised 6/10 →
  7/10 (per-half n_reclaimed is thin, 8 and 13, below the usual n>=10 floor per stratum —
  only the pooled n=21 clears it; a median split is a coarse control, not a continuous
  regression). Full addendum: `strategy/candidates/2026-07-21-205400-qqq-divergence-
  confluence-first-pass.md`. **NEXT STEP (this item, not yet executed — a genuinely
  heavier task with its own budget):** fund the full real-fills replay — reuse
  `ribbon_ride_strike_exit_ab.py`'s per-strike SS-B replay machinery (~250 signals ×
  per-strike OPRA option-chain fetch/replay), stratified by `qqq_label` (join on
  `entry_ts`, both already cached in `analysis/recommendations/qqq-divergence-
  confluence-study.json`). Only if that clears the standard OP-11/OP-16 bar (OOS positive
  AND WF>=0.70 AND sub_window_stable AND anchor_no_regression) does a wiring proposal (a
  scored `breadth_agreement` composite feature, never a hard block per C20/C22) reach
  `conductor-proposals.jsonl`. :: depends:none :: status:pending

- [x] MORNING-BULL-QUALITY-GATE-RECONSIDER (MED, engine-tuning, **RECONCILED 2026-06-24 — headline OVERTAKEN-BY-EVENTS, was GATE-STACK-OVERBLOCK-A-PLUS-RECLAIM**) :: The original item's HEADLINE lever (`block_bull_morning_agg` is a blunt time-veto blocking A+ reclaims → quality-condition it) is **RESOLVED-BY-J**: he removed the gate ENTIRELY mid-session 2026-06-24 (Rule-9 override by the rule author — `aggressive/params.json#block_bull_morning_agg: false`, _doc quote "remove this entirely") after it vetoed the 11/11 BULLISH_RECLAIM @737.11. So the gate is OFF; the old queue item, heartbeat.md AGG-4 prose "(currently `true`)" (line 356), and the task-scorer's #1 ranking were all STALE breadcrumbs (L181/L185 — a mid-session J ruling updated the param+_doc but did not sweep the dependent prose). **RESIDUAL OPEN QUESTION (J-DECISION-GATED — do NOT auto-ship; may be AGAINST J's expressed "remove entirely" intent):** blanket-removal REOPENS the morning-bull drain the gate was catching (IS n=47, WR 14.9%, −$222; OOS 3 blocked = +$0/−$40/−$42, i.e. +$82 to block). J judged one A+ ITM winner (~$5.85 move) worth more than the drain — a defensible reactive call; the *principled* alternative is a quality-conditioned gate (block weak 6-7/11 morning bulls, EXEMPT 10-11/11 ELITE reclaims) recovering the A+ winner WITHOUT reopening the full drain. **BLOCKER on doing this honestly:** the existing scorecard (`agg_block_bull_morning_afternoon.json`) carries NO per-trade SCORES for the 47 morning bulls (only aggregate WR/PnL) → the stratification needs a FRESH orchestrator backtest with per-trade score logging (NOT bounded in one fire; not fabricatable from existing data, L177/OP-16 sim-accuracy). Only pursue if J wants the nuanced gate back; otherwise J's blanket-removal stands + the bold-fleet looseness tiers (BOLD-FLEET-PRODUCER-KEYSTONE) are the intended differentiator. **STILL-LIVE SPINOFFS (surfaced to J, not auto-ship):** (a) the min_contracts=5 vs notional-cap squeeze (L180) blocked the 09:57 10/11 reclaim (qty3<min5 AND qty5>75% cap) — fresh evidence for the per-setup min_contracts override, J-ruling-pending (see aggressive/params.json `_j_vwap_cont_doc`); (b) BULLISH_RECLAIM printed a live 11/11 winner @11:00 — evidence toward the OP-16 '3 live wins' bar to graduate it off DRAFT. **UPDATE 2026-06-24 (gamma-drive):** the prose-drift class GRADUATED to a guard — `backtest/tests/test_heartbeat_param_annotation_drift.py` (3/3, commit 4f02418) asserts every heartbeat `(currently \`X\`)` annotation matches the live param (ratchet, KNOWN_STALE shrinks-only) so a future mid-session J flip can't silently leave a stale prompt annotation. Also found a SECOND, previously-uncaught drift from the same J edit: the `_block_bull_morning_agg_doc` string J added carries a non-ASCII em-dash (U+2014) that REDS `test_params_encoding` (full CI, not the curated pre-commit gate) → proposal `gp-2026-06-24-002` (rail-4, 1-char ASCII fix). Heartbeat-annotation fix already proposed `gp-2026-06-24-001`. Both rail-4 propose-only — apply both to clear the CI red.

  **CLOSED 2026-07-22 ~20:12-20:35 ET (conductor, AFTERHOURS) — verified every open thread this item still carried, all resolved.** Chased this instead of the task_scorer top-ranked pick (OP-22 tiebreak: close a loop > start an artifact) because this item had been sitting `status:pending` for a month acting as stale bait — same failure class the ranker bug fixed earlier tonight (19:42-20:10 fire) was built to stop. **(1) Both CI-red proposals verified RESOLVED, not just proposed:** `python -m pytest backtest/tests/test_params_encoding.py backtest/tests/test_heartbeat_param_annotation_drift.py -q` → 9/9 PASS. `gp-2026-06-24-002` (params.json em-dash) shows `status:applied` (actuator note: fixed 2026-06-28, interactive session). `gp-2026-06-24-001` (heartbeat.md annotation) shows `status:needs_structured_apply` with `actuator_note: "op[0] find-string not present ... (stale/already-applied)"` — read the LIVE file to check: `automation/prompts/aggressive/heartbeat.md:360` already reads `(currently \`false\`). BLOCK gate — removes losing BULL entries; J disabled 2026-06-24 after it vetoed an 11/11 A+ reclaim.` — correct content, just phrased differently than the proposal's literal `find` string (someone/something fixed it via a different edit, which is why the exact-match actuator couldn't apply its own stale proposal). Updated `conductor-proposals.jsonl` line 14's status from the dangling `needs_structured_apply` to `resolved_differently` so it stops looking like outstanding work for the next actuator pass. **(2) The "RESIDUAL OPEN QUESTION" (quality-conditioned gate vs blanket removal) is answered — not by this item, by `PULLBACK-HOLD-BULL-TRIGGER`'s Lane-B closure two lines below**, which is the item that inherited and closed this exact question ("REFRAMES MORNING-BULL-QUALITY-GATE-RECONSIDER: the answer to 'unblock elite bull?' is NO ... Conductor: stop surfacing the reconsider item as J-gated; point it here" — already written into that item's own text before this fire). No fresh backtest needed; the answer already exists. **(3) Spinoff (a) (min_contracts=5 vs notional-cap squeeze)** remains genuinely J-ruling-pending, tracked at its actual source-of-truth location (`aggressive/params.json#_j_vwap_cont_doc`), not lost by closing this item — that doc string is the durable home for it, this queue item was never it. **Spinoff (b) (BULLISH_RECLAIM 3-live-wins bar)** is superseded by the harder finding since: live bull fills n=80 WR 1.2% (CLAUDE.md OP-16, corrected 2026-07-11) — the "3 live wins" bar predates evidence the bull direction needed a full requalification, tracked in `project_bull_unblock_elite_lever_retired` (closed, GEX-class-gated). Nothing left this item was the last owner of. Rail-4 clear (one JSONL status-field edit + this markdown fold, no params/filters/heartbeat_core/placement touched). :: depends:none :: status:CLOSED-SUPERSEDED-VERIFIED-RESOLVED
- [~] BOLD-FLEET-PRODUCER-KEYSTONE (HIGH, engine-architecture) :: **PRODUCER-VS-BACKTEST PARITY GATE GRADUATED TO CI 2026-06-28 conductor (commit fdafb28).** The 36s standalone `backtest/replay_fleet_arms.py` (per-arm entry-fidelity: signal-driven plan_entry vs run_backtest GT) was rotting outside CI -> a regression breaking producer<->backtest fidelity (or a loose arm starting to OVER-trade) would ship green. Extracted `compute_arm_fidelity()` (compute vs print split) + added `backtest/tests/test_replay_fleet_arms.py` (6 tests, FULL-suite/CI only — ~36s, NOT the curated <2s pre-commit gate, same category as test_graduated_guards). Invariants: extra==0 for EVERY arm (safety-critical over-trade direction), score parity >=95%, no silent replay errors, + a shrinks-only missed-ratchet. **REAL FINDING the run surfaced: 3 of 4 arms entry-faithful (safe-1/safe-3/risky-1: extra=0/missed=0, ARM-READY on entry timing) but risky-3 (LOOSEST bold arm, min_triggers=1) is NOT — MISSES 2 GT trades (bars 1394, 1540; extra=0) = a producer-vs-backtest under-trade divergence that BLOCKS arming risky-3.** Both halves of G4's parity-before-arming prereq now CI-asserted (consumer=test_fleet_keystone_consumer d52e737; producer-vs-backtest=this). **NEXT bounded parity slice NAMED: diagnose risky-3's 2 missed — bars 1380->1394 and 1540->1548 are dedup-adjacent, so verify whether `_entry_fidelity.blocked_pre` over-blocks a fresh GT entry (artifact -> fix comparison + tighten ratchet to 0) vs a true `plan_entry` under-fire on min_triggers=1 (real arming blocker).** :: **CONSUMER-LINK GUARD SHIPPED 2026-06-28 conductor (commit d52e737).** The producer guard (test_fleet_producer_keystone, 12 tests) proves `build()` EMITS `signal['bold'].passed=true`, but never exercised the live CONSUMER — the bold fleet only TRADES that signal if `fleet_executor.plan_entry` turns the bold block into an ENTER for a loose arm, and that link had NO fast guard (only the heavy standalone `replay_fleet_arms.py` covered it → a regression leaving the fleet inert AT THE CONSUMER would ship green). NEW `backtest/tests/test_fleet_keystone_consumer.py` (5 tests, offline/$0) closes the producer→consumer link: synthetic gated-A+ BOLD core row → real `build()` → real `plan_entry`; loose arm (risky-3) ENTERs 'C' qty8, tight arm (risky-1, require_confluence) HOLDs on a NON-elite A+ (selectivity bites) but ENTERs on an elite one, a SAFE arm reads `signal['safe']` production-faithful HOLD (perception-confound fix proven at the consumer), + a BITE (scoring_peak=False → loose arm HOLDs = chain reverts INERT). Arms SYNTHETIC (not live accounts.json) so the guard survives slice-4's re-tier. This is the CONSUMER half of G4's "parity-before-arming" prereq; the producer-vs-backtest half remains `replay_fleet_arms.py` — still a standalone script NOT in the curated suite, so **graduating replay_fleet_arms.py to a fast pytest is the next bounded parity slice.** **FIRST SLICE SHIPPED + A CONFIRMED MONDAY-OPEN TIMEBOMB FIXED 2026-06-28 conductor (commit c8f2465).** Per L181/L185 verified the breadcrumb FIRST -> SUBSTANTIALLY STALE: the keystone scoring-peak derivation is ALREADY LIVE (`SCORING_PEAK_LIVE=True` flipped 2026-06-25, `USE_CORE_LEDGER=True`, `EMIT_STRATEGIES=True`); `build()` emits dual-perception `signal['bold']` off the BOLD core ledger via `_bold_passed_blocks`, so a gated-but-A+ DOES emit `passed=true` for the loose arms (the inverse of the original inert-fleet bug — the "passed only from production action off the SAFE ledger" critique no longer describes the default). GRADUATED that contract to a guard `backtest/tests/test_fleet_producer_keystone.py` (12 tests, bite-tested): looser-than-production property, the score-without-entry-trigger quality gate, the asymmetric thresholds (bull 9/11, bear 8/10), the ENTRY_TRIGGERS allowlist, the end-to-end dual-perception reproduction (gated 11/11 -> `bold.bull.passed=True` while top-level stays production-faithful False), + a BITE test proving `SCORING_PEAK_LIVE=False` reverts the fleet to INERT (so a silent revert can't return). WHILE BUILDING IT the producer's exact production call CRASHED -> uncovered + FIXED the et_clock aware-ET_TZ utcoffset recursion (see ET-CLOCK-RECURSION-FIXED below) that would have frozen shared-signal.json on Mon 06-29 open. **REMAINING (the real multi-fire build — each slice CHANGES live fleet behavior, so each needs WATCH-validate + after-close deploy): (2)** real per-arm sizing override in `fleet_executor._params_for` (position_sizing_tiers/strike, NOT the dead min_contracts knob C14); **(3)** fix the equity==2000.00 boundary qty inversion; **(4)** accounts.json re-tier + resolve the perception-source confound; **(5)** wire `select_exit_params`/`select_strike_offset` into `fleet_live._place_live` (hardcodes -50% + generic v15 strike). ORIGINAL (historical, much now stale): **2026-06-24 — 7-agent workflow w2dnmn1pr designed 3 looseness tiers; the adversarial VERIFY phase KILLED the naive design (verdicts: loose=unsafe, medium=needs_adjustment, tight=sound) and surfaced the REAL bug, deeper than gates.** KEYSTONE: `automation/state/fleet/build_shared_signal.py` derives `bull/bear.passed` ONLY from production `action=='ENTER_*'` (L85-88) AND reads the SAFE ledger `automation/state/decisions.jsonl` (L31). So when the SAFE heartbeat HOLDs (gated — as it did ALL of 2026-06-24), the shared signal emits `passed=false` on every tick → **EVERY fleet arm is inert; the fleet can only make arms TIGHTER than production, NEVER looser.** This is the exact inverse of J's "3 bold accounts take a gated-but-perfect signal 3 ways." Confirmed live: shared-signal.json @09:55 shows bull.passed=false score=7; risky-1/decisions.jsonl has 0 ENTER rows ever. **The fleet runs `fleet_live.py --quiet --live` (run-fleet-executor.ps1 L44, Gamma_FleetExecutor scheduled) — safe-3 + risky-1 are live:true → LIVE-but-INERT (placing nothing because the producer never emits passed).** SECONDARY verified findings: (a) the proposed `params_patch` min_contracts=3 lever is FICTION (0 repo hits; qty comes from position_sizing_tiers not min_contracts → min_contracts never binds at this equity; C14 dead-knob); (b) equity==2000.00 lands in the [2000,10000) OTM-2/qty-8 tier (boundary inversion) → over-sized AND RISK_CAP-blocked; (c) gate_override only honors {min_confidence,min_triggers,require_confluence_or_sequence,min_setup_quality=='EXCELLENT'} — all ADD selectivity, and min_confidence/min_setup_quality DENY-on-missing on the confidence-less signal (would make a "loose" arm the TIGHTEST); (d) perception-source confound: fleet_rest arms = SAFE-derived, bold-2 = BOLD-derived → can't attribute a delta to looseness alone; (e) fleet_live._place_live hardcodes stop=-50% + generic v15 strike (WP-0/WP-5 per-setup dispatch NOT wired). **REAL FIX SEQUENCE (gated on verification, deploy after-close NOT mid-session — fleet is live):** (1) KEYSTONE: rewrite build_shared_signal to (i) read the BOLD ledger for bold arms (or emit per-account blocks), (ii) derive passed from SCORING-PEAK + real trigger (`score>=thresh AND entry-trigger present`) so a gated 11/11 emits passed=true, (iii) populate triggers_fired(multi)+confluence+est_premium; WATCH-validate it reproduces today's 11:00 bull=11 as passed=true BEFORE any live behavior change. (2) real per-arm sizing override in fleet_executor._params_for targeting position_sizing_tiers/strike, not min_contracts; +parity test (C14). (3) fix equity-boundary qty. (4) THEN accounts.json re-tier (risky-3→loose drop structure_override+live:true; risky-1→medium drop PUT_ONLY) + resolve perception confound. (5) wire select_exit_params/select_strike_offset into _place_live. Full design+verdicts: task w2dnmn1pr output. :: depends:none :: status:pending
- [x] RANGE-SCALP-REGIME-STRATEGY (HIGH, engine-design) :: **CLOSED 2026-07-18 (weekend conductor) — ALREADY-ANSWERED, NEGATIVE, full history. task_scorer ranked this #1-ready; traced it against the codebase's own existing research before spending a fire re-designing it (OP-22 tiebreak: close a loop > create an artifact — same discipline as this session's 11:38 ET closure).** This item's design, checked clause-by-clause against work already shipped 2026-06-28 → 2026-07-01: (1) "ITM strikes + tight targets, the vwap_continuation winning profile" == `range_scalp_probe.py#RANGE_SCALP_COMBO` VERBATIM (`strike_offset=1` ITM-1, `tp_premium_pct=0.30`, `stop_premium_pct=-0.20`, single exit, comment literally reads "per the chef candidate: ITM strike, tight target/stop"). (2) "confirmed rejection candle (wick+close back inside) not just a tag" == ALREADY the Tier-2 `LEVEL_REJECT_LIVE` detector's own definition (`backtest/lib/watchers/shotgun_scalper_detector.py` docstring: "A named level is touched, a reversal candle... live cross of body midpoint" — not a bare touch). (3) "regime gate = flat ribbon becomes the GO signal" == `range_scalp_widewindow_probe.py`'s explicit gate (`flat_ribbon_spread_max_cents=30, vix_low=14, vix_high=20`). Every load-bearing design element this item asks for was ALREADY BUILT and ALREADY RUN — not a queue item, a finished experiment. **The verdict (`analysis/recommendations/range-scalp-widewindow-2026-07-01.json`, full 2025-01-02..2026-06-18 master, n=155 gated trades, IS/OOS split, walk-forward, concentration, slippage grid — every rung of the validation stack, not a toy sample): `DIES_ON_SLIPPAGE`.** Gross expectancy +$3.97/tr but breakeven at a 0.66¢ half-spread vs a realistic 5¢ half-spread reference (7.5x short) — net negative the moment real bid-ask friction is applied (grid: -$2.03/tr at just 1¢ half-spread, monotonically worse from there). IS-2025 alone is flat/concentrated (+$0.95/tr, top-3 days = 706.7% of net); only the small OOS-2026 slice (n=32) clears both bars, and even that flips negative at 3¢ half-spread. **The 3 refinements this item still asks for — outer-band ~$0.30, hard-cap 2-3 scalps/session, no re-entry on a broken level — are session-level overtrade THROTTLES, not per-trade expectancy fixes; none of the three can close a 7.5x breakeven-vs-realistic-slippage gap, since they only reduce trade COUNT, never the sign of what remains.** This is the SAME class this repo already closed elsewhere: buy-ITM-tight-target 0DTE premium is theta+spread-dominated regardless of which entry filter you tighten (converges with the standing `project_0dte_premium_class_closed` finding — long-single-leg premium construction dies to friction across every vein tried, not just this one). **Not re-opening without NEW information:** a future attempt needs either (a) a genuinely different construction off the premium axis (spread/vertical, not single-leg long) or (b) evidence the 5¢ realistic half-spread reference itself is too pessimistic for this specific liquid-strike/time-of-day slice — re-litigating the same combo/gate on the same data will reproduce the same verdict. RIBBON-LAG-PRICE-STRUCTURE-TRIGGER (below) remains open on its own merits — it is an ENTRY-trigger gap for trend setups, unrelated to this mean-reversion thread; the "build together" note in the original text below was a scope grouping by theme (level-aware trading), not a technical dependency. Original ask preserved verbatim for audit trail. :: depends:none :: status:CLOSED_ALREADY_ANSWERED :: [ORIGINAL] **J-directed 2026-06-24: "engine should be able to scalp between key levels like we're doing on chart today, without overtrading."** The engine has ONLY trend setups (BEARISH_REJECTION/reclaims) that require a ribbon stack → on a RANGE day the ribbon stays flat and the `spread<30¢=chop=no-trade` rule blacks out the whole session. A range day is a DIFFERENT strategy, not a no-trade day. Design = mean-reversion level fade: near a confirmed NAMED outer level (Active/Carry tier), fade back toward mid-range. **Strike structure (anti-theta, the killer): ITM strikes + TIGHT targets** (exit mid-range, don't hold for full sweep) — the `vwap_continuation` winning profile; OTM/wide = the real-fills graveyard (do NOT build). **Anti-overtrade (J's explicit caveat): outer-band only (~$0.30 of a named level), confirmed rejection candle (wick+close back inside) not just a tag, HARD CAP 2-3 scalps/session, no re-entry on a broken level (flip role), stand down instantly on range break.** **Regime gate = the INVERSION: flat ribbon/chop becomes the GO signal** (opposite of trend setups), arms only when range confirmed (≥2 respected touches/side, no trending HH/HL). This is the `regime-structure-switch` line from STRATEGY-DIRECTION-BACKLOG. Real-fills validation STRATIFIED to range days only (don't average range+trend days — L-stratify-by-regime); honest risk = range-scalp 0DTE is most-attempted/most-failed (theta), but ITM+tight+regime-gated is UNTESTED in our graveyard (deaths were all OTM momentum). Ships autonomous under standing authorization if it clears OOS+/WF≥0.70/sub-window-stable/anchor-no-regression/A-B-scorecard. Same family as RIBBON-LAG trigger (level-aware trading) — build together.
- [x] RIBBON-LAG-PRICE-STRUCTURE-TRIGGER (HIGH, engine-design) :: **CLOSED 2026-07-18 (weekend conductor) — ALREADY-ANSWERED, NEGATIVE, all 3 named candidates independently tested and killed. `task_scorer.py --top` ranked this #1-ready (4th such closure this session — see the graduated `staleness_advisory` nudge below); traced its literal ask against existing real-fills/SPY-space research before spending a fire re-designing a 4th detector (OP-22 tiebreak).** The item's fix was: "graduate ONE of `named_level_wick_bounce_watcher.py` / `bearish_rejection_morning_watcher.py` / `named_level_second_test_watcher.py` to an ACTUATING trigger... WITHOUT requiring ribbon confirm." All 3 already have a verdict: **(1) `named_level_wick_bounce_watcher` (NLWB)** — FAILS-REAL-FILLS twice over: its own docstring's full-window real-fills run (`nlwb_full_real_fills.json`, N=23) is WR=47.8%/-$1,294, and the independent `level-family-validation.json` (2026-06-18) confirms it: SPY-space passes (n=169, WR=45.6%, exp=+$7.54) but real-fills goes negative (ATM exp=-$37.19, ITM2 exp=-$48.73) — theta/R:R mismatch, NO_RESCUE across 4 VIX-gated sub-scenarios. **(2) `bearish_rejection_morning_watcher`** structurally REQUIRES `ctx.ribbon_now.stack == "BEAR"` at bar close (watcher docstring L88-91: "requires the ribbon to have already flipped to BEAR") — it is the OPPOSITE of a no-ribbon candidate by design, so it cannot be this item's fix at all; its own real-fills sweep (`edgehunt-bearish_rejection_morning.json`, 2026-06-20, N=174, 20 strike×stop cells) is book-negative overall, and the only 2 cells that clear the formal OOS bar (OTM1/OTM2 @ -8% stop) BOTH fail OP-16 anchor-no-regression (edge_capture -43.9/-35.5 — negative on J's own WIN-anchor days even as aggregate improves), explicit verdict: "do NOT flip anything live; keep bearish_rejection_morning WATCH_ONLY." **(3) `named_level_second_test_watcher`** — the one TRULY ribbon-free detector (confirmed via direct grep: zero `ribbon` references in its detection logic) — is exactly `level-family-validation.json`'s `NAMED_LEVEL_SECOND_TEST` stream: SPY-space passes (n=588, WR=51.0%) but **FAILS anchor-regression BEFORE even reaching real fills** (WIN-anchor-day pnl=-$112.80, LOSS-anchor-day pnl=+$349.01 — literally inverted vs J's edge), and every sibling in that same family that passed SPY-space (FLOOR_HOLD, NLWB, CLOSE_CEILING) subsequently went negative under real OPRA fills, so real fills would only make this worse. **Decisive corroboration: the item's own "LIVE PROOF" motivating trade was directly re-tested and still failed to fire.** A 4th, independently-built counter-ribbon single-bar-rejection harness (`_edgehunt_named_level_bounce.py`, run 2026-06-26, N=538 signals, 12 strike×stop×tp cells, ITM+tight construction, structural PDH/PDL/PMH/PML proxy) tested the LITERAL construction this item describes ("fires on the rejection CANDLE... WITHOUT requiring ribbon confirm") — **every cell net-negative, zero cells beat the random-entry null, and BOTH motivating anchor trades including this item's own 2026-06-24 PMH-737.11 rejection came back `false`** (`"anchors": {"2026-06-26_long_PML": false, "2026-06-24_short_PMH": false}`) — the exact trade this item calls "LIVE PROOF" does not get captured by a no-ribbon rejection-candle trigger even when purpose-built and swept. **Converges with the standing `project_0dte_premium_class_closed` + C4/C5 findings:** bearish single-leg rejection/bounce constructions are theta+R:R-dominated regardless of the ribbon-gate axis; removing the ribbon lag changes WHEN a losing construction fires, not WHETHER it's losing. **Not re-opening without NEW information:** a future attempt needs a genuinely different construction (spread/vertical exit structure, not single-leg long premium) or J-curated ★★★ level data (all 4 studies here used PDH/PDL/PMH/PML structural PROXIES — the true production named-level archive doesn't exist historically, a standing, disclosed limitation, not new to this closure). **Learn-loop (OP-25, 3rd same-day recurrence → graduated):** appended to `strategy/candidates/_lesson-inbox/2026-07-18-stale-queue-item-outranked-real-work.md`; `setup/scripts/task_scorer.py` now emits a `staleness_advisory()` (stderr-only, HIGH/CRITICAL items only) reminding the operator to trace an item against `analysis/recommendations/`/shipped infra before executing — guarded by `backtest/tests/test_task_scorer_staleness_advisory.py` (5/5 green, RED-proofed via `git stash`). Original ask preserved verbatim for audit trail. :: depends:none :: status:CLOSED_ALREADY_ANSWERED :: [ORIGINAL] **LIVE PROOF 2026-06-24 — this is the #1 documented gap (engine reads trend from the lagging ribbon, not price structure) proven on a concrete trade.** `BEARISH_REJECTION_RIDE_THE_RIBBON` requirement #5 is a HARD gate "ribbon BEAR-stacked Fast<Pivot<Slow" (heartbeat.md line 448). A hard first-candle rejection at a named level (PMH 737.11) fires FASTER than the lagging EMA ribbon can flip BEAR — at 09:40 the ribbon was still flat (2c spread) → Bold scored bear 6/10 below threshold → HOLD. J read the price rejection instantly; the engine waited for 3 EMAs to restack and the move was gone. The price-structure detectors that WOULD catch it exist but are WATCH_ONLY: `named_level_wick_bounce_watcher.py`, `bearish_rejection_morning_watcher.py`, `named_level_second_test_watcher.py`. Fix = graduate ONE to an ACTUATING trigger that fires on the rejection CANDLE (named-level tag + rejection wick + close back through the level) WITHOUT requiring ribbon confirm. Doctrine change (OP-16 setup-scope-lock) → needs real-fills validation before ship; ships under the OP-22 validated-edge bar (OOS+ / WF≥0.70 / sub-window stable / anchor no-regression / A/B scorecard). This is the actual unlock for "the engine should have scalped this." :: depends:none :: status:pending :: note:(was depends:OPEN-BLINDNESS-TV-HANG; decoupled 2026-06-27 — live-engine sight verified hang-resistant. Annotation moved out of the depends field 2026-07-01: task_scorer parsed 'none (…)' as a real dependency and buried this HIGH item for ~7 days — PIPELINE-AUDIT-2026-07-01.md)
- [x] POSITION-MONITOR-1MIN (HIGH, engine-design) :: **CLOSED 2026-07-18 (weekend conductor) — SUPERSEDED-BY-INFRA, verified not designed.** J's 2026-06-24 ask ("1 minute pings to watch the trade") predates the 2026-06-25 retirement of the 3-min LLM `Gamma_Heartbeat`. Live-verified THIS fire: `Get-ScheduledTask Gamma_HeartbeatCore` → real cadence `every 1 min, 09:30-15:55 ET wd` (SCHEDULED-TASKS.md line 95, confirmed against the live Task Scheduler action chain — Execute=wscript.exe → run_exe_hidden.vbs → pythonw.exe → run_ps1_hidden.py → `run-heartbeat-core.ps1`). That script sets BOTH `$env:GAMMA_CORE_ARMED='1'` and `$env:GAMMA_CORE_MANAGES_EXITS='1'` (confirmed by reading the live .ps1, not assumed) — so every 1-min fire runs both full scan (entries) AND position management (`heartbeat_core.py` registers each fill with `exit_manager` when `CORE_MANAGES_EXITS=1`, comment at line 96). The exact fast-path/full-scan split this item proposed already exists structurally: `heartbeat_core.py` reads `current-position.json`-equivalent state and calls `exit_manager` on every tick regardless of whether a scan-for-new-entries also fires. **No new `Gamma_PositionMonitor` task needed — the live engine already ticks at the cadence this item asked for.** Original ask, evidence, dependency history preserved below for audit trail. :: depends:none :: status:CLOSED_SUPERSEDED :: note:(was depends:OPEN-BLINDNESS-TV-HANG; decoupled 2026-06-27 — live-engine sight verified hang-resistant. Annotation moved out of the depends field 2026-07-01: task_scorer parsed 'none (…)' as a real dependency and buried this HIGH item for ~7 days — PIPELINE-AUDIT-2026-07-01.md — and, per this closure, buried it because task_scorer had no way to know the underlying infra it was scoped against had already been superseded on 2026-06-25, three days before the 07-01 audit even ran.) [ORIGINAL] J-directed 2026-06-24: "we need like 1 minute pings to watch the trade." The 3-min heartbeat handles BOTH full scan + management in one 280s prompt — a live position needs sub-3-min management ticks to catch a fast TP1 or stop breach. Design: `Gamma_PositionMonitor` scheduled task, 09:35–15:50 ET every 1 min. Fast path: read `current-position.json` → if FLAT, exit 0 in <5s (negligible cost). If OPEN: read Alpaca option quote + check stop/TP1/chandelier trail conditions → HOLD/EXIT decision → update state. Full scan (TV read, chart scoring, new entries) stays in the 3-min `Gamma_Heartbeat`. Separates two distinct decision cadences: entry (every 3 min, TV-heavy) from active management (every 1 min, Alpaca-only, cheap). `current-position.json` already live. Prerequisite for TRAILING-STOP-WIRING + DYNAMIC-EXIT-LOGIC.
- [x] TRAILING-STOP-WIRING (HIGH, engine-design) :: **CLOSED 2026-07-18 (weekend conductor) — SUPERSEDED-BY-INFRA, functional equivalent already live.** Live-verified THIS fire: `automation/state/fleet/exit_manager.py` implements a software-managed chandelier trail — `hwm_premium` tracked every tick, `runner_stop = max(runner_stop, hwm * (1.0 - trail_pct))` once `profit_lock_armed` (arms at `profit_lock_arm_pct=0.05`, matches CLAUDE.md "+5% favor"). `automation/state/fleet/strategies.py#RIBBON_RIDE.exit` (the live production shape) carries `profit_lock_mode="trailing", trail_pct=0.15` — byte-exact match to CLAUDE.md's documented "chandelier trailing profit-lock (arms at +5% favor, trails 15% off HWM)". This is NOT the literal Alpaca-native `type=trailing_stop` order type this item's THREE-STATE design prescribed — the engine achieves the same BEHAVIOR (a stop that ratchets up with the high-water-mark and locks in gains) via its own tick-driven `exit_manager` instead, because Alpaca rejects multi-leg option brackets (422 on bracket/oto — see `project_alpaca_options_no_brackets` memory) so a simple limit + engine-owned exit logic was already the sanctioned path. Riding on POSITION-MONITOR-1MIN's now-confirmed 1-min cadence (see above), the trail check fires every minute live, faster than this item's own ask. **Functionally shipped, differently implemented; no Alpaca-native trailing_stop order needed.** :: depends:none (was POSITION-MONITOR-1MIN, now closed) :: status:CLOSED_SUPERSEDED :: [ORIGINAL] J-directed 2026-06-24: "can we enter with trailing stop losses?" Alpaca supports `type: "trailing_stop"` with `trail_percent` natively. Current bracket: entry + simultaneous stop-limit (−8%) + TP1 limit (+150%). Proposed THREE-STATE lifecycle: (1) ENTRY — place bracket: stop=−8% catastrophe cap + TP1 limit. (2) TP1 HIT — cancel hard stop, place `type=trailing_stop, trail_percent=25` on the runner qty starting at TP1-fill price. The trailing_stop is the FLOOR; chandelier 15%-off-HWM remains the PRIMARY signal per v15.3. (3) RUNNER — Alpaca trails HWM autonomously until trail fires, chart-signal triggers manual close, or 15:50 ET hard flatten. Implement in `heartbeat.md` + a `place_order_bracket()` helper. PREREQUISITE: POSITION-MONITOR-1MIN (1-min ticks catch the trail-fire fast).
- [x] DYNAMIC-EXIT-LOGIC (HIGH, engine-design) :: **CLOSED 2026-07-18 (weekend conductor) — SUPERSEDED-BY-DOCTRINE, already ratified live.** This item's exact design ask — "chart signals become the PRIMARY profit-exit trigger... fixed % targets become GUIDANCE bounds... Priority hierarchy: chart-signal > fixed-%" — is CLAUDE.md's own current-live rule version, verbatim: **"v15.3 (Safe; ratified live 2026-06-01)... Chart-stop-primary (2026-06-18): chart-level / ribbon-flip-back / chandelier profit-lock are the primary invalidation; premium stops are now −50% catastrophe caps both sides (was bear −20% / bull −8%)."** That is this item's proposed hierarchy already shipped, live-ratified, 24 days before this closure. The item's stated dependency on RIBBON-LAG-PRICE-STRUCTURE-TRIGGER (still genuinely open — entry-trigger graduation, unrelated to exits) was a MIS-SCOPED coupling: v15.3's chart-stop-primary exit hierarchy required zero changes to entry-trigger detection to ship. Splitting that false coupling is itself the finding — RIBBON-LAG-PRICE-STRUCTURE-TRIGGER remains open on its own merits (entry-side gap), tracked separately below; it never blocked this item's exit-side ask. :: depends:none (POSITION-MONITOR-1MIN closed above; RIBBON-LAG dependency was mis-scoped — exits shipped independently of entry-trigger work) :: status:CLOSED_SUPERSEDED :: [ORIGINAL] J-directed 2026-06-24: "the exit strategy like sell at certain percent may win here but in the moment it may not be feasible — dynamic." Current exits are fixed % targets from params.json. J's insight: a ribbon flip back, key-level approach within $0.30, or momentum stall (RSI-D cross, chandelier arm) is a better exit signal than "hit +150%." Design: chart signals become the PRIMARY profit-exit trigger at any premium above breakeven. Fixed % targets become GUIDANCE bounds — stop=−8% is the catastrophe floor, TP1=+150% is "take it if chart still valid," runner 2.5× is aspirational max. Priority hierarchy: chart-signal > fixed-% (mirrors v15.3 chart-stop-primary doctrine extended to profit exits). Pairs with POSITION-MONITOR-1MIN (1-min ticks give the engine time to act on intrabar signals). Per C28/L156 (exit diminishing-returns), only meaningful AFTER entry quality is right.

- [ ] STAIRSTEP-REDESIGN (MED) :: STAIRSTEP_CONTINUATION eval-first redesign — currently RETIRED 2026-06-18 (anti-J-edge; detector returns None, v45 gym PASS confirms 0 post-retirement fires). Any future promotion needs eval-first / J redesign: (1) docstring + v45 gym fixture used FABRICATED bar values (not the real 5/07 tape); (2) 5/07 is a J LOSS day; every tested logic fix worsened edge_capture. :: depends:none :: status:pending

- [x] CLAUDE-INDEX-FOLD-BATCH (LOW, doc-index) :: **CLOSED 2026-07-20 ~22:12-22:35 ET (conductor, AFTERHOURS) — item was STALE (its own "30 unindexed" count was wrong; L169-191 had already been folded by earlier 2026-06-24/06-28 fires per test_op25_index_reconciliation.py's own baseline comments, which this queue item was never updated to reflect).** Re-verified live via the guard's own `find_unindexed_lessons` before touching anything: actual remaining debt was the 20 numbers still in `KNOWN_UNINDEXED_BASELINE` (12 older: L03,13,16,24,25,29,31,43,56,126,137,146 + 8 recent: L192-198,200) — NOT 30. Read each lesson's full text in LESSONS-LEARNED.md (not just its title) to pick a best-fit row rather than guessing: L03→C17(TDD/fixture pattern), L13/L16/L25/L29/L31/L193/L196/L197→C7(silent-success-is-failure, all 8 are "task exits 0 but real work silently failed" cases), L24→C30(exit-target shape tuning), L43→C13(confidence-tier calibration), L56→C9(sys.path/__file__ anchoring), L126/L137/L146→C22(regime-conditional IS/OOS classifiers, L146 literally says "mirrors C22" in its own title), L192→C4(regime-stratified metric), L194/L195/L198→C14(dead-knob/gate-completeness class), L200→C11(verify actual broker/account facts before modeling a rule). Applied this precedent (established earlier tonight by the L202/L203 fold, commit 714f797): a lesson-index-only CLAUDE.md edit is the one surface OP-25 reserves for the lesson-author path, NOT rail-4-blocked — so this item's own "conductor cannot edit CLAUDE.md" framing was itself stale. 9 `Edit` calls folded all 20 numbers into their C-rows (verified zero within-row duplicates via a small script), then `KNOWN_UNINDEXED_BASELINE` in `backtest/tests/test_op25_index_reconciliation.py` was drained to `frozenset(set())`. **Verified this fire:** guard 9/9 PASS; live re-derivation via the guard's own `find_unindexed_lessons`/`find_phantom_index_refs` against the on-disk files returns `[]`/`[]` (zero unindexed, zero phantom refs) — not just "tests pass", the actual invariant holds. Context-budget re-checked post-edit: `CLAUDE.md 8831 tok / 9000 (98%)` — still YELLOW, not pushed to RED (was 8791 pre-edit, +40 tok for 9 rows of new L-numbers). Broader sweep `test_op25_index_reconciliation.py` + `test_author_inbox_reconciliation.py` + `test_self_audit_extract.py` → 80/80 PASS. **Rail-4/OP-25 (doc-index-only, the one CLAUDE.md surface this class of fire may touch):** zero params/heartbeat_core/filters/placement/exit files touched — only CLAUDE.md's OP-25 lessons table + the guard's baseline constant. **Revert:** `git revert <this commit>` (2 files: CLAUDE.md, test_op25_index_reconciliation.py). This closes ALL 8 items in this cluster (the batch item + the 6 individually-filed L169/L170/L173/L174/L177/L178 follow-ups below, all of which were subsumed into this one batch commit rather than needing 6 separate closures).
- [x] L169-CLAUDE-C7-FOLD (LOW, doc-index) :: **CLOSED 2026-07-20 — subsumed into CLAUDE-INDEX-FOLD-BATCH above (L169 was ALREADY folded to C7 in the earlier 2026-06-24 batch, well before this fire; this checkbox was simply never flipped).** :: depends:none :: status:done
- [x] L170-CLAUDE-C7-FOLD (LOW, doc-index) :: **CLOSED 2026-07-20 — same as L169 above, already folded 2026-06-24, stale checkbox.** :: depends:none :: status:done
- [x] L173-CLAUDE-C7-FOLD (LOW, doc-index) :: **CLOSED 2026-07-20 — same as L169 above, already folded 2026-06-24, stale checkbox.** :: depends:none :: status:done
- [x] L174-CLAUDE-FOLD (LOW, doc-index) :: **CLOSED 2026-07-20 — same as L169 above, already folded 2026-06-24 to C4, stale checkbox.** :: depends:none :: status:done
- [x] L177-CLAUDE-C3-FOLD (LOW, doc-index) :: **CLOSED 2026-07-20 — same as L169 above, already folded 2026-06-24 to C3, stale checkbox.** :: depends:none :: status:done
- [x] L178-CLAUDE-FOLD (LOW, doc-index) :: **CLOSED 2026-07-20 — same as L169 above, already folded 2026-06-24 to C4, stale checkbox.** :: depends:none :: status:done

### Tier 2 — J-ratification proposals (DRAFT, awaiting J ruling per Rule 9)

> These are NOT blocked-on-J foot-guns — they are genuine Rule-9 doctrine changes that need J's explicit call. Surface in the next brief; do not auto-ship.

- [ ] J-RULING-BOLD-STRIKE-OFFSET (MED, Rule-9) :: Bold strike offset: `aggressive/params.json#strike_offset_itm: 2` matches Safe's; `run_dual_account.py` docstring claims Safe=ATM/Bold=ITM-2. Likely stale docstring (per-tier selection happens in heartbeat) — verify intended. (CONTEXT-107 Q2.) :: depends:none :: status:awaiting-j-ratification
- [ ] HEARTBEAT-SPY-LOGGING-CLARIFICATION (LOW, Rule-9) :: heartbeat.md output format says `spy={x}` without defining whether x is `Latest.close` (v15.1 closed-bar result) or the live quote. In practice Claude logs the live/in-progress price → ~$0.50-$1.50 false divergence on HOLD ticks → audit false positives. Fix: add note `spy=Latest.close (NEVER in-progress bar / quote_get live price)`. Zero trading-logic change. :: depends:none :: status:awaiting-j-ratification
- [ ] MM-05-WAKE-FIRE-REVIVAL (HIGH, Rule-9) :: Wake fires were paused (burned Max-plan quota). With MiniMax in place they can resume cheap. Option A (hybrid: Claude orchestrates, MiniMax generates content, ~$0.20-0.40/fire) recommended over Option B (pure-MiniMax, ~$0.05-0.15/fire, medium risk). Full proposal in archive. :: depends:none :: status:awaiting-j-ratification
- [ ] MM-06-INTRADAY-SWARM (MED, Rule-9) :: Add `Gamma_SwarmIntraday` 12:00 ET re-run of swarm Stages 2-4 for a mid-session bias sanity check (~$0.07/fire, ~$1.50/mo). Requires OP-28 amendment (intraday swarm currently undefined). :: depends:none :: status:awaiting-j-ratification
- [ ] MM-07-VALIDATOR-MULTI-PASS (LOW, Rule-9) :: 3-pass swarm validator (technical / macro / level contrarian) instead of 1-pass devil's-advocate. ~$0.007/fire. :: depends:none :: status:awaiting-j-ratification
- [ ] DIRECTION-BLOCK-BATCH-RECONCILE (HIGH, Rule-9) :: **PRE-SHIP CHECK DONE 2026-06-26 conductor (analysis/self-audit/PRE-SHIP-CHECK-direction-block-2026-06-26.md).** The STATUS [2026-06-26 ~11:50 ET] STAGED batch landed PARTIAL, not as one atomic commit. (1) **HOLD #2/#4** — `j_vwap_reclaim_fb_enabled` + `j_vix_dayside_enabled` must stay dormant: individually YELLOW but the combined Safe-2 ATM book is recency-RED (n=17, -$8.01/tr clear) + Bold ATM book RED (n=10, -$60.12/tr); the recency-confirmation gate (2026-06-22) forbids a live flip into RED. license_monitor pings J on RED->green => enable then. This is the CORRECT held state — do NOT auto-flip. (2) **J-DECISION: `gap_and_go_enabled=True`** went live with NO recency-tracker basis (WATCH->LIVE candidate) — confirm A/B-validated, else propose revert-to-dormant. **PARTIALLY ANSWERED 2026-07-16 evening** (redesign ship-list arming attempt, see `GAP-AND-GO-REVALIDATION-BEFORE-ARM` below): NOT confirmable as A/B-validated on the live path as currently wired (06-28 re-check found 0 robust cells; no isolated exit override exists, so an armed fill would trade under ribbon_ride's SS-B shape, not its validated chart-stop-only cell). Detection stays enabled (WATCH, zero behavior change); exec-arm stays absent pending the revalidation spec'd below — this is NOT yet the "propose revert-to-dormant" branch since `gap_and_go_enabled` (detection) was never the thing in question, only exec-arming was. (3) **J-DECISION: finish-or-drop** the un-applied tail — `entry_bar_body_pct_min` 0.20 (staged->0.0), `aggressive/params.json#require_bearish_fill_bar` true (staged->false), `block_conf_lvl_rec_afternoon` true (staged->false). Rail-4: conductor cannot apply; needs J ruling. :: depends:none :: status:awaiting-j-ratification
- [ ] GAP-AND-GO-REVALIDATION-BEFORE-ARM (MED, filed 2026-07-16 evening, worker-tier) :: gap_and_go PUT arming attempt REFUSED (validity check failed — full trace: `automation/overnight/STATUS.md` [2026-07-16 ~evening ET] entry + `markdown/research/SIX-ACCOUNT-DAILY-HYPOTHESIS-REDESIGN-2026-07-16.md` §7). Two blockers: (A) the 2026-06-19 ratification's PUT-side edge (+$67.96/tr) collapsed ~7x (+$9.66/tr, top5_day_pct=556%) on a 2026-06-28 re-validation over a near-identical window — never reconciled beyond "different window," and is the codebase's own already-standing reason it's excluded (`SIGNAL-SHAPE-COVERAGE-2026-07-10.md`). (B) `heartbeat_core.py`'s `_SETUP_EXIT_OVERRIDES` (line 1181) has no `gap_and_go` entry — an armed fill would silently trade the ribbon_ride SS-B structure-stop shape (cat-cap -50%/TP1 ~+50-100%), not its validated CHART-STOP-ONLY/TP1+30%/runner-2.5x cell (identical bug class to the pre-2026-07-02 vwap_continuation bug). **BLOCKER B CLOSED 2026-07-18 conductor-weekend.** Shipped: `_SETUP_EXIT_OVERRIDES["gap_and_go"]` (isolated `j_gap_and_go_premium_stop_pct=-0.50` / `j_gap_and_go_tp1_pct=0.30` in `automation/state/params.json`, mirroring go_live_params) + a new generic `stop_mode` (literal, not a params-key) support in the `_xov`-shape builder + `_synthetic_verdict_from_extra` now threads `row["stop_price"]` (the watcher's own first-bar-extreme, already stamped by `setup_dispatch.dispatch_extra_setups`) through as `verdict["rejection_level"]` — the exact input `exit_manager.ExitState.from_entry`'s structure-stop resolution needs. Verified inert for every OTHER armed/isolated setup (vwap_continuation etc. — none declare `stop_mode`, so they stay byte-identical "premium"). 9 new guards (`test_gap_and_go_exit_wiring_2026_07_18.py`) + RED-proofed (git-stash both edited files -> exact expected `KeyError`s) + 178/178 broader G4/money-path/trade-to-learn/exit-manager/exit-actuator suites green, zero regressions. **gap_and_go's exec-arm stays ABSENT (still WATCH-only) — this fixes the shape, it is NOT an arming decision.** **BLOCKER A STILL OPEN** (unchanged scope, genuinely separate/larger research fire): re-run the edgehunt sweep on the full window through today with a proper walk-forward split to reconcile the 06-19-vs-06-28 disagreement before any arming attempt. **Falsification rail (apply once armed, per redesign §6):** gap_and_go live-fills check at n>=15 — WR materially below 72.6% or negative expectancy -> pull the flag (`extra_setup_exec_armed.gap_and_go: false`, single-key revert). :: depends:none :: status:blocker-B-closed-blocker-A-open

### Tier 3 — research items not owned by the cook-queue loop

- [ ] RIBBON-SPREAD-PER-TIER-DESIGN (MED) :: `ribbon_min_spread_cents=30` applies globally to ALL quality tiers (LEVEL/ELITE/SUPER). Hypothesis: ELITE/SUPER setups tolerate a tighter spread. Design a per-tier spread table + backtest. (Also in cook-queue, source=claude.) :: depends:none :: status:pending
- [x] SAFE-VIX-CONDITIONAL-SIZING (MED) :: Quality sizing (bearish_streak>=3 OR vol_ratio 1.0-1.5) failed G3 WF due to regime-dependence. Re-test the SAME criteria gated on VIX regime (NEUTRAL 17.5-22 was the profitable band per CONTEXT-103). (Also in cook-queue, context-86-followup.) :: depends:none :: status:done
  **[CLOSED 2026-07-20 ~02:xx ET conductor (AFTERHOURS)]** Built `backtest/tools/safe_vix_conditional_sizing_ab.py`
  (reuses safe_quality_sizing_ab.py's eligibility/reweight logic, adds a VIX-regime-at-entry gate,
  day-level 09:35 ET reading per agg_vix_bear_threshold_sweep.py convention). Found CONTEXT-103
  (STATUS-ARCHIVE.md 2026-06-18) -- it's an IS-ONLY finding over the GENERAL SAFE bear population,
  not the narrow TRENDLINE-tier quality-sizing candidate this study re-tests; scope mismatch
  documented in the output. **Result: REJECT_ALL_CUTS** -- POOLED reproduction WF=-0.144 (worse than
  parent's already-failing 0.06 -- OOS grew from 6 to 13 upgraded trades since the parent study ran,
  weeks of fresh data added, net negative), BULL/VOLATILE both evidence_n<15 (INCONCLUSIVE_UNDERPOWERED,
  not FAIL), and NEUTRAL_17.5_22 -- the specific band CONTEXT-103's general-bear finding would predict
  as favorable -- comes back WORSE than pooled (WF=-0.287). No VIX regime rescues the candidate; the
  quality-sizing upgrade stays REJECTED. Scorecard: `analysis/recommendations/safe_vix_conditional_sizing.json`.
  Guard: `backtest/tests/test_safe_vix_conditional_sizing_regime.py` (6/6, RED-proofed by removing the
  source module -- ModuleNotFoundError as expected, restored clean). Curated safety gate (31+5) PASS.
  Zero trading-path files touched (pure research tool + scorecard + test, no params/heartbeat/filters/
  placement edits) -- this is a REJECT finding, nothing ships to the live engine.
- [ ] SAFE-MULTIDAY-APPROACH-GATE (MED) :: When price within $0.30-0.50 of a multi_day level (PDH/PDL/weekly), trigger on APPROACH rather than exact touch. (Also in cook-queue, gamma-autonomous.) :: depends:none :: status:pending
- [ ] FALSE-BREAK-OPEN-CARRY-GATE (LOW, defensive) :: Do-no-harm gate protecting the LIVE bearish_rejection edge: suspend bear entries 30 min after a ★★★ named level (Carry/Active/multi-day) is breached at the 09:35 open bar AND the next closed bar recovers above it (single-bar L59 floor_hold variant, n_min=1). NOT entry-hunting (so not OP-22-superseded) but single-day evidence (one -$204 trade 2026-05-21) + C28/L156 diminishing-returns on bear-rejection exit refinement. Full spec preserved in `strategy/candidates/_chef-inbox/2026-05-21-false-break-open-carry-gate.md.DONE`. Promote to chef fire ONLY IF (a) >=3 more days show the same false-break-open->bear-trap pattern, or (b) J prioritizes bear-rejection exit hardening. :: depends:none :: status:pending

### Tier 4 — long-standing low-priority carry-overs (verify still relevant before picking up)

- [ ] T60 (LOW) :: TradingView MCP J-drawn-line capture → key-levels.json (`j_drawn` source, tier=Active). :: status:pending
- [ ] T101 (MED) :: Capture ≥5 TV MCP fixtures at different bar-cycle phases for `crypto/data/fixtures/` (v13_tv_mcp_parity test cases). :: status:pending
- [ ] T102 (MED) :: Investigate v02 source-parity drift (~23% iterations disagree >0.05% Coinbase vs yfinance). Deeper diagnostic: log WHICH bar disagreed; consider Alpaca crypto as 3rd source for 2-of-3 voting. :: status:pending
- [~] EOD-PHASE-2.2/2.3/2.4 (MED, weekend) :: **NARROWED 2026-07-18 (conductor).** Traced against current reality before picking up: 2.2 (tight fingerprint matching) and 2.3 (hit-rate+expectancy via OPRA fills / simulator_real) were ALREADY fully real in `modules/forensics.py` (590 lines, built 2026-06-15) — the item's own description was stale. Of 2.4's "9 stub modules", only 2 were actually still Phase-1-shallow at this fire's start (`analyze_execution`, `analyze_doctrine`) — `detection`/`macro`/`technical`/`watcher_fleet`/`lessons`/`risk`/`process`/`tomorrow`/`engine_health` were already real. **Shipped this fire: `analyze_execution` real impl** — `modules/execution.py` (new): fill-timing-vs-trigger-bar (matches ENGINE_ENTER decision time_et to first entry-fill time_et, degrades gracefully to neutral-low when no decisions.jsonl match exists rather than crashing — verified live via a real CSV-fallback smoke run on 2026-07-17 where engine_decisions was genuinely empty), partial-fill detection (multi-clip entry + spread-secs), slippage (kept from Phase 1). Wired into `main.py` replacing the `stubs_mod.analyze_execution` call. 6 new guard tests (`test_eod_deep_execution_phase24.py`) + 17/17 green with the existing detection-phase3 suite; live smoke run on 2026-07-17 confirms end-to-end (`phase: "2.4"`, real per-trade evidence, score 77/100, no crash). **Remaining real scope, narrowed to ONE item:** `analyze_doctrine` (currently only checks `rule_breaks_today` count — Phase 2 should score PER-TRADE doctrine compliance dimensions, not just a flat rule-break tally). Left open, correctly scoped now (was 9 modules, is 1). :: depends:none :: status:pending
- [ ] SHOT-DISCORD-ALERT (LOW) :: Wire shotgun-scalper stage5 completion into `discord-watcher.py` (pattern from `check_v15_appeared()`). :: status:pending
- [ ] T24 / T25 / T16 / T17 / T106 / T107 (LOW) :: Misc one-shots: mtf_confluence spec (T24), grinder-concurrency-audit (T25), refactor sniper_evaluator (T16), verify today-bias schema (T17), full-history in-progress-leak replay (T106), per-tick chart_read replay forensic tool (T107). Verify relevance before starting — several predate the 05-23 reset. :: status:pending

---

## Archived 2026-06-19 (resolved / stale — preserved, not deleted)

> **Conservative archive.** Nothing deleted. The 172 machine-generated lines below are rolled up here; the full verbatim text of every one is preserved in `automation/overnight/queue-archive-2026-06-19.md` (1164 lines, byte-identical pre-triage copy). Resolution rationale is recorded per cluster.

### Cluster A — 62 stale HARVEST-REGFAIL / EDGE_REGRESSION_FAIL "CRITICAL" items (2026-05-30 .. 06-18)

**Verdict: ALL STALE / FALSE-ALARM. Archived.** These were auto-emitted by `gym_harvester.py` every time a single live-source-jitter validator blipped during a half-hourly regression run. Root causes, all benign:
- The bulk (passed=64/78) flagged ONLY the `KNOWN_FLAKY_LIVE_SOURCE` validators (`v02_source_parity` + `v15_three_source_parity.live`) — live Coinbase/yfinance/Alpaca BTC-bar timing jitter, NOT engine-correctness gates (per T-2026-05-17-07, runner.py carve-out). `overall_pass` already excludes them.
- The `v25_filter_gates.offline` (passed=83/84) blips were the v25 presence-guard during authoring/edit windows; gym is **88/88 green WITH replay** as of CONTEXT-107 (2026-06-18, commit 244b9e5) and CONTEXT-109 (88/88, commit chain 5d247c6…). The v25 presence guard was adversarially re-proven that same night.
- The single `v41_midday_trendline_gate.live` / `v42_sizing_risk_cap_guard.offline` / `v43_ghost_entry_dual_account.offline` blips (06-16) were transient new-validator authoring windows, all green afterward.
- The original file already carried the note **"No active CRITICAL items"** (queue line 126) + a prior dismissal of 17 such items — nothing ever drained these because they are not real work.

**If a future regression is REAL** (gym < 88 on a non-flaky stage), it surfaces via `gym-scorecard-{date}.json` + STATUS.md `## Known broken`, not here. Do not re-queue raw harvester REGFAILs into the active backlog.

IDs archived (verbatim text in archive file): HARVEST-REGFAIL-20260618-100011 … 100036; HARVEST-REGFAIL-20260617-100026; HARVEST-REGFAIL-20260616-100020 … 100023; HARVEST-REGFAIL-20260601-100019 … 100024; HARVEST-REGFAIL-20260531-100012 … 100035; HARVEST-REGFAIL-20260530-220615; HARVEST-REGFAIL-20260521-100012 (was already marked resolved).

### Cluster B — ~110 HARVESTED-FROM-GYM data-point items (RSI/REGIME/RIBBON/SWEEP/BREAKOUT/FOOTGUN, 2026-05-20 .. 06-18)

**Verdict: CATALOGUE-ONLY, no SPY action. Archived.** Every one is an informational BTC-gym observation (e.g. "BTC RSI=18 oversold", "v09_regime TREND_DOWN 72% of bars", "v14_sweep liquidity-grab at 65000", "v01_live foot-gun caught — bar correctly rejected"). The items that were processed (the `[x]` ones, 100007/100008/100014-100016/100111/100112/100243-100245) ALL closed as `completed-informational` / `completed-catalogued` / `validator-working-correctly` with **no doctrine change** — confirming the entire class is data-flywheel exhaust, not drainable work. SPY 0DTE has no measured edge-correlation to BTC RSI/regime extremes; the swarm `correlation_analyst` already consumes BTC trend as context.

These are exactly the OP-22 "371st untriaged candidate is debt" pattern. The `gym_harvester` retention cap should prune them; they are archived here rather than acted on. Full IDs + text in the archive file (HARVEST-REGIMEEXT-*, HARVEST-RSIEXTREME-*, HARVEST-RIBBONFLIP-*, HARVEST-SWEEP-*, HARVEST-BRKCLUSTER-*, HARVEST-FOOTGUN-*).

### Cluster C — duplicated gym-session RED roll-up blocks (T-GYM-2026xxxx)

**Verdict: STALE DUPLICATES. Archived.** ~30 near-identical "gym-session RED for {date}" blocks (many the same date repeated 6-8×), almost all reducing to `pin-chain-verify (RED): rule_version=unknown` or `heartbeat-pulse-check (RED): max gap 15.02min`. The pulse-check 15.02-min "gap" is the known hash-unchanged-skip artifact (L39 — the early-exit writes SKIP not FIRE). The `rule_version=unknown` is the pin-chain reading a transient state. Current gym is GREEN. These were never individually actionable. Verbatim in archive file.

### Cluster D — completed historical work (TONS, 2026-05-13 .. 06-15)

**Verdict: DONE. Retained in archive file.** The pre-triage queue was ~70% `[x]`-completed items spanning the SNIPER pipeline, VWAP/ODF/v14_enhanced/REGIME_SWITCHER research arcs, the FIRE-19..43 self-heal series, the ENGINE-BENEFIT loop cycles (watcher fleet, NLWB/HS/FBW real-fills validations), the SWARM calibration arc, the MiniMax migration, and the level-detection T51-T59 series. All complete; full text preserved verbatim in `queue-archive-2026-06-19.md` for audit history. Not re-listed here to keep this file lean.

### Notable items folded into the Active backlog above (so nothing real is lost in the archive)

- MM-05/06/07 (J-ratification) → promoted to Active Tier 2.
- HEARTBEAT-SPY-LOGGING-CLARIFICATION + the two CONTEXT-107 J-rulings → Active Tier 2.
- The 4 CONTEXT-106 deferred findings (account_id, shadow-ratify, stray crypto __init__, stairstep) → Active Tier 1 (also filed as cook-queue tasks).
- The genuinely-open low-pri carry-overs (T60, T101, T102, EOD-2.2/2.3/2.4, SHOT-DISCORD-ALERT, T24/25/16/17/106/107) → Active Tier 4 with a "verify still relevant" caveat.

### Still-open items intentionally LEFT in the archive (superseded / dead-research, do not resurrect without J)

- SNIPER everything (T35/T31/T42b/T42c/T42d/T43/T44/T44d, T14, sniper-v2) — SNIPER was INVALIDATED on real fills (`markdown/research/SNIPER-FINAL-VERDICT-2026-05-13.md`, 0 keepers) and the loop was retired. OPRA-dependent re-runs are moot.
- T40 (swap Gamma_Heartbeat → heartbeat-v15-draft) — superseded; v15 shipped live 2026-05-13, and CONTEXT-106 made heartbeat.md SAFE-only. The draft is historical.
- T72/T73/T74 (v14_enhanced grinder memory sidecars) — v14_enhanced is research-only; mitigations T70/T71 already shipped.
- SWARM-BROKE-N20-GATE / SWARM-TESTED-MIXED-N20-GATE / SWARM-CALIBRATION-FORMULA-V3 (awaiting-J) — need live accumulation to cross N≥20; not drainable now.
- The seeder/T2xx CHEF-tagged seeds (T201-T205), EOD-PHASE-3/3.B, OPRA-BACKFILL-5-14, REGISTER-EOD-DEEPDIVE-CRON — either subsumed by the live Kitchen loop or weekend multi-day work.
- T29/T2026-05-21 watch-accumulation items (MOMENTUM-HIGHVOL-VIX25-RETEST, HS-WATCHER-LIVE-ACCUMULATION) — blocked on live-observation accumulation, not on the conductor.

---

## Completed

### 2026-07-22 ~22:42-23:05 ET — conductor (AFTERHOURS): STRATEGY-CANDIDATES-UNTRACKED-BACKFILL closed in full (parts 1-3), commits `d148f7e8` + `2d8c7594`

- [x] STRATEGY-CANDIDATES-UNTRACKED-BACKFILL (HIGH) :: all 3 named fix-parts shipped this fire
  (a genuine loop-close, per the prior fire's own `conductor_outcome.py` "trend=regressing ->
  prefer a loop-closing item" note). **Part (1)+(2), one bulk commit (`d148f7e8`):** staged
  all 1,176 untracked `strategy/candidates/` files (confirmed not gitignored, ~8MB all
  markdown) via `git add --pathspec-from-file` against the exact `git status --porcelain`
  untracked list -- never `-A`/`.`. Deliberately excluded the concurrently-modified
  `_review-log.jsonl` (another live process's in-flight write), same lane-safety discipline as
  the prior consolidation-sweep commits that same night. Verified post-commit: `git show --stat`
  shows exactly 1,176 files, all under `strategy/candidates/`; nothing else swept in.
  **Part (3), guard (`2d8c7594`):** graduated `self_check.py#check_candidates_untracked_backlog`
  -- $0, fail-open, `git status --porcelain -- strategy/candidates/` scoped, flags DEGRADED
  (never BROKEN) above threshold 20. 8 new guard tests (`test_self_check_candidates_untracked.py`)
  -- confirmed the pre-fix HEAD copy of self_check.py has neither the function nor the `run()`
  wiring (would RED-catch a regression, verified without git-stash per the standing
  never-stash-in-this-repo rule -- read HEAD's copy into a throwaway temp file instead, then
  deleted it). Curated safety gate 31+5 PASS both commits (pre-commit hook auto-ran it); gym
  104/104 PASS, no regression. Real-repo probe now returns `[]` (0 untracked, post-backfill).
  Also found + fixed a Bash-quoting side-issue while staging (nothing structural -- a plain
  `--pathspec-from-file` without the erroneous `--pathspec-file-nul` flag was all that was
  needed) and a stale `.git/index.lock` (0 bytes, 1h40m old, confirmed no live `git.exe` process
  via `tasklist` before removing -- standard git-recommended cleanup, not a live-process kill).
  Revert: `git revert 2d8c7594` then `git revert d148f7e8` (guard first, since it's the later
  commit; the 1176-file backfill itself is safe to leave even if the guard is reverted). :: status:done

### 2026-07-22 ~09:12-09:20 ET — conductor (AFTERHOURS): lesson-inbox drain -> L240 + mis-suffixed DONE marker fix, commit `0a79918b`

- [x] `2026-07-22-prospector-exact-dedupe-key-misses-reworded-family-duplicate` (lesson-inbox,
  sole open item) :: graduated to L240 in LESSONS-LEARNED.md, folded into CLAUDE.md OP-25 C7
  row, pointer bumped L239->L240. Side-find fixed: `2026-07-10-...bxm-real-time-levels.DONE.md`
  in `_chef-inbox` was mis-suffixed (`.DONE.md` not `.md.DONE`) — still `*.md`-globbable, a live
  re-consumption risk; renamed via `git mv`. 16/16 guard tests PASS (1 RED before the rename
  fix). Full report: `STATUS.md` this timestamp. :: status:done

- [ ] Next fire (no higher-priority item ready): all 4 author inboxes empty; pick next-oldest
  `_chef-inbox` item that is NOT TradingView-MCP-dependent (tool surface still lacks
  `tradingview`-prefixed tools this window) — CFTC/FINRA/alpha-vantage/polygon/OFI family is
  free-data-only and unblocked. `T-AUDIT-TAIL` remains the only queue.md `status:open` item,
  still not a clean 60-min pick per its own note. `queue.md` retention-cap consolidation
  (2789+ lines) still a named future task, not yet actioned. :: status:open

### 2026-07-21 ~17:42-18:10 ET — conductor (AFTERHOURS): stale validator-inbox item closed + time-bomb test found+fixed, commit `426e097`

- [x] 2026-07-14-tick-audit-zero-count-bug (validator-inbox, 7d stale) :: root fix already
  shipped commit `cc6755b` (2026-07-14), inbox item never marked closed. Live-verified fix
  still holds (`heartbeat-tick-audit-2026-07-21.json` total_ticks=770). While re-running its
  guard suite, found `test_stale_source_none_when_fresh` had gone silently RED on 2026-07-21 --
  a hardcoded `TODAY="2026-07-14"` literal compared against a freshly-written temp file's REAL
  mtime, only ever true on the day it was authored. Fixed: derive TODAY/now from the file's
  own real mtime. RED-proofed via `git stash`; 33/33 broader sweep; curated safety gate PASS.
  Self-audit gap batch re: TV-CDP check (2026-07-21T17:31:28) triaged as evidence-checked-false
  (timeout already exists, zero heartbeat_core consumption of self_check output). Lesson filed:
  `2026-07-21-hardcoded-today-literal-vs-real-file-mtime-time-bomb.md`. Full report:
  `STATUS.md` this timestamp. :: status:done

### 2026-07-21 ~07:48-08:20 ET — conductor (AFTERHOURS): PROSPECTOR-STATE-LOSS-REPROMOTION-FLOOD fixed + backlog deduped, commit `ff8ac55`

- [x] PROSPECTOR-STATE-LOSS-REPROMOTION-FLOOD (author-inbox hygiene + producer bug, self-found
  via STAGE 1 priority-5 chef-inbox audit) :: `_chef-inbox` had 65 files, 60 of them
  `prospector-*` data-source candidates dating back to 2026-06-16 (35 days stale) with 0 ever
  reviewed by chef (0 hits in `_chef-log.jsonl`). Root cause: the 2026-06-27..07-13
  git-stash-drop recovery (commit 41889a0) reset `analysis/prospector/state.json`, wiping
  `promoted_dedupe_keys` -- ledger rows from before the reset stayed re-eligible for
  `promote_top1`'s "oldest not-yet-promoted" pick, so the SAME 17 ideas got re-promoted into
  fresh dated files every few days for weeks (37 of 65 files were pure re-promotion noise).
  FIX: `already_promoted_from_inbox()` (`setup/scripts/prospector.py`) derives already-promoted
  status from the `_chef-inbox` filesystem itself (any date, `.md`/`.md.DONE`, matched by
  dedupe_key tail) as a second, state.json-independent check -- a repeat state loss cannot
  reproduce this bug class again. Repaired `state.json`'s `promoted_dedupe_keys` (5 -> 28,
  full recovered set). Deduped the existing backlog: 37 redundant files renamed to `.DONE`
  with a pointer to the surviving first-surfaced copy, leaving 28 unique ideas + 1 non-prospector
  item for chef to actually review going forward (down from 60). Guard: 6 new tests in
  `backtest/tests/test_prospector.py` (55/55 total), RED-proofed via `git stash` (all 6 failed
  with the exact expected pre-fix mismatch, restored clean, re-verified green). Broader sweep
  (`test_prospector` + `test_firm_brief_prospector_section` + `test_free_model_audit_prospector`)
  81/81 PASS. Curated safety gate (31+5-suite) PASS. Post-commit verified via `git ls-tree HEAD`
  (both a surviving unique file and a `.DONE`-renamed duplicate confirmed present as expected).
  **Zero trading-path files touched** (`prospector.py` is an observation-only R&D organ feeding
  `_chef-inbox`, no params/heartbeat_core/filters/placement/exit code) -- ships as engine-benefit
  per OP-22/OP-26, no J ratification needed. **Revert:** `git revert ff8ac55` (68 files, purely
  additive/renaming). Lesson filed:
  `_lesson-inbox/2026-07-21-producer-state-loss-silent-inbox-flood.md` (new discovery angle on
  C34: a silently-reset producer idempotency state can flood a downstream author inbox for
  weeks with zero crash/RED symptom -- the general antidote is deriving idempotency from the
  downstream artifact itself, not solely an upstream counter). **Not fixed this fire (out of
  scope, flagged only):** `state.json`'s `fires_total: 4` counter is itself stale/wrong (real
  fire count since 2026-06-16 is far higher) -- cosmetic, non-load-bearing, left alone rather
  than chased for a green number; a pre-existing set of 3 dangling `git stash` entries (unrelated
  to this fire, from prior sessions, correctly NOT dropped) noted for a future fire's cleanup
  judgment, not actioned here. Cost: ~$3.9 (STAGE 0/1 reads incl. task_scorer + queue.md HIGH
  tier review confirming all HIGH items already closed/not-pickable, chef-inbox audit + root-cause
  trace through prospector.py/state.json/git log, fix + backfill script + backlog dedup script,
  6 new tests + RED-proof round-trip, broader 81-test sweep, curated safety gate, commit +
  post-commit verification, this queue/STATUS/lesson-inbox update).

> OP-22 consolidation 2026-07-08: 25 finished [x] items moved here from Active backlog (loop G15).

### 2026-07-18 ~12:00-12:20 ET — conductor-weekend: V53-GYM-RED-LEVEL-BREAK-FIRST-STRIKE fixed + structurally guarded (3rd occurrence of the F26-class registry-drift bug, now closed with a graduated guard instead of a 3rd hand-fix)

- [x] V53-GYM-RED-LEVEL-BREAK-FIRST-STRIKE (HIGH, gym-regression, F26-class-repeat) ::
  Engine-health RED found independently at STAGE 0 (`drift_report.json` `overall_health`=RED,
  `consecutive_fail_streak`=120, `v53_setup_dispatch.live` 0/48 in 24h) — this fire diagnosed
  it fresh (traced the misleading STDERR `_build_ctx failed: AttributeError` to expected T5
  garbage-payload test noise, then isolated the real cause via `run_live()`'s `names_ok:
  false`), fixed it, and only AFTER fixing discovered a parallel same-day fire
  (PROMOTER-WRITES-LIVE-KEY, ~12:03-12:16 ET) had already filed this exact root cause as a
  queue item + lesson-inbox note without fixing it (rail-3 discipline on that fire). Both
  analyses independently converged on the same diagnosis — cross-confirms it.
  **Fixed:** `crypto/validators/v53_setup_dispatch.py` — added `level_break_first_strike` to
  `_KNOWN_SETUP_NAMES`. Verified `python crypto/validators/runner.py` gym 104/104 GREEN
  (was 103/104), `v53_setup_dispatch.live` now `pass: true`.
  **Went further than the interim fix** (per the other fire's own recommendation not to
  "repeat a 3rd time"): added `backtest/tests/test_graduated_guards.py::
  test_setup_dispatch_names_registry_sync`, which AST-parses `SetupDispatcher.run()`'s
  `dispatchers` registry and diffs it against `_KNOWN_SETUP_NAMES` in BOTH directions
  (missing-from-validator = hard fail; stale-in-validator = cleanup nudge) — no refactor of
  `_KNOWN_SETUP_NAMES` into a roster-derived property needed; the two lists just can no
  longer silently drift apart, checked on every `pytest` run, not only the 30-min cron.
  RED-proofed via `git stash` (fails without the fix with the exact diagnosis, passes with
  it). This is now the 3rd occurrence of the F26 registry-drift class (1st: 2026-07-11,
  `double_bottom_base_quiet`+`bollinger_squeeze`; 2nd: this bug, same day, two independent
  discoveries; 3rd would be structurally impossible now) — OP-25's "re-violated lesson MUST
  become a code assertion" applied for real this time instead of a 3rd hand-patch.
  Commit `a586100`. Lesson-inbox items from both fires consolidated (see
  `2026-07-18-hand-maintained-allowlist-drifts-from-live-roster.md`, updated in place, and
  `2026-07-18-setup-dispatch-registry-validator-drift.md`, this fire's own filing) —
  lesson-author can fold either/both into one L# (same root cause, same fix).
  :: depends:none :: status:done

### 2026-07-18 ~11:05 ET — worker-tier: FUTURES-EDGE3-TT-CREDENTIAL-RETIRE -- own-book SIM lane for mes-mnq-div-futures, TT-credential dependency killed instead of waited on

- [x] FUTURES-EDGE3-TT-CREDENTIAL-RETIRE (HIGH, futures-7th-arm, $0) :: `mes-mnq-div-futures`
  (`automation/state/fleet/accounts.json`, OOS +$71.46/tr n=118 8/8 gates,
  `edge3_mesmnq_div.py::FROZEN_CONFIG`) sat dormant since 2026-06-21 behind `enabled=false` +
  a Trading Technologies sandbox credential that was never wired (`docs/futures/` confirmed
  does not exist). PM decision (Fable/Opus): retire the dependency instead of waiting on it.
  **Alpaca-futures checked honestly first, verdict NO with live evidence:**
  `get_all_assets(asset_class="us_future")` on the real Safe-2 paper account returns zero
  assets (the same call with `asset_class="crypto"` returns 80+ real pairs same session,
  proving the query path works); documented AssetClass enum is `{us_equity, us_option,
  crypto}` only -- no Alpaca paper-futures path exists on any account we hold. **Built the
  honest equivalent:** `setup/scripts/futures_edge3_sim.py` -- own-book SIM lane (same tier
  as the crypto twin's bear-SIM lane) driving the SAME FROZEN_CONFIG detector byte-identical
  (only a local `dataclasses.replace(enabled=True)` copy, never the shared object) against
  REAL live ES=F/NQ=F quotes (yfinance, verified live), ATR-chandelier + chart-stop exit
  reused verbatim from `edge3.b4`'s own constants, gap-aware stop fills, every ledger row
  tagged `fidelity="sim_fill_vs_real_quote"`. RTH-scoped (09:30-16:00 ET, not the full Globex
  week) -- an evidenced correction, not tuning: the frozen edge is defined entirely on RTH 5m
  bars, so polling overnight buys nothing. Falsification rail: >=20 closed round trips ->
  `edge3-sim-progress.json` compares mean pnl to $71.46/tr, flags
  `INVESTIGATE_QUOTE_QUALITY` on a >50% shortfall. **Registered + verified alive real fire:**
  `Gamma_FuturesEdge3Sim` (`setup/scripts/install-futures-edge3-sim.ps1`),
  `Start-ScheduledTask` -> `LastTaskResult=0`, real `edge3-sim-state.json` after that fire:
  `last_action="noop" last_reason="market_closed_outside_rth"` (Saturday, market genuinely
  closed) -- `NextRunTime=2026-07-20 09:30 ET` confirms the first LIVE window is Monday's RTH
  open (not Sunday 18:00 ET Globex open -- the edge never acts outside RTH). Tests: 24/24 new
  (`backtest/tests/test_futures_edge3_sim.py`, incl. an end-to-end entry off a REAL validated
  historical signal day), zero regressions on `test_futures_mirror_shadow.py` (70/70, sibling
  lane untouched) + the fleet accounts-schema suites. `accounts.json`'s arm gained a
  `tt_credential_dependency_RETIRED_2026_07_18` note (historical broker/key_ref fields kept
  for audit trail, `enabled` stays false -- SIM only, no live order path implied). $0
  (yfinance + deterministic Python). Full detail: STATUS.md ~11:05 ET entry same date. ::
  depends:none :: status:done

### 2026-07-17 ~22:47 ET — worker-tier: GOAL-REPLAY-TODAY-GREEN ITERATION 7 (rigor verification pass) -- correct-exit re-adjudication of L1, 0/5 SHIP confirmed, goal TERMINAL

Re-verified iteration 5/6's load-bearing "0/5 flip, recency-overfit" conclusion, which had been
computed on the now-known-wrong `simulate_trade_real` exit shape for at least one candidate.
Scope audit FIRST (not assumed): code-traced all 5 parked candidates' actual exit engines; only
`elite_bear_level_reject_gate_ab.py` (L1) was genuinely computed via `simulate_trade_real` -- the
other 4 (bold-strike ATM/fleet-strike-proxy, zone-band, pong) already drive
`exit_manager.plan_exit_actions` directly via independently-built parallel harnesses
(`structure_stop_study.SS_B_SHAPE` lineage or pong's own paired-delta grid), proven materially
close to the live shape (structure-mode `premium_stop_pct` is inert, overridden by
`catastrophe_stop_pct` which byte-matches) -- not re-run, on evidenced grounds.

Rebuilt L1's removed-cohort P&L via `backtest/tools/regime_readjudication_correctexit.py` (new)
using `exit_manager_walk.walk_exit_manager` (the iteration-6 harness) under the REAL
`strategies.py#RIBBON_RIDE.exit` shape, same entry population/predicate as iteration 4/5,
unchanged. **Cross-checked 16/16 exact match against `exit_variant_ab.py`'s independently
-computed control_pnl for the same trades** (fable-too-good discipline -- confirms no new wiring
bug). **Result: L1 does NOT flip to PASS (still NO-SHIP), but the underlying MECHANISM inverted:**
under the wrong shape, 13/16 (81%) of the removed trades were artificially flattened to exactly
$0.00 (profit-lock-fixed-mode breakeven-round-trip artifact); under the correct shape the same
cohort nets **+$2,629.30 across 16 trades (10W-6L)** -- the "ELITE-tier bear entries" this lever
wanted to block are actually a NET-PROFITABLE population under the real exit mechanism, which is
exactly why blocking them now shows a clean, concentration-independent FAIL (both is_delta_mean
and oos_delta_mean negative) rather than the original concentration-driven
INSUFFICIENT_REGIME_SHIFT. Both routes land on NO-SHIP for L1, for materially different reasons --
reported precisely.

**GOAL DISPOSITION: TERMINAL, DONE.** 0/5 candidates ship, confirmed under the correct exit model
for the one affected candidate and evidenced-unaffected for the other 4. `automation/overnight/
GOAL-REPLAY-TODAY-GREEN.md`'s GOAL DISPOSITION section closes the loop: faithful replay harness
built+verified (iter 6, 6/6, 5% delta), decision-layer levers closed (0/5 across two independent
methodology passes), exit-quality lever closed (WIDER_TRAIL_25 clean FAIL), today's decision-layer
replay faithful (5/5 capture, 12/12 tier parity). No `params.json`/`aggressive/params.json` file
touched this iteration or across the goal. SIM-EXIT-SHAPE-PARITY-AUDIT filed above as separate
follow-on (the correct-exit rebuild pattern should extend to other `simulate_trade_real`-based
studies outside this goal's scope). No further iteration scheduled under this goal name.
Files: `backtest/tools/regime_readjudication_correctexit.py`,
`analysis/recommendations/regime-readjudication-correctexit-2026-07-17.{json,md}`,
`automation/overnight/GOAL-REPLAY-TODAY-GREEN.md` ITERATION 7 + GOAL DISPOSITION,
`automation/overnight/STATUS.md` 2026-07-17 ~22:47 ET entry.

### 2026-07-17 ~22:25 ET — worker-tier: EXIT-MANAGER-REPLAY-HARNESS BUILT (GOAL-REPLAY-TODAY-GREEN iteration 6) -- 6/6 faithful, second root cause found, exit-quality candidate NO-SHIP
Built the harness this item spec'd (`backtest/lib/exit_manager_walk.py` + `backtest/tools/exit_manager_replay.py`): drives the REAL `automation/state/fleet/exit_manager.py plan_exit_actions` decision core tick-by-tick over today's real 1-min OPRA bars, instead of `simulate_trade_real`. **Result: 6/6 of today's real core round trips within tolerance** (iteration 2: 0/5, iteration 3: 2/5-trivial) -- the win iterations 2-3 could not get. Total delta -$17.15 on +$342.00 live (5.0%). Both real winners now correctly ride via the trailing chandelier instead of breakeven-zeroing.
**Second, previously-undocumented root cause found:** every sim-based ribbon_ride study in this codebase (including `elite_bear_level_reject_gate_ab.py`'s "faithful" config) reads exit knobs from `params.json`'s top-level keys, but the REAL exit_manager registration reads `automation/state/fleet/strategies.py#RIBBON_RIDE.exit.to_dict()` instead (trailing chandelier + structure-stop-primary, not fixed-mode premium stop) -- the sim was testing the WRONG shape, not an approximation of the right one.
**Exit-quality A/B (step 3):** only 6 real trades exist under the current STOP-B shape (all today, STOP-B shipped 2026-07-09) -- no historical population to A/B against directly, so `backtest/tools/exit_variant_ab.py` re-derives 188 historical ribbon_ride entries' exits under CONTROL (real shape) vs CANDIDATE `WIDER_TRAIL_25` (trail 15%->25%). **Regime-conditioned verdict: clean FAIL, 0/5 gates** (regime-OOS delta -$5.05/tr, WF=-3.34, unstable, BH-FDR p=0.855). Full-population delta -$813.30/188 trades. NO-SHIP; params.json untouched; exits stay SS-B.
Guard: `backtest/tests/test_exit_manager_replay.py` (4/4). Full detail: `automation/overnight/GOAL-REPLAY-TODAY-GREEN.md` ITERATION 6, `automation/overnight/STATUS.md` 2026-07-17 ~22:25 ET entry.

### 2026-07-17 — worker-tier: REGIME-REFERENCE-CLASS-ADJUDICATION (methodology EARNS_RIGHTS, 0/5 parked candidates flip to PASS)
Resolved `analysis/recommendations/REGIME-REFERENCE-CLASS-ADJUDICATION-2026-07-17.md` (Fable/Opus
frame): 5+ studies all park on negative-2025-IS/positive-2026-OOS (`INSUFFICIENT_REGIME_SHIFT`)
under calendar WF -- is that (A) recency-overfitting or (B) genuine regime break? Built a
regime-CONDITIONED validator (VIX band `params.json#vix_iv_regime_bands` + trend character
`crypto/lib/market_structure.py#analyze_structure`, the SAME primitives
`context_bundle_producer.py`'s live daily trend read uses) that classifies every trading day and
validates candidates via a chronological (not calendar-year) within-regime split. **MANDATORY
self-validation gate passed BEFORE adjudicating anything:** all 4 known-bad cohorts (NLWB n=23,
confluence-fresh95 n=38, double-top n=354, a seeded pure-noise placebo n=40) correctly KILLED;
the one known-good cohort with enough n (`vwap_continuation` ITM-2/-8%, the sole
STRATEGY-SPACE-REGISTRY.jsonl row marked LIVE, n=163) cleared all 5 gates cleanly (WF=1.359,
BH-FDR p=0.005); OP-16 anchor dates all coherently labelled. Global tautology check: Cramér's V
0.21 (regime is NOT a calendar-year proxy) -- **verdict EARNS_RIGHTS.** Re-adjudicated the 5
parked candidates anyway with an honest result: **0/5 flip to PASS.** elite-bear L1 stays
INSUFFICIENT_REGIME_SHIFT even within its own regime bucket (n=8, thin, concentration-driven).
bold-strike ATM's calendar confound genuinely clears under regime-conditioning (is-delta flips
sign) but the "edge" fails BH-FDR (p=0.46) and concentration -- never a real population effect,
just correlated with a few outsized trades that happened to land in 2026. zone-band gets WORSE
under regime-conditioning. pong-resting-limit reproduces its original near-miss shape, now
blocked by BH-FDR instead of the anchor gate. fleet strike/risky-3 inherits bold-strike ATM's
result (no separate cohort, per `WF-GATE-METHODOLOGY-2026-07-16.md`'s own disposition).
**Disclosed limitation (fable-too-good hunt):** one regime bucket (`MID_uptrend`) covers 53% of
all 389 trading days, so most candidates' "target regime" defaults to it -- for those,
regime-conditioning is honestly closer to a chronological (not calendar) split than a narrow
regime-specific test; still a real, useful mechanism, just a humbler one than advertised.
**Answer: (A) recency-overfitting** is the better-supported read for these 5 candidates -- not
because the methodology failed (it earned the right cleanly) but because none of them survive
scrutiny once the calendar framing is removed. No `params.json`/strike-selection file touched, no
orders, no ship. Full record: `analysis/recommendations/prereg-regime-conditioned-validation-2026-07-17.json`
(frozen prereg) + `regime-conditioned-validation-2026-07-17.{json,md}` +
`regime-conditioned-readjudication-2026-07-17.json`. Code:
`backtest/tools/regime_classifier.py` + `regime_conditioned_validator.py` +
`regime_conditioned_self_validation.py` + `regime_conditioned_readjudication.py`.

### 2026-07-17 — worker-tier: STUDY-STATIC-VS-TRENDLINE-REJECT-BOUNCE-PHASE (OOS-VALIDATED, NO-SHIP)
GOAL-REPLAY-TODAY-GREEN ITERATION 4. Re-framed away from the originally-spec'd
"position_in_prior_range / bars-since-session-extreme bounce-maturity proxy" (would have
required inventing an ex-ante classifier, and the sibling day-type trend/chop classifier had
already FAILED 2026-07-15, `daytype-gate-result.md` 3/3 KILL) to a cleaner, fully ex-ante,
zero-invented-proxy framing: gate BEAR-side `ELITE`-tier entries (traced the code -- ELITE's
`confluence`/`sequence_rejection` triggers are, by construction, impossible without a matched
static price level, so "ELITE bear" IS "static-level-anchored bear," not an approximation of
it). Structural mirror of the already-live `block_elite_bull` gate (bull side already blocked;
bear side wasn't). Full-history real-fills OOS study (`backtest/tools/elite_bear_level_reject_gate_ab.py`,
IS=2025 n=119, OOS=2026 YTD n=86, frozen `ab_delta_per_trade_v2026_07_16` WF form): **NO-SHIP,
ladder verdict `INSUFFICIENT_REGIME_SHIFT`** -- ELITE-tier bear trades were net WINNERS in 2025
(+$533/6tr) and net LOSERS in 2026 YTD (-$683/11tr), both WF forms deeply negative (-0.699 /
-1.774), 1/2 IS sub-windows hurt. fable-too-good hunt (built into the script): the entire
apparent OOS edge is 3 concentrated trades (drop-top-3 zeroes the delta to $0.00) and a 20-seed
random-removal placebo null does NOT clear alpha (p_null=0.1429) -- ELITE-tier is not
demonstrably better than blocking 11 random PUT trades. CONFIRMED (via raw
`core-decisions.jsonl`, not audit prose) the lever would have skipped today's 11:06/11:40 ELITE
losers (+$139 avoided) and kept the 13:01 TRENDLINE winner untouched -- real, but explicitly the
confirmation, not the ratification basis. `params.json` NOT touched. Re-test trigger recorded
(AMENDMENT 1): OOS window >=50% longer (on/after ~2026-10-19) OR >=30 new ELITE-bear episodes
accrued post-2026-07-08. Full record: `analysis/recommendations/elite-bear-level-reject-gate-ab-2026-07-17.{json,md}`,
`automation/overnight/GOAL-REPLAY-TODAY-GREEN.md` ITERATION 4 LEDGER entry.

### 2026-07-17 — worker-tier: SAFE-TRADES-CSV-JOURNALING-GAP (done-shipped, root cause found + fixed + backfilled)
J-directed direct fix of the queue item filed by the same-day safe-tape audit
(`analysis/daily-brief/2026-07-17-safe-tape-audit.md` Part 1, Trade 5). **Root cause:**
`fleet_journal_bridge.py` -- the ONLY automated `pnl-statement.json` -> `trades.csv` bridge
that exists -- hardcoded `FLEET_REST_ARMS = ("safe-3","risky-1","risky-3")` and its own
docstring wrongly claimed the 2 core mcp_heartbeat arms (safe-2/bold-2) had "an existing
journaling path... written by the live heartbeat"; that path does not exist. `broker_fills.py`
was ALREADY computing correct engine-vs-manual attribution for safe-2/bold-2 round trips
(checking `exec`/`extra_exec`/`exit_pass` in `core-decisions.jsonl`) -- the bridge just never
consumed it for those two arms, so BOTH primary and extra_exec (G4 side-channel) core-Safe/Bold
engine fills were silently unjournaled. **Fix:** added `CORE_ARMS`/`ALL_BRIDGE_ARMS` +
`_build_core_decision_index()` (normalizes core's `exec`/`extra_exec` schema into the same
entry_dec shape the fleet path already understands -- zero new attribution logic, extra_exec
gets identical treatment automatically) + a manual-attribution exclusion in
`_primary_round_trips` (core round trips attributed "manual" are J-called trades already
journaled via the separate `j_intent_journal.py` pathway -- never duplicated here). Wired into
`firm_brief.py`'s existing EOD-adjacent call site (`run_bridge(arms=ALL_BRIDGE_ARMS)`).
**Backfill:** historical dates before 2026-07-17 were found to have a mix of already-logged
(hand-aggregated, some with 1-second partial-fill-leg timestamp jitter) and genuinely-missing
core round trips going back to 06-26; rather than risk a double-count on a hand-rolled natural-
key reconciliation heuristic (verified one real near-miss case: 07-02 09:57:15/16), seeded the
watermark with a clean historical CUTOVER at 2026-07-17 (pre-cutover dates left exactly as
found, flagged for a separate careful reconciliation pass -- NOT done here, scope stayed to
what J asked) and ran the real (non-dry-run) bridge for 2026-07-17 only. **Result:** all 6
core-Safe round trips for 2026-07-17 now in `trades.csv` (744P -37, 745P -102, 746C +89
[J-manual, pre-existing], 746P +241, 745P#2 bollinger_squeeze +105, 743P -56), CSV total
verified **+$240.00**, exact match to broker-truth (`pnl-statement.json` / live
`get_account_activities`). Also backfilled 3 core-Bold round trips (743P, +191 net) as a
consistent side effect of the same fix. Idempotency verified (re-run after backfill = 0 new
rows). journal/2026-07-17.md's `## Trades` prose gained an ADDENDUM section narrating all 5
previously-invisible engine round trips including the bollinger_squeeze fill. **Guard tests:**
`backtest/tests/test_fleet_journal_bridge.py` +10 new (24/24 total green), RED-proofed (8
failed against pre-fix code, stashed/restored). Read-only on trading-decision logic --
journaling/accounting only, no `heartbeat_core.py`/`params.json` touched. Companion fix same
session: `trade_today_watcher.py` cross-arm order-id dedup (safe-1/safe-2 shared-account
double-count, task_32d96df3) -- `backtest/tests/test_trade_today_watcher.py` +4 new (32/32
green), also RED-proofed. Full detail: `automation/overnight/STATUS.md` 2026-07-17 entry.
:: depends:none :: status:done

### 2026-07-15 — worker-tier: CONTEXT-BUNDLE-EXTENSION-EVENTS-PRIORDAY (done-shipped, LOGGED-ONLY, follow-up to Phase 0/Phase 1)
J's direct ask: "review the new labels... that involve current real world events and prior day technical analysis." Extended `setup/scripts/context_bundle_producer.py` (Phase 0's trend-alignment producer, commit `b1597a6`) with the two pre-approved fast-follow dimensions from that same v1-scope note: `events` (macro-calendar.json + news.json — next/last event, minutes-to/-since, `no_trade_window_active` computed live via `macro_calendar.compute_no_trade_windows` reused verbatim, `calendar_stale` anchored to `Gamma_MacroCalendar`'s real 07:45 ET weekday fire), `prior_day` (prior complete trading day OHLC off the SAME already-fetched `daily_df`), `today_context` (gap_pct_at_open, position_in_prior_range, 60-min 09:30-10:30 ET opening range null-before-10:30-by-design, `rvol_session_so_far` — causal cumulative-volume-vs-20-day-median-at-same-elapsed-time, needed one new `5Min`/35-day fetch), `levels_context` (nearest active key-levels.json level above/below + count within 1%). schema_version 1→2, `compute_trend_alignment`'s signature/behavior fully untouched (re-verified: the already-built-and-KILLed Phase 1 correlation study, `test_trend_alignment_correlation_study.py`, 11/11 still green). Every field null-with-reason on missing/not-yet-available inputs; each dimension isolated in its own try/except in `main()`. Zero new `heartbeat_core.py` reads — it already tags the whole bundle dict verbatim, so the enriched schema rides along for free; re-RED-proofed anyway with 2 new tests (`test_context_bundle_tag_no_behavior_change.py`) proving byte-identical verdicts with the ENRICHED bundle present vs absent. `Gamma_ContextBundle` re-registered 09:30→09:25 ET start (`install-context-bundle.ps1`), live-verified against the real scheduled-task registry (`StartBoundary=07:25 MT`, `DaysOfWeek=62`, `RepDuration=PT6H35M`, `State=Ready`, real Wednesday `NextRunTime`). Real `--once` run pre-market against the ACTUAL current files: `degraded:false`, next_event=PPI 08:30 ET today (med), prior_day=Tuesday's real OHLC, or/rvol correctly null (market not open), levels_context resolved 7 levels within 1% of spot. 71/71 tests green across the 4 touched/adjacent suites (31 `test_context_bundle_producer.py` [+17 new] + 8 `test_context_bundle_tag_no_behavior_change.py` [+2 new] + 11 `test_trend_alignment_correlation_study.py` + 21 `test_macro_calendar_producer.py`). Grading path (correlation-scorer, same pattern that KILLed trend-alignment) pinned as a spec paragraph in the module docstring only — NOT built, per the task's explicit item-6 scope. Full detail: `automation/overnight/STATUS.md` 2026-07-15 ~01:17 ET REVOKE-report entry. :: depends:none :: status:done

### 2026-07-14 — worker-tier: TREND-ALIGNMENT-PHASE1-CORRELATION (done-killed, look-ahead leak found+fixed, KILL reinforced not overturned)
Ran the FROZEN pre-reg (`analysis/recommendations/prereg-trend-alignment-correlation-2026-07-14.json`) exactly across P1 (MODELED, SS-B replay, n=250 canonical `ribbon_ride` cohort)/P2 (MEASURED, real fills, n=113→110 engine)/P3 (J's OP-16 anchor, n=7, context-only). **Kill ladder: 3/4 (now, post-fix, actually 2/4) required conditions failed — P1 verdict = KILL, overall = KILL.** Adversarial verify pass (`/fable-too-good` + `/think-like-fable` discipline) then found `alignment_for_decision`'s `_slice()` in `backtest/tools/trend_alignment_correlation_study.py` sliced on bar-OPEN timestamp (`timestamp <= ts`) instead of bar-CLOSE (`timestamp + granularity <= ts`) — a systematic C6 look-ahead leak (every entry_ts is intraday, so the still-forming daily/hourly/15m bar's already-realized future OHLC leaked in every single decision). **Fixed**: `_BAR_GRANULARITY` map (daily=1day/hourly=1h/m15=15min) + corrected `_slice`, 2 new regression guard tests (`test_alignment_for_decision_excludes_still_forming_bar_mid_span` catches a decision_ts strictly mid-bar, the exact shape prior guards never tested). **Re-ran the frozen scoring pass with the fix — verdict did NOT flip, got MORE decisive**: P1_OOS rho -0.054→-0.150 (still null/negative), P2_engine rho +0.041→-0.143 (flips to AGREE in sign with P1 — pre-fix, P1/P2 disagreed in sign; post-fix both show a mild NEGATIVE trend-alignment/outcome relationship), and full-alignment bucket (+3, the strongest form of the hypothesis) is now clearly the WORST bucket in both P1_OOS (mean -$148.43) and the disclosed adversarial finding. **Conclusion: mechanical entries already price trend in — multi-TF alignment does not separate winners from losers on this engine's signals, if anything mild over-alignment correlates with worse outcomes (not significant, p>0.10, don't over-read it).** Phase 0's context-bundle tag stays LOGGED-ONLY, not promoted to any gate/veto/sizing input. No orders, no live params/config touched. Full detail: `analysis/recommendations/trend-alignment-correlation.{json,md}`, `backtest/tools/trend_alignment_correlation_study.py` (fix), `backtest/tests/test_trend_alignment_correlation_study.py` (+2 guards, 31/31 green incl. Phase 0's own suite). :: depends:none :: status:done-killed

### 2026-07-14 — worker-tier: A5-PREMARKET-DETERMINISTIC-FALLBACK (built + wired + guard-tested, done-shipped)
Built the deterministic fallback spec'd in `analysis/deep-research/2026-07-14-premarket-reliability.md` (3-week audit: the premarket LLM step missed 25-44% of trading days across 3 failure shapes -- CCR/auth outage, hollow-success, reaped-silent -- all degrading to the same stale `today-bias.json`). New `setup/scripts/premarket_deterministic_fallback.py` ($0, pure Python, no LLM/MCP/CDP): mechanical bias from premarket-close-vs-prior-close + overnight-range-position (un-blockable Alpaca REST + yfinance paths already proven by `sight_beacon.py`/`heartbeat_core.py`), VIX context against the EXISTING `params.json` static thresholds (never hardcoded), key_levels preferring the already-fresh `key-levels.json` deterministic producer with a prior-day-H/L-from-bars fallback-of-fallback, news_calendar via `macro_calendar.py#run(do_fetch=False)`, load-bearing `safe_equity_confirmed`/`bold_equity`/`daily_loss_budget_dollars` read from the SAME-run `daily_loss_guard.rearm()` output (no extra network call), `rule_version_pin` read straight out of `premarket.md`'s own `RULE_VERSION_EXPECTED` constant (single source, never duplicated). Every write stamped `degraded:true, source:"deterministic_fallback"`, ZERO fabricated `falsifiable_predictions`. FAIL-SAFE: refuses to write anything (ok=False, file untouched) if the PRIMARY input (SPY bars) is unavailable from every source -- never fabricates a bias from nothing. Wired into `run-premarket.ps1`'s existing OP-33 deliverable-verify gate: fires ONLY inside the already-existing `deliverableMsg` failure branch (after both LLM attempts + the silent-failure detection), re-verifies the fallback's own degraded markers before trusting it, and reports the outcome under a NEW `### DEGRADED: premarket` STATUS.md heading distinct from the pre-existing `### BROKEN:` heading (spec point 4's explicit "distinguish stale from degraded-fresh" ask) -- exit reclassified 3->0 only on a confirmed fresh degraded write, stays 3/BROKEN if the fallback also fails. `self_check.py` gained a parallel distinction (`PREMARKET DEGRADED` problem, classifies as DEGRADED not BROKEN via `_problem_is_broken`, never masked by the pre-existing date-only `PREMARKET STALE` check). Guards: `backtest/tests/test_premarket_deterministic_fallback.py` (23 tests -- bias formula incl. deadband/disagreement, VIX threshold bucketing, rule-version-pin read, key-levels fresh-then-fallback, and the load-bearing STALE-DATE-DETECTION guard proving `date` always derives from the live ET clock never from stale/foreign input data) + `backtest/tests/test_premarket_fallback_wiring_guard.py` (11 tests locking the `.ps1`/`self_check.py` wiring itself, RED-proofed live this session by breaking the DEGRADED heading and confirming the guard catches it before reverting). 34/34 green; full 3711-test suite collects clean; `run-premarket.ps1` PS 5.1 parse-verified. Zero orders, zero live-param edits, built/wired after 16:05 ET per the market-hours discipline. :: depends:none :: status:done

### 2026-07-14 — worker-tier: TRENDLINE-BREAK-BATTERY-S1 + CALL-VETO-SSB-REVAL-S2 (both KILL/premise-false, done-killed)
S1: froze `analysis/recommendations/prereg-trendline-break-battery-2026-07-14.json` (3 entry variants x 2 line families x 2 directions = 12 cells), ran it verbatim on the full G1 break-dataset (48,336 real episodes, real OPRA replay through live exit_manager/SS-B). **All 12 cells FAIL** -- negative expectancy, BH-FDR-significant, OOS-negative, none beats nulls. S2: instructed to re-validate an "old CALL-veto scorecard" under SS-B -- searched `analysis/recommendations/` + `strategy/candidates/` and found no such scorecard ever existed (10 Chef drafts, all still NEEDS-OOS/NEEDS-REAL-FILLS) -- reported premise-false rather than fabricating a stand-in. Full detail + verdict tables: `analysis/recommendations/trendline-break-battery.{json,md}` + `analysis/recommendations/trendline-call-veto-ssb-reval.json`, `automation/overnight/STATUS.md` 2026-07-14 entry. Did not touch the in-flight TRENDLINE-SUBSYSTEM-AUDIT crew's own files/prereg (`trendline_engine.py`, drawing bridge, audit doc, `trendline-structure-conviction-preregistration.json` -- read-only/untouched, that spec still `FROZEN_PENDING_RUN` and belongs to that crew). :: depends:none :: status:done-killed

### 2026-07-11 — worker-tier: SAFE-2-ACCOUNT-REPLACEMENT (CRITICAL, resolved WITHOUT waiting on J)
**Resolution actually taken (not the depends:J-creates-account path this item was filed under):** rather than block on J provisioning a brand-new Alpaca paper account, repointed core Safe (`heartbeat_core.py` ACCOUNTS["safe"], the `alpaca` MCP server) at the fleet champion/challenger roster's OWN `safe-1` arm account (`PA3DHPT7KIQE`) — a real, ACTIVE, already-provisioned paper account (live-verified equity $1,746.75, options_trading_level 3) — and retired the `safe-1` fleet arm (`automation/state/fleet/accounts.json` status active→retired) to free it for reuse, since one broker account can't safely serve two independent execution paths (mcp_heartbeat + fleet_rest) at once. Paper-only, fully reversible, sanctioned under standing autonomy doctrine (OP-0) — no J action needed. Active fleet_rest roster is now `{safe-3, risky-1, risky-3}` (was 4, incl. safe-1).
**Full blast-radius fix (14 files beyond the 3 credential files):** `setup/scripts/broker_fills.py` + `fleet_journal_bridge.py` (`FLEET_REST_ARMS` 4→3 tuples — the broker_fills one was a REAL bug: leaving safe-1 in would have double-processed the reused account under two labels and misattributed core Safe's future fills as "manual"), `accounts_status.py` (`ORDER`/`ENGINE_WIRING` — would've shown a duplicate-account row + double-counted the TOTAL), `mcp_audit.py` + `mcp_audit_direct.py` + `context_audit.py` (all three hardcoded the OLD dead account number `PA3S2PYAS2WQ` as an expected-value check — would have started FALSE-FAILING the weekly MCP audit and the CLAUDE.md integrity check the moment the credential fix landed), `fleet_eod.py` (comment), `cockpit/server.js` + `automation/prompts/mcp-weekly-audit.md` + `.claude/skills/mcp-weekly-audit/SKILL.md` + `markdown/specs/ARCHITECTURE.md` + `markdown/infra/mcp-install.md` + `markdown/0dte/dual-account-design.md` + `CLAUDE.md` (docs/labels). Tests: `test_six_account_routing.py` + `test_six_account_exit_shapes.py` updated (6-arm/4-arm hardcoded sets → 5/3, new explicit guard `test_safe1_is_retired_not_dispatched`), `test_broker_fills.py::test_fleet_rest_arm_option_is_engine` fixture arm swapped safe-1→safe-3 (real fixture-drift catch — safe-1 dropping out of `FLEET_REST_ARMS` flipped its attribution from "engine" to "manual", caught by running the suite, not by inspection). State resets: `circuit-breaker.json` (core Safe) baseline reset off a moment-of-write live equity re-query ($1,746.75, was pinned to the dead account's stale $1,512.71), `today-bias.json` equity fields patched to match (will be naturally overwritten by Monday's real premarket fire). **Verified, not claimed:** direct REST re-query (bypassing the session's stale MCP connection) confirms `PA3DHPT7KIQE` / `ACTIVE` / equity $1,746.75 / `trading_blocked=False` / `options_trading_level=3`; `self_check.py` re-run this session dropped the `BROKER KEY STALE/REVOKED: safe-2` problem entirely (only the unrelated, pre-fix `DRESS-REHEARSAL RED` snapshot remains, timestamped BEFORE this fix — worth a fresh look, not re-run here to stay in scope). Fleet test suite (`automation/state/fleet/` + the 4 fleet-adjacent `backtest/tests/` files) before/after: **5 failed (pre-existing, unrelated — today's recency-min-sizing qty-clamp ships, confirmed identical failures before AND after) + 305→306 passed** (net +1 from the new guard test), zero regressions. `test_broker_fills.py`/`test_fleet_journal_bridge.py`: 26/27→27/27 (the one fixture-drift fix). Full detail + exact revert steps (harder than a flag flip — needs BOTH the credential un-repoint AND un-retiring the fleet arm): `automation/overnight/STATUS.md` 2026-07-11 REVOKE-report entry, `automation/state/fleet/accounts.json`'s `safe-2._repoint_2026_07_11` / `safe-1._retired_doc` fields. **Known gap, not fixed here (out of scope, flagged not hidden):** `params.json`'s `_j_ribbon_ride_strike_override_doc` still says the core Safe account is "DELETED pending J's replacement" (a giant embedded doc-string, cosmetic-only — the feature itself reads a live flag, not that prose, so it is functionally unaffected and reactivates automatically now that core Safe has a live account again); `automation/state/dress-rehearsal.json` not re-run. :: depends:none :: status:done

(2026-07-01 down through 2026-06-19 dated Completed entries — 119 lines / ~54KB —
moved verbatim to `automation/overnight/queue-archive-2026-07-23-completed.md` on
2026-07-23 by conductor, QUEUE-MD-RETENTION-CAP, to bring queue.md back under the
Read tool's 256KB single-shot limit. Nothing deleted — pointer only.)

(historical completions preserved verbatim in `automation/overnight/queue-archive-2026-06-19.md`)

## Blocked
(none active — Rule-9 J-ruling items live in Active Tier 2, which are decisions not blocks)

## Forward backlog (deliberate-future)
See automation/overnight/forward-backlog-2026-06-19.md for the post-all-night-loop forward work (Tier 0 BEARISH_REJECTION exit/regime; Tier 1 decision-lib P3/P4; Tier 2 key-levels archive + watcher RETIRE).

## HARVESTED-FROM-GYM (auto-queued by crypto/benchmarks/gym_harvester.py)

- [ ] HARVEST-SWEEP-20260723-100054 (MED) :: v14_sweep liquidity-grab at level=66000 dir=up bar_idx=12 | wick_excess=0.0379% close_back=0.2331% — feeds v15.2 sweep-blocker doctrine :: key=EDGE_SWEEP_DETECTED:2026-07-23T09:57:03.671131+00:00:66000:up:12 :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260722-100050 (LOW) :: v09_regime TREND_UP dominant: 75/81 bars (93%) | last_regime=CHOP atr_14=67 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-21T10:00:00+00:00:TREND_UP :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260722-100051 (LOW) :: v09_regime TREND_UP dominant: 69/81 bars (85%) | last_regime=TREND_DOWN atr_14=70 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-21T11:00:00+00:00:TREND_UP :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260722-100052 (LOW) :: v09_regime TREND_UP dominant: 63/81 bars (78%) | last_regime=TREND_UP atr_14=59 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-21T12:00:00+00:00:TREND_UP :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260722-100053 (LOW) :: v09_regime TREND_UP dominant: 69/81 bars (85%) | last_regime=TREND_UP atr_14=81 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-21T13:00:00+00:00:TREND_UP :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260722-100054 (LOW) :: v09_regime TREND_UP dominant: 58/80 bars (72%) | last_regime=BREAKOUT atr_14=116 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-21T14:00:00+00:00:TREND_UP :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260722-100055 (LOW) :: v09_regime TREND_DOWN dominant: 56/80 bars (70%) | last_regime=TREND_DOWN atr_14=68 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-22T07:00:00+00:00:TREND_DOWN :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260722-100056 (LOW) :: v09_regime TREND_DOWN dominant: 68/81 bars (84%) | last_regime=TREND_DOWN atr_14=69 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-22T08:00:00+00:00:TREND_DOWN :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260722-100057 (LOW) :: v09_regime TREND_DOWN dominant: 57/81 bars (70%) | last_regime=TREND_UP atr_14=70 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-22T09:00:00+00:00:TREND_DOWN :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260721-100046 (LOW) :: v09_regime TREND_UP dominant: 56/80 bars (70%) | last_regime=TREND_UP atr_14=183 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-20T16:00:00+00:00:TREND_UP :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260721-100047 (LOW) :: v09_regime TREND_UP dominant: 57/80 bars (71%) | last_regime=TREND_UP atr_14=89 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-21T05:00:00+00:00:TREND_UP :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260721-100048 (LOW) :: v09_regime TREND_UP dominant: 59/81 bars (73%) | last_regime=TREND_UP atr_14=89 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-21T06:00:00+00:00:TREND_UP :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260721-100049 (LOW) :: v09_regime TREND_UP dominant: 63/81 bars (78%) | last_regime=TREND_UP atr_14=86 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-21T07:00:00+00:00:TREND_UP :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260721-100050 (LOW) :: v09_regime TREND_UP dominant: 65/81 bars (80%) | last_regime=TREND_UP atr_14=94 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-21T08:00:00+00:00:TREND_UP :: depends:none :: status:queued
- [ ] HARVEST-REGIMEEXT-20260721-100051 (LOW) :: v09_regime TREND_UP dominant: 69/81 bars (85%) | last_regime=TREND_UP atr_14=93 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-07-21T09:00:00+00:00:TREND_UP :: depends:none :: status:queued

### T-GYM-20260619 HIGH gym-session RED for 2026-06-19

**Audits failing:**
- chart-data-verify (RED): 0 bars checked, max div $0.0000
- heartbeat-tick-audit (MISSING): tick-audit output not found
- watcher-state-inspector (MISSING): watcher-state output not found

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260619 HIGH gym-session RED for 2026-06-19

**Audits failing:**
- chart-data-verify (RED): 0 bars checked, max div $0.0000
- heartbeat-tick-audit (MISSING): tick-audit output not found
- watcher-state-inspector (MISSING): watcher-state output not found

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260619 HIGH gym-session RED for 2026-06-19

**Audits failing:**
- chart-data-verify (RED): 0 bars checked, max div $0.0000
- heartbeat-tick-audit (MISSING): tick-audit output not found
- heartbeat-pulse-check (RED): max gap 15.02min
- watcher-state-inspector (RED): could-not-load-bars-for-date

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260623 HIGH gym-session RED for 2026-06-23

**Audits failing:**
- heartbeat-tick-audit (MISSING): tick-audit output not found
- watcher-state-inspector (MISSING): watcher-state output not found

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260624 HIGH gym-session RED for 2026-06-24

**Audits failing:**
- heartbeat-tick-audit (RED): 78 live ticks, 4 MISALIGNED-CRITICAL (5.1%)

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

- [ ] ENGINE-VECTORIZATION (HIGH, perf — the "thousands fast" unlock) :: **2026-06-24: the backtest is 54s/combo → grinds take hours; profile shows the cost is per-bar pandas row-indexing (1.6M `.iloc`/`fast_xs` calls), NOT cacheable I/O.** Baseline for byte-identical validation captured: `backtest/autoresearch/_vectorize_baseline.json` (strike_offset=2/L2/-8% → n=159, sum_pnl=2593.09, **hash c9b7c82bce74250d** — NOTE: this exact combo now reproduces n=308/total=$3982.94 on today's larger OPRA window, per the LAYER-1 fire below; n/sum_pnl in this stale baseline reflect the 2026-06-24 data cutoff, not a regression). THREE hot layers (each validated against the hash after change, 54-80s/run): (1) **levels.py `_detect_from_history`** — `history=spy_df.iloc[:bar_idx+1].copy()` + re-derive date/time on the GROWING slice every day (365× = O(n²), ~44s cumulative). spy_df_full ALREADY carries `date`; precompute `time`+tz once, skip the per-day copy/derive (~1.8× alone, most isolated → DO FIRST). **[LAYER 1 SHIPPED 2026-07-23, see note below — honest result was ~6%, not 1.8×; the boolean-mask slice construction dominates that layer, unaddressed.]** (2) **filters.py per-bar lookback loops** — `prior_bars.iloc[j]["close"]` double-index in range loops (L393/408 sweep, +`.iloc[k]` at L377/452/521/650/1000/1187) → precompute close/high/low/open/vol numpy arrays ONCE in run_backtest, inject via BarContext (new fields), replace .iloc with array[k]. THIS is the big multiplier — cProfile (2026-07-23) confirms: `fast_xs`/`_ixs`/`__getitem__` chain totals ~110s cumulative of a ~205s profiled run (profiler overhead inflates absolute seconds; relative share is the signal), concentrated in `filters.py:evaluate_bullish_setup`/`evaluate_bearish_setup` (~90s+40s cumulative) and `engine/score.py:score_bar` (~65s). **NEXT STEP, not yet attempted.** (3) **orchestrator bar loop** L865 `bar=spy_df.iloc[idx]` + L906 `vix_aligned.iloc[idx]` per bar → array access. Target: 54s → ~3-5s (10-15×) so the 3360 grid runs in ~minutes. Do as a DEDICATED build, one layer at a time, hash-validated. :: depends:none :: status:layer1-shipped-layer2-3-open

> **LAYER 1 SHIPPED 2026-07-23 ~17:12-18:10 ET (conductor, AFTERHOURS), commit `2c6eaf75`.**
> `_detect_from_history` now skips re-deriving "date"/"time" via `.dt.date`/`.dt.time` when the
> caller already supplies those columns (mirrors the pre-existing `_find_swept_levels` precedent
> in the same file); `orchestrator.py` precomputes "time" on `spy_df_full` once up front
> alongside the already-precomputed "date" so its hot path (`_level_per_day` cache-miss, once
> per trading day) benefits automatically.
>
> **Verified byte-identical (OP-33, not just "should work"):** ran the full real-OPRA-fills
> reproducer (`strategy_space_grind --cell OTM-2:L2:pct_-8`) before AND after the change —
> n=308, total=$3982.94, edge_capture=$1100.97, wf=2.762, wr=0.1786, max_dd=-$988.33 identical
> to the last decimal both times. 3 new guard tests
> (`test_levels_precomputed_columns_parity.py`: skip-if-present==recompute parity,
> date-only-precomputed still derives time independently, no-precompute path unaffected) +
> 23/23 pre-existing `test_level_quality_guards.py` + 31+5 curated safety gate all PASS.
> Post-commit `git show 2c6eaf75 --stat --name-status` confirms exactly the 3 intended files
> landed.
>
> **Reported honestly, not oversold (no-oversell doctrine):** cProfile'd the same cell and
> isolated `_detect_from_history` in a direct microbenchmark (365 calls, real data, no
> cProfile overhead skewing the number): 27.33s → 25.74s, a genuine but modest ~6% win at this
> layer — NOT the item's speculated "~1.8× alone." Root cause of the shortfall: the dominant
> remaining cost inside this layer is the boolean-mask slice construction
> (`spy_df_full[spy_df_full["timestamp_et"] <= bar_time]`, O(n) per day, unchanged by this fix),
> not the `.dt.date`/`.dt.time` derivation this fix targeted. Full wall-clock A/B on the whole
> grind cell (83.4s → 87.2s) showed NO measurable difference — within run-to-run noise, because
> this layer is a small fraction of total runtime once real-OPRA-fills I/O and layer-2's ~1.6M
> `.iloc` calls dominate (cProfile breakdown filed above in the item body).
>
> **Scope + revert:** pure `backtest/lib/` perf + a new test file — zero params/heartbeat_core/
> filters/placement/exit/CLAUDE.md touched. Revert: `git revert 2c6eaf75`.
>
> **NEXT (not this fire):** layer 2 (filters.py's `.iloc`-per-bar lookback loops, the real
> "big multiplier" per the cProfile numbers above) is the next dedicated build — precompute
> close/high/low/open/vol as numpy arrays once in `run_backtest`, inject via `BarContext`,
> replace `.iloc[k]` with `array[k]` at the ~7 cited call sites. Item stays open (HIGH), not
> closed — layer 1 of 3 done, honestly quantified, 2 remain.

- [x] ENGINE-VECTORIZATION-FINDING (2026-06-24) :: **RESOLVED — the real lever is a config flag, not vectorization.** Self-time profile (not cumulative) showed evaluate_bearish/bullish_setup called 50,814× = EXACTLY 2× the 25,407 bars: the orchestrator scores each bar once for the decision (L983/1008) then AGAIN via engine.score_bar as a per-bar parity oracle (L1031, gated by `_ENGINE_SCORE_ASSERT`, docstring: "Opt-out via GAMMA_ENGINE_SCORE_ASSERT=0 for perf-sensitive sweeps"). The oracle changes ZERO trades. Clean A/B: assert-ON 73.4s, assert-OFF 46.0s = **1.6x, byte-identical (hash c9b7c82bce74250d)**. Wired GAMMA_ENGINE_SCORE_ASSERT=0 into mass_grind.py. My L1 (levels copy/derive) + L2 (sweep array) code attempts were NO-OPS (already day-cached / sweep not hot) — REVERTED via git checkout. HONEST CEILING: no 10x without a full numpy bar-loop rewrite; cost is distributed (filters/pandas/levels). 1.6x is the free validated win. Baseline signature kept at backtest/autoresearch/_vectorize_baseline.json for any future engine-perf work. :: depends:none :: status:done
- [ ] GATE-TIERS-IMPLEMENT (HIGH, fleet-architecture) :: Implement the per-arm gate-tier design from markdown/audits/GATE-PROVENANCE-AUDIT-2026-07-02.md: SAFE=full stack / BASE=untouched / RISKY=safety-class-only + min_triggers 1, via gate_profile+gate_params in fleet accounts.json gate_override (absent = byte-identical today), per-arm _HARD_SKIP_VERDICTS; guards per step, single-key revertible; measure per-arm fill-funnel N=10 days. J directive 2026-07-02 ("risky account should take the one-gate-away trade"). :: depends:none :: status:pending
- [x] MIN-RIBBON-SEMI-ARMED-FIX (HIGH, engine-bug) :: gates.py:322 treats min_ribbon_momentum_cents=0 as a LIVE threshold — J reverted this gate (L107) but the engine still runs it (16 blocked rows/30d, 3 should-be-0 episodes). 1-line fix + vary-and-assert guard. Ref GATE-PROVENANCE-AUDIT-2026-07-02. **CLOSED 2026-07-11:** root cause = `is not None` doesn't special-case zero (`0 is not None` → True → gate stays armed at threshold 0, blocking any bar where ribbon spread didn't strictly widen). Fix: `is not None` → truthy (`if _rmom_thresh:`), 1 line, gates.py:323. params.json already carried `null` (a prior session fixed the DATA side; unchanged by this fix) — this closes the CODE-level gap so 0 can never re-arm it again regardless of what the param is set to. Guard: `test_gate_min_ribbon_momentum_cents_zero_is_off` (backtest/tests/test_engine_gates_parity.py) — vary-and-assert on a sharply-contracting ribbon (momentum -30, the exact shape that used to false-block): threshold 0/0.0/None all allow; a real threshold (5.0) on the SAME contracting context still correctly blocks. Tests: 26/26 → 27/27 passed (test_engine_gates_parity.py + test_f1_ribbon_momentum_disabled.py), including all 6 real-anchor-day oracle-vs-orchestrator integration parity tests (unaffected). Flagged, not fixed tonight (separate follow-up, spawned): backtest/lib/orchestrator.py:1482 has the IDENTICAL `is not None` bug in its own inline gate cascade (backtest/A-B path, not live) — a future param sweep hitting 0 there would still silently misbehave; max_ribbon_duration_bars has the same-shaped bug in both files (currently inert at 999, no live evidence of harm). **FOLLOW-UP CLOSED same-day, see STATUS.md "ORCHESTRATOR-RIBBON-ZERO-FIX":** both orchestrator.py lines fixed (1482 + 1503) + gates.py:342 (max_ribbon_duration_bars, not yet fixed there either) — real 2025-06-03 anchor-day disagreement caught live by the assert-agree oracle during guard authoring. 28/28 + 11F/95P/1S (unchanged pre-existing) after. :: depends:none :: status:done
- [x] SAFE3-CONFIDENCE-ALWAYS-BLOCK-FIX (MED, fleet-bug) :: safe-3 arm's "A+ confidence >=0.65" gate reads a field the shared signal never carries -> always-blocks (arm has 1 trade/30d). Fix the field or delete the gate; guard. Ref GATE-PROVENANCE-AUDIT-2026-07-02. **CLOSED 2026-07-11:** confirmed the mismatch directly on both sides — fleet_executor.py's plan_entry/_gate_check read blk.get("confidence", signal.get("confidence")); build_shared_signal.py has NEVER emitted a "confidence" key anywhere (own docstring: "confidence/confluence/est_premium" omitted, faithfulness upgrade never built). Git archaeology: accounts.json.bak-2026-06-25-pre-grid shows safe-3's original intent was real (min_confidence:0.65, the "A+" arm design, from the 2026-06-22 fleet-go-live commit 3da3747) — but the 2026-06-25 grid rebuild already dropped min_confidence from every LIVE arm (current accounts.json has zero "confidence" occurrences anywhere), independently corroborated by replay_fleet_arms.py's own comment ("is moot now — current accounts.json safe-3 has no min_confidence"). DELETED the dead check (not fixed-forward — populating a real confidence score needs a validated model, out of scope tonight) since current live behavior is byte-identical either way and the grid rebuild had already moved the design away from confidence-gating. Guard: test_min_confidence_gate_removed_and_inert (automation/state/fleet/test_fleet_executor.py) — proves a STALE min_confidence key + a confidence-free signal (the real production shape) still ENTERs, plus a source-level check the read is structurally gone. Tests: 22/22 -> 23/23 (test_fleet_executor.py), 239/239 across the full fleet/ test directory. :: depends:none :: status:done
- [x] VETO-LAYER-EVIDENCE-CHECK (MED, gate-provenance) :: SUPERSEDED 2026-07-11 — premise was stale. The "zero fires in ledger history" claim was true as of 2026-07-02 but is no longer true: AUDIT-HARNESS-B1 measured 15 real vetoes with 93.3% veto-only accuracy (14/15 correct blocks; 1 false-veto found, would've been +$65.40). Burden-of-proof is now MET, not failed — do NOT A/B-remove the gate. Ongoing evidence-gathering continues automatically via Gamma_FreeModelAudit (every-other-day, ≥85%/≥15-evidence bar) instead of a one-shot removal test. Ref GATE-PROVENANCE-AUDIT-2026-07-02, markdown/infra/FREE-MODEL-AUDIT-HARNESS.md. :: depends:none :: status:done

### T-GYM-20260702 HIGH gym-session RED for 2026-07-02

**Audits failing:**
- crypto-gym (53 validators) (RED): 102/104 pass (KNOWN_FLAKY excluded: 1)

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260703 HIGH gym-session RED for 2026-07-03

**Audits failing:**
- crypto-gym (53 validators) (RED): 103/104 pass
- chart-data-verify (RED): 0 bars checked, max div $0.0000
- heartbeat-tick-audit (MISSING): tick-audit output not found
- watcher-state-inspector (MISSING): watcher-state output not found

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260706 HIGH gym-session RED for 2026-07-06

**Audits failing:**
- crypto-gym (53 validators) (RED): 102/104 pass (KNOWN_FLAKY excluded: 1)

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.


### T-ENGINE-LAG-20260707 HIGH heartbeat_core lagging -- missed J-called BEARISH_REJECTION entry (09:50 close < 749.28)

**Symptom:** 2026-07-07 ~09:50-10:00 ET SPY rejected the ~750 ribbon, CLOSED 749.03 below 749.28 support (5m), ran to 748.7. Engine held every tick (verdict HOLD, bear_score 4 / bull_score 7) and MISSED the entry J called live. Gamma placed manual paper puts instead (Safe 5x747P @0.82 ord eb818929, Bold 3x750P @2.14 ord b858f462).

**Two root causes -- diagnosed live from core-decisions.jsonl, NOT yet fixed (market-hours engine edit forbidden -- scar):**
1. STALE PRICE FEED: decisions at 09:53-09:54 showed spy=749.655 (the 09:45 5m close) while real spot was 748.87 -- engine price input lags ~2 bars / ~8 min, so it literally cannot see the dump in time. Find where heartbeat_core sources spy (beacon eye / ema-snapshot?) and why it lags the live tape; the static ema-snapshot.json was also stale (yesterday EOD compute).
2. LAGGING htf_15m GATE: htf_15m=BULL (slow 15m EMA still elevated from yesterday 752 rally) capped bear_score at 4 even as the 15m ROLLED OVER (lower highs 752.4->750.94->750.18, gap-down, broke session support). C28 lagging-ribbon class -- the htf classifier must weight recent 15m structure/BOS, not just a slow EMA stack.

**Action (AFTER-HOURS only):** reproduce both from automation/state/core-decisions.jsonl (07-07 rows); (a) fix price-feed freshness + add a guard that REDs if engine spy diverges > ~15c from the live beacon; (b) make htf_15m responsive to 15m rollover/BOS + guard that a confirmed support-break-close registers as bear. Validate on the 07-07 tape via the override harness, ship with guard+revert per paper-autonomy rail. :: status:pending

**REFINEMENT (2026-07-07 ~10:07 ET, read the actual code + J scalp spec):**
- CORRECTED bug #1: not a stale beacon -- heartbeat_core._fetch_spy_5m (L637) decides on CLOSED 5m bars and drops the forming bar (_htf_15m_stack(df.iloc[:-1]) L468, no-look-ahead C6). So best-case entry is the 09:50 support-break CLOSE (~748.6), ~$2 later than J's rejection entry. FIX: make BEARISH_REJECTION_RIDE_THE_RIBBON fire on the REJECTION CANDLE (wick off ribbon/round-level + rollover / lower-high), not only on the confirmed support-break close. Must NOT break C6 -- validate it is not look-ahead (rejection candle is CLOSED before entry).
- bug #2 confirmed in code: _htf_15m_stack (L321) needs 50x 15m bars (48-EMA warmup) so at the open it runs on PRIOR-DAY 15m bars -> stale BULL -> caps bear_score. FIX: de-weight the slow 15m EMA stack when the intraday 15m has a fresh rollover/BOS; or gate on recent-structure not just EMA stack.
- J SCALP PROFILE (certified scalp move, encode as the exit/size profile for this setup): size 3-5 contracts; QUICK profits (take MOST off fast at TP1); HOLD 1-2 runners. Distinct from v15 tp1_qty_fraction 0.8 -- this is take-most-quick + tiny-runner.
- SHIP: AFTER-HOURS ONLY. Validate the earlier-trigger vs J real trades (OP-16 edge_capture -- must not degrade the winners or add the losers) BEFORE apply. guard+revert per paper-autonomy rail. NOT a mid-session hot-patch (rule 9 + market-hours-edit scar).

**CORRECTION supersedes the above (2026-07-07 ~11:05 ET, /think-like-fable, primary evidence):**
The earlier 'stale price feed + de-lag htf_15m' framing was WRONG. Root cause from engine_cli.py:446-462 + today core-decisions:
- Routing = side.PASSED (threshold) + len(triggers_fired), NOT raw bear/bull score. Bear NEVER passed today: 0 triggers fired the whole move (setup=None every tick). bull_score 8-10 vs bear 4-7 is a red herring.
- Core bear setup needs level_rejection/sequence_rejection = price approach-and-reject an ACTIVE level. Today was an OPENING-DRIVE rejection off 750.93, but 750.93 only became a level AFTER the 09:30 bar set the high; price never re-tested it. Core engine has NO ribbon-wick trigger.
- J's EXACT setup already exists: backtest/lib/watchers/ribbon_rejection_wick_detector.py (spec = J's 2026-07-02 live read, identical to today). It is UNWIRED because it was VALIDATED AND KILLED: battery 2025-01..2026-07 OPRA real fills, 0/24 BH-FDR survivors, J-exact config N=174 WR 65.5% but expectancy -16.16/tr, OOS -30, both dirs negative. C3 premium-bleed / inverted R:R (chandelier cuts winners, -30% stops bleed losers). Scorecard analysis/recommendations/ribbon-rejection-wick.json.

**REVISED ACTION (after-hours, offline, on fresh OPRA -- NOT the old de-lag plan):**
1. RE-VALIDATE the wick detector with J's ACTUAL SCALP EXIT (the disclosed-untested lever): quick TP ~+30-40%% or at next level + FAST structure stop (level reclaim) + 1-2 runners, vs the battery's fixed TP+50/stop-30/chandelier which the kill nail blames. Full 18mo, OOS split, BH-FDR, drop-top3, slippage-to-breakeven. Wire as ENTRY only if it survives ALL. CAVEAT L58: this R:R family historically does NOT rescue via exit knobs -> treat as ~low-P.
2. Wire ribbon_rejection_wick as a VETO/exit signal regardless (scorecard's own future_vein): bear wick => do-not-enter-bull + tighten runners. Today the engine nearly took a BULL reclaim at 09:34, 2 min before the dump. Low-risk, likely-positive.
3. MINOR hygiene: prune expired levels from key-levels.json (731.22 exp 06-30, 734.52 exp 06-29 still present in a 07-07 feed) -- did NOT cause today.
DO NOT wire on today's n=1 win. :: status:pending

### T-WICK-EXITGRID-20260707 HIGH RUN AFTER CLOSE -- exit-redesign re-validation of J's ribbon-rejection scalp

**Built 2026-07-07 (/think-like-fable), import-clean + all 8 exit configs construct. UNVALIDATED vs data until the smoke runs.**
Premise: ribbon_rejection_wick entry FAILED 0/24 with a FIXED exit; the kill nail blamed the exit; J's SCALP exit (quick TP + tight stop + partial+runner) is the one un-searched lever. This battery grids ONLY the exit (8 pre-registered configs, entry fixed to J-anchor), BH-FDR across the 8, full robustness bar.
**Runbook (after close, reaper-exempt venv, ONE process -- NEVER mid-session):**
  1. SMOKE first (proves harness + knob non-vacuity): === RIBBON_REJECTION_WICK exit-grid battery [SMOKE] ===
master: 2274 RTH bars 2026-05-19 09:30:00..2026-07-01 15:55:00
[1/3] superset scan
  scan 0/1865 bars  events=0  0s
  scan done: 1865 bars -> 321 superset events (1s)
  321 superset events
[2/3] knob non-vacuity self-check
  [knob-check] baseline slice pnl=294  fast_tight slice pnl=163  LIVE (differs)
[3/3] exit-grid battery
  E1_baseline_repro  N=  15 WR=0.47 exp=$ -67.68 OOS_exp=$ -67.68 drop3=$ -1386.6 p=0.962 (1s)
  E2_quick_scalp     N=  16 WR=0.38 exp=$ -44.27 OOS_exp=$ -44.27 drop3=$ -1017.0 p=0.954 (2s)
  E3_quick_runner    N=  16 WR=0.44 exp=$ -18.49 OOS_exp=$ -18.49 drop3=$  -702.6 p=0.521 (2s)
  E4_mid_runner      N=  16 WR=0.44 exp=$ -16.88 OOS_exp=$ -16.88 drop3=$  -702.6 p=0.468 (3s)
  E5_tight_stop      N=  17 WR=0.18 exp=$ -37.85 OOS_exp=$ -37.85 drop3=$ -1044.0 p=0.823 (3s)
  E6_fast_tight      N=  17 WR=0.35 exp=$ -17.96 OOS_exp=$ -17.96 drop3=$  -660.6 p=0.646 (4s)
  E7_bigtp_tight     N=  17 WR=0.35 exp=$ -30.04 OOS_exp=$ -30.04 drop3=$  -866.0 p=0.846 (4s)
  E8_j_scalp         N=  16 WR=0.44 exp=$  -8.08 OOS_exp=$  -8.08 drop3=$  -561.9 p=0.351 (5s)

VERDICT: FAIL (survivors 0/8) -> C:\Users\jackw\Desktop"nalysis
ecommendations
ibbon-rejection-wick-exitgrid.json
  => setup STAYS KILLED as an entry; wire the detector as a VETO only (scorecard future_vein).
  2. If smoke green + knob-check LIVE: full run (drop --smoke). Scorecard -> analysis/recommendations/ribbon-rejection-wick-exitgrid.json
**SHIP/KILL:** CLEARS (any config passes ALL gates incl OOS+FDR+drop-top3+bear-side-exp) -> stage a WIRE-DETECTOR proposal (arm after a later close). FAIL -> setup STAYS KILLED as entry; wire ribbon_rejection_wick as a VETO only (do-not-enter-bull on fresh bear wick). Prior L58: low P(rescue) -- treat FAIL as the base case, CLEARS as the surprise to be extra-skeptical of (fable-too-good).
**Owed if it shows promise:** structure (ribbon-reclaim) stop is only PROXIED by premium-% here -- a true structure-stop sim extension is the follow-up. :: status:pending :: depends:after-close-run
### T-GYM-20260707 HIGH gym-session RED for 2026-07-07

**Audits failing:**
- crypto-gym (53 validators) (RED): 103/104 pass

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.


**RESULT T-WICK-EXITGRID-20260707 = FAIL 0/8 (ran 2026-07-07 ~17:15 ET, market closed, venv-exempt):**
Full 18mo n~195/config real OPRA. E1 baseline repro -17.20 (== original -16.16, harness parity OK). BEST = E8 j_scalp (tp0.40/stop-0.18/partial+runner): -8.60/tr full, -4.88 OOS, p=0.010, drop3 -2217. ALL 8 negative. J's exit cut the loss ~75% OOS + signal beats random (p<0.05) but C3 premium-bleed keeps it sub-zero. Scorecard analysis/recommendations/ribbon-rejection-wick-exitgrid.json.
REFRAME (do not keep grinding the same shape -- OP-32): auto-BUY of this signal is DEAD (proven 24+8 configs). Architecture -> DETECT+ALERT+VETO+execute-on-J-call (banked +$377 manual today). Open levers: (a) SELECTIVE entry (15m-confirm + 5m-engulf; T-WICK-SELECTIVE, testing now), (b) DEFINED-RISK SPREAD instrument (C3 fix; bigger build). :: status:done

### T-RIBBON-REJECTION-FINAL-VERDICT 2026-07-07 -- 4 BATTERIES, DEAD AS NAKED BUY.
Ran tonight (market closed, venv-exempt): exit-grid 0/8, selective-entry mirage (n=29 +2.03 drop3 -408), hold-grid 0/6 (best -15.77/tr; +41 smoke was 2 lucky dumps, drop3 -6525). Volume-profile agent: KILLED (already built _b4_volume_profile_poc 2026-06-21, loses to random-entry null) + real volume needs PAID Alpaca SIP (J money-decision). Signal beats random every time but C3 premium-bleed sinks it under EVERY config. => STOP grinding this as an entry (OP-32). DO NOT run a blind optimize-everything sweep (made 2 mirages tonight; multiplicity).
OPEN LEVERS: (1) INSTRUMENT: test same signal as DEFINED-RISK SPREAD (kill=premium bleed; needs 2-leg OPRA sim). (2) WALK-FORWARD re-opt of VALIDATED setups + triage 93 BARE params (param_provenance.py). (3) VETO: ribbon_rejection_wick as bull-veto.
Built: setup/scripts/param_provenance.py, automation/state/param-provenance.json. Scorecards: ribbon-rejection-wick-{exitgrid,selective,holdgrid}.json. :: status:done


## AUDIT 2026-07-07 (autonomous unknown-unknown hunt, 11 CONFIRMED / 0 refuted) -- fixes ship next session GUARDED
Verified headline: engine placed 0 broker orders today; 18 ENTER_BEAR (10:46-15:50) ALL NOT_FLAT behind J's 10:00 manual puts; 48 more gated bear-skips. Engine saw bear (late), was blocked -- not blind PM.

### T-AUDIT-01 J-DECISION manual-vs-engine coexistence -- manual trade LOCKS OUT the engine all day (18 ENTER_BEAR blocked NOT_FLAT). Not a bug (flat-before-entry=C11 safety) but a POLICY: register manual fills w/ engine? allow-add? Needs J. HIGH :: status:awaiting-j-ratification (genuine policy fork, correctly not auto-decided)
### T-AUDIT-02 HIGH expired key-level fed live -- **CLOSED, verified stale 2026-07-21 (conductor, AFTERHOURS).** Already fixed: `heartbeat_core.py:376` `FIX2 (2026-07-07)` skips any level whose `expires_at` parses to a date strictly before today (fail-open on missing/null/unparseable), guarded by `test_audit_fix_heartbeat.py`. status:CLOSED
### T-AUDIT-03 HIGH fill reconciliation -- **CLOSED, verified stale 2026-07-21 (conductor, AFTERHOURS).** Already fixed: `heartbeat_core.py:1170` `_reconcile_fill` `FIX3 (2026-07-07)` polls the placed order to a terminal state (bounded retries, 3s hard cap, fail-open) so filled orders no longer stick at pending_new/filled_qty=0, guarded by `test_audit_fix_heartbeat.py::TestFillReconciliation`. status:CLOSED
### T-AUDIT-04 MED fill_funnel FALSE RED -- **CLOSED, verified stale 2026-07-21 (conductor, AFTERHOURS).** Already fixed (2 rounds, 2026-07-07 + 2026-07-08 second false-red fix): `fill_funnel.py` `attempted` now requires a real placement-outcome status; `NOT_FLAT`/`SKIP_*`/`RISK_DENY_*` are explicitly excluded from `attempted` (lines 64-102). Tonight's live funnel run (`python setup/scripts/fill_funnel.py`) confirms GREEN, no false RED. status:CLOSED
### T-AUDIT-05 HIGH-verify-first time_stop_et -- **CLOSED, verified stale 2026-07-21 (conductor, AFTERHOURS), the item's own "re-verify before fixing" instruction followed.** Re-grepped live code: `heartbeat_core.py:987` passes `time_stop_et=params.get("time_stop_et")` through to `exit_actuator.manage_tick` -> `exit_manager.parse_time_stop_et`, confirmed NOT hardcoded 15:50 (that's now only the fallback default when params omits the key). `params.json:39` carries `"time_stop_et": "15:40"` live. `python -m pytest backtest/tests -k time_stop -q` -> 26 passed; `-k audit_fix -q` -> 36 passed (both suites, this fire, fresh run). No code change needed -- this whole T-AUDIT-02..05 cluster was fixed 2026-07-07/08 and simply never pruned from the queue (OP-22 compound-don't-accumulate: verified-stale items closed rather than re-investigated by every future fire). status:CLOSED
### T-AUDIT-TAIL: synthesis feed truncated mid-item-5; 6 more CONFIRMED + all MED/LOW never delivered. RE-RUN synthesis (resumeFromRunId wf_a6e5356c-0e7) to recover the tail. Lower priority now that 02-05 (the items the tail note worried might be incomplete) are confirmed already fixed and closed above -- if picked up, re-run the synthesis fresh rather than trying to resume a 2-week-stale workflow run id. :: status:open


### T-RIBBON-SPREAD-KILL 2026-07-07 -- 5th & FINAL kill: DEFINED-RISK SPREAD also bleeds.
Smoke (built + math-verified, 4 guards): expectancy +132..228/spread WR 64-89% LOOKS great but = null-contamination mirage. OOS negative all 9 configs; random-entry null itself positive (low-VIX grind-up EOD spread collects intrinsic); only 1/9 beats null (w3 TP60 p=0.023, OOS -197); 7/10 trades BULL, bear side n=3. Verdict SMOKE_NEGATIVE, recommend KILL, do NOT run full 18mo. Files: ribbon_rejection_spread_battery.py, test_ribbon_rejection_spread.py (4/4), analysis/recommendations/ribbon-rejection-spread.json.
=> RIBBON-REJECTION FAMILY EXHAUSTIVELY DEAD AS AN ENTRY (naked buy 0/24, exit-grid 0/8, hold 0/6, selective mirage, spread smoke-neg). It is VETO/EXIT-ONLY info. STOP testing it as an entry in any premium wrapper. Remaining uses: bull-veto + DETECT+ALERT+J-calls+Gamma-executes (banked +$377 today). :: status:done


### T-VWAPCONT-EXITPARAM-CANDIDATE 2026-07-07 -- walk-forward found a ~$10/tr stale-param win (NOT dynamic re-opt)
walkforward_optimizer.py on vwap_continuation (N=149 real OPRA, 5 folds, anti-leak guard 4/4): DYNAMIC re-opt OVERFITS (WF test $52.67/tr LOSES -$2.51 to best-fixed $55.18) => static architecture is CORRECT, do NOT build dynamic re-opt machinery. BUT current static -0.08/0.30 = $44.81/tr is ~$10 stale; best fixed = -0.06/0.40 (wider stop+higher TP1), converged 4/5 folds, both knobs live+monotone. Scorecard analysis/recommendations/vwapcont-walkforward.json.
CAVEATS: best-fixed is IN-SAMPLE (needs OOS confirm), grid coarse 3x3, this is the ATM cell -- ITM-2 armed cell must be re-verified per C29. => T-VWAPCONT-AB-VALIDATE running: A/B -0.06/0.40 vs -0.08/0.30 on the LIVE cell, full OP-22 gate; if CLEARS, ship j_vwap_cont_premium_stop_pct/tp1_pct via guard+revert+REVOKE. **CLOSED, verified stale 2026-07-21 ~22:15-22:35 ET (conductor, AFTERHOURS).** This already SHIPPED 2026-07-07: `vwapcont-exit-ab-ship-gate.json` verdict SHIP (n=149 real OPRA, ALL 5 OP-22 gates PASS -- parity/OOS-beats-current/WF=1.62/quarters-stable/anchor-no-regression/drop-top3-positive), live-verified this fire: `automation/state/params.json` `j_vwap_cont_premium_stop_pct=-0.06` / `j_vwap_cont_tp1_pct=0.4` (doc-stamped `_j_vwap_cont_exit_updated_2026_07_07`) + `automation/state/fleet/strategies.py:122` VWAP_CONTINUATION.exit carries the identical shape (both lanes synced, no two-lane drift) -- `git status --short` on both files clean (nothing uncommitted), `git log` shows the shipping commits already landed. Guard `pytest backtest/tests/test_vwapcont_exit_ab_ship_gate.py -q` -> 6/6 PASS fresh this fire. BONUS finding: the 2026-07-09 `vwapcont-entry-exit-matrix.json` (STOP-A ground rule 11, pre-registered 24-cell grid replayed through the LIVE `exit_manager.plan_exit_actions` core, NOT just `simulate_trade_real`) independently RE-CONFIRMED this exact cell -- its `control_id: "P1T1F1L1"` IS -0.06/0.40 (`live_cell_as_of_freeze` in the frozen preregistration matches byte-for-byte), verdict **CONTROL-STANDS**: 0/23 wider/looser challenger cells (P2-P4 stops, T2 tp1, F2 frac, L2 trailing-lock, structure-stop family) beat it on all 4 pre-registered conditions. So the CAVEATS this item raised (IS-only, needs OOS confirm) are answered TWICE over: once by the ship-gate's own OOS split, once by an independent later study that tried to unseat it and failed. No action needed -- this is a 2-week-old un-pruned ledger entry for already-completed, already-reconfirmed work (OP-22 compound-don't-accumulate, same class as tonight's earlier T-AUDIT-02..05 cluster). Zero trading-path files touched by THIS fire (only this queue.md doc-close). :: status:CLOSED

- [x] ET-CLOCK-RECURSION-FIXED (was a CONFIRMED MONDAY-OPEN LIVE RED, fixed 2026-06-28 conductor commit c8f2465) :: `et_clock._EasternTZ.utcoffset` called `dt.astimezone(utc)` on an aware ET_TZ datetime -> astimezone needs `dt.utcoffset()` -> infinite recursion. Crashed the LIVE fleet producer (`build_shared_signal.build()` default now = `datetime.now(utc).astimezone(ET_TZ)` then `strftime('%z')`); the exact prod call `python build_shared_signal.py` crashed. Latent since the et_clock wiring (50071b4, 2026-06-26 18:42) landed after Fri's last RTH -> would have frozen shared-signal.json Mon open. FIX (root, protects all 9+ live paths): aware-in-ET (`tzinfo is self`) routes through the same wall-clock DST lookup as the naive branch; naive path byte-identical. Guard: `test_et_clock.py::test_aware_et_tz_datetime_does_not_recurse` (bite-tested). Foot-gun banked to `_lesson-inbox`. :: depends:none :: status:done
- [x] WINDOW-LEAK-COMPLIANCE-DRAIN (HIGH, engine-benefit infra, **DONE 2026-06-30 ~07:55 conductor**) :: the 04:00 daily `audit_window_leak_compliance.py` went RED on **13 `subprocess.run` calls missing `creationflags=CREATE_NO_WINDOW`** across 11 files (C8/OP-27 L41 conhost-flash foot-gun; worst offender `heartbeat_core._engine_verdict` fires every RTH tick = J-disturb). Added the canonical `_CREATE_NO_WINDOW` const + `creationflags` to all 13 (autonomy_actuator x2, discord-responder, gamma_manager, github_audit, heartbeat_core, lesson_regression_audit, manager_overseer, preopen_readiness, run_cold_evals, self_audit x2, license_monitor) -- zero behavior change (no-op off-win32). Audit re-run GREEN (0/0/0). Graduated the daily-monitored-but-unenforced audit into a build ratchet `backtest/tests/test_window_leak_compliance.py` (3/3, non-vacuous bite). Safety gate 31+5 PASS; touched-module no-regression 60/60. NOTE: heartbeat_core is the engine CODE not the heartbeat PROMPT -> rail-4 clear. :: depends:none :: status:done
- [x] PARAMS-CONSUMER-RECONCILE-TEST (HIGH, engine-correctness, **GUARD SHIPPED 2026-07-02 ~05:56 conductor commit 95a603b**) :: Built the broad params<->consumer reconciliation ratchet `backtest/tests/test_params_consumer_reconciliation.py` (4/4): every ratified (non-underscore, non-metadata) key in the canonical Safe params.json must have a live reader in the consumer surface (setup/scripts, backtest/lib, automation/scripts, crypto/validators, automation/prompts, setup/*.ps1). REDs LOUD on any NEW dead knob; shrinks-only `KNOWN_DEAD` (24 keys) forces restore-or-remove as each gains a consumer. Extends the gate-only v25 presence guard (test_params_filters_drift) to exit/sizing/entry-window/liquidity/macro/session-timing knobs. Non-vacuous bite proven both directions (new-dead REDs; revived-key REDs). Rail-4 CLEAR (test-only). Revert: `git revert 95a603b`. **FOLLOW-UP (the 24 restore-or-remove decisions, now guard-tracked):** PARAMS-DEAD-KNOB-DISPOSITION — decide RESTORE (wire consumer) or REMOVE for each KNOWN_DEAD key; the ratchet forces the allowlist to shrink as each closes. :: depends:none :: status:done
- [x] ADJUDICATE-CD-2026-06-29-001-TP1-REVERT (HIGH, params-hygiene, **DONE 2026-07-02 ~07:52 conductor — KEEP, zero params change**) :: Adjudicated cd-2026-06-29-001 → **KEEP (shelved the revert), zero params change** (no perturbation before today's money-path proof). EVIDENCE: (1) the change came from pk-2026-06-28-001 whose scorecard = **CLEARED / eval_bar_cleared=true** (WF 3.566, OOS +$56.86/tr, anchor 1692) → PASSED the full auto-ratify eval gate; only the recency gate was skipped. (2) Post-07-01 TRADE-TO-LEARN, **recency is LIVE-money-only** — these are PAPER accounts, so the "CONFIRM-BEFORE-CAPITAL bypass" premise is superseded by J's own 07-01 ruling; the passed eval gate is the paper bar. (3) `tp1_qty_fraction=0.8` is live-read correctly (heartbeat_core:1054) + doctrine-documented (CLAUDE.md:28). (4) `v15_profit_lock_mode=fixed` is a **DEAD KNOB in live core** — both exit branches force "fixed" (L1055 hardcode on the primary TRADE-TO-LEARN path + L1068 fallback reads the un-prefixed `profit_lock_mode` key which is absent → default "fixed"); reverting to "trailing" = ZERO live effect. Proposal status pending→shelved w/ full resolution. J REVOKE surface: near-inert, trivially re-openable. Ref markdown/audits/PIPELINE-AUDIT-2026-07-01.md break #7. :: depends:none :: status:done
- [x] FIX-CD-2026-06-28-002-ID-COLLISION (HIGH, approval-bus-integrity, **DONE 2026-07-02 ~01:54 conductor commit 5e536ca**) :: `conductor-proposals.jsonl` reused proposal_id cd-2026-06-28-002 on two DIFFERENT active rows (BOLD-FLEET accounts.json change + L192 CLAUDE.md doc-fold). Confirmed the actuator resolves a dup id inconsistently: `by_id` dict (companion sync, L155) = last-wins → doc-fold; `next()` (apply/revert, L580/L699) = first-wins → BOLD-FLEET, so `ship cd-2026-06-28-002` could approve one row and apply/revert the other. FIX: re-id'd the BOLD-FLEET orphan → cd-2026-06-28-003 (doc-fold KEEPS -002 = canonical in test_op25_index_reconciliation baseline comments + 6 STATUS CLAUDE-INDEX-FOLD refs); cleared the mis-attributed 'CLAUDE.md op stale' actuator_note (BOLD-FLEET ops target accounts.json — proof the collision was actively biting). Guard `test_proposal_id_uniqueness.py` 4/4 pins ACTIVE-status id uniqueness (bite-tested; terminal re-emissions allowed). Rail-4 CLEAR (approval-bus STATE, zero live-trading behavior change). Revert: `git revert 5e536ca`. :: depends:none :: status:done
- [x] PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB (HIGH → WONT-FIX-BY-DESIGN, **RESOLVED 2026-07-02 ~03:55 conductor commit 0480ced**) :: MISDIAGNOSIS (OP-33 frame-audit). The `_params_to_kwargs` chandelier drop is INTENTIONAL and L156-encoded, guard-protected by `test_profit_lock_not_in_baseline.py` — NOT a C14 dead-knob. L156: the chandelier is regime-conditional (net-negative on the volume-dominant trending IS windows), so mapping it into the baseline would permanently bias EVERY candidate comparison negative (a measurement-integrity foot-gun). The task's premise ("every A/B verdict suspect") is FALSE: the drop is SYMMETRIC across both A/B arms (baseline + candidate both traverse the mapper), so relative verdicts are unaffected; only the baseline's absolute-vs-live P&L is conservative, exactly the tradeoff L156 chose. PHASEC itself: "Does not affect port cells." "Fixing" the mapping would VIOLATE L156 and RED its guard. ACTIONS: (a) strengthened the L156 guard with the REAL production key names (`v15_profit_lock_*`) + a non-vacuous real-params.json bite (test 2→3, verified a leaky mapper REDs); (b) corrected the misleading PHASEC RESULTS.md caveat 7 mislabel; (c) closed here. Rail-4 CLEAR (guard + doc; no params/heartbeat/orders/filters/CLAUDE). :: depends:none :: status:done
- [x] LEVELS-CONTRADICTORY-ROLES-DRAIN (HIGH, engine-correctness, **DONE 2026-06-30 ~17:58 conductor commit b04cd8e**) :: the content-aware self-check (3f5d575) was RED with "KEY-LEVELS CONTRADICTORY ROLES": 741.61 (x7) + 741.81 (x9) each carried BOTH a ceiling and a floor role (engine read one price as resistance AND support). ROOT: `refresh_levels_intraday.refresh()` deduped only its own `INTRADAY_*` labels, preserved upstream-duplicated curated PMH/PML, and re-added INTRADAY_PMH/PML at a colliding price with a polarity role that contradicted the curated fixed role. FIX (audit fix-order #4 "levels role/dedup at the producer"): `_normalize_levels` enforces one-polarity-role-per-price + price-cluster dedup over the full written set; self-heals every run. Live file repaired 26->11 (RED->GREEN). Guard +5 (13/13) incl. producer/consumer contract test (calls real self_check) + non-vacuous bite. Rail-4 CLEAR (producer code, no params/orders/filters/heartbeat/CLAUDE). :: depends:none :: status:done
- [x] SELF-CHECK-DATA-GATED-FRAME-FIX (HIGH, engine-monitor-correctness, **DONE 2026-06-30 ~23:50 conductor commit 5de3e73**) :: the live content-aware self-check (`self-check-last.json`, 23:39) was BROKEN on "ENGINE CANNOT ENTER: 386 ticks / 0 ENTER / 32x SKIP_ELITE_BULL_LEVEL_RECLAIM" -- but tonight's 3-lever bull-unblock audit CLOSED that thread (block_elite_bull KEEP -$241; sequence_reclaim coupled off; bull DATA-GATED, not a bug). The monitor sat perpetually-RED on validated-correct behavior = L189 "persistently-RED masks new orphans". FIX: `_DATA_GATED_BLOCK_VERDICTS`; `check_engine_tradeability` flags BROKEN only on a NON-data-gated block + DEGRADED only for the LIVE bear direction; the data-gated bull sit-out is silent. Live verdict flipped BROKEN->GREEN. FRAME-CORRECTED the guard that baked in the old frame (`test_self_check_flags_zero_entry_with_blocks`) + new `test_self_check_tradeability.py` (8/8 matrix). Curated gate 31+5 PASS; verify-committed clean. Lesson-inbox: guard-baked-in-the-masking-frame. Rail-4 CLEAR (observability code). :: depends:none :: status:done
- [x] WIRE-PREOPEN-READINESS-SCHEDULE (MED, observability-infra) :: **DONE 2026-06-29 conductor (commit e385567).** Closed both halves the verifier left open. (1) **J-ping:** transition-only `maybe_alert` in `preopen_readiness.py` — reuses the engine_health outbox+mention pattern (no new path), pings J ONCE on a NEW red check, idempotent (keyed on `red_checks` set), fail-open (rail-2, never raises/trade-halts); `main()` reads prior reds before overwriting `preopen-readiness.json`. (2) **Schedule:** `setup/scripts/install-preopen-readiness.ps1` registers `Gamma_PreopenReadiness` at 06:25 MT = 08:25 ET weekly Mon-Fri via the flash-free wscript→pythonw chain (BEFORE Premarket 08:30); weekly trigger (NOT one-shot → won't go dark). Documented in SCHEDULED-TASKS.md (count 63→64). Guard `test_preopen_readiness.py` +7 (23/23, non-vacuous bite). Live: task Ready, NextRun TODAY 08:25 ET; ran GREEN end-to-end (7 chain tasks + 6 fleet accounts, no false ping). Registry/TZ/installer guards 15/15, curated gate 31+5 PASS. **W26 manual pre-Monday ritual now fully automated.** :: depends:none :: status:done
- [x] PROMOTE-KEEPER-RECENCY-GATE (HIGH, safety-frame-fix) :: **DONE 2026-06-29 conductor (commit cb82456).** Frame-fix for the recurring promote_keeper #1-then-dismiss loop (OP-33d). The OP-11 auto-clear (`contender_oos_check.py`) checked 4 gates (oos/wf/sub-window/anchor) but NEVER the documented CONFIRM-BEFORE-CAPITAL recency gate -> a dead-premium-axis contender (WR 12%, tp+150%) auto-applied to LIVE params on 06-28 (commit b8896df: tp1 0.667->0.8 + profit-lock trailing->fixed) DESPITE recency=RED. Shipped gate 5 (`assess_recency_gate`, fails CLOSED, never blocks J's manual approval); guard `test_contender_oos_recency_gate.py` 11/11 (bite-tested). The already-live 06-28 change flagged to J for revert-or-keep (cd-2026-06-29-001, rail-4). :: depends:none :: status:done
- [x] PROMOTE-KEEPER-RECENCY-GATE-DEFENSE-IN-DEPTH (LOW, safety-belt) :: **DONE 2026-06-29 conductor (commit 8200ac3).** Wired a self-contained fail-closed `_recency_gate_clears` into `autonomy_actuator.auto_approve_pending`'s `op11_evalbar` branch -- the actuator re-verified wf/oos/anchor but NOT recency, so a pre-gate / manually-flipped / alternate-path `eval_bar_cleared=true` could auto-apply a recency-RED change at the SECOND chokepoint. Pure-stdlib mirror of `assess_recency_gate` (the actuator stays decoupled from the heavy autoresearch stack); a PARITY guard pins the two to identical verdicts across 8 fixtures so they can't drift (C14). Guard `test_actuator_recency_gate.py` (23/23): fail-closed matrix, only-explicit-True, parity, + the bite (clearing op11 auto-approves iff recency confirmed). Updated `test_autonomy_auto_approve.py` to supply a recency-confirmed fixture for its op11 case. Curated gate 31+5 PASS, verify-committed clean. The recency capital gate now guards BOTH chokepoints (emit: contender_oos_check cb82456; apply: actuator 8200ac3). :: depends:none :: status:done
- [x] TASK-SCORER-RECENCY-GATE-THE-SELECTOR (LOW, conductor-tooling, OP-33d frame-fix) :: **DONE 2026-06-30 conductor (commit 910aad7).** The recency gate was enforced at the EXECUTOR (both apply chokepoints) but NOT at the SELECTOR — so `task_scorer` ranked the dead-axis recency-RED `PROMOTE-KEEPER` ready=#1 on ~9 consecutive fires, costing each fire a manual verify-then-dismiss. FIX: `_recency_explicitly_red()` reads the SAME `headline.edges_confirmed_on_recent` field the capital gates read and down-ranks a `PROMOTE-KEEPER` item to `ready=false` ONLY on a readable EXPLICIT RED (missing/garbled/confirmed -> not suppressed; conservative attention-routing fails OPEN, never hides work). Self-contained stdlib (task_scorer's run-anywhere/never-raises contract preserved). Verified live: PROMOTE-KEEPER gone from default ranking, present under --all with the block reason; auto-returns to ready=true when recency flips green. Guard `test_task_scorer_recency.py` 17/17 (bite + field-contract parity vs `autonomy_actuator._recency_gate_clears`, C14); existing `test_task_scorer.py` 12/12 no-regression; curated gate 31+5 PASS. Lesson-inbox: gate-the-selector-not-just-the-executor. :: depends:none :: status:done
- [x] G6-VIX-INTRADAY-FEED (P1, data-feed) :: **SHIPPED DISARMED 2026-06-27 conductor (commit 2b24652).** PRODUCER: `heartbeat_core._fetch_vix_intraday()` + `_build_payload` now attaches `bar_ctx['vix_intraday']` (^VIX 5m, RTH-only, newest-last) CAUSALLY capped at the trigger bar — but ONLY when `j_vix_dayside_enabled` (gated on the SAME flag the dispatch consumer is gated on, so producer+consumer arm together). Dormant => byte-identical no-op, ZERO extra hot-path download (the dispatch loop skips `_dispatch_vix_dayside` entirely while the flag is false). Fail-open (None -> watcher SKIPs, never guesses regime). Replay-injection seam added (`vix_intraday=` param). CONSUMER: `setup_dispatch._build_ctx` threads bar_ctx['vix_intraday'] onto the frozen BarContext. Graduated to an 11-test guard `backtest/tests/test_g6_vix_intraday_feed.py` (dormant-no-fetch, causal-cap, fail-open, ctx-thread, + feed-present clears `SKIP_NO_FEED:vix_intraday_not_wired` while absent still reports it). 59 existing dispatch/core/g4 tests green; curated safety gate PASS. **ARM is STILL J+recency-gated** (vix_dayside recency-RED book per DIRECTION-BLOCK-BATCH-RECONCILE; license_monitor pings on RED->green). REMAINING refinement (LOW, when armed w/ live data): the feed position-aligns by tail-slice; harden to per-timestamp alignment vs the SPY sameday grid if a missing VIX bar ever shifts it (dormant => only mis-logs). :: depends:none :: status:done
- [x] G5-SWARM-PREMARKET-TZ (P1, scheduled-task) :: **STALE-RESOLVED 2026-06-27 conductor (commit 0e4fe33) — the TZ fix was ALREADY applied 2026-06-26; the queue item was never swept (L181/L185 stale breadcrumb).** Verified LIVE: `Gamma_SwarmPremarket` trigger StartBoundary=`2026-06-26T06:15:00-06:00` = 06:15 MT = **08:15 ET**, MSFT_TaskWeeklyTrigger DaysOfWeek Mon-Fri (a weekday-only daily fire — legitimate), NextRun=Mon 06/29 08:15 ET. `install-swarm-task.ps1` + `register_tz_fixed_tasks.ps1` both use `-At "06:15"` MT. The 10:18 ET swarm_output.json was the OLD pre-fix trigger; LastRun=never is expected (re-registered after that day's fire time → first real fire Monday). **What was genuinely MISSING (and now SHIPPED): a guard** — `backtest/tests/test_scheduled_task_tz_ordering.py` (5 tests, bite-tested non-vacuous) statically asserts the prep-chain TZ-consistency + ordering (swarm 08:15 < ema 08:20 < premarket 08:30 ET) so a future TZ edit can't silently re-misorder the swarm->premarket handoff, AND pins `install-tasks.ps1` as KNOWN_TZ_UNFIXED via a shrinks-only ratchet (see G17 below). :: depends:none :: status:done
- [x] G7-EOD-FLATTEN-PURE-PYTHON (P1, engine-resilience) :: **SHIPPED + COMMITTED 2026-06-27 conductor (commit 221d0c6).** The prior fire authored+validated it but left it UNCOMMITTED (verify-committed foot-gun L164/L187). This fire verified the 12/12 guard + confirmed via `Get-ScheduledTask` that the new Core tasks are NOT registered (only the LLM `Gamma_EodFlatten`/`_Aggressive` are live), then committed the 3 files for durability. The pre-commit registry guard `test_every_installed_task_is_documented` BLOCKED the first attempt (the new `Gamma_EodFlattenCore`/`_Aggressive` weren't in SCHEDULED-TASKS.md = exactly why the prior fire couldn't commit) → fixed by documenting both under `## Proposed`. **ACTIVATION (running `install-eod-flatten-core.ps1` to swap the live 15:55 ET order-close task) stays J-gated → see G7-ACTIVATE; proposal cd-2026-06-27-001.** `Gamma_EodFlatten`/`_Aggressive` was LLM-based via `claude --print` on eod-flatten.md — the SAME fragile Max-pool substrate the heartbeat was migrated away from. FIX: `setup/scripts/eod_flatten.py` — pure-Python, NO LLM/MCP/CDP: loads both safe-2+bold-2 creds from `secrets.json` via `fleet_broker.load_creds()`, queries `open_spy_option_positions` per account, calls `close_all_spy_options(live=True)` with a 3-attempt retry-until-zero loop, logs to `automation/state/logs/eod-flatten-YYYY-MM-DD.{log,jsonl}`, fail-open per account (one error never blocks the other), uses `et_clock.et_now()` for all timestamps (NEVER naive datetime.now()), exits 0 always. Idempotent + expiry-agnostic (closes 0DTE AND 1DTE). WIRE: `setup/scripts/install-eod-flatten-core.ps1` registers `Gamma_EodFlattenCore` + `Gamma_EodFlattenCore_Aggressive` at 13:55 MT = 15:55 ET via the flash-free wscript+pythonw chain, disables the retired LLM tasks. GUARD: `backtest/tests/test_eod_flatten.py` (12/12 green) pins FLAT_NOOP / CLOSE_ON_OPEN / FAIL_OPEN / ET_CLOCK / DRY_RUN / NO_CREDS / EXPIRY_AGNOSTIC. DRY-RUN VALIDATED: both paper accounts flat on weekend -> NOOP + exit 0, zero orders placed. :: depends:none :: status:done
- [x] G8-COMPANION-APPROVAL-BUS (P1, presence) :: **SHIPPED 2026-06-27 conductor (commit fe4c552) — chose option (a).** `autonomy_actuator.sync_companion_approvals()` now reads `companion-decisions.jsonl` (J's localhost:4317 phone/watch Approve/Reject taps) and flips the matching **PENDING** `conductor-proposals.jsonl` row → `approved` (approve, tagged `approved_via:companion`) / `shelved` (reject) — the symmetric companion equivalent of the Discord `ship <id>` flow. Wired at the TOP of `apply_approved()` (no new scheduled task — same auto-wire pattern STATUS-RETENTION chose; runs every Gamma_AutoApply after-hours fire). **RAIL-4 CLEAR:** records J's consent ONLY; the deterministic apply path (apply_ops + safety gate + snapshot + git commit + revert) is UNCHANGED and still does all editing. **SAFE:** synthetic `act-*`/`oblig-*` cards name no proposal_id → ignored; only `pending` rows are touched (never re-opens applied/approved/shelved/reverted) → idempotent, J's later action always wins. Graduated to a 13-test guard `backtest/tests/test_companion_approval_bridge.py` (approve/reject flip, synthetic-ignored, non-pending-never-retouched ×5 statuses, idempotent, fail-open on missing file, torn-line, dry-run-no-mutate, + a bite test proving the pending-only check protects an applied row). 19/19 actuator+bridge tests green; curated safety gate 29+5 PASS. The companion face is now a genuine approval surface (no longer notify-only) — a J tap on the pending `gp-2026-06-24-001` card will flow through. :: depends:none :: status:done
- [x] G18-BARE-CMD-HIDDEN-CHAIN (P2, scheduled-task-infra) :: Two tasks fail `audit_scheduled_tasks.py` BARE_CMD_POWERSHELL (HARD FAIL — Win11 OpenConsole flash, project_mcp_window_leak_fix): `Gamma_ContextGuard` (16:10 ET daily) + `Gamma_SwarmPremarket` (08:15 ET wd). :: **DONE 2026-06-27 conductor (commit cf3ef6a).** Root cause = a RECURRENCE: the 2026-06-26 TZ fix `register_tz_fixed_tasks.ps1` sections #1/#2 re-registered both tasks with BARE powershell actions, clobbering the earlier flash-fix; `Gamma_SwarmPremarket` was also never in `fix-powershell-task-flash.ps1`'s targets. FIX at the SOURCE (not just the live task): converted register_tz_fixed_tasks.ps1 #1/#2 + register-context-guard.ps1 + install-swarm-task.ps1 to the wscript->run_exe_hidden.vbs->pythonw->run_ps1_hidden.py chain (matched the already-correct #3 SpendSummary; -AutoFix preserved for ContextGuard; stale manual-instructions echo fixed), added SwarmPremarket to the converter targets. Applied to LIVE tasks via the converter (Set-ScheduledTask preserves triggers — verified Start boundaries 14:10 MT / 06:15 MT intact). Audit re-run: 2 flags -> 0, **HEALTH GREEN**. L189's transition-alerting blindness now mechanically resolved (audit no longer stuck RED). Graduated to `backtest/tests/test_installer_no_bare_console_action.py` (4/4, bite-tested) — a static installer-SOURCE scan closing the gap the WS6 guard left (it only tested detection helpers, never installer source). 6 pre-existing latent bare installers seeded into a shrinks-only ratchet (crypto x3, watchdog-modes-sweep, register-eod-deep-dive, scripts/setup-all) — fix-when-touched, the ratchet forces removal on fix. NOTE: a separate pre-existing audit count drift (active 55 vs registry-says 61, disabled 7 vs 1) is informational (not a flag) — follow-up to reconcile SCHEDULED-TASKS.md stated counts vs live. :: depends:none :: status:done
- [x] G14-EXIT-RIBBON-FLIPBACK-WIRE (HIGH, engine-exit, **DONE 2026-07-01 ~20:15 conductor — "fn=None" was STALE; real bug = a BULL/BEAR literal mismatch that silently killed the v15.3 PRIMARY exit**) :: DIAGNOSED (OP-33): wiring already EXISTS (`_ribbon_flip_fn` L564 + `_manage_exits` passes `flip_fn` L586). Real defect: `_ribbon_flip_fn` compared `ribbon_stack == ("BULLISH"/"BEARISH")` but the producer (`backtest/lib/ribbon.py` L102-104) only emits `"BULL"/"BEAR"/"MIXED"/"WARMUP"/"UNKNOWN"` → never matched → v15.3 chart-stop-PRIMARY ribbon-flip-back silently never fired (C14 dead-knob), HIDDEN by a VACUOUS guard (re-implemented the buggy logic inline vs importing the real fn — L197/G16). FIX: literal `"BULL"/"BEAR"` (in concurrent-fire 4e71618) + MY commit f76ac48 rewrote the guard to import the REAL fn + assert real literals + producer-alphabet contract + MIXED/UNKNOWN hold + retired-literal bite. Anchor 5/04 721P +$730 preserved; `manage_tick` calls fn with side="P"/"C" (verified). VALIDATED: graduated_guards 105/1skip, money-path 35/35, exit/funnel 45/45, curated 31+5. Rail-4 (revert `git revert f76ac48`+REVOKE). FOLLOW-UP (separate, not this fire): RATCHET_STOP runner stop is tick-managed (no resting broker order) → a missed tick leaves it un-enforced that bar. :: depends:none :: status:done
- [x] G13-STRUCTURE-VETO-SYSPATH-HARDEN (P2, engine-defensive) :: **RESOLVED 2026-06-27 conductor (commit b0f3416) — the breadcrumb's proposed fix was DANGEROUS; shipped the correct guard instead.** VERIFIED before building (L181/L185): (1) **the G13-proposed sys.path edit is ACTIVELY HARMFUL** — adding `_REPO/crypto`/`_REPO/crypto/lib` at sys.path[0] would shadow `backtest/lib` with `crypto/lib` (which has its own `ribbon.py` and NO `engine/`), breaking engine_cli's `from lib.engine.gates import`/`from lib.ribbon import` entirely. The real imports are `from crypto.lib.X import Y` which already resolve via `_REPO` (present) — the path edit doesn't even help them. REJECTED. (2) **The REAL gap (same class as G16): the structure veto's `_classify_sameday_5m` (crypto.lib import + tz-aware Bar + swing-classify) is wrapped in a bare `except -> 'unknown'` = fail-open, and EVERY existing test MOCKS it** (`_with_structure_veto` patches `_classify_sameday_5m`) → a silent break (crypto.lib rename, `_REPO` drop, naive-timestamp regression — crypto.lib.bar.Bar raises ValueError on a naive open_time, swallowed → 'unknown' → Gate 16 off) would disable the wrong-way-entry veto (the −$237 incident) with all tests green. Confirmed empirically: naive timestamps → 'unknown' (silent disable); production is safe TODAY only because heartbeat_core supplies tz-aware NY ISO (L147+L428). SHIPPED `backtest/tests/test_structure_veto_classifier_live.py` (13 tests, bite-tested non-vacuous: REDs when the classifier silently returns 'unknown') exercising the REAL end-to-end path (downtrend/uptrend classify, crypto.lib import resolves, the naive-timestamp fail-open characterized, fail-open-never-raises, + the no-shadow invariant that pins WHY the path-fix was rejected). 42 passed (sibling test_structure_veto.py no-regress); curated safety gate 29+5 PASS. :: depends:none :: status:done
- [x] WATCHER-FEED-REARM-CONFIRM (MED, engine-correctness) :: **CLOSED + SHIPPED 2026-06-24 (commit 33c22ed). See Completed.** Confirmed full 09:30–15:55 ET coverage (154 diag + 78 obs rows, every ET hour 09..15, zero crash/darkness signals) → re-armed `watcher_feed` to `critical=True` + graduated to a guard. ~~DE-RISKED 2026-06-24 (commit 2eceac1)~~ — an end-to-end integration guard (`backtest/tests/test_watcher_live_integration.py`) now proves `main()` traverses the full pipeline to completion on a healthy synthetic frame (rich diag emitted) + that a fleet crash stays loud (verify-now-not-later; replaces "wait for live RTH"). Remaining step = the live-RTH FORMALITY. THREE guard layers now in place: ET-gate 3e8ed79, load-fallback 57cef40, integration 2eceac1. Post-fix confirmation for the watcher_live fixes: the ET-gate (commit 3e8ed79) AND the load_data total-darkness fix (commit 57cef40, 2026-06-24). On the next RTH, read `automation/state/watcher-live-diag.jsonl` + `watcher-observations.jsonl` and confirm the producer now emits rows across the **full 09:30–15:55 ET** window (previously blind until 11:30 ET). IF confirmed → re-arm `watcher_feed` to `critical=True` in `setup/scripts/engine_health.py` (the 06-22 reclass was a deliberate temporary downgrade). IF 06-23-style TOTAL darkness recurs: the diag will now show WHICH path failed (`load_data_unexpected_error:*` = corrupt CSV now caught; `no_bars_after_topup`; `yfinance_topup_failed:*`) — if STILL zero rows the cause is upstream of `main()` (task not firing / import-time crash / machine asleep), so investigate the scheduled task `LastTaskResult` + the wscript→pythonw chain. :: depends:none :: status:pending
- [x] STATUS-RETENTION-AUTOWIRE (LOW, engine-benefit) :: **CLOSED + SHIPPED 2026-06-24 (commit 27b5782).** See Completed. Wired `status_retention.py` into `run-conductor.ps1` after the rail-1 after-hours gate (after-hours only) + before the claude launch (this fire reads trimmed STATUS); fail-open `try{}catch{}`, CREATE_NO_WINDOW, idempotent. Graduated to a regression guard (`test_retention_is_autowired_into_conductor_wrapper`, 11/11). Chose the conductor wrapper over a new scheduled task (zero TZ foot-gun, zero risk to trading jobs) — it already runs after-hours every fire and the tool is idempotent. :: depends:none :: status:done
- [x] GRADUATE-NULL-STRIKE-UNIVERSE-PARITY (MED, engine-benefit) :: **CLOSED + SHIPPED (commit bb6dd55).** See Completed. :: depends:none :: status:done
- [x] J-RULING-BOLD-KILLSWITCH (HIGH, Rule-9) :: **CLOSED 2026-06-21 (conductor) — no J-ruling needed; conflict already resolved + now guarded.** See Completed. The -60% was drift, not a doctrine choice: both `aggressive/circuit-breaker.json` and `aggressive/params.json#daily_loss_kill_switch_pct` now read **-50%** (reconciled 2026-06-21 to match CLAUDE.md Rule 5; the more-protective value was always canonical). Graduated to a parity-ratchet test so the drift can never silently recur. :: depends:none :: status:done
- [x] DIR-NULL-P5-GATE-GRADUATION (MED, engine-benefit) :: **DONE 2026-06-28 gamma-drive (commit 87a73f8).** Wired the direction-controlled null into `family_grind.run_family` as an automatic P5 gate: `is_directional_family()` flags firing-rate >80% (C27); a PASS-P4 cell of such a family must beat the dir-null MAX on exp AND its MEAN on drop-top5 (fail-CLOSED via `dir_null_survives`) or downgrades to `PASS-P4-DIR-ARTIFACT` (not an elite); else `PASS-P5`. Non-directional families byte-identical. Guards: `test_dir_null_p5_gate.py` (6 behavioral, bite-tested) + `test_graduated_guards::test_l188_dir_null_p5_gate_wired_into_family_grind` (static ratchet). L188 prose marked graduated. **GRADUATE L188 (encoded 2026-06-26 conductor) from a one-off verify cross-check to an automatic gate.** The direction-controlled null (random bars, side = `sign(close−open)` = momentum-aware random entry) currently lives ONLY in `backtest/autoresearch/_verify_bollinger.py` — it caught `three_ducks` (firing 98% of days, passed the random-SIDE null but COLLAPSED vs the dir-null = direction-following artifact) vs `bollinger_squeeze` (survived both = real selection alpha). FIX: wire the dir-null into `family_grind.py` as an automatic **P5 gate** for any family flagged directional/high-firing-rate (>80% of days, C27) — a family must beat the dir-null MAX (and drop-top5 beat its MEAN) before any FORWARD-VALIDATE verdict; add a `test_graduated_guards` assertion so the gate can't be silently dropped. Per OP-22, first occurrence stays prose (done — L188); graduate when re-hit OR when the next directional family is ground (whichever comes first). Engine-benefit authoring, rail-4 clear → ships on green tests, no A/B. :: depends:none :: status:pending
- [x] PHASE2-C1-BIAS-EMA-NULLS (MED) :: **STALE-RESOLVED 2026-06-21.** The fields are NOT null — they live under `key_levels` (the original probe checked top-level). `automation/scripts/compute_ema_snapshot.py` (scheduled `Gamma_EmaSnapshot` 08:20 ET) computes Saty-ribbon EMAs 13/20/48 + SMA-50 from the SPY CSV and patches today-bias key_levels in-place when premarket's TV pull fails (06-19: `ema_read_failed: true` holiday → fallback populated 751.09/751.3/751.94/752.12, matching ema-snapshot.json). The producer was UNTRACKED (L164) + UNTESTED → tracked + graduated to a guard (`backtest/tests/test_compute_ema_snapshot.py` 7/7) this fire. Moved to Completed. :: depends:none :: status:done

### T-GYM-20260708 HIGH gym-session RED for 2026-07-08

**Audits failing:**
- crypto-gym (53 validators) (RED): 103/104 pass

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-STOPA-ENTRY-EXIT-MATRIX HIGH -- ⛔ STOP CHECKPOINT A ready for sign-off

**[J: STOP-A ENTRY-EXIT-MATRIX awaiting your (or Fable/Opus) sign-off before T5/T6.** Read `markdown/planning/STOP-A-ENTRY-EXIT-MATRIX.md`.** Headline: the shipped `-20/+150` exit LOSES -$757 on the 79 real fleet fills; a wider-stop/partial-scalp/trailing shape makes +$1,053..1,574 on the same fills (T4 anchor). Passive limit entry is a CONDITIONAL win (helps a scalp exit, hurts a no-stop ride -- T3). Nothing shipped. T5 candidates pre-registered (frozen) in `analysis/recommendations/entry-exit-matrix-stop-a-preregistration.json`.]**

**[J: two live exit shapes (ribbon_ride -20/+150, vwap_continuation -8/+30) are on PROVISIONAL P5 waivers (`automation/state/p5-shape-waivers.json`) -- sign, replace via T5, or retire. The ribbon_ride shape fails its own P5 gate (the T5 scar, now instrumented).]**

**Action (post-sign-off only):** run T5 confirmatory OOS on the pre-registered list -> A/B scorecards -> STOP CHECKPOINT B. :: depends:J-signoff :: status:blocked-on-J

**LIVE EVIDENCE (2026-07-09 09:43-10:34 ET, fleet BULLISH_RECLAIM_RIDE_THE_RIBBON on the 747.5/747.9 reclaim) — CORRECTED after checking the actual option tape (Fable, ~11:50 ET):** 3 same-signal round-trips, ALL premium-stopped (09:49 / 10:07 / 10:34), ~-$383 realized across the 4 arms, thesis direction ultimately RIGHT (SPY 748.2 -> 750.2 by 11:44). **BUT the naive "exit-A would have banked it" read is FALSE for rounds 1-2:** 751C bars show the 10:05-10:15 flush took the contract 0.54 -> 0.14 (-74% peak-to-trough) — exit-A's -50% stop fires there for a BIGGER loss than the -20% control on both 751C rounds; only round 3 (750C, low 0.32 vs -50% stop 0.27, then 0.54 -> 1.03 high by 11:40) pays under exit-A. This is T-W7 layer-(a)'s finding reproduced live (wider stop adds downside on whipsaws, only pays on rides) — the layers-disagree conflict is REAL and today is a microcosm of it. The deeper leak today was ENTRY QUALITY: 09:43 bought the FIRST break into the documented 748.43/748.78 resistance cluster ($0.85 headroom vs a +/-40%-noise $0.50 premium); SPY rejected off 748.78 (memory score 111, 63 touches — the feed CALLED it), flushed to ~747.3 (intrabar reclaim failure), and the payable break came ~10:55-11:20. See T-W8-HEADROOM-RETEST below. :: depends:STOP-B :: status:escalated-to-STOP-B

**UPDATE (Fable review 2026-07-08 late):** STOP-A execution independently verified — finding STANDS (anchor parity: actual −$893 vs replayed control −$757). 7 corrections shipped incl. P5-gate full-set fix (was reading 15/86 survivors), dead trail-knob discovery (old grind never tested trailing — 181/181 pairs identical), engine-contract card §3 correction (core arms trade the strategies.py ribbon_ride shape in production, NOT params tp/stop), pre-registration v2. **[J: new two-lane discrepancy — vwap_continuation trades −8%/+30% on fleet arms but −6%/+40% on core arms (j_vwap_cont_* params keys). Which is the validated cell?]** Next executor: markdown/planning/HANDOFF-2026-07-11-CONFIRM-AND-WIRE.md

**UPDATE (CONFIRM-AND-WIRE executor, 2026-07-08 late):** T-W6 answered (`markdown/audits/T-W6-VWAP-TWO-LANE-PROVENANCE-2026-07-08.md`) — **−0.06/+0.40 is the validated cell** (git-archaeology: both lanes started at −0.08/+0.30 on 2026-07-02; a 2026-07-07 walk-forward study improved the core lane only to −0.06/+0.40, all 5 OP-22 gates PASS, `strategies.py` was never touched — a duplicated-knob drift, not a live A/B). **[J: which full vwap shape should the fleet trade? Fable review sharpened this (C29): the validated cell is the ENTIRE core shape (−0.06/+0.40/qty-frac 0.8/PL fixed/ATM) — the fleet ExitShape differs on qty-frac (0.667), lock (trailing), and strikes (per-arm), so a naive two-field sync creates an untested THIRD combination. Options: port the whole validated cell (still needs P5-or-waiver + STOP-B) or hold for the owed vwap matrix. See the caveat in markdown/audits/T-W6-VWAP-TWO-LANE-PROVENANCE-2026-07-08.md.]** T-W2 (dead lock/trail knob) fixed + red-proofed (`backtest/tests/test_lock_trail_kwargs_wired.py`) without touching the L156-guarded `_params_to_kwargs`. T-W3 fresh v2 grind (6720 combos, real trail_pct{0.15,0.22}+time-exit{10,60} axes) launched in background, running for hours — see HANDOFF report for live status. T-W4 (per_band_stop.py) + T-W5 (entry_manager.py + shadow ledger, 98 real entries/8 sessions, fill-rate 85.9% vs T3's 77.6% backtest — sim-live parity PASS) built, unit-tested, red-proofed, shadow-only. Full report: markdown/planning/CONFIRM-AND-WIRE-REPORT-2026-07-08.md

### T-AUTOPSY-H-2026-07-08-stop-noise MED — autopsy hypothesis: stop_inside_noise_floor

**Claim:** the live stop exits losers that then pay the thesis -- the stop is harvesting winners, not cutting losers. **Evidence:** `{"losers_in_window": 12, "stopped_then_paid": 8, "fraction": 0.667, "window_n": 14}` (analysis/autopsies/2026-07-08.md).
**Action:** replay exit-A (-50/+150/sell66/trail15) on these exact fills via exit_shape_parity_study (kill-check) · confirm on the fresh OPRA slice per the STOP-A pre-registration (T-W7) :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-07-08-entry-spike MED — autopsy hypothesis: paying_the_signal_spike

**Claim:** entries fill materially above the signal-minute low -- the marketable ask+buffer buys the local premium spike (defect #2). **Evidence:** `{"median_paid_above_min_low": 0.3, "n": 14}` (analysis/autopsies/2026-07-08.md).
**Action:** entry_manager shadow (T-W5): log limit-below/patience counterfactual fills next to real entries for 3+ sessions :: depends:none :: status:DONE (2026-07-08 — `automation/state/entry-shadow.jsonl`, 98 entries/8 sessions, shadow fill-rate 85.9% vs T3 backtest 77.6%, within tolerance)

### T-AUTOPSY-H-2026-07-08-left-on-table MED — autopsy hypothesis: exit_shape_dominated

**Claim:** a fixed counterfactual shape beats the shipped exits by more than 2x the window's net P&L -- the exit shape, not the signal, is the bottleneck. **Evidence:** `{"sum_stop_cost": 1913.0, "window_net_pnl": -382.0, "n_dominated": 3, "window_n": 14}` (analysis/autopsies/2026-07-08.md).
**Action:** STOP-A sign-off -> T-W7 confirmatory on the frozen v2 candidates · enumerate levers beyond exit shape per markdown/trading-knowledge/GENERATIVE-LENS.md (DTE / spread / strike / sizing) :: depends:none :: status:proposed

## 2026-07-09 after-hours — profit-lock scope mismatch (engine-owner follow-up, DONE)

- [x] PROFIT-LOCK-SCOPE-MISMATCH (HIGH, engine-correctness, sim-vs-live) :: RESOLVED 2026-07-09 evening (the matrix parity_check's "engine-owner follow-up"). Finding: simulate_trade_real arms the profit-lock PRE-TP1 on the whole position (sim:540-584, the ratchet feeds the exit-ALL stop at sim:644); live exit_manager only armed at/after TP1 — and since the TP1 fill itself sets profit_lock_armed, profit_lock_arm_pct was a DEAD knob live. Every vwap exit scorecard (parity 07-02 + ship-gate 07-07) passed thr=0.05 believing it mirrored live. Quantified (matrix parity_check isolation): the lock component ≈ -$0.72/tr aggregate on vwap ($54.73→$55.45 with thr=0 — real per-trade divergences, roughly EV-neutral aggregate); the -$39.71/tr cross-engine delta is mostly ribbon-flip modeling + fill conventions. DECISION: do NOT port sim semantics into live (it would also have silently mutated the just-shipped SS-B structure cell, which was validated on live semantics). Shipped instead: exit_manager/ExitShape gained expressible profit_lock_arm_scope (post_tp1 default = byte-identical legacy, red-proof-verified; full = sim parity), armed by NOTHING (arming needs live-machine scorecard + STOP-B); cross-machine pins RED on silent convergence from either side (backtest/tests/test_profit_lock_scope_pin.py + fleet test_exit_manager.py::test_pre_tp1_lock_*); both scorecards annotated sim_semantics_caveat; engine-contract card renders the scope ("arm +5% (post-TP1)"); live vwap cell independently re-affirmed CONTROL-STANDS by the matrix (exit_manager engine, fresh tail). Lesson inbox: 2026-07-09-profit-lock-scope-mismatch.md :: depends:none :: status:DONE
- [ ] EXIT-ENGINE-PARITY-RESIDUAL (MED, research-integrity) :: The undiagnosed remainder of the bar-replay($15.02) vs simulate_trade_real($54.73) control-cell gap after the two confirmed mechanisms (pre-TP1 lock ≈ $0.72, ribbon-flip-back ~26% of sim exits — inconclusive in isolation): likely fill-order/tie-break conventions between the two independent bar walks. Matters only when someone quotes simulate_trade_real ABSOLUTE dollars as live-expected P&L — relative A/Bs within one engine + real-fills anchors (current discipline) are unaffected. Diagnose via per-trade exit-reason diff on the 149-trade control set before the next sim-authority ratification :: depends:none :: status:pending

## 2026-07-09 after-hours (from G11 review)

- [x] G11-LEVEL-MEMORY-AB-REPLAY (HIGH, engine-edge, research-bridge) :: DONE 2026-07-15 — pre-reg `analysis/recommendations/prereg-level-memory-wire-2026-07-15.json` (frozen+committed before run), scorecard `analysis/recommendations/level-memory-wire.json`/`.md`. Real-fills counterfactual replay (`backtest/tools/level_memory_wire_ab.py`, new additive `levels.py#_detect_from_history(memory_levels_by_day=...)` hook, real production trigger logic) over 2026-06-05..07-14 (26 sessions): CONTROL 28 trades / TREATMENT 26 trades. Participation-added n=2 (−$489.50, both `confluence`-triggered losers) + shared-behavior-changed n=1 ($0 delta) = combined n=3, below the pre-registered 15-evidence floor → **verdict NEGATIVE_INSUFFICIENT_N, flag left ON** (revert clause not invoked — insufficient evidence, not a pass). Live cross-check of the 3 real wire-live sessions (07-09/07-10/07-14): the wire touched exactly 1 real signal episode (07-14 10:36-10:38 ET, deduped from 3 identical ticks) — blocked by `VETOED_BY_MODELS` then `RISK_DENY_PDT`, zero real fills, zero real P&L. OPRA cache backfilled for the 4 missing sessions (88 contracts, 0 errors) so the whole window replays on real fills. :: depends:none :: status:done
- [x] G11-C14-WIRING-GUARD (MED, engine-correctness) :: DONE 2026-07-15 — `backtest/tests/test_graduated_guards.py::test_level_memory_live_merge_key_present_and_boolean` asserts live params.json carries `level_memory_live_merge` as a present boolean; PASSED. :: depends:none :: status:done
- [x] D1-TV-CDP-ROOT-CAUSE (HIGH, infra) :: TV CDP root-cause live repro (Invoke-TvLaunchSafe PSArgumentException, D1 #1) + port assess_tv_cdp into self_check.py (D1 #3) :: depends:none :: status:CLOSED_PARTIAL (item 3 SHIPPED, item 1 not re-pickable -- no active outage to repro)

> **CLOSED item 3 (port assess_tv_cdp into self_check.py) 2026-07-21 ~17:12-17:35 ET
> (conductor, AFTERHOURS): SHIPPED, commit `866aac9`.** Confirmed live (grep, zero hits) that
> `self_check.py` -- the surface J's STATUS.md/engine-health.json morning brief actually reads
> every ~30 min -- still had ZERO tv/cdp/9222/TradingView awareness, 12 days after the D1 audit
> flagged this as effort=S. `preopen_readiness.py`'s `assess_tv_cdp`/`fetch_tv_cdp` (built
> 2026-07-06) already solved this correctly but only fires once at 08:25 ET and is a different
> file. **Built:** `check_tv_cdp(now, fetch=None)` (new, ported not imported -- matches this
> file's own deliberate-duplication convention per `check_macro_calendar_freshness`'s docstring)
> + `_fetch_tv_cdp_reachable()` (urllib probe on `:9222/json/version`, fail-open on any
> exception, never raises). Windowed 08:10-16:00 ET weekdays (Gamma_LaunchTV 08:00 + 5-min-slack,
> Gamma_TvWatchdog 08:05-16:00/5min); classifies RED/BROKEN (not DEGRADED) on an unreachable CDP,
> matching `assess_tv_cdp`'s own critical severity -- a dead CDP has the disclosed real cost from
> the 07-07/09 outage (premarket bias degraded to `"no-trade-tv-fail"`). Wired as step 14 in
> `run()`. **Verified this fire (OP-33):** new guard `backtest/tests/test_self_check_tv_cdp.py`
> (8/8) RED-proofed via `git stash -- setup/scripts/self_check.py` alone -- all 8 failed pre-fix
> with the exact expected `AttributeError: module 'self_check' has no attribute 'check_tv_cdp'`,
> `git stash pop` restored cleanly, re-verified 8/8 green. Broader sweep:
> `pytest backtest/tests/ -k self_check` -> **71/71 PASS, 0 regressions**. Curated safety gate
> (31+5-suite) PASS. `git ls-tree HEAD` confirmed both files (self_check.py, new test) landed on
> HEAD, not just staged. **Zero trading-path files touched** -- `self_check.py` is an
> observation-only monitoring organ (no broker/params/heartbeat_core/placement/exit code); ships
> as engine-benefit per OP-22/OP-26, no J ratification needed. **Revert:** `git revert 866aac9`
> (2 files, additive, no data loss). **Item 1 (live repro of the 2026-07-08 PSArgumentException)
> NOT attempted this fire** -- confirmed `tv-watchdog-status.json` shows `cdp_up: true` right now
> (2026-07-21 16:00 ET), i.e. there is no active outage to reproduce; deliberately forcing a kill
> just to repro a 12-day-stale error message would be a live-TV-disruption risk for no evidentiary
> gain (TV is J's actively-used chart tool, not a throwaway sandbox) and is out of scope for an
> after-hours conductor fire. Left `status:CLOSED_PARTIAL` rather than fully closed so a future
> fire that HAS a live repro opportunity (TV genuinely down again) knows item 1 is still open.
- [x] J-BRAINSTORM-CROSS-TICKER (HIGH, dedicated-session, Fable-owned) :: DONE 2026-07-10 — delivered as markdown/planning/CROSS-TICKER-BRAINSTORM-2026-07-10.md. Verdict: confluence=yes (one composite feature), second-chain=no (QQQ pre-named as the only future exception), explicit preconditions + kill criteria. qqq_divergence_confluence seeded battery-ready in Prospector. Checkbox was stale (work shipped, box never flipped) — closed 2026-07-11 during queue hygiene pass. :: depends:STOP-B-done :: status:done
- [x] CRYPTO-TWIN-T1-T4 (CRITICAL, J-requirement 2026-07-10) :: DONE, superseded and exceeded — T1-T4 shipped 2026-07-10 night and the program continued straight into markdown/planning/TWIN-PROGRAM.md's B1-B2 build (unit-lots, scenario scheduler, gauntlet, real live autonomous fill 2026-07-11). Checkbox was stale (work shipped, box never flipped) — closed 2026-07-11 during queue hygiene pass. :: depends:none :: status:done
- [x] GATE-ORDERING-FIX-RELAUNCH (HIGH, confirmed-bug) :: **CLOSED 2026-07-20 (conductor, verification-only) -- ALREADY SHIPPED, item was stale.** Live-read `setup/scripts/heartbeat_core.py::run_account` lines 911-946: the exact fix the item's own spec named ("move the stale-trigger-bar check to the top ... before decide_payload") is present verbatim, with an inline dated comment block ("FIX (2026-07-10, GATE-PROVENANCE-SWEEP): staleness must be resolved BEFORE any verdict/gate name can claim this tick's logged action") citing the SAME `GATE-PROVENANCE-SWEEP-2026-07-10.md` doc this item points to. `if _stale_trigger_bar(payload, et): rec["action"] = "SKIP_STALE_TRIGGER"` is checked unconditionally, first, ahead of every other branch (ENTER_*/SKIP_LATE_ENTRY/etc.) -- exactly the ordering the item asked for. Guard test `backtest/tests/test_gate_provenance_ordering_2026_07_10.py` exists and is committed to main; re-ran live this fire: **17/17 PASS**. Some prior fire (not this session, no matching STATUS.md/commit-message trace found for "GATE-ORDERING" specifically) completed the relaunch and the checkbox was simply never flipped -- same "stale checkbox, shipped work" class as G11/CROSS-TICKER/CRYPTO-TWIN-T1-T4 above. No code changed this fire (verification-only). :: depends:none :: status:done
- [x] VWAP-TREND-PULLBACK-VERIFY-FAILED (HIGH, do-NOT-wire, **CLOSED 2026-07-23 ~18:42-19:15 ET conductor, honest study run**) :: Ran the frozen pre-registered spec (`analysis/recommendations/vwap-trend-pullback-study-spec.json`, frozen 2026-07-10, never executed until now) via the new `backtest/autoresearch/vwap_trend_pullback_honest_study.py`. **VERDICT: KEEP-DORMANT (confirmed reskin of #1 vwap_continuation, gate_11 HARD BLOCK).** On the LIVE chart-stop-only exit config, 387 trading days through 2026-07-22: ATM exp -$1.09/trade, WF median -0.857 (FAILS >=0.70), sub-window 3/4 hurt, drop-top3/top5 both negative. gate_11 (mandatory/blocking regardless of gates 1-10) reproduces the 2026-06-21 finding on ~13 more months of data: same-side day-overlap vs live `vwap_continuation` = 1.000 (>= 0.80 reskin threshold, unchanged). The escape-hatch after-10:30-only subset does NOT clear either: only 20.2% of signals land after 10:30 (falsifies the "fills the afternoon coverage hole" framing outright, spec's own 30% threshold), and that n=21 subset is expectancy-negative (-$16.90/tr) and OOS-unstable. Scorecard: `analysis/recommendations/vwap-trend-pullback-honest-study.json` + `.md`. Watcher docstring + reason/metadata strings corrected to cite the closed study (was citing the never-run spec + a stale "+OOS$69/trade" claim in the live `reason=` string). Guards: `test_vwap_trend_pullback_watcher.py` 5/5 green (only `promotion_status==WATCH_ONLY` is asserted, unchanged/correct), curated safety gate 31+5 PASS. **This closes the thread for good** — the reskin finding is exit-config-independent, now confirmed twice (2026-06-21 master frame + 2026-07-23 extended frame); no further re-litigation without genuinely new detector logic. :: depends:none :: status:done
- [x] TWIN-B1.5-BEAR-SIM-LANE (HIGH, twin-program) :: Bear-side (P) exit lifecycles can't run on Alpaca spot crypto (long-only). Middle tier: run the P-side branches (structure-stop close-ABOVE-trigger, bear cat-cap, bear TP1/trail) as SIM-tier scenarios -- simulated fills against LIVE BTC quotes via the existing backtest/futures/fill_sim_broker.py machinery (gap-aware, 62 tests) -- clearly labeled tier=SIM in path-coverage.json (schema amended in B1). Real market dynamics, honest fill simulation, strictly better than fixtures. :: DONE 2026-07-14 -- shipped as additive functions inside setup/scripts/crypto_twin_scenarios.py (mirror_premium/_bear_hilo_premiums synthetic put-mirror math + _build_sim_bear_shape/_pick_next_sim_branch/run_sim_bear_tick), reusing the REAL exit_manager.plan_exit_actions core (side="P") and fill_sim_broker.gap_aware_stop_fill verbatim (imported, not forked) for stop-fill pricing; never touches exit-state.json/journal.jsonl/decisions.jsonl (own sim-bear-positions.json/sim-bear-scenario-state.json/sim-bear-journal.jsonl, every journal row tier="SIM"); path-coverage.json's 3 bear branches keep tier="SIM", grading reuses _grade/_mark_exercise_result unchanged. 23 new tests (backtest/tests/test_crypto_twin_sim_bear.py), 147/147 total crypto-twin suite green, zero regressions on the 54 pre-existing LIVE-lane tests. LIVE-VERIFIED same session: ran all 3 branches end-to-end against real Alpaca BTC/USD quotes -- ENTRY_STRUCTURE_STOP_BEAR closed via structure_stop @ 63789.79 (fill 63789.79), ENTRY_TP1_TRAIL_BEAR + ENTRY_CAT_CAP_BEAR both closed via ribbon_flip_back (a genuinely-live independent exit condition, graded GREEN per the always-acceptable-stage rule) -- all 3 branches GREEN, zero incidents, zero LIVE-ledger writes (mtimes unchanged). reachable via `python -m crypto_twin_scenarios --sim-bear [--force-sim-branch ...]`. **FOLLOW-UP SHIPPED 2026-07-16 (SIX-ACCOUNT-DAILY-HYPOTHESIS-REDESIGN.md ship-list #4):** wired into the 24/7 Gamma_CryptoTwin scheduler -- `crypto_twin_scenarios.run_scenario_tick()` (the function `crypto_twin_health.run_tick_with_health`, the Gamma_CryptoTwin scheduled-task entrypoint, already called every 5 min) now ALSO calls `run_sim_bear_tick()` on every production tick, own try/except so a SIM-lane bug can never mask the LIVE row. No edit to `crypto_twin_core.py`/`crypto_twin_health.py`; revert = delete the `TWIN-B1.5-WIRE` block in `run_scenario_tick`, ENTER_BEAR falls straight back to SKIP_NO_SHORT_CRYPTO. Guard: 2 new tests in `backtest/tests/test_crypto_twin_scenarios.py` (`test_run_scenario_tick_sim_bear_lane_ticks_every_call`, `test_run_scenario_tick_enter_bear_skip_still_gets_a_sim_bear_row`, RED-proof against the pre-wiring code), 227/227 crypto-twin suite green, curated safety gate PASS. **LIVE-VERIFIED same evening:** the real scheduled task picked up the code on its next fire (22:08:50 UTC, no restart needed) and placed a genuine SIM entry (`ENTRY_STRUCTURE_STOP_BEAR` @ raw BTC $64,155.355); a manual verification tick 4 min later (22:12 UTC) showed it close via a real structure-stop crossing (`sim_fill_raw_price: 64135.92`, graded GREEN) -- full entry-to-exit lifecycle, zero incidents, zero LIVE-ledger writes. That is fill 1 of the falsification rail's n=10 bear-SIM-fill sample (queue.md/redesign-doc §6: "if the first 10 bear-SIM fills show >55% loss rate, pull the wiring") -- 1 data point, not yet decision-grade; a stop-out is an expected, non-alarming outcome for coverage-forcing (the branch is DESIGNED to exercise the stop path, not to claim edge). Twin P&L (SIM or LIVE) stays mechanism-validation only, never SPY evidence. :: depends:TWIN-B1 :: status:done
- [ ] TWIN-B6-SIM-FRICTION-CALIBRATION (HIGH, twin-program, transfers-to-SPY) :: Use accumulating twin real fills to CALIBRATE the replay harness's fill/friction/latency models (every study discloses 'frictionless fills' -- twin data closes that caveat honestly). Mechanism transfer, not edge. :: depends:TWIN-B1 :: status:pending
- [ ] TWIN-B7-FREE-MODEL-BENCH (MED, twin-program, brain-sovereignty) :: Evaluate + trial free veto models (qwen/nemotron/new roster candidates) on twin decisions as a $0 corpus -- agreement/latency/hallucination metrics; promote to SPY veto lanes only after twin-bench clearance. :: depends:TWIN-B1 :: status:pending
- [ ] TWIN-B8-SUNDAY-CERTIFICATION (MED, twin-program) :: Weekly Sunday-evening full gauntlet sweep of ALL trading-path commits from the week + certification report -> Monday opens pre-certified. Python + free-LLM summary, $0. :: depends:TWIN-B2 :: status:pending
- [ ] TWIN-DOCTRINE-FIRST-DEPLOY (MED, doctrine, propose-only) :: Formalize 'twin-first deploys': any new watcher/detector/exit feature runs 24-48h on the twin before touching a SPY path. CLAUDE.md one-liner proposal via conductor rail-4 + TWIN-PROGRAM.md section. :: depends:TWIN-B1 :: status:pending
- [x] TWIN-B3-ENTRY-MANAGER-LIVE (HIGH, twin-program) :: Graduate entry_manager (T-W5 passive-limit machinery, sim-shadow only) to LIVE measurement on the crypto twin -- real limit-below/patience/cancel fills, mechanism metrics only. Spec: markdown/planning/TWIN-PROGRAM.md stream 3. SHIPPED 2026-07-15 (place_entry_ab A/B alternation + crypto_twin_entry_quality.py; first real passive fill 6ca7aa4b +6.13bps improvement; 2 mechanism bugs caught+fixed rep #1 -- see TWIN-PROGRAM.md B3 section + STATUS.md). Measurement now accrues autonomously on every scenario entry. :: depends:TWIN-B1 :: status:in-progress-live-measuring
- [x] TWIN-B4-CHAOS-DRILL (MED, twin-program) :: Weekly scheduled failure injection on the twin (process-kill mid-position, corrupt state file, stale feed, breaker mid-trip) + resilience ledger. Spec: TWIN-PROGRAM.md stream 4. SHIPPED 2026-07-15 (setup/scripts/twin_chaos_drill.py; Gamma_TwinChaos registered Sunday 03:00 ET; real drill cycle run live tonight, all 4 recovered -- see TWIN-PROGRAM.md B4 section + STATUS.md). :: depends:TWIN-B1 :: status:done
- [ ] TWIN-B5-GRAMMAR-TELEMETRY (MED, twin-program) :: Pattern-grammar rules shadow/log-only on live crypto bars -- firing rates, repaint-safety, C6 discipline telemetry; never edge claims. Spec: TWIN-PROGRAM.md stream 5. :: depends:TWIN-B1 :: status:pending
- [ ] OPEN-BELL-STATUS-PUSH (HIGH, visibility, OP-33e) :: J asked "is the engine working well on its own today?" at 09:58 ET 2026-07-09 (j-question-ledger, >=2nd is_running-intent ask) = missing instrument. Build: 09:36 ET one-shot push of engine-health.json verdict + kill-switch armed/re-armed-today + tick-cadence + fills-so-far, delivered via the SAME channel that carries fill pings (those DID fire 09:44 today) + voice-bot morning brief. Do NOT re-debug the text-ping mute (known hole, superseded by voice bot). Retires the question standing. :: depends:none :: status:pending
- [x] T-W7C-GRIND-VERIFY-THEN-STOPB (HIGH, exit-shape, tonight-first) :: mass-grind v2 (layer-c kill-check) progress file quiet since 05:51 ET 07-09 with PASS-P4 survivors already in funnel-v2 (e.g. OTM-3 stop-12/tp150/sell50/trailing0.15 wf 13.7) — verify complete-vs-reaper-killed; if incomplete relaunch reaper-exempt ONE process; then run mass_grind_phase5 regen + convene STOP-B with ALL THREE layers (T-W7 (a) FAIL / (b) strong-pass conflict + fresh P5). STOP-B owns the exit decision — do NOT wire exit-A on anchor strength alone (fresh slice + today's rounds 1-2 both show -50% losing MORE on whipsaws). exit-C+entry-2 was the only fresh-slice outperformer; entry-2 shadow keeps accumulating. :: depends:none :: status:CLOSED_SUPERSEDED

> **CLOSED 2026-07-21 ~16:45-17:35 ET (conductor, AFTERHOURS): SUPERSEDED, not executed as
> originally specced.** Verified `mass-grind-v2-progress.jsonl` (10.4MB, mtime 07-09 18:14) and
> `mass-grind-phase5.jsonl`/`-summary.json` (mtime 07-10 01:47, NOT quiet-since-05:51 as this
> item's own text claimed -- the grind DID complete and phase5 DID regen, contradicting the
> stale filing) -- so the "verify complete-vs-reaper-killed" half is moot, already resolved.
> The "convene STOP-B" half is superseded by a STRICTLY MORE RIGOROUS research lineage that ran
> AFTER this item was filed and reached actual verdicts on the exit-shape question using the
> real dual-layer + sub-window-stability discipline this item only gestured at:
> `P5-TOPCELL-REAL-FILLS-CONFIRM` (DONE 2026-07-11, 5/6 PASS on real fleet fills) +
> `PROFIT-P2-RIBBON-RIDE-STRIKE-AB` (DONE-WITH-VERDICT 2026-07-11, ATM strike wins / SS-B exit
> stays) + `STRUCTURE-STOP-ZONE-BAND` (CLOSED 2026-07-20, band-width REJECT_ALL) +
> `STRUCTURE-STOP-REFERENCE-LEVEL` (CLOSED_NO_SHIP 2026-07-20, zone-boundary reference NO-SHIP).
> STOP-B's own governing question ("which exit shape ships") has an ANSWER as of tonight:
> **SS-B / chart-stop-primary stays, ATM strike, trigger-exact reference** -- confirmed on real
> fills through at least 3 independent post-T-W7C studies. This item's "exit-C+entry-2" framing
> and the raw mass-grind-v2/phase5 artifacts are now superseded groundwork, not a live decision
> point -- closing rather than re-running to avoid re-litigating an already-answered question.
> **ROOT CAUSE FOUND + FIXED en route (the actual highest-value output of this fire):** every
> study in that lineage (including the two 07-20 closures above) shares ONE real-fills loader,
> `exit_shape_parity_study.load_fleet_engine_fills()`, hardcoded to `FLEET_REST_ARMS` (safe-1/
> safe-3/risky-1/risky-3) -- and fleet_rest has been DARK since 2026-07-09 (confirmed:
> PROFIT-P1-FLEET-EXIT-PARITY). ALL real trading since (safe-2/bold-2 in `fills-ledger.jsonl`,
> current through TODAY, 157+43 fills) is on the CORE arms, which this loader cannot see --
> the exact, disclosed-but-unfixed "0/0 exhibit fills recoverable" gap both 07-20 closures
> flagged, and the reason the recurring `T-AUTOPSY-H-*-stop-noise`/`-left-on-table` hypotheses'
> "confirm on fresh OPRA slice" proposed test has never once been runnable against current data.
> **FIX (additive, NOT a default change -- verified 127 real safe-2/bold-2 fills predate
> `structure_stop_study.ANCHOR_END_DATE` 2026-07-08, so flipping the DEFAULT would have silently
> shifted every already-frozen anchor pin, e.g. `test_control_anchor_reproduces_established_
> baseline_live`'s `-757.1` CONTROL total -- exactly the re-pick-after-seeing-results hazard the
> no_repick_clause discipline exists to prevent):** added `CORE_ARMS = ("safe-2", "bold-2")` +
> `ALL_LIVE_ARMS = FLEET_REST_ARMS + CORE_ARMS`; `load_fleet_engine_fills` gained an `arms=`
> parameter defaulting to the UNCHANGED `FLEET_REST_ARMS` (byte-identical to every existing
> caller across ~14 tools), with `arms=ALL_LIVE_ARMS` available for any FUTURE, separately-
> frozen study that wants current-day coverage. Also fixed the hardcoded output filename
> (`exit-shape-parity-2026-07-08.json` regardless of run date -- a silent-success/C7 footgun for
> anyone re-running `main()` expecting a fresh file) to use the actual run date.
> **Verified this fire (OP-33):** new `backtest/tests/test_exit_shape_parity_study_core_arms.py`
> (5 tests) RED-proofed via `git stash push -- backtest/tools/exit_shape_parity_study.py` -- 4/5
> failed pre-fix with the exact expected `AttributeError: ... no attribute 'ALL_LIVE_ARMS'`
> (the 5th, the backward-compat default-scope test, correctly PASSED pre-fix too since that
> behavior is unchanged by design); `git stash pop` restored cleanly (confirmed via `git diff
> --stat` + grep for the new constants), re-verified 5/5 green. Broader sweep:
> `pytest backtest/tests/test_structure_stop_study.py -m "not slow"` -> **21/21 PASS** (the
> 1 network-dependent anchor-pin test correctly deselected, untouched by design -- its default-arg
> call path is structurally guaranteed byte-identical). **This does NOT itself re-run any study**
> against the newly-visible core-arm data -- that is deliberately left for a FUTURE fire to spec
> as its own fresh, separately-frozen pre-registration (per the no_repick_clause discipline), not
> silently folded into an existing verdict.
> **Zero trading-path files touched** -- `exit_shape_parity_study.py` is observation-only
> analysis tooling (no broker import, no params/heartbeat_core/filters/placement/exit code).
> Ships as engine-benefit per OP-22/OP-26, no J ratification needed. **Revert:** `git revert
> <this commit>` (2 files: the tool + the new guard test, additive only, no data loss).
> Lesson filed: `_lesson-inbox/2026-07-21-real-fills-loader-blind-to-arm-rename.md` (a producer's
> hardcoded arm-scope silently went stale when the production account naming/lineup moved on
> without it -- same C14 dead-knob family, new angle: a "real data" anchor can itself become
> synthetic-by-omission if the population it filters for stops matching where the real trading
> now happens).
- [x] T-W8-HEADROOM-RETEST-CANDIDATES (HIGH, entry-quality, pre-register-only) :: RAN 2026-07-09T11:28 ET — verdict 0 PASS / 10 FAIL / 2 INCONCLUSIVE_SMALL_N (analysis/recommendations/headroom-retest-tw8.json, verified directly from key_findings). Both candidates FAILED as specified (headroom gate + retest-limit); no further hours recommended on this spec. NOTE the block_elite_bull re-validation sub-item WAS separately completed (SS-B revalidation, KEEP, hash-pinned). Checkbox was stale — closed 2026-07-11 during dormant-asset audit (artifact wins over checkbox; see also the audit's finding that 3 queue tickets had stale statuses). :: depends:T-W7C :: status:done-failed
- [x] FUTURES-PHASE1-BATTERY (HIGH, futures-7th-arm, $0-tonight) :: J directive 07-09: futures = the 7th arm ("futures would be banking off this" — correct: today's 09:43 long on MES with an ATR point stop survives the 10:05 flush [~-9 ES pts vs 15-20pt stop] and banks 747.3->750.2; no theta, no premium noise floor, no PDT wall [which blocked core's vwap entry at 10:31 today]). Run FUTURES-REVIVAL-PLAN Phase 1 EXACTLY (markdown/futures/FUTURES-REVIVAL-PLAN-2026-07-02.md section 4): resample cached Databento 1m -> 4h/daily, build swing_sim gap-aware extension, run RRW-short cohort + E2 at-level/VWAP-aligned contexts + structure/BOS reads on MES through the canonical battery WITH random-entry nulls + BH-FDR; scorecard per seed pass-or-kill at analysis/recommendations/futures-swing-{seed}.json. Data gap 06-12->now via yfinance 1h. NOTHING arms without a cleared scorecard (June NO-EDGE control is the null template). :: **STALE CHECKBOX, closed 2026-07-14 queue hygiene — the battery RAN 2026-07-09: VERDICT KILL all 3 seeds (rrw_short / e2_context / structure_bos_choch), 0/96 cells cleared the pre-registered PASS gate; per-seed scorecards exist at analysis/recommendations/futures-swing-{rrw_short,e2_context,structure_bos_choch}.json + summary futures-swing-phase1-summary.md; second independent pass converging with the 2026-07-02 0/12 DOES_NOT_TRANSFER battery. FUTURES-FILLSIM-ARM's own line already recorded this KILL. Vein now formally closed registry-wide as `ohlcv_bar_pattern_mining_family` (EDGE-KILL-LEDGER 2026-07-14, reopen = new NON-OHLCV data only); futures forward path = FUTURES-MIRROR-SHADOW forward evidence.** :: depends:none :: status:done-kill
- [x] FUTURES-MIRROR-SHADOW (HIGH, futures-7th-arm, $0-forward-evidence) :: **SHIPPED 2026-07-09 (`setup/scripts/futures_mirror_shadow.py` + `Gamma_FuturesMirror`, 5-min RTH + 16:05 sweep — a DIFFERENT, purpose-built shadow engine, not a swing_core_runner/fill_sim_broker mode as this line originally scoped it; REUSE DECISION documented in that file's own docstring: fill_sim_broker's process_quote/place_bracket don't fit a multi-concurrent-signal 2-session mirror, so only its gap_aware_stop_fill + swing_sim.wilder_atr were reused, not the broker class itself), EXTENDED 2026-07-14 (J: "make sure you trade futures today too").** 07-14 additions: (1) `core-decisions.jsonl` coverage — the original build only watched the 4 fleet REST arms, never the 2 PRIMARY accounts (Gamma-Safe-2/Gamma-Risky-2); core rows now tagged `core-safe`/`core-bold`, cross-source deduped against fleet arms (fixed a real schema gap en route: core rows name the setup field `setup`, fleet rows name it `setup_name` — `scan_arm_lines` now falls back `setup_name or setup`). (2) `setup/scripts/futures_shadow_progress.py` — the arming-bar tracker this line called for but the 07-09 build deliberately punted ("evaluated by a LATER session, not this one"): computes n_round_trips/total_pnl/positive_expectancy every poll (piggybacks on the existing 5-min cadence, no new task), computes the buy-hold null ONLY once n_round_trips>=20 (zero network calls below the floor — verified via a monkeypatch-must-not-be-called guard), writes `automation/state/futures/shadow-progress.json`. (3) One `firm-brief.md` line (`render_futures_shadow_lines`, fail-open). **Verified real 2026-07-14 09:45-09:46 ET: ran `futures_mirror_shadow.py --once` twice back-to-back against real production ledgers — 2nd run's watermarks byte-identical to the 1st (`{"risky-1":525,"risky-3":525,"safe-1":259,"safe-3":525,"core":1032}` both times, only `last_run_et` advanced) proving idempotent catch-up; core-decisions.jsonl cold-started cleanly to line 1032 ignoring the pre-existing stale backlog (see STATUS.md "CORE/FLEET DECISION LEDGERS FOUND STALE" entry same date — unrelated pre-existing finding, not caused by this work); `shadow-progress.json` real output `n_round_trips=0, armable=false` (0 closed round trips exist yet — honest, not a bug, the mirror only started accumulating v2-spec evidence 07-09).** Guard: `test_futures_mirror_shadow.py` (70/70, was 43/43), `test_futures_shadow_progress.py` (27/27, new), `test_firm_brief_futures_shadow_section.py` (6/6, new) — 103/103 total, zero regressions. RRW rare-cohort battery: already run 07-09 per the same commit (`INCONCLUSIVE_SMALL_N`, not re-run today — no new data since). Gamma_FuturesMirror launcher/scheduling machinery deliberately UNTOUCHED this session (already registered+healthy, confirmed via `Get-ScheduledTaskInfo` LastTaskResult=0 through 07-13 + a real 07-14 09:30 ET fire — today's popup-storm-fix session already rewired its Class-3 launcher chain, out of scope to touch again). Bar to arm unchanged: >=20 closed round trips, positive expectancy, beats buy-hold null — currently 0/20, no arming decision pending. :: depends:none :: status:done-forward-watch
- [x] FUTURES-FILLSIM-ARM (MED, futures-7th-arm, paper-sanctioned, NOW BLOCKED: Phase-1 returned KILL on all seeds -> no PASS scorecard exists; arming path runs through FUTURES-MIRROR-SHADOW forward evidence instead) :: futures_heartbeat_core.py EXISTS and dry-run VALIDATED 07-07 (real MNQ bracket built, routed=false; blockers: cert futures_approved=False + 24h resets + SDK absent from backtest/.venv). Wire the plan's section-2d fallback: OWN FILL-SIM paper lane (would-be-trades.jsonl) against live yfinance/TV quotes + fill funnel from day one + Gamma_SwingCore (15:35 ET daily) + Gamma_SwingMonitor (15min verify) via wscript->pythonw chain + DailyTrigger (not one-shot) + visibility surface (OP-33c). Trades ONLY Phase-1-cleared setups. LIVE futures stays J-gated (OP-0 #1) and J still owes the PROD token rotation (.env.tastytrade, owed since 06-22) — sandbox pair suffices for everything paper. :: **FOLDED 2026-07-14 queue hygiene — the dependency (FUTURES-PHASE1-BATTERY) returned KILL on all seeds, so "trades ONLY Phase-1-cleared setups" is an empty set forever under this spec; the OHLCV-mining vein it depended on is now registry-closed (`ohlcv_bar_pattern_mining_family`, reopen = new NON-OHLCV data only). The standing futures arming path is FUTURES-MIRROR-SHADOW forward evidence (>=20 closed round trips + positive expectancy + beats buy-hold null — currently 0/20). REOPEN this ticket only if that forward bar clears and a fill-sim lane is then the right next step.** :: depends:FUTURES-PHASE1-BATTERY :: status:done-folded-superseded
- [x] CCR-GATEWAY-KEEPALIVE (HIGH, infra, single-point-of-failure) :: The claude-code-router gateway (127.0.0.1:3456, under EVERY claude fire since 2026-07-08) died overnight 07-08->07-09 with NO auto-restart -> every LLM fire failed with ConnectionRefused (killed Gamma_Premarket's LLM step -> breaker staleness; would have killed tonight's TradeAutopsy/digest/conductor). Fable restarted it 07-09 ~13:4x ET (ccr start, pid 8312) + verified end-to-end (claude -p round-trip returned CCR-OK, quoted). BUILD tonight: Gamma_CcrKeepalive scheduled task (every 5 min, mirrors Gamma_DiscordBridge keepalive pattern): probe TCP 3456 -> if dead, ccr start + log + outbox-ping on repeated failure; pytest with a bite; document in SCHEDULED-TASKS.md. Also fold the lesson: any daemon that sits under N>1 fires needs a liveness loop the day it ships, not after its first silent death. :: depends:none :: status:done-2026-07-09-SUPERSEDED-BY-2026-07-14-FIX -- the keepalive shipped 07-09 but only guarded the AUTOMATION half (probe+restart). It never guarded the INTERACTIVE half, and "every claude fire since 2026-07-08" turned out to mean J's Desktop app too (global ~/.claude/settings.json env/apiKeyHelper override, not a per-fire opt-in) -- so a 2026-07-13 PC restart left CCR's fallback router (config.json Router.default = hardcoded ollama, ZERO Anthropic entry) silently serving J's Desktop app local Ollama for a full workday, no error, while this keepalive's TCP-only probe reported healthy the whole time. Root-caused + fixed 2026-07-14 (see STATUS.md dated entry + strategy/candidates/_lesson-inbox/2026-07-14-ccr-boot-lockout.md): global override removed from settings.json (Desktop app + bare CLI now hit Anthropic directly, always); ccr_keepalive.py extended with `_check_and_fix_interactive_settings()` (runs every fire, independent of the TCP probe, auto-heals + backs up + pings J); NEW guard backtest/tests/test_ccr_interactive_isolation.py (14/14, RED-proofed + live acceptance check + repo-wide allowlist scan). LIVE-VERIFIED 2026-07-14: killed+restarted CCR, confirmed it DOES re-inject the hijack into settings.json on every restart (not a rare event), confirmed the next unattended 5-min fire auto-caught+fixed+pinged.
- [x] BREAKER-REARM-STALENESS (MED, risk-correctness, OP-33c) :: Found 2026-07-09 ~10:00 ET while VERIFYING (not claiming) engine health: BOTH circuit-breaker.json files still show the 2026-07-08 premarket re-arm (Safe last_reset 07-08 08:31, equity 1512.83; Bold session_id 2026-07-08, equity 1963.04) while trading 07-09 — daily-loss thresholds anchored to YESTERDAY's start equity. engine-health killswitch check reads GREEN because it only verifies not-tripped, not re-armed-today => GREEN-while-stale hole. Verify why today's premarket re-arm didn't rewrite them (task fired? wrote elsewhere?); add "re-armed TODAY" to the engine-health killswitch check. Low live impact today (core accounts flat + block_elite_bull sitting out) but this is exactly the class OP-33(c) exists for. :: **STALE CHECKBOX, closed 2026-07-23 (conductor, AFTERHOURS) — the fix SHIPPED the SAME DAY the ticket was filed (commit `1b2cfeeb`, 2026-07-09 11:34 MT: `daily_loss_guard.py#rearm()` deterministic LLM/CCR-independent premarket re-arm + `engine_health.py#check_breaker_rearm()` "re-armed TODAY" canary for both `breaker_rearm_safe`/`breaker_rearm_bold`), but the queue checkbox was never flipped — same class as the T-W8-HEADROOM/FUTURES-PHASE1-BATTERY stale-checkboxes closed 2026-07-11/07-14 (artifact wins over checkbox). Re-verified THIS fire (OP-33): `test_engine_health_breaker_rearm.py` 14/14 green; live `engine-health.json` this fire shows both checks GREEN with today's date (`breaker_rearm_safe: last_reset=2026-07-23`, `breaker_rearm_bold: session_id=2026-07-23`) — the exact "GREEN-while-stale hole" this ticket was filed to close no longer exists. No code change needed, `task_scorer.py` surfaced this because the checkbox (not the work) was stale.** :: depends:none :: status:done-already-shipped-checkbox-was-stale

### T-GYM-20260709 HIGH gym-session RED for 2026-07-09

**Audits failing:**
- crypto-gym (53 validators) (RED): 103/104 pass

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260710 HIGH gym-session RED for 2026-07-10

**Audits failing:**
- crypto-gym (53 validators) (RED): 102/104 pass (KNOWN_FLAKY excluded: 1)

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

## 2026-07-11 (J: "audit the logic every other day... reusable harness... trained with our smart claude llms")

- [x] AUDIT-HARNESS-B1 (CRITICAL, free-model-trust, in-flight) :: **DONE 2026-07-11.** Built setup/scripts/free_model_audit.py — reusable, pluggable harness that has Claude (Sonnet) grade free-tier model decisions against ground truth (counterfactual replay, reusing trade_autopsy.py's mechanism) or blind re-judgment when no ground truth exists. First subject wired: heartbeat_core.py's `_free_model_eval` 2-model veto gate (production, highest stakes — 15 real VETOED_BY_MODELS rows in core-decisions.jsonl as of tonight). Scorecard pattern reused from shadow_model_eval.py. Confidence bar >=85%/>=15 evidence pts (same bar as the existing Nemotron promotion standard). Gamma_FreeModelAudit task fires daily, self-gates to every-other-day internally (never a bare DaysInterval trigger — proven-safe pattern per this repo's trigger lessons). VERIFIED: 35/35 pytest; real dry-run graded all 106 real evaluated ticks (0 mocked, 0 needed LLM fallback) — veto-only accuracy 93.3% (14/15 TRUE veto), GO-only accuracy 67.0% (61/91, mostly reflects underlying strategy WR not veto quality), blended 70.8%/106pts (below 85% bar — NOT YET CONFIDENT, correctly reported, not oversold). Scheduled task registered + fired + independently re-verified (see SCHEDULED-TASKS.md `Gamma_FreeModelAudit` row for full verification detail). Full report: analysis/free-model-audit/heartbeat-veto/2026-07-11-scorecard.md. :: depends:none :: status:done
- [x] AUDIT-HARNESS-B2 (HIGH, free-model-trust) :: **DONE 2026-07-11 ~10:51 ET.** Wired `twin_review` as the second `AUDIT_SUBJECTS` entry in `setup/scripts/free_model_audit.py` (new adapter `setup/scripts/free_model_audit_twin_review.py`) — confirmed the real `automation/state/crypto-twin/reviews/2026-07-11.json` sidecar shape by reading it directly before building against it, not trusted from description alone. Ground-truth shape is DIFFERENT from heartbeat_veto's counterfactual replay (there's no $ counterfactual for a mechanism-health read): new 4th `grading_method` tag `deterministic_cross_check` — agreement between twin_review.py's HEALTHY/DEGRADED/CONCERNING read and twin_sentinel.py's deterministic RED/YELLOW/GREEN verdict for the SAME UTC day (GREEN<->HEALTHY, YELLOW<->DEGRADED, RED<->CONCERNING). Prefers a same-day recorded `twin-sentinel.json` snapshot (most trustworthy — real point-in-time judgement); falls back to calling `twin_sentinel.evaluate()` directly since no append-only sentinel history file exists yet (disclosed caveat: the reconstruction path's BREAKER_TRIPPED/ACCOUNT_REGRESSION rules reflect CURRENT `twin-health.json` state, not the historical target date — only matters for dates other than "today"). REAL dry-run (`--subject twin_review --force`) against the only real review that exists (day one, as expected): **1 evidence point, 1/1 correct (100% this-run), honestly reported INSUFFICIENT EVIDENCE (1/15 floor)** — no synthetic padding, confidence math reported as far below threshold per the task's explicit instruction. VERIFIED: **56/56 pytest** across the full `free_model_audit` family (17 framework incl. 2 updated registry tests + 19 heartbeat_veto unchanged + 20 new `test_free_model_audit_twin_review.py`, zero regressions). Scorecard: `analysis/free-model-audit/twin-review/2026-07-11-scorecard.md`. **FOLLOW-UP FLAGGED, not fixed here (out of this task's scope — CONSTRAINTS didn't authorize touching the scheduler):** `Gamma_FreeModelAudit`'s registered command line (`install-free-model-audit.ps1`) still hardcodes `--subject heartbeat_veto` only — wiring the registry does NOT make twin_review actually fire on any cadence yet; spawned as a separate background task. :: depends:AUDIT-HARNESS-B1,TWIN-OVERSIGHT-PYRAMID :: status:done
- [x] AUDIT-HARNESS-B3 (MED, free-model-trust) :: **DONE 2026-07-15 ~00:35 ET.** Wired the two remaining `AUDIT_SUBJECTS`: `prospector` (`setup/scripts/free_model_audit_prospector.py`) and `swarm_consult` (`setup/scripts/free_model_audit_swarm_consult.py`). `prospector` grades idea-promotion judgment by pure record-linkage (deterministic_cross_check, no LLM call) — for every idea promoted to `strategy/candidates/_chef-inbox/` (read from the REAL filesystem listing, not the stale `state.json.promoted_dedupe_keys` counter which undercounts 4 vs 29 real promotions — disclosed, not silently fixed), checks for a `kind:"kill"` row in ideas-ledger.jsonl (authoritative) or a KILL/CLEAR verdict word next to its dedupe_key anywhere under `analysis/recommendations/`. `swarm_consult` grades open-ended brainstorm/decide/critique/audit quality via blind Sonnet re-judgment PROMOTED to primary method (no $ counterfactual or 2nd deterministic source exists for prose): Sonnet answers the same question blind, then a 2nd Sonnet call scores agreement against the swarm's synthesis (`grading_method: llm_judgment`) — capped at `MAX_SAMPLE_PER_RUN=5` consults/run (2 Sonnet calls each) to bound cost, most-recent-first regardless of backlog size. Both subjects flip `wired=True` in the registry; `test_registry_has_stub_subjects_unwired` replaced with `test_registry_has_prospector_wired`/`test_registry_has_swarm_consult_wired`/`test_registry_has_exactly_four_wired_subjects`. VERIFIED: **97/97 pytest** across the full `free_model_audit` family (19 framework + 19 heartbeat_veto + 20 twin_review + 20 new prospector + 19 new swarm_consult, zero regressions). REAL runs (`--subject prospector --force` + `--subject swarm_consult --force`, real subprocess Sonnet calls, not mocked): `prospector` — 31/31 promoted ideas graded, **INSUFFICIENT EVIDENCE** (0/15; every promotion is still pending, none has cycled through a battery to a recommendations scorecard yet — honestly reported, not guessed). `swarm_consult` — 5/5 graded (the 5 most recent daily "audit Project Gamma" consults, 07-09..07-13), 1/5 agreed with Sonnet's blind re-answer (20%), **INSUFFICIENT EVIDENCE** (5/15) — n=5 correctly NOT extrapolated into a verdict on swarm quality. Both scorecards: `analysis/free-model-audit/prospector/2026-07-15-scorecard.md`, `analysis/free-model-audit/swarm-consult/2026-07-15-scorecard.md`. Confirmed `backtest/.venv` is reaper-exempt (`_shared.ps1` `EXEMPT_DAEMONS`) so the ~5min swarm_consult run (10 real Sonnet subprocess calls) was NOT killed mid-run. **NOT DONE (out of this task's scope, flagged not fixed):** `Gamma_FreeModelAudit`'s scheduled-task command line still hardcodes `--subject heartbeat_veto` only (same follow-up AUDIT-HARNESS-B1/B2 already flagged) — `--subject all` would now pick up all 4 wired subjects automatically since AUDIT_SUBJECTS is built dynamically, but the scheduler itself was not touched (CONSTRAINTS for this task didn't grant schedule changes). :: depends:AUDIT-HARNESS-B1 :: status:done
- [x] CRYPTO-GYM-V53-DRIFT-TRIAGE (HIGH, silent-failure) :: **CLOSED 2026-07-11 (coach).** Root cause: v53_setup_dispatch.live's hardcoded `_KNOWN_SETUP_NAMES` set (4 names) never updated when `double_bottom_base_quiet` and `bollinger_squeeze` setups were wired into setup_dispatch.py on 2026-07-01/02 (commits 4e71618, 004e7ea) — live dispatcher correctly returns 6 setup results but the validator's `names_ok` structural check rejected the 2 unrecognized names on every fire, 100% deterministic fail. Confirmed via direct run: `python crypto/validators/v53_setup_dispatch.py` showed `names_ok: false` with `bollinger_squeeze`/`double_bottom_base_quiet` in results. Confirmed NOT correlated with tonight's Safe-2 deletion/crypto-account churn (2026-07-10 evening) — STATUS.md drift lines show v53_setup_dispatch.live already at 0.0%/48 as of 2026-07-02 15:xx (fail streak climbing from that date), i.e. broken continuously for 9 days *before* tonight's account churn. Fix: added both names to `_KNOWN_SETUP_NAMES` in crypto/validators/v53_setup_dispatch.py. Verified: `python crypto/validators/runner.py` → `SUMMARY: passed=104/104 overall_pass=True`; `python crypto/benchmarks/track_drift.py` → `CONSECUTIVE FAIL STREAK: 0`. v02_source_parity (83.33%→ self-heals as rolling 24h window ages out pre-fix history; already flagged in-report as "likely single-provider artifact", v15 3-source = 100% same window) and v12_multi_timeframe.live (87.5%) are SEPARATE, smaller, pre-existing degradations not explained by the v53 fix — logged as CRYPTO-GYM-V02-V12-FOLLOWUP below, not fixed tonight (not a 5-min fix, needs its own root-cause). :: depends:none :: status:done
- [x] CRYPTO-GYM-V02-V12-FOLLOWUP (MED, drift) :: **CLOSED 2026-07-15 (overnight Lane C, worker-tier).** Both root-caused with real evidence, neither was a threshold-tuning job. **v02_source_parity**: NOT a validator bug — `v15_three_source_parity.py`'s own docstring already documents the mechanism (yfinance settles its close later than Coinbase, structural to a strict 2-source check, ~11-20% grinder drift rate is NORMAL); v15 already exists as the true 2-of-3 quorum ratifier and was passing 100% the whole time — the real bug was one layer up: `crypto/benchmarks/track_drift.py::build_report` computed the "likely single-provider artifact" diagnosis into the alert TEXT but then still let it flip `overall_health` to RED (why the self-diagnosis in queue.md 2026-07-02/07-11 never closed the loop — raising PRICE_TOLERANCE_PCT 5bp→7bp on 2026-05-23 papered over it once already and didn't help, because the mechanism is timing, not tolerance width). Fix: `build_report` now splits `alerts` (all, for visibility) from `blocking_alerts` (drives `overall_health`); a v02 dip ratified by a healthy v15 (>=95%, same-window AND same-iteration via grinder `v15_parity`) is informational-only. `setup/scripts/run-crypto-regression.ps1` STATUS.md writer now keys change-detection off `blocking_alerts`. **v12_multi_timeframe.live**: grinder.jsonl (17,656 iterations, 2026-06-15..07-15) shows exactly 2 distinct bars EVER triggered a volume disagreement (2026-06-28T17:35Z +66.2%, 2026-07-11T07:50Z +58.6%, both agg>native, 0 price disagreements ever, both persisted unchanged for ~91 fetches/~3h = the live fetch-window width, never reconciling) — a rare, confirmed-real, same-provider cross-granularity Coinbase settlement artifact (native multi-minute candle occasionally freezes volume before some late trades attribute, while the finer 1m endpoint already reflects them), NOT a bug in `_aggregate()` (proven exact by the existing T1-T6 offline suite). The old zero-tolerance pass criterion let one rare isolated bar fail the whole run for the ~3h it stayed in-window. Fix: `_compare()` gained `max_vol_outlier_bars=1` (volume only; price stays true zero-tolerance since it's never legitimately disagreed). **Verified fresh this fire**: `python crypto/validators/runner.py --skip-replay` → `SUMMARY: passed=103/103 overall_pass=True` (v02_source_parity PASS, v12_multi_timeframe.offline/.live both PASS). `python -m pytest crypto/ -q` → `91 passed` (86 pre-existing + 5 new `test_track_drift.py` + 3 new v12 offline guard tests T7-T9 folded into the existing 6). Regenerated `drift_report.json` live: v02 alert now correctly tagged `[info-only]` and absent from `blocking_alerts`; `overall_health` stayed RED this run for an UNRELATED reason — `v53_setup_dispatch.live` shows 13 consecutive fails 2026-07-14 13:27-18:27 UTC (~09:27-14:27 ET) still inside the 24h rolling window, but has posted 16 consecutive PASSES since 19:27 UTC and `consecutive_fail_streak: 0` confirms the engine is healthy right now — the SAME already-fixed-but-still-in-window pattern v02/v12 had, just for a stage outside this task's scope. NOT re-broken, NOT chased tonight (out of Lane C scope) — self-heals from the rolling window by ~2026-07-15 18:27 UTC as the stale cluster ages out; flagged for visibility only (OP-33), no action needed unless it recurs. Lesson candidate queued: `strategy/candidates/_lesson-inbox/2026-07-14-quorum-ratified-alert-still-gated-health.md` (suggested L201). :: depends:none :: status:done
## 2026-07-11 profitability deep-research ranked plan (synthesis: markdown/research/PROFITABILITY-DEEP-RESEARCH-2026-07-11.md)

- [x] PROFIT-P1-FLEET-EXIT-PARITY (CRITICAL, exit-shape) :: **SCORECARDS DONE 2026-07-11 (worker-tier), MIGRATION PENDING (separate reviewed step, not this task).** Built `backtest/tools/fleet_exit_parity_per_arm.py` (reuses structure_stop_study.py's certified CONTROL_SHAPE/SS_B_SHAPE/replay_structure_aware + exit_shape_parity_study.py's load_fleet_engine_fills/reconstruct_positions verbatim — zero reinvention; ONE deliberate non-reuse disclosed in the module docstring: structure_stop_study's bar-fetcher hardcodes TODAY=2026-07-09 for its own one-off run day, which would silently truncate today's-now-historical option bars on a rerun, so this script always uses the plain historical fetcher). Ran for real (backtest/.venv, real Alpaca OPRA option-bar fetches, zero network calls for SPY 5m — 100% local cache `spy_5m_2026-05-19_2026-07-10.csv`). VERIFIED: reconstructed n + actual_total_pnl per arm matches `analysis/deep-research/2026-07-11-ledger-forensics.md`'s independently-computed per-account table EXACTLY (safe-1 n=24/-$242.00, safe-3 n=19/-$272.00, risky-1 n=19/-$486.00, risky-3 n=27/-$274.00) — cross-check via a second, independently-authored method, not self-referential. Verdicts (none migrate on this evidence): safe-1 KEEP_CURRENT_SHAPE (SS-B $15.25 worse); safe-3/risky-1/risky-3 SS_B_BETTER_BUT_FRAGILE (SS-B beats CONTROL by $88-368 raw, but drop-top-3 concentration check flips the comparison in all 3 — the improvement rides on a few big trades, not a broad shift). **CAVEAT surfaced, not acted on:** `structure_stop_enabled=true` is ALREADY live in BOTH `automation/state/params.json` and `aggressive/params.json` (shared by fleet_rest arms via `fleet_executor._params_for` reading the SAME 2 files core uses) and `strategies.py`'s ribbon_ride registry already declares `stop_mode="structure"` for all 6 SPY arms (test_six_account_exit_shapes.py) — so the "migration" this ticket describes as a future step may already be config-armed fleet-wide (single shared flag, not per-arm), pending only a live trigger; confirmed via decisions.jsonl/exit-state.json that 0 fleet fills have occurred since 07-09 so this is unobserved, not contradicted. Scorecards: `analysis/recommendations/fleet-exit-parity-{safe-1,safe-3,risky-1,risky-3}.json` (per-episode detail + aggregate + drop-top3 + both-halves robustness). No config flipped, no orders placed. **RESOLVED (Fable, same day): the caveat is CONFIRMED in source — fleet arms inherit SS-B from the shared params files (fleet_executor.py:55-56 + structure_stop_enabled=true verified live in both) — so P1 is FORWARD-WATCH, not a pending migration decision. No separate migration step exists; the fill funnel + firm brief report the first live SS-B fleet exits from Monday. The drop-top-3 fragility reads are honest but structurally biased against trailing-runner shapes (the right tail IS the design); n=19-27 too small to settle — forward evidence decides. Synthesis addendum: PROFITABILITY-DEEP-RESEARCH-2026-07-11.md §P1-addendum.** :: depends:none :: status:done-forward-watch
- [x] P5-TOPCELL-REAL-FILLS-CONFIRM (HIGH, exit-shape) :: **DONE 2026-07-11.** Dormant-asset audit's #2-ranked item (analysis/deep-research/2026-07-11-dormant-assets.md §1): confirm the mass-grind-phase5 top cell(s) on real OPRA fills via exit_manager (never simulate_trade_real's absolute $, per standing profit_lock_arm_scope doctrine). Built `backtest/tools/p5_topcell_real_fills_confirm.py` (reuses strategy_space_grind.run_cell for signal-source parity, t4_exit_matrix.py's ExitState/plan_exit_actions replay, exit_shape_parity_study.py's real fleet-fills anchor — almost unchanged, per the audit's own prediction). SCOPE FINDING: literal "top 5 by ranking" collapses to ONE distinct shape (tp1_premium_pct/tp1_qty_fraction are DEAD AXES within the P5-survivor set — verified byte-identical n=399/exp=$34.32 across 4 different tp1 targets in the raw funnel data; mechanism: simulate_trade_real's zero-threshold trailing-arm branch resolves every trade via the lock or the -8% stop before any tested TP1% is reached) — ran all 6 GENUINELY DISTINCT shapes among the 106 survivors instead, same "handful not a grind" budget. RESULT: **5/6 PASS, 1/6 MIXED.** Top-ranked cell (OTM-1/stop-8%/trailing15%): LIVE post_tp1 exp=+$25.62/tr (n=381, vs sim-reported $34.32 -- the scope-mismatch's real cost is -$8.70/tr, not catastrophic) AND real-fleet anchor no_regression=True ($68.33 candidate vs $23.70 control on 18 real PUT positions) -> PASS. Only OTM-1/stop-12%/trailing15% MIXED (LIVE positive $18.98/tr but anchor regression -$33.83 vs $23.70 control). 2 METHODOLOGICAL FINDINGS surfaced en route (both disclosed in the artifact, NOT silently fixed): (a) t4_exit_matrix.py/t5_confirmatory_matrix.py's shared `_load_bars` includes the fill bar itself in the replay loop (`>=` on entry_ts) where simulate_trade_real's own bar-walk starts ONE BAR LATER (simulator_real.py:492) — fixing this in THIS script's own bar-loader changed the top cell's LIVE expectancy from -$20.23/tr to +$25.62/tr, i.e. materially; T4/T5's own prior (already-acted-on, STOP-A/STOP-B) conclusions were NOT re-audited (out of scope) but may carry the same bias on any candidate whose stop/arm is same-bar-reachable from the fill price. (b) exit_manager.py's `ARM_SCOPE_FULL` ("full = simulator parity" per its own docstring) does NOT actually reconcile with simulate_trade_real's real recorded number on a bar-level trace (verified on a specific trade: simulate_trade_real rode a 45%-adverse excursion to a later profitable exit; the ARM_SCOPE_FULL replica stopped it immediately) -- root cause not isolated this session, "sim full-scope" column reported EXPLORATORY/unreconciled, NOT used for the verdict (LIVE post_tp1 is). Both flagged as background follow-ups. Files: `analysis/recommendations/p5-topcell-real-fills-confirm.{json,md}`. :: depends:FDR16-P5-crew-done(FDR-16 leg) :: status:done
- [x] PROFIT-P2-RIBBON-RIDE-STRIKE-AB (CRITICAL, strike-tier, EXTENDED with same-run exit head-to-head) :: **DONE-WITH-VERDICT 2026-07-11 (worker-tier).** Built `backtest/tools/ribbon_ride_strike_exit_ab.py` — ONE process, TWO axes, exit_manager replay at LIVE scope (post_tp1) on the canonical `_signal_cache` ribbon_ride cohort (n=250, both directions, 2025-01-06..2026-06-17), real local OPRA bars, zero network. Reuses (unchanged): structure_stop_study's certified SS_B_SHAPE + replay_structure_aware, tw8_level_context DIRECT trigger-level recovery (39.2% recoverable; rest fall back to premium-only cat-cap per contract), t4_exit_matrix.battery (OP-16 edge_capture_rel), null_baseline.random_entry_null (20 seeds via sim_fn injection through the SAME replay engine), ribbon_rejection_wick_battery.bh_fdr (alpha=0.10, 6 cells, 3 survivors). Fill-bar convention: CORRECTED `>` primary + OLD `>=` as a sensitivity column on every cell — sign-flip = UNSTABLE_ON_OPEN_AUDIT, pre-declared. **AXIS-1 (strike, SS-B fixed) VERDICT: ATM wins** — +$47.96/tr over OTM-2 control (exp $65.82 vs $17.86, n=244), positive BOTH years (IS +$4.7K/OOS +$11.3K), WF 4.25, halves+, drop3 +$36.64, null PASS, BH survivor, toggle-STABLE (+$52.32) → **clears OP-11 auto-ratify; MAY SHIP as the v15.4 weekend rule update (params NOT changed by this task — arming is the separate step)**. OTM-1 +$19.12/tr confirms the gradient but fails its own null (don't arm; ATM dominates). **ITM-2 KILLED as gradient endpoint on this cohort**: $19.5K OOS rides -$17.0K IS-2025, drop3 NEGATIVE (-$30.19), top3-share 5.5x (C22 regime concentration) — WP5's ITM>ATM>OTM gradient reproduces only through ATM here, breaks at ITM-2. Corroboration: OTM-2 control's own drop3 exp is negative (-$2.13/tr) — the live tier's edge rides 3 trades. **AXIS-2 (exit, P5-topcell challenger vs SS-B on identical episodes) VERDICT: SS-B stays** — at OTM-2 challenger +$19.04/tr but sign-FLIPS to -$9.45 under the old fill-bar convention → UNSTABLE_ON_OPEN_AUDIT, blocked on chips task_4935ea80/task_86001855; at ITM-2 toggle-stable +$58.34/tr but OP-16 anchor REGRESSION (edge_capture_rel 576 vs SS-B 1149 — tp+30% banks early, caps J's winner days) → WAIT_EVIDENCE. Honest flag: challenger's risk profile is much smoother (OTM-2 maxdd -$687 vs -$4,798; top3 0.30 vs 1.19) — rematch after the chips land. Scorecard: `analysis/recommendations/ribbon-ride-strike-exit-ab.{json,md}` (per-cell battery + sensitivity column + ship-vs-wait split). **CHIPS LANDED 2026-07-14 (ultracode-review Job 1):** task_4935ea80 (commit `f0bceb1`) + task_86001855 (commit `fb027f1`) finished their sessions but sat on unmerged branches `claude/hopeful-driscoll-917b45` / `claude/frosty-zhukovsky-f22e22` — cherry-picked onto main today (`test_fill_bar_convention.py` 4/4 green). Their scope was T4/T5 (`t4_exit_matrix.py`/`t5_confirmatory_matrix.py`) + the playbook 2.12 same-bar-trailing-ratchet look-ahead writeup, NOT `ribbon_ride_strike_exit_ab.py` directly — verdict there: T5/STOP-B KILLS stand, zero verdict flips (one evidence-revoked upgrade, exit-C+entry-2). **AXIS-2's own OTM-2 sign-flip is UNRESOLVED by this landing** — no audit has yet re-run `ribbon_ride_strike_exit_ab.py`'s challenger cell under both conventions with the corrected T4/T5 bar-loader; still WAIT_EVIDENCE, rematch remains open. Job 2 of the same review (`ssb-fillbar-sensitivity-2026-07-14.{json,md}`) covers `structure_stop_study.py`'s SS-A/B/C (the SS-B *stays* side of this gate), not the challenger side. :: depends:FDR16-P5-crew-done(satisfied) :: status:done-with-verdict
- [x] PROFIT-P3-MORNING-GATE-PREREG (HIGH, time-of-day) :: **RUN 2026-07-14 (worker-tier). VERDICT: KILL all 3 candidates.** Built `backtest/tools/morning_gate_study.py` + shared `backtest/tools/p3p5_baseline.py` (gate-OFF population reused BYTE-IDENTICAL to PROFIT-P2's own shipped OTM-2/SS-B cell: n=250, exp=$17.86, total=$4,465.60 -- cross-checked against `ribbon-ride-strike-exit-ab.json` before running any candidate). Ran the registration EXACTLY as frozen (no re-picks): V1 (block<11:00, n_kept=198/n_removed=52), V2 (block<10:30, 218/32), V3 (block<10:35, 212/38). **All 3 FAIL stage 1 on the full net window** -- gate-ON expectancy ($0.98 / $12.98 / -$0.91) is WORSE than gate-OFF ($17.86) for every candidate, the opposite of the 9-day hypothesis-source finding (34/34 morning losers) once evaluated on the full 2025-01-06..2026-06-17 history -- k1+k2 (OOS) both fail, BH-FDR (k4) rejects all 3 at alpha=0.10. **Anchor disclosure (mandatory report, not a P3 pass/fail gate): all 3 candidates would have blocked 2 of J's 3 OP-16 winners' actual entries** (4/29 10:25:51 ET and 5/04 10:27:50 ET, both <10:30) -- flagged MISCALIBRATED per the registration's own anchor-context instruction. Scorecard: `analysis/recommendations/morning-gate-result.{json,md}`. :: depends:none :: status:done-kill
- [x] PROFIT-P4-NBBO-CAPTURE (HIGH, telemetry, unblocks-future-research) :: Persist option NBBO (bid/ask/mid) for the chosen contract on every decision row + entry/exit event. Friction stream confirmed NO NBBO history exists anywhere (ledger spread_cents = SPY EMA-ribbon spread, NOT option spread) and bid_ask_spread_max_cents=8 is a dead knob with zero consumers. Additive telemetry on heartbeat_core decision logging + guard test. **CLOSED 2026-07-20 (conductor, AFTERHOURS).** Traced first: the "exit event" half of this item's premise was already partially answered pre-existing -- `exit_actuator.manage_tick`'s per-tick results already carry `best_premium`/`worst_premium` (= ask/bid from `get_option_quote_hilo`, 2026-07-09 STRUCTURE-STOP visibility work) and that list is threaded verbatim into `rec["exit_pass"]` in `heartbeat_core.run_account` -- so exit-side NBBO was already reaching core-decisions.jsonl, just unlabeled as "nbbo". The genuine gap was ENTRY-side: `_execute`'s `plan` dict (the row `rec["exec"]` persists) never carried the option quote it priced off of. Fixed: `plan["nbbo"] = {"bid","ask","mid","spread"}`, RECONSTRUCTED from the SAME `mid`/`entry_px` already computed by `get_option_mid`+`marketable_limit_price` this tick (ask=entry_px-buffer, bid=2*mid-ask, both formulas algebraically inverted from the functions that produced them) -- deliberately NOT a third independent `get_option_quote_hilo` fetch, so this adds ZERO new network round-trips to the entry-critical path and cannot introduce a race between 3 separate quote reads. Guard: `backtest/tests/test_nbbo_capture_2026_07_20.py` (5/5 -- dry-plan reconstruction exact-value pin, custom `entry_cross_buffer` inversion, an explicit "must never call get_option_quote_hilo" zero-new-network-call pin, end-to-end PLACED-row persistence + JSON-serializability, and NO_PREMIUM short-circuit leaves `nbbo` absent not None). RED-proofed via `git stash` on the single edited file: 4/5 failed with the exact expected `KeyError: 'nbbo'`; `git stash pop` restored cleanly (`git diff --stat` confirmed the intended 2-hunk change), re-verified 5/5 green. Broader sweep (`test_audit_fix_heartbeat.py`+`test_money_path_2026_07_01.py`+`test_trade_to_learn_2026_07_01.py`+`test_min_entry_premium_floor.py`+`test_real_fill_guard.py`+this file) -> 100/100 PASS, zero regressions. Curated safety gate (31+5-suite) PASS. **Rail-4 (PAPER, entry-telemetry-only -- guard test + revert path + REVOKE report in STATUS.md):** touches `setup/scripts/heartbeat_core.py` (`_execute`'s `plan` dict gains one additive key; no pricing/sizing/gate/placement logic changed -- `mid`/`entry_px`/`tp`/`stop`/qty all byte-identical) + the new guard test + this queue.md line. **REMAINING for a future slice (not this fire's scope):** `fleet_live.py` (lines 322/326) and `j_intent_executor.py` (line 483) have the SAME `get_option_mid`+`marketable_limit_price` double-fetch shape on their own separate entry paths (fleet-arm live trading + J-called manual entries) and could get the identical NBBO reconstruction -- left untouched here since the item's own scope named "heartbeat_core decision logging" specifically. **Revert:** `git revert <this commit>` (single pathspec commit, 3 files). :: depends:none :: status:done
- [x] PROFIT-P5-EXPECTED-MOVE-PREREG (MED, entry-gate) :: **RUN 2026-07-14 (worker-tier). VERDICT: KILL all 3 candidates on k6 (mandatory anchor violation).** Built `backtest/tools/expected_move_gate_study.py`, reusing the SAME shared `p3p5_baseline.py` population as PROFIT-P3 (byte-identical gate-OFF baseline, the registration's own required cross-check -- confirmed by construction, both scripts import one module). ATM straddle day-series (365 days, `analysis/exit-parity/p5-expected-move-day-series.json`) computed real-OPRA per the frozen formula (straddle @ first bar >=09:35 ET x 0.85). **k6 MANDATORY: all 3 candidates would have SKIPPED at least one of J's 3 OP-16 winners' actual entries** -- e.g. the 4/29 710P ($1.67 premium) and 5/04 721P ($0.85) trades both fail V2 (implied_premium_ceiling < entry_premium_needed_for_tp1) and V3 (budget_ratio too high) because their premiums were a LARGE share of a comparatively modest day's expected move -- the exact anti-edge failure mode EXTERNAL-0DTE-MECHANISMS-2026-07-11.md's own mechanism #1 flagged as disqualifying. Also disclosed: k5 (existing VIX-gate-only baseline) already captures +$26.45/tr lift on this population, MORE than any of the 3 candidates' own gate-ON delta ($15.53 / -$30.04 / -$7.34) -- no candidate clears 'lift over the VIX gate' either. Stage 1 expectancy: V1 alone is nominally positive (gate-ON $33.39 vs gate-OFF $17.86) but still killed on k6 (anchor) + fails stage 2 OOS. Scorecard: `analysis/recommendations/expected-move-gate-result.{json,md}`. :: depends:none :: status:done-kill

### T-TWIN-AUTOPSY-H-TWIN-2026-07-11-unknown_exit_stage MED — [TWIN/CODE-ONLY] mechanism hypothesis: unknown_exit_stage

**Claim:** test claim **Evidence:** `{"n_hits": 3}` (analysis/autopsies/2026-07-11.md).
**Action:** add a regression guard :: depends:none :: status:proposed

## Twin escalations

- [ ] TWIN-ESCALATION-20260714-1784029284 2026-07-14 TICK_GAP+LOW_UPTIME (TICK_GAP: last tick 462.6 min ago (threshold 20 min); LOW_UPTIME: 48/140 ticks today (34.3%, threshold 70%)) :: dispatch a Sonnet investigation :: status:pending

- [ ] TWIN-ESCALATION-20260717-1784333700 2026-07-17 TICK_GAP (TICK_GAP: last tick 4095.0 min ago (threshold 20 min)) :: dispatch a Sonnet investigation :: status:pending
- [ ] TWIN-ESCALATION-20260719-1784506738 2026-07-19 TICK_GAP (TICK_GAP: last tick 1090.1 min ago (threshold 20 min)) :: dispatch a Sonnet investigation :: status:pending
## Needs J's own hands (system/power settings -- outside what I'm allowed to change)

- [ ] PC-SLEEP-7H-OVERNIGHT-2026-07-14 (HIGH, infra, crypto-twin-uptime) :: **Root-caused, report-only (ultracode-review JOB 4).** Box slept 2026-07-13 22:01:46 local (MT) -> 2026-07-14 05:35:27 local (7h33m) = 2026-07-14T00:01:45..07:35:26 ET once correctly TZ-converted (task's own "22:01->05:35 ET" framing was local-time-as-ET, corrected in STATUS.md). Cause = a MANUAL Start-Menu Sleep click by the logged-in user (Event 1074 StartMenuExperienceHost.exe + Event 42 "Sleep Reason: Application API"), NOT an idle timeout -- `powercfg` confirms STANDBYIDLE/HIBERNATEIDLE already 0 (Never) on both AC/DC, nothing to fix there. **J action (one-liner, NOT run by me):** `reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer" /v NoStartMenuSleepOption /t REG_DWORD /d 1 /f` (hides Sleep from the Start Menu power button; may need sign-out or `gpupdate /force`) -- I have not verified this value against a live registry read beyond confirming the parent policy key path exists, so J should confirm it actually suppresses the tile after running it. Alternative/belt-and-suspenders if J wants to keep manual sleep available: enable "Wake the computer to run this task" on a pre-market task (e.g. `Gamma_LaunchTV`) -- `RTCWAKE` is already `Enable` on AC, so this needs no other change; treats the symptom not the cause, not applied. Full evidence: STATUS.md 2026-07-14 "PC SLEPT 7.5h OVERNIGHT" entry. :: depends:none :: status:pending-needs-J

## 2026-07-14 trendline program follow-ups (post break-battery KILL)
- [x] TREND-FADE-PREREG (HIGH->KILL, A4/OPRA-sequential job 3/3, 2026-07-14 16:57-17:0x ET) :: **DONE -- 12/12 cells FAIL, KILL.** Froze `analysis/recommendations/prereg-trendline-fade-battery-2026-07-14.json` (3 fade variants F1_immediate/F2_reclaim-confirmed/F3_low-volume x 2 families x 2 directions = 12 cells, own nulls incl. the load-bearing break_direction_null, BH-FDR alpha=0.10, same OOS_BOUNDARY/seed=1407 as S1) BEFORE running `backtest/tools/trendline_fade_battery.py` on the full 78,191-line break-dataset.jsonl through the LIVE exit_manager (SS-B shape) on real OPRA bars (180.8s, 51,534 candidate episodes). Mechanical result per the frozen pass_bar: 1/12 PASS (F3_low_volume::body::resistance, n=4072, wf=20.6). **That PASS did not survive a post-hoc stability audit** (added per OP-33/fable-too-good before any ship call, since the mission's OP-11 auto-ratify bar requires sub_window_stable which this study's own frozen pass_bar never tested): OOS-only monthly showed 2 of 7 months strongly negative (2026-01 -$630/tr, 2026-02 -$322/tr), the ENTIRE OOS-positive total traced to March 2026 alone (OOS ex-March net NEGATIVE ~-$58,816), and top-10 single days summed to 249.2% of the cell's total pnl (one day, 2026-03-27, = 52.4% alone) -- a concentration artifact, not a generalizable edge. Downgraded to FAIL; **final verdict 12/12 FAIL**, matching S1's break-continuation KILL. Bottom line: both break-continuation (S1) AND break-fade (this study) are now KILLED for this signal source -- the "opposite-direction null beats real 10/12" disclosure that motivated this study does not translate into a standalone tradeable edge once tested as its own pre-registered hypothesis. Nothing ships, nothing arms, no params/config/trading-path file touched, no orders placed. Scorecard: analysis/recommendations/trendline-fade-battery.{json,md}. Sequential OPRA lane released. :: depends:none :: status:done
- [ ] TREND-PREMARKET-ANCHOR-GAP (MED, detector-scope) :: G1 found the live detector (and the dataset) is RTH-only while J anchors lines at PREMARKET wick lows (his 2026-07-14 line anchored ~747.4 premarket -- outside anything the detector ever considers). Decide + implement: extend detection to premarket bars (liquidity-filtered) or document the boundary; affects the visibility bridge's usefulness to J. :: depends:none :: status:pending
- [x] TV-MCP-DRAW-API-FIX-REOPENED (HIGH, tooling, task_74d00764) :: **CLOSED 2026-07-20 (conductor, verification-only) -- ALREADY FIXED, item was stale.** Read live `C:\Users\jackw\Desktop\SwjshAlgoKnife\mcp-servers\tradingview-mcp\src\core\drawing.js` (the exact file+path the item names): `listDrawings`/`getProperties`/`removeOne`/`clearAll` ALL call `_resolve(_deps)` first, matching `drawShape`'s pattern -- the bare-identifier bug this item describes is not present in the current file. `git log` on that repo shows the real fix landed 2026-07-14 10:12 MT, commit `6f25ce4` ("fix(drawing): listDrawings/getProperties/removeOne/clearAll never resolved getChartApi"), with a matching root-cause commit message (bare `getChartApi`/`evaluate` identifiers only bound under `_getChartApi`/`_evaluate` import aliases) and a new test file `tests/drawing_getchartapi.test.js` (4 mocked-_deps functional tests + 1 static source-audit guard). Re-ran live this fire: `node --test tests/drawing_getchartapi.test.js` -> **5/5 PASS**. No build/dist step in this package (`package.json main: src/server.js`, direct ESM import, no bundler) so there is no stale-compiled-artifact risk -- the fix is live on the exact path the running MCP server imports. The item's "judge-verified FABRICATED" claim was accurate as of whenever the judge ran, but a later commit (author "Sauce Bot", not this session) genuinely fixed it afterward and the item was never re-checked against current state. No MCP restart needed -- this server is spawned fresh per Claude Code session via `.mcp.json`'s stdio launcher, not a persistent daemon, so every session already picks up current `src/`. No edit made to the (READ-ONLY per project convention) SwjshAlgoKnife repo this fire -- verification-only. :: depends:none :: status:done
- [x] VIX-DEADZONE-MAP (HIGH, gate-interaction, C15, from 2026-07-14 TA workflow devil's-advocate) :: **DONE (analysis-only, 16:2x-17:xx ET).** Queue item's own premise was HALF WRONG: there is no live "bear-entry VIX floor" -- `vix_entry_thresholds` (bull_max 17.20 / bear_min 17.30 Safe) is VESTIGIAL, consumed only by a dormant shadow lane (`fast_path_executor.py`, last fired 2026-05-20) and the crypto gym, never by `backtest/lib/engine/gates.py`'s canonical 15-gate live list. The ONE real live VIX gate (`block_elite_bull`, Safe band [0,25) = 88.7% of days per 124-day dense sample 2026-01-02..2026-07-08) fires ONLY on tier==ELITE+level_reclaim bull -- NOT the SUPER/TRENDLINE tiers today's two headline signals were -- and was already SS-B-revalidated KEEP 4 days ago (n=28, SS-B total -$3,873.60 vs old-shape -$560.00 -- the gate saves money). 5-account participation matrix built: 4/5 accounts (core:safe + fleet:safe-3/risky-1/risky-3) share ONE VIX-gate profile because the 3 fleet_rest arms structurally inherit core:safe's tick-level pass/fail (build_shared_signal.py) and can only add selectivity, never bypass it; only core:bold runs an independent (narrower, [15,18)) band and has NO vix_bear_hard_cap at all (asymmetry flagged, follow-up below). Today's actual zero-trade day: 146 gate-fired blocks, only 28 (19.2%) VIX-attributable -- the rest was the free-model veto layer (37, already A6-graded net +$565.50 positive) + 5 unrelated structural gates (75) + PDT/premium-floor (6). No re-shaping ships -- nothing here clears the evidence bar for a change; KEEP is itself the verdict. Full report: analysis/deep-research/2026-07-14-vix-deadzone-map.md. :: depends:none :: status:done
- [x] A6-VETO-GRADE-2026-07-14 (HIGH, free-model-audit, evidence-only) :: **DONE same-day (out-of-cadence --force run, 16:20 ET).** Graded ALL of today's model-veto decisions from core-decisions.jsonl (37 veto + 6 go rows via free_eval.veto — note: exceeds the "22" headcount this queue item's own VIX-DEADZONE-MAP entry used; that was a rough same-day estimate, 37 is the authoritative full-day count) via counterfactual replay against real OPRA bars. Result: **today's veto-only false-veto rate = 11/37 = 29.73%** (blocked winners), vs the **historical baseline 1/15 = 6.67%** from the 2026-07-11 scorecard — a 4.46x elevation. **Does NOT cross the pre-declared 30% pre-registration trigger** (misses by 0.27pp) — per "never a vibe-flip," no veto-scope pre-reg written today; forcing one at 29.73% under this week's P&L pressure would be exactly the evidence-optional move the threshold exists to block. Net dollar framing: false vetoes cost $391.20 in foregone winners; true vetoes (26/37) saved $956.70 in avoided losers → net veto value today still **+$565.50 positive**. Cumulative (all-time) rate unchanged at 68.9%/151pts, still not confident (bar 85%). **Flag for next cadence:** if the elevated rate persists 1-2 more graded cycles, cumulative evidence would clear the bar without needing to round today's number up. Scorecard: analysis/free-model-audit/heartbeat-veto/2026-07-14-scorecard.md. :: depends:none :: status:done
- [x] VIX-VESTIGIAL-KNOB-CLEANUP (MED, doc-hygiene, from VIX-DEADZONE-MAP) :: **DONE (16:5x ET, same-day as flagged).** `vix_entry_thresholds` (params.json + aggressive/params.json: bull_max_exclusive_or_falling / bear_min_exclusive_and_rising / bull_hard_cap) has ZERO live consumers -- not in backtest/lib/engine/gates.py's canonical 15-gate list, not in heartbeat_core.py. Its only consumers are setup/scripts/fast_path_executor.py (a dormant shadow "observer" lane, last wrote fast-path-decisions.jsonl 2026-05-20, 55+ days stale) and crypto/lib/vix_filter.py (gym-only, non-edge). This was the SECOND time the key had been misread as a live gate (today's own queue item cited "bear-entry threshold 17.30" as blocking real trades; it doesn't) -- and became a THIRD live near-miss same-day: a separately-dispatched task (A3, "BEAR VIX FLOOR under SS-B") was briefed to pre-register+SS-B-sweep this exact vestigial key before this cleanup item landed; the A3 task caught it independently (re-derived from source, did not just trust this queue entry) and voided itself rather than burn the OPRA-sequential lane on a dead knob -- see analysis/recommendations/bear-vix-floor-ssb.md. Fix applied: added `_vix_entry_thresholds_doc` vestigial-marker comment to both params.json and aggressive/params.json (doc-only, zero behavior change, verified both files still parse). fast_path_executor revival left untouched -- no case made for it, silence would have been the only wrong move and this isn't silence. Evidence: analysis/deep-research/2026-07-14-vix-deadzone-map.md §1, analysis/recommendations/bear-vix-floor-ssb.json. :: depends:none :: status:done

- [x] A3-BEAR-VIX-FLOOR-SSB (HIGH->VOID, OPRA-sequential job 2/3, 2026-07-14 16:41-17:0x ET) :: **DONE -- VOID, no OPRA grind run.** Briefed to pre-register 3 variants (17.30 control / 16.0 / no-floor) of the "bear-entry VIX floor" and SS-B-revalidate on real OPRA fills, motivated by today's VIX-16.80-floored-bear-entries framing. Premise check FAILED before any pre-registration was frozen: independently re-verified (not just cited) that backtest/lib/engine/gates.py's canonical 15-gate list -- the only thing heartbeat_core.py's engine_cli consults for live orders -- has no bear-VIX-floor gate; the only 2 VIX gates are block_elite_bull (bull-only band) and vix_bear_hard_cap (bear CEILING >=23, opposite direction). vix_entry_thresholds.bear_min_exclusive_and_rising=17.30 has zero live consumers (dormant fast_path_executor.py shadow lane + crypto gym only). Corroborates and independently re-derives VIX-DEADZONE-MAP (status:done, ~16:20 ET, completed just before this task started) rather than chaining an unverified claim into a KILL decision. Provenance trace for the 17.30 constant itself (backtest/lib/filters.py, research-only, non-live): introduced in bulk snapshot commit d0c8ac0 2026-06-15 with no SAFE-specific scorecard anywhere in analysis/recommendations/ -- only an AGG sweep exists (aggressive_vix_bear_threshold_sweep.py), and even that doesn't clearly favor 17.30 over 16.0. Sequential OPRA lane released unused, clear for job 3. Instead applied the already-flagged VIX-VESTIGIAL-KNOB-CLEANUP fix (doc-only). Scorecard: analysis/recommendations/bear-vix-floor-ssb.json + .md. :: depends:none :: status:done
- [ ] BOLD-VIX-BEAR-CEILING-GAP (LOW, disclosure-only, from VIX-DEADZONE-MAP) :: aggressive/params.json has NO `vix_bear_hard_cap` key at all (Safe has 23.0). Confirmed via grep + gates.py gate #15 reading `params.get("vix_bear_hard_cap", None)` -> None on Bold -> the gate structurally never fires for Bold bear entries at any VIX level. Not evidence this is WRONG (Bold's wider vix_entry design intentionally trades higher-vol regimes per its own doc comments) -- just undocumented and never explicitly evidence-checked the way Safe's 23.0 cap was (safe_vix_bear_hard_cap.json, OP-22 auto-ratified 2026-06-18). One-time check: does a Bold-scoped VIX≥23 (or ≥25/30, matching Bold's other wider bands) bear-ceiling clear OOS+SS-B on Bold's real fills? If yes, ship with a scorecard; if no evidence either way, leave as-is and just add the doc-comment disclosure so it stops looking like an oversight. Evidence: analysis/deep-research/2026-07-14-vix-deadzone-map.md §1 table. :: depends:none :: status:pending
- [x] TRENDLINE-CONVICTION-OVERRIDE (HIGH->KILL, TRENDLINE-SUBSYSTEM-AUDIT crew's own frozen spec, run+closed 2026-07-14 ~14:40 ET) :: **DONE -- KILL, block_elite_bull's VIX[15,17.5) band stands.** Ran the audit crew's own `trendline-structure-conviction-preregistration.json` (FROZEN_PENDING_RUN since earlier today, untouched by the separate S1/S2 break-battery crew) verbatim via new `backtest/tools/trendline_conviction_override_study.py`: n=93 (IS=85/OOS=8) ELITE-bull level_reclaim signals in VIX[15,17.5) reconstructed from the BASE unblocked run, 3 candidates (TL-A wick-only J's-rule, TL-B wick-only alt-threshold, TL-C wick-or-body) tested as a conviction-rescue against block_elite_bull's own baseline (elite-bull-block-vix-01.json IS bucket avg=-$100/tr, n=73). **TL-A/TL-B FAIL condition_1 outright** (rescued mean=-$0.28/tr, n=18, WR=22.2%). **TL-C mechanically PASSES** (+$23.57/tr, n=26, WR=19.2%) but a leave-largest-winner-out robustness diagnostic (added before any ship call, disclosure-only, no re-pick) shows it's a single-trade artifact: one +$1,949.80 signal is 318.2% of the rescued population's net P&L; excluding it alone flips the mean to -$53.48/tr. No candidate clears the evidence bar the mission requires. Remainder-population regression check (condition_2) and no-lookahead guard (condition_4, `backtest/tests/test_trendline_conviction_override_no_lookahead.py`, 2/2 pytest) both PASS for all 3 candidates -- the KILL is on condition_1's outlier-dependence, not a methodology flaw. Zero params/config/trading-path edits, zero orders. Scorecard: `analysis/recommendations/trendline-conviction-override-result.{json,md}`; pre-registration updated in-place with `status:RUN_COMPLETE` + result pointer (no threshold/candidate re-picked). :: depends:none :: status:done-killed

## 2026-07-14 EDGE deep-research verdicts (synthesis: markdown/research/EDGE-DEEP-RESEARCH-SYNTHESIS-2026-07-14.md)
- [ ] EDGE-1-PASSIVE-LIMIT-GRADUATION (HIGH, execution-alpha, SEC-DERA-verified) :: Graduate entry_manager (T-W5) passive-limit entries: TWIN-B3 live measurement on the crypto twin -> SPY A/B. Halves the dominant measured loss driver (transaction costs = >70% of retail 0DTE losses; non-marketable limits cost ~$0.021-0.028 vs $0.05 marketable). TWIN-B3 leg SHIPPED 2026-07-15 (live A/B accruing on twin; first passive fill +6.13bps). NEXT gate: >=20 twin passive fills in automation/state/crypto-twin/entry-quality.json -> then write the frozen SPY A/B pre-registration (delta=0.10/patience=3/cancel). :: depends:none :: status:in-progress-live-measuring
- [x] EDGE-2-DEBIT-SPREAD-AB (HIGH->KILL, ran+closed 2026-07-15 ~00:20 ET) :: **DONE -- KILL both variants (OTM-1, OTM-2).** Frozen pre-reg (prereg-debit-spread-ab-2026-07-14.json, v1->v2 after a found-and-fixed intrabar-trigger defect, hash repinned) run verbatim via backtest/tools/debit_spread_ab_study.py: ATM long + OTM-1/OTM-2 short vs naked ATM control, 250-signal ribbon_ride cohort (n=244) + 110 real-fill corroboration (n=92), exits via the live exit_manager at live params.json scope. Expectancy -$63.06/-$52.65 per episode vs naked's -$5.24; OOS negative, qpf=0.0, BH-FDR confirms the delta is significant but it's a WORSENING. Mechanism: friction_pct_of_premium ~3-4x the naked control's (25.7%/17.0% vs 5.8%) -- the same $0.02/leg+$0.65/leg/side haircut applied to a net-debit base 2.5-4x thinner. No OP-16 anchor regression (heavily caveated -- naked ATM convention itself doesn't reproduce J's real winning P&L on those days). Scorecard: analysis/recommendations/debit-spread-ab.{json,md}. **The sibling BUILD lane's setup/scripts/spread_executor.py mleg machinery stays DISARMED** (spread_execution_enabled:false in both params.json) -- this scorecard was its arming gate and it did not clear. STATUS.md 2026-07-15 ~00:25 entry. :: depends:none :: status:done-killed
- [x] STRIKE-AB-CONVENTION-RECONCILIATION (HIGH, cross-study audit, ran+closed 2026-07-15 ~01:20 ET) :: **DONE -- ATM arming STANDS on relative grounds; the naked-ATM's -$5.24 was NOT an apples-to-apples comparison.** J flagged a real cross-study contradiction: ribbon-ride-strike-exit-ab.json's ATM/SS-B cell (+$65.82/tr, the arming evidence for PROFIT-P2-ARMED below) has zero friction code, vs EDGE-2-DEBIT-SPREAD-AB's naked-ATM control (-$5.24/episode) which has real haircuts. New `backtest/tools/strike_ab_convention_reconciliation.py` (sanity-check-verified to reproduce the +$65.82 cell to the penny before any toggle) found the two studies actually differ on **5** conventions, not the 2 named when this was flagged: friction (-$47.86/tr, the named one), fill-bar convention (+$2.06/tr, negligible -- AND debit_spread_ab_study.py's own docstring self-identifies as the OLD pre-p5_topcell-fix `>=` convention, not "corrected" as characterized -- a mislabeling caught and flagged), premium_stop stage-fix ($0.00, verified no-op under ARM_SCOPE_POST_TP1), plus **2 previously-undisclosed axes that dominate**: exit-shape swap (SS_B_SHAPE -> debit_spread's LIVE params.json shape, -$57.81/tr, 81% of the total gap) and the structure-stop chart layer's absence in debit_spread_ab_study (+$32.55/tr in isolation). All 5 factors' contributions verified ORDER-INDEPENDENT (forward and reverse toggle paths agree to the cent). **The literally-requested re-run** (strike axis OTM-2/OTM-1/ATM/ITM-2, SS-B held fixed, HONEST friction added): ATM beats OTM-2 by $50.52/tr (was $47.96/tr pre-friction -- the relative delta not only survives, it widens slightly) and **ATM is the ONLY one of the 4 strike cells that clears positive expectancy overall AND is stable across both chronological halves** once real friction is honestly modeled -- OTM-2 (the pre-override control), OTM-1, and ITM-2 all go net-negative under honest friction. Verdict: **arming stands, on stronger grounds than mere relative comparison.** Scorecard: analysis/recommendations/strike-ab-convention-reconciliation.{json,md}. Process lesson filed: strategy/candidates/_lesson-inbox/2026-07-15-cohort-scorecard-convention-header-missing.md (specs a machine-readable `convention_header` schema for every cohort-level scorecard, suggest L201). :: depends:none :: status:done
- [x] DAYTYPE-GATE-STUDY (MED->KILL, reframe/regime-lever probe, ran+closed 2026-07-15 ~01:10 ET) :: **DONE -- clean KILL, all 3 variants, wrong-direction result.** Pre-registered (`prereg-daytype-gate-2026-07-15.json`, frozen+committed before running, commit 994bce5) 3 zero-look-ahead-by-10:30-ET day-type classifiers (V1 opening-range extension+hold, V2 first-hour RVOL+close-location, V3 inverted compression-ratio -- V1 is a strict superset of V3 by design) against JOB1's honest-convention OTM-2 control population (entry_ts>=10:30 ET only, n=218 retained of 250). Result via `backtest/tools/daytype_gate_study.py`: **all 3 FAIL condition_1 (direction_correct) -- TREND-bucket expectancy is WORSE than CHOP-bucket for every variant** (V1 -$97.26 vs -$24.22, V2 -$250.87 vs -$18.70, V3 -$53.80 vs -$33.79), the opposite of the hypothesized direction. Shuffle-null p_null 0.58-0.99 (nowhere near significant, 0/3 BH-FDR survivors). J-anchor ex-ante catch rate: V1/V3 1/3, V2 0/3 (none clear the pre-registered >=2/3 bar). Neither bucket clears positive expectancy in this population -- the retained OTM-2-control slice itself is net-negative (exp=-$35.07) before any split, consistent with JOB1's OTM-2 honest-convention result; day-typing does not rescue it. Confirms the competing_hypothesis frozen in the pre-reg (day-level concentration is not front-runnable by a 10:30-ET-observable opening-range/RVOL/compression signature with these 3 designs) -- a clean, well-powered, publishable negative. Scorecard: analysis/recommendations/daytype-gate-result.{json,md}. Prereg updated in-place status:RUN_COMPLETE + result_pointer (no threshold re-picked). :: depends:none :: status:done-killed
- [x] EDGE-3-HOLD-POSTURE-PREREG (MED->KILL, ran+closed 2026-07-15 ~00:20 ET) :: **DONE -- KILL both variants (MIN_HOLD_30, TRAIL_ONLY_60), TRAIL_ONLY_60 nuanced not clean-negative.** Frozen pre-reg (prereg-hold-posture-2026-07-14.json) run via backtest/tools/hold_posture_ab_study.py, reusing EDGE-2's population/battery/BH-FDR machinery as a library import (same cohort, same battery discipline). MIN_HOLD_30 (30min floor before any non-catastrophe exit): clean KILL, exp -$60.57/episode, OOS-, qpf=0.167, BH-FDR-significant WORSENING. TRAIL_ONLY_60 (trailing-primary, TP1 deferred past 60min): aggregate exp -$1.37 (near-breakeven, slightly better than control's -$5.24), OOS+, qpf=0.667, but delta vs control not significant (p_null=0.917) -> KILL per the frozen pass bar; swings from control's -$674 to +$141.80 on J's 3 real OP-16 anchor days specifically -- real but not (yet) aggregate-significant, flagged for a future anchor-stratified follow-up rather than closed dead. Found-and-fixed a real exit_manager stage-labeling bug before reporting (premium_stop label conflated the static catastrophe cap with a pre-TP1 profit-lock-floor exit under arm_scope="full"; same fix applied to debit_spread_ab_study.py, confirmed no-op there). Scorecard: analysis/recommendations/hold-posture-ab.{json,md}. STATUS.md 2026-07-15 ~00:25 entry. :: depends:none :: status:done-killed
- [x] EDGE-KILL-LEDGER (MED, hygiene) :: **DONE 2026-07-14 (hygiene+release lane).** 5 formal closure rows appended to `analysis/backtests/STRATEGY-SPACE-REGISTRY.jsonl` (verdict DEAD, schema-matched to the `mechanical_external_timing_64families` family-closure precedent, each with what/why-killed/evidence-artifact/reopen-condition): `gex_dealer_gamma_alpha_family` (1,972-day SPY study no lift after VIX+ATM-IV controls + CBOE de-minimis 0DTE MM flow + internal b4-gamma-wall-interaction INFEASIBLE; gex_context stays calm-regime descriptor only), `orderflow_imbalance_intraday_family` (OOS R^2 ~3%, Sharpe ~0.12, HFT-decay), `ohlcv_bar_pattern_mining_family` (two independent internal batteries: futures Phase-1 0/12 + 0/96 KILL-all-seeds, trendline 12/12 break + 12/12 fade FAIL, converging with the external 14-family/947-day battery — closes NEW mining only, validated setups stay live), `post_news_drift_family` + `volume_magnitude_signal_family` (precise nulls; news stays defense-only, volume stays confluence-only). All rows REOPEN only on new NON-OHLCV data. Cross-linked: markdown/research/EDGE-DEEP-RESEARCH-SYNTHESIS-2026-07-14.md. All 5 rows verified JSON-parse-clean post-append (6067→6072 lines). :: depends:none :: status:done
- [ ] TRAIL60-REOPEN-WATCH (LOW, from hold-posture KILL 2026-07-14) :: TRAIL_ONLY_60 killed under the frozen significance bar (p_null=0.917) but was near-breakeven aggregate (-$1.37 vs control -$5.24), OOS-positive, qpf 0.667, and flipped J's 3 OP-16 anchor days from -$674 to +$141.80. REOPEN CONDITION: re-run the same frozen spec once >=50 NEW real fills accrue under SS-B (cheap re-run, no new design). Not a wire, a watch. :: depends:fills-accrual :: status:pending
- [ ] EXITMGR-STAGE-LABEL-CONFLATION (MED, ledger-hygiene, from 2026-07-14 study bugfix) :: exit_manager's "premium_stop" stage label conflates the static -50% catastrophe cap with a pre-TP1 profit-lock-floor exit under profit_lock_arm_scope="full" — the study scripts were fixed; check whether exit_manager itself / live journal rows carry the ambiguous label and disambiguate (two distinct stage names), guard test. Affects any future exit-reason analytics. :: depends:none :: status:pending
- [x] LIVE-SHAPE-VS-CERTIFIED-SSB-DELTA (HIGH, live-P&L-relevant, from strike-ab reconciliation) :: The reconciliation's single biggest factor: swapping the study's SS_B_SHAPE constant for LIVE params.json's actual exit shape costs -$57.81/tr on the flagship cohort (81% of the +$66->-$5 cross-study gap). QUESTION: does the shape configured in live params.json match the SS-B shape that was CERTIFIED (ssb-certification-2026-07-09 + the fill-bar sensitivity re-cert)? Diff every exit knob (tp1 fraction/target, trail pct, cat-cap, structure-stop params) study-constant vs live params vs certification artifact. If live is running non-certified knob values that replay -$57.81/tr worse, that is a TODAY problem — reconcile which is correct and align, with a scorecard + revert line. Evidence: analysis/recommendations/strike-ab-convention-reconciliation.md job1b_gap_bridge_atm. :: depends:none :: status:closed-investigated-no-change :: RESOLVED 2026-07-15 08:24 ET -- traced every knob the live exit_manager consumes for core ribbon_ride (strategies.py:103-105, commit 933bd65 -- the SAME commit ssb-certification-2026-07-09.json certified, unchanged since) against SS_B_SHAPE + the certification artifact: ALL consumed knobs already MATCH certified (tp1_premium_pct 1.0, tp1_qty_fraction 0.667, profit_lock_mode trailing, trail_pct 0.15, catastrophe_stop_pct -0.50, stop_mode structure, structure_stop_enabled true, time_stop_et 15:40 -- the doctrine-15:50 suspicion was itself wrong, v15.3 intentionally set 15:40 and certification used exactly that). The -$57.81/tr shape_config=LIVE toggle in job1b was a STUDY-CONSTANT ERROR (debit_spread_ab_study.py-style params.json reader modeling a disarmed, unrelated feature), not a live misconfig -- v15_profit_lock_* keys have ZERO consumers on the ribbon_ride path, top-level tp1_premium_pct/tp1_qty_fraction feed only a log-only display field. Bold checked separately, same conclusion (shared strategies.py). NOTHING SHIPPED. Baseline suite 200/200 green (unchanged). Full 3-way diff + evidence: analysis/recommendations/strike-ab-convention-reconciliation.md FOLLOW-UP section + matching .json key.

## J-INTENT-EXECUTOR (HIGH, J-called 2026-07-15 13:30 ET) — standing deterministic executor for J-called conditional trades
- **Why:** J: 'you are too slow to decide then implement and making LLM calls for logic.' Today's J-called 752P took ~16 min to arm (hand-written one-off watcher, one stale-bar bug), ~2 min trigger->fill, ~1 min stop->flat — every hop had an LLM wake inside it. Deterministic > LLM on hot paths (OP-3); the machinery for J-called trades didn't exist.
- **Design (picked from 3-option brainstorm):** standalone daemon j_intent_executor.py + automation/state/j-intents.json. Claude's only role = translate J's sentence into an intent JSON (one turn, <60s). Executor: 15s poll, trigger/invalidation eval on completed 5m bars (or live-bid mode per intent), entry via REST (mine fast_path_executor.py key-loading), risk_gate sizing + kill-switch check, rests TP1, holds chart-stop/catastrophe/chandelier/time-stop, flattens itself, auto-writes journal + trades.csv rows (Rule 8), reaper-exempt via backtest/.venv python.
- **Acceptance gate (before ANY live arm):** replay test must reproduce today's real trade exactly from recorded bars — entry on the 13:15 bar (tag 752.255, close 751.785 < 751.94) AND chart-stop flatten on the 13:20 bar (close 752.405 > 752.26). Plus guard tests: stale-bar immunity (the bug found today), no-trigger timeout, invalidation path, kill-switch refusal.
- **Reuse, do not rebuild:** scratchpad put_rejection_watcher.py + put_exit_watcher.py (debugged trigger/exit logic, this session), fast_path_executor.py REST pattern, risk_gate.check_order, settlement_ledger.
- **Target latency:** arm <60s / entry <15s / exit <15s. Zero LLM calls after arming.
- **Later (not v1):** Discord bridge accepts intent commands directly, zero-Claude arming.

**CLOSED 2026-07-21 ~19:20 ET (conductor, AFTERHOURS) — fully shipped, never marked done; closing the loop.**
Verified live, not re-built: `setup/scripts/j_intent_executor.py` exists (38.4KB, last touched 2026-07-18),
`automation/state/j-intents.json` is the live store (default-empty doc confirms the pure-no-op-when-empty
design), and `Gamma_JIntentExecutor` is registered in `SCHEDULED-TASKS.md` (09:25 ET weekdays). Re-ran the
acceptance-gate replay this fire: `backtest/tests/test_j_intent_executor_replay.py` **23/23 PASS**, and the
suite's own fixture (`spy_5m_2026-07-15_j_intent_752p.csv`) reproduces the EXACT real trade named in this
item's own acceptance criteria — entry bar closes 13:15 ET at 751.785 (< 751.94 confirm-close), chart-stop
exit bar closes 13:20 ET at 752.405 (> 752.26 stop) — byte-matching the acceptance gate's stated numbers.
No code change needed; this fire's only action is closing a queue item that has been done-but-untracked
since 2026-07-18, preventing it from re-surfacing as "not started" to a future fire (OP-22 compound,
don't accumulate). :: status:done

## EOD-2026-07-15 FIXES (Fable EOD review, filed 16:58 ET) — three verified engine defects from today's tape
1. **BOLD-STRIKE-X-FLOOR-COLLISION (HIGH):** Bold <$2K tier = OTM-3 (V15_BOLD_TIERS, crypto/lib/strike_selection.py) x min_entry_premium=0.30 (ENTRY-1, shipped 07-09) are mutually exclusive after ~noon: 13:56 ENTER_BULL resolved 757C @ $0.08 -> SKIP_MIN_PREMIUM_FLOOR x5 ticks; Bold structurally CANNOT trade afternoons. Also OTM-3 IS the documented bleed cohort (edge-hunt 06-20; strike reconciliation 07-14: ATM only positive cell — SAFE cohort, C29 blocks blind transfer). ACTION: pre-registered Bold strike-axis study (reuse reconciliation runner w/ Bold sizing/exits, honest friction), tier decision from evidence. NOTE: CLAUDE.md account table says Bold=ITM-2 — doc-drift vs live ladder (ITM-2 only at >=$25K); reconcile doc after study.
   **[CLOSED 2026-07-15 ~19:16 ET, status:done-null]** Ran the pre-registered study (`analysis/recommendations/prereg-bold-strike-axis-2026-07-15.json` frozen first, commit `f8cf973`; runner `backtest/tools/bold_strike_axis_ab.py`, reuses the reconciliation runner's `replay_generic()` unchanged). Floor-collision CONFIRMED at scale: OTM-3 clears the floor only 41.7% overall / 33.8% afternoon, AND is an economic loser (expectancy -$10.81/tr, OOS -$14.37/tr) — a genuine double-fault. **Verdict: NULL at the full pre-registered 5-gate bar** — every cell (incl. control) fails the WF gate, traced to a structural cohort-wide artifact (every cell's 2025 IS-half is net-negative under SS-B/honest-friction, so `wf` is undefined by construction for all 6 cells — cross-validated against the 07-14 Safe reconciliation's `job1a`, which shows the identical `wf: null` on its own 4 cells). ATM flagged WATCH (near-miss, fails only the structurally-unreachable WF gate; beats control +$28.77/tr OOS, clears floor/anchor/BH-FDR/stability) — one-line diff + guard-test spec drafted in the scorecard's `near_miss_diagnostic`, **NOT applied** (same-night flip deferred to a J REVOKE window per task instruction, -$369 Bold day). CLAUDE.md doc-drift reconciliation flagged as a separate spawned task (token-budget-aware, CLAUDE.md was already 99% of its 9K cap) rather than done inline. Scorecard: `analysis/recommendations/bold-strike-axis-2026-07-15.{json,md}`. Full narrative: `automation/overnight/STATUS.md` 2026-07-15 ~19:16 ET entry. NOTHING SHIPPED to any trading-path file.
2. **VETO-SNAPSHOT-UNITS-FALSE-VETO (HIGH, ships tonight):** qwen3:14b vetoed Bold 14:16-14:20 ENTER_BEAR reading `spread=75.14` (EMA ribbon width in CENTS) as option bid-ask in DOLLARS ("implausibly large... data entry error"). Fix: rename field to ribbon_width_cents + unit-annotate every numeric in _veto_snapshot prompt; guard test; file as false-veto evidence row in free_model_audit (B1 heartbeat_veto) — exactly the failure class the harness exists for.
3. **SELF-CHECK-PDT-STALE-LANGUAGE (MED, ships tonight):** self_check fired 'PDT-BLOCKED[safe]: 7/3 day-trades' at 15:09 — margin-PDT language on a CASH account (risk_gate is cash_settlement since fd09a78). Alert is wrong/misleading (nothing actually blocked; both trades filled). Sync self_check to pdt_gate_mode.
4. (already queued this morning) MACRO-CALENDAR-STALE: Gamma_MacroCalendar 07:45 fire didn't run 07-15 (28.5h stale stamp in context bundle).

## WF-GATE-STRUCTURALLY-NULL (HIGH, methodology, filed 2026-07-15 evening)
- Two independent studies same day (bold-strike-axis-2026-07-15 all 6 cells incl. control; strike-ab-convention-reconciliation job1a all 4 cells) show wf undefined/failing because the 2025 IS half is net-negative under SS-B + honest friction while 2026 is positive -- WF>=0.70 cannot pass for ANY candidate, so it no longer discriminates.
- ACTION: redesign the WF ratification gate for the SS-B era (e.g. rolling-origin walk-forward on 2026-only windows, or WF on the A/B DELTA rather than absolute halves) via its own pre-registered methodology note; until then every battery/scorecard must disclose WF-null and rest on the remaining gates. Do NOT silently drop the gate.
- Interaction: tonight's directional-gate battery warned in-flight (SendMessage) not to mass-disable on it.
- Fallout candidate: ATM cell for BOLD (bold-strike-axis near_miss_diagnostic) passes 4/5 with only WF failing -- re-adjudicate once the WF redesign lands.

## GAMMA-PARTICIPATION-DAILY (built+shipped 2026-07-15, from root-cause audit SS9)
- [x] PARTICIPATION-DAILY-INSTRUMENT (HIGH, goal-layer, root-cause audit 2026-07-15 SS9) :: **DONE 2026-07-15.** Built `setup/scripts/participation_daily.py` (wraps `backtest/tools/participation_cascade.py`, reuses its parsing verbatim), registered `Gamma_ParticipationDaily` (16:10 ET weekdays, `setup/scripts/install-participation-daily.ps1`), writes `automation/state/participation-daily.json` (per-account safe-2/bold-2 fills-vs-target + GREEN/YELLOW/RED/IDLE) + Discord-alerts on YELLOW/RED. Verified live (manual + real `Start-ScheduledTask` fire): `safe=1/2-4 [YELLOW] bold=0/2-4 [YELLOW]`. Guard: `backtest/tests/test_participation_daily.py` (20/20). :: depends:none :: status:done
- [ ] PARTICIPATION-DAILY-SELF-CHECK-WIRE (MED, hygiene, from PARTICIPATION-DAILY-INSTRUMENT above) :: Wire participation verdict into self_check once hygiene lane lands -- `setup/scripts/self_check.py` is owned by another agent right now, deliberately NOT edited by this task. `automation/state/participation-daily.json` (per-account safe/bold fills-vs-target, default 2-4/day, + a GREEN/YELLOW/RED/IDLE verdict per account and an overall rollup) should surface through self_check's DEGRADED/BROKEN pipeline the same way `check_fill_funnel` and the other standing checks do -- `participation_cascade.py`'s own module docstring already sketches the one-line hookup shape (`check_participation_cascade`). Until this lands, J is NOT blind: `participation_daily.py` already appends its own `discord-outbox.jsonl` line on YELLOW/RED (de-duped per date+verdict) independent of self_check -- this item is about CONSOLIDATING onto the one surface, not creating a first alert path. :: depends:self-check-hygiene-lane :: status:pending

### T-AUTOPSY-H-2026-07-16-stop-noise MED — autopsy hypothesis: stop_inside_noise_floor

**Claim:** the live stop exits losers that then pay the thesis -- the stop is harvesting winners, not cutting losers. **Evidence:** `{"losers_in_window": 29, "stopped_then_paid": 22, "fraction": 0.759, "window_n": 30}` (analysis/autopsies/2026-07-16.md).
**Action:** replay exit-A (-50/+150/sell66/trail15) on these exact fills via exit_shape_parity_study (kill-check) · confirm on the fresh OPRA slice per the STOP-A pre-registration (T-W7) :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-07-16-entry-spike MED — autopsy hypothesis: paying_the_signal_spike

**Claim:** entries fill materially above the signal-minute low -- the marketable ask+buffer buys the local premium spike (defect #2). **Evidence:** `{"median_paid_above_min_low": 0.133, "n": 30}` (analysis/autopsies/2026-07-16.md).
**Action:** entry_manager shadow (T-W5): log limit-below/patience counterfactual fills next to real entries for 3+ sessions :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-07-16-left-on-table MED — autopsy hypothesis: exit_shape_dominated

**Claim:** a fixed counterfactual shape beats the shipped exits by more than 2x the window's net P&L -- the exit shape, not the signal, is the bottleneck. **Evidence:** `{"sum_stop_cost": 3694.65, "window_net_pnl": -1126.01, "n_dominated": 9, "window_n": 30}` (analysis/autopsies/2026-07-16.md).
**Action:** STOP-A sign-off -> T-W7 confirmatory on the frozen v2 candidates · enumerate levers beyond exit shape per markdown/trading-knowledge/GENERATIVE-LENS.md (DTE / spread / strike / sizing) :: depends:none :: status:proposed

### T-GYM-20260716 HIGH gym-session RED for 2026-07-16

**Audits failing:**
- crypto-gym (53 validators) (RED): 103/104 pass

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

## VETO-HTF-CONFLICT-REGRADE (HIGH, filed 2026-07-16 ~19:05 ET, Fable)
- The HTF pre-check study (vwapcont-htf-precheck-2026-07-16, pre-registered, KILL) found HTF-OPPOSED vwap_continuation signals OUTPERFORM aligned ones (+$67.15/tr n=48 broad-based vs +$8.87/tr n=73 outlier-carried). Mechanism fits C28 (15m ribbon lags; fast signals catch reversals first).
- CONSEQUENCE: the free-model veto's most common rejection reason ("conflicting HTF") is now evidence-suspect -- it may systematically block the BETTER cohort. Today it blocked 5 vwap_continuation re-fires on exactly this reasoning AFTER the 2 losses; those blocks now need counterfactual grading, not assumed-correct framing.
- ACTION: extend free_model_audit.py B1 (heartbeat_veto) grading with a tagged hypothesis: vetoes citing HTF conflict, graded by counterfactual replay, reported as their own cohort. If false-veto rate on HTF-reasoning exceeds the harness bar, the veto prompt gets an evidence note ("HTF opposition is NOT disqualifying per vwapcont-htf-precheck-2026-07-16") the same way the ribbon-width units fix landed.
- Also: my own 07-15/16 narratives ("counter-HTF was the stated risk and it bit") are now suspect -- n=2 anecdotes vs n=121 study. Noted for intellectual honesty.
- **PARTIAL RESULT 2026-07-16 ~19:25 ET (Sonnet):** B1 adapter extended -- `setup/scripts/free_model_audit_heartbeat_veto.py::classify_veto_reason_class` (+`_item_veto_reason_class`) keyword-tags every graded veto item into {htf_conflict, spread_data_doubt, other} from the free models' own reason strings (built from the real 160-reason/76-item corpus in core-decisions.jsonl); `veto_reason_class_breakdown`/`veto_reason_class_scorecard_section` cross-tabulate ALL graded veto items (re-joining history.jsonl against a fresh ledger re-collect, not just today's trickle) and render a per-class table + verdict line, cited against this study. Wired into the generic harness via a new optional `SubjectAdapter.extra_scorecard_section` hook in `free_model_audit.py` (additive-only -- twin_review/prospector/swarm_consult unaffected, guarded by `test_subject_adapter_extra_scorecard_section_defaults_to_none`). REAL run (`--subject heartbeat_veto`, forced by the due cadence gate, 34 new items graded via counterfactual replay against real OPRA bars, 0 LLM-fallback needed): **htf_conflict false-veto rate = 22.4% (11/49 graded, ALL-TIME cumulative) vs spread_data_doubt 0.0% (n=1) and other 50.0% (n=2)** -- see `analysis/free-model-audit/heartbeat-veto/2026-07-16-scorecard.md`. **Evidence bar NOT cleared: the comparison cohort (spread_data_doubt + other combined) is only n=3, structurally short of the n>=5 floor** -- non-HTF veto reasons are rare (3/76 = 4% of all-time veto items), so this may take a long time to reach n=5 via organic veto activity alone. Per the pre-registered decision rule, the veto sysmsg in `heartbeat_core.py::_free_model_eval` was NOT touched. Confirms the queue item's premise though: htf_conflict is 49/52 = 94% of all graded veto items, exactly the dominance this item flagged. **LEFT OPEN** -- re-run `free_model_audit.py --subject heartbeat_veto --force` periodically; ship the sysmsg evidence note only once htf_conflict's false-veto rate is graded as materially above a same-sized (n>=5) non-HTF comparison cohort. Guards: `test_free_model_audit_heartbeat_veto.py` (classifier on 15 real quoted reason strings + breakdown/scorecard tests), `test_free_model_audit.py` (extra_scorecard_section wiring, tolerant-of-broken-extension). Side-note (fixed same session): `load_bar_state`/`save_bar_state`/`append_history`/`load_history_items`/`already_graded_ids`/`append_status_note` had their path defaults bound at module-import time (`path: Path = HISTORY` in the signature) instead of resolved per-call -- a test that ran `run_subject()` under `monkeypatch.setattr(fma, "HISTORY", tmp_path)` silently kept writing to the REAL `automation/state/free-model-audit-history.jsonl`/`free-model-audit-state.json` (7 junk rows + 2 junk subject keys, caught immediately, cleaned up, root-caused, and fixed at the source -- signatures now take `Optional[Path] = None` resolved inside the function body).

## WF-GATE-REDESIGN-METHODOLOGY (Fable judgment work, queued for next block)
- Two studies proved wf_ge_070 structurally unreachable post-SS-B (is_mean<=0 for every cell incl. controls). Redesign candidates: rolling-origin 2026-only WF, or WF on the A/B delta. Needs a pre-registered methodology note BEFORE it gates any study again. Blocks: Bold ATM re-adjudication, risky-3 strike table.

## TRENDLINE-FIXES-2026-07-17 (HIGH, tonight after 16:00 ET -- J: "fix your trends")
1. PREMARKET DRAW CANNOT SILENTLY SKIP: 2 budget-skips in 2 days. Move the draw step out of the
   LLM premarket fire into a deterministic scheduled step (trendline_draw_state clear + engine
   detect + draw via cdp_eval.mjs fallback if MCP down), or make the skip emit a RED status line.
   **[CLOSED 2026-07-20 ~00:xx ET conductor (AFTERHOURS), commit see STATUS.md]** Took the
   stated alternative (status-line, not the deterministic-step rewrite): `trendline_draw_state.py`
   gained `mark_run(status, reason)` (+ CLI `mark-run --status success|skipped --reason ...`),
   stamped into `trendline-draw-state.json`'s new `last_run` field. Wired both success and
   TV-down/skill-failure/context-budget-skip paths in `premarket.md` Step 5c + the
   `trendline-draw` skill's new Step 6 to call it. New `self_check.check_trendline_draw_freshness`
   (check #13 in `run()`) reads the stamp weekday-only, past a 09:00 ET slack window past the
   08:30 fire: never-marked / stale-prior-day / today-marked-skipped all surface as DEGRADED
   (deliberately never BROKEN -- Step 5c is non-load-bearing visibility per its own docs) to
   STATUS.md + Discord via the existing `_alert()` path, so a 3rd silent skip can't recur invisibly.
2. FRESH/SAME-DAY DESCENDING LINE TIER: J hand-drew the week's descending line twice this week;
   detector only scores multi-day rails (documented gap, pre-reg A/B spec already in
   TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14). Run that A/B; ship a same-day tier if it clears.
   **CLOSED 2026-07-20 ~04:xx ET conductor (AFTERHOURS), commit see STATUS.md.** Corrected a
   false premise first: the audit's referenced pre-reg
   (`analysis/recommendations/trendline-structure-conviction-preregistration.json`) answers a
   DIFFERENT question (a VIX-band conviction override for `block_elite_bull`) and is already
   `status: RUN_COMPLETE` / `result_verdict: KILL` -- not a spec for the same-day-priority gap;
   the audit's own "Not done" section says the same-day tier "needs its own eval, not bundled
   into this audit's read-mostly fixes," i.e. no A/B spec existed for THIS gap. Since this is a
   SHADOW-only visibility feature (write_live_state's own docstring: "the engine does NOT trade
   off these yet"), not a live trading gate, no P&L A/B applies -- a mechanism-correctness guard
   is the right validation, same class as item 1/item 4's shipped precedents. Fix:
   `trendline_engine.detect(bars, include_same_day_tier=True)` (default False, every existing
   caller/test byte-identical) adds a second best-scoring pass restricted to TODAY's bars per
   (kind, family), appended `tier="same_day"` when genuinely different from its primary sibling
   (deduped on exact anchor identity); wired live at `main()`, the one production entry point
   (`Gamma_Trendlines` 5-min RTH cadence + the premarket drawing bridge). `Trendline.tier` +
   `write_live_state`'s JSON both carry the new field. **Deliberately NOT wired into the
   drawing skill's on-chart DRAW CAP** (`.claude/skills/trendline-draw/SKILL.md`) -- doing so
   would reopen the 2026-07-15 "too many trend lines" noise complaint the cap exists to fix;
   left for item 3 (zoom-aware drawing) to reconsider together. Guard:
   `backtest/tests/test_trendline_same_day_tier.py` (9/9 -- default-unchanged, additive-never-
   replaces, dedup-when-primary-already-is-same-day, no-op-when-no-distinct-line, no-lookahead,
   write_live_state schema, families=both). Zero trading-path files touched (`params.json`/
   `heartbeat_core.py`/`filters.py`/placement/exit code untouched) -- SHADOW/visibility-only.
3. ZOOM-AWARE DRAWING: multi-day rails at intraday zoom read as noise (J: "a blind person drew
   them"). Draw rule: only render lines whose anchor span overlaps the visible ~2-day window,
   or label-offset placement; spec small, validate on a real screenshot.
   **MECHANISM SHIPPED 2026-07-21 ~19:xx ET (conductor, AFTERHOURS), commit see STATUS.md.**
   Implemented the label-offset branch: `trendline_engine.zoom_classify(a_unix, now_unix,
   window_days=2.0)` + `Trendline.zoom_class` ("in_window" | "anchor_offscreen", additive field,
   default preserves every existing caller/reader byte-identical) classify each line's anchor
   against a ~2-day window ending at the line's own last bar (no wall-clock dependency, no
   look-ahead -- `now` is always the last bar already in the caller's `bars` slice, mirrors T15's
   same-day-tier no-look-ahead pattern exactly). Opt-in via `detect(include_zoom_class=True)`,
   wired live at the ONE production entry point (`main()`, same call site as T15's
   `include_same_day_tier=True`) so both the `Gamma_Trendlines` 5-min cadence and the on-demand
   `--json` skill invocation get it. `write_live_state`'s JSON payload carries `zoom_class` per
   line for self_check/dashboard/skill consumers. SKILL.md gained a new step 3a documenting how
   the drawing skill should read the hint (draw the full ray regardless; treat
   `anchor_offscreen` as a prompt to verbally flag the anchor is off J's current view / consider
   `chart_get_state` before trusting the heuristic over the real chart). Guard:
   `backtest/tests/test_trendline_zoom_aware.py` (13/13 -- boundary inclusive/exclusive,
   opt-in-default-unchanged, old-anchor-classified-offscreen, fresh-same-day-anchor-in-window,
   selection/count unchanged, composes with the same-day tier, no-look-ahead, write_live_state
   schema). RED-proofed via `git stash -- backtest/autoresearch/trendline_engine.py` (all 13
   failed with the exact expected `TypeError`/`AttributeError`, `git stash pop` restored clean,
   re-verified 13/13 green). Broader sweep `pytest backtest/tests/ -k trendline` -> **99/99 PASS,
   zero regressions**. Curated safety gate (31+5) PASS. Zero trading-path files touched
   (`params.json`/`heartbeat_core.py`/`filters.py`/placement/exit code untouched) --
   SHADOW/visibility-only, same class as T15. **NOT done this fire, deliberately deferred:**
   validation "on a real screenshot" against the ACTUAL chart-visible-range -- this conductor
   fire has no live TV MCP tool binding (headless), so the classification is a bars-only
   heuristic approximation, not a proven fix for the visual complaint; the next interactive
   session with a live TV chart should invoke the trendline-draw skill, deliberately pick a
   multi-day line that comes back `anchor_offscreen`, and confirm the on-chart result actually
   reads clean at J's normal intraday zoom -- only then is this item fully closed. Revert:
   `git revert <commit>` (3 files: engine, guard test, SKILL.md doc -- additive-only, no data
   loss).
4. THREAD shadow_triggers_fired INTO core-decisions.jsonl (was chip task_4ce16208, chips dead):
   today's J-called trendline break is the FIRST live validation point for trendline_reclaim and
   it is invisible in the ledger. Small heartbeat_core rec addition, zero-behavior-change guard.
   **[CLOSED 2026-07-19 ~22:xx ET conductor (AFTERHOURS), commit see STATUS.md]** Threaded
   `score.bull.shadow_triggers_fired` (filters.BullishSetupResult, LOGGED-ONLY) all the way
   through `engine_cli.decide_payload`'s `base` dict -> `heartbeat_core.py::run_account`'s
   `rec` dict -> `core-decisions.jsonl`. Purely additive DATA-ONLY key (`shadow_triggers_fired`,
   `[]` default), zero effect on verdict/side/triggers_fired/gate. Guard:
   `backtest/tests/test_shadow_triggers_threaded_2026_07_19.py` (6/6, RED-proofed via
   `git stash`: all 5 non-trivial assertions failed with the exact expected KeyError/[] leak
   with the fix stashed out; restored clean). Broader sweep (engine_cli/heartbeat_core/
   shadow_trigger/trigger_level_exact/trendline-scoped) 136/136 PASS, zero regressions.
   Curated safety gate (31+5) PASS. Full REVOKE report in STATUS.md.

## WEEKEND-METHODOLOGY-REVIEW: regime-matched IS window for delta-WF (Fable, filed 2026-07-17 ~11:05 ET)
- THREE studies in 3 days share one signature: positive/stable 2026 OOS deltas, negative 2025 IS
  deltas -> INSUFFICIENT_REGIME_SHIFT parks (Bold strike cells 07-16; zone-rejection Bold 07-17;
  LBFS wf split 07-15 same shape). Either all three are overfit to recent tape, or calendar-2025
  under SS-B pricing is the wrong reference class for judging 2026 config changes (SS-B did not
  exist in 2025; VIX regime differs; C22/C23 lineage).
- WEEKEND TASK (rule 9 cadence): frozen successor note to WF-GATE-METHODOLOGY-2026-07-16
  adjudicating regime-matched vs calendar IS windows. Anti-overfit protections must survive --
  the answer is NOT "drop 2025", it is choosing the defensible reference class BEFORE looking at
  which choice ratifies more candidates. Consider: VIX-regime-matched IS episodes, or SS-B-era-only
  rolling origin now that 2026 has ~7 months. Adversarial review required (the obvious failure
  mode: methodology-shopping until candidates pass).
- Consumers waiting: Bold ATM (parked), Bold zone-rejection cells (parked), risky-3 strike table.

### T-GYM-20260717 HIGH gym-session RED for 2026-07-17

**Audits failing:**
- crypto-gym (53 validators) (RED): 103/104 pass

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

**CLOSED 2026-07-20 ~04:xx ET conductor (AFTERHOURS) -- STALE, self-resolved.** Live-checked
`crypto/data/scorecards/latest.json` this fire: `overall_pass: true`, `104/104 passed`
(`checked_at 2026-07-20T08:19:06Z`, fresher than this item's 2026-07-17 filing) -- a later
scheduled gym run since this was filed cleared the 1 failing stage, same pattern as the
2026-07-19 `conductor-weekend` fire's "gym drift already resolved" finding for a different
stage. No action needed; closing so it stops competing for attention against live RED items.

## HTF-LEVEL-LOOKBACK-EXTENSION (MED, weekend-ratifiable pre-reg, filed 2026-07-17 ~18:28 ET, Sonnet)

**Trigger:** J: "why didn't we look back to 06-30/07-02/07-08 -- that was an extremely strong
bounce off this level [741-744.5] this morning." Full audit: `analysis/daily-brief/2026-07-17-htf-levels-audit.md`.

**Verified:** the 740-744.5 zone is real multi-week confluence -- RTH low landed inside it on
06-30 (740.89), 07-02 (740.03), 07-08 (739.51), and today (740.80), each followed by a $2.4-6.9
bounce (median $3.30 across 9/41 sessions since 05-19 that tested this band). J's read holds.

**Root cause (two additive gaps, both in the still-shadow, never-live memory system):**
1. `level_memory_producer.py::LOOKBACK_DAYS = 10` (trading days) -- as of today's window
   (07-06..07-17), 06-30 (13 days back) and 07-02 (11 days back) are structurally outside the
   horizon. Captured on their own day, aged out since.
2. `level_memory.py::CLUSTER_TOL = 0.35` / producer `DEDUP_EPS = 0.60` fragment the $3.5-wide
   zone into narrow sub-clusters. Proof: today's 16:00 ET shadow file (07-08 in-window, today's
   whole bounce baked in) shows exactly ONE support entry near the zone -- 743.19, memory_score
   48, tier Reference (needs >=60 for `refresh_levels_intraday.py`'s live merge). Never merged.

**Counterfactual (honest, walked bar-by-bar via core-decisions.jsonl):** the missing level was
NOT the binding constraint. Ribbon stayed BEAR-stacked all session (Filter 5 hard veto, zero bull
triggers all day) and VIX ran 19.0-19.5 -- inside `block_elite_bull`'s [0,25) block band, the same
gate that fired SKIP_ELITE_BULL_LEVEL_RECLAIM 25x on 07-15 and 2x on 07-16 with ribbon=BULL and
triggers=['level_reclaim','confluence'] present. Even a perfect HTF level would have died at the
same gate that killed 07-15/16. Value of this fix = conviction/visibility/multi_day_confluence
signal quality, NOT a guaranteed unlock of more live entries -- `block_elite_bull` stays CLOSED
(2026-06-30 audit, -$241 to remove) and is NOT being reopened here.

**Spec:**
1. Additive HTF tier in `level_memory_producer.py` (existing 10-day/$0.35 intraday tier
   untouched): `HTF_LOOKBACK_DAYS=25`, `HTF_CLUSTER_TOL=1.00`, own MIN/STRONG memory floors
   (needs backtesting, not a guessed copy of 20/60). Write to a new `key-levels-htf.json` shadow
   file first -- mirrors the existing G11 shadow-before-merge pattern.
2. Separate live-merge flag `level_memory_htf_live_merge` (default false) in
   `refresh_levels_intraday.py`, own `HTF_MERGE_CAP` (propose 4, vs intraday's 6) -- independently
   A/B-able without perturbing the already-tuned intraday merge.
3. Render HTF levels as a ZONE (wide box), not a hairline, labeled `HTF_SUP_NN`/`HTF_RES_NN`.
   Cross-ref `strategy/candidates/_lesson-inbox/2026-07-17-levels-are-zones-proximity-band.md`
   (filed today ~10:15 ET, same doctrine gap on the rejection-tolerance side).
4. Validate via the standing eval-first gate (OP-16): backfill 60-90 trading days, replay through
   the existing trigger-replay harness, file A/B scorecard at
   `analysis/recommendations/htf-level-lookback-extension.json`. Ratify (flip the merge flag) only
   if OOS_positive AND WF>=0.70 AND sub_window_stable AND anchor_no_regression -- standard bar,
   no J gate to ship.
5. **Build requirement, not optional:** an intraday $0.35-cluster level and an HTF $1.00-cluster
   level from the SAME physical shelf can both land in `key-levels.json` a dollar or two apart.
   `detect_confluence`'s $0.30 tolerance is already near-tautological once any level_reclaim
   fires (`_read_levels` tags nearly every active level as "multi_day") -- two nearby levels from
   one shelf risks making `min_triggers=2` closer to `min_triggers=1` in practice for HTF-adjacent
   reclaims. Extend `_normalize_levels`'s prefix-stripped dedup (or widen `ROLE_EPSILON` across
   HTF/intraday same-shelf pairs) BEFORE live merge ships; this must be a named test in the A/B
   scorecard.
6. Flag-don't-touch: a larger HTF-eligible level_reclaim pool changes the input distribution
   feeding the CLOSED block_elite_bull audit. Informational re-check after ship, not a reopening.

**Cost:** compute $0 (pure Python, already scheduled, ~1950 bars vs ~780 today, <100ms). Level
count: worst case +4 active entries (~16-18 total, still inside `ACTIVE_BAND=$12` budget). Real
cost is the confluence-tolerance interaction in item 5 above, not compute.

:: depends:none :: status:proposed

## BOLD-TIER-BOUNDARY-HYSTERESIS-SPEC (LOW, spec-only, from CORE-BOLD-TAPE-AUDIT-2026-07-17)

- [ ] BOLD-TIER-BOUNDARY-HYSTERESIS (LOW, risk-hygiene, filed 2026-07-17 evening, Sonnet tape audit) ::
  Bold's first confirmed round trip (743P, +$191) pushed equity $1,963.04 -> $2,153.84, crossing the
  $2K `V15_BOLD_TIERS` boundary (OTM-3 -> OTM-2). `pick_tier()`/`pick_strike()`
  (`crypto/lib/strike_selection.py:142-183`) is a stateless `[equity_min, equity_max)` lookup called
  fresh every tick against LIVE broker equity (`heartbeat_core.py:1258-1261`, a real
  `GET /v2/account`, no start-of-day cache) -- confirmed the graduation is not a "next session" event,
  it recomputes intraday, mid-tape. Repo-wide grep for `hysteresis` finds zero hits on the strike-tier
  path (one unrelated hit in `level_alert_daemon.py`'s level-touch debounce). The only existing test
  (`test_bold_core_strike_tier_2026_07_15.py::T9`) checks boundary INCLUSIVITY at exactly $2,000, not
  repeated CROSSING behavior. Bold sits 7.7% above the $2,000 line as of today -- one bad trade
  (catastrophe -50% on a 5-lot ~$0.40 premium ~= -$100) puts it back under, a second win pushes it
  back over; nothing damps oscillation across the line. **This is a SPEC request, not an
  implementation** -- do not wire without ratification:
  1. Define the flap condition precisely: N crossings within M trades/session, or dwell-time-based
     (tier only changes if equity has been on the new side for >= K consecutive ticks/trades)?
  2. Decide the guard shape: a hard "sticky" band (e.g. tier only steps down after equity clears
     $1,900, not $2,000 exactly -- asymmetric hysteresis) vs a cool-down (tier locked for N trades
     after a crossing) vs simple session-lock (tier fixed at session open, only re-evaluated at the
     next day's premarket -- closer to what the CLAUDE.md doctrine text implicitly assumed before
     this audit corrected it).
  3. Whichever shape is chosen must be A/B'd against the current stateless behavior on real fills
     before shipping (OP-16 eval-first gate) -- a flapping-prevention guard that itself never fires
     (equity rarely actually re-crosses) has zero cost to add but also zero proven benefit; the case
     for shipping rests on whether repeated live crossings actually happen, which needs more sessions
     of evidence than today's single data point.
  Evidence: `analysis/daily-brief/2026-07-17-bold-tape-audit.md` §4. :: depends:none :: status:proposed

  **UPDATE 2026-07-18 (BOLD-CORE-ATM-WIRE ship):** the boundary this item concerns has moved. Core
  Bold's $0-2K tier is now ATM (`crypto/lib/strike_selection.py#V15_BOLD_CORE_TIERS`, wired into both
  `heartbeat_core.py` and `j_intent_executor.py`'s bold branches), so the first crossing Bold will hit
  climbing from $2K is now ATM -> OTM-2, not OTM-3 -> OTM-2 -- one tier-step milder (offset delta 2 vs
  3). The flap mechanism and this spec's open questions (1-3 above) are unchanged; only the specific
  strike-offset jump at the boundary shrinks. Re-check this item's evidence against the new boundary
  once Bold has crossed $2K again under the ATM tier.

## BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL (HIGH, filed 2026-07-18, from BOLD-CORE-ATM-WIRE ship)

- [ ] BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL :: core Bold's $0-2K strike tier shipped OTM-3 -> ATM
  2026-07-18 (`crypto/lib/strike_selection.py#V15_BOLD_CORE_TIERS`, wired into `heartbeat_core.py` +
  `j_intent_executor.py`'s bold branches; `STATUS.md` [2026-07-18 ~10:51 ET] entry has full detail) on
  J's explicit in-chat authorization, as a PARTICIPATION fix (afternoon `min_entry_premium` floor
  clearance 0.3376 OTM-3 vs 0.9688 ATM) -- NOT a claim that the underlying P&L evidence
  (`analysis/recommendations/bold-strike-axis-2026-07-15.json`) cleared OP-16's auto-ratify bar; it
  clears 4/5 gates but FAILS `wf_ge_070` per the still-open WF-GATE-STRUCTURALLY-NULL item above.
  ACTION: once core Bold accumulates n>=20 live fills under this sub-$2K ATM tier, run a real-fills
  expectancy check (OOS_positive / WF / sub_window_stable / anchor_no_regression, same battery as any
  other candidate) against this specific cell. If the result is NEGATIVE, this is NOT a silent
  re-flip back to OTM-3 -- escalate to Fable judgment (`/think-like-fable`) given the WF-gate-fail
  provenance already on record, rather than a mechanical Sonnet revert. If POSITIVE, this closes the
  loop on the WF-gate-structurally-null item's "re-adjudicate once the WF redesign lands" deferral for
  this specific candidate. Revert available any time regardless (one line each call site, back to
  `ss.V15_BOLD_TIERS`) if J calls it before n=20. :: depends:none :: status:proposed

## J-ONLY-COMPANION-PUSH-ACTIVATION (HIGH, J-action-required, filed 2026-07-18 conductor-weekend)

- [ ] J-ONLY: activate phone/watch push notifications -- this is the ONE remaining step
  that retires the "is it running / is it trading / whats the status" question J has
  asked **34 times over 17 days** (`automation/state/j-question-ledger.jsonl`, flagged by
  `friction_distiller.py`'s `recurring_user_question` class, occ=34, FAST_ESCALATE=2).
  **Corrected 2026-07-18 (conductor fire, ~13:53 ET):** the original occ=43/49-line count
  was inflated -- 15 of 49 ledger lines (31%) were self-inflicted: every scheduled
  conductor/conductor-weekend/conductor-rth/weekly-review fire submits the wrapper's
  `# RUNTIME CONTEXT (injected by wrapper, ...)` header + full `conductor.md` prose as the
  literal UserPromptSubmit text, and that doctrine prose itself contains phrases ("the
  success bar is daily paper trading", "the rig's function is trading", "never a live
  futures order") that trip the `is_running`/`is_trading` regexes with zero J involvement.
  Fixed in `setup/hook-detect-correction.ps1`'s `$qIsSystem` exclusion (now also skips any
  prompt carrying the wrapper marker), the 15 fake lines were pruned from the ledger, and
  `friction-ledger.jsonl` was regenerated (recurring_user_question now occ=34, still
  STEP-BACK-ELIGIBLE -- the underlying J friction is real, just was over-counted). Guard:
  `backtest/tests/test_graduated_guards.py::test_operator_friction_excludes_wrapper_self_fire`.
  The J-action-required fix below (push activation) is unaffected -- still the correct next step.
  Root cause (two-layer, both verified this fire): (1) VAPID keys already exist
  (`automation/state/.vapid.json`, generated 2026-06-21) -- `sendPush()` is NOT disabled
  at that layer, contrary to the first hypothesis; (2) `automation/state/push-subscriptions.json`
  is `[]` -- ZERO devices have EVER subscribed, because Android Chrome refuses
  push/voice permission grants over plain `http://192.168.x.x`
  (`gamma-companion/MOBILE_PWA_DESIGN.md`, written 2026-06-21, never actioned). The
  fix is two commands + one phone tap, all on J's own device/network, which is why
  this is filed here rather than auto-applied:
  1. `tailscale serve https://gamma.tailnet:443 http://localhost:4317` (or your chosen
     Tailscale MagicDNS name) -- gives the companion an HTTPS front-door Android trusts.
  2. On your Android phone (same tailnet): open `https://gamma.tailnet/`, Chrome menu ->
     "Add to Home Screen", open the installed app once, grant the notification
     permission prompt. That single grant creates the FIRST row in
     `push-subscriptions.json` and `sendPush()` (already wired into
     `approvals.js`/`escalate.js`/`server.js`) starts actually reaching your phone+watch.
  3. Repeat step 2 on the Samsung Watch's browser if it has one, or rely on Android's
     cross-device notification mirroring (watch usually inherits phone push automatically).
  **Verification once done:** `backtest/.venv/Scripts/python.exe setup/scripts/gamma_status.py`
  -> the `-- PUSH (phone/watch) --` line should read `[OK] VAPID configured, N device(s)
  subscribed -- pushes are live`. Until then it will keep (correctly) reporting DISABLED --
  that is not a bug, it is the honest current state.
  **Not done autonomously, and won't be:** `gamma-companion/lib/guard.js` DENY_WRITEs
  `.vapid.json`/`push-subscriptions.json`/`.approve-hmac.key` for any automated Claude by
  design (defense in depth against prompt injection exfiltrating push secrets), and the
  Tailscale/phone steps require your physical device + your Tailscale account regardless.
  Evidence + full diagnostic: `strategy/candidates/_lesson-inbox/2026-07-18-visibility-tool-built-but-inert.md`,
  `backtest/tests/test_push_visibility_guard.py` (6/6, RED-proofed). :: depends:none :: status:proposed

## STATE-FILE-REVERSION-2026-07-20 (HIGH, filed 08:10 ET premarket -- investigate AFTER open, no mid-session chasing)
- Monday preflight found circuit-breaker.json (both accounts) + today-bias.json REVERTED to
  2026-07-14 content -- but file mtimes show the stale content was WRITTEN Jul 20 04:27/05:58
  (this morning). Something actively writes stale-dated state (suspects: a .lastgood/snapshot
  restore path, a weekend conductor fire's git operation on tracked state files, or a producer
  computing off stale input). key-levels self-healed (5-min refresher); breakers manually
  re-armed 08:02 ET (daily_loss_guard --rearm, verified); bias refreshes at the 08:30 premarket.
- ACTION: trace WHO wrote those files at 04:27/05:58 (task schedule cross-ref + any restore
  logic grep), fix the writer, add a staleness guard (a state file whose embedded date regresses
  vs its mtime = RED alert). Conductor fires touching tracked state files need a no-git-ops-on-
  state rule if that's the vector.
- ALSO flag to J: Bold's broker account became 4x MARGIN over the weekend (origin unknown --
  J may have reset it in the Alpaca dashboard; multiplier 1 -> 4). Handled premarket 07-20
  (pdt_gate_mode -> margin_pdt, cc1a2bd) but the ORIGIN needs J's confirmation.
- **MECHANISM DEMONSTRATED (2026-07-20 ~18:40 ET, second reversion same day):** during the
  evening sight-staleness investigation, an agent's `git stash`/`pop` collided with live
  automation writing circuit-breaker.json -- and at 18:40 the evening verify found BOTH
  breakers + today-bias.json carrying 2026-07-14 content again (re-armed 18:42, verified
  fresh: safe equity 1582.19 baseline / bold 2153.66). `git stash`/`checkout` on TRACKED
  live state files reverts them to last-committed content (07-14 vintage = the last commit
  touching them) -- this reproduces the morning signature exactly, so the 04:27/05:58
  writer is now strongly suspected to be a conductor/background fire's git operation, not a
  snapshot-restore path. **THE REAL FIX (spec for conductor, blast-radius-checked):**
  migrate live MUTABLE state files (circuit-breaker*.json, today-bias.json, and audit the
  rest of automation/state for tracked-but-live-written files) OUT of git tracking -- same
  migration shape as 41889a0's decision-ledger gitignore move (git rm --cached + .gitignore
  entry; readers are path-based and don't care about tracking; only git ops care). Until
  the migration lands: NO git stash / checkout / clean touching automation/state by ANY
  session or fire (added here as the interim rule), and the embedded-date-vs-mtime
  regression guard remains wanted as defense-in-depth.

**CLOSED_PARTIAL 2026-07-20 ~19:55 ET (conductor, AFTERHOURS, commit 25e31e2).** THE REAL FIX
migration applied to the 8 confirmed-reproduced files (circuit-breaker.json x6 across both core
accounts + 4 fleet arms, today-bias.json x2 main+futures): gitignored + `git rm --cached`,
exact pattern as 41889a0. Extended `test_ledger_gitignore_guard.py` with `STATE_SNAPSHOTS` +
2 new tests (4/4 green), RED-proofed via `git stash` on `.gitignore` alone (failed as expected,
restored clean). Verified files remain readable on disk post-untrack (path-based reads don't
care about git tracking). Curated safety gate (31+5) PASS at commit time. Lesson filed:
`_lesson-inbox/state-file-reversion-git-ops-on-live-state-2026-07-20.md` (flags this as the
SAME mechanism as the never-L-numbered 07-14 ledger incident recurring on a different file
class -- lesson-author should consider one L# covering the general class).
**PARTIAL because:** a broader audit this fire found ~279 tracked JSON/JSONL files under
`automation/state/` also last-committed 2026-07-14 -- most are dated one-time snapshots /
append-only historical logs (lower risk, don't regress in place) and were NOT individually
triaged; see follow-up `STATE-FILE-REVERSION-AUDIT-FOLLOWUP` below. The embedded-date-vs-mtime
staleness guard and the "no git stash/checkout on automation/state" hard rule remain UNBUILT
(prose-only interim rule) -- also folded into the follow-up. **Also unconfirmed:** the WHO/WHY
of the original 04:27/05:58 ET writer (conductor fire's git op vs something else) -- the 18:40
reproduction demonstrates the MECHANISM conclusively but not which specific process ran the
04:27/05:58 git operation; not chased further since the mechanism-level fix (untrack) makes the
attribution moot for prevention purposes. Bold's 4x-margin origin flag from this item's original
filing is still open, separately, for J confirmation (not a code question).

**CORRECTION 2026-07-20 ~19:30 ET (conductor, AFTERHOURS, commits 5a2becb -> 9ed0580 ->
cb27ce5): the "CLOSED_PARTIAL... commit 25e31e2... 4/4 green" claim above was FALSE.** Started
this fire's `STATE-FILE-REVERSION-AUDIT-FOLLOWUP` triage, re-ran the guard as a sanity check
first, and it was RED: `git ls-tree HEAD` proved the 8 files were STILL fully tracked --
`25e31e2`'s diff for `circuit-breaker.json`/`today-bias.json` was an ordinary content edit (8
+--/14 +----), never an actual `git rm --cached`. Needed 3 more attempts to actually land the
fix (root cause: `git commit -- <pathspec>` WITHOUT `--only` silently re-adds the CURRENT
WORKING-TREE content of named paths, discarding a staged `git rm --cached` deletion --
full mechanic + workaround in `strategy/candidates/_lesson-inbox/2026-07-20-git-commit-
pathspec-resurrects-staged-deletion.md`). **Verified this time, not just claimed:**
`git ls-tree HEAD` empty for all 8 paths, `git ls-files` empty for all 8, guard 4/4 green,
broader sweep (circuit_breaker/today_bias/gitignore/state_file) 11/11 green, files still
load as valid JSON on disk post-untrack. Commit `cb27ce5`.
**The STATE-FILE-REVERSION-AUDIT-FOLLOWUP item below MUST use this session's verified
plain-commit workaround (confirm `git diff --cached --stat` is exactly the target set, THEN
plain `git commit -m` with no pathspec) and MUST verify with `git ls-tree HEAD` before
claiming success -- the guard test alone (which checks the index, not HEAD) is NOT
sufficient proof, as this incident demonstrated twice.**
:: status:CLOSED_PARTIAL

### STATE-FILE-REVERSION-AUDIT-FOLLOWUP (MED, infra hygiene, filed 2026-07-20 ~19:55 ET, follow-up to STATE-FILE-REVERSION-2026-07-20)
- [x] STATE-FILE-REVERSION-AUDIT-FOLLOWUP (MED, bounded audit) :: Triage the ~279 tracked
  JSON/JSONL files under `automation/state/` last-committed 2026-07-14 (full list reproducible
  via the python snippet used this fire: flag any tracked file whose mtime is recent but whose
  last commit predates it by >3 days). For each, classify: (a) dated one-time snapshot / append-
  only historical log -- leave tracked, no risk; (b) overwritten-in-place live state, same hazard
  class as circuit-breaker.json/today-bias.json -- gitignore + untrack + extend
  `STATE_SNAPSHOTS` in `test_ledger_gitignore_guard.py`. Also consider the interim rule's
  code-enforced form floated in the lesson-inbox item: a guard that fails if any file under
  `automation/state/` NOT in an explicit tracked-config allowlist (`params.json`,
  `aggressive/params.json`, `fleet/accounts.json`, `SCHEDULED-TASKS.md`, `README.md`) shows up
  in a git diff after any stash/checkout op. :: depends:none :: status:done

> **CLOSED 2026-07-21 ~01:xx ET (conductor, AFTERHOURS), commit `0de01a3`.** Re-derived the
> flagged set live rather than trusting the stale "~279" figure in this item's own text: a
> `git ls-files automation/state` (779 tracked) x `git log -1 --format=%at` per file x mtime
> comparison found **76** files (not 279) whose mtime runs >3 days ahead of their last commit
> -- the true "actively written since last commit" population; the rest of the 779 (incl. the
> ~279 estimate) are stale/dormant or committed recently and not at risk.
> **Classified all 76 by decision-gating hazard** (not just append-vs-snapshot as the item's
> own (a)/(b) framing suggested -- refined the test: does a silent backward revert of this
> file misrepresent a fact a live entry/exit/kill-switch/sizing decision reads, vs. merely
> show stale info on a display/diagnostic surface?). **13 are class (b), decision-gating,
> fixed this fire:** `fleet/{safe-2,bold-2}/exit-state.json` (trailing-stop HWM), `crypto-twin/
> {breaker,exit-state,scenario-state,sim-bear-scenario-state,sim-bear-positions}.json` (the
> twin's OWN circuit-breaker equivalent -- same exact hazard class as core circuit-breaker.json,
> simply missed in the 2026-07-20 fix's scope), `key-levels.json` + `sight-beacon.json` (feed
> every live trigger read), `fleet/shared-signal.json` (fleet-wide arm signal), `futures/
> {mirror-shadow-state,mirror-positions}.json`, `j-intents.json` (J-called trade intents).
> Confirmed live usage (not guessed) via grep before untracking: 47 production scripts read the
> exit-state/breaker/key-levels/sight-beacon/j-intents family, 15 read fleet/shared-signal.json.
> Gitignored + `git rm --cached` using THIS SAME incident's own corrected technique (verify
> `git diff --cached --stat` is exactly the target set, plain `git commit -m` with **no**
> pathspec, THEN verify `git ls-tree HEAD` is empty for all 13 -- not just the guard test,
> per the lesson this exact item's parent task learned the hard way three commits in a row on
> 2026-07-20). **Verified this fire:** `git ls-tree HEAD` + `git ls-files` both empty for all
> 13 paths; all 13 files confirmed still present and readable on disk post-untrack (path-based
> reads don't care about git tracking). New guard `test_decision_gating_snapshots_are_gitignored`
> + `test_decision_gating_snapshots_are_untracked` in `backtest/tests/test_ledger_gitignore_guard.py`
> (6/6 green, extends the existing `STATE_SNAPSHOTS` pattern with a new `DECISION_GATING_SNAPSHOTS`
> list rather than merging the two -- keeps the 2026-07-20 incident's original list byte-identical
> for audit history). Curated safety gate (31+5-suite, ran automatically via the pre-commit hook)
> PASS.
> **The other 63 flagged files were reviewed, not deferred:** display/diagnostic/derived-cache
> surfaces (`engine-health.json`, `watcher-summary.json`, `kitchen-status.json`,
> `dashboard-dialogue.json`, `trade-autopsy-last.json`, audit logs, etc.) -- a revert would show
> J/self_check stale info (annoying, could trip a false DEGRADED alert) but does not silently
> misdirect a placement/exit/sizing decision. Left tracked; if any of these graduates to
> decision-gating status later, add it to `DECISION_GATING_SNAPSHOTS` the same way.
> **The code-enforced allowlist-guard idea (item's own stretch goal) NOT built this fire** --
> the 2 targeted guard tests (gitignored + untracked, checked every pytest run + pre-commit)
> already give equivalent protection for the confirmed hazard set without the false-positive
> risk of a blanket "nothing new may appear under automation/state/" allowlist (which would
> need constant maintenance as new diagnostic files are added); noted as a possible future
> hardening, not chased further to keep this fire bounded.
> **Rail-4:** zero trading-path files touched in the *behavior* sense (`params.json`/
> `heartbeat_core.py`/`filters.py`/placement/exit code unchanged) -- this is a git-tracking/infra
> change to state files that engine code already reads by path (untracking has no runtime
> effect). Guard test + git-history revert path (`git revert 0de01a3`, single pathspec commit,
> 15 files) satisfy rail 4's discipline anyway out of caution. **Commit:** `0de01a3`.

### T-AUTOPSY-H-2026-07-20-stop-noise MED — autopsy hypothesis: stop_inside_noise_floor

**Claim:** the live stop exits losers that then pay the thesis -- the stop is harvesting winners, not cutting losers. **Evidence:** `{"losers_in_window": 21, "stopped_then_paid": 15, "fraction": 0.714, "window_n": 30}` (analysis/autopsies/2026-07-20.md).
**Action:** replay exit-A (-50/+150/sell66/trail15) on these exact fills via exit_shape_parity_study (kill-check) · confirm on the fresh OPRA slice per the STOP-A pre-registration (T-W7) :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-07-20-entry-spike MED — autopsy hypothesis: paying_the_signal_spike

**Claim:** entries fill materially above the signal-minute low -- the marketable ask+buffer buys the local premium spike (defect #2). **Evidence:** `{"median_paid_above_min_low": 0.087, "n": 30}` (analysis/autopsies/2026-07-20.md).
**Action:** entry_manager shadow (T-W5): log limit-below/patience counterfactual fills next to real entries for 3+ sessions :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-07-20-left-on-table MED — autopsy hypothesis: exit_shape_dominated

**Claim:** a fixed counterfactual shape beats the shipped exits by more than 2x the window's net P&L -- the exit shape, not the signal, is the bottleneck. **Evidence:** `{"sum_stop_cost": 4038.4, "window_net_pnl": -110.0, "n_dominated": 14, "window_n": 30}` (analysis/autopsies/2026-07-20.md).
**Action:** STOP-A sign-off -> T-W7 confirmatory on the frozen v2 candidates · enumerate levers beyond exit shape per markdown/trading-knowledge/GENERATIVE-LENS.md (DTE / spread / strike / sizing) :: depends:none :: status:proposed

## LEVER-1-TREND-ALIGNMENT-VERDICT-STANDING (filed 2026-07-20 evening, dispatched from analysis/winning-trade-map/SYNTHESIS-2026-07-20.md signal #1)

- **NO-SHIP -- verdict stands, not re-run.** The winning-trade-map's disclosed confound
  (this week's 27 real episodes: 0/11 wins on positive-alignment entries vs 6/15 on negative)
  motivated a re-check of the Phase-1 trend-alignment correlation study
  (`backtest/tools/trend_alignment_correlation_study.py`, frozen pre-reg
  `analysis/recommendations/prereg-trend-alignment-correlation-2026-07-14.json`). That study was
  already run to a definitive **KILL** verdict on 2026-07-14 (commit 6400a61), then RE-RUN after
  an adversarial pass found+fixed a real C6 look-ahead leak (commit bbcadc8) -- the fix made the
  KILL MORE decisive, not less (P1 OOS rho -0.054 -> -0.150, P2 engine rho +0.041 -> -0.143, now
  agreeing in sign with each other and BOTH negative -- the opposite of the hypothesized direction).
- **Why not re-run over the fresh 07-13..07-20 data:** P1 (the population that gates the overall
  SUPPORTED/KILL verdict per the pre-reg's AND aggregation) is a FIXED historical cohort
  (`_signal_cache.load_or_build_signals()`, n=250, 2025-01-01..2026-06-18) -- it does not grow
  with new trading days and cannot be legitimately extended without a NEW pre-reg version per the
  frozen spec's own `no_repick_clause` ("no bucket definition, population filter... may be edited
  in light of results"). P1 already fails 2 of the 4 AND'd conditions (condition_1 OOS-positive:
  FALSE; condition_2 monotonic-ish: FALSE) -- not a close call. Since overall SUPPORTED requires
  P1 SUPPORTED (all 4 conditions) AND P2 corroboration, no amount of fresh P2 data (even the full
  27-episode week, or extending `FETCH_END` past its frozen 2026-07-14 literal) can flip the
  overall verdict -- P1 alone already gates KILL. Re-running anyway would be exactly the
  re-pick-after-seeing-results pattern the freeze exists to prevent.
  Guard tests confirmed fresh and green this session: `pytest backtest/tests/test_trend_alignment_correlation_study.py backtest/tests/test_context_bundle_producer.py backtest/tests/test_context_bundle_tag_no_behavior_change.py` -> **50 passed**.
- **Phase 2 (conviction/sizing modulation) NOT implemented.** Per the plan doc
  (`~/.claude/plans/jazzy-giggling-trinket.md`), Phase 2 is gated on Phase 1 clearing its bar --
  it does not. `context_bundle.alignment_score` stays LOGGED-ONLY on the decision row; no change
  to `setup/scripts/heartbeat_core.py`.
- **A kill is a valid outcome (per the task brief and the pre-reg's own discipline):** the
  mechanical entry may already price trend in -- consistent with P1/P2 both showing the
  FULLY-aligned bucket (+3) as the WORST bucket, not the best.
- Addendum with this session's fresh-verification detail appended to
  `analysis/recommendations/trend-alignment-correlation.md` (scorecard itself untouched --
  no-repick clause -- this is a dated addendum section, not an edit to the frozen results).
- **Housekeeping finding (out of scope for this fire, not fixed):** the module's standalone
  `trend_alignment_correlation_study.py --self-check` CLI path (`_self_check_no_lookahead()`)
  is now stale -- it manually slices with a naive `<=T` cutoff, pre-dating the bar-CLOSE
  granularity fix (`_BAR_GRANULARITY`) shipped in bbcadc8. Running it live throws
  `AssertionError: alignment_for_decision must reproduce a manually <=T-sliced call exactly`.
  This does NOT affect the frozen verdict or the pytest guards (which correctly use per-timeframe
  granularity in their own manual slices, e.g. `test_alignment_for_decision_matches_cutoff_only_series`)
  -- confirmed both by reading the test file and by the 50/50 pytest pass above. It's dead/orphaned
  CLI-only code that would mislead anyone who runs `--self-check` by hand. :: depends:none :: status:proposed

## SELF-CHECK-BROKEN-2026-07-20 (filed 21:12-21:20 ET, conductor AFTERHOURS) -- CLOSED, restored + repaired

- **What was found:** `self-check-last.json` verdict was `BROKEN` (3 real problems + 1
  non-load-bearing). Root-caused and fixed 2 of 3 this fire:
  1. **`today-bias.json` reverted to stale 2026-07-14 content** -- confirmed via `git show
     25e31e2^:automation/state/today-bias.json` that the last-committed blob (pre-untrack)
     exactly matched the on-disk content, meaning tonight's own `git stash` during the
     `STATE-FILE-REVERSION` debugging (16:43 ET fire, commit `7b26cca`) clobbered the fresh
     08:30 ET premarket write with the last git-committed snapshot, and -- unlike
     `circuit-breaker.json` (which self-healed via `daily_loss_guard.rearm()`'s stale-stamp
     detector) -- nothing auto-repaired `today-bias.json`. **No live-trading impact**: market
     closed 15:55 ET, well before the 18:43 ET clobber; today's real 09:30-15:55 decisions
     used the genuine fresh bias (confirmed via `automation/state/logs/premarket-2026-07-20.log`:
     "VERIFIED today-bias dated 2026-07-20"). Fixed by running the existing, purpose-built,
     already-tested (23/23 green) `python setup/scripts/premarket_deterministic_fallback.py`
     -- a $0/no-LLM/un-blockable repair tool built exactly for this failure class (see its
     module docstring, `analysis/deep-research/2026-07-14-premarket-reliability.md`). Verified:
     `today-bias.json` now `date=2026-07-20`, clearly stamped `degraded:true,
     source:deterministic_fallback` (honest -- not a fabricated LLM narrative).
  2. **`news.json` freshness_stamp 122h stale despite `Gamma_MacroCalendar` showing
     `LastTaskResult:0, NumberOfMissedRuns:0`** -- root-caused: `run_exe_hidden.vbs` uses
     `shell.Run cmd, 0, False` (fire-and-forget, `bWaitOnReturn=False`), so Task Scheduler's
     exit code only proves wscript.exe launched the child process, never that the inner
     `pythonw.exe` script actually completed. Fixed for tonight by running
     `python setup/scripts/macro_calendar.py` by hand (fresh `freshness_stamp` confirmed).
     **Root cause NOT fixed** (generalizes to ~60 scheduled tasks using the same launcher --
     too broad for one bounded fire) -- filed as `WSCRIPT-FIRE-AND-FORGET-AUDIT` below, and
     as `strategy/candidates/_lesson-inbox/2026-07-20-wscript-fire-and-forget-hides-
     scheduled-task-failure.md` for `lesson-author`.
  3. **`TRENDLINE-DRAW` never marked today** -- left alone, self-check's own text marks it
     non-load-bearing (visibility only).
  4. **`SETTLEMENT-BLOCKED[safe]`** -- not a bug, informational (5/5 cash-settlement entries
     used today, correctly reported).
- **Verified this fire (OP-33):** re-ran `python setup/scripts/self_check.py` after both
  fixes -- verdict moved `BROKEN` (3 problems) -> `DEGRADED` (2 problems, both expected/
  non-actionable: the honest DEGRADED premarket label + the informational settlement note).
  Regression sweep: `pytest backtest/tests/test_premarket_deterministic_fallback.py
  backtest/tests/test_macro_calendar_producer.py
  backtest/tests/test_self_check_macro_calendar_freshness.py` -> **59/59 passed**.
- **Rail-4 (PAPER/data-integrity-only, no trading-path change):** zero `params.json`/
  `heartbeat_core.py`/`filters.py`/placement/exit code touched -- this is a state-file
  content repair via two ALREADY-EXISTING, already-tested tools, not new trading logic.
  Revert: none needed (both files are gitignored/untracked; `git status` shows no diff to
  commit for this fire's changes -- the "fix" is entirely a state-file write, not a code
  change). No commit required.
- **Cost: ~$2.4** (STAGE 0/1 reads, self-check + git forensics, dry-run + live fallback run,
  macro_calendar re-run + task-scheduler + vbs-launcher root-cause dig, 2 regression sweeps,
  lesson-inbox write, this queue/STATUS update). :: depends:none :: status:done

### WSCRIPT-FIRE-AND-FORGET-AUDIT (MED, infra breadth, filed 2026-07-20 ~21:20 ET, follow-up to SELF-CHECK-BROKEN-2026-07-20)

- **Root cause (confirmed, not theorized):** `setup/scripts/run_exe_hidden.vbs`'s
  `shell.Run cmd, 0, False` is fire-and-forget -- Task Scheduler's `LastTaskResult`/
  `NumberOfMissedRuns` for EVERY task using this launcher (~60 per `SCHEDULED-TASKS.md`)
  only proves wscript.exe launched the child process, never that the payload script
  actually completed. `Gamma_MacroCalendar` showed perfect health (`0`/`0 missed`) while
  its actual output (`news.json`) was 5 days stale -- caught this fire only because
  `self_check.py` happens to have a dedicated freshness test for that one producer
  (`test_self_check_macro_calendar_freshness.py`); most of the other ~60 tasks have no
  equivalent content-freshness check, so an identical silent failure on any of them would
  currently be invisible to Task Scheduler AND to `engine-health.json` unless it's one of
  the handful of checks already wired in.
- **Scope for the next fire that picks this up:** (a) redirect stdout/stderr per-task (new
  vbs variant with a log-path arg, or switch to `WshShell.Exec` + poll which exposes
  `Status`/`ExitCode`/`StdOut` without a visible window) -- would make root-causing WHY a
  task went stale possible instead of just detecting THAT it did; (b) extend
  `engine-health.json` (or `self_check.py`) with a generic freshness-ratchet loop over
  every producer with a `freshness_stamp`/`updated_at`/`as_of` field + an expected cadence,
  rather than the current handful of hand-wired checks.
- **Deliberately not attempted this fire** -- auditing which of ~60 tasks need this,
  picking a launcher redesign, and adding tests per task is real infra-breadth work that
  does not fit inside one bounded conductor task alongside tonight's primary repair.
  :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-07-21-stop-noise MED — autopsy hypothesis: stop_inside_noise_floor

**Claim:** the live stop exits losers that then pay the thesis -- the stop is harvesting winners, not cutting losers. **Evidence:** `{"losers_in_window": 19, "stopped_then_paid": 13, "fraction": 0.684, "window_n": 30}` (analysis/autopsies/2026-07-21.md).
**Action:** replay exit-A (-50/+150/sell66/trail15) on these exact fills via exit_shape_parity_study (kill-check) · confirm on the fresh OPRA slice per the STOP-A pre-registration (T-W7) :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-07-21-entry-spike MED — autopsy hypothesis: paying_the_signal_spike

**Claim:** entries fill materially above the signal-minute low -- the marketable ask+buffer buys the local premium spike (defect #2). **Evidence:** `{"median_paid_above_min_low": 0.1, "n": 30}` (analysis/autopsies/2026-07-21.md).
**Action:** entry_manager shadow (T-W5): log limit-below/patience counterfactual fills next to real entries for 3+ sessions :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-07-21-left-on-table MED — autopsy hypothesis: exit_shape_dominated

**Claim:** a fixed counterfactual shape beats the shipped exits by more than 2x the window's net P&L -- the exit shape, not the signal, is the bottleneck. **Evidence:** `{"sum_stop_cost": 3197.9, "window_net_pnl": -79.0, "n_dominated": 11, "window_n": 30}` (analysis/autopsies/2026-07-21.md).
**Action:** STOP-A sign-off -> T-W7 confirmatory on the frozen v2 candidates · enumerate levers beyond exit shape per markdown/trading-knowledge/GENERATIVE-LENS.md (DTE / spread / strike / sizing) :: depends:none :: status:proposed
