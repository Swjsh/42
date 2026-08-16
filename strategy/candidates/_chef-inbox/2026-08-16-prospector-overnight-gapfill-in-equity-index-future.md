# Chef Inbox — Overnight Gap‑Fill in equity index futures – a large portion of the ov

**Routed by:** Gamma_Prospector 2026-08-16
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Overnight Gap‑Fill in equity index futures – a large portion of the overnight price gap tends to be closed within the first 30 minutes of the US session -- Liquidity providers and arbitrageurs aggressively fill overnight gaps, creating a predictable mean‑reversion signal for both SPY options and MES/MNQ futures. Data source: Quandl CHRIS dataset for CME futures (https://www.quandl.com/data/CHRIS). Cost: $0. Instrument fit: both.

## Research Question for Chef
Overnight Gap‑Fill in equity index futures – a large portion of the overnight price gap tends to be closed within the first 30 minutes of the US session -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Quandl CHRIS dataset for CME futures (https://www.quandl.com/data/CHRIS)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:overnight-gapfill-in-equity-index-future) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
