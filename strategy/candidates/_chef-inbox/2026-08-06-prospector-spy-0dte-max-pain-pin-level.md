# Chef Inbox — SPY 0DTE Max Pain (Pin) Level

**Routed by:** Gamma_Prospector 2026-08-06
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Max Pain (Pin) Level -- Identifies the strike where total open interest dollar value is minimized, often acting as a magnet for price near expiration. Data source: CBOE Open Interest Archive (daily OI snapshots) – downloadable CSV from CBOE website. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Max Pain (Pin) Level -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE Open Interest Archive (daily OI snapshots) – downloadable CSV from CBOE website
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-max-pain-pin-level) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
