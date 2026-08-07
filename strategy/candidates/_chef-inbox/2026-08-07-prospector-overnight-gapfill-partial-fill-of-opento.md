# Chef Inbox — Overnight Gap‑Fill – partial fill of open‑to‑close gaps within the fir

**Routed by:** Gamma_Prospector 2026-08-07
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Overnight Gap‑Fill – partial fill of open‑to‑close gaps within the first hour -- Large overnight price gaps tend to revert partially during the first 60 minutes of trading, providing a short‑term mean‑reversion opportunity. Data source: CBOE LiveVol 1‑Day Options and Futures data (https://www.cboe.com). Cost: paid. Instrument fit: 0dte.

## Research Question for Chef
Overnight Gap‑Fill – partial fill of open‑to‑close gaps within the first hour -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE LiveVol 1‑Day Options and Futures data (https://www.cboe.com)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:overnight-gapfill-partial-fill-of-opento) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
