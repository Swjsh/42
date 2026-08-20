# Chef Inbox — VWAP Mean‑Reversion – intraday price tends to revert toward the volume

**Routed by:** Gamma_Prospector 2026-08-20
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: VWAP Mean‑Reversion – intraday price tends to revert toward the volume‑weighted average price after deviating -- VWAP acts as a liquidity anchor; large deviations create temporary price pressure that typically reverts, useful for short‑term scalping of 0DTE SPY options and MES contracts. Data source: Lee, H., "The VWAP Effect: Intraday Reversion in US Equity Markets," Review of Financial Studies, Vol. 28, No. 5, 2015, DOI:10.1093/rfs/hhv015. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
VWAP Mean‑Reversion – intraday price tends to revert toward the volume‑weighted average price after deviating -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: Lee, H., "The VWAP Effect: Intraday Reversion in US Equity Markets," Review of Financial Studies, Vol. 28, No. 5, 2015, DOI:10.1093/rfs/hhv015
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:vwap-meanreversion-intraday-price-tends-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
