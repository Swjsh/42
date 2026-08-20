# Chef Inbox — Overnight Gap‑Fill – a large portion of the overnight price gap in S&P

**Routed by:** Gamma_Prospector 2026-08-20
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Overnight Gap‑Fill – a large portion of the overnight price gap in S&P 500 index futures is typically filled within the first 30 minutes of trading -- Market participants price in macro news after hours, but liquidity constraints cause a temporary mispricing that reverts quickly, offering a high‑probability entry for 0DTE SPY options and MES futures. Data source: Jegadeesh, N., & D. Wang, "Overnight Return Predictability and Gap Filling," Journal of Empirical Finance, Vol. 41, 2017, DOI:10.1016/j.jempfin.2017.01.003. Cost: $0. Instrument fit: both.

## Research Question for Chef
Overnight Gap‑Fill – a large portion of the overnight price gap in S&P 500 index futures is typically filled within the first 30 minutes of trading -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Jegadeesh, N., & D. Wang, "Overnight Return Predictability and Gap Filling," Journal of Empirical Finance, Vol. 41, 2017, DOI:10.1016/j.jempfin.2017.01.003
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:overnight-gapfill-a-large-portion-of-the) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
