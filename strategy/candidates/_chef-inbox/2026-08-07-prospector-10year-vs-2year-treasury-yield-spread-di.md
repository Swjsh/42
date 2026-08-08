# Chef Inbox — 10‑Year vs 2‑Year Treasury yield spread divergence

**Routed by:** Gamma_Prospector 2026-08-07
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `cross_asset_signals` surfaced: 10‑Year vs 2‑Year Treasury yield spread divergence -- A widening 10Y‑2Y spread reflects investor confidence in long‑term growth, often bullish for equity futures, while a narrowing spread can forewarn risk‑off pressure on MES/MNQ. Data source: Federal Reserve Economic Data (FRED) series DGS10 and DGS2, downloadable via the FRED API. Cost: $0. Instrument fit: both.

## Research Question for Chef
10‑Year vs 2‑Year Treasury yield spread divergence -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) series DGS10 and DGS2, downloadable via the FRED API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:10year-vs-2year-treasury-yield-spread-di) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
