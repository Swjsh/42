# Chef Inbox — Front-month to second-month basis (curve) of E-mini S&P 500 (ES) futur

**Routed by:** Gamma_Prospector 2026-08-04
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `futures_positioning` surfaced: Front-month to second-month basis (curve) of E-mini S&P 500 (ES) futures -- Changes in the ES basis reflect near-term supply/demand imbalances and can lead price action in the front month, offering a leading indicator for swing moves. Data source: Quandl EOD futures chain for CME_ES1 and CME_ES2 (free via https://www.quandl.com/data/CME). Cost: $0. Instrument fit: mes.

## Research Question for Chef
Front-month to second-month basis (curve) of E-mini S&P 500 (ES) futures -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: Quandl EOD futures chain for CME_ES1 and CME_ES2 (free via https://www.quandl.com/data/CME)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:front-month-to-second-month-basis-curve-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
