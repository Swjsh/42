# Chef Inbox — CFTC Commitments of Traders (COT) large-speculator net positioning for

**Routed by:** Gamma_Prospector 2026-07-26
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `futures_positioning` surfaced: CFTC Commitments of Traders (COT) large-speculator net positioning for E-mini S&P 500 futures -- Extreme net long or short positions by large speculators often precede mean‑reverting moves in the MES swing mirror. Data source: CFTC weekly COT report, available free at https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm. Cost: $0. Instrument fit: mes.

## Research Question for Chef
CFTC Commitments of Traders (COT) large-speculator net positioning for E-mini S&P 500 futures -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: CFTC weekly COT report, available free at https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:cftc-commitments-of-traders-cot-large-sp) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-08-05 ~05:45-06:15 ET conductor (AFTERHOURS, acting as chef, CHEF-INBOX-BACKLOG-DRAIN dedup pass): 2 newer near-duplicate(s) folded in this fire -- 2026-07-31-prospector-cftc-commitment-of-traders-cot-large-spe.md (same CFTC COT idea, 2nd recurrence); 2026-08-04-prospector-cftc-cot-large-speculator-net-positionin.md (same idea, 3rd recurrence). Canonical status unchanged: CONSOLIDATED -- canonical for the CFTC COT large-speculator-positioning family. All 3 instances self-label $0 (CFTC's own weekly COT report is genuinely free, no vendor needed). Unresearched, genuinely viable -- weekly (not daily) cadence limits sample size for a 0DTE-scale backtest, flagged for chef.. -->
