# Chef Inbox — CME Daily Settlement Auction Imbalance for S&P 500 Futures

**Routed by:** Gamma_Prospector 2026-08-22
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: CME Daily Settlement Auction Imbalance for S&P 500 Futures -- Imbalance signals reveal directional pressure at the daily settlement auction, improving MES/MNQ entry timing. Data source: CME Group Settlement Auction Imbalance CSV files (https://www.cmegroup.com/market-data/settlement-auction-imbalance.html). Cost: $0. Instrument fit: mes.

## Research Question for Chef
CME Daily Settlement Auction Imbalance for S&P 500 Futures -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: CME Group Settlement Auction Imbalance CSV files (https://www.cmegroup.com/market-data/settlement-auction-imbalance.html)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:cme-daily-settlement-auction-imbalance-f) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
