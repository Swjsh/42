# Chef Inbox — SPY 0DTE Put/Call Ratio – ratio of total 0DTE put volume to call volum

**Routed by:** Gamma_Prospector 2026-07-28
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Put/Call Ratio – ratio of total 0DTE put volume to call volume for SPY options expiring same day -- Extreme PCR readings signal contrarian sentiment spikes that often precede short-term mean-reversion in SPY price. Data source: CBOE Equity Put/Call Ratio for SPY 0DTE, available via CBOE DataShop API (free registration) or as symbol $PCALL_SPX_0DTE from most market data vendors. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Put/Call Ratio – ratio of total 0DTE put volume to call volume for SPY options expiring same day -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE Equity Put/Call Ratio for SPY 0DTE, available via CBOE DataShop API (free registration) or as symbol $PCALL_SPX_0DTE from most market data vendors
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-putcall-ratio-ratio-of-total-0d) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none


<!-- NOTE 2026-08-22 ~04:xx ET conductor (WEEKEND, acting as chef, CHEF-INBOX-BACKLOG-DRAIN family-dedupe sweep): received 3 fold-in(s) from the same family, no new information -- 2026-08-06-prospector-intraday-spy-0dte-putcall-ratio-pcr-by-s.md, 2026-08-15-prospector-spy-0dte-putcall-ratio-pcr-calculated-fr.md, 2026-08-19-prospector-intraday-spy-putcall-ratio-pcr-for-0dte-.md -->
