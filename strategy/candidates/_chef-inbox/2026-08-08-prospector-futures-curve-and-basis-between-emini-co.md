# Chef Inbox — Futures curve and basis between E‑mini contracts and their underlying 

**Routed by:** Gamma_Prospector 2026-08-08
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `futures_positioning` surfaced: Futures curve and basis between E‑mini contracts and their underlying index -- The basis (future price minus spot) reveals cost‑of‑carry and market sentiment, helping to time roll‑overs and spot‑vs‑future bias. Data source: Quandl dataset CHRIS/CME_ES1 (E‑mini S&P 500 Futures) and CHRIS/CME_NQ1 (E‑mini Nasdaq 100 Futures). Cost: $0. Instrument fit: both.

## Research Question for Chef
Futures curve and basis between E‑mini contracts and their underlying index -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Quandl dataset CHRIS/CME_ES1 (E‑mini S&P 500 Futures) and CHRIS/CME_NQ1 (E‑mini Nasdaq 100 Futures)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:futures-curve-and-basis-between-emini-co) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
