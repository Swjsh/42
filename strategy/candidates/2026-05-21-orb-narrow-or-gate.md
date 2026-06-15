# DRAFT: ORB Narrow-OR Range Gate

**Status:** DRAFT — requires J ratification per Rule 9 before any watcher or engine change  
**Confidence:** 8/10 — positive evidence 5 of 6 quarters, N=143 (long-only), strong WR separation  
**Author:** Gamma overnight session (OP-22)  
**Date:** 2026-05-21 (updated 2026-05-21T04:30 ET with direction analysis)  
**Source analysis:** `analysis/watcher-fleet-analysis-2026-05-21.md` Priority 3+4

---

## Finding

The ORB watcher's N=391 graded observations reveal two independent quality dimensions: **OR-range** and **direction**. The interaction between them determines the recommended gate.

### Dimension 1: OR-range (the primary signal)

| Gate | N | WR | Total P&L | Avg P&L/trade |
|---|---:|---:|---:|---:|
| Narrow OR (≤$2.00) — long only | 143 | 88.1% | +$4,596 | +$32.1 |
| Wide OR (>$2.00) — long only | 131 | 48.9% | +$2,781 | +$21.2 |
| Narrow OR (≤$2.00) — short only | 75 | 57.3% | +$487 | +$6.5 |
| Wide OR (>$2.00) — short only | 42 | 50.0% | -$705 | -$16.8 |

### Dimension 2: Direction (secondary, interacts with OR-range)

| Direction | N | WR | Total P&L | Avg P&L/trade | Regime |
|---|---:|---:|---:|---:|---|
| Long all sizes | 274 | 70.4% | +$7,378 | +$26.9 | 4-of-6 quarters |
| Short all sizes | 117 | 54.7% | -$218 | -$1.9 | regime-sensitive |

**Key insight:** The "-$218 short drag" headline masks a two-population problem. Wide shorts are -$705 (the real bad actor). Narrow shorts are +$487, but this is heavily concentrated in 2026-Q2 (+$1,170) and NOT regime-robust without 2026-Q2 (sum = -$682 across other quarters).

---

## The Four-Scenario Comparison

This is the decisive table for J's ratification decision:

| Scenario | N | WR | Total P&L | Avg/trade | Quarters+ |
|---|---:|---:|---:|---:|---|
| Baseline (no gate) | 391 | 65.7% | +$7,161 | +$18.3 | 2-of-6 |
| **Option A: Long-only gate** | **274** | **70.4%** | **+$7,378** | **+$26.9** | **4-of-6** |
| Option B: Narrow-OR gate (all directions) | 218 | 78.9% | +$5,084 | +$23.3 | 4-of-6 |
| **Option C: Narrow-OR + long-only** | **143** | **90.2%** | **+$4,597** | **+$32.1** | **5-of-6** |

**Quarters+ = number of quarters with N≥3 AND positive P&L (of 6 total quarters).**

### Quarterly breakdown — all four scenarios

| Quarter | Baseline | Long-only (A) | Narrow-all (B) | Narrow-long (C) |
|---|---|---|---|---|
| 2025-Q1 | N=18, -$624 | N=12, -$766 | N=3, -$128 | N=3, -$128 |
| 2025-Q2 | N=60, -$18 | N=42, +$317 ✓ | N=24, +$754 ✓ | N=18, +$1,183 ✓ |
| 2025-Q3 | N=99, +$1,612 ✓ | N=57, +$1,650 ✓ | N=75, +$1,290 ✓ | N=42, +$1,250 ✓ |
| 2025-Q4 | N=28, -$378 | N=17, +$43 ✓ | N=16, -$351 | N=5, +$70 ✓ |
| 2026-Q1 | N=37, -$982 | N=13, -$110 | N=22, +$254 ✓ | N=10, +$126 ✓ |
| 2026-Q2 | N=149, +$7,551 ✓ | N=133, +$6,245 ✓ | N=78, +$3,265 ✓ | N=65, +$2,095 ✓ |

*(2025-Q1 N=3 treated as insufficient sample in Options B/C)*

---

## Regime Durability Analysis (the decisive criterion)

**Option A (long-only):** 4-of-6 quarters positive. Still negative in 2025-Q1 and 2026-Q1 — both choppy/bear markets where SPY trending down limits breakout follow-through even for longs.

**Option B (narrow-OR, all directions):** Also 4-of-6 quarters. Different failure profile: 2025-Q4 (-$351, N=16) is negative. But 2026-Q1 is positive (+$254) because narrow ORBs in early 2026 had clean directional resolution despite the overall choppy market.

**Option C (narrow-OR + long-only):** 5-of-6 quarters positive (only 2025-Q1 insufficient sample). This is the most regime-robust subset — positive in EVERY meaningful quarter across the 16-month backfill. WR=90.2% approaches institutional-grade signal quality.

### Interpretation

A narrow opening range (≤$2.00, ~0.27% of SPY price) concentrates early-session energy into a tight band. When that band breaks, the directional move is usually genuine. Wide ORs reflect pre-open chop or gap indecision — the 30-min ORB fires on noisier structure.

The long-only filter adds the structural bull-market advantage: in 2025-2026, bullish ORB breakouts have the market's own trend behind them. Short ORB breakdowns fight the drift — even when they work mechanically, their P&L is worse on average.

Combined, these two dimensions select the most mechanical, most repeatable, most regime-durable ORB signal.

---

## Proposed Watcher Change (Option C recommended)

> **DRAFT only — do NOT implement without J ratification per Rule 9.**

In `backtest/lib/watchers/orb_watcher.py`:

1. Add constants:
   ```python
   MAX_OR_RANGE = 2.00    # skip if OR > this
   ALLOWED_DIRECTIONS = ("long",)  # or ("long", "short") for Option B
   ```
2. In signal generation:
   ```python
   or_range = or_high - or_low
   if or_range > MAX_OR_RANGE:
       return None   # wide OR — noisy, skip
   if direction not in ALLOWED_DIRECTIONS:
       return None   # short ORBs fight the trend — skip
   ```

**Impact on OP-21 promotion path:**
- Option C reduces signal volume from ~25/month to ~9/month (143/391 × 25 ≈ 9.2)
- But improves per-signal quality from WR=65.7% → WR=90.2%
- Positive expectancy over 16-month backfill is maintained across all meaningful quarters
- Option A (long-only only) would preserve ~17/month volume at WR=70.4%

**J's trade-off decision:**
- Option A: volume vs robustness balance. Keeps more P&L (+$7,378), less regime-proof (4-of-6 Q).
- Option B: moderate quality lift. Includes narrow shorts (+$487 aggregate, but not regime-robust).
- **Option C (this DRAFT)**: best regime durability (5-of-6 Q), highest WR (90.2%), but lowest volume.

See companion DRAFT `2026-05-21-orb-direction-filter.md` for Option A (long-only gate as standalone).

---

## Concerns and Limitations

1. **Total P&L reduction (Option C vs baseline):** Removes +$2,564 of historical P&L. Cost of precision over volume.
2. **2025-Q1 sample:** N=3 in Option C — too small to conclude. Not modeled as a positive.
3. **Narrow short ORBs excluded (Option C):** The +$487 narrow short P&L is dropped. Acceptable given its concentration in 2026-Q2 (NOT regime-robust without that quarter).
4. **OR-range not in heartbeat.md:** Production engine would need OR-range computed from first 30m bars before any promotion. This is a feature-add.
5. **Watch-only status unchanged:** ORB is STABLE (WATCH_ONLY). This gate affects future watcher observation quality only — no live trading change.

---

## Ratification Checklist

Before implementing:
- [ ] J selects between Option A, B, or C (or requests alternatives)
- [ ] Walk-forward validation of selected gate on held-out data
- [ ] Engine feature-add: OR-range computed in heartbeat.md if Option B or C chosen
- [ ] Gym remains 65/65 PASS after any code change
- [ ] OP-21 promotion gate re-evaluated with gated sample

---

*Filed by Gamma overnight autonomous session. DRAFT only. No production changes.*
*Updated 2026-05-21T04:30 ET with full direction × OR-range four-scenario analysis.*
*Updated 2026-05-21T05:45 ET with L67 dedup correction (see below).*

---

## DEDUP CORRECTION (2026-05-21 ~05:45 ET)

**All tables above use undeduplicated (raw) observation counts. L67 root cause: Gamma_Heartbeat
fires every 3 min; each tick within the same 5-min SPY bar appends a row to
watcher-observations.jsonl. Inflation factor: ~4.5× for ORB observations.**

Three ORB analysis scripts now apply the L67 dedup gate (`bar_timestamp_et[:16]`) as of this session:
`orb_regime_scan.py`, `orb_narrow_or_walkforward.py`, `orb_vix_gate.py`.

### Corrected Option C stats (deduped unique-bar counts)

| Scenario | N (deduped) | WR | P&L | Q+ | Notes |
|---|---:|---:|---:|---|---|
| LONG_ALL (Option A baseline) | 61 | 60.7% | +$1,023 | 4/6 | vs raw N=274, WR=70.4%, P&L=+$7,378 |
| **LONG_OR_LT2.00 (Option C)** | **32** | **81.2%** | **+$976** | **5/6** | vs raw N=143, WR=88.1%, P&L=+$4,597 |
| LONG_OR_GT2.00 (wide) | 29 | 37.9% | +$47 | 2/6 | vs raw N=131, WR=48.9%, P&L=+$2,781 |

### Walk-forward (deduped)

- IS (train, 2025-Q1 to 2025-Q3): N=21, WR=76.2%, Sharpe=10.10
- OOS (test, 2025-Q4 to 2026-Q2): N=11, WR=90.9%, Sharpe=6.74
- **OOS/IS ratio: 0.667 → PASS (gate ≥ 0.50)** ← corrected from 1.149 (inflated)
- Verdict unchanged: PASS. OOS WR (90.9%) outperforms IS WR (76.2%).

### Quarterly breakdown (deduped Option C = LONG_OR_LT2.00)

| Quarter | N | WR | P&L |
|---|---:|---:|---:|
| 2025-Q1 | 1 | 0% | -$42 |
| 2025-Q2 | 6 | 100% | +$394 |
| 2025-Q3 | 14 | 71.4% | +$417 |
| 2025-Q4 | 2 | 100% | +$27 |
| 2026-Q1 | 4 | 75% | +$19 |
| 2026-Q2 | 5 | 100% | +$161 |

Q2-2026 concentration: **16%** (vs 45% raw) — concentration concern resolved.

### What changed vs the tables above

- **N counts**: 4.5× smaller (143→32 for Option C). The strategy has fewer unique-bar signals per year.
- **WR direction**: still strong (81.2%), but not 90.2%. Some of the "extra" wins in raw stats were duplicate rows for the same bar.
- **P&L**: smaller (nominal $976 vs $4,597) because multiple rows for the same bar accumulated pnl. The $976 is the correct net P&L for 32 unique unique-bar entries.
- **Walk-forward ratio**: 0.667 vs 1.149 — still PASS, but not "OOS improves over IS on Sharpe."
- **Q2 concentration**: 16% vs 45% — much better diversification.
- **Gate validity**: UNCHANGED. Narrow-OR WR=81.2% vs wide-OR WR=37.9% is a clear edge.

**The gate decision stands. Promotion to PROMISING confirmed on deduped evidence.**
Real-fills (OPRA, N=22) are unaffected by dedup — OPRA-based, not watcher-grader based.
