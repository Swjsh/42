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

1. **Scoped clear of the ENGINE's own prior drawings (NEVER `draw_clear`).** `draw_clear` has no
   scope/tag parameter — it wipes EVERY drawing on the chart, including J's own manual lines, so
   it is disqualified regardless of anything below.

   **UPDATE 2026-08-09: `draw_remove_one`/`draw_list` are NO LONGER BROKEN — verified live this
   session.** The 2026-07-14 finding (`"getChartApi is not defined"`) no longer reproduces:
   `draw_list` returned a real 52-shape inventory, `draw_remove_one` on two freshly-drawn test
   lines both succeeded (`remaining_shapes` counted down 54→53→52 exactly), and calling it on a
   stale/already-gone `entity_id` correctly returned `{success:false, error:"Shape not found:
   ..."}` — the documented not-found case, not a crash. **Use the MCP tools directly now:**
   ```
   backtest/.venv/Scripts/python.exe setup/scripts/trendline_draw_state.py list-ids
   ```
   For each printed `entity_id`, call `mcp__tradingview__draw_remove_one({entity_id})` directly.
   Treat `{success:false, error:"Shape not found: ..."}` as success-for-our-purposes (the line was
   already gone), never a failure. Then:
   ```
   backtest/.venv/Scripts/python.exe setup/scripts/trendline_draw_state.py clear-record
   ```
   (Only clear the record AFTER the chart-side removals actually run -- clearing first and then
   failing a removal would leak an orphaned drawing nothing can find again.)

   **Fallback if this regresses again:** the OLD `ui_evaluate` JS-injection workaround is still
   valid and documented in git history (this file, pre-2026-08-09) — read
   `automation/scripts/tv_ops/remove_drawing.js`, substitute `__ENTITY_ID__` → `"<entity_id>"`,
   pass to `mcp__tradingview__ui_evaluate({ expression: <substituted js> })`. Re-verify with
   `draw_list` before trusting either path if MCP tooling has changed since 2026-08-09.

2. **Detect** (JSON mode, no log side-effect -- this also writes the record J asked for when run
   WITHOUT `--no-log`, e.g. the once-daily premarket fire; on-demand draws use `--no-log` so they
   don't duplicate rows outside the production 5-min cadence):
   ```
   cd backtest && .venv/Scripts/python.exe -m autoresearch.trendline_engine --no-log --json
   ```
   Returns up to 4 PRIMARY lines (wick-support, wick-resistance, body-support, body-resistance --
   only lines that actually scored `respect_count >= 1` are present, may be fewer than 4), PLUS
   up to 4 more `tier="same_day"` lines (T15, 2026-07-20 -- the best-scoring line per
   (kind, family) restricted to TODAY's bars only, appended when it's a genuinely different line
   from its primary sibling; see `trendline_engine.detect(include_same_day_tier=True)`). Each
   line carries `anchor_family` ("wick" | "body"), `tier` ("primary" | "same_day"), `kind`
   ("support" | "resistance"), anchors (`a_unix`/`a_price`/`b_unix`/`b_price`), the forward
   projection (`proj_unix`/`proj_price`), `status` (INTACT/TESTING/BROKEN), `respect_count`,
   `break_level`, and (T16, 2026-07-21) `zoom_class` ("in_window" | "anchor_offscreen" -- see
   step 3a).

3. **DRAW CAP — at most 2 lines on the chart: the single best-respected PRIMARY line per SIDE
   (support + resistance), selected across BOTH families by `respect_count`.** (J, 2026-07-15:
   "way too many trend lines on the screen" — the 4-line families×sides draw plus his own lines
   was unreadable. All detections still LOG; only the DRAW is capped. State the winning line's
   family in its label.) **`tier="same_day"` lines are deliberately EXCLUDED from this draw
   selection for now** (T15, 2026-07-20) -- they exist in the JSON/log/`trendlines-live.json`
   shadow state for self_check/dashboard/future consumers, but adding them to the on-chart draw
   pool would reopen the exact 2026-07-15 noise complaint this cap exists to fix.

3a. **ZOOM-AWARE LABEL PLACEMENT (T16, 2026-07-21, TRENDLINE-FIXES-2026-07-17 item 3):** J's
    complaint was specifically about intraday zoom -- "multi-day rails at intraday zoom read as
    noise... a blind person drew them." Each returned line now carries a `zoom_class` HINT
    computed from the bars alone (a ~2-day window ending at the line's own `current_et`, NOT a
    live check of the chart): `"in_window"` (the anchor `a_unix` is recent -- label normally, at
    the anchor point via `point`) or `"anchor_offscreen"` (the anchor predates the window -- at
    a normal intraday zoom the anchor point renders off-screen to the left, so **label-offset**
    instead: still draw the full ray from the true anchor through `proj_unix` (`extendRight`
    already does this), but when calling `draw_shape`, note in your report to J that this line's
    anchor is off J's current view and consider placing the descriptive text label near the
    line's CURRENT value (at/after `proj_unix`) rather than trusting `showLabel`'s default
    anchor-point placement -- TradingView's own label rendering for a `trend_line` shape is
    anchored at `point`/`point2`, not independently repositionable, so this is a SOFT signal for
    your verbal report and for choosing whether to zoom the chart out before drawing, not (yet) a
    distinct on-chart mechanism. **Before trusting this heuristic over what you actually see: call
    `mcp__tradingview__chart_get_state` (or eyeball the current chart) for the TRUE visible time
    range** -- `zoom_class` is a conservative, no-look-ahead APPROXIMATION computed from bars
    alone; it has no idea what J actually has on screen. If a line comes back `anchor_offscreen`
    and you have a live TV session, this is exactly the case to validate against a real
    screenshot before reporting the fix as visually confirmed -- that validation has NOT
    happened yet (mechanism-only ship, same shipping bar as T15's same-day tier: SHADOW-only,
    engine does not trade off these, so a mechanism-correctness guard is the right bar, not a P&L
    A/B). Guard: `backtest/tests/test_trendline_zoom_aware.py`.

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
- Called `trendline_draw_state.py mark-run` (see step 6 below) so a skipped/missed daily run
  surfaces to `self_check`/STATUS.md instead of going unnoticed (2026-07-19 fix).

## Step 6 — stamp the outcome (2026-07-19, self_check visibility)
Once daily via `Gamma_Premarket`, ALWAYS stamp the run outcome so
`self_check.check_trendline_draw_freshness` can tell whether Step 5c actually fired today:
```
# on success
.venv/Scripts/python.exe setup/scripts/trendline_draw_state.py mark-run --status success
# on TV-down / skill failure / context-budget skip
.venv/Scripts/python.exe setup/scripts/trendline_draw_state.py mark-run --status skipped --reason "<why>"
```
On-demand invocations (J asking mid-session) may skip this — it exists to catch the ONE daily
premarket fire silently not happening, not to track every ad-hoc redraw.

## Alternate detection source (2026-08-09): `trendline_chart_draw.py` + `trendline_detector.py`
A second detector, `backtest/lib/trendline_detector.py` (pivot-anchored, built 2026-08-09,
`crypto.lib.market_structure` swing-pivot primitives), plus its chart-drawing bridge
`setup/scripts/trendline_chart_draw.py`, is available alongside the `trendline_engine.py` flow
above -- NOT a replacement, an additional option with two things the autoresearch engine doesn't
have: a **stable line-id** (`make_line_id` → `TL-{symbol}-{timeframe}-{RES|SUP}-{W|B}-
{first_anchor_unix}`, survives re-detection across runs) and a first-class **`just_retested`**
boolean (a touch landed on the CURRENT bar and isn't the line's own anchor — distinct from the
3-way intact/testing/broken `status`, and the concrete answer to "retested-from-below"). Same
color table, same 1-per-side draw cap, same wick/body-in-the-label rule — ported verbatim, not
reinvented. Usage: `trendline_chart_draw.compute_draw_payload(bars, symbol=..., timeframe=...)`
returns ready-to-splat `draw_shape` kwargs; `bars_from_ohlcv_json()` adapts a live
`mcp__tradingview__data_get_ohlcv` call. Verified live 2026-08-09: 2 lines (1 support/wick, 1
resistance/body) drawn on the real BATS:SPY chart, screenshotted, then cleanly removed via
`draw_remove_one` with zero impact on the chart's other 52 pre-existing shapes. Guard tests:
`backtest/tests/test_trendline_chart_draw.py` (8 tests, RED-proofed). Both detectors currently
coexist; a future session may want to A/B which one produces more USEFUL (not just more) lines
before picking one — not decided here.

### Timeframe recommendation (2026-08-09, Task 3)
**Default: detect AND draw on the SAME timeframe as the currently-displayed chart (5m for the
live SPY 0DTE trading view — confirmed via `chart_get_state`, `chart_resolution: "5"` is the
standing default) — never project a different timeframe's lines onto it.** Reasoning: J has
twice complained about exactly the failure mode cross-timeframe projection would reintroduce —
"multi-day rails at intraday zoom read as noise... a blind person drew them" (T16,
2026-07-21) and "way too many trend lines on the screen" (2026-07-15). A line fit on 1h or Daily
bars is calibrated to that scale's noise floor; re-projected onto a 5m chart it either looks
arbitrary (doesn't touch anything a 5m eye would call a pivot) or requires a SECOND, unrelated
detection pass just to justify it being there. `trendline_chart_draw.py` sidesteps the T16
anchor-offscreen problem structurally rather than patching around it: it takes whatever bar
window the caller hands it (default recommendation: ~240 5m bars ≈ 3 trading days, matching
`trendline_detector.annotate_decisions_with_trendline_state`'s own default `lookback_bars=240`),
which keeps every anchor close enough to "now" that it can't render off-screen in the first
place — bounding the INPUT window, not label-placement-patching the OUTPUT. Per-instrument: this
project trades SPY 0DTE only (minutes-to-hours holds → 5m is the natural unit); a swing
instrument on a days-to-weeks holding period (e.g. the MES futures swing battery, a different
lane) would need its OWN timeframe-matched detection (4h/Daily, per that program's own bar data)
under the SAME principle — never SPY's 5m lines projected onto a futures chart or vice versa.
This recommendation is implemented as the bridge's default, not merely written down: `timeframe`
defaults to `"5m"`, and nothing in `compute_draw_payload` reads or projects a different TF's data.

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
