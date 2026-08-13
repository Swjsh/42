# Chef Inbox — TRIN (Arms Index) = (Advancing Issues / Declining Issues) / (Advancing

**Routed by:** Gamma_Prospector 2026-08-13
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `microstructure_internals` surfaced: TRIN (Arms Index) = (Advancing Issues / Declining Issues) / (Advancing Volume / Declining Volume) -- TRIN below 0.7 indicates overbought conditions and above 1.3 indicates oversold, offering intraday overbought/oversold signals for SPY options and MES futures. Data source: Derived from NYSE advance/decline and volume data; available as real-time TRIN ticker ^TRIN on platforms like Thinkorswim, TradeStation, or via Polygon.io. Cost: paid. Instrument fit: both.

## Research Question for Chef
TRIN (Arms Index) = (Advancing Issues / Declining Issues) / (Advancing Volume / Declining Volume) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Derived from NYSE advance/decline and volume data; available as real-time TRIN ticker ^TRIN on platforms like Thinkorswim, TradeStation, or via Polygon.io
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:trin-arms-index-advancing-issues-declini) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
