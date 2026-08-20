# Engine-Stress Swarm — Batch Report

**Generated:** 2026-08-20T01:22:35 ET
**Disclosure:** Perturbed/synthetic bars -> BS-sim option fills -> RANKING-ONLY, not a WR authority (CLAUDE.md C1).

## Grid
- Runs: 1200 (1200 ok / 0 errors)
- Seeds: 2026-08-04, 2026-06-05, 2026-06-09, 2026-06-23, 2026-08-18, 2026-05-19, 2026-05-27, 2026-06-03, 2026-06-12, 2026-06-24, 2026-07-01, 2026-07-09, 2026-07-16, 2026-07-23, 2026-07-30
- Perturbations: baseline, trend_flip, amplify, dampen, gap_open, vix_up, vix_down, add_noise
- Variants: base_v15, tp1_30_allout, tp1_30_split, tp1_50_split, tp1_75_split, risk_15pct, risk_50pct, exit_chandelier, exit_fixed_tight, bull_off
- Aggregate BS-sim P&L (ranking-only): $7728.5 over 1164 trades

## By day (breadth check -- is a bad total real, or one bad day smeared in?)
- 15 days sampled, 7 net-negative (46.7%)
- Worst day: 2026-06-09 total_pnl=$-14063.4 (-182.0% of aggregate)
- Best day: 2026-07-09 total_pnl=$12825.1

| date | runs | total_pnl (full grid) | baseline_pnl (unperturbed only) |
|---|---|---|---|
| 2026-05-19 | 80 | $-26.0 | $0.0 |
| 2026-05-27 | 80 | $-1699.7 | $-776.0 |
| 2026-06-03 | 80 | $-4165.2 | $-60.3 |
| 2026-06-05 | 80 | $2833.7 | $-321.6 |
| 2026-06-09 | 80 | $-14063.4 | $-7302.6 |
| 2026-06-12 | 80 | $11259.5 | $-628.4 |
| 2026-06-23 | 80 | $-955.8 | $-52.2 |
| 2026-06-24 | 80 | $861.4 | $-6.3 |
| 2026-07-01 | 80 | $-856.7 | $0.0 |
| 2026-07-09 | 80 | $12825.1 | $3637.4 |
| 2026-07-16 | 80 | $430.6 | $0.0 |
| 2026-07-23 | 80 | $-3885.5 | $-38.7 |
| 2026-07-30 | 80 | $953.9 | $-4298.0 |
| 2026-08-04 | 80 | $4025.7 | $0.0 |
| 2026-08-18 | 80 | $190.9 | $-23.0 |

## Anomalies surfaced: 36
- **big_loss** seed=2026-07-23 pert=add_noise variant=exit_fixed_tight pnl=-1262.5
- **big_loss** seed=2026-07-23 pert=add_noise variant=bull_off pnl=-1106.0
- **big_loss** seed=2026-06-09 pert=trend_flip variant=base_v15 pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_30_allout pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_30_split pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_50_split pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_75_split pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=risk_15pct pnl=-1008.6
- **sizing_fragile** seed=2026-06-09 pert=baseline variant=exit_chandelier pnl=420.8
- **sizing_fragile** seed=2026-07-09 pert=baseline variant=tp1_50_split pnl=566.7
- **sizing_fragile** seed=2026-06-09 pert=trend_flip variant=bull_off pnl=447.6
- **sizing_fragile** seed=2026-06-09 pert=amplify variant=tp1_75_split pnl=792.4
- **sizing_fragile** seed=2026-06-12 pert=amplify variant=tp1_50_split pnl=581.4
- **sizing_fragile** seed=2026-07-09 pert=amplify variant=tp1_50_split pnl=638.1
- **sizing_fragile** seed=2026-06-09 pert=dampen variant=tp1_30_allout pnl=672.6
- **sizing_fragile** seed=2026-07-30 pert=dampen variant=base_v15 pnl=876.0
- **sizing_fragile** seed=2026-06-09 pert=gap_open variant=exit_chandelier pnl=632.7
- **sizing_fragile** seed=2026-07-23 pert=gap_open variant=tp1_75_split pnl=572.6
- **sizing_fragile** seed=2026-06-05 pert=vix_up variant=tp1_75_split pnl=541.4
- **sizing_fragile** seed=2026-06-09 pert=vix_up variant=bull_off pnl=621.3

## Swarm verdict (5-model free panel)
_models: nvidia/nemotron-3-super-120b-a12b:free, nvidia/nemotron-3-ultra-550b-a55b:free, openai/gpt-oss-20b:free (3/5 ok)_

**Consensus points**  
- All perspectives agree the reported P&L is BS‑simulated ranking‑only, not a real‑world fill or market‑impact authority.  
- All note missing critical disclosures: account size/risk basis, real‑fill assumptions (slippage, spreads), out‑of‑sample validation, and concentration/position limits.  
- All treat the anomaly rows as meaningful signals that the engine may have logic gaps under certain perturbations.  
- All agree that further, more rigorous testing (OOS, live‑paper, sensitivity analysis) is required before any reliance on the engine’s edge.

**Key disagreements**  
- **Robustness claim:** Perspective 2 and Perspective 5 stress the engine’s overall profitability and claim robustness across perturbations, while Perspective 3 argues the anomalies reveal concrete, repeatable holes (entry logic under `trend_flip`, rejection detection under `add_noise`).  
- **Weight of evidence:** Perspective 2 dismisses the anomalies as statistically insignificant noise due to tiny trade counts; Perspective 3 treats the identical trades across variants as deterministic proof of a flaw; Perspective 5 sits in the middle, acknowledging robustness but insisting on real‑world validation.  
- **Most rigorous take:** Perspective 3 provides the most specific, actionable diagnosis (identifying the exact setup and perturbation that cause identical losing trades across multiple variants) and proposes concrete, testable fixes. Its analysis is grounded in the observed data rather than aggregate P&L, making it the strongest basis for remediation.

**Synthesized recommendation**  
The engine shows promise but contains detectable logic gaps: entry signals are not robust to trend‑flip perturbations, and the BEARISH_REJECTION_RIDE_THE_RIBBON setup fires on noise‑induced reversals. Prioritize adding a higher‑timeframe trend‑confirmation gate and a volume‑filtered rejection threshold, cap concurrent rides on the same setup, then re‑run the stress grid (focused on `trend_flip` and `add_noise` perturbations) to verify the big‑loss anomalies disappear before pursuing broader OOS or live‑paper validation.

**Confidence in synthesis**  
7 – The three perspectives converge on the need for missing disclosures and further validation, but diverge on the severity of the flaws. Perspective 3’s detailed anomaly analysis provides the strongest evidence, raising confidence that the recommended fixes target real engine holes rather than simulation artifacts.

**Single most‑important next action**  
Implement a trend‑flip robustness gate (e.g., require the 15‑minute trend to align with the 60‑minute trend or VWAP slope) and re‑run the deterministic stress grid for the `trend_flip` perturbation on the 2026‑06‑09 seed; confirm that the three identical losing trades are eliminated or reduced to a statistically insignificant level.

**Watch‑for signal**  
If, after adding the trend‑confirmation gate, the `trend_flip`/2026‑06‑09/ base_v15 (or any variant) still produces the exact same three losing trades (BEARISH_REJECTION at 09:50, BEARISH_REJECTION at 10:10, BULLISH_RECLAIM at 10:50) with EXIT_ALL_PREMIUM_STOP, then the gate did not address the underlying entry‑logic flaw and the engine’s hole is deeper than a simple trend filter can fix. This would invalidate the current synthesis and require a redesign of the setup detection logic itself.