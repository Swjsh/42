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

