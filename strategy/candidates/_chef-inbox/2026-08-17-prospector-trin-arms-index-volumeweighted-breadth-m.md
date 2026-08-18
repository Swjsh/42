# Chef Inbox — TRIN (Arms Index) – volume‑weighted breadth measure

**Routed by:** Gamma_Prospector 2026-08-17
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:openai/gpt-oss-20b:free

## The Finding
Prospector beat `microstructure_internals` surfaced: TRIN (Arms Index) – volume‑weighted breadth measure -- TRIN combines volume, advancing/declining stock counts, and price change to flag bullish or bearish momentum that can be used to time 0‑DTE option entries or mes exits. Data source: Barchart TRIN Index (symbol: TRIN) via Barchart.com API. Cost: paid. Instrument fit: both.

## Research Question for Chef
TRIN (Arms Index) – volume‑weighted breadth measure -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Barchart TRIN Index (symbol: TRIN) via Barchart.com API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:trin-arms-index-volumeweighted-breadth-m) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
