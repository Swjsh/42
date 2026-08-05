# Chef Inbox — Overnight Globex session high/low/range for MES/MNQ

**Routed by:** Gamma_Prospector 2026-07-26
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `futures_positioning` surfaced: Overnight Globex session high/low/range for MES/MNQ -- An expanded overnight Globex range often predicts the direction and magnitude of the next day's swing in the mirror. Data source: Quandl CME Futures Globex OHLC dataset (e.g., CHRIS/CME_ES1 for MES, CHRIS/CME_NQ1 for MNQ) offering free delayed data. Cost: $0. Instrument fit: mes.

## Research Question for Chef
Overnight Globex session high/low/range for MES/MNQ -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: Quandl CME Futures Globex OHLC dataset (e.g., CHRIS/CME_ES1 for MES, CHRIS/CME_NQ1 for MNQ) offering free delayed data
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:overnight-globex-session-highlowrange-fo) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-08-05 ~05:45-06:15 ET conductor (AFTERHOURS, acting as chef, CHEF-INBOX-BACKLOG-DRAIN dedup pass): CONSOLIDATED -- canonical for the Globex overnight-session-range family, self-labels $0. -->
