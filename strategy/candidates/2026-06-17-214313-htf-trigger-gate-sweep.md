# Strategy candidate: HTF-alignment and multi-trigger gate-relaxation sweep

> DRAFT — Chef proposal 2026-06-17T21:43:13. J ratifies.

## Hypothesis

Allowing bear entries at score < 10/10 when the 15-min HTF stack confirms BEAR direction
(Categories D1–D5) or when 3+ independent triggers fire simultaneously (Categories H1–H5)
should add profitable marginal trades beyond the strict all-filters-pass baseline.

Primary claim: HTF alignment is a compensating signal strong enough to override 1–2 failed
non-structural filters. Multi-trigger confluence (3+ triggers) similarly compensates for
a missing single filter.

## Backtest evidence

- Data window: 2025-01-01–2026-06-16 (16 months), evaluated on J's 6 anchor days only
- Base config: vix_soft_mode=True, allow_one_blocker=True, min_spread=25c, ATM strike,
  tp1=0.30, runner=2.0 (period-correct for J's Apr/May 2026 trades)
- Script: `backtest/autoresearch/gate_sweep_htf_triggers.py`
- Output: `analysis/recommendations/gate_sweep_htf_triggers.json`

### Reference baselines

| Config | 4/29 | 5/01 | 5/04 | 5/05 | 5/06 | 5/07 | edge_capture | OP16 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Strict 10/10 | +63 | -23 | +120 | skip | skip | +45 | $160 (10%) | FAIL |
| vix_soft only | -270 | -23 | +341 | skip | skip | +45 | $48 (3%) | FAIL |
| vix_soft + OB=25c | -86 | -166 | +1,751 | skip | skip | +192 | $1,500 (97%) | PASS |

### Scenario results (all 10 scenarios)

**ALL 10 scenarios produced ZERO marginal trades vs baseline.**

Each scenario (D1–D5, H1–H5) returned identical per-day P&L as the main baseline:
- edge_capture: $1,500 (97.3% of max) — same as baseline
- marginal_trades: 0 on all 6 J-days

### Root cause diagnosis

Diagnostic run intercepting evaluate_bearish_setup revealed:

**`blocked_bars = 0` on all 6 J-days regardless of vix_soft_mode.**

With vix_soft_mode=True, the VIX gate becomes a score demerit (-1) rather than a hard block.
Every bar that reaches evaluate_bearish_setup either:
(a) Passes all filters (passed=True) — already captured by baseline
(b) Fails a STRUCTURAL filter (F1 time, F5 ribbon) — cannot be overridden by scenario gate
(c) Is never evaluated because the orchestrator pre-filters it (quality escalation lock)

The monkey-patch gate injection (override passed=True when gate_fn fires) never fires because
there are no blocked non-structural bars on J's 6 days.

- edge_capture: **$0 marginal gain across all 10 scenarios**
- aggregate_sharpe: N/A
- final_score: $0 × N/A = 0
- op16_pass: NO (edge_capture < 771)
- marginal_trades: 0 / day on all 6 days
- real_fills_validated: N/A (no new trades to validate)

## Key finding: why the gate injection approach doesn't add trades

The quality escalation lock (orchestrator lines 976–1068) is the real gate preventing
re-entries after the first trigger fires. On 4/29, the 11:50 SUPER entry (score=8, 3 triggers)
fires and quality-locks the rest of the day. Subsequent bars with htf_15m_stack=BEAR and
score=8–9 are blocked by SKIP_QUALITY_LOCK, not by evaluate_bearish_setup returning passed=False.

Gate injection at the evaluate_bearish_setup level is structurally unable to rescue these bars.
The quality escalation lock gate is upstream in the orchestrator loop, not addressable by a
filter-level patch.

**Structural constraint confirmed by Rank-32:** The gate sweep combinations already found
(2026-06-17) that no single combo gate clears 50% OP-16 floor, and 5/01 is unreachable by
ANY bear combo gate (countertrend BULL-ribbon setup — htf=BULL all day).

## What this sweep disproves

1. HTF alignment does NOT add net-new entries on J-days (already saturated by vix_soft + OB)
2. Multi-trigger quality (3+ triggers) does NOT rescue blocked entries on J-days (none exist)
3. Gate injection via evaluate_bearish_setup monkey-patch is the wrong lever for this problem

## What the data suggests instead

If the research goal is to recover J's 4/29 +$342 and 5/01 +$470 specifically:
- 4/29: engine fires at 11:50 instead of J's 10:25. Timing problem — quality escalation lock
  should be conditioned on TIME not just quality rank (earlier HTF-confirmed entry should win)
- 5/01: htf=BULL all day, ribbon=BEAR 13:00+. Structurally countertrend. Needs separate
  BEARISH_REVERSAL class (Rank-28 candidate) not a score-threshold gate

## Disclosures (per OP-20)

1. **Account-size assumption:** Evaluated with ATM strikes and period-correct tp1=0.30
   (params in effect during J's April/May 2026 trades, not current v15.3 production)
2. **Sample-bias disclosure:** 6 J-anchor days only — not a full IS/OOS window. These
   days are specifically selected because J confirmed them as signal examples. Not a
   representative sample of general market conditions.
3. **Out-of-sample test result:** N/A — no promotion to test
4. **Real-fills check:** N/A — no new trades added by any scenario
5. **Failure-mode enumeration:**
   - Primary: gate injection is at wrong level (evaluate_bearish_setup) when the
     real gate is quality escalation lock (orchestrator)
   - Secondary: vix_soft_mode saturates all J-days, leaving no blocked bars to rescue
   - Tertiary: 5/01 is structurally unreachable by any bear gate (htf=BULL, countertrend)
6. **Concentration:** Not applicable — zero marginal trades

## Knob changes proposed

**None.** This sweep is a diagnostic negative — confirms the current approach is saturated
on J's 6 anchor days. No params.json changes recommended.

## Next research directions

1. **Quality-lock time-gate:** Modify escalation lock to allow re-entry if (a) htf=BEAR
   AND (b) new trigger set is equal-or-higher quality AND (c) >= 90min since prior entry.
   This could rescue 4/29 afternoon entries currently blocked by SKIP_QUALITY_LOCK.

2. **BEARISH_REVERSAL class (Rank-28):** 5/01 needs a separate evaluation path for
   countertrend setups where ribbon=BEAR but htf=BULL. Already in design stage.

3. **HTF gate at quality-lock level:** Instead of filter-level injection, add HTF condition
   to the quality escalation lock to allow same-quality re-entry when htf just flipped to BEAR.

## Pre-merge gate

`python crypto/validators/runner.py` — not applicable (no production changes proposed).
No params changes; no new validator needed.

## My confidence (1-10) and why

**1/10** — All scenarios REJECT. This sweep confirms the gate injection approach is the wrong
lever. The finding is useful (now we know evaluate_bearish_setup is never the blocker with
vix_soft=True), but the hypothesis is disproved. Next candidates should target the quality
escalation lock or the countertrend REVERSAL class, not score-threshold gates.
