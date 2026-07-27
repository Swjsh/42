# Chef Inbox — Arms Index (TRIN) – Advance/Decline Ratio with volume weighting

**Routed by:** Gamma_Prospector 2026-07-27
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `microstructure_internals` surfaced: Arms Index (TRIN) – Advance/Decline Ratio with volume weighting -- Combines market breadth and volume to gauge whether a rally is supported by broad participation or is fragile, useful for both SPY options and futures. Data source: NASDAQ Data Link (formerly Quandl) dataset "NASDAQ/AD" which provides TRIN values. Cost: $0. Instrument fit: both.

## Research Question for Chef
Arms Index (TRIN) – Advance/Decline Ratio with volume weighting -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: NASDAQ Data Link (formerly Quandl) dataset "NASDAQ/AD" which provides TRIN values
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:arms-index-trin-advancedecline-ratio-wit) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
