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
