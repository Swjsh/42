# Chef Inbox — NYSE TICK Index – real‑time net uptick/down‑tick count

**Routed by:** Gamma_Prospector 2026-08-09
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `microstructure_internals` surfaced: NYSE TICK Index – real‑time net uptick/down‑tick count -- Captures short‑term buying pressure that often precedes 0DTE option moves and MES intraday spikes. Data source: NYSE Open Market Data feed (TICK), accessible via Quandl (code: NYSE_TICK) or directly from NYSE Market Data API. Cost: $0. Instrument fit: both.

## Research Question for Chef
NYSE TICK Index – real‑time net uptick/down‑tick count -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: NYSE Open Market Data feed (TICK), accessible via Quandl (code: NYSE_TICK) or directly from NYSE Market Data API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:nyse-tick-index-realtime-net-uptickdownt) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none


<!-- NOTE 2026-08-22 ~04:xx ET conductor (WEEKEND, acting as chef, CHEF-INBOX-BACKLOG-DRAIN family-dedupe sweep): received 3 fold-in(s) from the same family, no new information -- 2026-08-12-prospector-nyse-tick-index-real-time-difference-bet.md, 2026-08-17-prospector-nyse-tick-index-tick5-realtime-net-buyse.md, 2026-08-21-prospector-nyse-tick-index-real-time-uptick-downtic.md -->
