# Chef Inbox — CME Order Imbalance Indicator (OIB) for CME Globex futures

**Routed by:** Gamma_Prospector 2026-08-04
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: CME Order Imbalance Indicator (OIB) for CME Globex futures -- Identifies early buying or selling pressure from order imbalances before the CME auction, giving a predictive edge on MES/MNQ direction. Data source: CME Group website – OIB data via CME Data API (free tier) https://www.cmegroup.com/tools-information.html. Cost: $0. Instrument fit: mes.

## Research Question for Chef
CME Order Imbalance Indicator (OIB) for CME Globex futures -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: CME Group website – OIB data via CME Data API (free tier) https://www.cmegroup.com/tools-information.html
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:cme-order-imbalance-indicator-oib-for-cm) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
