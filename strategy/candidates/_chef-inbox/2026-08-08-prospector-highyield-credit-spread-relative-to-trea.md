# Chef Inbox — High‑Yield credit spread relative to Treasuries

**Routed by:** Gamma_Prospector 2026-08-08
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `cross_asset_signals` surfaced: High‑Yield credit spread relative to Treasuries -- Widening HYG‑10Y spread signals credit market stress and risk‑off bias, useful for shorting SPY 0DTE or MES/MNQ, while tightening spread indicates risk appetite and a bullish tilt. Data source: ICE BofA US High Yield Index (HYG) spread data via Bloomberg Terminal or ICE Data Services. Cost: paid. Instrument fit: both.

## Research Question for Chef
High‑Yield credit spread relative to Treasuries -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: ICE BofA US High Yield Index (HYG) spread data via Bloomberg Terminal or ICE Data Services
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:highyield-credit-spread-relative-to-trea) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
