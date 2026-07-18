# GOAL: engine replays 2026-07-17 GREEN on all 6 arms, via generalizable tuning

> J-set goal (2026-07-17 ~18:50 ET, "put yourself in a loop until the goal is done"):
> "today's 6am table making $ on EACH arm + executing good entries and exits from replaying
> today with the engine. fine-tune the engine until it can replay today and make $ with our
> sniper entries and tech analysis."

## The eval (what "done" measures)
Replay 2026-07-17's real tape through EACH of the 6 arms' configs and score:
1. Per-arm P&L on today's replay (target: all 6 > $0).
2. CAPTURED the day's sniper entries: 13:01 trendline_rejection put (+$241 live), 14:03
   bollinger wick put (+$105), 13:51 bold trendline put (+$191), the J-called 746C retest.
3. AVOIDED / reduced the losers: 11:06 & 11:40 ELITE static-level rejections into an
   unexhausted bounce (−$37, −$102 live).
4. Exits captured a fair share of each winner's available move (trend-day exit quality).

## THE ANTI-OVERFIT LAW (non-negotiable — this is what makes the win real)
Tuning ONLY on today's tape = curve-fitting = a config that loses Monday. Every lever:
- must be driven by a GENERALIZABLE finding (the audits, not "today needs X"),
- must be validated on an OOS basket (recent days + the OP-16 anchor days) — a lever that
  helps ONLY today is REJECTED,
- today's replay is the CONFIRMATION eval, never the fitting target.
Fable-too-good applies at every green: a suspiciously clean replay is hunted, not celebrated.
If the honest ceiling is "not all 6 can be green OOS-safely on this tape," that is a valid
terminal state — report it, don't force it.

## Lever queue (from today's 6 audits — each gets OOS-validated before it counts)
| # | Lever | Source audit | Fixes which arm(s) |
|---|---|---|---|
| L1 | Static-vs-trendline tier down-weight in bounce phase | safe-tape | core Safe morning losers |
| L2 | Trend-day exit tuning (chandelier/hold vs current SS-B) | safe-tape + TRAIL60 | Safe/Bold winners left money |
| L3 | Fleet tight-gate: single-trigger trendline admission | tight-arms | safe-3, risky-1 (dark) |
| L4 | Fleet strike tier vs $0.30 floor (OTM-3 priced out winner) | tight-arms | fleet arms |
| L5 | Favorable-extreme (wick) entry targeting | wick study (running) | all arms, entries |
| L6 | HTF level tier (June30/Jul2/Jul8 shelf) | htf-levels | morning bull participation |

## Loop structure (self-paced via ScheduleWakeup)
1. Build the replay-today eval harness (iteration 1, running). Baseline all 6 arms; confirm the
   harness reproduces live P&L (safe +240 / bold +191 / risky-3 +248 / tight ~0) = faithful.
2. Each iteration: pick highest-value lever → OOS-validate → if it holds, apply (params/guard/
   revert) → re-run today's replay → record per-arm delta in this doc's LEDGER.
3. Continue until all 6 arms > $0 on today's replay with every applied lever OOS-clean, OR an
   honest ceiling is documented.
4. STATUS.md carries the live scorecard so J sees progress on return.

## LEDGER (append each iteration: lever, OOS verdict, today-replay per-arm result)
- (iteration 1: building the eval harness + baseline)
- **ITERATION 1 COMPLETE (2026-07-17 ~19:15 ET) -- eval harness built, baseline established,
  HARNESS NOT YET FAITHFUL (honest terminal state for this iteration, per the anti-overfit law's
  own "report it, don't force it" clause).** Tool: `backtest/tools/replay_today_eval.py`. Output:
  `analysis/recommendations/replay-today-baseline-2026-07-17.json`. Guard:
  `backtest/tests/test_replay_today_eval.py` (14/14 pass). No params/config/strike-table file
  touched -- measurement only.
  | arm | live P&L | replay P&L | delta | faithful (±$150, same-sign)? |
  |---|--:|--:|--:|:--:|
  | core_safe | +$240 | +$55.12 | -$184.88 | NO |
  | core_bold | +$191 | -$250.00 | -$441.00 | NO (wrong sign) |
  | fleet_safe_3 | $0 | $0 | $0 | YES (trivial) |
  | fleet_risky_1 | $0 | $0 | $0 | YES (trivial) |
  | fleet_risky_3 | +$248 | +$32.75 | -$215.25 | NO |
  Capture: 1/4 in-scope named events captured (13:51 bold trendline put only); 13:01 trendline
  put + both 11:06/11:40 ELITE losers MISSED by the replay. 14:03 bollinger-wick put + the
  12:04 J-called 746C are OUT OF SCOPE by construction (separate setup family / no engine rule
  exists yet respectively), disclosed not papered over.
  **ROOT CAUSE (diagnosed, not just observed): level-set source mismatch is DOMINANT, not the
  5 exit-mechanics fidelity approximations.** lib.orchestrator's price-history auto-detected
  levels found ZERO candidate triggers near 11:06/11:40 ET (live's real ELITE entries) while
  inventing an 11:35 ET level_rejection for core_bold that live never took (-$467.50 stopped,
  alone flipping core_bold's day from live's +$191 to replayed -$250). Live's actual level set
  is `automation/state/key-levels.json` (refreshed intraday 08:28 ET today) plus J's manually
  ARMED zone-rejection intents (journal 10:39 ET) -- neither is consumed by the research
  orchestrator's own auto-detector. Secondary: 5-min bar granularity (71 rows) vs live's 1-min
  heartbeat (386 ticks) compounds timing/count divergence.
  **VERDICT: this harness is NOT trustworthy to tune against yet.** Tuning any of the L1-L6
  levers on top of it this iteration would be optimizing against a signal stream that doesn't
  match what the live engine actually sees -- a lever that "fixes" the replay could easily be
  fixing an artifact of the level-set gap, not a real edge, and would fail the anti-overfit
  law's OOS-validation requirement anyway once tested honestly. Iteration 2's highest-value next
  step: feed this harness live's real level pipeline (key-levels.json + armed zone intents)
  before touching any lever, then re-baseline faithfulness before the loop proceeds to tuning.
- **ITERATION 2 COMPLETE (2026-07-17 ~20:00 ET) -- architectural rebuild: SIGNAL/CONTEXT layer
  now reads verbatim from the recorded automation/state/core-decisions.jsonl + each fleet arm's
  decisions.jsonl (no level re-detection anywhere); DECISION layer (classify_tier/gates) and
  EXIT layer (lib.simulator_real.simulate_trade_real, real OPRA bars) re-run on top of that
  faithful input stream. STILL NOT FAITHFUL to tight tolerance -- honest terminal state for this
  iteration, per the anti-overfit law's "report it, don't force it" clause; the harness moved
  from a SIGNAL problem to a precisely-diagnosed DATA-RESOLUTION problem (see below).** Same
  tool: `backtest/tools/replay_today_eval.py` (rebuilt, not new). Output:
  `analysis/recommendations/replay-today-baseline-2026-07-17.json`. Guard:
  `backtest/tests/test_replay_today_eval.py` (13/13 pass, new: signal-layer capture pin +
  decision-layer tier-reproduction pin + engine-only-truth pin, on top of the determinism +
  faithfulness pins carried over from iteration 1).

  **SIGNAL LAYER: FIXED, verified.** Capture 5/5 in-scope named events (iteration 1: 1/4).
  Decision-layer tier reproduction 12/12 (classify_tier() on the recorded/reconstructed triggers
  matches live's own recorded tier on every extracted entry, zero mismatches). Root cause #6
  (level-set source mismatch) is closed BY CONSTRUCTION -- there is no level detector left in
  this harness to disagree with live; entries' strike/qty/side/triggers/stop-reference-level are
  all read verbatim from the engine's own recorded exec blocks.

  | arm | live P&L (raw) | live P&L (engine-only) | replay P&L | delta vs engine-only | faithful (tol)? |
  |---|--:|--:|--:|--:|:--:|
  | core_safe | +$240 | +$151 (excl. $89 J-called 746C, no engine rule fires it) | -$312.00 | -$463.00 | NO |
  | core_bold | +$191 | +$191 | +$65.25 | -$125.75 | NO |
  | fleet_safe_3 | $0 | $0 | -$83.25 | -$83.25 | NO (tol $40) |
  | fleet_risky_1 | $0 | $0 | -$138.75 | -$138.75 | NO (tol $40) |
  | fleet_risky_3 | +$248 | +$248 | -$36.75 | -$284.75 | NO |

  Tolerance this iteration: max($40, 15% of \|live_engine_pnl\|) per arm -- deliberately much
  tighter than iteration 1's $150 (the task's own instruction: "near-exact, not +/-$150"), NOT
  reverse-fit to pass anything -- 0/5 arms clear it, reported honestly.

  **ROOT CAUSE of the residual (quantified with real numbers this run, not asserted): the EXIT
  layer's only available data is 5-MINUTE OPRA/SPY bars; live trades on a ~1-minute clock, and
  today's 0DTE option premiums moved fast enough intrabar that 5-minute resolution provably
  cannot reproduce live's fills/exits.** Two distinct, disclosed mechanisms:
  (a) *Entry-fill-price approximation* -- "next 5-min bar open + slippage" missed by $0.23/30%
  on core_safe's 13:01 trendline entry ($1.01 sim vs $0.78 live -- the premium fell sharply in
  the bar's first ~90 seconds) vs only $0.07 on the 11:06 entry -- bar-dependent, not a fixed
  offset. (b) *Exit-mechanism gap, both directions* -- the chart-level stop (5m bar CLOSE vs
  level+/-$0.50 buffer) fires LATER than live's faster structure-stop (core_safe 11:06: live
  exited in 5 min for -$37; this harness needed 25 min to confirm a buffered breach), while the
  premium/profit-lock stop (checks each 5-min bar's LOW as the conservative worst-case touch)
  fires EARLIER/WRONGLY -- once profit-lock arms at +5% the floor jumps to breakeven, and a
  5-min bar's LOW round-tripping back to that floor zeroed out 3 of core_safe's 5 entries (13:01,
  14:03, 14:49) that on live's real tape ran to +$241/+$105/-$56 without ever giving back that
  much intrabar. Neither mechanism is a bug (both are the same real, shared, production-used
  simulate_trade_real code every other real-fills caller in this codebase relies on) and neither
  is lever-tunable -- no lever changes what data is available. Filed separately per task
  instruction, not patched blindly here: `markdown/planning/FUTURE-IMPROVEMENTS.md` PARITY-GAP-2.

  **Capture report (with the faithful stream):** 13:01 trendline put -- CAPTURED. 14:03
  bollinger wick put (via the extra_exec side channel, excluded by iteration 1's primary-channel-
  only read) -- CAPTURED. 11:06 + 11:40 ELITE losers -- both CAPTURED. 13:51 bold trendline put
  -- CAPTURED. 12:04 J-called 746C stays correctly OUT OF SCOPE (no engine rule, confirmed again
  via trades.csv j_override='Y').

  **VERDICT: harness_verdict.trustworthy_to_tune_against = False.** The SIGNAL/DECISION layers
  are now faithful and ready; the EXIT layer is not, for a precisely diagnosed, non-lever-
  tunable reason. Per the task instruction ("If and ONLY IF faithfulness now passes, name the
  next lever") -- it does not pass, so NO lever is named/tuned this iteration. Per the
  anti-overfit law, tuning ANY of L1-L6 on top of this EXIT layer right now would risk fitting
  an artifact of the 5-minute-bar exit-timing gap rather than a real edge. Iteration 3's actual
  choice is between (i) acquiring finer-resolution (1-minute) OPRA option bars for today to
  close the exit-layer gap, or (ii) documenting the 5-minute-bar ceiling as a standing harness
  limitation and re-scoping the faithfulness check to ENTRY-side-only levers (L1, L6) that don't
  route through the exit walk -- a decision for iteration 3 to make explicitly, not pre-picked
  here.
- **ITERATION 3 COMPLETE (2026-07-17 ~20:55 ET) -- chose option (i): acquired real 1-minute OPRA
  option bars + 1-minute SPY bars for exactly today's 7 traded contracts. RESULT, HONEST (not
  forced): the entry-fill-price mechanism is FIXED; the exit-mechanism mechanism is NOT fixed --
  1-min resolution revealed a DIFFERENT, MORE SEVERE artifact of the same underlying fragility,
  not a smaller one. Harness still NOT trustworthy_to_tune_against at the exit-layer dollar
  level.** Tool: `backtest/tools/fetch_today_1min.py` (new, bounded, 8 REST calls, $0) ->
  `backtest/data/highres/*_1m_2026-07-17.csv`. `backtest/tools/replay_today_eval.py` extended
  with `simulate_entry_best()` (1-min primary, 5-min `simulate_entry()` fallback, never triggered
  this run). Two new backward-compatible optional kwargs added to the SHARED
  `backtest/lib/simulator_real.simulate_trade_real()` (`entry_fill_delay_minutes`,
  `opt_df_override`, both default to prior 5-min behavior byte-for-byte) so the 150+ other callers
  of that function are provably unaffected -- full existing pytest suite re-run clean (223 passed
  / 1 skipped, zero regressions) before and after. Guard: `backtest/tests/test_replay_today_eval.py`
  now 24/24 (13 iteration-2 pins unchanged + 11 new iteration-3 pins).

  **1-min data availability: REAL bars, not BS-approx.** All 7 contracts (SPY260717P00741000
  through P00746000 + C00746000) plus SPY itself returned gapless 1-minute OPRA/stock bars
  covering the full 390-minute RTH session on the existing Safe-2 paper-key market-data
  entitlement -- no fallback needed, confirmed via a direct test fetch before building anything.

  | arm | live P&L (engine-only) | replay P&L (5-min, iter 2) | replay P&L (1-min, iter 3) | faithful (1-min)? |
  |---|--:|--:|--:|:--:|
  | core_safe | +$151 | -$312.00 | $0.00 | NO (tol $40) |
  | core_bold | +$191 | +$65.25 | +$99.00 | NO (tol $40) |
  | fleet_safe_3 | $0 | -$83.25 | $0.00 | YES (trivial) |
  | fleet_risky_1 | $0 | -$138.75 | $0.00 | YES (trivial) |
  | fleet_risky_3 | +$248 | -$36.75 | +$4.00 | NO (tol $40) |

  Faithfulness: 2/5 arms (both trivial $0/$0, not a mechanism win) -- same count as would clear
  by coincidence, not an improvement in kind over iteration 2's 0/5.

  **Entry-fill-price mechanism: FIXED, measured.** All 12 real entries now show entry-price
  deltas of $0.00-$0.08 vs live's actual fill (was up to $0.23/30% at 5-min resolution,
  core_safe's 13:01 trendline entry). This closes iteration 2's mechanism (a) cleanly.

  **Exit-mechanism gap: NOT fixed -- REVEALED A WORSE ARTIFACT.** `v15_profit_lock_mode="fixed"`
  (the real, live-configured value in `automation/state/params.json`) plus a stop-offset that
  defaults to 0.0 (never wired to a production value) locks the stop floor at EXACTLY breakeven
  the instant a position ticks +5% favorable, and never moves it again. Checked at 1-min cadence
  (390 checks/day vs 78 at 5-min) against genuinely volatile real 0DTE intra-minute prints
  (verified: `SPY260717P00744000`'s opening minute alone ranged $2.13-$3.64 on 237 real
  trades/1387 contracts -- confirmed via the raw cached bar, not a stale-quote guess), this now
  fires almost immediately: **all 5 of core_safe's entries exit via `EXIT_ALL_PREMIUM_STOP` at
  exactly $0.00 P&L in exactly 2 minutes each** (was 3/5 zeroed at 5-min). More discrete checks
  against real intra-minute noise raised the odds of catching a floor-touch, not lowered them --
  the uniformity (5/5 identical hold-time, exit reason, and $0 outcome regardless of whether the
  trade was a real winner or loser live) is itself the fable-too-good tell that this is an
  artifact, not a fidelity win. Not a bug in this harness or in `simulate_trade_real` (both
  correctly implement the real, configured "fixed" profit-lock convention) -- filed as an updated
  finding in `markdown/planning/FUTURE-IMPROVEMENTS.md` PARITY-GAP-2, along with a new, NOT-yet-
  validated hypothesis (`profit_lock_stop_offset_pct` is a real, currently-unset production knob
  -- candidate for lever L2, needs its own OOS scorecard before touching).

  **VERDICT: `harness_verdict.trustworthy_to_tune_against = False`, unchanged from iteration 2.**
  Per the task's own routing (step 6, conditional on faithfulness passing) no dollar-level lever
  is ratified this iteration. Per the SCOPE REFINEMENT below (pre-authorized before this run),
  the SIGNAL/DECISION layer -- iteration 2's actual, untouched-by-this-iteration fix -- remains
  100% capture / 12-of-12 tier match, so entry-side levers (L1/L3/L4/L6) ARE evaluable now,
  independent of the exit-layer dollar residual. **First-lever recommendation (per task step 6,
  not acted on this iteration): OOS-validate L1 (static-vs-trendline tier down-weight in bounce
  phase) next.** It is the single mechanism that cleanly explains BOTH of today's core_safe
  morning losers (11:06/11:40 ELITE static-level rejections fired mid-bounce) AND the day's best
  winner (13:01 TRENDLINE-tier entry with a LOWER raw bear_score, 7 vs 10/10, that outperformed
  anyway) -- the safe-tape audit already named this discriminator but only at n=3 (today only),
  well short of the OOS bar; L3/L4 are lower-priority (L3's blocked-cohort evidence is n=5, "far
  below n>=30" per the SCOPE REFINEMENT's own pre-flagged honest ceiling; L4 has no fleet-specific
  evidence yet, only a confirmed-zero-impact reading for core Bold; L6 was already found "not the
  binding constraint this morning" by its own audit). Expand L1's sample across recent days + the
  OP-16 anchor days before any ratification decision -- not done this iteration per the explicit
  "do not tune" instruction.
- **ITERATION 4 COMPLETE (2026-07-17 ~21:20 ET) -- L1 OOS-VALIDATED. VERDICT: NO-SHIP
  (`INSUFFICIENT_REGIME_SHIFT`, frozen ladder). Today's n=3 discriminator does NOT clear the OOS
  bar on the full history -- exactly the outcome the anti-overfit law exists to catch, reported
  honestly rather than forced.**

  **Lever, made precise + fully ex-ante (no invented bounce-phase classifier):** gate BEAR-side
  (PUT) `ELITE`-tier entries of `BEARISH_REJECTION_RIDE_THE_RIBBON`/`BULLISH_RECLAIM_RIDE_THE_RIBBON`.
  Traced the code (`backtest/lib/orchestrator.py:1186-1219`, `backtest/lib/filters.py:741,
  1390-1398`): `ELITE` = `has_confluence OR has_sequence`, and BOTH of those triggers are, by
  construction, impossible without a matched static price level (`detect_confluence` returns
  `None` whenever `rejection_level is None`; `sequence_rejected` is looked up FROM
  `rejection_level`). So "ELITE-tier bear entry" and "static-level-anchored bear entry with a
  confirming trigger" are the SAME set, not an approximation -- this sidesteps the day-type
  classifier's failure mode (`analysis/recommendations/daytype-gate-result.md`, 3/3 variants
  KILL 2026-07-15) entirely: no day-level or bounce-phase inference required, every field is
  known at signal time. Also the precise structural mirror of the already-LIVE `block_elite_bull`
  gate (blocks ELITE-tier CALLS unconditionally) -- this tests completing the missing bear-side
  half of that symmetric pair, not inventing a new gate class.

  **OOS study** (`backtest/tools/elite_bear_level_reject_gate_ab.py` ->
  `analysis/recommendations/elite-bear-level-reject-gate-ab-2026-07-17.{json,md}`): full-history
  real-fills replay, faithful current-production Safe config (chart-stop-primary -50%
  catastrophe caps, tp1_qty_fraction 0.8, profit_lock fixed arm+5%, ATM strike, all 6 currently-
  ratified entry gates), IS=2025 calendar year (n=119 control trades), OOS=2026 YTD through
  2026-07-08 (n=86 control trades, 6+ months). WF form `ab_delta_per_trade_v2026_07_16`
  (WF-GATE-METHODOLOGY-2026-07-16.md + AMENDMENT 1), both normalizations disclosed.

  | gate | value | pass? |
  |---|---|:--:|
  | 1. OOS positive | IS_delta=-$532.80 (n=6 removed, net WINNERS in 2025) / OOS_delta=+$683.14 (n=11 removed, net losers in 2026) | OOS: True |
  | 2. WF>=0.70 | gate-cohort-normalized **-0.699**; full-population-normalized **-1.774** (both forms reported per mandatory disclosure) | **FAIL** |
  | 3. sub_window_stable | IS_H1_2025 flat / IS_H2_2025 HURT (-$532.80, all of IS's removed-cohort pnl concentrated in 1 trade); OOS 0/3 hurt | **FAIL** (1 IS window hurt) |
  | 4. anchor_no_regression | OP-16 J_WINNERS days: base -$256 -> candidate -$24 (improves, 1 bad ELITE-bear trade axed on J's own 2026-05-04 win day); J_LOSERS days: unaffected (0 removed) | PASS |
  | 5. BH-FDR | p=0.0395 (single-candidate, degenerates to a plain one-sided test at alpha=0.10 -- disclosed) | nominally PASS, but see placebo below |
  | evidence_n advisory | n_oos_removed=11 (< 15 floor) | thin |

  **Ladder verdict: `INSUFFICIENT_REGIME_SHIFT`** (is_delta<=0 AND oos_delta>0 -- ELITE-tier
  bear entries were net WINNERS in 2025 and net LOSERS in 2026 YTD; per the frozen ladder this
  parks, never auto-ships, on a candidate that only helps in the newest regime).

  **fable-too-good hunt (built into the script, not bolted on after):**
  - **Concentration is the whole story.** Dropping just the top-3 OOS removed trades by
    |pnl| (2026-06-26 -$336, 2026-05-04 -$232, 2026-07-08 -$115) takes OOS_delta from +$683.14
    to **-$0.00** -- the other 8 removed trades net to exactly zero. The apparent OOS edge is
    3 trades, not a population effect.
  - **Random-removal placebo null: p_null=0.1429 (does NOT clear alpha=0.10).** 20 seeds of
    removing 11 random PUT trades (any tier) from the same OOS control population produced an
    OOS delta >= the real candidate's in ~14% of seeds -- i.e. picking ELITE tier specifically
    is not clearly better than blocking 11 random bear trades. This is the more relevant check
    than the BH-FDR line above (which only asks "is the removed cohort's own mean negative,"
    not "is ELITE the right lens") and it fails.
  - One genuine positive: one of the 3 concentrated trades sits on 2026-05-04, one of J's own 3
    anchor WINNER days -- axing a bad ELITE-bear entry on J's best day is directionally the
    right kind of mechanism, just not enough alone to clear the bar.

  **CONFIRMATION on today (secondary, not the fitting target)** -- verified directly against
  raw `automation/state/core-decisions.jsonl` (account=safe, 2026-07-17), not audit prose:
  11:06:03 `triggers=['level_rejection','confluence']` tier=ELITE -> lever SKIPS (avoids -$37).
  11:40:04 same tier=ELITE -> lever SKIPS (avoids -$102). 13:01:03
  `triggers=['trendline_rejection']` tier=TRENDLINE -> lever KEEPS, untouched (the +$241
  winner). Trade 6 (14:49, 743P) is also tier=TRENDLINE, untouched (still -$56). The 13:56-14:00
  cluster is tier=SUPER (ribbon_flip present), untouched -- lever only targets ELITE, not SUPER.
  **Today capture-delta if shipped: +$139 (avoids both morning losers, touches nothing else) --
  core_safe's replay P&L would move from +$240 to +$379.** This is real and mechanically clean,
  but per the task's own instruction this is the CONFIRMATION, not the ratification basis --
  the OOS study is what decides, and it says no.

  **SHIP DECISION: NO-SHIP.** `params.json` NOT touched. This is the honest outcome the task
  explicitly named as plausible ("a lever that only helps today is REJECTED... n=3 is almost
  certainly too thin alone") -- confirmed, not asserted: 11 OOS episodes is a real expansion
  beyond n=3, but the mechanism reverses sign across 2025->2026, fails both WF forms, fails
  1/2 IS sub-windows, and fails its own placebo-null sanity check. Shipping this would be
  fitting the artifact the concentration check just found, not the safe-tape audit's mechanism.

  **Re-test trigger recorded (WF-GATE-METHODOLOGY AMENDMENT 1, adjudication snapshot):**
  adjudicated 2026-07-17, OOS window 2026-01-02..2026-07-08 (188 calendar days), n_oos_removed=11.
  Re-test when EITHER the OOS window has grown >=50% in calendar length since this date (i.e.
  ~94 more days, on or after ~2026-10-19), OR >=30 NEW ELITE-tier-bear episodes have accrued in
  the cohort post-2026-07-08 (whichever first).

  **Filed:** `automation/overnight/queue.md` STUDY-STATIC-VS-TRENDLINE-REJECT-BOUNCE-PHASE moved
  to Completed with this result (superseded by the ex-ante ELITE-tier framing, no separate
  bounce-phase proxy needed or built). New spec-only queue item EXIT-MANAGER-REPLAY-HARNESS filed
  per the FRAME AUDIT's item 1 (forked exit-faithfulness project) -- spec only, not built.
- **ITERATION 5 (2026-07-17 ~21:40 ET) -- L1's `INSUFFICIENT_REGIME_SHIFT` park (+ the same
  signature on 4 OTHER studies: bold-strike ATM, fleet strike, zone-band, pong) resolved via a
  load-bearing methodology adjudication, run separately and reported in full at
  `analysis/recommendations/REGIME-REFERENCE-CLASS-ADJUDICATION-2026-07-17.md` /
  `regime-conditioned-validation-2026-07-17.{json,md}`. Summary for this ledger: built a
  regime-CONDITIONED validator (VIX band + trend character, the SAME primitives
  `context_bundle_producer.py`'s live daily read uses), self-validated it FIRST against
  known-bad (NLWB, confluence, double-top, a seeded noise placebo -- all 4 correctly killed) and
  known-good (`vwap_continuation` ITM-2/-8%, the one STRATEGY-SPACE-REGISTRY.jsonl row marked
  LIVE -- cleared all 5 gates, WF=1.359, BH-FDR p=0.005) cohorts. **Verdict: EARNS_RIGHTS**
  (Cramér's V=0.21 -- not a calendar-year tautology). Re-adjudicated all 5 parked candidates
  anyway: **0/5 flip to PASS.** L1 (elite-bear) specifically: still INSUFFICIENT_REGIME_SHIFT
  even within its own regime bucket (MID_downtrend, n=8, concentration-driven -- drop-top-3 still
  zeroes the regime-OOS delta, exactly like the original calendar study). **Answer for this
  goal's L1 lever: stays NO-SHIP, now on a second independent axis (calendar AND regime), not
  just one.** Disclosed limitation: the regime classifier's dominant bucket (`MID_uptrend`, 53%
  of all trading days) captured most candidates by the modal-bucket rule, making regime-
  conditioning closer to a chronological-not-calendar re-split for those cases than a true
  narrow-regime test -- reported honestly, not hidden.

## SCOPE REFINEMENT (Fable/Opus judgment, 2026-07-17 ~19:40 ET — after iteration 2)
Iteration 2 made the SIGNAL+DECISION layer faithful (5/5 sniper captures, 12/12 tier parity) but
the EXIT layer diverges because only 5-min option bars are cached vs live's 1-min clock. The
literal "green dollar figure per arm" is therefore NOT trustworthy at current resolution —
forcing it green would measure a data artifact (anti-overfit law forbids). So the success metric
splits:
- **PRIMARY (faithful now):** does the tuned engine CAPTURE the winners (13:01 trendline, 14:03
  bollinger, 13:51 bold) and SKIP/reduce the losers (11:06/11:40 ELITE static) across all 6 arms?
  Measured on the faithful decision layer — this is the real "does it see J's edge" question.
- **SECONDARY (data-gated):** directional P&L sign, exact dollars only trustworthy once 1-min
  OPRA bars for today's contracts close the exit-walk gap (iteration 3).
- **Lever routing:** entry-side levers (L1 static-vs-trendline, L3 tight-gate, L4 strike, L6 HTF)
  are evaluable NOW on the faithful decision layer. Exit lever (L2) waits for 1-min faithfulness.
- **Likely honest ceiling (flagged, not pre-concluded):** the tight arms (safe-3/risky-1) can only
  go green-on-today by loosening their gate = L3, which is a 1-for-5/+$148 cohort at n=5 — far
  below the n>=30 OOS bar. "4 arms green OOS-safe + 2 tight arms need more evidence" may be the
  honest terminal state; forcing the tight arms green today would be the exact curve-fit the law
  bans. Let the faithful eval + OOS actually run before concluding.

## FRAME AUDIT (Fable/Opus, 2026-07-17 ~20:30 ET — after iteration 3, OP-32 "same wall twice")
Iterations 2 AND 3 both hit the exit-simulation wall (iter 3's 1-min data made exit fidelity
WORSE, not better). Two hits on the same shape = audit the frame, don't grind a 4th time.
DIAGNOSIS: the exit divergence is NOT a data-resolution problem — it's that `simulate_trade_real`'s
profit-lock/stop model is KNOWN-divergent from the live `exit_manager` (documented lesson:
sim-vs-live profit-lock scope mismatch; sim breakeven-locks at +5% where live's exit_manager does
not). Live core_safe ran the 746P to +$241; the sim breakeven-zeros it in 2 min. This is a
sim-vs-live EXIT-PARITY gap, not a live bug (live did NOT prematurely stop) and not fetchable.
DECISION (reframe):
1. Exit-P&L faithfulness via simulate_trade_real is ABANDONED as a goal. The truly-faithful path
   is replaying through the live exit_manager itself — forked as its own named project
   EXIT-MANAGER-REPLAY-HARNESS (queue), NOT a blocker for the lever loop.
2. The DECISION layer IS faithful (5/5 capture, 12/12 tier). Proceed to decision-layer levers
   (L1/L3/L4/L6) NOW, measured by CAPTURE (takes winner / skips loser) + OOS A/B-delta (where the
   common-mode exit-sim error cancels — same reason delta-WF works). Exit-quality lever L2 waits
   for the exit_manager-replay project.
3. Goal success re-stated honestly: "the tuned engine, on today's faithful decision stream,
   captures the sniper entries and skips the losers across all arms, with every applied lever
   OOS-clean" — NOT an exact-dollar six-green (unachievable/untrustworthy on the current sim).
