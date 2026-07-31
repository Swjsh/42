# Chef Inbox — Front‑month WTI crude oil price (CL=F) as a commodity‑linked leading i

**Routed by:** Gamma_Prospector 2026-07-31
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `cross_asset_signals` surfaced: Front‑month WTI crude oil price (CL=F) as a commodity‑linked leading indicator for equity indices -- Sharp drops in oil prices reflect weakening global demand and inflation concerns, often coinciding with risk‑off equity moves; rallies suggest reflationary optimism and equity support. Data source: CME WTI Crude Oil front‑month futures ticker CL=F (or CL1!), available free via Quandl (CHRIS/CME_CL1) or Yahoo Finance. Cost: $0. Instrument fit: both.

## Research Question for Chef
Front‑month WTI crude oil price (CL=F) as a commodity‑linked leading indicator for equity indices -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CME WTI Crude Oil front‑month futures ticker CL=F (or CL1!), available free via Quandl (CHRIS/CME_CL1) or Yahoo Finance
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:frontmonth-wti-crude-oil-price-clf-as-a-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
