# Chef Inbox — Quiver Quant free unusual options activity feed

**Routed by:** Gamma_Prospector 2026-08-10
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `data_feeds_free` surfaced: Quiver Quant free unusual options activity feed -- Aggregates retail‑flow‑detected abnormal options volume/open‑interest changes, highlighting potential institutional positioning that precedes intraday moves in SPY 0DTE contracts. Data source: Quiver Quant API – /beta/live/optionsunusual endpoint (https://api.quiverquant.com/beta/live/optionsunusual). Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
Quiver Quant free unusual options activity feed -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: Quiver Quant API – /beta/live/optionsunusual endpoint (https://api.quiverquant.com/beta/live/optionsunusual)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:quiver-quant-free-unusual-options-activi) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
