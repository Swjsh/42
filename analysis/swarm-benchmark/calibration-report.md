# SWARM Confidence Calibration Report

> Generated: 2026-05-17T20:20Z | N=62 days graded
> ECE: 24.28% | Overall accuracy: 61.5%

---

## Summary

- **Days graded:** 62 (52 tradeable, 10 abstain/choppy)
- **Overall direction accuracy:** 61.5%
- **Expected Calibration Error (ECE):** 24.28%
  - ECE < 5% = well-calibrated | ECE 5-15% = moderate miscalibration | ECE > 15% = severe

## Confidence Inflation

- **Max conf value used:** 95
- **Days at max conf:** 10 (19.2% of all days)
- **Interpretation:** mild inflation (<25%)

The synthesis agent assigns maximum confidence on too many days. A well-calibrated
model should reserve max confidence for rare, very-clear-signal days (<15% of days).

**Fix:** In `automation/swarm/prompts/synthesis_cio.md`, add explicit scoring guidance:
- conf=95: all 4 specialists agree + macro confirms + no dissent from validator
- conf=75: 3 of 4 agree + macro neutral
- conf=50: 2 of 4 agree OR meaningful dissent
- conf=25: majority split OR macro contradicts technicals

## Per-Confidence-Value Accuracy

| swarm_conf | Days | Correct | Wrong | Actual % | Expected % | Gap |
|------------|------|---------|-------|----------|------------|-----|
| 14 | 1 | 1 | 0 | 100.0% | 14% | +86.0% |
| 15 | 1 | 0 | 1 | 0.0% | 15% | -15.0% |
| 16 | 1 | 1 | 0 | 100.0% | 16% | +84.0% |
| 25 | 5 | 2 | 3 | 40.0% | 25% | +15.0% |
| 31 | 1 | 0 | 1 | 0.0% | 31% | -31.0% |
| 35 | 1 | 1 | 0 | 100.0% | 35% | +65.0% |
| 36 | 1 | 0 | 1 | 0.0% | 36% | -36.0% |
| 50 | 2 | 2 | 0 | 100.0% | 50% | +50.0% |
| 55 | 1 | 1 | 0 | 100.0% | 55% | +45.0% |
| 57 | 1 | 1 | 0 | 100.0% | 57% | +43.0% |
| 60 | 1 | 1 | 0 | 100.0% | 60% | +40.0% |
| 61 | 2 | 2 | 0 | 100.0% | 61% | +39.0% |
| 65 | 1 | 1 | 0 | 100.0% | 65% | +35.0% |
| 68 | 1 | 0 | 1 | 0.0% | 68% | -68.0% |
| 70 | 1 | 0 | 1 | 0.0% | 70% | -70.0% |
| 75 | 1 | 0 | 1 | 0.0% | 75% | -75.0% |
| 76 | 7 | 5 | 2 | 71.4% | 76% | -4.6% |
| 82 | 3 | 1 | 2 | 33.3% | 82% | -48.7% |
| 83 | 2 | 1 | 1 | 50.0% | 83% | -33.0% |
| 88 | 8 | 5 | 3 | 62.5% | 88% | -25.5% |
| 95 | 10 | 7 | 3 | 70.0% | 95% | -25.0% |

## Bucket Analysis

| Bucket | Days | Accuracy | Expected | Gap |
|--------|------|----------|----------|-----|
| low (0-39) | 11 | 45.5% | 19.5% | +26.0% |
| medium (40-59) | 4 | 100.0% | 49.5% | +50.5% |
| high (60-74) | 6 | 66.7% | 67.0% | -0.3% |
| very_high (75-89) | 21 | 57.1% | 82.0% | -24.9% |
| max (90-100) | 10 | 70.0% | 95.0% | -25.0% |

## Direction Bias

- Bullish days: 29 → accuracy: 69.0%
- Bearish days: 23 → accuracy: 52.2%

## Signal Thresholds (trading recommendations)

- **conf >= 95:** observed 70.0% accuracy (10 days) → use as strong signal

## Actionable Synthesis Agent Prompt Updates

Based on this calibration, the synthesis agent's confidence rubric needs tightening.
File: `automation/swarm/prompts/synthesis_cio.md`

**Current problem:** swarm assigns conf=95 on too many days; actual accuracy on
those days is only ~70.0%.

**Proposed rubric update (add to synthesis prompt):**

```
CONFIDENCE CALIBRATION RULES (mandatory):
- conf >= 90: ALL of the following must be true:
  * 4/4 specialists agree on direction
  * Macro calendar: no event within 24h (or event is in-line with direction)
  * Validator's devil-advocate found NO structural flaw
  * Technical agent shows EMA ribbon + VWAP + level ALL aligned
  * Reserve this level for <15% of days
- conf 70-89: 3 of 4 specialists agree, macro neutral or aligned
- conf 50-69: 2 of 4 agree OR one meaningful structural concern
- conf 25-49: Mixed signals or clear structural risk
- conf < 25: Use only for near-certain fades or no-trade bias
```

*Report generated 2026-05-17T20:20Z. Re-run after mega-batch completes (~60+ days) for stable estimates.*