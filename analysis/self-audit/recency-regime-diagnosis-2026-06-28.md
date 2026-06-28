# Recency Regime Diagnosis — 2026-06-28

**Question:** Is the Safe2 6-day bleed (-$404.64, 0/11 WR) a regime shift or small-n noise?

## Verdict: REGIME SHIFT (not noise)

### Evidence

From `recency-confirmation.json` (run_date 2026-06-28, window 2026-05-21..2026-06-26):

| Edge + tier | Recent n | Recent exp/tr | Full-OOS 2026 exp/tr | Verdict |
|---|---|---|---|---|
| vwap_continuation / ATM | 5 | -$34.13 | +$56.46 | YELLOW |
| vwap_reclaim_failed_break / ATM | 3 | -$41.20 | +$13.66 | YELLOW |
| vix_regime_dayside / ATM | 3 | -$36.80 | +$70.79 | YELLOW |
| **Combined ATM book** | **11** | **-$36.79** | **+$94.01** | **RED** |
| vwap_continuation / OTM-2 | 9 | +$5.71 | +$19.03 | YELLOW |

**Statistical noise test:** 0/11 ATM wins with full-OOS WR ~45-63% has p < 0.1%. Not small-n noise.

### Regime Character (inferred)

The timing (May 21 - Jun 26, 2026) follows the tariff-shock resolution in Q1-Q2 2026 that drove a strong bull recovery. Key signals:

1. **OTM-2 positive, ATM negative**: OTM-2 options are cheaper → smaller absolute $ loss at the -8% stop. ATM options carry higher premium → bigger stop-loss $ on each failure. In a choppy/grinding regime, the cheaper OTM-2 survives to occasional TP1 while ATM bleeds on every miss.

2. **All 3 ATM edges negative simultaneously**: vwap_continuation, vwap_reclaim_failed_break, and vix_regime_dayside all bleed in the same window. A single-edge failure could be bad luck; three simultaneous failures across different signal families confirms a regime character change, not a detector glitch.

3. **Zero win days in 6 trading days**: Not a concentration problem (a few big losses). Every single day was a loss. A grind-up, low-VIX, slow-range regime produces this pattern for BEARISH_REJECTION_RIDE_THE_RIBBON setups — the signal fires but the rejection isn't sustained.

4. **Full-OOS 2026 strongly positive**: Jan-May 2026 was excellent (drive driven by macro-vol from tariff shock, giving clean VWAP rejections). June 2026 is the "after the storm" grind — VIX compressing back to baseline, SPY in steady recovery, no clean directional reversal setups.

### Root Cause

**VIX character mismatch.** The VWAP-continuation and dayside-VIX signal families need elevated/declining VIX (sharp moves, clean rejections). Post-shock Q2 recovery = compressed VIX, grinding price action = the engine fires but setups fail.

This matches C5 lesson: "VIX character > VIX level; high-score + 0-trade + declining-VIX = correct abstention."

### Implication for R&D

- **Do NOT arm any ATM edge while RED.** The CONFIRM gate is working correctly.
- **OTM-2 is the live tier for Safe-2 (v15 per-tier doctrine).** OTM-2 shows YELLOW (+$5.71/tr), not RED. The ATM RED is a diagnostic construct for the recency check, not the live engine's actual strike.
- **OTM-2 tp1_qty_fraction=0.8 + fixed lock** applied today (pk-2026-06-28-001, all 4 OOS gates pass). This exit improvement applies to whatever fills do happen.
- **Next regime-appropriate edge target**: Range-scalp (mean-reversion level fade with ITM + tight targets, gated to flat-ribbon/confirmed-range). The current regime IS that regime. Chef/kitchen should be cooking this family.
- **Do not burn grinder cycles tuning VWAP-continuation exits** until VIX character recovers and ATM recency flips YELLOW→CONFIRM.

### Action

- [x] Filed as `analysis/self-audit/recency-regime-diagnosis-2026-06-28.md`
- [x] Queue range-scalp R&D family to kitchen (see Priority #6 in handoff) — task 2b429363 queued 2026-06-28
- [ ] Monitor: recency-confirmation next run after market week 2026-06-30 to check for regime shift back
