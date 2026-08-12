# Chef Inbox — Daily change in CME open interest for MES and MNQ contracts

**Routed by:** Gamma_Prospector 2026-08-12
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `futures_positioning` surfaced: Daily change in CME open interest for MES and MNQ contracts -- Rising open interest with price indicates new money entering a trend; declining OI with price move suggests weakening momentum and possible swing. Data source: CME settlement data including open interest, available free via Quandl datasets CME/MES1 and CME/MNQ1 (https://www.quandl.com/data/CME). Cost: $0. Instrument fit: mes.

## Research Question for Chef
Daily change in CME open interest for MES and MNQ contracts -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: CME settlement data including open interest, available free via Quandl datasets CME/MES1 and CME/MNQ1 (https://www.quandl.com/data/CME)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:daily-change-in-cme-open-interest-for-me) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
