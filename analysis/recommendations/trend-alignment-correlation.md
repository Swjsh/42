# Trend-Alignment Correlation Study -- Phase 1 Results

Scored: 2026-09-02T05:27:15 ET. Frozen pre-reg: `analysis/recommendations/prereg-trend-alignment-correlation-2026-07-14.json` (no re-picks after freeze).

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
| -3 | 9 | $200.40 | $1803.60 |
| -2 | 0 | - | $0.00 |
| -1 | 24 | $42.23 | $1013.40 |
| +0 | 0 | - | $0.00 |
| +1 | 41 | $56.53 | $2317.60 |
| +2 | 0 | - | $0.00 |
| +3 | 16 | $-148.43 | $-2374.80 |

Spearman (bucket vs mean-pnl): rho=-0.150, p=0.157. Shuffle-null 90% interval (seed=1407, n=1000 draws, alpha=0.1): [-0.1627574785768802, 0.17177445262792726]. Beats null: **False**.

Monotonic-ish (<=1 adjacent-bucket inversion): **FAIL** (2 inversions across 4 present buckets).

Aligned-vs-fighting t-test (secondary, disclosed only): {'n_aligned': 57, 'n_fighting': 33, 'mean_aligned': -1.0, 'mean_fighting': 85.36, 't_stat': -0.736895564936749, 'p_value': 0.4637074677083082}

Top-3-episode concentration: 1.582 of total P&L (OP-20 disclosure).

Win/loss x aligned/fighting contingency: {'aligned_win': 20, 'aligned_loss': 37, 'neutral_win': 0, 'neutral_loss': 0, 'fighting_win': 12, 'fighting_loss': 21}. % losers fighting trend: 36.2. % winners aligned with trend: 62.5.

### P1 full-window (IS+OOS combined, for reference -- IS/OOS split is the primary read)

| bucket | n | mean pnl | total pnl |
|---|---|---|---|
| -3 | 27 | $59.11 | $1596.00 |
| -2 | 0 | - | $0.00 |
| -1 | 80 | $-5.56 | $-444.80 |
| +0 | 0 | - | $0.00 |
| +1 | 107 | $27.98 | $2994.00 |
| +2 | 0 | - | $0.00 |
| +3 | 36 | $8.90 | $320.40 |

## Kill-criteria ladder (P1's own SUPPORTED/KILL verdict)

1. OOS positive + beats shuffle-null: **False**
2. Monotonic-ish: **False**
3. Survives drop-top-3-per-bucket: **True** (post-drop n=78, rho=-0.146, p=0.204)
4. Both chronological halves same sign: **True** (first half n=45 rho=-0.129, p=0.399, second half n=45 rho=-0.251, p=0.097)
5. P2 (real fills) corroborates sign: **True** (P2 engine n=386, evidence floor met=True)

## P2 -- real engine fills (MEASURED)

n=386 engine-attributed closed episodes ({'engine': 386, 'manual': 5, 'unknown_attribution': 0, 'n_positions_total': 391}), 0 still-open excluded by construction.

### P2 engine expectancy-by-alignment-bucket

| bucket | n | mean pnl | total pnl |
|---|---|---|---|
| -3 | 124 | $-10.66 | $-1322.00 |
| -2 | 0 | - | $0.00 |
| -1 | 37 | $-24.57 | $-909.00 |
| +0 | 0 | - | $0.00 |
| +1 | 54 | $-7.96 | $-429.99 |
| +2 | 0 | - | $0.00 |
| +3 | 171 | $21.31 | $3644.00 |

Spearman: rho=-0.078, p=0.127. Beats null: False (n=386, evidence floor n>=15 met: True -- P2's job is DIRECTIONAL corroboration, not an independent statistical pass/fail).

Win/loss contingency: {'aligned_win': 60, 'aligned_loss': 165, 'neutral_win': 0, 'neutral_loss': 0, 'fighting_win': 39, 'fighting_loss': 122}. % losers fighting trend: 42.5. % winners aligned: 60.6.

### P2 manual (n=5, reported separately, NEVER pooled into engine expectancy)

| bucket | n | mean pnl | total pnl |
|---|---|---|---|
| -3 | 1 | $-60.00 | $-60.00 |
| -2 | 0 | - | $0.00 |
| -1 | 0 | - | $0.00 |
| +0 | 0 | - | $0.00 |
| +1 | 3 | $91.33 | $274.00 |
| +2 | 0 | - | $0.00 |
| +3 | 1 | $89.00 | $89.00 |

## P3 -- J's OP-16 anchor trades (n=7, corroboration/context ONLY, never counted toward pass/fail)

| date | role | side | j_pnl | signed_score | aligned | fighting |
|---|---|---|---|---|---|---|
| 2026-04-29 | winner | P | $342.00 | +1 | False | False |
| 2026-05-01 | winner | P | $470.00 | -1 | False | False |
| 2026-05-04 | winner | P | $730.00 | -3 | False | True |
| 2026-05-05 | loser | P | $-260.00 | -3 | False | True |
| 2026-05-06 | loser | P | $-300.00 | -3 | False | True |
| 2026-05-07 | loser | C | $-45.00 | +1 | False | False |
| 2026-05-07 | loser | C | $-120.00 | +3 | True | False |

Spearman (n=7, always INCONCLUSIVE per evidence floor): rho=0.094, p=0.842.

## Pooled cross-population sign check (informational only -- see pre-reg primary_metric)

{'p1_oos_sign': False, 'p2_engine_sign': False, 'p3_sign': True, 'all_agree': False}

## Honesty notes

- P1 is a MODELED replay (SS-B exit shape on real OPRA bars), not a live fill -- absolute dollars are QTY=10 research-scale, not account-size absolute.
- P2 is MEASURED (real broker fills) but n~113 spans multiple arms/risk-tiers pooled together per the pre-reg's population definition; not stratified by arm here.
- P3's alignment reconstruction is MODELED (no live context-bundle existed at those April/May 2026 trade times) even though j_pnl itself is MEASURED.
- This pre-reg's scope ends at 'does it correlate' -- a SUPPORTED verdict does NOT itself change any live behavior (OP-0 #1 / OP-16 eval-first gate). It only qualifies a separately pre-registered Phase 2 proposal for HOW the tag would be consumed.
- **Build-time observation (disclosed, not a re-pick):** buckets 0/+2/-2 are EMPTY in every population's table above. Root cause verified directly (sampled 60 P1 alignment reads): `analyze_structure`'s per-timeframe classifier essentially never returns 'range'/'unknown' on SPY daily/hourly/15m history in this window -- every timeframe read was 'uptrend' or 'downtrend', never a 0-vote. `alignment_score` is therefore structurally odd-valued ({-3,-1,+1,+3}), not the full [-3,+3] the pre-reg's bucket range anticipated. This does not change any scoring/kill-criteria logic (all bucket math already handles n=0 buckets correctly) -- disclosed because it means this study's effective resolution is 4 buckets, not 7, a fact worth carrying into any Phase 2 design.
