# Chef Inbox — Market Profile (TPO) built-in TradingView indicator – displays time‑pr

**Routed by:** Gamma_Prospector 2026-07-28
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Market Profile (TPO) built-in TradingView indicator – displays time‑price opportunity distribution, highlighting value area and point of control -- Reveals where price spent most time, exposing acceptance zones and potential breakout levels not visible via EMA/RSI. Data source: TradingView built-in Market Profile indicator (uses price and time series). Cost: $0. Instrument fit: both.

## Research Question for Chef
Market Profile (TPO) built-in TradingView indicator – displays time‑price opportunity distribution, highlighting value area and point of control -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView built-in Market Profile indicator (uses price and time series).
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:market-profile-tpo-built-in-tradingview-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
