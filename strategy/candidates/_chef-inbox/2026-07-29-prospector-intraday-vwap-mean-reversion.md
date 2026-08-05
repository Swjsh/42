# Chef Inbox — Intraday VWAP mean reversion

**Routed by:** Gamma_Prospector 2026-07-29
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Intraday VWAP mean reversion -- Price tends to revert to the volume‑weighted average price (VWAP) within the trading day, especially after deviations exceeding 0.5%, offering short‑term mean‑reversion opportunities. Data source: Intraday SPY and MES minute VWAP calculated from TAQ or IQFeed data. Cost: $0. Instrument fit: both.

## Research Question for Chef
Intraday VWAP mean reversion -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Intraday SPY and MES minute VWAP calculated from TAQ or IQFeed data
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:intraday-vwap-mean-reversion) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-08-05 ~05:45-06:15 ET conductor (AFTERHOURS, acting as chef, CHEF-INBOX-BACKLOG-DRAIN dedup pass): CONSOLIDATED -- canonical for the intraday VWAP-mean-reversion family, self-labels $0. -->
