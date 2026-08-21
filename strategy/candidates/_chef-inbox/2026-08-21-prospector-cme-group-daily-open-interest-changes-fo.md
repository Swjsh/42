# Chef Inbox — CME Group daily open interest changes for ES and NQ futures

**Routed by:** Gamma_Prospector 2026-08-21
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `futures_positioning` surfaced: CME Group daily open interest changes for ES and NQ futures -- Rising open interest alongside price moves confirms new money entering the trend, helping to validate swing direction and strength. Data source: CME Group Daily Open Interest report via Quandl (EOD) or CME DataMine free delayed feed. Cost: $0. Instrument fit: both.

## Research Question for Chef
CME Group daily open interest changes for ES and NQ futures -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CME Group Daily Open Interest report via Quandl (EOD) or CME DataMine free delayed feed
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:cme-group-daily-open-interest-changes-fo) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
