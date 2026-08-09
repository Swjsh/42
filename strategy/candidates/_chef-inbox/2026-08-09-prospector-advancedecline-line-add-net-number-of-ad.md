# Chef Inbox — Advance‑Decline Line (ADD) – net number of advancing vs. declining sto

**Routed by:** Gamma_Prospector 2026-08-09
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `microstructure_internals` surfaced: Advance‑Decline Line (ADD) – net number of advancing vs. declining stocks on NYSE/NASDAQ -- Measures broad market breadth; extreme divergences can signal upcoming directional swings in SPY options and futures. Data source: NASDAQ TotalView data (ADV/DEC counts) via the free Daily Summary API from IEX Cloud. Cost: $0. Instrument fit: both.

## Research Question for Chef
Advance‑Decline Line (ADD) – net number of advancing vs. declining stocks on NYSE/NASDAQ -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: NASDAQ TotalView data (ADV/DEC counts) via the free Daily Summary API from IEX Cloud
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:advancedecline-line-add-net-number-of-ad) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
