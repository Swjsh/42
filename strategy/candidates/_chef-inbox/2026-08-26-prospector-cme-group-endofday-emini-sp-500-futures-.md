# Chef Inbox — CME Group End‑of‑Day E‑mini S&P 500 Futures Open Interest feed

**Routed by:** Gamma_Prospector 2026-08-26
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: CME Group End‑of‑Day E‑mini S&P 500 Futures Open Interest feed -- Rising open interest in ES futures often precedes directional pressure that can be mirrored in MES/MNQ intraday price moves. Data source: CME Group Market Data API (https://www.cmegroup.com/market-data/files.html) – free end‑of‑day CSV for ES open interest and volume. Cost: $0. Instrument fit: mes.

## Research Question for Chef
CME Group End‑of‑Day E‑mini S&P 500 Futures Open Interest feed -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: CME Group Market Data API (https://www.cmegroup.com/market-data/files.html) – free end‑of‑day CSV for ES open interest and volume
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:cme-group-endofday-emini-sp-500-futures-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
