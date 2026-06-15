# ORB VIX Regime Gate Analysis
Generated: 2026-05-21 03:49 ET

## Summary Table

| Scenario | N | WR% | P&L | Pos-Q | Q2-2026 N | Q2 Conc% |
|---|---|---|---|---|---|---|
| LONG_ALL | 274 | 69.3% | $+7,378 | 4/6 | 133 | 84.6% |
| LONG_VIX15 | 256 | 69.5% | $+6,855 | 4/6 | 133 | 91.1% |
| LONG_VIX18 | 126 | 69.0% | $+2,138 | 2/5 | 73 | 131.6% |
| LONG_VIX20 | 32 | 34.4% | $-620 | 0/3 | 0 | -0.0% |
| LONG_VIX22 | 18 | 16.7% | $-706 | 0/2 | 0 | -0.0% |
| LONG_VIX25 | 6 | 0.0% | $-438 | 0/2 | 0 | -0.0% |

## Per-Quarter Breakdown (LONG_ALL vs LONG_VIX20)

| Quarter | ALL N | ALL P&L | VIX20 N | VIX20 P&L |
|---|---|---|---|---|
| 2025-Q1 | 12 | $-766 | 0 | $+0 |
| 2025-Q2 | 42 | $+317 | 21 | $-300 |
| 2025-Q3 | 57 | $+1,650 | 0 | $+0 |
| 2025-Q4 | 17 | $+43 | 3 | $-231 |
| 2026-Q1 | 13 | $-110 | 8 | $-88 |
| 2026-Q2 | 133 | $+6,245 | 0 | $+0 |

## OP-20 Disclosure

- **account_size:** $1K paper (qty=3, ~$30-60 per trade at ATM option premiums)
- **sample_bias:** 391 obs from replay — watcher-based grading, not production fills
- **oos_test:** No walk-forward yet — pending if VIX gate shows promise
- **real_fills:** Not run — watcher grading uses fixed premium model
- **failure_modes:** VIX threshold may not generalize to future high-vol regimes. If VIX reverts to <20, ORB signals would be suppressed entirely.
- **concentration:** Q2-2026 concentration in LONG_ALL = ~85%. Best VIX gate Q2 concentration: -0.0%