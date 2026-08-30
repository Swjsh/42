# Chef Inbox — Lunch‑Lull Volatility Compression – a pronounced dip in volatility fro

**Routed by:** Gamma_Prospector 2026-08-30
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Lunch‑Lull Volatility Compression – a pronounced dip in volatility from 11:30 ET to 13:30 ET -- Reduced news flow and thinner order flow during the midday lull lower variance, allowing tighter spreads and higher probability of range‑bound strategies. Data source: CME DataMine historical futures tick data (https://datamine.cmegroup.com). Cost: paid. Instrument fit: both.

## Research Question for Chef
Lunch‑Lull Volatility Compression – a pronounced dip in volatility from 11:30 ET to 13:30 ET -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CME DataMine historical futures tick data (https://datamine.cmegroup.com)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:lunchlull-volatility-compression-a-prono) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
