# Chef Inbox — VWAP Reversion – price tends to revert toward the day’s VWAP after ext

**Routed by:** Gamma_Prospector 2026-08-06
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: VWAP Reversion – price tends to revert toward the day’s VWAP after extreme moves -- Intraday price excursions away from the volume‑weighted average price exhibit statistically significant mean‑reversion, offering a reversion signal. Data source: NASDAQ TotalView‑ITCH feed via Nasdaq Data Link (https://data.nasdaq.com). Cost: paid. Instrument fit: both.

## Research Question for Chef
VWAP Reversion – price tends to revert toward the day’s VWAP after extreme moves -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: NASDAQ TotalView‑ITCH feed via Nasdaq Data Link (https://data.nasdaq.com)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:vwap-reversion-price-tends-to-revert-tow) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
