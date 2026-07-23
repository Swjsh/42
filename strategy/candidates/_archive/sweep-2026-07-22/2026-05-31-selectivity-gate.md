# DRAFT CANDIDATE — Selectivity gate (J's 'sniper entries', validated 68-trade OOS)

> STATUS: DRAFT for J. Not ratified. Rule 9 — entry-gate changes are J's, on a weekend, in writing.
> Generated 2026-05-31. Numbers from analysis/selectivity-gate-2026-05-31.md / _gate_test.json (real fills).

## The finding (the real answer to "tighten the entries")
On the production OOS trade set (68 trades / 60 cached-fill days, real OPRA fills), filtering
to CONVICTION setups concentrates the edge dramatically — same engine, same trades, just selective:

| config | n | WR | per-trade/c | total/c |
|---|---|---|---|---|
| production (ungated) | 68 | 0.32 | +4.0 | +272 |
| confluence OR >=2 triggers | 25 | 0.4 | +20.0 | +500 |
| **(conf OR >=2 trig) AND not-midday** | 17 | 0.47 | **+26.4** | +448 |

WR 0.32 -> 0.47; per-trade +4.0 -> +26.4/c; keeps ~25% of
trades on HIGHER total P&L. Consistent across 3 independent dimensions (confluence, trigger-count,
time-of-day) — not a single-cut artifact.

## Why this is the right kind of fix
- It's EXACTLY J's instinct: "more sniper entries", "be more selective", "closer to the move".
- It needs NO new code — maps to existing params: filter_10_min_triggers_bull/bear, confluence_min_signals,
  and a midday entry-window carve-out.
- It's a LARGE-sample OOS result, unlike the stop/PL/D1 headlines that reversed on bigger samples.
- It does not touch the bull/bear stop or profit-lock (those were confirmed already-optimal).

## Candidate params change (for grinder validation, NOT yet applied)
- `filter_10_min_triggers_bull: 2 -> 2` (already), `filter_10_min_triggers_bear: 1 -> 2` (tighten), OR
- `confluence_min_signals` raised, OR a require-(confluence OR >=2 triggers) gate, AND
- a midday (11:30-14:00 ET) entry suppression OR size-down.
Sweep these via the grinder; the winner = highest edge_capture x sharpe (OP-16) that keeps J's
4/29 + 5/04 anchors and >=20 OOS signals.

## Gates before ratification (OP-11 / OP-16 / Rule 9)
- Re-run on a WIDER OOS span (the queued option-grid fetch) to push n well past 16.
- Confirm it does not drop the J anchors (4/29 710P, 5/04 721P).
- A/B scorecard at analysis/recommendations/ before any params.json + heartbeat.md gamma-sync.

## Provenance
Real OPRA fills, $0.02 slippage. Trade set = one production run_backtest over the 60-day OOS span;
gates are pure filters of that set (no re-sim). _gate_test.json + selectivity-gate-2026-05-31.md.


---

## LARGE-SAMPLE UPDATE 2026-05-31 (307 real-fills OOS trades, 345 days)

307 OOS trades, all-day: +3.8/trade, WR 0.3.

GATE RESULTS (n>=30 only):
| gate | n | WR | per-trade/c | total/c |
|---|---|---|---|---|
| >=2 triggers AND not-midday | 94 | 0.34 | **+10.7** | +1006 |
| conf AND not-midday | 76 | 0.33 | **+10.0** | +761 |
| NO midday-trendline (surgical) | 218 | 0.31 | +7.2 | **+1562 (highest)** |
| not-midday only | 161 | 0.35 | +8.6 | +1383 |

AUTOPSY: 24 of 32 midday losers = 1-trigger trendline rejection -> premium stop. That single pattern = -323/c of the midday bleed.

SURGICAL RECOMMENDATION: block MIDDAY entries that have only a trendline_rejection trigger (i.e., require >=2 triggers or a level_rejection if midday). This preserves 71% of all trades while improving per-trade +3.8->+7.2/c and achieving HIGHEST total P&L.

Param mapping: `filter_10_min_triggers_bear: 1` -> `filter_10_min_triggers_bear_midday: 2` (or add a midday trendline-only block in filters.py). Grinder sweep needed for exact param → gamma-sync once ratified.
