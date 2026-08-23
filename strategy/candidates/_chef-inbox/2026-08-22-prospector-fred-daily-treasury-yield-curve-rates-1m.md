# Chef Inbox — FRED Daily Treasury Yield Curve Rates (1‑Month to 30‑Year)

**Routed by:** Gamma_Prospector 2026-08-22
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: FRED Daily Treasury Yield Curve Rates (1‑Month to 30‑Year) -- Shifts in short‑term Treasury yields affect risk‑free rates and implied volatility, refining option pricing models. Data source: Federal Reserve Economic Data API (https://fred.stlouisfed.org/docs/api/fred/). Cost: $0. Instrument fit: both.

## Research Question for Chef
FRED Daily Treasury Yield Curve Rates (1‑Month to 30‑Year) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Federal Reserve Economic Data API (https://fred.stlouisfed.org/docs/api/fred/)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:fred-daily-treasury-yield-curve-rates-1m) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
