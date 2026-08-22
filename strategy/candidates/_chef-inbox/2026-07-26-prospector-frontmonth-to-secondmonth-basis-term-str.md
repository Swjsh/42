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

<!-- NOTE 2026-08-05 ~05:45-06:15 ET conductor (AFTERHOURS, acting as chef, CHEF-INBOX-BACKLOG-DRAIN dedup pass): CORRECTED + CONSOLIDATED -- canonical for the futures calendar-basis family. Original ask self-labeled paid (CME DataMine/Quandl term-structure dataset); the 08-04 recurrence claims $0 via Quandl's free EOD futures chain endpoint (CME_ES1/CME_ES2). Unverified claim, carried forward not independently confirmed this fire. NOTE: 2026-07-31's 'ES vs MES basis' item is a DIFFERENT idea (cross-contract-size basis, not calendar term structure) and is self-labeled paid with no free-path recurrence found -- rejected standalone, not folded here. -->


<!-- NOTE 2026-08-22 ~04:xx ET conductor (WEEKEND, acting as chef, CHEF-INBOX-BACKLOG-DRAIN family-dedupe sweep): received 4 fold-in(s) from the same family, no new information -- 2026-08-08-prospector-futures-curve-and-basis-between-emini-co.md, 2026-08-12-prospector-calendar-spread-basis-between-nearmonth-.md, 2026-08-17-prospector-futures-curve-and-basis-between-frontmon.md, 2026-08-21-prospector-futures-curvebasis-between-frontmonth-an.md -->
