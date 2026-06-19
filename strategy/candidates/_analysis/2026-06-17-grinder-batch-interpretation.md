# Grinder Batch Interpretation — 2026-06-17

Tasks closed: 917ce271, 48e71fff, ccf17d04, 8f968c43
Evaluation framework: edge_capture >= 771 (50% of J max 1542) AND pnl_5_05 <= 0 (loser day) AND SW_hurt <= 1

---

## 1. sniper_stage2_grinder (task 917ce271)

**Top keeper combo:**
- vol_mult=1.1, body_min_cents=0.02, min_stars=2, strike_offset=2
- premium_stop_pct=-0.06, tp1_premium_pct=0.40, runner_target_pct=3.0
- profit_lock_threshold_pct=0.0, tp1_qty_fraction=0.667, qty=10
- proximity_dollars=1.5, require_break_above_open=True

**Anchor day P&L:**
- 4/29 (J winner): +$181.84 ✓
- 5/01 (J winner): $0
- 5/04 (J winner): +$191.64 ✓
- 5/05 (J LOSER):  **+$202.41** ✗ RED FLAG
- 5/06 (J LOSER):  $0
- 5/07 (J LOSER):  +$235.40

**Metrics:** edge_capture=373.48, wide_pnl=40,656.65, wide_n=234, wide_wr=0.932

**Verdict: REJECT**

Reasons:
1. edge_capture=373 < 771 minimum (24% of J max). Gate fails by 2x.
2. Fires on J loser day 5/05 with +$202 profit. Engine is BUYING what J avoids.
3. wide_wr=93.2% is implausibly high — IS overfit signal. Real-fills IS WR is typically 45-65%.
4. min_stars=2 + require_break_above_open + proximity=1.5 combination may be data-snooping from Stage-1 keepers.

OP-20 disclosures: concentration in wide_pnl driven by high-WR overfit, not genuine edge. No OOS gate run.

---

## 2. overnight_grinder (task 48e71fff)

**Top keeper combo:**
- super_stop=-0.2, super_tp1=1.0, runner_target=3.0
- level_qty=18, level_stop=-0.1, level_tp1=0.3, trendline_stop=-0.06

**Anchor day P&L:**
- 4/29 (J winner): +$306.30 ✓
- 5/01 (J winner): -$16.17 (small loss)
- 5/04 (J winner): +$804.72 ✓
- 5/05 (J LOSER):  $0 ✓
- 5/06 (J LOSER):  $0 ✓
- 5/07 (J LOSER):  +$74.29

**Metrics:** edge_capture=1094.85, wide_pnl=1,005.13, wide_n=353, wide_wr=0.161

**Quarter breakdown:**
- 2025-Q1: -$889.60 (NEGATIVE)
- 2025-Q2: -$934.85 (NEGATIVE)
- 2025-Q3: -$192.72 (NEGATIVE)
- 2025-Q4: -$1,289.39 (NEGATIVE)
- 2026-Q1: +$5,431.97 (ONLY positive — tariff-shock spike)
- 2026-Q2: -$1,120.28 (NEGATIVE)

**Sub-window estimate:**
- W1_2025H1: ~-$1,824 (Q1+Q2 2025) → SW_HURT
- W2_2025Q3: ~-$193 → SW_HURT (borderline, exceeds $50 threshold)
- W3_2025Q4: ~-$1,289 → SW_HURT
- W4_2026H1: positive (Q1-2026 dominant) → HELP
- SW_hurt ≈ 3/4. Fails gate (≤1 required).

**Verdict: REJECT**

Reasons:
1. edge_capture=1,095 passes the J-edge gate ✓ (sole positive signal)
2. BUT: 5/6 quarters are negative. The entire wide_pnl=+$1,005 comes from a single tariff-shock quarter (2026-Q1: +$5,432 offsets $4,427 losses everywhere else).
3. SW_hurt ≈ 3/4 — catastrophic sub-window failure. Gate requires ≤1.
4. wide_wr=16.1% — 1-in-6 trades wins. This is a lottery ticket strategy, not an edge.
5. The super_stop=-0.20 (20% stop) is 2× the production stop. This is a wider-net approach that catches more in volatile regimes but bleeds in choppy markets.

C4 disclosure: 2026-Q1 concentration makes aggregate metrics misleading. This would appear to "work" until the tariff-shock regime ends, then revert to losing.

---

## 3. vwap_overnight_grinder (task ccf17d04)

**Top keeper combo:**
- vol_mult=1.5, proximity_dollars=0.15, lookback_bars=2, body_min_cents=0.05
- premium_stop_pct=-0.14, tp1_premium_pct=0.5, runner_target_pct=2.0
- strike_offset=2, qty=3, tp1_qty_fraction=0.667
- profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05
- require_ribbon_agreement=True, ribbon_min_spread_cents=30.0

**Anchor day P&L:**
- 4/29 (J winner): $0 ✗ MISS
- 5/01 (J winner): +$40.01
- 5/04 (J winner): $0 ✗ MISS
- 5/05 (J LOSER):  +$40.54 ✗ RED FLAG
- 5/06 (J LOSER):  $0
- 5/07 (J LOSER):  $0

**Metrics:** edge_capture=40.01, wide_pnl=587.72, wide_n=12, wide_wr=0.833

**Verdict: REJECT**

Reasons:
1. edge_capture=40 < 771. Catastrophic fail — captures only 2.6% of J's max possible edge.
2. MISSES both primary J winner days (4/29 and 5/04). VWAP setup fires at different times than J's edge.
3. FIRES on J loser day 5/05 (+$40.54). Counter-edge confirmed.
4. n=12 total trades in 16 months. Insufficient sample for any confidence.
5. wide_wr=83.3% with n=12 is meaningless — small sample overclaims.

Note: The VWAP reclaim/rejection setup fires at different market moments than BEARISH_REJECTION_RIDE_THE_RIBBON. It's not a refinement — it's a different strategy that doesn't align with J's observed edge days.

---

## 4. sniper_overnight_grinder (task 8f968c43)

**Top keeper combo:**
- vol_mult=1.3, body_min_cents=0.05, min_stars=2, strike_offset=2
- premium_stop_pct=-0.08, tp1_premium_pct=0.40, runner_target_pct=1.5
- profit_lock_threshold_pct=0.0, profit_lock_stop_offset_pct=0.05
- tp1_qty_fraction=0.667, qty=10, proximity_dollars=1.5
- require_break_above_open=True

**Anchor day P&L:**
- 4/29 (J winner): +$113.65 ✓
- 5/01 (J winner): $0
- 5/04 (J winner): +$115.98 ✓
- 5/05 (J LOSER):  **+$126.51** ✗ RED FLAG
- 5/06 (J LOSER):  $0
- 5/07 (J LOSER):  +$147.13

**Metrics:** edge_capture=229.63, wide_pnl=24,696.46, wide_n=208, wide_wr=0.923

**Verdict: REJECT**

Reasons:
1. edge_capture=229 < 771. Fails by 3.4×.
2. Fires on J loser day 5/05 (+$126). Same structural problem as sniper_stage2.
3. wide_wr=92.3% is implausibly high — same overfit fingerprint as sniper_stage2.
4. SNIPER_LEVEL_BREAK is a ★★★+ level break setup. The 5/05 J loser was a mean-reversion day — level breaks go wrong in these conditions. The gate does not protect against this regime.
5. runner_target_pct=1.5 (vs production 2.5) cuts winners short — a defensive compromise that doesn't solve the 5/05 problem.

Comparison note: sniper_stage2 (917ce271) uses vol_mult=1.1 vs sniper_overnight (8f968c43) vol_mult=1.3. Neither vol threshold prevents 5/05 fires. The 5/05 problem is structural to the SNIPER setup, not a tuning issue.

---

## Summary table

| Task | Setup | edge_capture | 5/05 P&L | SW_hurt | Verdict |
|------|-------|-------------|----------|---------|---------|
| 917ce271 | SNIPER_STAGE2 | 373 ✗ | +$202 ✗ | n/a | REJECT |
| 48e71fff | OVERNIGHT (v14/15) | 1095 ✓ | $0 ✓ | ~3 ✗ | REJECT |
| ccf17d04 | VWAP | 40 ✗ | +$41 ✗ | n/a | REJECT |
| 8f968c43 | SNIPER_OVERNIGHT | 229 ✗ | +$127 ✗ | n/a | REJECT |

**None of these 4 grinder outputs yield a ratifiable candidate.**

---

## Actionable findings

1. **SNIPER_LEVEL_BREAK structural problem:** Both SNIPER variants fire on 5/05 (J loser). The loser days are characterized by mean-reversion/chop after an initial directional move. SNIPER breaks levels into this chop. A VIX-velocity gate (L45: VIX character > VIX level) may help — on 5/05 VIX was flat/falling despite elevated level, which is the false-break fingerprint.

2. **overnight_grinder quarter concentration:** The v14/v15 general sweep is capturing tariff-shock (2026-Q1) exclusively. Any gate derived from this sweep will overfit to that regime. Need regime-stratified WF with hold-out on 2026-Q1.

3. **VWAP setup fires at wrong times:** VWAP reclaim/rejection setups don't align with J's edge moments (4/29, 5/04). These are valid strategies but for a different market condition. Deprioritize VWAP research until BEARISH_REJECTION edge is fully exploited.

4. **Suspicious high WR (93%) in SNIPER grinders:** Production BEARISH_REJECTION real-fills WR is 45-55%. Any grinder producing 93% WR on IS is almost certainly selecting on exit criteria rather than entry edge. The `-0.06` stop (SNIPER_STAGE2) plus high `runner_target_pct=3.0` likely creates many "didn't hit stop yet" phantom wins.
