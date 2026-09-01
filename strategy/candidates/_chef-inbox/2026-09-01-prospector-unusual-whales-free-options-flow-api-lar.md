# Chef Inbox — Unusual Whales free options flow API (large trades filter)

**Routed by:** Gamma_Prospector 2026-09-01
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: Unusual Whales free options flow API (large trades filter) -- Aggregates reported large block trades and sweeps, revealing early directional pressure that can be exploited for 0DTE SPY option entry/exit timing. Data source: Unusual Whales API (free tier), https://unusualwhales.com/api. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
Unusual Whales free options flow API (large trades filter) -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: Unusual Whales API (free tier), https://unusualwhales.com/api
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:unusual-whales-free-options-flow-api-lar) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
