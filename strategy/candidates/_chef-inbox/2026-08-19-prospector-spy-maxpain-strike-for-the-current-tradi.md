# Chef Inbox — SPY Max‑Pain Strike for the current trading day

**Routed by:** Gamma_Prospector 2026-08-19
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY Max‑Pain Strike for the current trading day -- The strike with the greatest open‑interest loss (max pain) tends to attract price convergence as expiration approaches, offering a target level for intraday positioning. Data source: CBOE GEX/OI archive (existing) processed to compute daily max‑pain. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
SPY Max‑Pain Strike for the current trading day -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE GEX/OI archive (existing) processed to compute daily max‑pain
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-maxpain-strike-for-the-current-tradi) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
