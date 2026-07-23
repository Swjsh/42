# Chef Inbox — SPY 0DTE Implied Volatility Skew (10Δ vs 25Δ) – measures the relative 

**Routed by:** Gamma_Prospector 2026-07-22
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Implied Volatility Skew (10Δ vs 25Δ) – measures the relative IV of near‑the‑money puts versus calls -- Skew reflects market asymmetry expectations; a steep skew often precedes sharp moves, giving a predictive edge for intraday option pricing. Data source: OptionMetrics US Equities Options Database (IV surface) or Bloomberg B‑PIPE IV data. Cost: paid. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Implied Volatility Skew (10Δ vs 25Δ) – measures the relative IV of near‑the‑money puts versus calls -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: OptionMetrics US Equities Options Database (IV surface) or Bloomberg B‑PIPE IV data
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-implied-volatility-skew-10δ-vs-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-07-23 ~07:xx ET conductor (AFTERHOURS, acting as chef, backlog triage):
STAYS OPEN, REFRAMED -- downgrade the "Cost: paid" framing. IV per contract is ALREADY
fetched free via the same Alpaca options snapshots endpoint used by _capture_greeks /
get_option_greeks (log-only today, G8) -- a 10-delta vs 25-delta skew read is a strike-
selection detail on top of data we already pull, not a reason to license OptionMetrics/
Bloomberg B-PIPE. Not attempted this fire (needs a proper strike-to-delta mapping + skew-
over-time capture loop, real new work) -- flagged as the likely free path. -->
