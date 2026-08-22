# Chef Inbox — Order Flow Imbalance (OFI) by @Sanjay – cumulative delta proxy for buy

**Routed by:** Gamma_Prospector 2026-07-22
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `tv_community_indicators` surfaced: Order Flow Imbalance (OFI) by @Sanjay – cumulative delta proxy for buyer‑seller aggression -- Measures net buying vs. selling pressure on each tick, providing an order‑flow edge not captured by price‑only indicators. Data source: Public Pine Script library, author "Sanjay", script name "Order Flow Imbalance" (https://www.tradingview.com/script/… ). Cost: $0. Instrument fit: both.

## Research Question for Chef
Order Flow Imbalance (OFI) by @Sanjay – cumulative delta proxy for buyer‑seller aggression -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Public Pine Script library, author "Sanjay", script name "Order Flow Imbalance" (https://www.tradingview.com/script/… )
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:order-flow-imbalance-ofi-by-sanjay-cumul) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-07-23 ~07:xx ET conductor (AFTERHOURS, acting as chef, backlog triage):
STAYS OPEN, BLOCKER CLARIFIED. The real blocker for this one is NOT TV MCP access -- it's
that a genuine order-flow-imbalance / cumulative-delta signal needs bid/ask-classified TICK
or QUOTE data (buyer-initiated vs seller-initiated volume), which is NOT present in anything
we currently cache (5m OHLCV+volume bars carry no bid/ask/tick classification). This is a
genuinely NEW data-source question, not a TV-tool-availability question like the S/R-zone
items. Do not attempt a bar-volume proxy and call it OFI (that's a different, weaker signal
with a different name) -- either source real tick/quote data (cost/vendor decision, flag to
J before any paid vendor) or close this one as infeasible without new data. Left open
pending that decision rather than closed, since it's a genuine fork not yet resolved. -->

<!-- NOTE 2026-08-05 ~05:45-06:15 ET conductor (AFTERHOURS, acting as chef, CHEF-INBOX-BACKLOG-DRAIN dedup pass): CONSOLIDATED -- canonical for the cumulative-delta/order-flow-proxy family (different Pine Script authors, same underlying idea: derive a buy/sell-pressure proxy from price+volume on existing bars, no Level2 data needed). All 3 instances self-label $0. -->

<!-- CORRECTION 2026-08-05 ~06:xx ET conductor (same fire): the note directly above is IMPRECISE
against the 07-23 blocker-clarification note two blocks up -- re-read that note before acting on
this item. QuantNomad's and LuxAlgo's "Cumulative Delta" Pine scripts (the two folded duplicates)
are the SAME bar-volume PROXY the 07-23 note explicitly warns against treating as real OFI (no
bid/ask tick classification, just up/down-candle volume). Folding them here as the same PROXY
family is correct triage (they don't deserve 3 separate open items); it does NOT mean the proxy
is now endorsed as equivalent to true order-flow-imbalance. If chef ever picks this family up,
the two live options are still: (a) test the bar-volume proxy explicitly labeled as a proxy, weaker
claim, lower bar, or (b) source real tick/quote data (new vendor, cost/vendor decision, flag to J
before any paid vendor). -->



<!-- NOTE 2026-08-22 ~04:xx ET conductor (WEEKEND, acting as chef, CHEF-INBOX-BACKLOG-DRAIN family-dedupe sweep): received 4 fold-in(s) from the same family, no new information -- 2026-08-05-prospector-order-flow-heatmap-by-luxalgo-public-pin.md, 2026-08-10-prospector-cumulative-delta-order-flow-by-lazybear-.md, 2026-08-14-prospector-order-flow-imbalance-ofi-by-luxalgo-publ.md, 2026-08-18-prospector-cumulative-delta-public-pine-script-by-l.md -->
