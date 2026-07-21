# Chef Inbox — Treasury Treasury-Bills (3-Month) yield fluctuations

**Routed by:** Gamma_Prospector 2026-07-10
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:google/gemma-4-31b-it:free

## The Finding
Prospector beat `data_feeds_free` surfaced: Treasury Treasury-Bills (3-Month) yield fluctuations -- Provides a proxy for the 'risk-free' rate and immediate liquidity stress, affecting 0DTE option pricing and delta hedging speed. Data source: FRED API (Series: DGS3MO). Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
Treasury Treasury-Bills (3-Month) yield fluctuations -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: FRED API (Series: DGS3MO)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:treasury-treasury-bills-3-month-yield-fl) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
