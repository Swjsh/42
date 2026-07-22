# Chef Inbox — CBOE BuyWrite Index (BXM) real-time levels and volatility skew

**Routed by:** Gamma_Prospector 2026-07-10
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:qwen/qwen3-next-80b-a3b-instruct:free

## The Finding
Prospector beat `data_feeds_free` surfaced: CBOE BuyWrite Index (BXM) real-time levels and volatility skew -- BXM reflects covered-call writing pressure, which correlates with institutional SPY option flow and can signal short-term volatility compression or expansion ahead of expiry. Data source: CBOE BXM Index, https://www.cboe.com/tradable_products/bxm/. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
CBOE BuyWrite Index (BXM) real-time levels and volatility skew -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE BXM Index, https://www.cboe.com/tradable_products/bxm/
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:cboe-buywrite-index-bxm-real-time-levels) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- DONE 2026-07-22T04:xx conductor (AFTERHOURS): screened, see leaderboard row 50 +
analysis/recommendations/bxm-gate-feasibility-2026-07-22.json. BXM's raw level is
non-stationary/SPX-trending (unlike VIX, not a vol level) so a level-band gate was the
wrong shape for the literal ask -- adapted (disclosed, not silent, OP-20) to a 5-day
trailing annualized realized-vol-of-BXM-returns gate, median-split compressed/elevated,
against ALL real journal fills (n=190). NEITHER candidate clears the OP-11/16 bar
(compressed CONCENTRATED $18.42/tr, elevated DRY -$5.37/tr, neither walk-forward stable).
Free `^BXM` daily data confirmed available via yfinance for the full trade-history window
(backtest/data/bxm_daily_2026-04-01_2026-07-21.csv). Guard: test_bxm_gate_probe.py 4/4
PASS. NEEDS-MORE-DATA, not rejected -- re-run as the ledger grows. -->

