# Chef Inbox — Order Flow Imbalance (OFI) by @Sanjay – cumulative delta proxy for buy

**Routed by:** Gamma_Prospector 2026-07-22
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `tv_community_indicators` surfaced: Order Flow Imbalance (OFI) by @Sanjay – cumulative delta proxy for buyer‑seller aggression -- Measures net buying vs. selling pressure on each tick, providing an order‑flow edge not captured by price‑only indicators. Data source: Public Pine Script library, author "Sanjay", script name "Order Flow Imbalance" (https://www.tradingview.com/script/… ). Cost: $0. Instrument fit: both.

## Research Question for Chef
Order Flow Imbalance (OFI) by @Sanjay – cumulative delta proxy for buyer‑seller aggression -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Public Pine Script library, author "Sanjay", script name "Order Flow Imbalance" (https://www.tradingview.com/script/… )
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:order-flow-imbalance-ofi-by-sanjay-cumul) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
