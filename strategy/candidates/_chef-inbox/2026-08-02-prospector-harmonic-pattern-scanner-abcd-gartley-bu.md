# Chef Inbox — Harmonic Pattern Scanner (ABCD, Gartley, Butterfly) by ZigZagTrader

**Routed by:** Gamma_Prospector 2026-08-02
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Harmonic Pattern Scanner (ABCD, Gartley, Butterfly) by ZigZagTrader -- Automatically labels harmonic price patterns on the chart, providing high‑probability reversal zones that complement EMA/RSI signals for 0DTE and futures entries. Data source: Public Pine Script: 'Harmonic Pattern Scanner' by ZigZagTrader (https://www.tradingview.com/script/...). Cost: $0. Instrument fit: both.

## Research Question for Chef
Harmonic Pattern Scanner (ABCD, Gartley, Butterfly) by ZigZagTrader -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Public Pine Script: 'Harmonic Pattern Scanner' by ZigZagTrader (https://www.tradingview.com/script/...)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:harmonic-pattern-scanner-abcd-gartley-bu) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
