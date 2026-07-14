# Trend-Alignment Correlation Study -- Phase 1 Results

Scored: 2026-07-14T19:32:49 ET. Frozen pre-reg: `analysis/recommendations/prereg-trend-alignment-correlation-2026-07-14.json` (no re-picks after freeze).

## VERDICT: KILL

P1 (own verdict): **KILL**. Overall (P1 AND P2-corroboration): **KILL**.

A KILL/INCONCLUSIVE result here is a publishable, informative outcome per this program's own discipline -- it does NOT get re-run or re-picked. A KILL means Phase 0's context-bundle tag stays LOGGED-ONLY (or is retired), never promoted to a gate/veto/sizing input.

## Hypothesis (frozen)

Signals ALIGNED with the multi-timeframe (daily+hourly+15m) trend at entry have higher expectancy than signals FIGHTING it. Operationalized as: per-trade P&L, grouped by an AGREEMENT bucket in [-3..+3] (positive = trend agrees with the trade's own side, negative = trend fights it, computed via alignment_vs_side()'s signed_score -- NOT the raw market-direction alignment_score, so bull and bear populations pool onto the same agreement axis), should show monotonic-ish increasing expectancy from bucket -3 to +3, and losing episodes should skew toward negative buckets while winners skew toward positive buckets.

## P1 -- canonical ribbon_ride cohort, SS-B replay (MODELED, real OPRA bars)

n_total_signals=250, OOS (date>=2026-01-01) n=90, no-OPRA-coverage skips=0. Self-check vs `replay_cell()`: **PASSED** (ref_total_pnl=$4465.60).

### P1 OOS expectancy-by-alignment-bucket

| bucket | n | mean pnl | total pnl |
|---|---|---|---|
| -3 | 6 | $-60.30 | $-361.80 |
| -2 | 0 | - | $0.00 |
| -1 | 20 | $-21.49 | $-429.80 |
| +0 | 0 | - | $0.00 |
| +1 | 41 | $123.28 | $5054.40 |
| +2 | 0 | - | $0.00 |
| +3 | 23 | $-65.35 | $-1503.00 |

Spearman (bucket vs mean-pnl): rho=-0.054, p=0.613. Shuffle-null 90% interval (seed=1407, n=1000 draws, alpha=0.1): [-0.1697443174643978, 0.17646677768546604]. Beats null: **False**.

Monotonic-ish (<=1 adjacent-bucket inversion): **PASS** (1 inversions across 4 present buckets).

Aligned-vs-fighting t-test (secondary, disclosed only): {'n_aligned': 64, 'n_fighting': 26, 'mean_aligned': 55.49, 'mean_fighting': -30.45, 't_stat': 0.8856056744867767, 'p_value': 0.37836975570294085}

Top-3-episode concentration: 1.582 of total P&L (OP-20 disclosure).

Win/loss x aligned/fighting contingency: {'aligned_win': 25, 'aligned_loss': 39, 'neutral_win': 0, 'neutral_loss': 0, 'fighting_win': 7, 'fighting_loss': 19}. % losers fighting trend: 32.8. % winners aligned with trend: 78.1.

### P1 full-window (IS+OOS combined, for reference -- IS/OOS split is the primary read)

| bucket | n | mean pnl | total pnl |
|---|---|---|---|
| -3 | 20 | $-79.84 | $-1596.80 |
| -2 | 0 | - | $0.00 |
| -1 | 75 | $-18.53 | $-1390.00 |
| +0 | 0 | - | $0.00 |
| +1 | 100 | $42.24 | $4223.80 |
| +2 | 0 | - | $0.00 |
| +3 | 55 | $58.70 | $3228.60 |

## Kill-criteria ladder (P1's own SUPPORTED/KILL verdict)

1. OOS positive + beats shuffle-null: **False**
2. Monotonic-ish: **True**
3. Survives drop-top-3-per-bucket: **True** (post-drop n=78, rho=-0.075, p=0.515)
4. Both chronological halves same sign: **False** (first half n=45 rho=0.008, p=0.958, second half n=45 rho=-0.146, p=0.338)
5. P2 (real fills) corroborates sign: **False** (P2 engine n=110, evidence floor met=True)

## P2 -- real engine fills (MEASURED)

n=110 engine-attributed closed episodes ({'engine': 110, 'manual': 3, 'unknown_attribution': 0, 'n_positions_total': 113}), 0 still-open excluded by construction.

### P2 engine expectancy-by-alignment-bucket

| bucket | n | mean pnl | total pnl |
|---|---|---|---|
| -3 | 0 | - | $0.00 |
| -2 | 0 | - | $0.00 |
| -1 | 42 | $-22.76 | $-956.00 |
| +0 | 0 | - | $0.00 |
| +1 | 49 | $-20.73 | $-1015.99 |
| +2 | 0 | - | $0.00 |
| +3 | 19 | $13.05 | $248.00 |

Spearman: rho=0.041, p=0.674. Beats null: False (n=110, evidence floor n>=15 met: True -- P2's job is DIRECTIONAL corroboration, not an independent statistical pass/fail).

Win/loss contingency: {'aligned_win': 6, 'aligned_loss': 62, 'neutral_win': 0, 'neutral_loss': 0, 'fighting_win': 1, 'fighting_loss': 41}. % losers fighting trend: 39.8. % winners aligned: 85.7.

### P2 manual (n=3, reported separately, NEVER pooled into engine expectancy)

| bucket | n | mean pnl | total pnl |
|---|---|---|---|
| -3 | 0 | - | $0.00 |
| -2 | 0 | - | $0.00 |
| -1 | 0 | - | $0.00 |
| +0 | 0 | - | $0.00 |
| +1 | 3 | $91.33 | $274.00 |
| +2 | 0 | - | $0.00 |
| +3 | 0 | - | $0.00 |

## P3 -- J's OP-16 anchor trades (n=7, corroboration/context ONLY, never counted toward pass/fail)

| date | role | side | j_pnl | signed_score | aligned | fighting |
|---|---|---|---|---|---|---|
| 2026-04-29 | winner | P | $342.00 | +1 | False | False |
| 2026-05-01 | winner | P | $470.00 | -1 | False | False |
| 2026-05-04 | winner | P | $730.00 | -3 | False | True |
| 2026-05-05 | loser | P | $-260.00 | -3 | False | True |
| 2026-05-06 | loser | P | $-300.00 | -3 | False | True |
| 2026-05-07 | loser | C | $-45.00 | -1 | False | False |
| 2026-05-07 | loser | C | $-120.00 | +3 | True | False |

Spearman (n=7, always INCONCLUSIVE per evidence floor): rho=0.150, p=0.749.

## Pooled cross-population sign check (informational only -- see pre-reg primary_metric)

{'p1_oos_sign': False, 'p2_engine_sign': True, 'p3_sign': True, 'all_agree': False}

## Honesty notes

- P1 is a MODELED replay (SS-B exit shape on real OPRA bars), not a live fill -- absolute dollars are QTY=10 research-scale, not account-size absolute.
- P2 is MEASURED (real broker fills) but n~113 spans multiple arms/risk-tiers pooled together per the pre-reg's population definition; not stratified by arm here.
- P3's alignment reconstruction is MODELED (no live context-bundle existed at those April/May 2026 trade times) even though j_pnl itself is MEASURED.
- This pre-reg's scope ends at 'does it correlate' -- a SUPPORTED verdict does NOT itself change any live behavior (OP-0 #1 / OP-16 eval-first gate). It only qualifies a separately pre-registered Phase 2 proposal for HOW the tag would be consumed.
- **Build-time observation (disclosed, not a re-pick):** buckets 0/+2/-2 are EMPTY in every population's table above. Root cause verified directly (sampled 60 P1 alignment reads): `analyze_structure`'s per-timeframe classifier essentially never returns 'range'/'unknown' on SPY daily/hourly/15m history in this window -- every timeframe read was 'uptrend' or 'downtrend', never a 0-vote. `alignment_score` is therefore structurally odd-valued ({-3,-1,+1,+3}), not the full [-3,+3] the pre-reg's bucket range anticipated. This does not change any scoring/kill-criteria logic (all bucket math already handles n=0 buckets correctly) -- disclosed because it means this study's effective resolution is 4 buckets, not 7, a fact worth carrying into any Phase 2 design.
