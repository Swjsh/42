# Chef Inbox — Daily Futures Curve Basis between CME E-mini S&P 500 (ES) and CME Micr

**Routed by:** Gamma_Prospector 2026-07-31
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:openai/gpt-oss-120b:free

## The Finding
Prospector beat `futures_positioning` surfaced: Daily Futures Curve Basis between CME E-mini S&P 500 (ES) and CME Micro E-mini S&P 500 (MES) -- The spread between ES and MES reflects funding pressure and liquidity imbalances that can predict short‑term directional moves in MES swing positions. Data source: CME Group Market Data Feed (MDU) – real‑time futures quotes for ES and MES. Cost: paid. Instrument fit: both.

## Research Question for Chef
Daily Futures Curve Basis between CME E-mini S&P 500 (ES) and CME Micro E-mini S&P 500 (MES) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CME Group Market Data Feed (MDU) – real‑time futures quotes for ES and MES
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:daily-futures-curve-basis-between-cme-e-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
