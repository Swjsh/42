# Plan 3 — Additional Decision Inputs (volume, events, regime)

> J's 2026-06-24 ask: "what other indicators may help us see that — like volume, what current events were going on, or market status overall."

## The question
Beyond price + ribbon, which inputs measurably improve how the engine reads key levels? Assess each for *incremental* edge on the level plays — don't bolt on indicators for their own sake (C3/C4: SPY-price edge ≠ option edge; beat the null).

## Inputs to assess
1. **Volume** — relative volume (vs 20-bar avg, already partially used as `filter_9_vol_multiplier`), volume profile / HVN-LVN nodes near levels, and reclaim/rejection volume confirmation. Does volume-confirmed level-play beat unconfirmed?
2. **Current events / catalysts** — the `scout` persona already writes `news.json`; how deeply is it wired into the entry decision? Should a level-play near a catalyst be sized up/down or blocked? (today: PCE tomorrow was the overhang.)
3. **Market status / regime** — overall trend vs chop, SPY vs key MAs on the day, breadth proxy, **VIX *character* not level** (C5). Regime should switch *which* strategy fires (trend setups vs the range-scalp from `RANGE-SCALP-REGIME-STRATEGY`).

## Method
Per input: measure its lift on the anchor day-set (real fills), disclose, keep only inputs that beat the random/null. Each surviving input → a confluence modifier or a regime switch, validated under OP-22.

## Deliverable
- Per-input value table (lift vs null, keep/drop).
- The kept inputs wired as confluence/size/regime modifiers — not vetoes.

## Owner / status
Background research agent (spawned 2026-06-24). Advisory first.
