# T2 — Entry/Exit Diagnostics (full OPRA ribbon_ride signal population)

**250 unique signals** priced across the OTM-3..ITM-2 ladder = **1451 positions** (ground rule 8: effective-n honesty). Window 2025-01-01..2026-06-18. FRICTIONLESS entry (bar open, no spread); 5-min OPRA bars; ribbon_ride only (ground rule 11). Same-5min-bar -S/+T ties ordered STOP-FIRST.

## Per-band noise floor (the priors that parameterize T3/T4)

| band | n | med entry | MAE 5m (med/worst-q) | MAE 10m (med/worst-q) | MFE EOD (med/p75) | −20% stop = ticks | spread proxy |
|---|--:|--:|--:|--:|--:|--:|--:|
| <0.20 | 189 | $0.10 | -20% / -33% | -29% / -43% | 56% / 233% | 2.0 | 42% |
| 0.20-0.50 | 247 | $0.33 | -17% / -26% | -24% / -35% | 100% / 284% | 6.6 | 34% |
| 0.50-1.00 | 321 | $0.73 | -14% / -26% | -22% / -32% | 97% / 234% | 14.6 | 33% |
| >1.00 | 694 | $1.75 | -10% / -20% | -15% / -27% | 71% / 141% | 35.0 | 25% |

**Reading:** `worst-q` = the 25th percentile of the signed MAE distribution — the DEEP tail (25% of signals draw down at least this much). This is the number that parameterizes stops: a stop shallower than worst-q gets harvested on 1-in-4 signals by noise alone. Where `−20% stop = ticks` is ≲3 and the spread proxy is a large % of premium, a −20% stop sits INSIDE the spread/noise (defect #1). Where MAE 10m median is deeper than a candidate stop, that stop is inside the MEDIAN noise floor (defect #3).

## Stop-harvest matrix — P(touch −S before +T | reached +T)

For each band: among signals that EVER reach +T, the fraction that first touch −S at/before the +T bar (i.e. a −S stop would harvest them out of an eventual +T winner). A high number = the stop is too tight for that target in that band.

### band <0.20  (n=189, med premium $0.10)

| target | reach% | −10% | −15% | −20% | −25% | −30% | −35% | −40% | −50% |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| +15% | 81% (153) | 78% | 61% | 56% | 48% | 38% | 29% | 26% | 18% |
| +25% | 72% (137) | 78% | 64% | 60% | 53% | 43% | 35% | 29% | 21% |
| +30% | 68% (129) | 78% | 66% | 61% | 54% | 45% | 36% | 31% | 22% |
| +50% | 58% (110) | 79% | 66% | 61% | 58% | 49% | 40% | 36% | 26% |
| +75% | 47% (88) | 80% | 65% | 59% | 57% | 50% | 39% | 36% | 25% |
| +100% | 42% (79) | 82% | 68% | 62% | 60% | 52% | 39% | 37% | 24% |
| +150% | 33% (63) | 86% | 70% | 62% | 59% | 51% | 40% | 36% | 27% |

### band 0.20-0.50  (n=247, med premium $0.33)

| target | reach% | −10% | −15% | −20% | −25% | −30% | −35% | −40% | −50% |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| +15% | 87% (215) | 67% | 57% | 45% | 39% | 28% | 26% | 17% | 11% |
| +25% | 83% (205) | 71% | 65% | 55% | 48% | 38% | 35% | 25% | 18% |
| +30% | 81% (200) | 74% | 67% | 58% | 50% | 42% | 38% | 30% | 22% |
| +50% | 72% (178) | 74% | 67% | 59% | 55% | 46% | 42% | 36% | 26% |
| +75% | 56% (137) | 74% | 69% | 59% | 55% | 45% | 39% | 34% | 25% |
| +100% | 51% (125) | 77% | 72% | 62% | 58% | 47% | 42% | 36% | 24% |
| +150% | 40% (100) | 77% | 71% | 62% | 59% | 47% | 39% | 34% | 23% |

### band 0.50-1.00  (n=321, med premium $0.73)

| target | reach% | −10% | −15% | −20% | −25% | −30% | −35% | −40% | −50% |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| +15% | 90% (290) | 66% | 51% | 45% | 36% | 29% | 21% | 17% | 10% |
| +25% | 84% (271) | 69% | 58% | 54% | 45% | 36% | 28% | 23% | 17% |
| +30% | 82% (262) | 70% | 59% | 55% | 48% | 38% | 29% | 24% | 17% |
| +50% | 70% (226) | 72% | 61% | 56% | 48% | 38% | 33% | 27% | 19% |
| +75% | 57% (184) | 78% | 69% | 62% | 54% | 44% | 37% | 33% | 22% |
| +100% | 49% (156) | 76% | 68% | 62% | 56% | 44% | 38% | 35% | 22% |
| +150% | 40% (128) | 77% | 67% | 60% | 54% | 44% | 38% | 35% | 25% |

### band >1.00  (n=694, med premium $1.75)

| target | reach% | −10% | −15% | −20% | −25% | −30% | −35% | −40% | −50% |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| +15% | 86% (600) | 58% | 46% | 36% | 28% | 21% | 16% | 13% | 8% |
| +25% | 79% (550) | 64% | 55% | 44% | 36% | 29% | 23% | 18% | 12% |
| +30% | 77% (533) | 66% | 56% | 46% | 39% | 32% | 26% | 21% | 14% |
| +50% | 61% (424) | 72% | 61% | 52% | 44% | 37% | 31% | 26% | 17% |
| +75% | 48% (332) | 74% | 62% | 56% | 47% | 42% | 36% | 30% | 19% |
| +100% | 38% (261) | 75% | 64% | 58% | 49% | 43% | 38% | 31% | 22% |
| +150% | 22% (153) | 77% | 62% | 60% | 46% | 42% | 38% | 31% | 22% |

---
_Source: `backtest/tools/entry_exit_diagnostics.py` over real cached OPRA. Exploratory — priors for T3/T4, not a ratification. Regenerate to refresh._
