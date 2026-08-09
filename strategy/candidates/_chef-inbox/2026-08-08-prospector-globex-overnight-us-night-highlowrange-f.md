# Chef Inbox — Globex overnight (U.S. night) high/low/range for MES/MNQ

**Routed by:** Gamma_Prospector 2026-08-08
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `futures_positioning` surfaced: Globex overnight (U.S. night) high/low/range for MES/MNQ -- Overnight price extremes often set the opening bias for the U.S. session, providing a low‑latency edge for swing positioning. Data source: Barchart API – Futures Overnight Session endpoint (https://www.barchart.com/solutions/api/futures/overnight). Cost: paid. Instrument fit: both.

## Research Question for Chef
Globex overnight (U.S. night) high/low/range for MES/MNQ -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Barchart API – Futures Overnight Session endpoint (https://www.barchart.com/solutions/api/futures/overnight)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:globex-overnight-us-night-highlowrange-f) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
