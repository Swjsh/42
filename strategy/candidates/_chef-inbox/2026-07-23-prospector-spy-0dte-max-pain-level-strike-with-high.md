# Chef Inbox — SPY 0DTE Max Pain Level – strike with highest aggregate open interest 

**Routed by:** Gamma_Prospector 2026-07-23
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Max Pain Level – strike with highest aggregate open interest for the day's expirations -- The max‑pain strike often acts as a price magnet on expiration day, helping to forecast intraday price drift for 0DTE option positions. Data source: CBOE Options Open Interest data for SPY (CBOE DataShop). Cost: paid. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Max Pain Level – strike with highest aggregate open interest for the day's expirations -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE Options Open Interest data for SPY (CBOE DataShop)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-max-pain-level-strike-with-high) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-07-23 ~07:xx ET conductor (AFTERHOURS, acting as chef, backlog triage):
STAYS OPEN, REFRAMED -- downgrade the "Cost: paid" framing. Max Pain needs open interest
across the day's full strike chain -- the SAME Alpaca options snapshots family used for
greeks/IV (fleet_broker.get_option_greeks) plausibly also carries OI per contract (Alpaca's
snapshot endpoint typically returns OI alongside greeks; unverified until a live pull is
inspected). If so, Max Pain is computable free from data we can already reach, no CBOE
DataShop license needed. Not attempted this fire (needs a full-chain OI puller + daily
max-pain-strike calc, real new work) -- flagged as the likely free path before any paid-
vendor ask reaches J. -->
