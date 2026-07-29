# Chef Inbox — Turn‑of‑the‑month effect in equity index futures

**Routed by:** Gamma_Prospector 2026-07-29
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Turn‑of‑the‑month effect in equity index futures -- Returns are systematically higher on the last trading day of a month and the first three days of the next month due to institutional cash flows, biasing intraday direction. Data source: Daily MES/ES continuous contract prices from Quandl/CME DataMine (free sample). Cost: $0. Instrument fit: mes.

## Research Question for Chef
Turn‑of‑the‑month effect in equity index futures -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: Daily MES/ES continuous contract prices from Quandl/CME DataMine (free sample)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:turnofthemonth-effect-in-equity-index-fu) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
