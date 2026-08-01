# Chef Inbox — FRED macroeconomic indicators (e.g., Initial Jobless Claims, ISM Manuf

**Routed by:** Gamma_Prospector 2026-08-01
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `data_feeds_free` surfaced: FRED macroeconomic indicators (e.g., Initial Jobless Claims, ISM Manufacturing PMI) via the FRED API -- Provides leading economic news that drives intraday SPY and futures volatility, allowing the model to anticipate macro‑shock moves. Data source: Federal Reserve Economic Data (FRED) API – https://fred.stlouisfed.org/docs/api/fred/. Cost: $0. Instrument fit: both.

## Research Question for Chef
FRED macroeconomic indicators (e.g., Initial Jobless Claims, ISM Manufacturing PMI) via the FRED API -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) API – https://fred.stlouisfed.org/docs/api/fred/
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:fred-macroeconomic-indicators-eg-initial) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
