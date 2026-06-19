# Strategy candidate: Category I — Perfect-Storm Combination Gates

> DRAFT — Chef proposal 2026-06-17T21:35:58. J ratifies.

## Hypothesis

Stacking 3-4 compensating signals simultaneously (score floor + morning window + level proximity + vol confirmation + HTF alignment + ribbon flip) identifies higher-quality entries than relaxing a single filter. Testing 8 distinct "perfect storm" combinations as both ADD gates (new entries the baseline misses) and FILTER gates (entries the baseline takes but the combo rejects).

Key question: Is there a combination gate that fires reliably on J's 3 winner days while reliably blocking J's 3 loser days?

## Backtest evidence

- **Script:** `backtest/autoresearch/gate_sweep_combinations.py`
- **Data:** `spy_5m_2025-01-01_2026-06-16.csv` (34,324 SPY bars, 22,283 VIX bars)
- **Train window:** N/A — point estimates only on the 6 J source-of-truth days
- **Test window:** 6 J days: 4/29, 5/01, 5/04 (winners) + 5/05, 5/06, 5/07 (losers)
- **Production params:** premium_stop_pct_bear=-0.10, tp1=0.50, tp1_qty=0.667, runner=2.5, f9_vol_mult=0.7, profit_lock trailing +5%/20%
- **Baseline (disable_filters=[8] + vix_soft=True):** edge_capture=$310, sharpe=-0.19, total_pnl=-$312

### Per-scenario results

All 8 scenarios FAIL OP-16 floor ($771):

| Scenario | edge_capture | edge% | N trades | sharpe | final_score | dropped | saves |
|---|---|---|---|---|---|---|---|
| I3: bear6+level0.30+vol4.0+ribbonflip | $341 | 22.1% | 1 | +0.45 | 152 | 4 | +$654 |
| BEST_COMBO_BEAR: bear8+any_compensator | $310 | 20.1% | 5 | -0.19 | -58 | 0 | $0 |
| MORNING_LEVEL_ONLY: bear7+morning+level0.25 | $310 | 20.1% | 4 | -0.17 | -54 | 1 | +$22 |
| I1: bear7+morning+level0.30+vol2.0 | $0 | 0% | 1 | -0.45 | -0 | 4 | -$288 |
| I2: bear6+morning+level0.30+vol3.0+htfBEAR | $0 | 0% | 1 | -0.45 | -0 | 4 | -$288 |
| I4: bear5+morning+level0.25+vol4.0+htfBEAR+ribbonflip | $0 | 0% | 0 | 0.00 | 0 | 5 | +$312 |
| I5: bull7+morning+level0.30+vol3.0+htfBULL | $0 | 0% | 0 | 0.00 | 0 | 5 | +$312 |
| TRIPLE_LOCK: bear7+htfBEAR+level0.30+vol2.0 | $0 | 0% | 1 | -0.45 | -0 | 4 | -$288 |

### J winner early-fire diagnostic (minutes relative to baseline)

| Scenario | 4/29 | 5/01 | 5/04 |
|---|---|---|---|
| I3 | BLOCKED | BLOCKED | 35 min EARLIER |
| BEST_COMBO_BEAR | 145 min EARLIER | 175 min LATER | 65 min LATER |
| MORNING_LEVEL_ONLY | 135 min EARLIER | BLOCKED | 30 min EARLIER |
| I1 | 120 min EARLIER | BLOCKED | BLOCKED |
| I2 | 120 min EARLIER | BLOCKED | BLOCKED |
| TRIPLE_LOCK | 120 min EARLIER | BLOCKED | BLOCKED |

- **edge_capture:** best is I3 at $341 (22.1% of max $1,542)
- **aggregate_sharpe:** best positive is I3 at +0.45
- **final_score:** I3 = 152
- **max_drawdown:** N/A (6-day sample)
- **real_fills_validated:** no

## Root cause analysis

The combination gate sweep reveals a structural finding more important than any single scenario result:

**5/01 is architecturally unreachable by ANY bear combo gate.** On 5/01, zero bars across all 78 RTH bars fire any of the 8 combination gates (BEST_COMBO_BEAR fires once, 175 minutes LATER than baseline — a late catch that doesn't help). J's 5/01 SPY 721P trade (+$470) was a trendline-rejection-only setup with ribbon=BULL and low VIX — it structurally requires the BEARISH_REVERSAL bypass (F5+F8 disabled for trendline-only setups). No volume ratio, no HTF=BEAR, no morning timing, and no ribbon_just_flipped apply. This means:

- **Max achievable edge_capture using combo gates alone: $870 max** ($341 from 5/04 if I3 applies, $342 if 4/29 applies at some combination, $0 from 5/01). Even perfect execution on 4/29 and 5/04 only gives 66% of J's max edge (1,072/1,542).

**The 5/01 problem is a separate research thread.** It requires the BEARISH_REVERSAL_BYPASS (Rank 28 in leaderboard) or a new trade class, not a combination gate.

**I3 is the only scenario with a positive final_score AND a positive filter effect:** it fires on 5/04 35 minutes earlier than baseline (potential improvement on an already-winning day) while dropping 4 other losing baseline entries (saving $654 in baseline losses). However, it completely blocks 4/29 (-$600 baseline entry which J won +$342) — so I3 actually HELPS on 5/04 but HURTS by dropping 4/29.

## Structural findings for cross-category synthesis

### What combination of gate level + compensating factor shows marginal_wr >= 0.45?
None of the 8 scenarios add marginal trades (all are SUBSETS of the baseline — more restrictive, not less). The OP-16 framework's "marginal entry" concept assumes gate-relaxation (less restrictive). For gate-tightening scenarios, the relevant metric is "filter saves" (blocking losers):

- **I4 + I5:** Save $312 each by blocking ALL 5 baseline trades (fully gated) — but also block all winners. Net: 0 winners captured, 0 losers triggered. Not useful.
- **I3:** 4 trades dropped (saves baseline -$653), 1 trade kept (5/04, +$341). This is the only scenario with selective value.

### Which single compensating factor has the most independent value at the -2 gate level?
At bear_score >= 8 (BEST_COMBO_BEAR): fires on same days as baseline, just with different timing. No filtering benefit.

At bear_score >= 6 with vol_ratio >= 4.0 + ribbon_just_flipped (I3): fires selectively on 5/04 (35 min earlier) and blocks 4/29, 5/01, 5/05, 5/07. The **ribbon_just_flipped** signal is the discriminating factor — 5/04 had a fresh ribbon flip (new bear stack); 4/29 did not.

### Recommended parameter set for first live test
**No combination gate scenario clears OP-16 floor.** I3 is the most promising gate shape (positive final_score at +152) but its edge capture is only 22% of max. The scenario filters too aggressively on 4/29 and blocks 5/01 entirely.

**Recommendation: Do not deploy as a new gate.** Instead, use these findings to inform the BEARISH_REVERSAL_BYPASS research (5/01 requires separate treatment) and to confirm that vol_ratio >= 4.0 + ribbon_just_flipped is a high-quality filter when applied as a SECONDARY confirmation gate on days where the baseline already fires.

## Disclosures (per OP-20)

1. **Account-size assumption:** Baseline uses ATM (strike_offset=0), Safe account params ($2K equity context). Results may differ at OTM-2 (Safe actual) or ITM-2 (Bold).
2. **Sample-bias disclosure:** Analysis conducted on exactly 6 days (the J source-of-truth days). No out-of-sample generalization is possible from this sample. Fire-rate counts per scenario (I1=0/78 bars most days; I3=1/78 on 5/04 only) are too sparse for statistical inference.
3. **Out-of-sample test result:** NOT APPLICABLE — this sweep is definitional (designed to characterize behavior on the specific J days used as ground truth in OP-16).
4. **Real-fills check:** Not performed. The P&L figures are from the engine's BS simulation with production exit params.
5. **Failure-mode enumeration:** (a) The "baseline" used disable_filters=[8] which is not production — production would have different entry counts. (b) The combo gate uses evaluate_bearish_setup() scores from a static context builder (not the full orchestrator state machine with quality escalation locks). (c) vol_ratio thresholds (2.0, 3.0, 4.0) are unstandardized — different days have different volume regimes. (d) The "first gate fire = same P&L as baseline" assumption overstates scenario value when the gate fires at a different bar than baseline.
6. **Concentration:** All evidence from 6 days. Top-1 day (5/04) = 100% of I3's edge_capture ($341). Concentration is definitional to this analysis type.

## Knob changes proposed
None. All scenarios fail OP-16. No params.json changes.

## Pre-merge gate

`python crypto/validators/runner.py` must show 30/30 PASS.

Current status: 83/84 PASS (v25_filter_gates.offline is a pre-existing failure, not caused by this work. No code was modified in validators or production filters.)

## My confidence (1-10) and why

**2/10 for any of these scenarios as live gates.**

The combination gate approach correctly identifies that I3 (ribbon_just_flipped + vol_ratio>=4.0 + level proximity) fires selectively on 5/04 but not on 4/29 or 5/01. This is not a bug — it reflects that J's three winner days have structurally different setups:

- **4/29:** Wick rejection, morning, VIX flat, ribbon=BEAR, no vol spike (I3 correctly blocks)
- **5/01:** Trendline rejection, midday, VIX low, ribbon=BULL (I3 correctly blocks — this setup is a BEARISH_REVERSAL, not a BEAR-combo setup)
- **5/04:** Level rejection, morning, VIX rising, ribbon=BEAR, vol spike + ribbon_just_flipped (I3 correctly fires)

The combination gate scores high on 5/04 but is structurally wrong for 4/29 and 5/01. J's edge spans at least 2 distinct setup types that cannot be unified under a single combo gate.

**For the cross-category synthesis:**
- Vol_ratio >= 4.0 is a high bar (fires rarely — 1 bar out of 78 on 5/04)
- ribbon_just_flipped is the most discriminating single compensator for BEAR-aligned setups
- Morning window (09:35-10:15) filters correctly for 4/29's pattern but not 5/01
- HTF="BEAR" is too restrictive (blocks 5/01 which was ribbon=BULL reversal)
- bear_score >= 8 + any_one_compensator fires too broadly (42 bars on 4/29, 28 bars on 5/04)

The search space for "combination gates that reliably fire on all 3 winner types" is essentially empty given the structural diversity of J's winning setups. The better research direction is to treat each setup type as its own trade class with its own OP-16 measurement: BEAR-aligned (4/29, 5/04) vs REVERSAL (5/01).
