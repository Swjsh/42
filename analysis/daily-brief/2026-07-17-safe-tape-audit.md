# CORE SAFE Tape Audit — 2026-07-17 (Friday)

_generated 2026-07-17 ~18:15 ET (after-hours work block), Sonnet, J-directed: "audit every arm,
its whole tape/thought process today. fine tune the winners, entries and exits."_

Scope: account `safe`/`safe-2` (PA3DHPT7KIQE) only. Every number below is cross-checked against
**three independent broker-truth sources**: `mcp__alpaca__get_account_activities` (live Alpaca
FILL activities), `automation/state/fills-ledger.jsonl` (arm=`safe-2` rows), and the
already-computed quant funnel table in `journal/2026-07-17.md`. All three agree. READ-ONLY audit —
no trading config touched.

---

## Verdict up front

- **The day was SIX round trips, not five.** A previously un-narrated trade — a `bollinger_squeeze`
  extra-setup PUT on SPY745, entered 14:03 ET while trade 4's runner was still resolving — banked
  **+$105**, the day's **second-best trade**. It is real, broker-confirmed, and it is missing from
  every piece of prose journaling (`journal/trades.csv` has zero rows for it; `journal/2026-07-17.md`'s
  `## Trades` narrative never mentions it). See Part 1, Trade 5.
- **Net day P&L verified: +$240.00** (six trades: -37, -102, +89, +241, +105, -56), matching the
  framing prompt's "+$239.28" to within 72 cents (residual almost certainly small per-contract
  regulatory fees not visible in raw fill data) and matching `journal/2026-07-17.md`'s own quant
  table (`[safe-2] 11 round trip(s): +240 (engine +151 / manual +89)`) exactly.
- **Morning losers (trades 1-2):** both were `tier ELITE` static-level rejections
  (`level_rejection`+`confluence`) fired *during* an unfinished recovery bounce and both got
  stopped within single-digit-to-teens minutes by SPY reclaiming a few cents/dimes above the
  trigger level. The winner (trade 4) was a `tier TRENDLINE` dynamic-line rejection with a
  **lower** bear_score (7 vs 10/10). Candidate discriminator identified — NOT proven at n=3 — spec'd
  as a pre-reg study in Part 2, no params touched.
- **Winner (trade 4) exit was correct-but-early on a trend day.** Chandelier trail did its job
  (real 15%-off-HWM breach, not a data glitch), but SPY kept falling for two more hours after the
  runner closed. Ties directly to the parked **TRAIL_ONLY_60** finding (`analysis/recommendations/hold-posture-ab.md`,
  filed 2026-07-14) — see Part 3.
- **Loser (trade 5, 743P) was a genuine two-way whipsaw**, not clean noise and not a clean "should
  have held." Evidence in Part 3.
- **J-called trade (trade 3) graded CLEAN** — good fill discipline, mechanical exits, no rule
  breaks. The "was 15% too tight" question has a data-backed answer: no.
- **One SPY-close correction:** the framing's "SPY closed ~741.2" is not what the broker tape
  shows. Verified RTH close (16:00 ET, SIP 5m bars) = **$743.23**, drifting to ~$742.40 by 16:15 ET
  after-hours — independently cross-checked against `analysis/daily-brief/2026-07-17-htf-levels-audit.md`'s
  own backtest-CSV pull for the same date, which shows the identical $743.23. Still well below
  trade 4's exit level (SPY 744.59), so the core finding (trend continued past the exit) is
  unchanged — just correcting the specific number.

---

## Part 1 — The tape, trade by trade

All times ET. All fills from `get_account_activities` (FILL, 2026-07-17), cross-checked against
`fills-ledger.jsonl` arm=`safe-2` and `core-decisions.jsonl` account=`safe`.

### Trade 1 — 744P, 11:06:32–11:11:04 ET — LOSS -$37.00

- **11:06:03 tick:** SPY 744.31, ribbon BEAR, htf_15m BEAR. `BEARISH_REJECTION_RIDE_THE_RIBBON`
  passed scoring, **tier ELITE**, triggers `['level_rejection','confluence']`, bear_score=10,
  bull_score=7. `trigger_level_exact=744.82` (premarket_high). Free-model veto layer: both lanes
  (qwen3:14b, nemotron-3-super-120b) voted GO, no veto.
- **Entry:** BUY 3x SPY260717P00744000, fills 2@1.41 + 1@1.42 = avg **1.4133**, cost $424.00.
  Stop mode: `structure` @ 744.82 (catastrophe cap -50% backstop, per v15.3 chart-stop-primary).
- **11:11:04 exit:** structure_stop fired — SPY 5m closed at **744.85**, 3 cents above the 744.82
  trigger. SELL_ALL 3 @ **1.29**, proceeds $387.00.
- **P&L: -$37.00** (-8.7% on premium). Hold time: 4m32s.

### Trade 2 — 745P, 11:40:28–11:56:03 ET — LOSS -$102.00

- **11:40:04 tick:** SPY 745.03, ribbon BEAR, htf_15m BEAR. Same setup, **tier ELITE**, triggers
  `['level_rejection','confluence']`, bear_score=10, bull_score=5. Nearest level above = 745.89
  (intraday_swing_high, dist 0.28). Both free-model lanes GO, no veto.
- **Entry:** BUY 3x SPY260717P00745000 @ **1.09**, cost $327.00. Stop: `structure` @ 745.89.
- **11:56:03 exit:** structure_stop — SPY 5m closed at **746.07**, 18 cents above the 745.89
  trigger. SELL_ALL 3 @ **0.75**, proceeds $225.00.
- **P&L: -$102.00** (-31.2% on premium). Hold time: 15m35s.

### Trade 3 — 746C, 12:04:29–12:12:20 ET — WIN +$89.00 (J-CALLED, manual)

- **Thesis (journal/2026-07-17.md, pre-trade):** J's hand-drawn descending trendline (drawn
  live on 07-16) broke UP at 10:05 ET (745.3→746.4), retested the topside ~745.9 at ~12:00 ET,
  bounced. Named pattern `TRENDLINE_BREAK_RETEST`. Engine at the touch: bear_score 6-8/bull 7,
  verdict HOLD — no live trigger class covers trendline retest (the shadow-logged
  `trendline_reclaim` mirror exists since 07-16 but isn't wired into core-decisions.jsonl yet).
  Fights both ribbon (BEAR) and HTF15 (BEAR) — J's structure read overrode the machine read,
  explicitly flagged as a caveat pre-trade.
- **Entry:** BUY 3x SPY260717C00746000, filled **1.13** (8 cents inside the ask per journal
  note), cost $339.00. Stop: structure close < 745.60. Cat-cap -50%.
- **12:10:17 TP1:** SELL_PARTIAL 2 @ **1.47** (+30% target), proceeds $294.00. Runner stop
  ratcheted to breakeven.
- **12:12:20 runner exit:** chandelier lock, HWM 1.49, trail 15% → stop 1.267ish, SELL_ALL 1 @
  **1.34**, proceeds $134.00.
- **P&L: +$89.00** (+26.3% on premium). Hold time: 7m51s. See Part 4 for execution grade.

### Trade 4 — 746P, 13:01:19–14:03:03 ET — WIN +$241.00 (the week's biggest winner)

- **13:01:03 tick:** SPY 746.32. Setup `BEARISH_REJECTION_RIDE_THE_RIBBON`, **tier TRENDLINE**,
  trigger `['trendline_rejection']` only (`trigger_level_exact=None` — dynamic line, not a fixed
  price). bear_score=7, bull_score=5 — both LOWER than trades 1-2. Both free-model lanes GO.
- **Entry:** BUY 3x SPY260717P00746000 @ **0.78**, cost $234.00. Stop: `structure`.
- **13:52:03 TP1:** SELL_PARTIAL 2 @ **1.56** (tp1 @ +100% — this setup's BASE-tier TP1 target is
  wider than the ELITE-tier default used on trades 1-2), proceeds $312.00. Runner stop → breakeven
  (0.80), then trail-armed, ratcheting up on every tick: 1.4365 → 1.462 → 1.496 → 1.6745 → **1.683**
  (best_premium print reached 1.98 at 13:59:03 ET, SPY 744.935).
  runner stop → breakeven → **BASE-QTY-VALUE PRESENT
- **14:03:03 runner exit:** chandelier trail — SELL_ALL 1 @ **1.63** (runner_stop level 1.683,
  slippage to the sell-side spread). Full reconstruction and counterfactuals in Part 3.
- **P&L: +$241.00** (+103.0% on premium). Hold time: 61m44s.

### Trade 5 — 745P (#2), 14:03:18–14:24:03 ET — WIN +$105.00 — **THE UN-NARRATED TRADE**

- This is a **separate, independent position** from trade 2 (also 745P, but a fresh contract
  bought 2h23m after trade 2 was flattened). It fired through the `extra_signals`/`extra_exec`
  side-channel, **not** the primary `ENTER_BEAR` verdict path — which is why it's invisible if you
  only scan `verdict != HOLD` rows. The governing tick (`14:03:03 ET`, verdict=`HOLD` at the
  top level) carries an `extra_signals` entry: `bollinger_squeeze` fired
  (`triggers: ['BB_SQUEEZE_RECENT','BAND_BREAK_DOWN','VOLUME_CONFIRM']`, direction short,
  confidence medium), and an `extra_exec` block shows it PLACED independently.
- **This is a sanctioned, validated setup family, not a bug.** `automation/state/params.json`:
  `extra_setup_exec_armed.bollinger_squeeze=true`, `bollinger_squeeze_enabled=true`,
  SAFE-only, with its own validated exit config (`j_bollinger_squeeze_premium_stop_pct=-0.08`,
  `tp1_pct=0.3`, `profit_lock_trail_pct=0.15`) — a "family-grind survivor" per its own params.json
  doc, intentionally exempted from the main ribbon-ride's chart-stop-primary -50% catastrophe cap
  doctrine because it's a distinct, separately-tuned family. No doctrine violation.
- **Entry:** BUY 3x SPY260717P00745000 @ **1.00** (limit 1.01), cost $300.00, submitted 15 seconds
  after trade 4's runner-exit order (18:03:03.815Z vs 18:03:18.909Z) — a brief, harmless overlap
  window, both sized independently within risk caps.
- **14:05:04 TP1:** SELL_PARTIAL 2 @ **1.28** (+30%), proceeds $256.00.
- **14:24:03 runner exit:** chandelier trail, SELL_ALL 1 @ **1.49**, proceeds $149.00.
- **P&L: +$105.00** (+35.0% on premium). Hold time: 20m45s.
- **Journaling gap (Rule 8):** `journal/trades.csv` has zero rows for this fill (account_id=`safe`
  only carries the manual 746C trade). This is not unique to today — `journal/trades.csv` also has
  no `account_id=='safe'` rows at all for 2026-07-16, suggesting the automated-engine → trades.csv
  journaling pipeline for core Safe has been silently dark for at least 2 sessions, compensated
  only by the auto-generated end-of-day quant funnel table (which IS complete and correct — the
  P&L total is right, it's the per-trade prose thesis/journal record that's missing). This is a
  Rule-8 gap, flagged for a separate fix (queued below), not something this audit patches.

### Trade 6 — 743P, 14:49:42–14:56:03 ET — LOSS -$56.00

- **14:49:03 tick:** SPY 743.26. **Tier TRENDLINE**, trigger `['trendline_rejection']`,
  bear_score=9, bull_score=5.
- **Entry:** BUY 3x SPY260717P00743000 @ **0.53**, cost $159.00. Stop: `structure` @ 744.22.
- **14:56:03 exit:** structure_stop — SPY 5m closed at **744.37** (well above 744.22, a clean
  reclaim, not a hair-trigger). SELL_ALL, filled in two pieces (2@0.34 + 1@0.35, same order,
  normal partial-fill mechanics), proceeds $103.00.
- **P&L: -$56.00** (-35.2% on premium). Hold time: 6m21s. Noise-or-real check in Part 3.

### Reconciliation

| Trade | Contract | Entry | Exit(s) | P&L |
|---|---|---|---|--:|
| 1 | 744P | 1.4133 | 1.29 | -$37.00 |
| 2 | 745P #1 | 1.09 | 0.75 | -$102.00 |
| 3 (manual) | 746C | 1.13 | 1.47/1.34 | +$89.00 |
| 4 | 746P | 0.78 | 1.56/1.63 | +$241.00 |
| 5 (bollinger, unlogged) | 745P #2 | 1.00 | 1.28/1.49 | +$105.00 |
| 6 | 743P | 0.53 | 0.34/0.35 | -$56.00 |
| **TOTAL** | | | | **+$240.00** |

---

## Part 2 — Morning losers (trades 1-2) vs winner (trade 4): discriminator search

Full `context_bundle` pulled for all three entry ticks, field by field:

| Field | Trade 1 (11:06, LOSS) | Trade 2 (11:40, LOSS) | Trade 4 (13:01, WIN) |
|---|---|---|---|
| SPY @ entry | 744.31 | 745.03 | 746.32 |
| tier | ELITE | ELITE | **TRENDLINE** |
| triggers | level_rejection + confluence | level_rejection + confluence | **trendline_rejection only** |
| trigger_level_exact | 744.82 (static) | 745.89 (static) | **None (dynamic line)** |
| bear_score / bull_score | 10 / 7 | 10 / 5 | **7 / 5** |
| position_in_prior_range | -0.535 | -0.340 | -0.234 |
| rvol_session_so_far | 1.583 | 1.490 | 1.401 |
| minutes since session low (09:35 ET, 740.80) | ~91 | ~125 | ~206 |
| level above / dist | 744.82 premarket_high / 0.51 | 745.89 intraday_swing_high / 0.28 | 747.25 intraday_rth_high / 0.93 |
| level below / dist | 744.22 premarket_low / 0.09 | 744.82 premarket_high / 0.79 | 745.98 level_memory / 0.34 |
| free-model veto | none (2/2 GO) | none (2/2 GO) | none (2/2 GO) |
| stop breach margin | +0.03 over trigger | +0.18 over trigger | (ran to TP1, N/A) |

**What's checked, not assumed:**

- **Bounce-leg maturity / position-in-range** moves monotonically toward the winner
  (-0.535 → -0.340 → -0.234; 91min → 125min → 206min since the 09:35 low) but this is a smooth,
  continuous trend across only 3 points — not a clean threshold, and not statistically anything at
  n=3. Flagged as a candidate, not a proof.
- **Score is backwards for the outcome**: both losers had the max bear_score (10); the winner had
  a *lower* bear_score (7). Score is not the discriminator here — if anything this is evidence the
  scoring formula isn't the thing separating winners from losers within this setup family.
- **The one clean categorical split in this sample**: both losers are `tier ELITE` (static
  price-level rejection); the winner is `tier TRENDLINE` (dynamic trendline rejection). Both
  losers were also stopped by SPY closing only a few cents to two dimes *above* their static
  trigger level, within single-digit-to-teens minutes of entry — consistent with catching noise
  right at a level rather than a durable rejection, while the underlying bounce (740.80 low at
  09:35 → 747.29 high at 10:15, a 40-minute, 6.5-point move) hadn't actually exhausted yet. This
  matches the known anti-pattern class **C22** (backward-looking classifiers anti-correlate with
  recovery periods) and **C20** (proximity/static-level gates anti-correlate with breakout/impulse
  structure) already in `LESSONS-LEARNED.md`.
- **Honest limitation**: n=3 same-day trades is not evidence of a validated edge. `tier ELITE`
  static-level rejections have presumably won on other days; today is one adverse sample, not a
  pattern.

**Pre-registered study spec (queued, NOT shipped, no params touched):**

> **STUDY-STATIC-VS-TRENDLINE-REJECT-BOUNCE-PHASE**: for
> `BEARISH_REJECTION_RIDE_THE_RIBBON`/`BULLISH_RECLAIM_RIDE_THE_RIBBON` historical signals
> (real-fills + real-OPRA replay, full history), split by trigger composition
> (`level_rejection`/`confluence` static-tier vs `trendline_rejection` dynamic-tier) AND by a
> bounce-maturity proxy (`position_in_prior_range` at signal time, and/or bars-since-session-extreme).
> Test whether static-level rejections underperform specifically when fired against an
> unexhausted intraday impulse (i.e., price is still trending toward/through the level rather than
> having already stalled there). Canonical battery (expectancy + OOS + regime per doctrine), BH-FDR,
> walk-forward. If it clears the standard bar (OOS_positive AND WF>=0.70 AND sub_window_stable AND
> anchor_no_regression), ships as a pre-entry gate refinement; if not, archived with the negative
> result documented. Filed to `automation/overnight/queue.md`.

---

## Part 3 — Exit fine-tuning: trade 4 (winner) and trade 6 (743P stop)

### Trade 4 (746P) — full exit reconstruction + 3 counterfactuals

Actual OPRA 5m bars for `SPY260717P00746000` pulled directly (not backtest-replayed) for the full
session.

**(a) Current SS-B shape (what actually happened):** entry 0.78 (13:01) → HWM tracked to ~1.98
(13:59, SPY 744.935) → chandelier 15%-trail breach on the 14:00-14:05 ET bar (option printed an
intrabar low of **1.47** inside that bar, versus a close of 1.81) → exit fill **1.63** at 14:03:03.
The 15%-off-HWM math checks out (1.98 × 0.85 = 1.683, matching the logged `runner_stop`) — **this
was a real, mechanically correct trail breach, not a data glitch or a misfire.** The premium genuinely
dipped through the trail level intrabar.

**(b) Chandelier-only counterfactual (no TP1 skim, full 3 contracts ride the trail from entry):**
after the actual exit, the option kept climbing to new highs — 2.19 (18:05Z bar), 2.65 (18:15Z),
**2.88 (18:25Z, a new HWM)**, before finally printing a genuine >15% pullback (low 1.99 in the
18:30Z/14:30 ET bar, a 30.9% drawdown off the 2.88 HWM). A pure chandelier-only ride (never taking
TP1, letting all 3 contracts trail) would have exited **~35-40 minutes later, around $2.40-2.45**,
not $1.63 — roughly **+$0.80/contract** better on that leg, or **+$240** across all 3 contracts
instead of the blended actual (+$241 total across the TP1+runner split as executed — i.e. a
chandelier-only ride on this specific day would have captured close to double).

**(c) Hold-to-time-stop (15:50 ET) counterfactual:** the option printed **$3.69** at the 16:00 ET
close bar (RTH close), and was still $3.5-3.7 in the first several minutes of after-hours. At the
actual 15:50 ET time-stop boundary (19:50Z bar), it was ~$2.16-2.46. Either way, dramatically above
the $1.63 actual exit.

**Verdict:** the mechanical exit was not wrong on its own terms — it correctly executed a real
15%-trail breach. The *shape* (TP1 skim + tight 15% runner trail) is what left money on the table
on a day the market kept trending in the position's favor for two more hours. **This is exactly
the situation `TRAIL_ONLY_60` (`analysis/recommendations/hold-posture-ab.md`, filed 2026-07-14) was
built to test**: trail-only, TP1-deferred posture, which on J's 3 OP-16 anchor multi-hour-ride days
flipped control's -$674 to +$141.80 — a real, directionally-consistent lift on exactly this
trend-day shape, even though it failed the aggregate significance bar (p_null=0.917, KILL per the
frozen pre-reg) and is parked at `TRAIL60-REOPEN-WATCH` in `queue.md` pending 50 new real fills
under SS-B. Today's trade 4 is one more real-world data point in that same direction — noted, not
enough alone to reopen the frozen study early.

### Trade 6 (743P) — was the stop noise or real?

Actual OPRA bars for `SPY260717P00743000` and SPY spot around the 14:45-16:00 ET window:

- Entry 0.53 (14:49:42 ET). SPY immediately bounced (743.9 → 744.6 by 14:50 ET).
- **14:56:03 stop:** SPY 5m bar closed **744.37**, comfortably (15c) above the 744.22 structure
  trigger — a real, non-borderline reclaim, unlike trade 1's 3-cent breach. Exit 0.34/0.35.
- **15:00-15:10 ET (the next 10-15 minutes):** SPY reversed hard back down (744.37 → 742.76), and
  the option spiked to **$0.94-1.08** — nearly double the entry premium. Had the position still
  been open, this window alone would have been a big win.
- **15:20-15:50 ET:** SPY whipsawed again (742.36 → 743.16 → 742.83 → 743.48 → 744.04 → 743.97),
  and the option crashed back to **$0.19** by the 15:50 ET time-stop boundary — *worse* than the
  actual -$56 stop-out.
- **16:00 ET close:** option back up to $0.64 (bar high $0.83) — modestly *above* the $0.53 entry,
  i.e. held-to-the-bell would have been a small win.
- **Verdict: genuinely mixed, not clean noise and not a clean missed hold.** The stop trigger itself
  was real (a clean, non-marginal 5m reclaim, not a hair's-width breach like trade 1). But the
  subsequent 70 minutes were two-way chop with a $0.19-$1.08 range on a $0.53 entry — holding
  through would have been a coin-flip on timing, not a reliable win. The mechanical stop did its
  job of capping a defined, small loss (-$56, 35% of premium risked, well inside the -50%
  catastrophe cap) rather than riding that volatility. Unlike trade 4, there is no clean asymmetric
  case for "should have held" here — this one is a legitimate example of a stop that got run by
  ordinary chop, not a mistake.

---

## Part 4 — Grading trade 3 (J-called, 746C)

- **Entry: clean.** Filled 1.13, 8 cents inside the ask on a marketable limit — good execution on
  a manual call.
- **Exits: fully mechanical, rule-compliant.** TP1 at +30% (6 minutes), chandelier lock 2 minutes
  later at HWM-15% (1.34 off a 1.49 HWM) — no hesitation, no discretionary override on the way out.
- **"Was the 15% trail too tight for a fresh breakout?"** — checked against the actual OPRA tape
  for the 40 minutes after the runner closed (12:12-12:55 ET): the option **dropped to $0.96 within
  8 minutes** of the exit (12:20 ET bar) — a 35.6% drawdown off the 1.49 HWM. Any trail up to and
  including ~35% would have been stopped at essentially the same spot. The later peak the trade
  prompt is implicitly asking about ($1.96 at 12:50 ET) only became reachable by surviving that
  intervening 0.96 print — which would have required accepting a ~40%+ giveback on a single 0DTE
  runner contract, a materially different (and much riskier) risk posture than a 15% trail, not a
  simple "loosen it a bit" tweak.
- **Verdict: 15% was not demonstrably too tight.** The proximate opportunity cost (missing the
  1.68-1.96 print 30-40 minutes later) required surviving a real intervening 35%+ drawdown first —
  that's a different, much wider risk/reward trade than what a 0DTE single-runner chandelier is
  designed to take. No execution error, no rule break. This is the same underlying tension as
  Part 3's TRAIL_ONLY_60 discussion (tight trail = give back less on reversals, cap upside on
  continuations) — a design trade-off, not a mistake on this specific trade.

---

## Findings summary (for queue/STATUS)

1. **[JOURNALING GAP, actionable]** Automated core-Safe engine trades are not reaching
   `journal/trades.csv` (only manual/J-called trades get rows for `account_id=='safe'`) — confirmed
   dark for both 2026-07-17 and 2026-07-16. The end-of-day quant funnel table is complete and
   accurate (P&L totals verified correct), but the per-trade prose/thesis record (Rule 8) is not
   being written for engine trades. Queued.
2. **[STUDY, pre-reg only]** `STUDY-STATIC-VS-TRENDLINE-REJECT-BOUNCE-PHASE` — candidate
   discriminator between tier-ELITE static-level rejections and tier-TRENDLINE dynamic rejections
   during unexhausted bounces. n=3 today, needs full-history validation. Queued.
3. **[CORROBORATION, no action]** Today's trade 4 chandelier-exit-early-on-a-trend-day pattern is
   one more real data point supporting the already-parked `TRAIL60-REOPEN-WATCH` item — not enough
   alone to reopen it (still waiting on the pre-registered 50-new-real-fills trigger).
4. **[DATA CORRECTION]** SPY's verified RTH close on 2026-07-17 was $743.23 (drifting to ~$742.40
   in the first 15 min after-hours), not "~741.2" — corrected for the record, does not change any
   directional conclusion above.

Full per-trade fills, context bundles, and OPRA bar pulls used for this audit are reproducible from
`automation/state/core-decisions.jsonl` (account=`safe`, 2026-07-17), `automation/state/fills-ledger.jsonl`,
and live Alpaca `get_account_activities`/`get_option_bars` calls (queried live during this audit,
not from a cache).
