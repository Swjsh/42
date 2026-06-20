# Walk-forward validation — 2026-05-10T16:50:56.009809

**Train:** 2025-01-01 to 2025-12-31  (engine optimized HERE)
**Test:**  2026-01-01 to 2026-05-07  (TRULY out-of-sample — never seen by optimizer)

**Verdict:** monday_ready

| Stage | Train P&L | Train $/mo | Test P&L | Test $/mo | Ratio (per-month) | Monday ready |
|---|---|---|---|---|---|---|
| stage3 | $7122 (12mo) | $593/mo | $2066 (4.3mo) | $480/mo | 0.81x | ✅ |
| stage3 | $6771 (12mo) | $564/mo | $2432 (4.3mo) | $566/mo | 1.00x | ✅ |
| stage3 | $6603 (12mo) | $550/mo | $2028 (4.3mo) | $472/mo | 0.86x | ✅ |
| stage2 | $6600 (12mo) | $550/mo | $2657 (4.3mo) | $618/mo | 1.12x | ✅ |
| stage3 | $6174 (12mo) | $515/mo | $2055 (4.3mo) | $478/mo | 0.93x | ✅ |

## Interpretation (per-month normalized — the HONEST metric)

- **Per-month ratio > 0.7x** = strategy generalizes well to OOS data
- **Per-month ratio 0.5-0.7x** = mild overfit, still trade-worthy
- **Per-month ratio < 0.5x** = serious overfit (DO NOT trade)
- **Test P&L < 0** = strategy fails out-of-sample (DO NOT trade)

Note: original total-P&L ratio (test/train) was misleading because train=12mo and test=4.3mo (naive ratio compares dollars not rate).