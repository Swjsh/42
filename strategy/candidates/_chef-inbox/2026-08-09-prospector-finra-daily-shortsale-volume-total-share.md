# Chef Inbox — FINRA Daily Short‑Sale Volume – total shares sold short per ticker per

**Routed by:** Gamma_Prospector 2026-08-09
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `microstructure_internals` surfaced: FINRA Daily Short‑Sale Volume – total shares sold short per ticker per day -- Elevated short‑sale activity can foreshadow rapid reversals or squeezes that drive 0DTE SPY option volatility. Data source: FINRA Short Sale Reporting (SSR) data, downloadable CSV from FINRA website or via the free Quandl dataset (FINRA/SSR). Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
FINRA Daily Short‑Sale Volume – total shares sold short per ticker per day -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: FINRA Short Sale Reporting (SSR) data, downloadable CSV from FINRA website or via the free Quandl dataset (FINRA/SSR)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:finra-daily-shortsale-volume-total-share) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
