# Chef Inbox — WallStreetBets sentiment via Pushshift Reddit API

**Routed by:** Gamma_Prospector 2026-08-18
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: WallStreetBets sentiment via Pushshift Reddit API -- Aggregated bullish/bearish comment volume can foreshadow retail‑driven spikes in SPY options activity. Data source: Pushshift Reddit API (https://pushshift.io/) – query r/wallstreetbets for daily sentiment scores. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
WallStreetBets sentiment via Pushshift Reddit API -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: Pushshift Reddit API (https://pushshift.io/) – query r/wallstreetbets for daily sentiment scores
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:wallstreetbets-sentiment-via-pushshift-r) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
