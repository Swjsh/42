# Chef Inbox — U.S. Treasury Daily Yield Curve rates (e.g., 2‑yr, 10‑yr) from FRED

**Routed by:** Gamma_Prospector 2026-08-05
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: U.S. Treasury Daily Yield Curve rates (e.g., 2‑yr, 10‑yr) from FRED -- Rapid shifts in short‑term Treasury yields influence equity risk sentiment and can forecast intraday SPY moves. Data source: Federal Reserve Economic Data (FRED) series DGS2, DGS10 via https://fred.stlouisfed.org/. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
U.S. Treasury Daily Yield Curve rates (e.g., 2‑yr, 10‑yr) from FRED -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) series DGS2, DGS10 via https://fred.stlouisfed.org/
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:us-treasury-daily-yield-curve-rates-eg-2) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
