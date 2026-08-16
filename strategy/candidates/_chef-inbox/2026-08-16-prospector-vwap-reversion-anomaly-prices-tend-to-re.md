# Chef Inbox — VWAP Reversion anomaly – prices tend to revert toward the daily VWAP a

**Routed by:** Gamma_Prospector 2026-08-16
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: VWAP Reversion anomaly – prices tend to revert toward the daily VWAP after large deviations -- Mean‑reversion of price relative to VWAP creates short‑term profit opportunities when price deviates beyond a sigma band. Data source: Bloomberg B‑PIPE intraday tick data (https://www.bloomberg.com/professional/solution/b-pipe/). Cost: paid. Instrument fit: both.

## Research Question for Chef
VWAP Reversion anomaly – prices tend to revert toward the daily VWAP after large deviations -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Bloomberg B‑PIPE intraday tick data (https://www.bloomberg.com/professional/solution/b-pipe/)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:vwap-reversion-anomaly-prices-tend-to-re) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
