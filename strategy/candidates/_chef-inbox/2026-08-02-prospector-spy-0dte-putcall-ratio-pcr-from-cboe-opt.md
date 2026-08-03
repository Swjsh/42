# Chef Inbox — SPY 0DTE Put/Call Ratio (PCR) from CBOE Options Tape

**Routed by:** Gamma_Prospector 2026-08-02
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:openai/gpt-oss-120b:free

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Put/Call Ratio (PCR) from CBOE Options Tape -- High PCR signals bearish pressure that often precedes rapid SPY moves, improving timing of gamma scalping entries. Data source: CBOE Options Market Data Feed (OPRA) – real‑time put and call volume for SPY, accessible via Bloomberg API or directly from CBOE (https://www.cboe.com/trading-resources/market-data/). Cost: paid. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Put/Call Ratio (PCR) from CBOE Options Tape -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE Options Market Data Feed (OPRA) – real‑time put and call volume for SPY, accessible via Bloomberg API or directly from CBOE (https://www.cboe.com/trading-resources/market-data/)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-putcall-ratio-pcr-from-cboe-opt) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
