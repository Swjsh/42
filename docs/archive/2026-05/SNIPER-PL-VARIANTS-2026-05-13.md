# SNIPER Real-Fills — Profit-Lock Variants — T42

Generated: 2026-05-13T18:09:05.945921

## Hypothesis

T35 verdict was CAVEAT (4/4 measured days flipped from BS-winners to real-losses).
After T41 added profit-lock to `simulator_real.py`, hypothesis: profit-lock RESCUES
SNIPER the same way it rescued v14_enhanced (T44b verdict: 3/3 PASS).

## Results

| Variant | profit_lock_threshold / offset | total BS | total real | 4/29 J real | Verdict |
|---|---|---|---|---|---|
| control_pl_off | 0.00 / 0.05 | $+2717 | $-1725 | $-329 | **STILL_FAILS** |
| pl_05_off05 | 0.05 / 0.05 | $+2717 | $-1725 | $-329 | **STILL_FAILS** |
| pl_05_off08 | 0.05 / 0.08 | $+2717 | $-1725 | $-329 | **STILL_FAILS** |
| pl_10_off05 | 0.10 / 0.05 | $+2717 | $-1725 | $-329 | **STILL_FAILS** |
| pl_10_off08 | 0.10 / 0.08 | $+2717 | $-1725 | $-329 | **STILL_FAILS** |

## Per-day detail (each variant)

### control_pl_off (threshold=0.00, offset=0.05)

| Date | BS | Real | Diff% | Status |
|---|---:|---:|---:|---|
| 2025-04-07 | $+2357 | $-926 | -139.3% | MEASURED |
| 2026-04-29 | $+114 | $-329 | -389.5% | MEASURED |
| 2026-05-04 | $+120 | $-234 | -295.4% | MEASURED |
| 2026-05-05 | $+127 | $-236 | -286.5% | MEASURED |

### pl_05_off05 (threshold=0.05, offset=0.05)

| Date | BS | Real | Diff% | Status |
|---|---:|---:|---:|---|
| 2025-04-07 | $+2357 | $-926 | -139.3% | MEASURED |
| 2026-04-29 | $+114 | $-329 | -389.5% | MEASURED |
| 2026-05-04 | $+120 | $-234 | -295.4% | MEASURED |
| 2026-05-05 | $+127 | $-236 | -286.5% | MEASURED |

### pl_05_off08 (threshold=0.05, offset=0.08)

| Date | BS | Real | Diff% | Status |
|---|---:|---:|---:|---|
| 2025-04-07 | $+2357 | $-926 | -139.3% | MEASURED |
| 2026-04-29 | $+114 | $-329 | -389.5% | MEASURED |
| 2026-05-04 | $+120 | $-234 | -295.4% | MEASURED |
| 2026-05-05 | $+127 | $-236 | -286.5% | MEASURED |

### pl_10_off05 (threshold=0.10, offset=0.05)

| Date | BS | Real | Diff% | Status |
|---|---:|---:|---:|---|
| 2025-04-07 | $+2357 | $-926 | -139.3% | MEASURED |
| 2026-04-29 | $+114 | $-329 | -389.5% | MEASURED |
| 2026-05-04 | $+120 | $-234 | -295.4% | MEASURED |
| 2026-05-05 | $+127 | $-236 | -286.5% | MEASURED |

### pl_10_off08 (threshold=0.10, offset=0.08)

| Date | BS | Real | Diff% | Status |
|---|---:|---:|---:|---|
| 2025-04-07 | $+2357 | $-926 | -139.3% | MEASURED |
| 2026-04-29 | $+114 | $-329 | -389.5% | MEASURED |
| 2026-05-04 | $+120 | $-234 | -295.4% | MEASURED |
| 2026-05-05 | $+127 | $-236 | -286.5% | MEASURED |
