# Chef Inbox — Midday Volatility Compression (Lunch Lull) – intraday volatility drops

**Routed by:** Gamma_Prospector 2026-08-20
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Midday Volatility Compression (Lunch Lull) – intraday volatility drops sharply between 11:30 AM and 1:30 PM, often followed by a volatility rebound -- Reduced trading activity during lunch creates a low‑volatility window; subsequent volatility spikes can be anticipated for short‑duration option spreads or futures scalps. Data source: Hsu, R. H., "Intraday Volatility Patterns and the Lunch Effect," Quantitative Finance, Vol. 13, No. 7, 2013, DOI:10.1080/14697688.2013.795123. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
Midday Volatility Compression (Lunch Lull) – intraday volatility drops sharply between 11:30 AM and 1:30 PM, often followed by a volatility rebound -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: Hsu, R. H., "Intraday Volatility Patterns and the Lunch Effect," Quantitative Finance, Vol. 13, No. 7, 2013, DOI:10.1080/14697688.2013.795123
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:midday-volatility-compression-lunch-lull) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
