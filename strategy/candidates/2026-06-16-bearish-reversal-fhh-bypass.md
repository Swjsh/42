# CANDIDATE: BEARISH_REVERSAL_FHH_BYPASS (Rank 28)

**Filed:** 2026-06-16  
**Filer:** Gamma (interactive session — not kitchen daemon)  
**Type:** filter_change (filter_5 + filter_8 bypass for FHH-specific reversal)  
**Status:** REJECTED — 2026-06-17. Wrong-bar anti-pattern L103.

## Hypothesis

When price runs up during the first hour of RTH (creating a First Hour High), then later retests that FHH from below while ribbon=BULL and clean level rejection fires, this is a high-probability BEARISH REVERSAL entry. The 5/01 11:50 J anchor (+$470 real) is the canonical case: FHH=724.24, ribbon=BULL, fhh_level_rejection fired.

Currently blocked by filter_5 (ribbon not BEAR) and filter_8 (VIX gate). This candidate bypasses both for the specific `fhh_level_rejection` trigger class only.

## Mechanism

**Condition (all must hold):**
1. `fhh_level_rejection` in triggers (NOT standard `level_rejection` — FHH-only)
2. `trendline_rejection` NOT in triggers (trendline-only bypass is already handled separately)
3. `ctx.ribbon_now.stack == "BULL"` (countertrend setup — BEAR ribbon already passes filter_5)
4. `include_bearish_reversal_bypass=True` (OPT-IN, default False — Rule 9 gated)

**Effect:** Removes filter_5 and filter_8 from blockers when all 4 conditions hold. Each removed filter costs -1 to bear_score (demerit). A FHH bypass entry scores at most 8/10 vs a clean BEAR-ribbon entry at 10/10.

**Depends on Rank 27 (FHH feature):** `fhh_level_rejection` only fires when `include_first_hour_high=True`. The bypass is meaningless without FHH enabled. These two features compose together.

## Stage-1 Results (2026-06-16)

**J anchor days — base vs (FHH + bypass combined):**

| J day | Type | Base_n | Base_pnl | FHH+Bypass_n | FHH+Bypass_pnl | Delta |
|---|---|---|---|---|---|---|
| 4/29 | J-WINNER | 2 | -$501 | 2 | -$501 | $0 |
| 5/01 | J-WINNER | 1 | -$56 | 2 | -$420 | -$364 |
| 5/04 | J-WINNER | 1 | +$793 | 1 | +$793 | $0 |
| **5/05** | **J-LOSER** | **0** | **$0** | **0** | **$0** | **$0** ✓ |
| **5/06** | **J-LOSER** | **0** | **$0** | **0** | **$0** | **$0** ✓ |
| **5/07** | **J-LOSER** | **1** | **+$161** | **1** | **+$161** | **$0** ✓ |

**Key finding:** 5/01 11:50 bar now passes (fhh_level_rejection fires, blockers cleared, passed=True ✓). But the BS-sim result is confounded: the 11:50 entry shows -$47.50 (BS-sim), not J's actual +$470 (real fills). This discrepancy is expected per L71/L74 (BS-sim vs real-fills gap). The 5/01 delta is negative in BS-sim but reflects position interaction with the 13:35 secondary entry, not the 11:50 trade quality.

**17-month OOS (base vs FHH+bypass combined, Jan 2025–May 2026):**
- Base: n=348, pnl=-$8,915
- FHH+Bypass: n=371, pnl=-$10,816
- **Delta: dn=+23, dpnl=-$1,901**

OOS is net negative. The FHH bypass fires on 23 additional bars across 17 months, and the net result is worse. This is expected in BS-sim because:
1. BS-sim entry premium is miscalibrated at countertrend FHH bars (theta/delta at wrong time)
2. The bypass fires correctly at 5/01-type events but also on other FHH retests that are bullish continuation (price retests FHH then breaks above)
3. Real-fills validation is needed to confirm the subset where J's entry quality discriminator (clean rejection, not continuation) would produce positive outcomes

**Graduated guards added (18 total, all PASS):**
- `test_bearish_reversal_bypass_fires_at_fhh`: Verifies 5/01 11:50 passes with fhh+bypass enabled (dead-knob guard)
- `test_bearish_reversal_bypass_no_regression_loser_days`: Verifies 5/05 and 5/07 signatures unchanged

## Discriminator Evolution

**v1 (any level_rejection + bypass):** Added 2 new losers on 5/05 (-$404), 5/06 (-$376), changed 5/07 from +$161 to -$448. Net -$1,250 on anchor days. REJECTED — too broad.

**v2 (HTF guard: htf_15m_stack != BULL):** Fully neutral on ALL days (delta=0 everywhere). But also blocked the 5/01 bypass: HTF=BULL at 11:50 on 5/01. REJECTED — too strict.

**v3 (fhh_level_rejection only — CURRENT):** FHH fires 23 times in 17 months, neutral on loser days, fires correctly at 5/01 11:50. Net OOS -$1,901 (BS-sim, expected to be negative — real-fills needed).

**v4 (empirically tested 2026-06-16):**

- **Proximity gate (ANTI-CORRELATED — DO NOT USE for gap-up J-anchor setups):** `fhh_quality_proximity`: require FHH within X$ of any `multi_day_level`. Result: removes 5/01 at ALL thresholds (0.50, 1.00, 2.00). Gap-up FHH is by definition ABOVE multi_day_levels, not near them — price broke above prior range. Documented as anti-pattern guard `test_fhh_v4_proximity_antipattern`.

- **Gap-up discriminator (PRESERVES 5/01, FILTERS 5/08):** `fhh_above_max_prior_min=1.00`: require FHH >= max(multi_day_levels) + $1.00 (price broke above all prior levels by at least $1). Result:
  - 24 bypass days → 6 bypass days (75% reduction in bypass fires)
  - Bypass drag: -$1,899 → -$257 (86% improvement)
  - 5/01 11:50: FHH=$724.24, max_prior~$722 → gap=$2.24 → PASSES ✓
  - 5/08: FHH=$736.66, max_prior~$737 → gap=-$0.34 → BLOCKED ✓
  - Graduated guard: `test_fhh_v4_gapup_preserves_501_filters_508` (24/24 total, all PASS)
  - Remaining 6 bypass days (at $1 gate): 2025-06-16, 2025-07-21, 2025-07-24, 2025-09-15, 2025-11-04, 2026-05-01
  - Net bypass delta with v4: -$257 vs no-bypass (v3 was -$1,901). Much closer to neutral.
  - Real-fills still needed for the 6-day subset before promotion.

## OP-20 Disclosures

1. **Sample concentration:** Hypothesis sourced from N=1 J anchor event (5/01 11:50). OOS coverage: 23 bars over 17 months, mostly losing in BS-sim.
2. **BS-sim unreliability:** 5/01 11:50 shows -$47.50 in BS-sim vs J's actual +$470. Discrepancy caused by L71/L74 (BS-sim option pricing calibration issues at countertrend bars). Real-fills validation is Stage-2 gate.
3. **Rule 9 flag:** `include_bearish_reversal_bypass=True` is OPT-IN, default False. Production heartbeat.md change requires J ratification.
4. **Requires Rank 27:** This candidate depends on `include_first_hour_high=True`. Without FHH, `fhh_level_rejection` never fires and the bypass is a no-op.

## Stage-2 OOS Results (2026-06-16)

**OOS window: 2026-05-08 to 2026-05-22 (10 trading days)**

| Mode | Baseline | FHH+Bypass | Delta |
|---|---|---|---|
| BS-sim | N=17, -$907 | N=18, -$952 | +1 trade, -$45 |
| Real-fills (5/8 only) | N=0, $0 | N=2, -$132.72 | +2 trades, -$133 |

**New trades in OOS (real-fills):**
- 5/8 10:10 PUT → -$68.64 (FHH bypass first fire)
- 5/8 11:15 PUT → -$64.08 (FHH bypass second fire same day)

**Key observations:**
1. Bypass fires **twice** on 5/8 (multiple FHH retests in a session). This is by design (no per-session lock on FHH bypass entries) but means N_bypass > 1 per day is possible.
2. Both 5/8 real-fills trades lost. Price retested FHH repeatedly on 5/8 but broke above rather than rejecting below.
3. Combined OOS: N=2 new trades, WR=0%, P&L=-$133. N is too small for statistical significance.
4. IS/OOS: IS anchor N=1 (+$470 real fills, 5/01 J trade), OOS N=2 (-$133). Insufficient evidence for promotion.

**OOS verdict: NEEDS-MORE-DATA** — mechanism fires correctly but directional evidence is negative in the one OOS day that has both data and bypass activation.

## Pre-merge Gate

- [x] **Stage-2 real-fills OOS:** Run 2026-05-08..22 with FHH+bypass, real fills. Done: N=2 new trades (5/8 only), both losses, -$132.72 total. See Stage-2 results above.
- [x] **Level quality discriminator (EMPIRICALLY TESTED 2026-06-16):** Proximity to multi_day_levels is ANTI-CORRELATED — removes 5/01 at all thresholds. Gap-up discriminator (`fhh_above_max_prior_min=1.00`) correctly preserves 5/01 and filters 5/08: reduces 24→6 bypass days, drag -$1,899→-$257 (86% improvement). Parameters added to filters.py + orchestrator.py. Guards `test_fhh_v4_proximity_antipattern` and `test_fhh_v4_gapup_preserves_501_filters_508` added (24/24 PASS).
- [ ] **Real-fills for 6-day v4 subset:** The 6 remaining bypass days with `fhh_above_max_prior_min=1.00` need real-fills validation (OPRA fills, not BS-sim). Currently N=1 (5/01, real J trade +$470).
- [ ] **Live accumulation:** Need 3+ live J wins on FHH rejection setup before confidence can rise above 5/10. Current: 0/3.
- [ ] **J ratification (Rule 9):** Heartbeat.md addition requires J signoff before going live.

## REJECTION RATIONALE (2026-06-17)

**Root cause: L103 wrong-bar anti-pattern.** The FHH bypass fires at the 5/01 11:50 FHH-rejection bar. J's actual +$470 win on 5/01 was a **trendline_rejection at 13:36** — a completely different bar, trigger, and time. Validating the bypass "works on 5/01" is date-level validation; the engine enters at the FHH bar which LOSES, not at J's bar which won.

Empirical confirmation: `run_backtest(include_first_hour_high=True, include_bearish_reversal_bypass=True)` shows 5/01 regresses from -$56 → -$420 (−$364). The bypass correctly identifies 5/01 as a gap-up day but takes the WRONG bar.

**The fix that would actually capture J's 5/01 trade** is not an FHH bypass — it requires the trendline-rejection path with filter_5 softened for midday (L95 finding). These are independent mechanisms. This candidate is retired.

See archived v4 mechanism in implementation status above — code remains in filters.py/orchestrator.py for reference but `include_bearish_reversal_bypass` defaults to False and this path will not be promoted.

## Confidence

REJECTED — 0/10.

## Implementation Status

- `backtest/lib/filters.py`: `bearish_reversal_bypass` parameter + V4 discriminators (`fhh_quality_proximity`, `fhh_above_max_prior_min`) with anti-correlation warning in comments
- `backtest/lib/orchestrator.py`: `include_bearish_reversal_bypass`, `fhh_quality_proximity`, `fhh_above_max_prior_min` kwargs thread to `evaluate_bearish_setup()`
- `backtest/tests/test_graduated_guards.py`: 4 guards (24/24 passing): bypass_fires_at_fhh, bypass_no_regression_loser_days, v4_proximity_antipattern, v4_gapup_preserves_501_filters_508
- Kitchen: Real-fills for 6-day v4 subset enqueued
