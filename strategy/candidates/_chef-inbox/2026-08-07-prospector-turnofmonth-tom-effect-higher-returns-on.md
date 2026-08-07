# Chef Inbox — Turn‑of‑Month (TOM) Effect – higher returns on month‑end and month‑sta

**Routed by:** Gamma_Prospector 2026-08-07
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Turn‑of‑Month (TOM) Effect – higher returns on month‑end and month‑start days -- Historical studies show a consistent positive drift on the last trading day of a month and the first two days of the next month, creating a calendar‑based edge. Data source: CRSP daily and intraday data accessed through WRDS (https://wrds-web.wharton.upenn.edu). Cost: paid. Instrument fit: both.

## Research Question for Chef
Turn‑of‑Month (TOM) Effect – higher returns on month‑end and month‑start days -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CRSP daily and intraday data accessed through WRDS (https://wrds-web.wharton.upenn.edu)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:turnofmonth-tom-effect-higher-returns-on) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
