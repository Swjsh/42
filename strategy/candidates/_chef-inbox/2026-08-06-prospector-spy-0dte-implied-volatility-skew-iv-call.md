# Chef Inbox — SPY 0DTE Implied Volatility Skew (IV Call – IV Put) at 25‑Delta

**Routed by:** Gamma_Prospector 2026-08-06
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Implied Volatility Skew (IV Call – IV Put) at 25‑Delta -- Measures asymmetry in market expectations of upside vs downside risk, offering a predictive edge for short‑term option premium decay. Data source: CBOE Live Volatility Index API (IV data per strike) – use the "SPY" option chain endpoint. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Implied Volatility Skew (IV Call – IV Put) at 25‑Delta -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE Live Volatility Index API (IV data per strike) – use the "SPY" option chain endpoint
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-implied-volatility-skew-iv-call) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
