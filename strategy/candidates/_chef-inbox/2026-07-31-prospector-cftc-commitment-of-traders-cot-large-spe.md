# Chef Inbox — CFTC Commitment of Traders (COT) Large Speculator Net Position for E-m

**Routed by:** Gamma_Prospector 2026-07-31
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:openai/gpt-oss-120b:free

## The Finding
Prospector beat `futures_positioning` surfaced: CFTC Commitment of Traders (COT) Large Speculator Net Position for E-mini S&P 500 (CME: ES) -- Tracks the aggregate directional bias of the biggest speculators, revealing shifts before retail flow impacts the intraday swing mirror. Data source: CFTC COT reports via Quandl (code: CFTC/ES), released weekly on Fridays. Cost: paid. Instrument fit: mes.

## Research Question for Chef
CFTC Commitment of Traders (COT) Large Speculator Net Position for E-mini S&P 500 (CME: ES) -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: CFTC COT reports via Quandl (code: CFTC/ES), released weekly on Fridays
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:cftc-commitment-of-traders-cot-large-spe) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
