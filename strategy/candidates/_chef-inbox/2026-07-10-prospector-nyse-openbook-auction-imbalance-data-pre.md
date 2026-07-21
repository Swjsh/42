# Chef Inbox — NYSE OpenBook auction imbalance data (pre-market and opening cross)

**Routed by:** Gamma_Prospector 2026-07-10
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:qwen/qwen3-next-80b-a3b-instruct:free

## The Finding
Prospector beat `data_feeds_free` surfaced: NYSE OpenBook auction imbalance data (pre-market and opening cross) -- Auction imbalances at 9:30 ET predict directional momentum in SPY and MES during the first 15 minutes, a critical window for 0DTE theta decay and futures liquidity events. Data source: NYSE OpenBook, https://www.nyse.com/data/nyse-openbook. Cost: $0. Instrument fit: both.

## Research Question for Chef
NYSE OpenBook auction imbalance data (pre-market and opening cross) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: NYSE OpenBook, https://www.nyse.com/data/nyse-openbook
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:nyse-openbook-auction-imbalance-data-pre) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
