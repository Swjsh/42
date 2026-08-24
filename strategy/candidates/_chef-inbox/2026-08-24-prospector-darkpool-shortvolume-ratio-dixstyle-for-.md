# Chef Inbox — Dark‑Pool Short‑Volume Ratio (DIX‑style) for SPY – dark‑pool short int

**Routed by:** Gamma_Prospector 2026-08-24
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `options_structure_metrics` surfaced: Dark‑Pool Short‑Volume Ratio (DIX‑style) for SPY – dark‑pool short interest vs total short interest -- Elevated dark‑pool short ratios often precede short‑squeeze dynamics, offering a contrarian signal for same‑day option positioning. Data source: FINRA short‑sale volume data via Nasdaq Data Link (formerly Quandl) – SPY ticker short‑sale aggregates. Cost: paid. Instrument fit: 0dte.

## Research Question for Chef
Dark‑Pool Short‑Volume Ratio (DIX‑style) for SPY – dark‑pool short interest vs total short interest -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: FINRA short‑sale volume data via Nasdaq Data Link (formerly Quandl) – SPY ticker short‑sale aggregates
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:darkpool-shortvolume-ratio-dixstyle-for-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
