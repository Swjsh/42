# Chef Inbox — Alpha Vantage Intraday OHLC and Technical Indicators for SPY

**Routed by:** Gamma_Prospector 2026-07-21
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:openai/gpt-oss-20b:free

## The Finding
Prospector beat `data_feeds_free` surfaced: Alpha Vantage Intraday OHLC and Technical Indicators for SPY -- Offers free intraday price bars and pre‑computed indicators (e.g., SMA, RSI) that can be used to generate momentum signals for 0DTE SPY options. Data source: Alpha Vantage API (https://www.alphavantage.co). Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
Alpha Vantage Intraday OHLC and Technical Indicators for SPY -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: Alpha Vantage API (https://www.alphavantage.co)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:alpha-vantage-intraday-ohlc-and-technica) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
