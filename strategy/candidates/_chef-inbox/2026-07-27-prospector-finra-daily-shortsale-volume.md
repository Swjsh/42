# Chef Inbox — FINRA Daily Short‑Sale Volume

**Routed by:** Gamma_Prospector 2026-07-27
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `microstructure_internals` surfaced: FINRA Daily Short‑Sale Volume -- Tracks aggregate short‑selling activity, a contrarian signal that often foreshadows rapid reversals in SPY and MES price action. Data source: FINRA Short Sale Reporting website (CSV download) – https://www.finra.org/finra-data/short-sale-data. Cost: $0. Instrument fit: both.

## Research Question for Chef
FINRA Daily Short‑Sale Volume -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: FINRA Short Sale Reporting website (CSV download) – https://www.finra.org/finra-data/short-sale-data
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:finra-daily-shortsale-volume) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
