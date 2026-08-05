# Chef Inbox — Add TradingView's Volume Profile (Visible Range) study and read its hi

**Routed by:** Gamma_Prospector 2026-07-10
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** J-2026-07-09

## The Finding
Prospector beat `tv_community_indicators` surfaced: Add TradingView's Volume Profile (Visible Range) study and read its high-volume-node 'shelves' as a structural level source -- High-volume nodes mark where the market previously accepted price for extended time -- SPY/MES tend to pause, reject, or accelerate through them, independent of Gamma's own trendline/level-memory engines. Data source: TradingView built-in Volume Profile (Visible Range) study via the existing TV MCP (chart_manage_indicator + data_get_pine_boxes/lines). Cost: $0. Instrument fit: both.

## Research Question for Chef
Add TradingView's Volume Profile (Visible Range) study and read its high-volume-node 'shelves' as a structural level source -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView built-in Volume Profile (Visible Range) study via the existing TV MCP (chart_manage_indicator + data_get_pine_boxes/lines).
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: volume_shelf_tv_vp) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-07-21 ~20:40 ET conductor (AFTERHOURS, acting as chef): CONSOLIDATED, still open
(real implementation work remains, not attempted this fire). This is the canonical item for the
TV Volume-Profile-shelf family (higher provenance than a swarm re-discovery: J-directed
2026-07-09). One duplicate folded in: 2026-07-11-prospector-volume-profile-visible-range-vpvr-
shows-.md.DONE (identical ask, swarm-sourced, no new information). The TV MCP tools this item
needs (chart_manage_indicator, data_get_pine_boxes) are confirmed present in this session's tool
surface -- the mechanism is available, just not yet wired into a backtest. Next bounded step:
add the Volume Profile study to a live TV chart session, pull shelves via data_get_pine_boxes
for a sample window, compare against Gamma's existing trendline/level-memory levels for overlap
vs incremental signal before committing to a full backtest. -->


<!-- NOTE 2026-07-23 ~07:xx ET conductor (AFTERHOURS, acting as chef, backlog triage):
STAYS OPEN, REFRAMED -- CANONICAL for the value-area/POC family (folds in the 2026-07-11
Market-Profile-TPO duplicate, closed separately with a pointer here). Correction to the prior
2026-07-21 note's premise: this session's actual bound tool list has ZERO tradingview-
prefixed tools despite the MCP-instructions block always being injected (confirmed this fire,
matches the DOJO-BUILD-HANDOFF finding) -- so "pull shelves via data_get_pine_boxes" is NOT
available to a conductor-class session. HOWEVER the underlying computation does not require
TV at all: a volume profile is a volume-weighted price histogram over a lookback window,
computable directly from the already-cached SPY 5m OHLCV+volume bars
(backtest/data/spy_5m_*.csv, volume column CONFIRMED present this fire). Next bounded step
for a future fire: build a pure-Python compute_volume_profile(bars, bin_width) -> HVN/LVN
shelf detector, then test shelf-proximity as a level source the SAME way level_memory.py was
null-tested (C25/C27 discipline -- naive-fire-rate vs random-level null, not just "does it
correlate"). No TV MCP dependency required for the research phase. -->

<!-- NOTE 2026-08-05 ~05:45-06:15 ET conductor (AFTERHOURS, acting as chef, CHEF-INBOX-BACKLOG-DRAIN dedup pass): 2 newer near-duplicate(s) folded in this fire -- 2026-07-28-prospector-market-profile-tpo-built-in-tradingview-.md (same value-area/POC family (TPO framing) -- reduces to the same testable hypothesis per the 2026-07-23 note already on this canonical); 2026-08-02-prospector-market-profile-tpo-by-alex-grover.md (same idea, 2nd TPO-framing recurrence). Canonical status unchanged: STILL OPEN -- canonical for the value-area/POC/volume-profile/market-profile family; next bounded step already specified: build compute_volume_profile(bars, bin_width) from cached SPY 5m OHLCV, no TV MCP dependency needed. -->
