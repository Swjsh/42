# Chef Inbox — Read CBOE's VIX1D (1-day volatility index, ticker ^VIX1D) as a same-ho

**Routed by:** Gamma_Prospector 2026-07-09
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** fable-2026-07-09

## The Finding
Prospector beat `options_structure_metrics` surfaced: Read CBOE's VIX1D (1-day volatility index, ticker ^VIX1D) as a same-horizon vol gate instead of only the 30-day headline VIX -- VIX1D isolates ULTRA-short-dated (next-day/0DTE-horizon) implied vol -- a more precisely-dated 'is today expected to be calm or violent' gate than 30-day VIX (C5: VIX character > VIX level). Data source: CBOE VIX1D index -- same access path Gamma already uses for VIX (Alpaca index endpoints or yfinance fallback). Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
Read CBOE's VIX1D (1-day volatility index, ticker ^VIX1D) as a same-horizon vol gate instead of only the 30-day headline VIX -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE VIX1D index -- same access path Gamma already uses for VIX (Alpaca index endpoints or yfinance fallback).
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: vix1d_gate) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
