# Chef Inbox — SPY 0DTE Put/Call Ratio (PCR) calculated from real‑time CBOE options v

**Routed by:** Gamma_Prospector 2026-08-15
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Put/Call Ratio (PCR) calculated from real‑time CBOE options volume -- High PCR signals bearish pressure that often precedes intraday SPY moves, offering a directional edge for 0DTE option strategies. Data source: CBOE Options Volume API (endpoint https://cdn.cboe.com/api/global/delayedquotes/spx/options) – free delayed feed. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Put/Call Ratio (PCR) calculated from real‑time CBOE options volume -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE Options Volume API (endpoint https://cdn.cboe.com/api/global/delayedquotes/spx/options) – free delayed feed
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-putcall-ratio-pcr-calculated-fr) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
