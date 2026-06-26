---
name: trendline-draw
description: Auto-detect, draw, and log respected price trendlines (ascending support / resistance rails) off SPY 5m swing pivots, with live break levels. Use when J says "draw the trend line", "where does the trend break", "review the trendlines", or as the engine's price-structure read. Built 2026-06-26 (J: "draw your own trendlines... maybe a skill").
---

# trendline-draw

Turns the manual "draw a line through the higher-lows and watch the break" into a repeatable,
logged capability. The math + respect-scoring lives in `backtest/autoresearch/trendline_engine.py`
(pure stdlib, un-blockable data path); this skill orchestrates run -> draw -> report.

## When to invoke
- J asks to draw a trendline / "where does it break" / "review the trendlines".
- During a live setup review when the trend is defined by higher-lows (support) or lower-highs (resistance).
- As the price-structure read that complements the lagging ribbon (a trendline break = Break-of-Structure).

## Steps
1. **Detect + log** (this also writes the record J asked for):
   ```
   cd backtest && .venv/Scripts/python.exe -m autoresearch.trendline_engine
   ```
   Output per line: anchors, slope, **line value now**, **respect_count**, **status** (INTACT / TESTING / BROKEN),
   the **BREAK level** (a 5m CLOSE beyond it = trend break = signal), and ready-made `draw_shape` anchor params.
   It auto-appends every detected line to `analysis/trendlines/trendline-log.jsonl`.

2. **Draw on the chart** (only if TV is up — check `mcp__tradingview__tv_health_check` first; chart should be `BATS:SPY`).
   For each line, call `mcp__tradingview__draw_shape` with the emitted params:
   ```
   shape="trend_line"
   point  = { time: <A_unix>, price: <A_price> }
   point2 = { time: <proj_unix>, price: <proj_price> }   # forward point ON the line -> extends right
   overrides = {"linecolor":"#26a69a"(support)|"#ef5350"(resistance),"linewidth":2,"extendRight":true,
                "showLabel":true,"text":"<kind> | break = 5m close <below|above> ~<break_level>"}
   ```

3. **Report to J**: the break level(s), respect_count, status, and the actionable rule — e.g.
   "support at ~733.2, respected 12x, INTACT; a 5m close below = short trigger." Note if a steep line is
   rising *into* a stalling price (the break sets up from a stall, not just a drop).

## Success criteria
- At least one respected line (respect_count >= 1) detected and logged.
- Drawn on the live chart (or break levels reported analytically if TV is down).
- The break level + status communicated as an actionable trigger.

## Notes / roadmap
- A trendline break IS a Break-of-Structure; pair with `crypto/lib/market_structure.py` (BOS/CHoCH + HH/HL/LH/LL).
- The autonomous engine version (engine fits + watches + fires on the break itself) sits behind the
  structure-veto wiring on the price-structure roadmap -- this skill is the manual-to-automatic bridge.
- v1 picks the single most-respected line per side; refine toward multi-line / span-weighted anchors as needed.
