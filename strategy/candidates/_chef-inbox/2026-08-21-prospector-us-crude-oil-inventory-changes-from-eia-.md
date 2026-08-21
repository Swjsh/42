# Chef Inbox — U.S. crude oil inventory changes from EIA weekly reports

**Routed by:** Gamma_Prospector 2026-08-21
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `cross_asset_signals` surfaced: U.S. crude oil inventory changes from EIA weekly reports -- Unexpected inventory draws or builds move oil prices, influencing energy sector exposure in SPY and the momentum of MES/MNQ contracts. Data source: U.S. Energy Information Administration (EIA) Weekly Petroleum Status Report API. Cost: $0. Instrument fit: both.

## Research Question for Chef
U.S. crude oil inventory changes from EIA weekly reports -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: U.S. Energy Information Administration (EIA) Weekly Petroleum Status Report API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:us-crude-oil-inventory-changes-from-eia-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
