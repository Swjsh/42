# Chef Inbox — Advance‑Decline line (ADD) – market breadth indicator

**Routed by:** Gamma_Prospector 2026-08-17
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:openai/gpt-oss-20b:free

## The Finding
Prospector beat `microstructure_internals` surfaced: Advance‑Decline line (ADD) – market breadth indicator -- The ADD ratio signals when a large number of stocks are advancing versus declining, which correlates with short‑term trend reversals that can guide mes/futures entries. Data source: Barchart Advance‑Decline Index (symbol: NYSE:ADD) via Barchart.com API. Cost: paid. Instrument fit: both.

## Research Question for Chef
Advance‑Decline line (ADD) – market breadth indicator -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Barchart Advance‑Decline Index (symbol: NYSE:ADD) via Barchart.com API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:advancedecline-line-add-market-breadth-i) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
