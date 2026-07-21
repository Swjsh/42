# Chef Inbox — 0DTE Gamma Concentration (Gamma Wall) identification

**Routed by:** Gamma_Prospector 2026-07-12
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:google/gemma-4-31b-it:free

## The Finding
Prospector beat `options_structure_metrics` surfaced: 0DTE Gamma Concentration (Gamma Wall) identification -- Identifies specific strike levels with extreme gamma density that act as magnets or hard ceilings/floors for intraday price action. Data source: OPRA real-time options chain data via Tradier or ThetaData API. Cost: paid. Instrument fit: 0dte.

## Research Question for Chef
0DTE Gamma Concentration (Gamma Wall) identification -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: OPRA real-time options chain data via Tradier or ThetaData API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:0dte-gamma-concentration-gamma-wall-iden) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
