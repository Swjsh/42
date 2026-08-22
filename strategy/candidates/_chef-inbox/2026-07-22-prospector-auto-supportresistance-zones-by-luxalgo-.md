# Chef Inbox — Auto Support/Resistance Zones by LuxAlgo – algorithmic zone detection 

**Routed by:** Gamma_Prospector 2026-07-22
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `tv_community_indicators` surfaced: Auto Support/Resistance Zones by LuxAlgo – algorithmic zone detection from swing highs/lows -- Generates statistically significant support and resistance rectangles, giving a structural map beyond manual trendlines. Data source: Public Pine Script library, author "LuxAlgo", script "Auto Support/Resistance Zones" (https://www.tradingview.com/script/… ). Cost: $0. Instrument fit: both.

## Research Question for Chef
Auto Support/Resistance Zones by LuxAlgo – algorithmic zone detection from swing highs/lows -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Public Pine Script library, author "LuxAlgo", script "Auto Support/Resistance Zones" (https://www.tradingview.com/script/… )
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:auto-supportresistance-zones-by-luxalgo-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-07-23 ~07:xx ET conductor (AFTERHOURS, acting as chef, backlog triage):
STAYS OPEN, REFRAMED -- CANONICAL for the swing-clustering S/R-zone family (folds in the
2026-07-11 Zeiierman duplicate, closed separately with a pointer here). Same tool-availability
finding as the volume-shelf item: no tradingview-prefixed tool is bound to this session
type, so pulling the literal community Pine script is not an option here -- but swing-high/
low clustering into zones is a standard, well-documented TA technique computable in pure
Python from cached OHLCV (find local swing pivots, cluster by price proximity within a zone
band per the levels-are-zones doctrine, weight by touch recency/count). Next bounded step:
build the pure-Python clusterer and null-test it the same way as level_memory.py before any
wiring proposal -- do not chase the specific TV script, build the equivalent primitive. -->


<!-- NOTE 2026-08-22 ~04:xx ET conductor (WEEKEND, acting as chef, CHEF-INBOX-BACKLOG-DRAIN family-dedupe sweep): received 2 fold-in(s) from the same family, no new information -- 2026-08-05-prospector-auto-support-resistance-zones-by-zeiierm.md, 2026-08-15-prospector-auto-support-and-resistance-levels-by-ze.md -->
