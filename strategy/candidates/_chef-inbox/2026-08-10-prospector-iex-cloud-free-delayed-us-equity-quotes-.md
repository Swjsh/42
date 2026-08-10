# Chef Inbox — IEX Cloud free delayed US equity quotes (including SPY) via IEX API

**Routed by:** Gamma_Prospector 2026-08-10
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `data_feeds_free` surfaced: IEX Cloud free delayed US equity quotes (including SPY) via IEX API -- Delivers sub‑second delayed price and size data that can be used to detect micro‑structure imbalances ahead of regular‑price updates for both SPY options and MES futures. Data source: IEX Cloud Free Tier API (https://iexcloud.io/docs/api/). Cost: $0. Instrument fit: both.

## Research Question for Chef
IEX Cloud free delayed US equity quotes (including SPY) via IEX API -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: IEX Cloud Free Tier API (https://iexcloud.io/docs/api/)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:iex-cloud-free-delayed-us-equity-quotes-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
