# Chef Inbox — Reddit r/wallstreetbets sentiment via Pushshift API

**Routed by:** Gamma_Prospector 2026-08-14
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `data_feeds_free` surfaced: Reddit r/wallstreetbets sentiment via Pushshift API -- Retail sentiment spikes often precede short‑term moves in SPY/MES, especially on 0DTE expiry days. Data source: Pushshift.io API https://pushshift.io/api-params/. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
Reddit r/wallstreetbets sentiment via Pushshift API -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: Pushshift.io API https://pushshift.io/api-params/
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:reddit-rwallstreetbets-sentiment-via-pus) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
