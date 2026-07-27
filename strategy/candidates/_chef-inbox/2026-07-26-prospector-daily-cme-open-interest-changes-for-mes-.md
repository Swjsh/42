# Chef Inbox — Daily CME open interest changes for MES and MNQ futures

**Routed by:** Gamma_Prospector 2026-07-26
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `futures_positioning` surfaced: Daily CME open interest changes for MES and MNQ futures -- Rising open interest alongside price movement confirms new money entering the trend, while falling OI warns of weakening momentum. Data source: CME Group DataMine API (or CME FTP) providing daily settlement open interest for MES (code ES) and MNQ (code NQ). Cost: paid. Instrument fit: mes.

## Research Question for Chef
Daily CME open interest changes for MES and MNQ futures -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: CME Group DataMine API (or CME FTP) providing daily settlement open interest for MES (code ES) and MNQ (code NQ)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:daily-cme-open-interest-changes-for-mes-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
