# Chef Inbox — 0DTE Gamma Concentration Index – sum of gamma weighted by open interes

**Routed by:** Gamma_Prospector 2026-07-28
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `options_structure_metrics` surfaced: 0DTE Gamma Concentration Index – sum of gamma weighted by open interest at each strike normalized by total gamma -- High gamma concentration near spot predicts increased intraday volatility and mean-reverting pressure as dealers hedge. Data source: CBOE options OI and implied volatility for SPY 0DTE strikes (free OI via CBOE FTP, free IV from CBOE VIX term structure); gamma computed via Black‑Scholes. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
0DTE Gamma Concentration Index – sum of gamma weighted by open interest at each strike normalized by total gamma -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE options OI and implied volatility for SPY 0DTE strikes (free OI via CBOE FTP, free IV from CBOE VIX term structure); gamma computed via Black‑Scholes
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:0dte-gamma-concentration-index-sum-of-ga) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
