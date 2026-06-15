# Confidence Formula Recalibration — 16-mo per-detector analysis (DRAFT)

> Date: 2026-05-18 evening (cycle 7)
> Run: `python backtest/autoresearch/confidence_recalibration.py`
> Per OP-25 engine-benefit autonomy (analysis only — does NOT modify detectors)

## TL;DR — surprise finding

The "0.60-0.70 sweet spot beats 0.80+" anomaly was **NOT a system-wide problem.** It was almost entirely a `double_bottom` artifact (32% of the sample). The other 6 detectors are correctly weighted — high confidence does correlate with high WR.

## Per-detector verdict (16-mo, 5,118 graded hits)

| Detector | n graded | 0.60-0.70 WR | 0.80+ WR | Verdict |
|---|---:|---:|---:|---|
| `double_bottom` | 1646 | **56.3%** | 52.2% | **MISTUNED** — high conf is worse than mid conf |
| `double_top` | 1225 | 45.6% | **49.1%** | OK (high conf wins) |
| `failed_breakdown_wick` | 298 | 53.1% | **57.9%** | OK |
| `rejection_at_level_bearish` | 205 | 51.0% | **66.7%** (n=9) | OK (small high-band n) |
| `momentum_acceleration` | 332 | 40.3% | **56.2%** | OK (huge ranking gap +16pp) |
| `head_and_shoulders_top` | 283 | 50.0% | **54.9%** | OK |
| `inside_bar_consolidation` | 0 | n/a | n/a | n/a (neutral bias never graded) |

## Why the cross-detector aggregate was misleading

Last cycle's confidence_band_wr (across all detectors):
```
<0.60       n=271   WR=47.6%
0.60-0.70   n=1043  WR=51.0%   <-- "sweet spot"
0.70-0.80   n=833   WR=48.5%
0.80+       n=229   WR=49.3%
```

That was 5118 hits pooled — double_bottom alone has 1646 (32%). Its MISTUNED pattern (high-conf < mid-conf) dragged the cross-detector aggregate to look like all detectors had the same problem. They don't.

## What's wrong with double_bottom's confidence formula

The 3 factors currently feeding confidence:
- `separation_pct` (between the two lows) — **SNR 0.04, NOT predictive**
- `neckline_rise_pct` (height of neckline above lows) — **SNR 0.78, NOT predictive**
- `bars_between` (gap between the two lows) — **SNR 0.51, NOT predictive**

None of these distinguish winning from losing double bottoms. So the more "confident" the formula says we are, the LESS it correlates with actual outcomes.

## Draft recommendation for double_bottom (DRAFT, not yet applied)

**Down-weight** the 3 current factors to ~equal small weights. **Add new candidate factors** from the hit's existing notes:

1. **`low2_volume_higher`** (bool) — Volume on second low > first. Already in notes. Often the "buyer stepping in" signal.
2. **`near_named_level`** — NEW field from Option D this evening. Could be a strong predictor (intuitive: double bottoms at PDL respect more often).
3. **`is_contra_trend`** — Already shown to give +5.5pp WR lift on double_bottom (5/18 16-mo findings).

These weren't included in confidence_recalibration's `FACTORS_PER_DETECTOR` analysis because the function only inspects native-notes numeric fields. Next-cycle work: extend the analyzer to test composite factors.

## What's well-tuned and stays as-is

- **double_top** uses `bars_between` (SNR 1.94, lower is better — bigger sample-size gap = stronger reversal) plus the other heuristics. Working.
- **failed_breakdown_wick** uses `close_back_margin_pct` (SNR 1.47, higher is better) — the deeper the reclaim, the cleaner the signal. Working.
- **momentum_acceleration** uses `range_mult` (SNR 1.09, higher is better) — wider bars are higher-conviction. Working.
- **rejection_at_level_bearish** + **head_and_shoulders_top** — confidence ranking matches WR ranking; keep as-is.

## What ships from this cycle

1. **`backtest/autoresearch/confidence_recalibration.py`** — per-detector factor analyzer. Re-runnable any time `pattern_backtest` produces new data.
2. **`analysis/confidence-recalibration-{ts}.json`** — full per-factor SNR + band breakdown.
3. **This DRAFT doc** — no production change. The detector confidence formulas in `crypto/lib/chart_patterns.py` are UNCHANGED.

## Why we ship the analysis but not the fix this cycle

Per OP-25: engine-benefit infrastructure (the analyzer) ships freely. But **changing the confidence formula in `crypto/lib/chart_patterns.py` is a primitive-level change** that affects:
- `pattern_backtest` analytical output
- `numeric_pulse` alert filtering (the `conf >= 0.65` gate)
- `fast_path_executor` decision filtering

So the formula change needs:
1. Validation: re-run 16-mo backtest with new formula → does WR ranking now go conf-up = WR-up?
2. Forward-compat: ensure existing alert thresholds (0.65) still cluster the highest-WR hits
3. v22 gym validator update to lock in new formula

That's a multi-cycle project. Tonight ships the analysis; next cycle implements the double_bottom recalibration + validates it.

## Next-cycle queue (post-this)

1. **Implement double_bottom confidence v2** — replace the 3 non-predictive factors with `low2_volume_higher` (boolean), `near_named_level` (boolean), `is_contra_trend` (boolean). Each contributes +0.05 to base 0.40, max conf 0.55 with all three. Re-run 16-mo backtest.
2. **Compare DBC v1 vs v2** WR-by-band. If v2 shows high-conf correlates with high-WR, ship to chart_patterns.py + bump v22 test count.
3. **Then move on to**: stale-lock-day-reset (item 6 from queue).
