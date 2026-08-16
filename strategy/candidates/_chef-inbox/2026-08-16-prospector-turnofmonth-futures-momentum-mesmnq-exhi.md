# Chef Inbox — Turn‑of‑Month futures momentum – MES/MNQ exhibit a statistically signi

**Routed by:** Gamma_Prospector 2026-08-16
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Turn‑of‑Month futures momentum – MES/MNQ exhibit a statistically significant positive drift in the first two trading days of each month -- Institutional fund inflows at month‑end generate buying pressure that persists into the next month, offering a systematic bias for futures entry. Data source: CME DataMine historical futures ticks (https://datamine.cmegroup.com). Cost: paid. Instrument fit: mes.

## Research Question for Chef
Turn‑of‑Month futures momentum – MES/MNQ exhibit a statistically significant positive drift in the first two trading days of each month -- this carries a testable directional/timing edge for mes.

## Backtest Request
Data: CME DataMine historical futures ticks (https://datamine.cmegroup.com)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:turnofmonth-futures-momentum-mesmnq-exhi) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
