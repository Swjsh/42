# Chef Inbox — Order Flow Imbalance (OFI) by LuxAlgo (public Pine Script) - estimates

**Routed by:** Gamma_Prospector 2026-08-14
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Order Flow Imbalance (OFI) by LuxAlgo (public Pine Script) - estimates buying vs selling pressure using volume and price change -- Captures short-term order-flow bias that precedes price moves, useful for intraday entries/exits. Data source: TradingView community Pine Script library: Order Flow Imbalance by LuxAlgo. Cost: $0. Instrument fit: both.

## Research Question for Chef
Order Flow Imbalance (OFI) by LuxAlgo (public Pine Script) - estimates buying vs selling pressure using volume and price change -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView community Pine Script library: Order Flow Imbalance by LuxAlgo
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:order-flow-imbalance-ofi-by-luxalgo-publ) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
