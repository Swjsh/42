# PRE-REGISTRATION (FROZEN) — J's own drawn trend lines, TOUCH/BREAK shadow, 2026-09-03

**Status: FROZEN before any forward data accrues past this build.** Commit timestamp of
this file is the freeze proof. `setup/scripts/j_drawn_lines_capture.py` (nightly capture),
`setup/scripts/j_drawn_lines_score.py` (nightly scoring), and
`setup/install-j-drawn-lines.ps1` (scheduled task, NOT run this session) are committed
alongside this file.

Queue item: `TRENDLINE-J-DRAWN-LINES-LEDGER` (HIGH). Supersedes nothing — this is a
sibling to, not a replacement for,
[`prereg-trendline-rising-support-human-anchor-2026-09-03.md`](prereg-trendline-rising-support-human-anchor-2026-09-03.md)
(T5 below). T5 tests a *mechanical reconstruction* of J's anchor logic against cached bars.
**This instrument tests something categorically different: J's OWN drawn lines, read
directly off the chart, never reconstructed.** Both are shadow-only, both feed the same
kind of TOUCH/BREAK/baseline machinery, and both are explicitly non-competing — a positive
read on one is not evidence for the other.

Motivating evidence (read-only, all committed):
- [`trendline-today-exhibit.md`](../deep-research/2026-09-03-money/trendline-today-exhibit.md) (T2) and
  [`trendline-historical-study.md`](../deep-research/2026-09-03-money/trendline-historical-study.md) (T3) —
  two frozen *mechanical* anchor rules (literal first-two-pivots; running-min + next-higher-pivot)
  both failed to reproduce J's actual drawn line. The natural next instrument stops trying
  to *guess* J's rule from bars and instead **reads the line he actually drew**.
- [`prereg-trendline-rising-support-human-anchor-2026-09-03.md`](prereg-trendline-rising-support-human-anchor-2026-09-03.md) (T5) —
  sibling instrument, same TOUCH/BREAK/baseline/CI machinery, reconstructs a candidate line
  from bars instead of reading it off the chart. Read there for the outcome-measurement
  convention this file reuses.
- `setup/scripts/trendline_headless_draw.py` / `tv_cdp.py` — the existing headless CDP path
  (no MCP, no LLM, $0) this instrument's capture step reuses verbatim for chart connection,
  and whose `"[GTL] "` text tag is the exclusion signal for engine-drawn lines.

---

## 0. CRITICAL EMPIRICAL FINDING (verified live 2026-09-03, gates the whole design below)

Before freezing the population/capture rule, the actual TradingView chart-widget API
(`window.TradingViewApi._activeChartWidgetWV.value()`, the same `CHART_API` path
`tv_cdp.py`/`draw_key_levels.py`/`trendline_headless_draw.py` already use) was probed
live, read-only, against the real SPY chart:

1. **`getAllShapes()` / `getShapeById(id).getPoints()` are NOT timeframe-scoped.**
   Switching the chart's active resolution between `"5"` and `"15"` via
   `chart.setResolution(res, {})` and re-listing `trend_line` shapes returned the
   **identical set of 25 entity IDs both times** (`ids_5 == ids_15` verified `True`, disjoint
   diffs empty both directions). TradingView drawings are chart-wide, not per-interval,
   unless the user has explicitly restricted a shape's `intervalsVisibilities` — checked on
   all 25 live shapes; none carry that restriction.
2. **A shape's reported anchor `time` is NOT resolution-invariant.** Reading the *same*
   entity ID's `getPoints()` while the chart is at resolution `"15"` vs resolution `"5"`
   returned **different** unix times for the same anchor — drift ranged from minutes to
   multiple **hours** on live data (e.g. entity `7qQlMk`: point-2 time `2026-07-17T19:45`
   at res=15 vs `2026-07-20T09:25` at res=5, a 61.6-hour drift on the identical shape).
   A stability check (two consecutive reads at a fixed resolution, no switch, 2s apart)
   was **identical both times** — this rules out a load-race; the drift is a deterministic
   function of *which resolution is currently active when you read the point*, not noise.
   Both readings are always grid-aligned to whichever resolution is active (checked:
   res=15 reads land on exact 900s multiples, res=5 reads on exact 300s multiples) — so
   grid-alignment cannot be used to recover which resolution a line was "really" drawn at
   either. There is no recoverable per-drawing "native timeframe" signal in this API.

**Consequences for the design below (both deviations from the task's literal
"dedupe by (timeframe, anchor1, anchor2)" framing, stated up front per anti-sycophancy
doctrine rather than silently implemented):**

- **Population identity = TradingView's own `entity_id`, not `(timeframe, anchor1, anchor2)`.**
  Deduping on resolution-dependent anchor times would let the *same physical drawing*
  enter the ledger twice (once tagged 5m, once 15m) purely as an artifact of which
  resolution the capture script happened to be on when it first saw the shape — inflating
  N and creating two "independent" ledger lines that are actually perfectly correlated
  (same price ray). `entity_id` is TradingView's real, stable identity for a drawing and is
  what is actually deduped on.
- **`timeframe` is recorded as `"other"` for every captured line** unless a future shape
  carries an explicit `intervalsVisibilities` restriction (checked for, wired, currently
  always absent). This is honest under C7 ("never fabricate a signal you don't have") —
  the field exists in the schema (per the task's ask) but its value is not asserted beyond
  what the API actually proves.
- **Anchor points are read and recorded at ONE fixed, deterministic capture resolution**
  (`"5"`, canonical — matches the 1m/5m cache this repo already scores everything against)
  for internal run-to-run reproducibility (proven stable). The `"15"`-resolution reading of
  the same points is also captured and stored as a disclosed cross-check field
  (`alt_points_res15`) plus a `drift_detected` flag — reported, never hidden, never used to
  gate anything.

None of the 25 live shapes found this session matched the day's described rising-support
anchors (5m `08:20`→`10:10`, 15m `08:15`→`10:00`, 2026-09-03) — the closest by date/price
was an ascending line spanning `06:15`→`15:00` today with a $12+ span, structurally
different from the tight AM double-bottom described. **This capture step reports exactly
what it finds, honestly — it does not assert these 25 legacy shapes are "J's daily
lines"; the population is defined mechanically (§1), not by provenance judgment.**

---

## 1. Population (frozen)

Every shape on the active SPY chart where `name == "trend_line"` (TradingView's own type
tag — the exact filter `trendline_headless_draw.py`'s `_own_trend_lines()` already uses)
**AND** whose `text` does **not** start with `"[GTL] "` (the sole existing engine-drawn
trend-line tag; `trendline_headless_draw.py` is the only trend_line producer in this repo
— verified by repo-wide grep, 2026-09-03). A `horizontal_line` (key levels, `"[G] "` tag)
is a structurally different shape type and is out of scope entirely — captured never.

This is a **mechanical, provenance-agnostic** definition: it does not attempt to judge
whether a human or a long-forgotten test script drew any given untagged line. Anything
that clears the two filters above is population, full stop — same discipline
`_own_trend_lines()` already applies for its own exclusion, just inverted.

## 2. Capture (frozen)

`setup/scripts/j_drawn_lines_capture.py`, run nightly (16:30 ET, after the market closes —
never during 09:30-15:55 ET, matching every other after-hours chart-touching script in this
repo):

1. Connect via `tv_cdp.TvChart` (the exact CDP path `trendline_headless_draw.py` uses — no
   MCP, no LLM, $0).
2. Record the chart's current resolution (`chart.resolution()`) before touching anything.
3. `setResolution("5", {})`, wait for the read to stabilize, list every non-engine
   `trend_line` shape, read `getPoints()` (→ `anchor1`/`anchor2`, sorted by time ascending)
   and `getProperties()` (→ `extend_right`, `extend_left`). This is the **canonical**
   reading (§0).
4. `setResolution("15", {})`, wait, re-read `getPoints()` for the *same* entity IDs → the
   disclosed alternate reading (`alt_points_res15`).
5. **Restore the original resolution** recorded in step 2, and verify the restore
   (`chart.resolution() == original`) before exiting. Never touches symbol, layout, or any
   other chart-widget setting. **Never calls `createShape`/`createMultipointShape`/
   `removeEntity`** — read-only against drawings, full stop (no code path in this script can
   modify or delete anything J drew).
6. Dedupe against the ledger by `entity_id` (§0). New entity IDs get `first_seen_et` =
   `et_clock.et_now()` at capture time and are appended to the ledger. An entity ID already
   in the ledger is never re-appended or re-timestamped, even if its `alt_points_res15`
   reading has since drifted (TradingView's internal state, not ours, moved — logged as
   `points_drift_since_capture` on the next capture that notices a mismatch, informational
   only, never rewrites the frozen `first_seen_et`/original anchors).
7. **Fail-open**: CDP/TradingView unreachable → `status=SKIPPED_TV_DOWN`, exit 0, same
   convention as every sibling headless-CDP script. Any other unexpected error is caught,
   stamped `status=ERROR`, flagged to `STATUS.md`, and returns 1 — never a silent failure,
   never an unhandled exception into the scheduler.

Output: `analysis/recommendations/j-drawn-lines-ledger.jsonl` (append-only, row
`kind: "line"`), state stamp `automation/state/j-drawn-lines-capture.json`.

## 3. Scoring (frozen)

`setup/scripts/j_drawn_lines_score.py`, run nightly (after capture) against cached 1m bars
(`backtest/data/spy_sip_cache/spy_1m_<date>.json`, never re-fetched — same hard constraint
as T5). For each ledger line:

- **Line shape**: `rising` if `anchor2.price > anchor1.price` (time-ascending anchors, §2
  step 3), `falling` if `<`, `flat` if equal. **Only `rising` lines are scored as events**
  (TOUCH=bounce-up, BREAK=close-down) — this instrument does not invent a resistance-line
  convention casually; `falling`/`flat` lines are counted and reported
  (`n_lines_excluded_non_rising`) but never scored, matching this session's own motivating
  context (J's described lines are rising support) and avoiding a fabricated mirror-image
  rule this prereg was not built to test. A future prereg can freeze the resistance-line
  convention separately if warranted.
- **No look-ahead (frozen, the load-bearing rule the task named directly)**: a line is
  scored starting from the first cached session bar whose **date** is strictly **after**
  `first_seen_et`'s ET calendar date. A line first captured tonight (2026-09-03) is scored
  from **2026-09-04** onward, never against today's own bars — even though today's bars are
  already sitting in the cache, they are the exhibit that led to building this instrument
  and would be a look-ahead disclosure, not forward evidence. Today's own capture (if any
  rows land on 2026-09-03) is logged and reported as **in-sample disclosure only**
  (`in_sample: true`), exactly the same flag convention T5 §6 uses, and never counts toward
  §5's decision-rule bar.
- **Line value at time `t`** (continuous, real-time-based — a drawn line persists across
  calendar days, unlike T5's within-session bar-index lines):
  `line(t) = a_price + rate * (t - a_time)`, `rate = (b_price - a_price) / (b_time - a_time)`,
  evaluated against each forward session's 5m bars (`5m_premkt` bar_set convention — built
  from `spy_1m`+`spy_5m` cache identically to T5 §2, full day from 04:00 ET). `extend_right`
  is required for a line to be evaluable past `anchor2`'s own time — a line with
  `extend_right: false` is scored only up to `anchor2.time` (never projected past where
  TradingView itself would stop drawing it) and reported separately
  (`n_lines_excluded_no_extend` for the calendar span past `anchor2`).
- **TOUCH** — a bar `j` where `|low(j) - line(j_time)| <= 0.20` (5m tolerance, matching T5
  §4) **and** `close(j) > line(j_time)`.
- **BREAK** — the first bar `j` where `close(j) < line(j_time) - 0.20`. The line dies at
  that bar for scoring purposes (no further events past a line's own first break) — a
  `rising` line does not "un-break."
- **Outcome + baseline**: identical convention to T5 §5 — close-to-close move and max
  favourable excursion at H ∈ {15, 30, 60} min (5m bar counts 3/6/12) in the touch's implied
  "up" direction, against a time-of-day baseline pooled from every non-event 5m bar at the
  same `HH:MM` across every session in the forward-scored population that has a full
  forward window.

Output: `analysis/recommendations/j-drawn-lines-summary.json` (per-timeframe aggregate —
`timeframe` bucket is always `"other"` per §0/§1, so today this collapses to one bucket;
the schema keeps the per-timeframe shape so a future capture-side fix that recovers a real
timeframe signal does not require a schema migration).

## 4. Decision rule (frozen, NOT softened after data starts arriving)

A trigger proposal proceeds to a real ratification pass only if **ALL** of, using
forward (`in_sample: false`) rows only, TOUCH events, H=60 min:

1. **`n_lines_forward >= 20`** AND **`n_sessions_forward >= 15`** (task's own stated bar —
   sessions = distinct dates contributing at least one scored bar to the forward population,
   lines = distinct entity IDs with `in_sample: false`).
2. **`rate_ci_lower (session-clustered bootstrap, day-resampled, 2.5th pctile) >
   baseline_rate`** at H=60.
3. **`mean_move_ci_lower > 0`** (session-clustered bootstrap 2.5th pctile of mean `c2c`) at
   H=60.

**Hard date gate, independent of the above:** no ship/kill verdict before **2026-10-30**,
mirroring T5 §7 verbatim — `status` stays `ACCRUING` (bar not met) or
`BAR_MET_DATE_GATED` (bar met, verdict withheld) until that date.

## 5. Falsifier (frozen, matches T5 §8's discipline)

Falsified (do not build) once the §4.1 bar is met, if:
- `rate_ci_lower <= baseline_rate` at H=60, OR
- `mean_move_ci_lower <= 0` at H=60, OR
- **top-3-line concentration `>= 0.60`** of total forward touch events (same guard T5/
  `stop_mode_shadow_ledger.py`/`day_throttle_shadow.py` all use).

## 6. Explicit non-goals

- **Never live, never paper, ever.** No code path in either script calls a broker, a live
  trigger function, or `filters.py`. §4's bar caps out at "proceeds to a real ratification
  pass," itself a separate, later, explicitly-authorized step this file does not
  pre-authorize.
- **Never modifies, removes, or creates a chart drawing.** `j_drawn_lines_capture.py` calls
  only `getAllShapes`/`getShapeById`/`getPoints`/`getProperties`/`resolution`/
  `setResolution` — no `createShape`, `createMultipointShape`, or `removeEntity` anywhere in
  the file. J's drawings, and anyone else's, are never at risk from this instrument.
- **Never leaves the chart's resolution changed** — §2 step 5 restores and verifies before
  exit, every run, including on error paths.
- Not a claim about *whose* line each population member is (§0) — population is defined
  mechanically by the engine-tag exclusion, not by provenance judgment.
- Not evidence yet, and not a re-run of T5 with a different anchor rule — a categorically
  different data source (read off the chart vs reconstructed from bars).

## 7. Build step (structured, for machine reference)

```json
{
  "build_step": {
    "id": "TRENDLINE-J-DRAWN-LINES-LEDGER",
    "sibling_instrument": "prereg-trendline-rising-support-human-anchor-2026-09-03.md",
    "frozen_date": "2026-09-03",
    "empirical_findings_gating_design": [
      "getAllShapes()/getPoints() are chart-wide, not timeframe-scoped -- verified live, identical entity-id sets under resolution 5 and 15",
      "a shape's reported point time is resolution-read-dependent (drift up to ~62h observed on live data), not resolution-invariant; stable when read repeatedly at a FIXED resolution",
      "no per-drawing native-timeframe signal is recoverable from this API"
    ],
    "design_deviations_from_literal_task_wording": [
      "dedupe key is TradingView entity_id, not (timeframe, anchor1, anchor2) -- resolution-dependent anchor times are not a safe dedupe key",
      "timeframe field recorded as 'other' for every line pending a real per-drawing signal (intervalsVisibilities), never fabricated from capture-resolution alone"
    ],
    "population": "trend_line shapes, text not starting with '[GTL] '",
    "canonical_capture_resolution": "5",
    "alt_capture_resolution": "15",
    "scoring": {
      "scored_line_shape": "rising only (anchor2.price > anchor1.price)",
      "tolerance": 0.20,
      "horizons_min": [15, 30, 60],
      "bar_set": "5m_premkt",
      "no_lookahead": "scored only from the first session date strictly after first_seen_et's ET calendar date"
    },
    "bar": {"min_lines_forward": 20, "min_sessions_forward": 15},
    "decision_rule": {
      "rate_ci_lower_gt_baseline": true,
      "mean_move_ci_lower_gt_zero": true,
      "all_required": true,
      "softenable": false,
      "hard_date_gate": "2026-10-30",
      "never_live": true
    },
    "falsifier": {
      "rate_ci_lower_le_baseline": true,
      "mean_move_ci_lower_le_zero": true,
      "top3_concentration_ge": 0.60
    },
    "artifacts": {
      "ledger": "analysis/recommendations/j-drawn-lines-ledger.jsonl",
      "summary": "analysis/recommendations/j-drawn-lines-summary.json",
      "capture": "setup/scripts/j_drawn_lines_capture.py",
      "scorer": "setup/scripts/j_drawn_lines_score.py",
      "scheduled_task": "Gamma_JDrawnLinesLedger",
      "install_script": "setup/install-j-drawn-lines.ps1"
    },
    "do_not": [
      "wire this instrument's output into any live or paper trigger, ever",
      "read a verdict before 2026-10-30 even if the bar is met earlier",
      "let today's (in-sample) capture rows satisfy the forward bar in section 4",
      "ever call createShape/createMultipointShape/removeEntity from the capture script",
      "dedupe on resolution-dependent anchor time instead of entity_id"
    ]
  }
}
```

## 8. Revert

Whole instrument, one shot: `Unregister-ScheduledTask -TaskName Gamma_JDrawnLinesLedger
-Confirm:$false` + delete `setup/scripts/j_drawn_lines_capture.py` +
`setup/scripts/j_drawn_lines_score.py` + `setup/install-j-drawn-lines.ps1` + this file
(+ the two output artifacts under `analysis/recommendations/`, analysis-only, nothing on
the trading path reads them). Same class as `Gamma_TrendlineHumanAnchorShadow`.
