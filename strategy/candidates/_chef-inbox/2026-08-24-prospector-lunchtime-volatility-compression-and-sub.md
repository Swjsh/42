# Chef Inbox — Lunch‑time volatility compression and subsequent breakout in MES

**Routed by:** Gamma_Prospector 2026-08-24
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Lunch‑time volatility compression and subsequent breakout in MES -- Volatility drops sharply between 11:30‑13:30 CT, then often expands in the afternoon, creating a volatility‑breakout opportunity for short‑straddle or directional trades. Data source: Andersen & Bollerslev, 'Intraday Periodicity and Volatility Persistence' (Journal of Financial Economics, 1997); MES 1‑minute bars from CME DataMine. Cost: paid. Instrument fit: mes.

## Research Question for Chef
Lunch‑time volatility compression and subsequent breakout in MES -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: Andersen & Bollerslev, 'Intraday Periodicity and Volatility Persistence' (Journal of Financial Economics, 1997); MES 1‑minute bars from CME DataMine
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:lunchtime-volatility-compression-and-sub) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
