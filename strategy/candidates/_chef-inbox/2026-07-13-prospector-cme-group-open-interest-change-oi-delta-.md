# Chef Inbox — CME Group open interest change (OI delta) for MES and MNQ futures to g

**Routed by:** Gamma_Prospector 2026-07-13
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `futures_positioning` surfaced: CME Group open interest change (OI delta) for MES and MNQ futures to gauge new money flow -- Rising OI with price indicates fresh trend participation, while falling OI warns of weakening momentum for swing trades. Data source: CME Group historical open interest via Quandl datasets CHRIS/CME_ES1 (ES) and CHRIS/CME_NQ1 (NQ), accessed through Quandl API. Cost: paid. Instrument fit: mes.

## Research Question for Chef
CME Group open interest change (OI delta) for MES and MNQ futures to gauge new money flow -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: CME Group historical open interest via Quandl datasets CHRIS/CME_ES1 (ES) and CHRIS/CME_NQ1 (NQ), accessed through Quandl API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:cme-group-open-interest-change-oi-delta-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
