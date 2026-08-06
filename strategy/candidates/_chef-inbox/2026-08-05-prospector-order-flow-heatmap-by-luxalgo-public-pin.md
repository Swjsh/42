# Chef Inbox — Order Flow Heatmap by LuxAlgo (public Pine Script library) – visualize

**Routed by:** Gamma_Prospector 2026-08-05
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Order Flow Heatmap by LuxAlgo (public Pine Script library) – visualizes buying vs. selling pressure per bar using delta volume approximations -- Shows real-time imbalance between buyers and sellers, flagging potential short-term reversals or continuations ahead of price moves. Data source: TradingView volume data with close/open classification to estimate buy/sell volume. Cost: $0. Instrument fit: both.

## Research Question for Chef
Order Flow Heatmap by LuxAlgo (public Pine Script library) – visualizes buying vs. selling pressure per bar using delta volume approximations -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView volume data with close/open classification to estimate buy/sell volume.
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:order-flow-heatmap-by-luxalgo-public-pin) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
