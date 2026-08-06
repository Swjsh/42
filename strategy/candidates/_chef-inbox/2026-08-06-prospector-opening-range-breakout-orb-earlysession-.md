# Chef Inbox — Opening Range Breakout (ORB) – early‑session range breakout predicts d

**Routed by:** Gamma_Prospector 2026-08-06
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Opening Range Breakout (ORB) – early‑session range breakout predicts direction -- If price breaks above (or below) the first 30‑minute high‑low range, it often continues in that direction, giving a short‑term momentum edge. Data source: NYSE TAQ intraday data via WRDS (https://wrds-web.wharton.upenn.edu). Cost: paid. Instrument fit: both.

## Research Question for Chef
Opening Range Breakout (ORB) – early‑session range breakout predicts direction -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: NYSE TAQ intraday data via WRDS (https://wrds-web.wharton.upenn.edu)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:opening-range-breakout-orb-earlysession-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
