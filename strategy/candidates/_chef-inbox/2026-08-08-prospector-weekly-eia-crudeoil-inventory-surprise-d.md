# Chef Inbox — Weekly EIA crude‑oil inventory surprise delta

**Routed by:** Gamma_Prospector 2026-08-08
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `cross_asset_signals` surfaced: Weekly EIA crude‑oil inventory surprise delta -- Unexpected large builds or draws in U.S. crude inventories move risk sentiment and can flip SPY 0DTE direction and MES/MNQ trend within the same trading day. Data source: U.S. Energy Information Administration (EIA) Weekly Petroleum Status Report, CSV download from eia.gov. Cost: $0. Instrument fit: both.

## Research Question for Chef
Weekly EIA crude‑oil inventory surprise delta -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: U.S. Energy Information Administration (EIA) Weekly Petroleum Status Report, CSV download from eia.gov
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:weekly-eia-crudeoil-inventory-surprise-d) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none


<!-- NOTE 2026-08-22 ~04:xx ET conductor (WEEKEND, acting as chef, CHEF-INBOX-BACKLOG-DRAIN family-dedupe sweep): received 1 fold-in(s) from the same family, no new information -- 2026-08-21-prospector-us-crude-oil-inventory-changes-from-eia-.md -->
