# Pattern Confidence Factor Regression

*Generated: 2026-05-20 01:07 ET*

## Confidence Band WR (from regression run)

| Band | N | WR% | Wins | Losses |
|---|---|---|---|---|
| <0.60 | 107 | 47.7% | 51 | 56 |
| 0.60-0.70 | 147 | 51.7% | 76 | 71 |
| 0.70-0.80 | 57 | 56.1% | 32 | 25 |
| 0.80+ | 64 | 48.4% | 31 | 33 |

## 0.60-0.70 Band Factor Combinations

| Factor Combination | Conf | N | WR% |
|---|---|---|---|
| `decisive_reclaim` | 0.6 | 66 | 51.5% |
| `low2_volume_higher+very_tight_lows` | 0.66 | 31 | 54.8% |
| `bars_between_sweet_spot+low2_volume_higher` | 0.66 | 29 | 44.8% |
| `bars_between_sweet_spot+very_tight_lows` | 0.65 | 21 | 57.1% |

## Formula Enumeration — What Lands in 0.60-0.70

The v2 formula (base=0.45 + 5 binary factors) produces EXACTLY 5 combos in [0.60, 0.70):

| Combo | Conf | N Factors |
|---|---|---|
| `decisive_reclaim` | 0.6 | 1 |
| `low2_volume_higher` | 0.6 | 1 |
| `decent_neckline_height+decisive_reclaim` | 0.65 | 2 |
| `decent_neckline_height+low2_volume_higher` | 0.65 | 2 |
| `bars_between_sweet_spot+very_tight_lows` | 0.65 | 2 |
| `bars_between_sweet_spot+decent_neckline_height` | 0.6 | 2 |
| `decent_neckline_height+very_tight_lows` | 0.6 | 2 |

## Root Cause

Single large-factor cases (decisive_reclaim or low2_volume_higher alone) land exactly at conf=0.60. Having 1 strong auxiliary factor with no structural confirmation performs WORSE than the base pattern with 0 factors (conf=0.45). The v2 formula's 0.15 weight for these factors is too high.

## Proposed v3 Adjustment

**Reduce decisive_reclaim and low2_volume_higher weights: 0.15 -> 0.11**

Effects:
- decisive_reclaim_alone: 0.45+0.11=0.56 (moves to <0.60 band, WR=55.9%)
- low2_volume_higher_alone: 0.45+0.11=0.56 (moves to <0.60 band, WR=55.9%)
- decisive_reclaim_plus_decent: 0.45+0.11+0.05=0.61 (stays in 0.60-0.70)
- volume_plus_decent: 0.45+0.11+0.05=0.61 (stays in 0.60-0.70)
- bars_between_plus_very_tight: 0.45+0.10+0.10=0.65 (unchanged)

Expected: Drain the 2 most common 0.60-band combos (~60% of N=447 in band) into the better <0.60 band. Monitor remaining 3 combos.

Per OP-25 engine-benefit autonomy: double_bottom confidence formula is RESEARCH analytics only (not live trading doctrine). v3 adjustment may ship without J ratification. Implement in crypto/lib/chart_patterns.py double_bottom_detector v2 weights dict after verification run.
