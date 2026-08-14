# Chef Inbox — U.S. Treasury Daily Treasury Yield Curve rates

**Routed by:** Gamma_Prospector 2026-08-13
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `data_feeds_free` surfaced: U.S. Treasury Daily Treasury Yield Curve rates -- Yield‑curve shifts affect interest‑rate sensitive futures (MES/MNQ) and equity indices intraday. Data source: U.S. Treasury Daily Treasury Yield Curve API https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve. Cost: $0. Instrument fit: both.

## Research Question for Chef
U.S. Treasury Daily Treasury Yield Curve rates -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: U.S. Treasury Daily Treasury Yield Curve API https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:us-treasury-daily-treasury-yield-curve-r) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
