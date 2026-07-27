# Chef Inbox — Front‑month to second‑month basis (term structure) of MES/NQ futures

**Routed by:** Gamma_Prospector 2026-07-26
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `futures_positioning` surfaced: Front‑month to second‑month basis (term structure) of MES/NQ futures -- A steepening or flattening basis reflects changing expectations of near‑term supply/demand and can signal imminent swing reversals. Data source: CME settlement prices accessed via Quandl CME Futures Term Structure dataset (free delayed) or CME DataMine API (real‑time). Cost: paid. Instrument fit: mes.

## Research Question for Chef
Front‑month to second‑month basis (term structure) of MES/NQ futures -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: CME settlement prices accessed via Quandl CME Futures Term Structure dataset (free delayed) or CME DataMine API (real‑time)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: futures_positioning:frontmonth-to-secondmonth-basis-term-str) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
