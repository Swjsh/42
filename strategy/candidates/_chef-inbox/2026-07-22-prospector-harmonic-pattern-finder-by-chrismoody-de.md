# Chef Inbox — Harmonic Pattern Finder by ChrisMoody – detects Gartley, Bat, Butterfl

**Routed by:** Gamma_Prospector 2026-07-22
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `tv_community_indicators` surfaced: Harmonic Pattern Finder by ChrisMoody – detects Gartley, Bat, Butterfly, and Crab formations -- Flags precise geometric reversal patterns, offering high‑probability entry zones absent from current EMA/RSI setup. Data source: Public Pine Script library, author "ChrisMoody", script "Harmonic Pattern Finder" (https://www.tradingview.com/script/… ). Cost: $0. Instrument fit: both.

## Research Question for Chef
Harmonic Pattern Finder by ChrisMoody – detects Gartley, Bat, Butterfly, and Crab formations -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Public Pine Script library, author "ChrisMoody", script "Harmonic Pattern Finder" (https://www.tradingview.com/script/… )
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:harmonic-pattern-finder-by-chrismoody-de) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-07-23 ~07:xx ET conductor (AFTERHOURS, acting as chef, backlog triage):
STAYS OPEN, REFRAMED. Harmonic patterns (Gartley/Bat/Butterfly/Crab) are a well-documented,
public zigzag+Fibonacci-ratio geometric algorithm -- genuinely computable in pure Python from
cached OHLCV without any TV dependency (unlike the S/R-zone items, this one was never
actually TV-locked, the prospector just cited a TV script as the discovery source). Real
scope risk: harmonic detectors are notorious for firing constantly on noise (the C27
"fires >80% of days = measures noise" lesson applies directly) -- any build MUST include
a naive-fire-rate audit before a single backtest number is trusted. Next bounded step: build
the pure zigzag+ratio detector + immediately run the C27 fire-rate sanity check before
spending real-fills budget on it. -->

<!-- NOTE 2026-08-05 ~05:45-06:15 ET conductor (AFTERHOURS, acting as chef, CHEF-INBOX-BACKLOG-DRAIN dedup pass): CONSOLIDATED -- canonical for the harmonic-pattern-detector family (Gartley/Bat/Butterfly/ABCD, different Pine Script authors, same underlying idea). Both instances self-label $0. -->


<!-- NOTE 2026-08-22 ~04:xx ET conductor (WEEKEND, acting as chef, CHEF-INBOX-BACKLOG-DRAIN family-dedupe sweep): received 2 fold-in(s) from the same family, no new information -- 2026-08-06-prospector-harmonic-pattern-indicator-by-alex-grove.md, 2026-08-19-prospector-hm-pattern-scanner-public-pine-script-by.md -->
