# Chef Inbox — Volume Profile Visible Range (VPVR) – shows volume distribution across

**Routed by:** Gamma_Prospector 2026-07-11
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Volume Profile Visible Range (VPVR) – shows volume distribution across price levels within the visible chart window -- Highlights high-volume nodes acting as magnet support/resistance, revealing institutional interest not captured by price-only indicators. Data source: TradingView built-in Volume Profile indicator (accessible via Indicators → Volume Profile). Cost: $0. Instrument fit: both.

## Research Question for Chef
Volume Profile Visible Range (VPVR) – shows volume distribution across price levels within the visible chart window -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView built-in Volume Profile indicator (accessible via Indicators → Volume Profile).
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:volume-profile-visible-range-vpvr-shows-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
