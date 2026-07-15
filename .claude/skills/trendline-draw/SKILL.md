---
name: trendline-draw
description: Auto-detect, draw, and log respected price trendlines (ascending support / resistance rails, WICK and BODY anchor families) off SPY 5m swing pivots, with live break levels. Use when J says "draw the trend line", "where does the trend break", "review the trendlines", "draw the engine's trendlines on my chart", or as the engine's price-structure read. Built 2026-06-26 (J: "draw your own trendlines... maybe a skill"); T14 wick/body families + visibility bridge 2026-07-14 (J audit: "why have we not drawn one yet i can see it").
---

# trendline-draw

Turns the manual "draw a line through the higher-lows and watch the break" into a repeatable,
logged, DRAWN capability. The math + respect-scoring lives in
`backtest/autoresearch/trendline_engine.py` (pure stdlib, un-blockable data path); this skill
orchestrates run -> draw -> report.

**J's anchor rule (verbatim, 2026-07-14): "trend lines only respect candle bodies OR wicks, not
both."** The engine detects TWO separate families per side (never mixed within one line):
- **WICK** family: anchors are the bar's low/high, AND must be an ACTUAL protruding wick (>= 10%
  of that bar's range, floored at 5 cents) -- a bar whose low sits a hair below its open/close
  (e.g. a 2-cent "wick") does NOT qualify; it's a body point, not a wick.
- **BODY** family: anchors are `min(open,close)` (support) / `max(open,close)` (resistance) --
  the legitimate second family for bars where the wick is negligible or absent.

## IMPORTANT: this is an ON-DEMAND skill, not a new automated 5-min fire
`draw_shape` / `draw_list` / `draw_remove_one` are TradingView MCP tools -- only callable from a
live Claude+CDP session. The headless pythonw scheduled task (`Gamma_Trendlines`, every 5 min
RTH) can DETECT + LOG lines but structurally CANNOT call MCP tools to draw them (verified:
`draw_shape` only appears in `automation/prompts/*.md` persona instructions, never in a
standalone script). So drawing happens: (a) once daily, embedded in the `Gamma_Premarket`
LLM-driven fire (08:30 ET) -- see that prompt's trendline-draw step; (b) on-demand, any time J or
a live session invokes this skill. Detection/logging stays fully automated either way (unchanged,
every 5 min); DRAWING is not continuously live without a session open to run it.

## When to invoke
- J asks to draw a trendline / "where does it break" / "review the trendlines" / "why isn't this on my chart".
- During a live setup review when the trend is defined by higher-lows (support) or lower-highs (resistance).
- As the price-structure read that complements the lagging ribbon (a trendline break = Break-of-Structure).
- Once daily via `Gamma_Premarket` (08:30 ET) -- see `automation/prompts/premarket.md`.

## Steps

1. **Scoped clear of the ENGINE's own prior drawings (NEVER `draw_clear`, and NEVER the MCP
   `draw_remove_one`/`draw_list` tools -- both are CONFIRMED BROKEN, `"getChartApi is not
   defined"`, same root cause premarket.md's Step 5 already works around; reproduced live
   2026-07-14 during the T14 audit).** `draw_clear` additionally has no scope/tag parameter — it
   wipes EVERY drawing on the chart, including J's own manual lines, so it's disqualified even if
   it worked. Use the proven `ui_evaluate` JS-injection path instead:
   ```
   backtest/.venv/Scripts/python.exe setup/scripts/trendline_draw_state.py list-ids
   ```
   For each printed `entity_id`, read `automation/scripts/tv_ops/remove_drawing.js`, substitute
   `__ENTITY_ID__` → `"<entity_id>"`, and pass the result to
   `mcp__tradingview__ui_evaluate({ expression: <substituted js> })`. It returns
   `{ success, removed_id, removed_type }` (or `{success:false, error:"not_found"}` if the line
   was already removed by hand — treat that as success-for-our-purposes, not a failure). Then:
   ```
   backtest/.venv/Scripts/python.exe setup/scripts/trendline_draw_state.py clear-record
   ```
   (Only clear the record AFTER the chart-side removals actually run -- clearing first and then
   failing a removal would leak an orphaned drawing nothing can find again.)

2. **Detect** (JSON mode, no log side-effect -- this also writes the record J asked for when run
   WITHOUT `--no-log`, e.g. the once-daily premarket fire; on-demand draws use `--no-log` so they
   don't duplicate rows outside the production 5-min cadence):
   ```
   cd backtest && .venv/Scripts/python.exe -m autoresearch.trendline_engine --no-log --json
   ```
   Returns up to 4 lines: wick-support, wick-resistance, body-support, body-resistance (only
   lines that actually scored `respect_count >= 1` are present -- may be fewer than 4). Each line
   carries `anchor_family` ("wick" | "body"), `kind` ("support" | "resistance"), anchors
   (`a_unix`/`a_price`/`b_unix`/`b_price`), the forward projection (`proj_unix`/`proj_price`),
   `status` (INTACT/TESTING/BROKEN), `respect_count`, and `break_level`.

3. **DRAW CAP — at most 2 lines on the chart: the single best-respected line per SIDE
   (support + resistance), selected across BOTH families by `respect_count`.** (J, 2026-07-15:
   "way too many trend lines on the screen" — the 4-line families×sides draw plus his own lines
   was unreadable. All 4 detections still LOG; only the DRAW is capped. State the winning
   line's family in its label.)

4. **Assert before drawing -- never render a mixed-anchor line.** For each line, before calling
   `draw_shape`, sanity-check: `anchor_family` is exactly one of "wick"/"body" (the engine's own
   `_fit` already structurally guarantees this per-line -- see its assert -- this is a cheap
   second layer, not a re-derivation). Never combine two lines' anchors into one shape.

4. **Draw on the chart** (only if TV is up — check `mcp__tradingview__tv_health_check` first;
   chart should be `BATS:SPY`). For each line, call `mcp__tradingview__draw_shape`:
   ```
   shape="trend_line"
   point  = { time: <a_unix>, price: <a_price> }
   point2 = { time: <proj_unix>, price: <proj_price> }   # forward point ON the line -> extends right
   overrides = {"linecolor": <see table>, "linewidth": 2, "extendRight": true,
                "showLabel": true,
                "text": "[<FAMILY>] <kind> | respect x<respect_count> | <status> | break = 5m close <below|above> ~<break_level>"}
   ```
   Color table (family is ALWAYS in the label text too -- color alone must never be the only tell):

   | kind | family | linecolor |
   |---|---|---|
   | support | wick | `#26a69a` (solid teal) |
   | support | body | `#80cbc4` (muted teal) |
   | resistance | wick | `#ef5350` (solid red) |
   | resistance | body | `#ef9a9a` (muted red) |

   After each successful `draw_shape`, record the returned `entity_id`:
   ```
   .venv/Scripts/python.exe setup/scripts/trendline_draw_state.py record --entity-id <id> --kind <support|resistance> --family <wick|body> --label "<summary>"
   ```

5. **Report to J**: the break level(s), respect_count, status, family, and the actionable rule —
   e.g. "WICK support at ~748.9, respected 63x, INTACT; a 5m close below = short trigger. Also a
   BODY support at ~748.7 (44x)." Note if a steep line is rising *into* a stalling price (the
   break sets up from a stall, not just a drop). If the SAME-DAY line J is eyeballing (e.g. a
   premarket low through a mid-morning low) doesn't appear among the top lines, say so explicitly
   — the current scoring (`respect - 5*violations + span*0.1`) favors longer-lived multi-day
   lines over fresh same-day ones; don't silently substitute a different line and imply it's the
   one J asked about.

## Success criteria
- At least one respected line (respect_count >= 1) detected and logged.
- Drawn on the live chart, family-labeled (or break levels reported analytically if TV is down).
- Prior engine-drawn lines scoped-cleared (never `draw_clear`) before the new set is drawn.
- The break level + status + family communicated as an actionable trigger.

## Notes / roadmap
- A trendline break IS a Break-of-Structure; pair with `crypto/lib/market_structure.py` (BOS/CHoCH + HH/HL/LH/LL).
- The autonomous engine version (engine fits + watches + fires on the break itself) sits behind the
  structure-veto wiring on the price-structure roadmap -- this skill is the manual-to-automatic bridge.
- Detection picks the single BEST-scoring line per (kind, family) -- up to 4 total; it does not
  yet surface a same-day-only line as a distinct 5th/6th candidate. See
  `markdown/audits/TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14.md` for the pre-registered A/B spec on
  whether a same-day-priority tier should be added.
- Full audit (detection quality, consumption, visibility, miss-trace, log hygiene):
  `markdown/audits/TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14.md`.
