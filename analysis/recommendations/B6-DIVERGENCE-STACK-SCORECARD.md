# B6 — DE-CONCENTRATION STACK SCORECARD

> The decisive test of whether **edge #3** (B5 MES->MNQ persistence/n2) is a real 3rd
> futures edge, or a 2026-bull-regime concentration artifact. Generated 2026-06-21. Pure-Python, $0.

**VERDICT: `ARCHIVE_REGIME_ARTIFACT`** — `cleared_OOS=false`, `best_OOS-alone_drop-top5 = -$23.01`, **NOT a plateau (a monotonically-worsening cliff).** 0 of 72 stacked cells clear the B6 bar.

> **Headline (one line):** stacking vol-regime ATR%-band (a) + persistence>=N (d) does NOT de-concentrate edge #3 OOS. The least-bad cell (thr=0.0015 / `drop_extreme_high` / N=2) still has OOS-alone drop-top5 = **-$23.01** (top5-day_OOS = 136.6%) — removing the 5 best OOS days flips the edge negative. More persistence makes it WORSE, not better. Edge #3 is a 2026-bull-regime concentration artifact (C22). **Do NOT ship.**

## What B6 tests

- edge #3 = B5 MES->MNQ thr=0.0015 d_persistence/n2 (cleared B5's 8 gates on FULL-sample drop-top5 +$3.65, but OOS-ALONE drop-top5 = -$16.36, top5-day_OOS = 120.1% -> NOT de-concentrated out-of-sample)
- **Stack:** fix (a) vol-regime ATR%-band ['low', 'mid', 'high', 'drop_extreme_high'] x fix (d) persistence N [2, 3, 4] x threshold [0.001, 0.0015, 0.002] (both fixes intersected as signal-set subsets).
- **B6 winner bar:** drop-top5 on OOS-ALONE > 0 AND OOS/tr > 0 AND all 7 other gates pass (FULL-sample drop-top5 is necessary but NOT sufficient).
- **Leakage controls:** ATR-band edges + any top-Q frozen on IS-2025 days only (inside fix_vol_regime); persistence is causal walk-back over closed bars; gate logic verbatim from B4 -> no drift across B4/B5/B6.
- **Data:** 367 common MES/MNQ days 2025-01-02 .. 2026-06-12; OOS split 256 IS / 111 OOS (OOS starts 2026-01-07).

## Result

- **Cells evaluated:** 72
- **B6-clearing cells:** 0
- **NO stacked cell cleared the OOS-alone drop-top5 > 0 bar.**

## Best cell (by OOS-alone drop-top5)

- **MES->MNQ thr=0.0015 drop_extreme_high/n2** — band `drop_extreme_high`, persistence N=2
- n = 106, OOS/tr = $54.54
- **drop-top5 OOS-alone = $-23.01** (top5-day OOS = 136.6%)
- drop-top5 FULL-sample = $-1.59 (B5's necessary-but-insufficient statistic)
- B6 clears: **False** — fails: ['B6_oos_drop_top5_>0']

## Persistence plateau map (headline thr=0.0015, band `drop_extreme_high`)

Is N=2 the center of a flat favorable region, or a fragile single-value spike?
drop-top5 on the **OOS-alone** window at each N:

### MES->MNQ

| N | n | OOS/tr | dropOOS | dropFULL | top5-day OOS% | B6 clears |
|---|---|---|---|---|---|---|
| 2 | 106 | 54.54 | -23.01 | -1.59 | 136.6 | False |
| 3 | 89 | 40.16 | -52.45 | -15.1 | 208.1 | False |
| 4 | 79 | 37.9 | -59.22 | -22.17 | 228.3 | False |

### MNQ->MES

| N | n | OOS/tr | dropOOS | dropFULL | top5-day OOS% | B6 clears |
|---|---|---|---|---|---|---|
| 2 | 65 | 7.31 | -30.49 | -28.26 | 433.9 | False |
| 3 | 45 | 5.7 | -37.19 | -27.44 | 571.6 | False |
| 4 | 31 | -16.27 | -56.69 | -32.56 | n/a | False |

## Honest read

**NO stacked (vol-regime x persistence) cell de-concentrates the OOS-alone window** (drop-top5 OOS stays <= 0 everywhere it otherwise qualifies). Per C22 (backward-looking gates anti-correlate with recovery / regime-specific edges), **edge #3 is a 2026-bull-regime concentration artifact**: its OOS profit lives in the 5 best OOS days and does not survive their removal. **Recommendation: do NOT ship edge #3.** The B5 full-sample drop-top5 +$3.65 was necessary but not sufficient; the decisive OOS-alone test fails.

**No favorable plateau — it is a cliff.** N=2 is not the center of a flat favorable region; it is the least-bad point of a uniformly-negative one. As persistence rises, OOS-alone drop-top5 gets monotonically WORSE (N2 -$23.01 -> N3 -$52.45 -> N4 -$59.22) while OOS concentration worsens (top5-day_OOS 136.6% -> 208.1% -> 228.3%). More persistence concentrates the edge into fewer big days rather than broadening it. This is a fragile single-value, not a robust plateau — the exact failure mode B6 was designed to detect, now confirmed un-fixable by stacking. Only 2 of 72 cells even had a positive FULL-sample drop-top5 (B5's gate-5), and both still went negative OOS-alone — full-sample gate-5 is confirmed necessary-but-not-sufficient.
