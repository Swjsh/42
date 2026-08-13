# Chef Inbox — FINRA Daily Short-Sale Volume (total short-sale volume reported for NY

**Routed by:** Gamma_Prospector 2026-08-13
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `microstructure_internals` surfaced: FINRA Daily Short-Sale Volume (total short-sale volume reported for NYSE/Nasdaq) -- Elevated short-sale volume often precedes short-covering rallies, providing a contrarian signal for intraday SPY/MES moves. Data source: FINRA publishes daily short-sale volume files at https://www.finra.org/finra-data/short-sale-volume, accessible via FTP or API; also available through Quandl (FINRA/SHORTVOL) and Bloomberg. Cost: $0. Instrument fit: both.

## Research Question for Chef
FINRA Daily Short-Sale Volume (total short-sale volume reported for NYSE/Nasdaq) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: FINRA publishes daily short-sale volume files at https://www.finra.org/finra-data/short-sale-volume, accessible via FTP or API; also available through Quandl (FINRA/SHORTVOL) and Bloomberg
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:finra-daily-short-sale-volume-total-shor) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
