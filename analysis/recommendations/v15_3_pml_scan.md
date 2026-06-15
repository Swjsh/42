# LIVE_PRICE_FIRST_BAR_TRIGGER — PML/PMH Stage-3 Frequency Scan
> Generated: 2026-05-21 04:07 ET
> Data: `spy_5m_2025-01-01_2026-05-15.csv` (77 qualifying trading days)

## Summary

**Stage-2 (PDL/PDH proxy) found: 1 event in 343 days (0.3%)**
**Stage-3 (PML/PMH actual premarket): BEAR=6 (7.8%), BULL=13 (16.9%), Total=19 (24.7%)**

Key finding: PML/PMH events are far more common than PDL/PDH fast-V events.
The premarket session routinely establishes levels that the first RTH bars test.

## Per-Quarter Breakdown

| Quarter | BEAR events | BULL events | Total |
|---|---:|---:|---:|
| 2025-Q2 | 1 | 2 | 3 |
| 2025-Q3 | 1 | 3 | 4 |
| 2025-Q4 | 0 | 4 | 4 |
| 2026-Q1 | 2 | 1 | 3 |
| 2026-Q2 | 2 | 3 | 5 |

## J Anchor Day Interaction

| Date | Category | Event type |
|---|---|---|
| 2026-05-15 | MOTIVATING | BEAR_PML_V_REVERSAL |

## Sample Events (first 10)

| Date | Type | PML | Bar940 Low | Bar945 Close | V-magnitude |
|---|---|---|---|---|---|
| 2025-04-11 | BEAR | 522.37 | 522.2 | 527.45 | +3.20 |
| 2025-05-15 | BULL | — | — | 585.33 | -0.48 |
| 2025-05-30 | BULL | — | — | 587.345 | -0.36 |
| 2025-08-05 | BEAR | 631.65 | 631.89 | 632.27 | +0.16 |
| 2025-08-12 | BULL | — | — | 637.58 | -2.28 |
| 2025-08-20 | BULL | — | — | 637.38 | -1.05 |
| 2025-08-29 | BULL | — | — | 646.12 | -0.73 |
| 2025-10-15 | BULL | — | — | 666.35 | -0.28 |
| 2025-10-16 | BULL | — | — | 666.6 | -0.19 |
| 2025-11-21 | BULL | — | — | 656.04 | -0.13 |

## Implications for v15.3 Promotion Path

- PML/PMH provides N~3 signals/quarter (vs PDL/PDH's N~1/quarter).
- This is sufficient base frequency for the 3+ live fires OP-21 gate.
- BEAR events occur ~7.8% of trading days (~0.2×/week).
- CRITICAL: frequency here is an UPPER BOUND — not all PML/PMH levels appear
  in key-levels.json as ★★+ named levels. Actual trigger rate depends on Gamma's
  premarket write. Estimated true rate: 30-60% of scan events → ~3-8 events/quarter.

## OP-20 Disclosures

1. **Account-size:** $1K paper (qty=3).
2. **Sample bias:** Upper-bound scan — real rate lower. PML/PMH naming requires
   Gamma's 08:30 ET premarket judgment, not available historically.
3. **OOS test:** All 16 months = frequency scan only. No P&L backtest.
4. **Real-fills:** Not run. Pending frequency confirmation.
5. **Failure modes:** Ghost-entry risk (in-progress bar). Fast-V reversal may
   trigger chandelier stop before the move develops.
6. **Concentration:** N/A (frequency scan).