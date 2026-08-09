# Bull-Trendline Graduation + Chart-Drawing Capability — 2026-08-09

> Clock verified `python setup/scripts/et_clock.py` → **2026-08-09 Sunday EDT, market_hours=False**.
> Sibling-owned files respected as read-only: `backtest/lib/trendline_detector.py` (imported, never
> edited), `exit_manager.py` / exit params (never touched), MES futures swing battery (not touched).
> No trading-path file edited (`filters.py`, `engine_cli.py`, `heartbeat_core.py`, `params.json` all
> untouched). No orders placed. Paper/analysis only.

---

## VERDICT

1. **Bull-side `detect_trendline_reclaim_bullish` (filters.py:944) stays in SHADOW.** Refreshed the
   07-31 real-OPRA standalone-trigger test through 9 newly-cached days; the naive number looked
   positive (+$7,120.85) but that was a position-overlap artifact (caught via a fable-too-good
   hunt) — corrected, it is **-$1,110.16 across 75 realistic trades, 8/10 days negative**. OOS_positive
   fails either way. Nothing shipped, nothing reverted (nothing touched).
2. **Chart-drawing capability SHIPPED** (read-only w.r.t. trading, $0): a bull+bear symmetric
   drawing bridge, verified by actually drawing on the live chart, screenshotting, and cleaning up.
3. **Timeframe recommendation implemented as the default**, not just written down: detect and draw
   on the SAME timeframe as the displayed chart (5m for live SPY 0DTE), never project across
   timeframes.

---

## Task 1 — Bull-side trendline detector: does it graduate?

### Ground truth, verified fresh (not assumed)

| claim | status | evidence |
|---|---|---|
| Bear's `detect_trendline_rejection_bearish` (filters.py:601) is LIVE and load-bearing | ✅ CONFIRMED | Read `analysis/deep-research/EOD-2026-08-06.md` directly: fired on all 8 `ENTER_BEAR` verdicts 2026-08-06, produced 100% of that day's P&L. Wired into `evaluate_bearish_setup`'s `triggers` list (filters.py ~1560-1625), AND gets a filter-relaxation carve-out (TRENDLINE-CHOP-ZONE, filters.py ~1627) when it's the sole level-tied trigger — 89% of bear ENTER verdicts over 33 sessions came through that bypass alone (G2 audit, 2026-07-27..08-01). |
| Bull's `detect_trendline_reclaim_bullish` (filters.py:944) is SHADOW-only | ✅ CONFIRMED | Its own docstring states it explicitly; verified structurally via `evaluate_bullish_setup` (filters.py ~1306-1330) — computed into `shadow_triggers` list, which is a SEPARATE field (`shadow_triggers_fired`) from `triggers`/`triggers_fired`, and `test_bull_trendline_wick_reclaim_shadow_only.py` proves byte-identical `passed`/`bull_score`/`blockers`/`triggers_fired` whether or not it fires. |
| Bull has 4 live triggers (level_reclaim / ribbon_flip / confluence / sequence_reclaim) vs bear's 6 | ✅ CONFIRMED | Read `evaluate_bullish_setup` directly: filter 11's `triggers` list only ever appends those 4 names; the trendline/wick shadow detectors are structurally excluded (see above). |

### The bear side was never formally eval-gated either — the task asked me to check, so I did

`detect_trendline_rejection_bearish` was built 2026-05-09 ("NEW 2026-05-09 night: trendline_rejection
trigger (CLAUDE.md OP 17 TDD)") and shipped off test-driven development alone — OP-16's eval-first
gate (A/B scorecard before ratification) didn't exist yet; v15 (which OP-16 belongs to) wasn't ratified
live until 2026-06-01, three weeks later. A repo-wide search of `analysis/recommendations/*trendline*`
turns up 18 files — g2-trendline-bypass, trendline-break-battery, trendline-fade-battery,
crypto-paper-trendline-reclaim, midday-trendline-gate, trendline-structure-conviction,
trendline-subclassification, trendline-conviction-override — **none of them is an original A/B
scorecard for `trendline_rejection` itself.** Its standing today rests on ~3 months of live
production survival plus one outsized day, not a pre-registered test. That is the honest "same bar"
comparison: **bull was held to, and failed, a formal real-OPRA/BH-FDR/day-level standalone-trigger
test that bear never had to pass.** This is itself a finding, not a rhetorical point — if bear's
`trendline_rejection` were proposed fresh today under OP-16, it would need the same test bull just
failed.

### The 07-31 study, and why it needed a refresh (not just a citation)

`analysis/deep-research/SHADOW-SIGNAL-INVENTORY-2026-07-31.md` / `backtest/tools/
shadow_signal_edge_2026_07_31.py` already ran `trendline_reclaim` as a **standalone entry trigger**
(take every shadow firing, walk it through the REAL exit_manager at the live `RIBBON_RIDE` shape,
real OPRA pricing only) with proper method discipline: BH-FDR across the 3 shadow signals,
per-day-block significance test (not per-trade — ~45 firings/day inside one session are not
independent draws), and a "coverage-bias-control" that only trusts days whose cached OPRA strike
ladder spans the whole day's SPY range. Result on the 3 days that qualified as of 07-31
(07-20/21/22): **n=27, total -$1,097 (-$1,588 at the true -50% cap), -$40.64/trade, WR 14.8%,
day-level stat=-3.401, p=0.00067 (normal approx) / p=0.077 (Student-t df=2, the more honest
small-n estimator), 3/3 days negative. Verdict: SIGNIFICANT NEGATIVE.**

Per the standing "recency > aggregate" doctrine (J, 2026-07-31: every armed/tested gate needs a
revalidation clock), that 9-day-old, 3-day-sample result was not good enough to cite verbatim —
more OPRA cache has landed since (2026-08-01..08-07 are now cached; they were not on 07-31,
verified via `ls backtest/data/opra_1m_cache`), so it was **re-run, not re-quoted.**

### The refresh — and the artifact it nearly produced

Built `backtest/tools/bull_trendline_reclaim_graduation_2026_08_09.py`, importing the 07-31 script's
own `fully_covered_days`/`run_one`/`day_level_test`/`one_sample_p`/`EXIT_SHAPE` verbatim (no
re-derivation), pointed at the wider `spy_5m_2026-05-19_2026-08-07.csv`. The unbiased-day set grew
from 3 to **10** (07-20/21/22/23/27/28/29/30, 08-05/06).

**Raw method (identical to the 07-31 study's own scope — "take every firing as an entry"):**
n=142, **total +$7,120.85, per-trade +$50.15, WR 23.9%.**

That looked too good, so per the fable-too-good protocol the artifact was hunted BEFORE reporting
it as a reversal. Per-day breakdown:

| date | day P&L (raw method) |
|---|---:|
| 2026-07-20 | -397.04 |
| 2026-07-21 | -165.81 |
| 2026-07-22 | -534.39 |
| 2026-07-23 | -915.68 |
| 2026-07-27 | -1,435.63 |
| 2026-07-28 | -256.36 |
| **2026-07-29** | **+10,107.47** |
| 2026-07-30 | +2,525.69 |
| 2026-08-05 | -1,145.26 |
| 2026-08-06 | -662.14 |

**8 of 10 days negative. One day is 142% of the total.** Dropping the single best day
(+10,107.47) flips the whole 10-day total to **-$2,986.62**. That is the textbook "one lucky day"
shape this repo's own `drop_best`/`day_majority` gates exist to catch (used verbatim in
`bull_gate_f5class_requal_2026_08_01.py` and `f10_f7_population_battery_2026_08_07.py`, the two
most recent sibling battery precedents).

**The mechanism, found by inspecting 2026-07-29's individual legs directly:** 20 raw firings that
day, 15 of them on **consecutive 5-minute bars (12:00-13:10 ET)** during one uninterrupted uptrend
— each one independently scored by the "take every firing as an entry" harness as its OWN trade,
most exiting via `runner_stop` at wildly profitable levels ($998-$1,272 each) because they are all,
mechanically, the SAME continuous move counted up to 15 times over. The real system is
**single-position-per-account** (Rule 4, C11 "verify flat before entry") — it could never have
held all 15 of these simultaneously. This is not a new failure mode in this repo (C27: ambient,
non-selective firing) but a related one specific to backtesting standalone triggers without a
position constraint — worth naming since the 07-31 study's own 3-day sample never happened to
contain a long enough uninterrupted trend to expose it.

**Correction: position-limited re-walk.** Same 152 events, same exit-manager walk, but a firing
only counts as a tradeable entry if the account would actually be flat at that bar (the prior kept
trade's own `exit_time_et` has already passed) — mirroring the real single-position constraint.

| | raw ("take every firing") | position-limited (realistic) |
|---|---:|---:|
| n (of 152 raw events) | 142 resolved | **75 kept** (77 were phantom re-entries into an open position) |
| total P&L | +$7,120.85 | **-$1,110.16** |
| per-trade | +$50.15 | **-$14.80** |
| win rate | 23.9% | 25.3% |
| days negative | 8/10 | **8/10** |
| day-majority (win_days > days/2) | — | **FAIL (2/10)** |
| drop-best still positive | — | **FAIL (-$1,879.07 remaining)** |
| day-level test | stat=0.648, p=0.517 | **stat=-0.863, p=0.388** |
| 2026-07-29 specifically | +$10,107.47 (20 events) | **+$647.98** (3 events kept, 17 rejected as overlap) |

**The corrected number is negative, on 3x the day-count, under a methodology now hardened against
the exact artifact that would otherwise have produced a false-positive reversal.** OOS_positive
(OP-16's own gate) fails under either the position-limited number or the raw method's own
drop-best test. Full per-day tables, coverage audit, and the exit-fallback disclosure inherited
from the 07-31 study: `analysis/deep-research/BULL-TRENDLINE-RECLAIM-GRADUATION-2026-08-09.json`.

### HARD GATE — Tuesday 2026-08-04 (+$3,624, all 5 accounts)

Checked directly against the production ledgers (not inferred from the backtest):

| ledger | 08-03 rows | 08-03 `trendline_reclaim` shadow fires | 08-04 rows | 08-04 `trendline_reclaim` shadow fires |
|---|---:|---:|---:|---:|
| core (`safe`+`bold`) | 772 | **0** | 776 | **0** |
| fleet `risky-1` | 384 | 0 | 384 | **0** |
| fleet `risky-3` | 384 | 0 | 384 | **0** |
| fleet `safe-3` | 384 | 0 | 384 | **0** |

**`trendline_reclaim` fired zero times, in shadow, across every real account, on both 08-03 and
08-04.** The standalone-trigger OPRA re-walk independently confirms the same thing (0 shadow events
that date → 0 resolved trades → the cell trivially reports `$0`, `is_unbiased_day: false`, and a
`PASS (trivial)` verdict). **Wiring this trigger live could not have changed a single decision,
tier, sizing choice, or fill on Tuesday 2026-08-04 — the day is provably untouched, not merely
un-degraded.** This is the cleanest possible way to satisfy a hard gate: not a statistical argument,
a direct absence in the ledger the actual engine wrote that day.

### Frequency — how often would it fire (price-only, no OPRA needed)

Direct replay of `detect_trendline_reclaim_bullish` over the continuous RTH 5m series
2025-01-02..2026-08-07 (399 sessions, the pinned 391-day lineage plus the newest cached tail),
global bar index / no per-day reset (matches `lib/orchestrator.py`'s own `BarContext` construction
— `prior_bars=spy_df` the WHOLE frame, `bar_idx` the global row index, confirmed by reading the
orchestrator directly, not assumed):

**9.53% of eligible bars fire (2,941 of 30,874); present on 82.5% of trading days (329/399).**
Moderate and recurring — not a rare, high-conviction event, and not so ambient it reads as pure
noise either (contrast `wick_reclaim`'s 57%-of-bars finding in the 07-31 study, which is the
"weather report, not a trigger" shape). This is a frequency number only, deliberately never mixed
with the $ figures above (different evidentiary basis — OPRA-bounded vs price-only).

### Structural risk beyond P&L (documented, not re-tested — the verdict above already fails)

`backtest/lib/engine/engine_cli.py::_derive_tier` (~line 484) bumps a trade to **SUPER tier** when
`len(winning_triggers) >= 3`, and `_derive_routing` (~line 465) breaks a bear/bull trigger-count TIE
by whichever side has MORE triggers. Wiring `trendline_reclaim` into `triggers` is therefore **not
provably inert even on bars that already qualify via a different trigger** — it can silently bump a
trade's quality tier (different sizing/gates downstream, e.g. `block_elite_bull`) or flip which
side wins a count-tied bar, a second-order effect the standalone-trigger P&L test cannot see at all.
Noted here as a citation of code actually read this session, not empirically re-quantified — the
primary verdict already fails without it, so this was not chased further; any future re-open of this
question needs its own cell for this specifically.

### Decision

**Stays in shadow.** Nothing in `filters.py`/`engine_cli.py`/`heartbeat_core.py` touched. No guard
changes needed — the existing `test_bull_trendline_wick_reclaim_shadow_only.py` already pins the
shadow-only status and continues to pass untouched. **Forward clock:** re-test when the
position-limited unbiased-day count reaches ≥20 (currently 10, N_FLOOR convention used elsewhere in
this repo's batteries), or if a future session wants to test it as a score-contributor/tiebreaker
rather than a standalone trigger — explicitly untested by either the 07-31 study or this refresh
(same open question the 07-31 doc already flagged and this refresh does not resolve).

---

## Task 2 — Chart-drawing capability

### What already existed (found before building anything new)

The `trendline-draw` skill (`.claude/skills/trendline-draw/SKILL.md`) + `backtest/autoresearch/
trendline_engine.py` already do almost everything asked for: wick/body anchor families (never
mixed per line — J's rule, structurally guaranteed), INTACT/TESTING/BROKEN status, a 1-line-per-side
draw cap (J, 2026-07-15: "way too many trend lines on the screen"), a color table by (kind,
family), labels that always state the flavor, zoom-aware label placement (T16), and scoped
cleanup bookkeeping (`setup/scripts/trendline_draw_state.py`) so only engine-drawn shapes are ever
removed. **This flow is proven in production** (real respect counts up to x63) and was not
replaced.

A concurrent sibling session built `backtest/lib/trendline_detector.py` this same session (verified
present, read-only per the file-ownership boundary; its own docstring explicitly names "chart
drawing... a sibling agent's lane" — this deliverable). It adds a formal, stable line-id scheme
(`make_line_id` → `TL-{symbol}-{timeframe}-{RES|SUP}-{W|B}-{first_anchor_unix}`, exactly the
`TL-{tf}-{dir}-{seq}`-shaped scheme the task described) and a first-class `just_retested` boolean —
the concrete answer to "retested-from-below" as a distinct visual state, not just a proxy inside
the 3-way status. Its test suite was 22/25 green the first time it was checked this session (3
candidate-generation edge cases failing, not public-API breakage) and **25/25 green when re-checked
later the same session** — the owning session fixed them in parallel; re-verified fresh, not assumed.

### What was built: `setup/scripts/trendline_chart_draw.py`

A bridge that consumes `trendline_detector.detect_trendlines()` for BOTH `support` (bull-relevant)
and `resistance` (bear-relevant) × both `wick`/`body` anchor modes, applies the SAME draw cap (best
1 per side by touch_count), and emits ready-to-splat `draw_shape` kwargs — colors and label format
**ported verbatim** from the existing J-approved skill, never re-derived:

| kind | anchor_mode | linecolor |
|---|---|---|
| support | wick | `#26a69a` (solid teal) |
| support | body | `#80cbc4` (muted teal) |
| resistance | wick | `#ef5350` (solid red) |
| resistance | body | `#ef9a9a` (muted red) |

Line width additionally communicates state (family + status are ALSO always in the text label —
width is a secondary tell, never the sole one): broken = 1 (de-emphasized but still visible),
just-retested = 3 (most actionable — price came back and held), otherwise 2. Every label opens
with `[WICK]` or `[BODY]` — never omitted — followed by kind, touch count, status, retest flag if
true, and the line-id suffix for cross-reference.

**Tagging so only engine-drawn shapes are ever removed:** reuses `trendline_draw_state.py`
unchanged — `record(entity_id, kind, family, label)` after each successful `draw_shape`,
`list-ids`/`draw_remove_one` (never `draw_clear`, which has no scope parameter and would wipe J's
own manual lines) to clean up, `clear-record` only after chart-side removal is confirmed.

### Verified live, not just unit-tested

1. Launched TradingView with CDP (`setup/launch_tv_debug.ps1` — `tv_launch`'s auto-detect failed,
   TV Desktop is an MSIX package at a non-standard path; the repo's own launch script knows this).
2. `tv_health_check` confirmed `chart_symbol: "BATS:SPY"`, `chart_resolution: "5"`.
3. `draw_list` returned the chart's real 52 pre-existing shapes (J's own manual lines + other
   systems' level lines).
4. Fetched 393 real recent SPY 5m bars, ran `trendline_chart_draw.compute_draw_payload()` — 4
   candidates found, cap correctly reduced to 2 (best support + best resistance).
5. Drew both via `mcp__tradingview__draw_shape` — both succeeded (`022V32`, `12G82J`).
6. **Screenshotted the chart** (`trendline_bull_bear_test_draw.png`) — both lines visible, correctly
   colored, correctly labeled with the flavor tag.
7. Recorded both in `trendline_draw_state.py`, then removed both via `draw_remove_one` —
   `remaining_shapes` counted **54 → 53 → 52**, exactly the 2 test shapes, confirming zero impact
   on anything else on the chart.
8. Confirmed via a final `draw_list`: **byte-identical 52-shape inventory, same IDs, same order** —
   the chart is exactly as it was before the test.
9. Also tested `draw_remove_one` on a stale (already-gone) `entity_id` from a prior session's
   bookkeeping — correctly returned `{success:false, error:"Shape not found: ..."}` rather than
   erroring destructively, confirming the documented not-found handling is sound.

### A bug found and fixed in passing (OP-0)

Both `.claude/skills/trendline-draw/SKILL.md` and `automation/prompts/premarket.md` (a LIVE daily
08:30 ET production step) documented `draw_list`/`draw_remove_one` as **CONFIRMED BROKEN**
(`"getChartApi is not defined"`, dated 2026-06-24/07-14) and instructed routing around them via a
`ui_evaluate` JS-injection workaround. Step 8-9 above are direct, dated, live proof this is no
longer true. Updated both docs with a dated correction pointing to this evidence, kept the old
workaround documented as a fallback in case of regression, and — deliberately — did **not**
restructure either file's actual mechanics beyond the factual correction (premarket.md is a live
daily production step; a deeper simplification is flagged as an opportunity for whoever next
touches it, not attempted same-session against blast-radius discipline).

### Guards + RED-proof

`backtest/tests/test_trendline_chart_draw.py` — 8 tests: draw-cap enforcement (plus its own
internal RED-proof: temporarily raising the cap and confirming 2 lines CAN be drawn when 2
candidates exist, then confirming the cap is back in place), label-always-states-flavor, color
matches the (kind, anchor_mode) table, best-by-touch-count selection, fail-open on a detector
exception (never crashes the caller), the TradingView-JSON bar adapter, and empty-input handling.

**RED-proof performed live this session** (not merely described): removed the `[WICK]`/`[BODY]`
prefix from `_label()`, re-ran `test_label_always_states_wick_or_body_flavor` → **FAILED** with the
exact expected assertion message, restored the original line via `Edit`, re-ran the full 8-test
suite plus `trendline_detector.py`'s own 25 → **33/33 GREEN**.

### Revert (one line)

```
git rm setup/scripts/trendline_chart_draw.py backtest/tests/test_trendline_chart_draw.py
```
Plus reverting the two doc edits (`.claude/skills/trendline-draw/SKILL.md`,
`automation/prompts/premarket.md`) if desired — purely additive, no existing consumer depends on
either file. The old `trendline_engine.py`-based flow is completely untouched and remains the
primary, proven path.

### Architecture constraint (stated, not silently worked around)

Confirmed live this session: `tv_health_check` fails until TradingView Desktop is launched with
CDP, and `draw_shape`/`draw_remove_one`/etc. are MCP tools that only exist inside a live Claude+CDP
session — a Windows Scheduled Task running bare `pythonw.exe` has no Claude session and therefore
no MCP tools to call. This matches the trendline-draw skill's own prior finding
("`draw_shape` only appears in `automation/prompts/*.md` persona instructions, never in a
standalone script") — there is no code fix for this, it is the shape of the integration.
**"Fold into the existing scheduled task" therefore means `Gamma_Premarket`** (the one LLM-driven
persona fire where drawing already happens, 08:30 ET) — not a new always-on draw daemon, which
cannot exist given how TradingView MCP is wired. Detection-only (no draw calls) CAN run headless —
`trendline_chart_draw.py`'s own CLI does exactly that, reusing the proven Alpaca fetch path, for a
detect-and-report dry run with zero MCP dependency.

---

## Task 3 — Timeframe recommendation

**Default: detect and draw on the SAME timeframe as the currently-displayed chart. Never project
a different timeframe's lines onto it.** Implemented as `trendline_chart_draw.compute_draw_payload`'s
default (`timeframe="5m"`), not merely written down.

**Why:** J has twice complained about exactly the failure mode cross-timeframe projection would
reopen — "multi-day rails at intraday zoom read as noise... a blind person drew them" (T16,
2026-07-21) and "way too many trend lines on the screen" (2026-07-15). A line fit on 1h/Daily bars
is calibrated to that scale's own noise floor; re-projected onto a 5m chart it either looks
arbitrary (doesn't touch anything a 5m eye would call a pivot) or needs a second, unrelated
detection pass just to justify its presence. Rather than patching this with a label-placement hint
after the fact (T16's `zoom_class` heuristic, which still exists and still works for the OLD
engine's multi-day lookback), the new bridge sidesteps the problem **structurally**: it takes
whatever bar window the caller hands it, and the recommended default (~240 5m bars ≈ 3 trading
days) is the SAME default `trendline_detector.annotate_decisions_with_trendline_state` already
chose independently (`lookback_bars=240`) — bounding the INPUT window keeps every anchor close
enough to "now" that it structurally cannot render off-screen, rather than detecting on a wide
window and then trying to hide the consequence.

**Per instrument/market:** this project trades SPY 0DTE only (minutes-to-hours holding period → 5m
is the natural chart-reading unit, confirmed as the standing default via `chart_get_state`'s
`chart_resolution: "5"`). A swing-holding-period instrument — the separate MES futures program is
the concrete example already in this repo (`backtest/futures/analysis/PHASE1-swing-battery`,
`MES_4h_rth_swingbattery2.csv`/`MES_daily_rth_swingbattery2.csv`) — would need its OWN
timeframe-matched detection (4h/Daily, matching its own holding period) under the identical
principle: match detection timeframe to trading/holding timeframe, never borrow another
instrument's or another timeframe's lines. Not built here (a different sibling's lane, per the
file-ownership boundary) — stated as the generalization of the same principle, not implemented for
futures.

---

## Files touched this session

| file | change |
|---|---|
| `backtest/tools/bull_trendline_reclaim_graduation_2026_08_09.py` | new — Task 1 evidence battery |
| `analysis/deep-research/BULL-TRENDLINE-RECLAIM-GRADUATION-2026-08-09.json` | new — raw output |
| `analysis/deep-research/SHADOW-SIGNAL-INVENTORY-2026-07-31.md` | appended dated correction section |
| `setup/scripts/trendline_chart_draw.py` | new — Task 2 chart-drawing bridge |
| `backtest/tests/test_trendline_chart_draw.py` | new — 8 guard tests, RED-proofed |
| `.claude/skills/trendline-draw/SKILL.md` | updated: draw_remove_one/draw_list fix, new bridge section, timeframe recommendation |
| `automation/prompts/premarket.md` | updated: same fix, factual correction only (2 spots) |
| `automation/overnight/STATUS.md` | new entry, this session |
| `analysis/deep-research/TRENDLINE-BULL-AND-CHART-2026-08-09.md` | this file |

Not touched: `backtest/lib/filters.py`, `backtest/lib/engine/engine_cli.py`,
`setup/scripts/heartbeat_core.py`, `automation/state/params.json`,
`automation/state/aggressive/params.json`, `backtest/lib/trendline_detector.py` (sibling-owned,
imported read-only), `exit_manager.py` / exit params (sibling-owned), MES futures battery
(sibling-owned).
