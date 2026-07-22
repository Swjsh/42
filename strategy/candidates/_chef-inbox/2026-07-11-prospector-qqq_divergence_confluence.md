# Chef Inbox — Label every ribbon_ride signal with QQQ simultaneous behavior at its c

**Routed by:** Gamma_Prospector 2026-07-11
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** J+fable-2026-07-10 (CROSS-TICKER-BRAINSTORM)

## The Finding
Prospector beat `cross_asset_signals` surfaced: Label every ribbon_ride signal with QQQ simultaneous behavior at its corresponding level (reclaimed/failed/none); stratify P&L; if agreement-cohort dominates, wire ONE composite breadth-agreement feature (QQQ sync + TICK/ADD) as a scored signal-quality input, never a hard block -- SPX is its mega-caps: a SPY level break unconfirmed by QQQ at its own equivalent level is the weak-break/whipsaw class (2026-07-09 exhibit). Data source: QQQ 5m bars (Alpaca/yfinance; cached SPY replay machinery reusable) -- zero new feeds. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
Label every ribbon_ride signal with QQQ simultaneous behavior at its corresponding level (reclaimed/failed/none); stratify P&L; if agreement-cohort dominates, wire ONE composite breadth-agreement feature (QQQ sync + TICK/ADD) as a scored signal-quality input, never a hard block -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: QQQ 5m bars (Alpaca/yfinance; cached SPY replay machinery reusable) -- zero new feeds.
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: qqq_divergence_confluence) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none

<!-- NOTE 2026-07-21 ~20:40 ET conductor (AFTERHOURS, acting as chef): STILL OPEN, HIGHEST-
READINESS item in the whole chef-inbox backlog after this fire's triage pass -- flagging for
next chef fire priority. The design is FULLY SPEC'D already (not by prospector's swarm, but by
J's own 2026-07-10 fable session): markdown/planning/CROSS-TICKER-BRAINSTORM-2026-07-10.md
calls this "battery-ready," specifies the exact method (label every ribbon_ride signal with
QQQ's simultaneous behavior at its own equivalent level: reclaimed/failed/none; stratify P&L;
wire as ONE scored composite feature, never a hard block -- explicitly NOT the TICK/ADD
internals also named in that doc, which this fire's parallel triage confirmed are NOT
fetchable free via yfinance, 404 on ^TICK/^ADD/^TRIN). Zero new external data-feed risk (QQQ
bars via Alpaca/yfinance, same mechanism as SPY). NOT executed this fire: doing it properly
needs fetching real QQQ 5m bars for the ribbon_ride signal population's dates (not just a
lightweight triage check) -- a legitimate, separate, real backtest task for a future chef fire
with its own budget, not folded into this inbox-hygiene pass. -->

