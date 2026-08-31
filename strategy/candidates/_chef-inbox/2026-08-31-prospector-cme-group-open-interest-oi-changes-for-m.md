# Chef Inbox — CME Group open interest (OI) changes for MES and MNQ front-month contr

**Routed by:** Gamma_Prospector 2026-08-31
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `futures_positioning` surfaced: CME Group open interest (OI) changes for MES and MNQ front-month contracts -- Rising OI with price moves indicates new money entering the trend, while falling OI warns of weakening momentum, useful for swing confirmation. Data source: CME DataMine historical OI series (ticker MES1! OI, MNQ1! OI) or Quandl CME_FUTURES_OI. Cost: paid. Instrument fit: both.

## Research Question for Chef
CME Group open interest (OI) changes for MES and MNQ front-month contracts -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CME DataMine historical OI series (ticker MES1! OI, MNQ1! OI) or Quandl CME_FUTURES_OI
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:cme-group-open-interest-oi-changes-for-m) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
