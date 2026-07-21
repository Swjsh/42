# Chef Inbox — IEX Cloud Real‑Time Quotes for SPY

**Routed by:** Gamma_Prospector 2026-07-14
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:openai/gpt-oss-20b:free

## The Finding
Prospector beat `data_feeds_free` surfaced: IEX Cloud Real‑Time Quotes for SPY -- Provides low‑latency, tick‑level price data to capture intraday price swings for 0DTE SPY options. Data source: IEX Cloud free tier (https://iexcloud.io). Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
IEX Cloud Real‑Time Quotes for SPY -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: IEX Cloud free tier (https://iexcloud.io)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:iex-cloud-realtime-quotes-for-spy) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
