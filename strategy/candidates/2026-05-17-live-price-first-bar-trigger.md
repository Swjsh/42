# Strategy candidate: LIVE_PRICE_FIRST_BAR_TRIGGER

> DRAFT — autonomous-session proposal 2026-05-17. J ratifies on weekend.
>
> **Work item:** Fix for the 1-bar lag at fast-V reversals documented in `journal/2026-05-15.md`
> (the −$770 BEARISH_REJECTION_RIDE_THE_RIBBON loss). Adds a NEW conditional trigger path —
> not a relaxation of v15.1, not a new setup name. The new trigger fires only inside the
> 09:35-09:45 ET window, only on named ★★+ PML/PMH/Carry levels, only on a live-bid cross
> with margin. Outside the window, v15.1 closed-bar rule continues to apply unmodified.

---

## Hypothesis

When a named ★★+ key level (PML / PMH / Carry tier ∈ {Active, Carry}) is broken (BEAR) or
reclaimed (BULL) on a live-bid tick during the 09:35-09:45 ET RTH-open window, and that
break/reclaim coincides with all v15.1 filters passing on the LAST CLOSED bar (ribbon stack,
spread, VIX, macro, volume), the engine should fire the entry IMMEDIATELY rather than waiting
for the 5m bar to close.

The hypothesis is that fast-V-reversal bars at the RTH open — bars that both break a level AND
reverse within the same candle — are concentrated in the first 10 minutes of RTH. The closed-bar
rule (v15.1 R1) waits for confirmation, by which time the V-reversal has already happened. A
live-bid trigger captures the level break BEFORE the reversal completes.

**The branch is structurally additive.** It cannot fire any setup that v15.1 would not also have
eventually fired (5 minutes later). The only difference is entry timing.

---

## Backtest evidence

> **Caveat upfront (per OP-20 disclosure #3):** Full historical SPY backtest of the
> v15.3 live-price branch has **NOT** yet been run. The evidence below is the smoke test
> (synthetic reproducer of the 5/15 09:40 event against the real 5m CSV) plus the journal
> forensic. Stage-2 SPY backtest is a J weekend deliverable.

| Claim | Evidence | Source |
|---|---|---|
| Real 09:40 bar OHLC matches journal narrative (broke PML 739.04 on close) | OHLC 739.16 / 740.10 / 738.62 / 738.66 → close $0.38 below PML | `backtest/data/spy_5m_2025-01-01_2026-05-15.csv` line 30994 |
| 09:45 bar wicked to 737.96 and closed ABOVE PML (V-reversal) | OHLC 738.66 / 739.67 / 737.96 / 739.65 → close $0.61 above PML | same CSV line 30995 |
| Closed-bar branch (v15.1) misses the leg down at 09:41 ET | smoke test Case 1: last_closed_bar = 09:35 (close 739.16 > PML), no level_reject fires | `backtest/autoresearch/v15_3_live_price_trigger_smoke.py` |
| Live-price branch (v15.3) catches the leg down at 09:41 ET | smoke test Case 1: live_bid 738.95 < PML - $0.052 with prior 09:35 close above PML | same |
| Closed-bar branch fires CORRECTLY at 09:46 ET (the real fill time, into the bounce) | smoke test Case 2: last_closed = 09:40 (high 740.10 > PML, close 738.66 < PML), level_reject fires | same |
| V-reversal bar (09:45) does NOT trigger fresh level_reject (close above level) | smoke test Case 3: at 09:50:30 ET, last_closed = 09:45, close 739.65 > PML | same |
| Named-level qualifier accepts PML 739.04 | tier=Active, stars=2, source matches `/premarket low/i` | smoke test Case 4 |
| Named-level qualifier rejects 1-star Reference psychological 740 | tier=Reference fails the tier filter | smoke test Case 5 |
| Window boundary [09:35, 09:45) is inclusive at 09:35:00 and exclusive at 09:45:00 | smoke test Case 6 | same |
| Stale quote (>60s) aborts the trigger | smoke test Case 7: 90s-old quote returns no fire | same |

### What the branch would have done on 2026-05-15

Per `journal/2026-05-15.md` and the real CSV:

- 09:35 ET bar closed at 739.16 (above PML 739.04, prior-bar gate satisfied).
- 09:40 ET in-flight: SPY travels 739.16 → 738.62 → 738.66. Live bid likely ~$738.95 around
  09:41-09:42 ET. v15.3 live-price branch fires.
- **Hypothetical v15.3 entry:** ~09:41-09:42 ET at spot ~738.95, premium ~$3.34-$3.55 (740P
  delta ~-0.4, ATM intrinsic + extrinsic).
- 09:45 ET bar wicks to 737.96 = ~$4.10-$4.30 premium HWM = +25% favor.
- Profit-lock chandelier arms at +5% favor (entry × 1.05 = $3.51), initial floor entry × 1.10 =
  $3.67. Trails 20% off HWM → trailing floor at $4.20 × 0.80 = $3.36, but stop floor is
  max($3.36, $3.67) = $3.67.
- V-reversal: 09:45 bar closes 739.65 → premium back near $3.30. Chandelier floor at $3.67
  → exit on first sub-$3.67 tick = breakeven-to-tiny-win exit.
- **Estimated v15.3 P&L on 5/15 trade:** ~ +$50 to +$300 vs v15.1 actual −$770.

### Edge-capture impact (J's source-of-truth days)

**Winners (engine MUST take — OP-16 floor):**

| Day | J trade | J P&L | Engine impact from v15.3 |
|---|---|---:|---|
| 2026-04-29 | SPY 710P × 6 | +$342 | TBD — need to check if any of J's wins fired on a live-bid first-bar cross. If J entered AT 09:46 on a confirmed close break, v15.3 would have fired ~5 min earlier; outcome same direction, marginally earlier entry. |
| 2026-05-01 | SPY 721P × 20 | +$470 | TBD — same logic |
| 2026-05-04 | SPY 721P × 10 | +$730 | TBD — same logic |

**Losers (engine MUST skip / lose less):**

| Day | J trade | J P&L | Engine impact from v15.3 |
|---|---|---:|---|
| 2026-05-05 | SPY 722P × 20 | -$260 | TBD — need to check if v15.3 would have fired earlier in the day where loss could have been worse |
| 2026-05-06 | SPY 730P × 10 | -$300 | TBD |
| 2026-05-07 | SPY 734C × 3 | -$45 | TBD |
| 2026-05-07 | SPY 737C × 10 | -$120 | TBD |

**Honest tension:** v15.3 cannot save the 5/15 trade entirely (chandelier exit ~breakeven is the
best case). But it converts a confirmed-bad $770 loss into a defensible scratch/small-win. That
is the actionable upside.

### Projected aggregate (rough)

- **edge_capture estimate:** PLACEHOLDER — needs Stage-2 SPY backtest. Per OP-22 verify-now-not-later,
  the smoke test verifies the trigger MECHANIC works correctly on 5/15. The PROJECTION across J's
  7-day source-of-truth set is pending.
- **edge_capture floor (771) status:** PLACEHOLDER — UNKNOWN until Stage-2 runs.
- **aggregate sharpe:** PLACEHOLDER — UNKNOWN until full backtest.
- **final_score:** PLACEHOLDER — UNAVAILABLE.

---

## Disclosures (per OP-20)

1. **Account-size assumption.** PLACEHOLDER. v15.3 does not change sizing. The dollar impact
   scales per tier as v15.1 does. On the 5/15 trade specifically: Gamma-Safe equity ~$102K =
   ITM-2 tier, qty=10 base. v15.3 entry ~$0.40 better premium on 10 contracts = ~$400 P&L
   improvement before chandelier dynamics. Stage-2 must measure this across the full sample.

2. **Sample-bias disclosure.** The single canonical bar (5/15 09:40) is the seed for this
   proposal, reverse-engineered from one journal forensic. Risk: the margin thresholds
   ($0.05 abs, 0.007% rel) and the window length (10 min) are tuned to ONE event. Stage-2
   must sweep these parameters across all RTH-open bars in the 16-month dataset and report
   fire-count + true/false positive rates. Recommended sweeps:
   - Window: `[09:35, 09:40)` (single-bar) vs `[09:35, 09:45)` (proposed) vs `[09:35, 09:50)`
   - Margin abs: `{$0.03, $0.05, $0.08, $0.10}`
   - Margin rel: `{0.005%, 0.007%, 0.01%, 0.02%}`

3. **Out-of-sample test result.** NOT YET RUN on SPY beyond the 5/15 day itself. The smoke
   test is a synthetic reproducer of one historical event, not a walk-forward measurement.
   Walk-forward + real-fills check are Stage-3 deliverables
   (`backtest/autoresearch/walk_forward_validate.py` + `simulator_real.py`). Required gate:
   v15.3 fires correctly on at least 3 historical fast-V days including 5/15, and fires zero
   false positives on J's winner-day datasets at the entry level.

4. **Real-fills check.** NOT YET RUN. The mechanic-level smoke test does not touch OPRA fills.
   Per OP-25 lesson 2026-05-13 05:20 ET, BS sim is RETIRED; `simulator_real.py` against OPRA
   bars is the only valid validation for the P&L estimate. The projected $50-$300 better
   outcome on the 5/15 trade is a SCENARIO estimate — not a measured OPRA outcome.

5. **Failure-mode enumeration.** See `automation/prompts/heartbeat-v15.3-draft.md`
   "Failure modes" section for the canonical list. Summary:
   - **Wick-only cross without follow-through.** Mitigated by $0.05-$0.052 margin + premium stop
     -20% + chandelier. Residual risk: bounded loss.
   - **Chop-through scenarios** at the level boundary. Mitigated by prior-closed-bar gate.
     Residual risk: rare for ★★+ levels at RTH open.
   - **Stale quote.** Mitigated by 60s freshness check.
   - **Macro hard-veto bypass.** Mitigated by gate sequence — every other filter still runs.
   - **Volume gate uses pre-impulse bar.** Mitigated by other filters (ribbon, VIX, macro).
     Residual risk: low-volume RTH-open trigger could fire on weak setup. Backtest measures.
   - **Wrong-direction trade on a sweep-style bar** (mirror of 5/14 09:58 foot-gun). v15.2's
     `bullish_sweep` blocker is the orthogonal fix. Recommend deploying v15.2 + v15.3 together.
   - **Multiple stacked levels.** Mitigated by tier+stars+source-regex filter. Residual: first
     level crossed wins, by design.

6. **Concentration.** PLACEHOLDER. Trigger fire rate on SPY not yet measured. Inside the
   09:35-09:45 ET window across 16 months ≈ 200 sessions × 2 bars = 400 sample bars. Estimated
   fire rate (★★+ level cross with margin): 5-15% of sessions, concentrated on gap days.
   Stage-2 must report:
   - fire rate (% of sessions)
   - true-positive rate (% of fires that resulted in directional follow-through > +5% favor)
   - top-5 day P&L concentration (% of aggregate from top 5 days)

---

## Knob changes proposed (DRAFT only — Chef does NOT edit params.json)

Proposed `params.json` field additions (under a new `v15_3_first_bar_live_price` sub-object).
Bumped `rule_version` if approved:

```json
"v15_3_first_bar_live_price": {
  "enabled": true,
  "window_start_et": "09:35:00",
  "window_end_et_exclusive": "09:45:00",
  "level_cross_abs_margin_dollars": 0.05,
  "level_cross_rel_margin_pct": 0.00007,
  "quote_freshness_seconds_max": 60,
  "qualified_level_tiers": ["Carry", "Active"],
  "qualified_level_min_stars": 2,
  "qualified_level_source_regex": "(?i)PMH|PML|premarket high|premarket low|Carry"
}
```

Open J questions per heartbeat-v15.3-draft.md:
- (Q1) Window length: `[09:35, 09:45)` vs `[09:35, 09:40)` (single-bar) vs `[09:35, 09:50)` (10 min into RTH).
- (Q2) Should v15.3 deploy independently of v15.2 (sweep blocker)? Recommend NO — deploy together
  because they are orthogonal fixes to mirror-image foot-guns (5/14 09:58 BULL + 5/15 09:40 BEAR).
- (Q3) Does the live-price branch apply to BOTH accounts (Safe + Bold)? Recommend YES — timing
  fix, not aggression/size knob.
- (Q4) Should the quote source be `mcp__tradingview__quote_get` or live OHLCV bar high/low?
  Recommend quote_get for cleaner bid/last semantics and tighter freshness.

**Production heartbeat.md edits live in `automation/prompts/heartbeat-v15.3-draft.md` Changes A-D.**
Per OP-4 (no code drift), both `heartbeat.md` AND `backtest/lib/filters.py` must update together.

---

## Pre-merge gate

`python crypto/validators/runner.py` must show OVERALL: PASS at moment of any production wiring
(OP-26 mandate — every heartbeat.md edit triggers the harness check). The v15.3 branch does NOT
add a new primitive to `crypto/lib/`; it is a heartbeat doctrine change. But the closed-bar
primitive in `crypto/lib/bar_reader.py` must stay green.

`python backtest/autoresearch/v15_3_live_price_trigger_smoke.py` must show OVERALL: PASS (7/7).
Current status (verified 2026-05-17 by author):

- Cases passed: 7 / 7
- Reads real OHLC from `backtest/data/spy_5m_2025-01-01_2026-05-15.csv`
- Verifies the 09:40 bar OHLC (739.16 / 740.10 / 738.62 / 738.66) and the 09:45 V-reversal
  bar (738.66 / 739.67 / 737.96 / 739.65)
- Verifies branch behavior at 4 wall-clock instants: 09:35:00 (window open), 09:41:30
  (in-flight), 09:45:00 (window close, exclusive), 09:46:38 (closed-bar fires, live-price
  out of window), 09:50:30 (V-reversal bar, no re-fire)

---

## My confidence (1-10) and why

**5/10.**

**Why this low (not 7+):**
- ZERO historical SPY backtest evidence beyond the synthetic reproducer of one event. v15.2's
  sweep blocker has crypto-harness 16-month replay; v15.3 has only the 5/15 forensic.
- The "fast-V at RTH open" pattern frequency is unknown. Could be 1 event in 16 months (this
  one), in which case the branch adds complexity for marginal benefit. Could be 5+ events per
  quarter, in which case it's a major edge improvement. The Stage-2 backtest will tell.
- Per OP-20, the candidate is missing real-fills check, out-of-sample window, concentration
  metric, account-size scaling measurement. All PLACEHOLDERs.
- The trigger fires on a LIVE in-progress bar — same class of mechanic that caused 5/14 09:58
  ENTER_BULL misfire (which closed-bar rule R1 was specifically introduced to prevent). The
  narrow scope (10-min window, ★★+ named levels only, level-cross detector not candlestick
  scorer) is the mitigation, but it's a new category of risk surface.

**Why this not lower (not 3 or 4):**
- The smoke test mechanic is correct: 7/7 cases pass against real CSV data. The trigger fires
  iff the proposal says it should fire and not otherwise.
- The hypothesis is well-defined and falsifiable: "fast-V level breaks at RTH open are systematic
  losers under closed-bar rule." Stage-2 backtest will either confirm or refute.
- The doctrine integration is clean: ADD ONE GATE (G2b) + RELAX ONE GATE (G2) only for triggers
  that pass G2b. No filter thresholds change, no setup names change, no sizing changes.
- The branch is additive to v15.2: v15.2 prevents bullish counterpart foot-gun (5/14 09:58),
  v15.3 prevents bearish counterpart foot-gun (5/15 09:40). They are orthogonal.

**Verdict: NEEDS-MORE-DATA — smoke test verified the mechanic; Stage-2 SPY backtest required
before ratification review.**

---

## Next steps (J's call)

1. **Stage-2 SPY backtest.** Wire the v15.3 branch into `backtest/lib/filters.py` per OP-4 and
   run: `python backtest/run.py --start 2025-01-01 --end 2026-05-15 --label v15.3_live_price --real-fills`.
2. **Identify fast-V days.** Per `journal/2026-05-15.md` next-priority #4: "isolate fast-V-reversal
   days (open-dump-and-reverse pattern) vs trend-continuation days in 60-day dataset." Output a
   tagged list.
3. **Per-day comparison.** For each fast-V day: did v15.1 enter into the bounce? Would v15.3
   have entered earlier? What's the P&L delta? Aggregate.
4. **Margin / window sensitivity sweep.** Per Disclosure #2.
5. **J-edge check.** Verify v15.3 does not regress any of the 7 source-of-truth days. Per OP-16
   edge_capture must stay ≥ 1542.
6. **If GREEN:** copy Changes A-D into production `heartbeat.md`, bump `rule_version` in
   `params.json` to `"v15.3"`, update `premarket.md` `RULE_VERSION_EXPECTED`, append L40 to
   `docs/LESSONS-LEARNED.md`.
7. **If RED on any J-edge day:** REJECT the candidate. The 5/15 trade was a $770 loss and we
   move on — we don't break edge-capture to fix one trade.

---

_Smoke test: `backtest/autoresearch/v15_3_live_price_trigger_smoke.py` (7/7 PASS as of 2026-05-17)._
_Heartbeat draft: `automation/prompts/heartbeat-v15.3-draft.md`._
_Underlying forensic: `journal/2026-05-15.md` Strategic Review §6 "Lesson of the day"._
