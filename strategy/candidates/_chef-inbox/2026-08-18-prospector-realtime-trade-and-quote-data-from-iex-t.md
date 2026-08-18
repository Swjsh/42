# Chef Inbox — Real‑time trade and quote data from IEX TOPS

**Routed by:** Gamma_Prospector 2026-08-18
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: Real‑time trade and quote data from IEX TOPS -- IEX TOPS provides low‑latency NBBO updates and trade prints that improve order‑flow timing for high‑frequency 0DTE SPY strategies. Data source: IEX Cloud free tier (https://iexcloud.io/docs/api/#tops). Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
Real‑time trade and quote data from IEX TOPS -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: IEX Cloud free tier (https://iexcloud.io/docs/api/#tops)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:realtime-trade-and-quote-data-from-iex-t) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
