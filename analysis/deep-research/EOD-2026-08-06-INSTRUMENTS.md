# EOD 2026-08-06 — LENS 4: close the standing gaps J has named twice

**Clock verified at session start:** `python setup/scripts/et_clock.py` → `2026-08-06 16:13:48 Thursday EDT, market_hours=False`. All work after-hours.

**Scope:** four standing gaps. Two are now SHIPPED instruments; one is a corrected diagnosis that
**refutes the brief's premise**; one is a frozen pre-registration.

---

## 0. Headline

| # | Item | Verdict |
|---|---|---|
| 1 | Auto-draw / auto-CLEAN key levels | ✅ **SHIPPED + running.** `Gamma_ChartAutoDraw`, headless CDP, $0. J's June levels are off the chart. |
| 2 | "Dead trendline feed" | ⚠️ **PREMISE REFUTED.** The trigger was never dead — it fires on 47.8% of sessions. A *different*, consumer-less legacy file was stale. 2 real bugs fixed anyway. |
| 3 | Recurring autopsy hypothesis + `hold_to_time` | ✅ **SETTLED + oracle quarantined.** The oracle authored **90.5%** of the "money left on the table" figure. |
| 4 | Breakdown vocabulary | 📋 **Frozen prereg filed.** No code, by design. |

**Commits:** `57076d38` (auto-draw) · `47c79f0b` (trendlines) · `44578c44` (autopsy) · queue entry below.
**Guards:** 39 new tests, **12 mutations RED-proofed**. No trading-path code touched.

---

## 1. AUTO-DRAW LEVELS — shipped

### What J saw, root-caused

J's chart showed `PMH 732.62` with SPY at 770. Reproduced exactly on the live chart: **43 accumulated
shapes, 27 of them horizontal lines**, including `PMH 732.62` and `PML 728.50` — ~$38 below spot.

Two independent mechanisms, both confirmed against live state:

1. **Nothing ever subtracted.** `key-levels.json` had *correctly* retired 732.62 and 728.50 into
   `deprecated_levels` — the state file knew they were dead. But every Claude session that ever drew
   levels only ever **added**. There was no remover, so the drawings outlived their own data.
2. **Stale entries in the ACTIVE list.** `PRIOR_CLOSE_2026-06-26` @ 731.22 and `PML_2026-06-29` @ 734.52
   were still in the live `levels` array with `draw_needed: true` — June levels a naive drawer would
   faithfully redraw onto an August chart.

### The headless breakthrough

Prior art (T14, in `trendline_draw_state.py`) concluded that chart drawing *"is necessarily an on-demand
skill invocation, not a new pythonw daemon"* because `draw_shape` is a TradingView **MCP** tool.

**That was true of the MCP, not of the chart.** The MCP is a Node process that speaks CDP on port 9222
and calls `window.TradingViewApi._activeChartWidgetWV.value()`. Nothing about it is Node-specific.
`setup/scripts/tv_cdp.py` speaks the same protocol from plain Python and calls the *same* entry points
(`createShape` / `getAllShapes` / `getShapeById` / `removeEntity`) the MCP uses — deliberate parity, so the
two cannot drift into drawing different kinds of object. **No MCP, no LLM, $0.**

### Safety — how it cannot delete J's work

This is the only automation in the repo that can destroy hand-drawn chart work, so the guards are
structural, not conventional:

- Touches **only** `horizontal_line` shapes. J's trendlines / rays / rectangles are a different shape
  type and are out of reach by construction.
- Removes a line only when provably its own: recorded `entity_id`, **or** text starting with the `[G] `
  TAG (orphan recovery when state is lost).
- **Never** calls `removeAllShapes()` — it takes no scope argument and would wipe the chart. Guarded by
  an AST-based test that strips docstrings first (the naive text scan fired on the warning comment).
- `--sweep-legacy` is the single exception and is authorised **only** by an exact price match against
  `deprecated_levels` — a staleness proof taken from our own state file, not a guess about authorship.
  Dry-run unless `--apply`; every removal logged.

### Verified (OP-33)

| Check | Result |
|---|---|
| Idempotency (the actual complaint) | 3 consecutive runs: **50 → 50 shapes**, removed 11 / drew 11 each time |
| Legacy sweep | Removed exactly 4: `PMH 732.62`, `PML 728.50`, `734.97 R (exp EOD)`, `752.09 (Battle PMH)` |
| Fired through the real scheduler | `LastTaskResult=0`, state file rewritten by the scheduler at 14:30:11 |
| Fail-open (TV down = normal off-hours) | Port forced to 9999 → `SKIPPED_TV_DOWN`, **exit 0**, drawn-list preserved |
| Visual | Screenshot shows the `[G]` dashed set clustered at spot 768; June lines gone |
| Guards | 15/15, **5 mutations RED-proofed** (band filter, deprecated filter, TAG prefix, TAG pin, `removeAllShapes`) |

**Task:** `Gamma_ChartAutoDraw` — 08:35 ET weekdays, repeating every 30 min to 16:05 ET
(`Weekly Mon–Fri`, `PT30M`/`PT7H30M`). Registered in `SCHEDULED-TASKS.md` (104 → 105).

**Revert:** `git revert 57076d38` + `Unregister-ScheduledTask -TaskName Gamma_ChartAutoDraw`.

### Open, NOT actioned (needs J)

23 horizontal lines remain that are **not** provably ours and **not** on the deprecated list — including
7 blank-text lines at full float precision (e.g. `737.6775648144016`) that look script-drawn but whose
authorship cannot be proven. **I did not delete them.** Chart drawings are not git-revertible, so
unprovable authorship is where the sweep stops.
Inspect: `draw_key_levels.py --dry-run --sweep-legacy`.

---

## 2. THE "DEAD TRENDLINE FEED" — premise refuted, two real bugs fixed

### The brief's claim, and what is actually true

> *"trendline_rejection is one of six bear triggers and currently can never fire."*

**This is false, and the correction matters more than the fix.**

`detect_trendline_rejection_bearish` (`backtest/lib/filters.py:601`) is called with
`ctx.bar, ctx.prior_bars, ctx.bar_idx`. It **computes its trendline in-process from the bars**. It has
never read `trendlines.json`. The trigger has no dependency on the stale artifact at all.

**Measured over the real 387-session population** (`spy_5m_2025-01-01_2026-07-22.csv`, RTH only, the
production `lookback=60 / min_swings=3`):

| Metric | Value |
|---|---|
| Sessions with ≥1 fire | **185 / 387 (47.8%)** |
| Total fires | 653 |
| Mean fires/day | 1.69 |
| % of bars | 2.18% |

Comfortably under the C27 >80% noise ceiling. The trigger is alive and behaving.

### What *was* actually broken

**There are two trendline producers, and the healthy one was mistaken for the dead one.**

| Producer | Output | State |
|---|---|---|
| `backtest/autoresearch/trendline_engine.py` (`Gamma_Trendlines`, 5-min RTH) | `trendlines-live.json`, `trendline-watch.json` | ✅ **Healthy** — both fresh at 16:00 ET today, `LastTaskResult=0` |
| `automation/scripts/compute_trendlines.py` | `trendlines.json` | ❌ Stale — content `as_of 2026-05-14` |

**Root-cause mechanism for the stale file (named, not guessed):** its *only* caller is
`automation/prompts/premarket.md` **step 2 — an LLM instruction**. It is on **no scheduled task**. And
the premarket deliverable-gate in `run-premarket.ps1` checks **only `today-bias.json`** — so an LLM run
that silently skipped step 2 still reported success. Classic C7: *audit outputs, not exit codes.*

**Blast radius checked:** a repo-wide search found **zero code consumers** of `trendlines.json`. Only its
own producer writes it; two prompt docs mention it. This matches the standing correction that trendline
consumption was 100% shadow with zero downstream consumers.

### Two real bugs fixed anyway

1. **Lexicographic latest-file pick.** `sorted(glob("spy_5m_*.csv"))[-1]` returned
   `spy_5m_2026-07-23_supplement.csv` (5 KB, one session) instead of
   `spy_5m_2026-05-19_2026-08-06.csv` (594 KB, current), because `"2026-07"` sorts after `"2026-05"`.
   Every trendline was being fitted to one stale July session while the file claimed to be current —
   the same family as the beacon `asc+limit` truncation and L242. Now sorts by parsed **end date**,
   tie-broken by size.
2. **No staleness filter on manual lines.** Auto lines had a ±$5 proximity filter; hand-drawn ones had
   none, so May anchors were extrapolated months forward and published as current. The artifact was
   emitting `projected_price_now` of **$2,825.07** and **−$1,117.96** against a $770 spot. Now bounded
   by `MANUAL_MAX_AGE_DAYS=10` / `MANUAL_MAX_DISTANCE=$15`, with every drop logged and reasoned.

**After the fix:** reads today's real bars (ending `2026-08-06T15:55:00-04:00`), 10 auto lines all within
$5 of spot, all 7 stale May/June manual lines dropped with explicit reasons. The output now carries
`source_csv`, `bars_end_et`, `manual_dropped` and a `status_note` stating the zero-consumer SHADOW status.

**Guards:** 8/8, **3 mutations RED-proofed**.

### Consumption stays SHADOW. Promotion bar

Per the standing correction, *"valid as CALL-veto" was never validated.* Nothing here changes that.
To promote trendline context out of shadow, it would need:

1. A **frozen pre-registration committed before the runner** (git-provable via `git merge-base --is-ancestor`).
2. Real-OPRA expectancy on the 391-day population, **stratified by regime**, not WR alone.
3. The veto measured as a **paired A/B on the same cohort** — every bar where it would have vetoed,
   priced both ways. A veto is only worth having if the vetoed cohort is *reliably* negative.
4. **n ≥ 20** in the affected cohort, and BH-FDR correction across whatever else is tested with it.
5. An explicit no-harm check against the existing six bear triggers.

**Recommendation (not actioned — no consumer, so no urgency):** retire `compute_trendlines.py` and
tombstone `trendlines.json` in favour of the single healthy `trendlines-live.json` surface. Two files
where one is 84 days stale is exactly the ambiguity that produced this false alarm.

---

## 3. THE RECURRING AUTOPSY HYPOTHESIS — settled, and the oracle quarantined

### Fix 1 — `H-*-stop-noise` stops re-emitting

`mechanism: stop_inside_noise_floor` auto-emitted on **07-08, 07-16, 07-21, 07-29, 08-04** and was never
run until today. The reason is structural: `HYP_DEDUPE_DAYS = 7` is a **cooldown, not an answer**. It
guarantees an already-answered question returns every week forever, which trains the reader to ignore
the queue.

Shipped `automation/state/hypotheses-settled.json` + `load_settled_mechanisms()` / `is_settled()`, wired
into `dedupe_hypotheses()` at **both** the SPY and TWIN call sites. Seeded with the verdict reached
today:

> **REGIME_CONDITIONAL_NOT_SHIPPABLE** — Tue 08-04 cohort −$1,111 → +$2,097 across −15%..−50%;
> Wed 08-05 −$1,279 → −$613 at best (still a loss); the 391-day gap-fade slice is **monotone worse** as
> the stop widens. A knob that only pays on days you cannot identify in advance is not shippable.
> Evidence: `analysis/deep-research/STOPPED-THEN-PAID-2026-08-04.md`.

`revisit_after` is the escape hatch for regime-conditional verdicts — re-open on a **stated date**, not
weekly by default. Registry failure is **fail-open**: a corrupt file silences nothing, never everything.

### Fix 2 — `hold_to_time` was a structural winner, and it set the headline number

`hold_to_time` is `premium_stop −95% / tp1 999 / runner 999 / qty 1.0`: it holds the **full** position to
the time exit with **effectively no stop**. It wins "best counterfactual" on every trend day **by
construction** and is the worst cell on every reversal day. And `stop_cost_vs_best` was computed as
`max(ALL counterfactuals) − actual` — so that structural win became the **"$ left on the table"** figure
J reads weekly.

**Measured across all 118 historical autopsy rows:**

| | |
|---|---|
| Rows where the oracle won "best counterfactual" | 30 / 118 (**25.4%**) |
| Total positive "left on table" | **$69,350.80** |
| …authored by the oracle | **$62,778.00 — 90.5%** |
| Worst single row | `actual −$104.00` → **`$7,080.00` claimed** (`SPY260804C00762000`) |

**A quarter of the rows produced nine-tenths of the number.** That is the $6,976-on-a-−$104-trade shape
the brief flagged, found in the data.

**Fix:** `DIAGNOSTIC_COUNTERFACTUALS = frozenset({"hold_to_time"})`. Oracle probes are excluded from
`best_counterfactual` / `stop_cost_vs_best` and reported separately as `oracle_best_pnl` /
`oracle_delta_vs_actual` with an explicit not-shippable note. The honest `exit_beat_theta` tag still uses
it — quarantined, not deleted. This also de-contaminates the `exit_shape_dominated` hypothesis, which
was fed by the same column.

It was never a shippable shape: −95% is outside the −50% catastrophe cap both sides, and *hold-longer
book-wide* is already in the GRAVEYARD (−$451.50 / 21).

**Verified:** real run, `4 positions autopsied, 0 new hypotheses`, exit 0. 16/16 new guards, **4 mutations
RED-proofed**, 142 existing autopsy-related tests still green.

> ⚠️ The `sum_stop_cost: 7718.0` figure in today's queue entry `T-AUTOPSY-H-2026-08-06-left-on-table`
> is a **pre-fix artifact** — it was emitted by an earlier run today. Today's own 4 rows are unaffected
> (the oracle did not win any of them); the contamination is historical.

### Side finding — the 14:21 long

On the losing 14:21 `769C` (−$36), the **shipped exit beat every counterfactual**:
wide-stop −$162, hold-to-time −$276, tagged `exit_beat_theta`. Whatever went wrong on that trade, it was
**not** the exit. That is evidence for the entry-timing question, not the exit-shape one — n=1.

---

## 4. BREAKDOWN VOCABULARY — frozen prereg filed

Queue entry `BREAKDOWN-VOCABULARY-GAP` added to `automation/overnight/queue.md`.

**The gap:** all four live setups (`BEARISH_REJECTION_RIDE_THE_RIBBON`, `BULLISH_RECLAIM_RIDE_THE_RIBBON`,
`VWAP_CONTINUATION`, `VWAP_RECLAIM_FAILED_BREAK`) are rejections or reclaims — every one requires price to
**approach a level and turn at it**. A level that breaks and keeps going is untradeable **by construction**,
not by policy. Today's put worked because 770.24 broke and ran, but the engine entered it as a *rejection
of the reclaim attempt* — we caught a breakdown through the only door we own.

**Filed as prereg-only, with the traps named so the naive version is not rebuilt:**

- **C20 / L102 / L219** — gate direction must match setup structure; **proximity gates anti-correlate with
  breakout setups**. Every level-tied trigger we own is proximity-based; a breakout wants *distance* and
  *acceleration away*. Bolting a breakout trigger onto proximity plumbing inverts the gate and reproduces
  a failure already documented twice.
- **C27** — frequency prescreen FIRST. Levels "break" constantly; if it fires >80% of days it is noise.
  Cheapest possible kill.
- **C28** — the ribbon is lagging. AND-gating a break-and-run to a ribbon flip fires after the move is
  over — exactly what filter 5 did at 14:21 today for −$36.

**Honest prior:** breakout systems are the most over-fit family in retail 0DTE, and this one must clear a
book that is currently profitable on rejections.

---

## Ledger

| Artifact | Path |
|---|---|
| CDP client | `setup/scripts/tv_cdp.py` |
| Level drawer | `setup/scripts/draw_key_levels.py` |
| Settled registry | `automation/state/hypotheses-settled.json` |
| Guards | `backtest/tests/test_draw_key_levels_2026_08_06.py` (15) · `test_compute_trendlines_2026_08_06.py` (8) · `test_trade_autopsy_settled_oracle_2026_08_06.py` (16) |
| Screenshot | `SwjshAlgoKnife/mcp-servers/tradingview-mcp/screenshots/gamma_autodraw_verify_2026_08_06.png` |

**Not done / owed:** legacy sweep of the 23 unprovable chart lines (needs J); retirement of
`compute_trendlines.py`; the trendline promotion study (no consumer → no urgency).
