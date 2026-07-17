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
