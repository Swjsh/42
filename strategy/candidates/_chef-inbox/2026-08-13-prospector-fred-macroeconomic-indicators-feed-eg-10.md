# Chef Inbox — FRED macroeconomic indicators feed (e.g., 10‑year Treasury yield, init

**Routed by:** Gamma_Prospector 2026-08-13
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `data_feeds_free` surfaced: FRED macroeconomic indicators feed (e.g., 10‑year Treasury yield, initial jobless claims) -- Real‑time macro shocks drive intraday SPY/MES moves, giving a leading edge for 0DTE options and futures. Data source: Federal Reserve Economic Data (FRED) API https://fred.stlouisfed.org/docs/api/fred/. Cost: $0. Instrument fit: both.

## Research Question for Chef
FRED macroeconomic indicators feed (e.g., 10‑year Treasury yield, initial jobless claims) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) API https://fred.stlouisfed.org/docs/api/fred/
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:fred-macroeconomic-indicators-feed-eg-10) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
