# Chef Inbox — High‑yield corporate bond spread (BAA‑AAA) as credit risk gauge

**Routed by:** Gamma_Prospector 2026-08-21
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `cross_asset_signals` surfaced: High‑yield corporate bond spread (BAA‑AAA) as credit risk gauge -- Widening high‑yield spread signals credit stress and equity downside risk, offering a cross‑asset risk indicator for SPY options and futures. Data source: ICE BofA US High Yield Index (HYG) vs Investment Grade Index (LQD) via Bloomberg or ICE Data Services. Cost: paid. Instrument fit: both.

## Research Question for Chef
High‑yield corporate bond spread (BAA‑AAA) as credit risk gauge -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: ICE BofA US High Yield Index (HYG) vs Investment Grade Index (LQD) via Bloomberg or ICE Data Services
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:highyield-corporate-bond-spread-baaaaa-a) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
