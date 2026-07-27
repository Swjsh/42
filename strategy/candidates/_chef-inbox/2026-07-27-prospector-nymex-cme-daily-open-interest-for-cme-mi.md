# Chef Inbox — NYMEX CME Daily Open Interest for CME Mini Futures via CME Group API

**Routed by:** Gamma_Prospector 2026-07-27
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:openai/gpt-oss-120b:free

## The Finding
Prospector beat `data_feeds_free` surfaced: NYMEX CME Daily Open Interest for CME Mini Futures via CME Group API -- Tracks shifts in speculative vs. hedging positions in MES/MNQ to anticipate short‑term liquidity imbalances. Data source: CME Group Market Data API (Free tier: https://developer.cmegroup.com). Cost: $0. Instrument fit: both.

## Research Question for Chef
NYMEX CME Daily Open Interest for CME Mini Futures via CME Group API -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CME Group Market Data API (Free tier: https://developer.cmegroup.com)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:nymex-cme-daily-open-interest-for-cme-mi) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
