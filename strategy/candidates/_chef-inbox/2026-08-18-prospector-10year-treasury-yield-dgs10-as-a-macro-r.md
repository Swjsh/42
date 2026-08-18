# Chef Inbox — 10‑Year Treasury Yield (DGS10) as a macro risk indicator

**Routed by:** Gamma_Prospector 2026-08-18
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: 10‑Year Treasury Yield (DGS10) as a macro risk indicator -- Rising yields often precede equity pullbacks, giving early warning for 0DTE SPY and MES directional bias. Data source: Federal Reserve Economic Data (FRED) API, series DGS10 (https://fred.stlouisfed.org/series/DGS10). Cost: $0. Instrument fit: both.

## Research Question for Chef
10‑Year Treasury Yield (DGS10) as a macro risk indicator -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) API, series DGS10 (https://fred.stlouisfed.org/series/DGS10)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:10year-treasury-yield-dgs10-as-a-macro-r) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
