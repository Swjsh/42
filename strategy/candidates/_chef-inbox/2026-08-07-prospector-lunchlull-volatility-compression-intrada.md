# Chef Inbox — Lunch‑Lull Volatility Compression – intraday volatility dip around 12‑

**Routed by:** Gamma_Prospector 2026-08-07
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Lunch‑Lull Volatility Compression – intraday volatility dip around 12‑1 PM -- Empirical work shows a pronounced volatility trough during the midday lunch period, after which volatility often spikes, offering a timing cue for breakout trades. Data source: Kibot minute‑level historical data (free tier) (https://www.kibot.com). Cost: $0. Instrument fit: both.

## Research Question for Chef
Lunch‑Lull Volatility Compression – intraday volatility dip around 12‑1 PM -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Kibot minute‑level historical data (free tier) (https://www.kibot.com)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:lunchlull-volatility-compression-intrada) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
