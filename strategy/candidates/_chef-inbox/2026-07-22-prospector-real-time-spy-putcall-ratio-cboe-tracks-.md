# Chef Inbox — Real-time SPY Put/Call Ratio (CBOE) – tracks the live balance of puts 

**Routed by:** Gamma_Prospector 2026-07-22
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `options_structure_metrics` surfaced: Real-time SPY Put/Call Ratio (CBOE) – tracks the live balance of puts versus calls on SPY -- A high put/call ratio signals bearish pressure that often precedes short‑term SPY declines, offering a directional edge for 0DTE trades. Data source: CBOE Live Options Data Feed (CBOE Live API), ticker SPYPC. Cost: paid. Instrument fit: 0dte.

## Research Question for Chef
Real-time SPY Put/Call Ratio (CBOE) – tracks the live balance of puts versus calls on SPY -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE Live Options Data Feed (CBOE Live API), ticker SPYPC
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:real-time-spy-putcall-ratio-cboe-tracks-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
