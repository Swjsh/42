# Chef Inbox — FRED 10‑Year Treasury Constant Maturity Rate (DGS10) series

**Routed by:** Gamma_Prospector 2026-08-26
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: FRED 10‑Year Treasury Constant Maturity Rate (DGS10) series -- Movements in the 10‑year yield impact risk‑off sentiment and thus SPY volatility, especially on 0DTE expiry days. Data source: Federal Reserve Economic Data (FRED) API – https://fred.stlouisfed.org/series/DGS10. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
FRED 10‑Year Treasury Constant Maturity Rate (DGS10) series -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) API – https://fred.stlouisfed.org/series/DGS10
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:fred-10year-treasury-constant-maturity-r) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
