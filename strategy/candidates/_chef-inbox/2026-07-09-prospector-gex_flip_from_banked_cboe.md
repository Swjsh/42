# Chef Inbox — Tag every 0DTE session by which side of the CBOE zero-gamma-flip SPY c

**Routed by:** Gamma_Prospector 2026-07-09
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** fable-2026-07-09

## The Finding
Prospector beat `options_structure_metrics` surfaced: Tag every 0DTE session by which side of the CBOE zero-gamma-flip SPY closed on, using the archive Gamma_CboeOiBank already banks -- Dealer hedging flips from move-dampening (positive gamma) to move-amplifying (negative gamma) at the zero-gamma strike -- a regime tag no current filter reads. Data source: journal/gex-archive/*-cboe.json (Gamma_CboeOiBank, free CBOE CDN, 14 sessions banked as of 2026-07-09) + gex_regime.py (already built). Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
SPY's proximity to the CBOE-derived zero-gamma flip point (the strike where net dealer GEX crosses from negative to positive) predicts a continuation-vs-reversion regime for 0DTE entries: price BELOW the flip (negative gamma) sees dealer hedging AMPLIFY moves (favor breakout/continuation setups), price ABOVE the flip (positive gamma) sees dealer hedging DAMPEN moves (favor fade/reversion setups, penalize breakout chases).

## Backtest Request
Data: journal/gex-archive/*-cboe.json (Gamma_CboeOiBank, free CBOE CDN, banking daily since 2026-06-22 -- 14 sessions on disk as of 2026-07-09, ZERO new fetch needed) joined by date to the existing real-OPRA-fills 0DTE trade log. gex_regime.py (net-GEX sign / zero-gamma-flip / wall computation) is ALREADY BUILT -- zero new code needed to read the archive, only to wire it into a backtest join.
Null hypothesis: trade outcome (win/loss, MFE, stop-hit rate) for a given setup is INDEPENDENT of which side of the zero-gamma flip SPY closed the prior session on -- i.e. the GEX regime tag adds no discriminating power over the engine's existing filters.
Pass bar: per gex_regime.assess_backtest_feasibility, a well-powered backtest needs >= 60-90 as-of days (14 banked as of 2026-07-09 -- this stub is CHEAPEST-FIRST bookkeeping, not a request to run the full battery early). Until the floor clears, the bounded FIRST deliverable is NOT a backtest: it is (a) a feasibility/continuity check confirming the archive is still accruing daily (Gamma_CboeOiBank + gex_archive_health.py already do this) and (b) a PRE-REGISTERED backtest design (exact join key, exact null, exact OP-16 edge_capture pass bar) filed now so the day the day-count crosses the floor there is zero fresh-design lag. Cross-reference: 'CLIMB-LADDER-NEXT-RUNG-IS-CLASS' in automation/overnight/queue.md already tracks this exact wait -- this stub gives Chef the pre-registered plan to execute the moment it clears, instead of re-deriving it from scratch then.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: gex_flip_from_banked_cboe) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
