# Chef Inbox — The Opening Range Breakout (ORB) predictive power for intraday trend d

**Routed by:** Gamma_Prospector 2026-07-23
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:google/gemma-4-31b-it:free

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: The Opening Range Breakout (ORB) predictive power for intraday trend direction -- Exploits the price discovery phase where the first 15-30 minutes of trading establish the day's dominant bias. Data source: Tukey's 'Exploratory Data Analysis' principles applied to SPY 1m OHLC data via Polygon.io API. Cost: paid. Instrument fit: both.

## Research Question for Chef
The Opening Range Breakout (ORB) predictive power for intraday trend direction -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Tukey's 'Exploratory Data Analysis' principles applied to SPY 1m OHLC data via Polygon.io API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:the-opening-range-breakout-orb-predictiv) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-08-05 ~05:45-06:15 ET conductor (AFTERHOURS, acting as chef, CHEF-INBOX-BACKLOG-DRAIN dedup pass): CORRECTED + CONSOLIDATED -- canonical for the ORB family. Original ask self-labeled paid; the 07-29 and 08-03 recurrences correctly identify this is $0 and needs NO new data: first-30-min high/low range is computable directly from the already-cached SPY 5m/1m OHLCV (backtest/data/spy_5m_*.csv). Genuinely viable, unresearched candidate -- next bounded step: backtest ORB range breakout/fade using the existing bar cache, no new ingestion needed. -->


<!-- NOTE 2026-08-22 ~04:xx ET conductor (WEEKEND, acting as chef, CHEF-INBOX-BACKLOG-DRAIN family-dedupe sweep): received 3 fold-in(s) from the same family, no new information -- 2026-08-06-prospector-opening-range-breakout-orb-earlysession-.md, 2026-08-15-prospector-opening-range-breakout-orb-effect-intrad.md, 2026-08-20-prospector-opening-range-breakout-orb-price-moves-b.md -->
