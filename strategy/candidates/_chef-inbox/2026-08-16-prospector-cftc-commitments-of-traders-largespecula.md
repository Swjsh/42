# Chef Inbox — CFTC Commitments of Traders large‑speculator net positioning for MES a

**Routed by:** Gamma_Prospector 2026-08-16
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `futures_positioning` surfaced: CFTC Commitments of Traders large‑speculator net positioning for MES and MNQ -- Tracks net long vs short of large speculators to gauge directional bias and potential crowd‑crowding reversals. Data source: Nasdaq Data Link (formerly Quandl) CFTC COT dataset, e.g., https://data.nasdaq.com/api/v3/datasets/CFTC/00100101.json. Cost: paid. Instrument fit: both.

## Research Question for Chef
CFTC Commitments of Traders large‑speculator net positioning for MES and MNQ -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Nasdaq Data Link (formerly Quandl) CFTC COT dataset, e.g., https://data.nasdaq.com/api/v3/datasets/CFTC/00100101.json
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:cftc-commitments-of-traders-largespecula) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
