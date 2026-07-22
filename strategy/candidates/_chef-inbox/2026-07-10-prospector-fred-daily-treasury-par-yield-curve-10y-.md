# Chef Inbox — FRED Daily Treasury Par Yield Curve (10Y-2Y spread)

**Routed by:** Gamma_Prospector 2026-07-10
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:google/gemma-4-31b-it:free

## The Finding
Prospector beat `data_feeds_free` surfaced: FRED Daily Treasury Par Yield Curve (10Y-2Y spread) -- Identifies regime shifts in macro risk appetite that correlate with SPY trend persistence or reversals. Data source: Federal Reserve Economic Data (FRED) API. Cost: $0. Instrument fit: both.

## Research Question for Chef
FRED Daily Treasury Par Yield Curve (10Y-2Y spread) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:fred-daily-treasury-par-yield-curve-10y-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-07-21 ~20:40 ET conductor (AFTERHOURS, acting as chef): CONSOLIDATED, still open
(real backtest work remains, not attempted this fire). This is the canonical master for the
FRED/Treasury-yield-curve family -- 4 duplicates/overlaps folded in this fire:
2026-07-12-prospector-10y2y-treasury-yield-spread-ust10yust2y-.md.DONE (exact duplicate),
2026-07-21-prospector-fred-macro-series-10year-treasury-yield-.md.DONE (broader restatement),
2026-07-11-prospector-treasuriesgov-real-time-2y-and-10y-yield.md.DONE (REJECTED as stated --
Treasury.gov's yield curve is daily/EOD, not real-time as claimed; same underlying series FRED
already mirrors with a documented API), and 2026-07-10-prospector-treasury-treasury-bills-3-
month-yield-fl.md.DONE (same FRED ingestion mechanism, different maturity -- DGS3MO -- fold in
as a sub-series once built, not a separate candidate). FRED's API is genuinely free
(registration required, well-documented, stable) -- this is a real, buildable, still-unbuilt
backlog item. Next bounded step: register a FRED API key ($0), pull DGS10/DGS2 (+ DGS3MO) daily
series alongside the 0DTE trade log, test the 10Y-2Y spread level/slope as a macro regime tag
against the standing OP-11/OP-16 pass bar. Not attempted this fire (real backtest + new
API-key registration, out of this triage-pass's budget). -->

