# Chef Inbox — ICE BofA US High Yield OAS (credit spread) as a risk‑sentiment gauge f

**Routed by:** Gamma_Prospector 2026-08-04
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `cross_asset_signals` surfaced: ICE BofA US High Yield OAS (credit spread) as a risk‑sentiment gauge for equity index futures -- Widening high‑yield OAS (>10 bps intraday) signals rising credit risk and tends to precede bearish moves in SPY 0DTE and MES/MNQ; tightening spreads signal bullish bias. Data source: ICE BofA US High Yield Index OAS (FRED series BAMLH0A0HYM2), accessible free via FRED API, Bloomberg, or Quandl. Cost: $0. Instrument fit: both.

## Research Question for Chef
ICE BofA US High Yield OAS (credit spread) as a risk‑sentiment gauge for equity index futures -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: ICE BofA US High Yield Index OAS (FRED series BAMLH0A0HYM2), accessible free via FRED API, Bloomberg, or Quandl
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:ice-bofa-us-high-yield-oas-credit-spread) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none


<!-- NOTE 2026-08-22 ~04:xx ET conductor (WEEKEND, acting as chef, CHEF-INBOX-BACKLOG-DRAIN family-dedupe sweep): received 2 fold-in(s) from the same family, no new information -- 2026-08-08-prospector-highyield-credit-spread-relative-to-trea.md, 2026-08-21-prospector-highyield-corporate-bond-spread-baaaaa-a.md -->
