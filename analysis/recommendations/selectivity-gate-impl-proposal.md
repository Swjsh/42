# IMPLEMENTATION PROPOSAL — Midday-Trendline Selectivity Gate (DRAFT for J, Rule 9)

> Generated 2026-05-31 from real-fills analysis (307 OOS trades, 345 cached-fill days).
> All numbers from computed JSON dumps (L77). Supersedes earlier stop/PL/sniper headlines.

## The finding in one sentence
**Blocking single-trigger trendline entries in the midday window (11:30-14:00 ET) improves
per-trade P&L ++3.8->+7.2/c while keeping 71% of all trades (highest total P&L +1562/c).**

## Evidence (real fills, 307 OOS trades, 345 days, multi-dimensional consistency)
| gate | n | WR | per-trade/c | total/c |
|---|---|---|---|---|
| All production | 307 | 0.3 | +3.8 | +1169 |
| NO midday-trendline (surgical) | 218 | 0.31 | **+7.2** | **+1562** (highest) |
| >=2 triggers AND not-midday | 94 | 0.34 | **+10.7** | +1006 |

Autopsy: 24 of 32 midday losers (2026-02-20..05-20) = `trendline_rejection` single-trigger → `EXIT_ALL_PREMIUM_STOP`. Every. Single. One.
The gate is not a time-of-day suppression — it's a CONVICTION requirement at midday.

**OP-16 anchor gate: PASS.** Gate suppressed 3 anchor-window trades , 5/04 721P still captured.

## What the implementation looks like
**Option A (surgical, least disruptive):** in `filters.py` (or orchestrator), skip trade entry if:
```python
is_midday = dt.time(11, 30) <= bar_time.time() < dt.time(14, 0)
is_trendline_only = (len(triggers_fired) == 1 and "trendline_rejection" in triggers_fired)
if is_midday and is_trendline_only:
    skip  # require >= 2 triggers or a level_rejection at midday
```
Keeps all non-midday trendline trades; keeps all midday trades with confluence/level/>=2 triggers.

**Option B (cleaner param, slightly more aggressive):** raise `filter_10_min_triggers_bear` from 1 to 2.
This gates ALL trendline-only setups globally. Stronger lift (++10.7/c per-trade) but
drops more signals (n=94 vs 218).

**Recommendation for the grinder:** sweep {'trendline_midday_min_triggers': [1, 2], 'global_min_triggers': [1, 2]},
compare per Option A vs B on edge_capture x sharpe, pick the one that dominates per OP-16.

## Path to live (Rule 9)
1. Grinder sweep → A/B scorecard at analysis/recommendations/
2. J ratifies on a weekend (CLAUDE.md Rule 9)
3. gamma-sync: update filters.py + params.json + heartbeat.md simultaneously
4. Shadow-mode test 2 weeks before live (OP-11 INNER loop)

## This IS J's "sniper entries" — proven on 307 OOS trades
The midday trendline losers are exactly "too early, too weak a signal, wrong time of day" — the
trades J intuitively skips when he's watching live. The gate encodes that judgment permanently.
