# Chef Inbox — Market Profile (TPO) built-in indicator - displays time-price distribu

**Routed by:** Gamma_Prospector 2026-08-14
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Market Profile (TPO) built-in indicator - displays time-price distribution, value area, and point of control -- Reveals where market has spent most time, highlighting fair value zones and potential rejection levels. Data source: TradingView built-in Market Profile indicator. Cost: $0. Instrument fit: both.

## Research Question for Chef
Market Profile (TPO) built-in indicator - displays time-price distribution, value area, and point of control -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView built-in Market Profile indicator
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:market-profile-tpo-built-in-indicator-di) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none


<!-- NOTE 2026-08-22 ~04:xx ET conductor (WEEKEND, acting as chef, CHEF-INBOX-BACKLOG-DRAIN family-dedupe sweep): received 1 fold-in(s) from the same family, no new information -- 2026-08-19-prospector-market-profile-tpo-public-pine-script-by.md -->
