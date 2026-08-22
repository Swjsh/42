# Chef Inbox — TRIN (Arms Index) – ratio of advancing volume to declining volume divi

**Routed by:** Gamma_Prospector 2026-08-09
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `microstructure_internals` surfaced: TRIN (Arms Index) – ratio of advancing volume to declining volume divided by advancing issues to declining issues -- Combines price and volume breadth to spot overbought/oversold conditions that often precede sharp 0DTE moves. Data source: CBOE Market Data (TRIN) available through BATS/ICE data feed or via the free Alpha Vantage technical indicator endpoint. Cost: $0. Instrument fit: both.

## Research Question for Chef
TRIN (Arms Index) – ratio of advancing volume to declining volume divided by advancing issues to declining issues -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CBOE Market Data (TRIN) available through BATS/ICE data feed or via the free Alpha Vantage technical indicator endpoint
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:trin-arms-index-ratio-of-advancing-volum) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none


<!-- NOTE 2026-08-22 ~04:xx ET conductor (WEEKEND, acting as chef, CHEF-INBOX-BACKLOG-DRAIN family-dedupe sweep): received 3 fold-in(s) from the same family, no new information -- 2026-08-13-prospector-trin-arms-index-advancing-issues-declini.md, 2026-08-17-prospector-trin-arms-index-volumeweighted-breadth-m.md, 2026-08-22-prospector-trin-arms-index-computed-from-nyse-advan.md -->
