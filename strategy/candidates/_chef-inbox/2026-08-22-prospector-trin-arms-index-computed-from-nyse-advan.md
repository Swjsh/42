# Chef Inbox — TRIN (Arms Index) computed from NYSE advancing/declining issues and vo

**Routed by:** Gamma_Prospector 2026-08-22
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `microstructure_internals` surfaced: TRIN (Arms Index) computed from NYSE advancing/declining issues and volume -- TRIN < 0.7 signals overbought conditions and potential short-term pullback in SPY/ES; > 1.0 signals oversold and bounce. Data source: NYSE publishes TRIN daily for free; minute-level data available via Tiingo or TradingView. Cost: $0. Instrument fit: both.

## Research Question for Chef
TRIN (Arms Index) computed from NYSE advancing/declining issues and volume -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: NYSE publishes TRIN daily for free; minute-level data available via Tiingo or TradingView
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:trin-arms-index-computed-from-nyse-advan) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
