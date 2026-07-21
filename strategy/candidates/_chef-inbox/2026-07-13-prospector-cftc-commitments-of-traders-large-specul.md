# Chef Inbox — CFTC Commitments of Traders large-speculator net positioning for E-min

**Routed by:** Gamma_Prospector 2026-07-13
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `futures_positioning` surfaced: CFTC Commitments of Traders large-speculator net positioning for E-mini S&P 500 (ES) and E-mini Nasdaq-100 (NQ) as a sentiment proxy -- Extreme net long/short positions by large speculators often precede short-term mean-reversion swings in MES/MNQ futures. Data source: CFTC Commitments of Traders report, weekly, free via https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm (ES and NQ contracts). Cost: $0. Instrument fit: mes.

## Research Question for Chef
CFTC Commitments of Traders large-speculator net positioning for E-mini S&P 500 (ES) and E-mini Nasdaq-100 (NQ) as a sentiment proxy -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: CFTC Commitments of Traders report, weekly, free via https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm (ES and NQ contracts)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:cftc-commitments-of-traders-large-specul) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
