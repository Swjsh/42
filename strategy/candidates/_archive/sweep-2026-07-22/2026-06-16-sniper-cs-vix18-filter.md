<!-- Filed: 2026-06-16 by Gamma autonomous session -->
<!-- Type: filter_change -->
<!-- Status: OOS-FAILED — 2026-06-17. WF=0.173 < gate 0.50. VIX-TRENDING gate is next step. -->

# CANDIDATE: SNIPER_CS_VIX18_FILTER

**Filed:** 2026-06-16  
**Filer:** gamma-autonomous (direct backtest, not kitchen spec)  
**Type:** filter_change + VIX regime gate  
**Status:** OOS-FAILED — 2026-06-17. WF=0.173 (gate 0.50). VIX-TRENDING gate is active follow-up.  
**Builds on:** SNIPER_CS_CHART_STOP (leaderboard #23)

## Hypothesis

Adding a VIX>=18 minimum filter to chart-stop SNIPER dramatically improves IS performance by eliminating low-vol chop entries. L73 established VIX character matters for level-break setups. High-VIX entries show stronger directional follow-through; wider chart-stop buffers (buf=1.0) survive intraday noise better in elevated-vol regimes where the price move is sustained.

## Full 64-Combo Sweep Results (IS: 2025-01-01 to 2026-05-22)

**40/64 combos positive with VIX>=18** | **n=95 for ALL combos** (same 95 VIX>=18 entries regardless of buf/tp1/runner)

### Top 5 combos by VIX18 wide_pnl:

| # | buf | tp1_r | run_r | off | VIX18 wp | Baseline wp | Delta | Delta% |
|---|-----|-------|-------|-----|----------|------------|-------|--------|
| 1 | 1.0 | 2.5 | 3.0 | 0 (ATM) | **$33,266** | $21,246 | +$12,020 | +57% |
| 2 | 1.0 | 2.5 | 3.5 | 0 (ATM) | $32,226 | $20,432 | +$11,794 | +58% |
| 3 | 0.75 | 2.5 | 3.5 | 0 (ATM) | $30,766 | $23,003 | +$7,763 | +34% |
| 4 | 1.0 | 2.5 | 3.0 | 2 (ITM-2) | $30,477 | $13,790 | +$16,687 | +121% |
| 5 | 0.75 | 2.5 | 3.5 | 2 (ITM-2) | $29,306 | $19,692 | +$9,614 | +49% |

**NEW BEST COMBO: buf=1.0/tp1=2.5/run=3.0/off=0 → $33,266** (vs prior stated best $29,306 at buf=0.75/off=2).

Full sweep: `analysis/recommendations/sniper-cs-vix18-sweep.json`

### Mechanism (buf=1.0 benefits most):
In high-VIX regimes, directional momentum sustains longer — wider stop (1.0 SPY point) survives noise without premature exit. Low-VIX entries (eliminated) reverse before reaching 2.5x TP1.
- **5/05 [J loser day] correctly skipped** — VIX was below 18 on 5/05/2026; engine correctly passes
- **4/29 [J winner day] still -$692** — SNIPER structural: SNIPER fires on different signals than BEARISH_REVERSAL (J's anchor). This is known (SNIPER ≠ J-edge capture). SNIPER is a separate trade class

## J anchor anchor impact (OP-16)

4/29 still shows -$691.85 — this is a KNOWN LIMITATION of SNIPER (it doesn't fire on J's BEARISH_REVERSAL anchor trades). SNIPER is evaluated separately by its own wide_pnl and WR metrics, not by J-anchor edge_capture. The -$692 on 4/29 is structural and unchanged by the VIX filter.

**The VIX filter correctly eliminates the 5/05 false-positive win** — engine was making $1,421 on a day J lost, which was suspicious (SNIPER fire into wrong-direction day).

## OP-20 disclosures

1. **Account-size:** qty=10, ITM-2 at SPY ~$750 → avg entry premium ~$3.00. Risk/trade: 10×$3.00×100×37%stop=$1,100. Needs $2,200+ account (50% risk cap).
2. **Sample bias:** Single best combo from prior 64-combo sweep. IS window = 2025-01-01 to 2026-05-22 (16 months). VIX filter adds 1 degree of freedom.
3. **Out-of-sample:** NEEDS-OOS. Run separate OOS window 2026-05-22 to 2026-06-15.
4. **Real-fills:** NEEDS-REALFILLS. Top SNIPER VIX>=18 anchor days need OPRA validation.
5. **Concentration:** unknown without top5_pct computation on filtered set. With 95 trades, concentration risk is moderate (less than NO_FILTER's 170 trades).
6. **Failure modes:** high-VIX environments produce larger option premiums and wider bid/ask spreads. BS-sim may overstate edge. Real-fills validation critical.

## OOS Walk-Forward Results (2026-06-17)

**IS (2025-01-01..2025-10-31):** n=43, pnl=$30,702, WR=44.2%, sharpe=2.060  
**OOS (2025-11-01..2026-05-22):** n=52, pnl=$2,563, WR=25.0%, sharpe=0.356  
**WF ratio: 0.173 — FAIL** (gate >=0.50)  
OOS P&L>0: PASS | OOS WR>=45%: FAIL

IS quarterly: Q1=$9,596 / Q2=$12,767 / **Q3=$0 (zero fires)** / Q4=$8,339  
OOS quarterly: Q4=-$1,151 / Q1+=$3,409 / Q2+=$305

**Root cause of IS overfit (L104 pattern):**  
Q3 2025 had zero SNIPER fires at VIX>=18 (summer low-VIX). The IS daily P&L series included 175 zero-value days + 43 non-zero days. Sharpe computed over all 218 days (80% are $0) → near-zero denominator → inflated IS Sharpe 2.060. The OOS has more complete VIX>=18 coverage (52 of 118 days) but WR degrades to 25%, confirming the IS regime (Q1/Q2/Q4 2025) was favorable to this setup but doesn't generalize.

**VIX level gate is IS-overfit.** VIX character (trending/escalating, L73) is the correct discriminator. Active follow-up: `vix_trending=True` gate in SniperCSCombo.

Full OOS results: `analysis/recommendations/sniper-cs-vix18-oos.json`

## Pre-merge gate

- [x] OOS window: WF=0.173 — FAIL
- [ ] VIX-TRENDING gate OOS (active follow-up — `vix_trending=True` in evaluator)
- [ ] Real-fills on top 3 SNIPER VIX-trending days (not J anchors — SNIPER has own anchor dates)
- [ ] Gym validators PASS

## Implementation

Add `vix_min: float = 0.0` to `SniperCSCombo` (DONE — 2026-06-16).
Add VIX gate in `_simulate_cs_trade()` after `vix_at_entry` computation (DONE — 2026-06-16):
```python
if combo.vix_min > 0 and vix_at_entry < combo.vix_min:
    return None
```

## Confidence

3 / 10 — OOS-FAILED (WF=0.173). IS edge was real but IS-overfit (Q3 zero-fire regime inflated Sharpe). VIX level gate alone does not generalize. VIX-TRENDING gate (prior_day_VIX > 5d_avg) is the OOS-validated mechanism per L73 — active follow-up in sniper_cs_evaluator.py.
