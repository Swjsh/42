# Chef Inbox — CME Daily Open Interest and change for E‑mini contracts

**Routed by:** Gamma_Prospector 2026-08-08
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `futures_positioning` surfaced: CME Daily Open Interest and change for E‑mini contracts -- Rising open interest alongside price moves signals new capital inflow, enhancing conviction on trend continuations. Data source: CME DataMine API – Daily Open Interest endpoint (https://datamine.cmegroup.com). Cost: paid. Instrument fit: both.

## Research Question for Chef
CME Daily Open Interest and change for E‑mini contracts -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CME DataMine API – Daily Open Interest endpoint (https://datamine.cmegroup.com)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:cme-daily-open-interest-and-change-for-e) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
