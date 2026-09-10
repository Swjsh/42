---
title: Key Levels & Chart-Reading — Audit, Benchmark, and Execution Plan
milestone: trustworthy-levels
owner_handoff_to: Sonnet agent (execution)
authored_by: Gamma (Opus) — deep-dive + first benchmark
date: 2026-06-15
framework: PAUL (PLAN -> APPLY -> UNIFY); Milestone -> Phases -> Plans -> Tasks
status: READY FOR EXECUTION (Phase 0 first)
cost_class: engine-benefit / observability (OP-22 — ships without weekend ratification; NO live-order or doctrine edits)
---

# Key Levels & Chart-Reading — Audit, Benchmark, and Execution Plan

> **For the executing (Sonnet) agent:** This document is self-contained and executable. It is the output of a full deep-dive into how Project Gamma draws key levels, how the engine and Claude "see" the chart, and the **first objective benchmark of level quality ever run on this repo.** Work the phases in order. Phase 0 is the foundation (you cannot improve what you do not measure). Each Task has **Files / Action / Verify / Done** — if any task feels ambiguous, re-read §2–§3 (the evidence) before guessing. Respect §6 (Boundaries) on every task: **never edit `automation/prompts/heartbeat*.md` or `automation/state/params*.json` to change live trading behavior without J's weekend ratification (Rule 9).** Instrumentation, benchmarks, and shadow/DRAFT proposals are always allowed.

---

## 1. Mission (Objective)

**Goal.** Make Project Gamma's key levels *provably good* — not "good because they look right," but good because we measure, every day, whether the levels we draw actually predict tradeable price reactions, and we improve the level-drawing + chart-reading pipeline against that measurement.

**Purpose.** The engine draws ~14.5 levels/day and uses them as the anchor for nearly every trigger (`level_reject`, `level_reclaim`, `confluence`, `sequence_*`). Yet until 2026-06-15 there was **zero forward-looking measurement** of whether those levels were any good. The schema even has `respect_count` / `broken_count` fields — initialized to 0 and **never incremented anywhere in the codebase.** We were flying blind on the single most load-bearing input to the strategy.

**Output of this milestone.**
1. A standing, daily-updated **level-quality scorecard** (per-source, per-regime, vs a fair null) wired into the gym.
2. **Closed instrumentation loop**: every drawn level gets graded against what price actually did; `respect_count`/`broken_count`/`bounce_history` become real, not placeholders.
3. A handful of **validated, DRAFT level-drawing + chart-reading improvements** (e.g., drop/down-weight sources with no edge, kill or fix the unvalidated "swept" upgrade, VIX-character-aware confidence, false-break + close-ceiling detectors) — each with an A/B scorecard ready for J's ratification.
4. Parity + reproducibility fixes for the gaps the audit found (strength score never recomputed, EMA fields permanently null, wick-rejection disabled, bounce_history rebuild).

---

## 2. What we found (the deep dive)

Four read-only audits mapped the system. Condensed findings with citations. **Read this before planning any task** — the line numbers are your map.

### 2.1 How levels are drawn today (the pipeline)
- **Generator (deterministic backbone):** [`backtest/lib/levels.py`](../../backtest/lib/levels.py) — `_detect_from_history()` derives the candidate set with **no look-ahead** (uses `history.iloc[:bar_idx+1]`). Sources: Globex H/L (T51), PMH/PML + premarket rejection buckets, **RTH-only** PDH/PDL/PDC (RTH-only fix 2026-05-08, levels.py:126-148), prior-day Volume-Profile POC (T53), 5-day rolling H/L, daily/weekly/monthly opens (T52), anchored VWAP from swing pivots (T57), round numbers, and a **liquidity-"swept" upgrade** (T58, levels.py:288-348).
- **Strength scoring:** [`backtest/lib/level_strength.py`](../../backtest/lib/level_strength.py) — `score_level()` → points from touch (log2), recency, multi-timeframe, volume, confluence, EMA-alignment → stars (`>=5.0`=★★★, `>=3.0`=★★, else ★). Round-number capped at ★, pivots capped at ★★.
- **Production curation (the LLM layer):** [`automation/prompts/premarket.md`](../../automation/prompts/premarket.md) Steps 2–5 — audits carry-over levels (5 mandatory fields, tier expiry: Active 24h / Carry 5 sessions / Reference 30 sessions), pulls fresh TV bars, writes [`automation/state/key-levels.json`](../../automation/state/key-levels.json) (schema v3) + [`automation/state/today-bias.json`](../../automation/state/today-bias.json), and draws lines via `mcp__tradingview__draw_shape`.

### 2.2 How the engine "sees" the chart (deterministic path)
- **Filters / chart-reading:** [`backtest/lib/filters.py`](../../backtest/lib/filters.py) — `evaluate_bearish_setup()` (10 filters) / `evaluate_bullish_setup()` (11 filters). Hard thresholds: `RIBBON_SPREAD_MIN_CENTS=30`, `LEVEL_PROXIMITY_DOLLARS=0.50`, `CONFLUENCE_TOLERANCE_DOLLARS=0.30`, `RIBBON_FLIP_LOOKBACK_BARS=3`, `VOL_BASELINE_BARS=20`.
- **Ribbon:** [`backtest/lib/ribbon.py`](../../backtest/lib/ribbon.py) + `ribbon_config.json` — EMA(13/20/48) fingerprinted to TV Saty Pivot Ribbon; stack = BULL/BEAR/MIXED; spread in cents.
- **Watcher fleet:** [`backtest/lib/watchers/`](../../backtest/lib/watchers/) — orb, bullish, v14_enhanced, opening_drive_fade, vwap, premarket_fail_fade, bearish_rejection_morning (watch-only), hs/double-bottom/rsi-divergence, sniper (watch-only), shotgun_scalper (blocked live).
- **Triggers:** `level_rejection`, `level_reclaim`, `ribbon_flip`, `confluence`/`multi_day_confluence`, `sequence_rejection`/`sequence_reclaim`, `trendline_rejection` (context-only, not an entry trigger), `wick_rejection` (function exists, **not wired into filter 10**).
- **Detection (close-based, strict):** `detect_level_rejection` = `bar.high > L and bar.close < L`; `detect_level_reclaim` = `bar.low < L and bar.close > L`.

### 2.3 How Claude "sees" the chart (live heartbeat path)
- **Per-tick prompt:** [`automation/prompts/heartbeat.md`](../../automation/prompts/heartbeat.md) (+ `aggressive/heartbeat.md`). Each tick: skip-gates → **R1 closed-bar filter** (`data_get_ohlcv(count=3)`, keep bars where `bar.time+5min <= now_et`) → VIX (cached, refresh rules) → SPY 5m + ribbon via `data_get_study_values` → 15m HTF every 5th tick → score filters 1–11 → v15.3 ribbon-conviction gates → macro-bias gate → ONE-line output + conditional `decisions.jsonl` row.
- **Levels read from JSON, not the chart.** Heartbeat reads `key-levels.json#levels[]`; it does **not** call `data_get_pine_lines`/`draw_list`. The drawn lines are cosmetic; the JSON is source-of-truth.
- **Self-tests:** `heartbeat-mcp-self-test` (infra), `heartbeat-tick-audit` (closed-bar correctness vs yfinance), `heartbeat-pulse-check` (cadence), `heartbeat-decision-trace` (per-filter trace), `pin-chain-verify` (rule-version pin).

### 2.4 How we validate today — and the hole
- **Gym:** `gym-session` aggregates 7 audits; `crypto/validators/runner.py` has **43 validator stages**. **None measure whether a drawn level was respected by price.** `v05_levels.py` counts touch events descriptively — it never grades.
- **Hypothesis grades:** [`automation/state/hypothesis-grades.jsonl`](../../automation/state/hypothesis-grades.jsonl) — ~5 manual predictions/day, graded PASS/FAIL at EOD (observed ~21% on the 24-row sample). **Never aggregated back into level scoring.** Grading is a prompt, not deterministic code.
- **Dead instrumentation:** `respect_count` / `broken_count` initialized to 0 and **never incremented** (`automation/scripts/compute_levels.py` ~lines 106-145). `bounce_history` only partially populated.
- **Relevant lessons:** L58 ("level quality is the problem, not parameters" — PDL proxy 71% sim → 47.8% real), L59 (close-ceiling distribution detector built, **not hooked to production**), L74 (SPY-space edge != option-space edge), L75 (false-break-launchpad at ★★★ on RTH open; detector specced, **not integrated**), L73/L40/L44/L45 (VIX *character* > VIX level).

---

## 3. The benchmark (the proof) — already built and run

**Built and run on 2026-06-15** (this is the "test and benchmark yourself" deliverable, not a plan):
- Script: [`analysis/level-quality/benchmark_level_quality.py`](../../analysis/level-quality/benchmark_level_quality.py)
- Results: [`analysis/level-quality/level-quality-benchmark.json`](../../analysis/level-quality/level-quality-benchmark.json) + [`level-quality-report.md`](../../analysis/level-quality/level-quality-report.md)

**Method.** For each of **219 trading days** (2025-08-01 → 2026-06-15), reconstruct the level set the engine would draw at the open (production `levels._detect_from_history`, no look-ahead), walk the day forward, classify each level's first touch as RESPECT / BREAK / CHOP, and compare every metric to a **random-levels null** (same count + price envelope). Thresholds swept (react ∈ {0.20,0.30,0.50}, window ∈ {3,6} bars). 3,183 real levels vs 9,549 random.

**Headline (react $0.30 / 6 bars):**

| Metric | Real | Random null | Lift |
|---|---|---|---|
| Touch rate (price reaches the line) | **52.8%** | 21.9% | **+30.9pp (2.4×)** |
| Respect rate *of touched* | 25.1% | 27.5% | **−2.4pp** |
| Respect rate *per drawn line* | 13.3% | 6.0% | +2.2× (all from touch rate) |
| Break rate of touched | 74.7% | 72.3% | — |
| Median reaction $ when respected | 1.81 | 1.81 | — |

**By source (real):** `multi_day` touch 34.6% / respect-of-touched 27.1% / **false-break 19.4% (best)**; `intraday` touch **73.3% (most-hit)** / respect 22.8% / **false-break 26.7% (worst)**; `round` touch 71.9% / respect 26.4%; `swept` touch 58.1% / respect 24.6% — **the swept upgrade shows no respect edge.**

**By VIX regime (real):** low-VIX respect-of-touched **28.8% (best)**, median reaction 1.17; high-VIX respect **24.1% (worst)** but median reaction **3.17 (biggest moves)**. Consistent with L73.

**The honest verdict (now measured):** The engine's level edge is **~100% placement, ~0% reaction-prediction.** Levels reliably mark *where* price goes (2.4× touch lift) but, once touched, are **no better than random at marking where price turns** (−2 to −3pp across every threshold). For a reaction-trading 0DTE strategy that enters *expecting a bounce/rejection at a level*, that is the number that matters — and it says the level itself currently adds no conditional information.

**Disclosed caveats (OP-20) — each becomes a roadmap item, do not skip:**
1. **Null is uniform-in-envelope, not distance-matched.** Real levels sit closer to price on average, so part of the +30.9pp touch lift is mechanical. The *conditional* respect result (−2.4pp) controls for this (conditions on touch) and is the robust claim. → Phase 1 adds a distance-matched null.
2. **`BREAK` is lenient** (close ≥ L+$0.15 within window) so break/respect aren't clean opposites on a market that moves; absolute rates are threshold-artifacts. Cross-threshold *lift* is the signal, not the absolute %. → Phase 1 hardens the outcome definition (ATR-scaled, directional).
3. **Tests the deterministic generator, not the LLM-curated `key-levels.json`** (git has only 1 snapshot). Premarket keep/drop/star-rating could add edge the generator lacks — **unmeasurable until we archive daily snapshots.** → Phase 0 Task 1.
4. **SPY price-space, not option premium** (L74). A "respected" level can still lose after delta/theta. → Phase 1 Task 3 adds option-space outcome.

---

## 4. The big list — everything that's missing or fragile

The full brainstorm. Each item tagged **[severity]** and the **(Phase)** that addresses it. This is the "what am I missing" answer — nothing here is dropped.

**A. Measurement / feedback loop (the core gap)**
- A1 **[CRITICAL]** No forward grading of levels; `respect_count`/`broken_count` are dead placeholders. *(Phase 0)*
- A2 **[CRITICAL]** No daily archive of `key-levels.json` → can't benchmark the *actual* curated levels, only the generator. *(Phase 0)*
- A3 **[HIGH]** Hypothesis grading is manual + a prompt, not deterministic code; never aggregated. *(Phase 0)*
- A4 **[HIGH]** No standing scorecard / gym stage for level quality; no trend over time. *(Phase 1)*
- A5 **[MED]** No option-space (premium) outcome attribution for levels (L74). *(Phase 1)*

**B. Level-drawing algorithm quality**
- B1 **[HIGH]** Intraday H/L levels: highest touch, worst respect, worst false-break — likely over-weighted. *(Phase 3)*
- B2 **[HIGH]** "Swept"/liquidity-grab conviction upgrade (T58) shows **no forward respect edge** — validate or kill. *(Phase 3)*
- B3 **[MED]** Round-number levels capped at ★ but benchmark respect (26.4%) ≈ multi-day — cap may be miscalibrated. *(Phase 3)*
- B4 **[HIGH]** Strength `stars` are **inherited, never recomputed** in premarket (score_level not called) → heartbeat prioritizes on stale scores. *(Phase 2)*
- B5 **[MED]** Level expiry windows hard-coded in protocol.md, not in params.json — un-tunable. *(Phase 3, DRAFT only)*
- B6 **[MED]** No deterministic "minimum quality to fire a trigger" gate — a ★ level fires the same as a ★★★. *(Phase 3, DRAFT only)*
- B7 **[MED]** Distance-from-spot filter ($5) can orphan legitimate Carry levels on trend days. *(Phase 3)*
- B8 **[LOW]** No false-break detector (L75) or close-ceiling detector (L59) in production despite both being specced/built. *(Phase 3)*

**C. Engine / parity / reproducibility**
- C1 **[HIGH]** `today-bias.json` EMA fields (`ema_fast/pivot/slow/sma_50`) are written `null` and never populated. Dead schema or incomplete spec. *(Phase 2)*
- C2 **[HIGH]** `wick_rejection` detector exists but is **not wired into filter 10** — J's 4/29 10:25 archetype is close-based-missed. *(Phase 2, DRAFT)*
- C3 **[MED]** `bounce_history` (drives `sequence_*` triggers) is assembled across layers and incomplete in real time; no rebuild-from-ledger at startup. *(Phase 2)*
- C4 **[MED]** Hard-coded proximity thresholds ($0.50/$0.30) with no volatility scaling. *(Phase 3, DRAFT)*
- C5 **[MED]** Silent `None` returns in trendline/wick/sweep detectors — no forensic logging. *(Phase 2)*
- C6 **[LOW]** Candlestick patterns computed but unused (dead path). *(Phase 2 cleanup)*
- C7 **[MED]** In-progress-bar (R1) fix is prompt-convention, not code — must stay covered by `heartbeat-tick-audit`. *(Phase 2 guard)*

**D. How Claude sees the chart (live)**
- D1 **[MED]** `chart_vision_observer` runs parallel but is never used to veto/confirm; two readers can diverge silently. *(Phase 4)*
- D2 **[MED]** Heartbeat has no multi-hour context (sees ~15 min of 5m + 30 min of 15m). *(Phase 4)*
- D3 **[LOW]** Near-miss alert reason is free-text Claude attribution; can mis-blame a filter. *(Phase 4 — auto-run decision-trace)*
- D4 **[LOW]** No intraday level freshness refresh; broken levels linger until next premarket. *(Phase 4, DRAFT)*

**E. Validation discipline**
- E1 **[HIGH]** Any level-drawing change needs a graduated guard + A/B scorecard + anchor-day no-regression before ratification (OP-11/OP-16). *(Phase 5)*
- E2 **[MED]** Shadow-mode harness should be able to A/B a *level-set* change, not just a filter change. *(Phase 5)*

---

## 5. The plan (PAUL: Milestone → Phases → Plans → Tasks)

**Milestone: `trustworthy-levels`.** Execute phases in order. Each phase ends with a UNIFY note (what was built, AC results, deviations). Phases 0–1 are pure instrumentation/benchmark (ship freely). Phases 2–4 produce **DRAFT** doctrine proposals (no live edits). Phase 5 is the ratification harness.

> **Wave map (parallelism):** Phase 0 Tasks 0.1/0.2/0.3 are independent (Wave 1). Phase 1 depends on Phase 0 data shape. Phases 2–4 are independent of each other and can run in any order once Phase 1 exists. Phase 5 depends on 2–4 producing proposals.

---

### PHASE 0 — Instrumentation & Ground Truth
*PLAN. Foundation: start capturing the data needed to ever know if levels are good.*

```yaml
phase: 00-instrumentation
type: execute
autonomous: true
files_modified:
  - automation/scripts/archive_key_levels.py        (new)
  - setup/scripts/run-archive-key-levels.ps1          (new)
  - analysis/level-quality/score_level_outcomes.py    (new)
  - automation/state/level-quality/ (new dir)
boundaries: instrumentation only — NO edits to heartbeat*.md, params*.json, levels.py logic
```

**AC-0.1** Given a trading day completes, When the archiver runs, Then a timestamped immutable copy of `key-levels.json` AND `today-bias.json` is written under `analysis/level-quality/snapshots/{date}/` and never overwritten.

**AC-0.2** Given an archived level set and that day's SPY 5m bars, When the outcome scorer runs at EOD, Then each level gets `{touched, first_touch_et, outcome: RESPECT|BREAK|CHOP|UNTOUCHED, reaction_dollars, false_break}` appended to `automation/state/level-quality/outcomes-{date}.jsonl`.

**AC-0.3** Given outcomes exist for a day, When the scorer finishes, Then `respect_count` / `broken_count` on the matching entries of the NEXT day's carry-over levels are incremented from real data (no longer 0-placeholders).

<task type="auto">
  <name>Task 0.1 — Daily key-levels snapshot archiver</name>
  <files>automation/scripts/archive_key_levels.py, setup/scripts/run-archive-key-levels.ps1</files>
  <action>
    Write a Python script that copies automation/state/key-levels.json and today-bias.json into
    analysis/level-quality/snapshots/{YYYY-MM-DD}/ (date = key-levels.json#for_session or today).
    Idempotent: refuse to overwrite an existing snapshot for that date (log SKIP_EXISTS).
    Wrap in a PS5.1 launcher (run-archive-key-levels.ps1) mirroring existing setup/scripts wrappers
    (system pythonw, CREATE_NO_WINDOW pattern — see L41/L81). DO NOT register a scheduled task yet;
    just provide the script + a one-line note in automation/state/SCHEDULED-TASKS.md proposing the
    16:05 ET slot for J to install. Anchor all paths to Path(__file__).resolve() (L60).
  </action>
  <verify>Run it twice; second run logs SKIP_EXISTS and does not modify the first snapshot. `ls analysis/level-quality/snapshots/` shows today's dir with both JSONs.</verify>
  <done>AC-0.1 satisfied.</done>
</task>

<task type="auto">
  <name>Task 0.2 — EOD level-outcome scorer</name>
  <files>analysis/level-quality/score_level_outcomes.py, automation/state/level-quality/ (output)</files>
  <action>
    Reuse the classification logic from analysis/level-quality/benchmark_level_quality.py
    (classify_level + tag_source) — import it, do not copy. For a given date: load that date's
    archived key-levels.json (or, for backfill, the production generator levels._detect_from_history),
    load SPY 5m bars (backtest/data merged CSVs, same loader as the benchmark), and write
    outcomes-{date}.jsonl with one row per level. Add an append-only running ledger
    level-quality-ledger.jsonl (date, n_levels, touch_rate, respect_rate_of_touched, break_rate,
    by_source breakdown). Include a --backfill START END mode that scores every historical day so we
    get a populated ledger on day one.
  </action>
  <verify>Run --backfill 2026-05-01 2026-06-15; confirm outcomes-*.jsonl files exist and ledger has ~30 rows with plausible rates (touch ~0.5, break ~0.7) matching the benchmark.</verify>
  <done>AC-0.2 satisfied.</done>
</task>

<task type="auto">
  <name>Task 0.3 — Wire real respect/broken counts back into level memory</name>
  <files>analysis/level-quality/score_level_outcomes.py (extend)</files>
  <action>
    After scoring day D, write a deterministic level-memory file
    automation/state/level-quality/level-memory.json keyed by rounded price ($0.05 buckets) holding
    cumulative {respect_count, broken_count, touch_count, last_seen, hit_rate}. This is a SEPARATE
    file — do NOT mutate production key-levels.json (that is premarket's job / Rule 9). Provide a
    read helper get_level_prior(price) that premarket COULD later consume (propose in Phase 3, do not
    wire now). Emit a STATUS line if any bucket reaches >=10 touches (enough for a stable hit_rate).
  </action>
  <verify>After backfill, level-memory.json exists; spot-check a heavily-tested round number (e.g. 750.00) shows touch_count>0 and hit_rate in [0,1].</verify>
  <done>AC-0.3 satisfied (counts come from real outcomes, not 0).</done>
</task>

---

### PHASE 1 — Productionize the Level-Quality Benchmark
*PLAN. Turn the one-shot benchmark into a hardened, standing metric with a fair null and a gym stage.*

```yaml
phase: 01-benchmark-harness
type: execute
autonomous: true
depends_on: ["00-instrumentation"]
files_modified:
  - analysis/level-quality/benchmark_level_quality.py (harden)
  - analysis/level-quality/level_quality_gym.py (new)
boundaries: measurement only
```

**AC-1.1** Given the benchmark runs, When it computes the null, Then a **distance-matched null** is available (random levels drawn to match the real levels' distance-from-open distribution), reported alongside the existing uniform null.

**AC-1.2** Given the outcome definition, When hardened, Then `reaction` is measured directionally and **ATR-scaled** (reaction in units of that day's ATR) so absolute rates are regime-comparable; the cross-threshold lift table still prints.

**AC-1.3** Given a weekly run, When the gym wrapper executes, Then it emits GREEN/YELLOW/RED on level quality (RED if respect-lift-vs-distance-matched-null ≤ 0 over the trailing window) into `analysis/gym/` and `STATUS.md`.

<task type="auto">
  <name>Task 1.1 — Distance-matched null + per-source lift</name>
  <files>analysis/level-quality/benchmark_level_quality.py</files>
  <action>
    Add a second null model: for each real level at distance d from open, draw a random level at
    open +/- d' where d' is sampled from the empirical distribution of real distances that day
    (shuffle the real |distances|, randomize sign). This isolates "did we pick the right PRICE"
    from "are our lines just closer to spot." Report respect-lift vs BOTH nulls. Add per-source
    lift vs distance-matched null (the actionable table: which sources beat chance at reaction).
  </action>
  <verify>Re-run; JSON has headline.null_distance_matched and by_source lift fields. Distance-matched touch-rate lift should shrink toward ~0 while respect lift stays the comparable signal.</verify>
  <done>AC-1.1 satisfied.</done>
</task>

<task type="auto">
  <name>Task 1.2 — ATR-scaled, directional outcome + option-space proxy</name>
  <files>analysis/level-quality/benchmark_level_quality.py</files>
  <action>
    (a) Compute per-day ATR (14-bar on 5m or daily true range); express reaction in ATR units and add
    respect@0.25xATR / 0.5xATR tiers. (b) Add an OPTION-SPACE proxy: translate the SPY reaction into
    approximate 0DTE premium move using a fixed delta assumption per moneyness (ITM-1~0.65, ATM~0.5,
    OTM-2~0.35) minus a theta drag stub, so we can flag levels whose SPY "respect" is too small to be
    tradeable after delta/theta (L74). Keep it labelled PROXY — real-fills validation is Phase 5.
  </action>
  <verify>JSON includes atr_scaled respect tiers and an option_space_tradeable_rate that is materially lower than the SPY tradeable_rate (proving the L74 gap is captured).</verify>
  <done>AC-1.2 satisfied.</done>
</task>

<task type="auto">
  <name>Task 1.3 — level-quality gym stage + weekly scorecard</name>
  <files>analysis/level-quality/level_quality_gym.py</files>
  <action>
    Wrap the scorer+benchmark into a callable that reads the trailing N-day ledger (Phase 0) and the
    benchmark, emits a one-glance verdict (GREEN: respect-lift > +2pp vs distance-matched null;
    YELLOW: 0 to +2pp; RED: <= 0), writes analysis/level-quality/weekly-{week}.md and appends a
    Known-broken line to STATUS.md on RED. Follow the gym-session skill output conventions. Propose
    (note only) a Sunday scheduled slot in SCHEDULED-TASKS.md; do not install.
  </action>
  <verify>Run it on current data; produces a weekly md + a verdict; on today's data verdict reflects the −2.4pp conditional finding (likely RED/YELLOW), proving the alarm works.</verify>
  <done>AC-1.3 satisfied.</done>
</task>

---

### PHASE 2 — Parity & Reproducibility Fixes (engine truth)
*PLAN. Fix the "computed-but-not-applied" and "specced-but-not-wired" gaps. DRAFT for anything that changes live behavior.*

```yaml
phase: 02-parity-fixes
type: execute
autonomous: true
depends_on: ["01-benchmark-harness"]
files_modified:
  - backtest/lib/level_strength.py (guard/test only)
  - backtest/tests/test_level_quality_guards.py (new)
  - strategy/candidates/ (DRAFT proposals)
boundaries: NO live heartbeat/params edits. Code that changes live scoring → DRAFT + graduated guard only.
```

**AC-2.1** Given premarket inherits levels, When stars are needed, Then either premarket recomputes `score_level()` OR a guard test fails loudly proving stars are stale (B4). Decide via benchmark: do recomputed stars correlate with respect? Write the finding.

**AC-2.2** Given the wick_rejection detector, When benchmarked against the close-based `level_rejection` on J's anchor archetypes, Then a DRAFT scorecard quantifies what wick-rejection adds (C2) — no live wiring.

**AC-2.3** Given parity-critical invariants (R1 closed-bar, trigger normalization, strength freshness), When the new guard test runs, Then it fails if any regresses (graduate to `backtest/tests/`).

<task type="auto">
  <name>Task 2.1 — Does star-rating predict respect? (B4)</name>
  <files>analysis/level-quality/benchmark_level_quality.py (extend), strategy/candidates/2026-xx-star-vs-respect.md</files>
  <action>
    For each benchmarked level, compute its score_level() stars (call level_strength on the as-of
    history) and stratify respect-rate by star tier. If ★★★ respect >> ★ respect, the formula works
    and the bug is that premarket never recomputes it → write a DRAFT proposal to have premarket call
    score_level. If stars do NOT separate respect, the formula itself is the problem → document which
    components (touch/recency/mtf/volume/confluence/ema) correlate with respect and propose a reweight.
  </action>
  <verify>Benchmark JSON gains by_star_tier respect table; DRAFT candidate states the verdict with numbers.</verify>
  <done>AC-2.1 satisfied (data-driven decision recorded).</done>
</task>

<task type="auto">
  <name>Task 2.2 — Quantify wick-rejection value (C2)</name>
  <files>analysis/level-quality/wick_vs_close_study.py (new), strategy/candidates/2026-xx-wick-rejection.md</files>
  <action>
    On all 219 days, find bars where high>L but close>=L (close-based MISS) and measure the forward
    reaction. If these "wick rejections" produce respect at a rate comparable to true close-rejections,
    the close-based filter 10 is leaving edge on the table (L's 4/29 archetype). Quantify added
    signal count + respect rate. Output DRAFT candidate ranked by edge_capture per OP-16. NO heartbeat edit.
  </action>
  <verify>Study prints N wick-rejections, their respect rate vs close-rejections; DRAFT candidate exists.</verify>
  <done>AC-2.2 satisfied.</done>
</task>

<task type="auto">
  <name>Task 2.3 — Graduated guards for level invariants</name>
  <files>backtest/tests/test_level_quality_guards.py</files>
  <action>
    Add pytest guards: (1) strength stars recomputed on a fixture differ from a deliberately-stale
    inherited value (proves freshness detection); (2) trigger strings are normalized (no price suffix)
    before ledger write (L79/L80); (3) the benchmark's no-look-ahead property holds (levels for D
    unchanged when future bars appended — mirror test_no_lookahead_future_bars). Keep them fast.
  </action>
  <verify>pytest backtest/tests/test_level_quality_guards.py passes; flipping one invariant makes it fail.</verify>
  <done>AC-2.3 satisfied.</done>
</task>

---

### PHASE 3 — Level-Drawing Algorithm Improvements (DRAFT proposals)
*PLAN. Use the benchmark to drop dead weight and add validated detectors. Every change is a DRAFT scorecard for J.*

```yaml
phase: 03-drawing-improvements
type: research
autonomous: true
depends_on: ["01-benchmark-harness"]
files_modified:
  - analysis/level-quality/* (studies)
  - strategy/candidates/* (DRAFT proposals + A/B scorecards)
boundaries: levels.py changes allowed ONLY behind a flag + A/B scorecard; NO live default change without J.
```

**AC-3.1** Given source-level respect data, When sources with no edge are identified (intraday H/L B1, swept B2), Then a DRAFT proposes down-weighting/removing them, with the before/after benchmark + anchor-day no-regression (OP-16) attached.

**AC-3.2** Given the false-break (L75) and close-ceiling (L59) detectors, When ported into the benchmark, Then each is shown to improve respect/avoid bad entries on historical data before any proposal.

**AC-3.3** Given VIX-character data, When stratified, Then a DRAFT proposes regime-aware level confidence (L73) with OOS validation (no single-window overfit).

<task type="auto">
  <name>Task 3.1 — Source pruning study (B1, B2, B3, B7)</name>
  <files>analysis/level-quality/source_pruning_study.py, strategy/candidates/2026-xx-source-pruning.md</files>
  <action>
    Re-run the benchmark with each source toggled off; measure the change in aggregate respect-lift
    and in downstream backtest edge_capture (run the existing backtest with the pruned level set on the
    anchor days). Specifically test: (a) drop raw intraday session H/L, (b) remove the swept upgrade,
    (c) lift the round-number ★-cap, (d) exempt Carry tier from the $5 distance filter. Keep ONLY
    changes that improve respect-lift AND do not regress the OP-16 anchor winners. Output DRAFT.
  </action>
  <verify>Study table shows respect-lift delta per source-toggle; DRAFT candidate lists keep/kill with anchor-day P&L unchanged or better.</verify>
  <done>AC-3.1 satisfied.</done>
</task>

<task type="auto">
  <name>Task 3.2 — Port + validate false-break (L75) and close-ceiling (L59) detectors</name>
  <files>analysis/level-quality/pattern_detectors_study.py, strategy/candidates/2026-xx-falsebreak-closeceiling.md</files>
  <action>
    Implement the L75 rule (open-bar low > $0.25 below a ★★★ level AND close back above → suspend bear
    entries 30 min) and L59 (N>=3 bars wick>=level, close<level → distribution) as pure functions over
    history. Measure on 219 days: how many bad entries would each have avoided, and the P&L delta on the
    anchor losers (5/05, 5/06, 5/07). DRAFT proposal only; reference crypto/lib/chart_patterns.py if a
    detector already exists there.
  </action>
  <verify>Study reports avoided-loss count + anchor-day deltas; DRAFT candidate written with OP-16 edge_capture.</verify>
  <done>AC-3.2 satisfied.</done>
</task>

<task type="auto">
  <name>Task 3.3 — VIX-character-aware level confidence (L73)</name>
  <files>analysis/level-quality/regime_level_study.py, strategy/candidates/2026-xx-regime-levels.md</files>
  <action>
    Split respect-rate by VIX character (level vs 5-day-avg, trending vs spike-revert) not just VIX
    level. If trending-high-VIX levels respect materially differently than spike-high, propose a
    regime-confidence multiplier. Validate IS/OOS (split the 219 days) to avoid the L73 over-fit trap;
    require WF ratio sanity. DRAFT only.
  </action>
  <verify>Study shows respect-rate by VIX-character with IS/OOS columns; DRAFT records WF ratio.</verify>
  <done>AC-3.3 satisfied.</done>
</task>

---

### PHASE 4 — How Claude Sees the Chart (live-path robustness, DRAFT)
*PLAN. Reduce LLM/engine divergence and add the missing context — proposals + shadow only.*

```yaml
phase: 04-live-reading
type: research
autonomous: true
depends_on: ["01-benchmark-harness"]
boundaries: NO heartbeat.md behavior change without J. Shadow/observer/auto-audit wiring is allowed.
```

**AC-4.1** Given `chart_vision_observer` runs in parallel, When its calls are graded vs heartbeat decisions over history, Then a report quantifies where vision would have helped/hurt (D1) — informational, gated for J.

**AC-4.2** Given a near-miss tick, When it fires, Then `heartbeat-decision-trace` is auto-run and its structured blocker (not free-text) is logged (D3).

<task type="auto">
  <name>Task 4.1 — Vision-vs-heartbeat divergence report (D1, D2)</name>
  <files>analysis/level-quality/vision_divergence_report.py</files>
  <action>
    Pair vision-observations.jsonl with decisions.jsonl by tick; tag ALIGNED/DIVERGED/vision-only/
    heartbeat-only; grade each against next-bar truth. Report whether vision adds level-reaction signal
    the numeric path misses. Also prototype a "multi-hour context" feature (count of same-level tests
    today, session trend) and measure if it separates respect. Informational only.
  </action>
  <verify>Report exists with divergence counts + accuracy-when-diverged; multi-hour feature shows a respect separation (or not, documented).</verify>
  <done>AC-4.1 satisfied.</done>
</task>

<task type="auto">
  <name>Task 4.2 — Auto-trace near-misses (D3)</name>
  <files>strategy/candidates/2026-xx-auto-decision-trace.md</files>
  <action>
    Propose (DRAFT) wiring heartbeat-decision-trace to auto-run when a near-miss alert fires, writing
    the structured blocker to decisions.jsonl instead of free-text. Spec the exact field; do not edit
    heartbeat.md. Include the cost estimate (OP-3).
  </action>
  <verify>DRAFT proposal with field spec + per-day cost estimate.</verify>
  <done>AC-4.2 satisfied.</done>
</task>

---

### PHASE 5 — Ratification Harness (eval-first)
*PLAN. Make level changes ratifiable the same way rule changes are.*

```yaml
phase: 05-ratification
type: execute
autonomous: true
depends_on: ["02-parity-fixes","03-drawing-improvements"]
boundaries: produces scorecards; J ratifies. NO auto-flip of production defaults.
```

**AC-5.1** Given a DRAFT level-set change, When the shadow harness runs it, Then it produces an A/B scorecard at `analysis/recommendations/{rule_id}.json` meeting the OP-11 auto-ratify gates (dominates, data_hash_match, thresholds_4_of_4, sub_window_stable, evidence_n>=20) — or clearly fails them.

**AC-5.2** Given any proposed change, When evaluated, Then the OP-16 J-edge anchors are re-scored (winners not regressed, losers not worsened) and real-fills authority is respected (L50/L71).

<task type="auto">
  <name>Task 5.1 — Level-set shadow A/B</name>
  <files>analysis/level-quality/level_shadow_ab.py</files>
  <action>
    Extend the shadow concept to swap the LEVEL SET (not just filter knobs): run the backtest with
    baseline vs candidate level generator over the full window + anchor days, emit the OP-11 scorecard
    JSON. Reuse backtest/lib + j_edge_tracker; verify strike-offset parity first (2026-05-23 incident).
  </action>
  <verify>Produces analysis/recommendations/{candidate}.json with all gate booleans + edge_capture; anchor winners >= prior.</verify>
  <done>AC-5.1 + AC-5.2 satisfied.</done>
</task>

---

## 6. Boundaries (GLOBAL — apply to every task)

```
## DO NOT CHANGE (without J's explicit weekend ratification — Rule 9)
- automation/prompts/heartbeat.md, automation/prompts/aggressive/heartbeat.md
- automation/state/params.json, automation/state/aggressive/params.json
- automation/prompts/premarket.md (live behavior)
- Any code path that PLACES or alters conditions for live orders

## ALWAYS ALLOWED (OP-22 engine-benefit / observability)
- New analysis/benchmark/validator/test scripts
- DRAFT proposals + A/B scorecards in strategy/candidates/ and analysis/recommendations/
- Reading any state; archiving snapshots; gym stages
- Editing backtest/lib/levels.py ONLY behind a flag with an A/B scorecard (default unchanged)

## DISCLOSURE (OP-20) — every result must state:
- N (sample size), IS vs OOS split, the null/baseline used, and the metric definition
- Real-fills is the only WR authority (L50/L71); BS-sim is ranking-only
- SPY price-space edge != option-space edge (L74)

## ANTI-REGRESSION (OP-16)
- Re-score the immutable J-edge anchors before any proposal; winners must not regress
```

---

## 7. Open questions / Discovery (resolve while building)

1. **Curated vs generated levels:** Once Phase 0 archives ~10 days of real `key-levels.json`, re-run the benchmark on the *curated* set. Does the LLM premarket curation add the reaction edge the raw generator lacks? (If yes, the fix is "trust curation more"; if no, the fix is in the generator.)
2. **Is "respect once touched" even the right target for 0DTE?** Maybe the placement edge (touch rate) is the real, tradeable edge and the strategy should lean into "price will reach this zone" rather than "price will bounce here." Worth a DRAFT framing for J — it could reshape the playbook.
3. **What is J's own hit-rate when he draws levels manually?** Compare J's manually-drawn trendlines/levels (read via `read_chart_drawings.js` → `trendlines.json`) against the same benchmark. If J's hand-drawn levels show real respect edge and the auto-generator doesn't, that gap *is* the edge to encode (OP-16 spirit).
4. **Confluence as the quality filter:** does requiring 2+ confluent sources (not just ±$0.30 proximity but multi-source agreement) lift respect above random? Confluence is the one lever the audit suggests could add conditional edge — test it early.
5. **Time-of-day:** do morning levels (J's 4/29, 5/04 archetypes) respect better than midday? Stratify by hour.

---

## 8. Definition of done (milestone)

- [ ] Daily `key-levels.json` snapshots archived; ledger populated; `respect_count`/`broken_count` come from real outcomes (Phase 0).
- [ ] Standing level-quality scorecard with a **distance-matched null** + option-space proxy, wired to the gym with a RED alarm (Phase 1).
- [ ] Graduated guards lock the parity invariants; star-vs-respect and wick-rejection questions answered with data (Phase 2).
- [ ] At least 2 DRAFT level-drawing improvements with A/B scorecards + anchor no-regression (Phase 3).
- [ ] Vision-divergence + near-miss-trace reports inform the live path (Phase 4).
- [ ] Level-set shadow A/B harness exists; one candidate run end-to-end through the OP-11 gates (Phase 5).
- [ ] **The headline number moves:** respect-lift-vs-distance-matched-null is positive and stable, OR we have a documented, ratified decision that placement (not reaction) is the edge we trade.

---

_Evidence base: 4 read-only audits (level pipeline, engine eyes, Claude's eyes, validation surface) + a 219-day benchmark, all 2026-06-15. Benchmark code/results live in `analysis/level-quality/`. This plan changes nothing live; it makes level quality measurable, then improvable._


---

## 9. TA DIAL-IN work order (2026-09-09) — "too many lines; what is the engine actually acting on?"

> Written 2026-09-09 ~23:30 ET by Fable 5.1 (judgment + plan only, per J: *"I don't want you to work on it. Plan it all out, then we flip to Opus."*). Evidence gathered fresh this session: live `draw_list` (68 shapes), `draw_get_properties` on the three lines J named, `automation/state/trendlines.json`, `chart_drawings.json`, a Sonnet read-only codebase audit, and two Sonnet web-research crews (canon docs: [`TRENDLINE-BREAK-LITERATURE` Part 2](../research/TRENDLINE-BREAK-LITERATURE-2026-07-14.md#part-2--trendline-construction-canon-external-research-2026-09-09) · [`INTRADAY-LEVELS-CANON`](../research/INTRADAY-LEVELS-CANON.md)). **Freeze:** shape-changing edits wait for 2026-10-30; everything marked NOW below is drawing / shadow / capture-only and does not change which trades are taken.

### 9.1 Verdict

**J cannot see what the engine trades because the engine never draws it.** The only trendline that gates an entry is fitted in-process, per tick, inside `backtest/lib/filters.py::detect_trendline_rejection_bearish` (pivot HIGHS, descending only, 60-bar lookback) and is never rendered. Every trendline on the chart — the `[GTL]` auto-lines, the 25 untagged lines back to May, J's own — is decoration relative to the entry gate. Levels: the gate reads only bare prices from `key-levels.json` within **$12** of spot; the chart draws up to **$15** and 14 lines, so the picture and the gate disagree by construction.

### 9.2 The three lines J named — mechanism, verified

| Line | What it is | Why it looks wrong |
|---|---|---|
| Red, 774.01 (09-03 13:45) → down-right, `[GTL] [WICK] RESISTANCE touch x5` (id `TJsQJS`) | engine auto-line, `Gamma_TrendlineHeadlessDraw` | J agrees it is good. Keep as the reference case for v2. |
| Cyan, 767.53 (09-03 09:30) → 759.82, `[GTL] [WICK] SUPPORT touch x3` (id `5iZLKB`) | engine auto-line | **Touch count is inflated by construction:** a "touch" is any bar whose extreme is within `max($0.10, 0.15% × price)` ≈ **$1.15** of the line (`trendline_engine.py:324`); `PIVOT_K = 1` makes nearly every bar a pivot; closes *through* the line only cost −5 in score, they are not disqualifying (`_fit`, `:320-333`). Canon's single most-agreed rule — a line may not cut through intervening price (Sperandeo; every algo scorer) — is not enforced. |
| Blue ray, **773.07 @ 09-03 08:30 ET** → 760.39, no label (id `UvNj5Q`) — J's line, lower wedge boundary | J hand-drawn | **Structurally impossible for the engine, twice:** (1) both fitters drop premarket bars (`compute_trendlines.py:143`, `trendline_engine.py:154`) so an 08:30 anchor cannot exist — canon says include premarket for SPY/ES, 08:30 ET is a named high-volatility moment; (2) `trendline_engine._fit` requires SUPPORT to ascend (`p2 <= p1 → continue`, `:311`) so a **descending support** (the lower rail of a falling wedge / channel) cannot be produced at all. |

Two more defects found on the way (not J-visible, but they corrupt the ledger the redesign must measure against):

- **Manual capture mislabels engine lines as J's and drops J's real line.** `compute_trendlines._load_manual_drawings` filters by TradingView *type* string `("trendline","trend line")` only (`:166`) — the engine's own `[GTL]` `trend_line`s pass and are written as `source: manual_chart_draw` (live `trendlines.json` lists `5iZLKB`/`TJsQJS` that way), while J's `ray` is rejected by the type filter. The correct population logic already exists in `j_drawn_lines_capture.py::_non_engine_trend_lines` (excludes `[GTL] ` by text) — two pipelines, one right.
- **Nothing ever clears lines it did not draw.** `draw_key_levels.py` and `trendline_headless_draw.py` each remove only their own tag. The 23 untagged trendlines (anchors from 2026-05-08 onward), 4 rays, ~15 orange unlabeled premarket LLM lines, "Death Cross", "R at LOW", "*** 769.24 BROKEN now RESISTANCE ***" have **no producer in the repo** (grep-verified) — session-ephemeral `draw_shape` calls that accumulate forever. 68 shapes today = 37 horizontal + 25 trend_line + 4 ray + 1 rectangle + 1 horizontal_ray.

### 9.3 What the engine ACTS on today (so the chart can show exactly that and nothing else)

| Input | Path | Status |
|---|---|---|
| `key-levels.json` bare `price` within $12, non-expired | `heartbeat_core._read_levels` → `filters.py` level_rejection / reclaim / confluence / wick_rejection | **ACTED-ON** |
| `role`/`multi_day` booleans | → `multi_day_levels` | ACTED-ON |
| `tier`/`label`/`touches`/`memory_score` | `conviction.score_conviction` (`shadow_only=True`) | SHADOW |
| In-process descending pivot-high trendline (60 bars, 3 swings, 0.10 % proximity) | `filters.py:758-870` | **ACTED-ON — never drawn** |
| Bullish trendline reclaim | `filters.py:1101` | SHADOW |
| BOS / CHoCH structure | `crypto/lib/market_structure.py` | ACTED-ON (veto input) |
| `trendlines.json`, `trendlines-live.json`, `confluence-zones.json` | — | zero consumers (doctrine-noted) |
| Every drawn shape, incl. J's | — | DECORATION to the gate |

Level types emitted by `refresh_levels_intraday.py`: intraday swing/RTH high-low, PMH/PML, prior-day H/L/C, multi-week shelf, level-memory. **Missing vs canon tier-1:** initial balance / opening range, VWAP + SD bands, developing value area / POC, gamma walls (0DTE-specific). Live file today: 20 levels (12 res / 8 sup).

### 9.4 Canon rules the redesign encodes (each cited in the research docs)

1. Pivots first (zigzag / fractal extrema with ATR-scaled prominence), lines only through pivots — never score touches against raw bars.
2. Touch tolerance = ATR fraction (~0.15–0.25 × 5m ATR), not 0.15 % of price. Emit the **touch ledger** (bar timestamps counted) with every line so a human can check the count.
3. **Hard constraint:** zero closes through the line between first anchor and now. Wick-through allowed only inside the tolerance band.
4. 2 pivots = DRAFT, 3rd touch = CONFIRMED. Only CONFIRMED lines are drawn.
5. Include premarket bars (04:00–09:30 ET) for pivots and anchors; RTH-only stays for the *break* logic.
6. Support may descend, resistance may ascend (channels / wedges exist). The second rail of a channel/wedge = parallel line off the single most-extreme opposite pivot, never an independent fit (Murphy / Bulkowski / Brooks).
7. Wick-vs-body: keep J's all-wick-XOR-all-body rule per line as an engineering convention (canon is contested, not against it).
8. Break = body close beyond line + buffer + persistence — already how `Trendline.status` works; do not regress it.
9. Levels are ZONES (already doctrine): merge levels within the zone width (ATR-based, ~0.3–0.5 % of price for 5m work; canon quotes 0.5–1.5 % for swing) into one band; staleness is **event-driven** (broken-and-not-retested), not calendar-driven.
10. Indicator minimalism: VWAP earns a slot; a 9-EMA ribbon + SMA 50/200 + Saty pivot ribbon on one 15m chart matches no named school (Brooks / Grimes). *Presented as canon, not as Gamma's aesthetic call — J decides the layout.*

### 9.5 Workstreams (Opus = judgment items, Sonnet = builds; all NOW items are freeze-compatible)

| # | Workstream | Owner | When | Deliverable · guard · revert |
|---|---|---|---|---|
| A | **Draw what you trade.** `heartbeat_core` writes `automation/state/engine-view.json` per tick: the in-process trendline it fitted (anchors, proximity band, status) + the ≤$12 active level set with the role/multi_day booleans the gate read. `trendline_headless_draw.py` gains a second tag `[GE]` (engine-acting) drawn solid; `[GTL]` shadow lines become dashed/thin or off by default. Purely additive read-out of values the gate already computed — no gate logic changes. | Sonnet | NOW | guard: engine-view fields == filters.py inputs on a replayed tick; revert = `git revert` |
| B | **Chart hygiene sweep.** New `setup/scripts/chart_hygiene.py` (fired inside `Gamma_ChartAutoDraw`): (1) J-registry — any untagged shape captured once in `automation/state/j-shapes.json` is J's and is never touched; (2) untagged shapes NOT in the registry and older than 2 sessions, plus orphan `[G]`/`[GTL]` outside the band → removed; (3) draw band 15 → 12 to match the gate; (4) `draw_key_levels` merges levels within the zone width into one rectangle (zone) with weight = tier. Dry-run first, log every removal id+text to `analysis/chart-hygiene/{date}.jsonl`. Never `draw_clear`. | Sonnet | NOW | guard: registry shapes survive 100 mutation runs; revert = re-draw from ledger |
| C | **Trendline fitter v2 (shadow).** New `backtest/lib/trendline_fit_v2.py` implementing §9.4 1–7. Bars = 04:00–16:00 ET 5m. Output = lines + touch ledger + draft/confirmed flag + channel rail. Validation = **reproduce J's hand-drawn lines**: `j-drawn-lines-ledger.jsonl` + tonight's `UvNj5Q` (773.07@1788438600 → 760.39@1788989400) as ground truth; metric = anchor within 1 × tolerance and slope within 10 % for ≥ 80 % of J's lines, AND v1's cyan line is NOT produced. Runs shadow beside v1 via `Gamma_TrendlineShadow`; the `filters.py` detector is untouched until 10-30. | Sonnet build → Opus reviews the ledger | NOW (shadow) | guard: J-line reproduction test; v1 untouched |
| D | **One manual-capture pipeline.** `compute_trendlines._load_manual_drawings` delegates to `j_drawn_lines_capture._non_engine_trend_lines` (text-tag exclusion, include `ray` / `horizontal ray`), and `trendlines.json` stops labelling engine lines `manual_chart_draw`. | Sonnet | NOW (30-min fix) | guard: `[GTL]` line never `manual`; a `ray` is captured; revert = `git revert` |
| E | **Canon levels as drawn context.** Add initial balance (09:30–10:30 H/L), opening range 5/15, VWAP ± 1σ/2σ, prior-day VWAP as **drawn** `[G]` zones with their own weight. Emitted into `key-levels.json` under a new `role: "context"` that `_read_levels` ignores (so the gate is unchanged) — flip to gate input is a 10-30 prereg. Gamma walls: only if a $0 source exists (C36 — check wired pipes first; no new vendor). | Sonnet | NOW (drawn) · 10-30 (gate) | guard: `_read_levels` output byte-identical with/without context rows |
| F | **Opus judgment items.** (1) Ratify the tag taxonomy: `[GE]` = acts-on, `[G]` = level context, `[GTL]` = shadow fitter, untagged = J. (2) Read WS-C's ledger against J's lines and decide whether v2 replaces v1 in `filters.py` at 10-30 — prereg it now (`analysis/prereg/`) with the kill criterion: if v2-gated entries on the 40-day window are not ≥ v1 on ex-best-day PF, v1 stays. (3) Decide the zone-width constant from the ATR study (WS-C emits it). (4) Verify Murphy's 3 %/2-day rule from primary text before any constant is named after it (flagged UNVERIFIED by the crew). (5) Indicator layout — put the canon in front of J once, in one line, then implement whatever he says. | Opus | first Opus session | — |

### 9.6 Order of operations (no time units — order only)

D → B (dry-run, then apply) → A → C (shadow ledger accumulates) → E (drawn) → F(1,3,4) → F(2) prereg → 10-30 decision → F(2)/E gate flips ship or die.

### 9.7 Definition of done

- Opening the chart shows **one** solid engine layer (`[GE]`: the line + ≤ $12 zones the gate read on the last tick), J's own shapes untouched, everything else dashed or gone. Shape count on a normal day ≤ ~20 (from 68).
- `trendlines.json` `manual` entries are J's lines only, rays included.
- v2 shadow ledger reproduces J's blue 08:30-anchored line and does not reproduce the cyan `touch x3` line — quoted, not claimed.
- Every drawn trendline carries its touch ledger in the label (`touch x3 @ 08:30, 10:15, 13:45`), so "it doesn't touch three times" is checkable in five seconds.

### 9.8 Boundaries

- No edit to `filters.py`, `heartbeat_core` gating, `refresh_levels_intraday` band/selection, or `params*.json` before 10-30 (freeze). WS-A adds a *read-out*, not a gate.
- Never `draw_clear`. Never remove a shape in the J-registry. Never redraw during 09:30–15:55 ET beyond the existing 30-min cadence.
- No new paid data vendor for gamma levels (OP-3 / C36).

---

### 9.9 ADDENDUM (2026-09-09, Opus execution session) — prior coverage WS-C must build on, not around

> Written while executing §9.6's order (D → B → A → C → E → F). Recorded here rather than in a
> new file per OP-22 (fold, don't accumulate). Every claim below was read from source this
> session and is quoted, not recalled.

**§9.5 row C says "New `backtest/lib/trendline_fit_v2.py`". That framing is wrong and would have
produced a second implementation of a read that already exists (L251).** `backtest/lib/
trendline_detector.py` (32 KB, 2026-08-09) already satisfies most of §9.4:

| §9.4 rule | State in `trendline_detector.py` | Evidence |
|---|---|---|
| 1 — pivots first, never raw bars | **DONE** | `_fit_candidate` walks `same_kind_swings` only; `DEFAULT_PIVOT_WINDOW = 2` (`:124`). Pivot identification is not home-grown — it reuses `crypto.lib.trendlines.find_swing_points` (`:88`), the exact primitive `crypto.lib.market_structure.analyze_structure` itself calls, and window 2 *"matches `crypto/lib/market_structure.DEFAULT_WINDOW`"* (`:122`) |
| 2b — emit the touch ledger | **DONE** | `_Candidate.touch_bar_indices`; plus `DEFAULT_MIN_BARS_BETWEEN_TOUCHES = 6` (`:131`, Tori "6+ candles between taps") and `DEFAULT_MIN_SPAN_BARS = 6` (`:137`) — spacing rules v1 lacks entirely |
| 4 — 3 touches | **PARTIAL** | `DEFAULT_MIN_TOUCHES = 3` (`:126`); the DRAFT(2)/CONFIRMED(3) split is missing |
| 6 — support may descend | **ALREADY POSSIBLE** | `_fit_candidate(require_slope: Literal["any","rising","falling"])` (`:288`) rejects on slope *only when the caller asks*. A descending support is a **caller config**, not a code gap — this is the single biggest divergence from `trendline_engine.py`'s hard `p2 <= p1 → continue` (`:311`) |
| 7 — wick XOR body per line | **DONE** | `_body_view` (`:228`) / `_view_for_mode` (`:249`) with an `AnchorMode` |
| 3 — zero closes through | **HALF DONE — the real gap** | the violation set IS computed (*"every CLOSED bar from anchor_a onward whose CLOSE broke through the line"*) but only **scored**: `score = len(touches) - VIOLATION_PENALTY * len(violations) + (i2 - i1) * SPAN_BONUS_WEIGHT`. Canon says a close through is **disqualifying**, not a penalty |

**Genuine remaining gaps — the true WS-C scope:**

1. **ATR-scaled tolerance.** `DEFAULT_TOUCH_TOLERANCE_DOLLARS = 0.20` (`:120`) is a fixed dollar
   amount. Canon rule 2 wants ~0.15–0.25 × 5m ATR. **Fair warning — this constant is not
   thoughtless:** its own comment ties it to J's *"levels are zones, not prices"* (2026-07-17) and
   says *"this IS the zone width."* So WS-C is not correcting an oversight, it is making a
   deliberate constant **adaptive** — the ATR study (F(3)) must show the fixed $0.20 is materially
   wrong across regimes before the swap is justified, not merely that ATR-scaling is more
   fashionable.
2. **Closes-through disqualifying** (`max_close_violations=0` as an option), default preserving
   today's scoring.
3. **DRAFT vs CONFIRMED** status; only CONFIRMED is drawable.
4. **Premarket bars 04:00–09:30 ET** — a *loader*-side gap (`bars_from_dataframe`, `:553` and its
   callers), not a detector gap.
5. **The parallel channel/wedge rail** — genuinely absent.

**Revised instruction:** extend `trendline_detector.py`, each gap behind a parameter whose default
reproduces today's exact behaviour, plus a thin "v2 profile" entry point that switches them on
together. A separate module is acceptable only if it *imports* the detector rather than
re-deriving pivots/touches/violations.

**Prior art on WS-C's own acceptance test — read before rediscovering it:**

- [`analysis/deep-research/2026-09-03-money/trendline-today-exhibit.md`](../../analysis/deep-research/2026-09-03-money/trendline-today-exhibit.md) `/.json` — a mechanical,
  read-only attempt to reproduce J's 2026-09-03 rising support against this same detector. It
  already establishes which of J's lines the detector can and cannot construct, and why: on 15m,
  J's literal `08:15` anchor is **never a confirmed swing-low pivot even with full-day hindsight**
  (`06:45`/`07:30` are lower and dominate the same fractal neighbourhood). That is the WS-C
  metric's hardest case, already characterised.
- [`analysis/recommendations/prereg-trendline-rising-support-human-anchor-2026-09-03.md`](../../analysis/recommendations/prereg-trendline-rising-support-human-anchor-2026-09-03.md) — FROZEN,
  built and scheduled: `setup/scripts/trendline_human_anchor_shadow.py` +
  `Gamma_TrendlineHumanAnchorShadow`, backfilled once, decision gated forward-only past
  2026-10-30. If WS-C's shadow wiring would duplicate this fire, **piggyback on it — no new
  scheduled task.**
- `prereg-trendline-rising-support-v2-human-anchor-PROPOSAL-2026-09-03.md` is SUPERSEDED; read the
  file above instead.

### 9.10 RATIFIED (2026-09-09, Opus) — the drawing-tag taxonomy [F(1)]

Four layers, one meaning each. This is decided, not proposed — implement against it.

| Tag | Layer | Meaning | Drawn as |
|---|---|---|---|
| `[GE] ` | **acts-on** | The line and zones the gate actually read on the last tick. If it is not `[GE]`, it did not gate a trade. | **Solid**, full weight |
| `[G] ` | level context | Key levels and (later, WS-E) canon context: IB, opening range, VWAP bands, prior-day VWAP | Zones, weight by tier |
| `[GTL] ` | shadow fitter | The auto-fitted trendline lane. Shadow. Never gated a trade. | **Dashed / thin, or off by default** |
| *(untagged)* | **J** | Anything a human drew. Registry-protected, never touched by any script. | As J drew it |

Three rules that follow, and are not negotiable:

1. **A tag is a claim about causality, not about who drew it.** `[GE]` means *this gated*. Nothing may
   wear `[GE]` unless `heartbeat_core` wrote it into `engine-view.json` on a real tick. The whole
   point of §9 is that J currently cannot tell decoration from decision; a loose `[GE]` recreates the
   exact problem in a new coat of paint.
2. **The prefix set lives in ONE place, imported, never copied.** Today `TAG` is defined twice —
   `setup/scripts/draw_key_levels.py:66` (`"[G] "`) and `setup/scripts/trendline_headless_draw.py:81`
   (`"[GTL] "`) — and `setup/scripts/j_drawn_lines_capture.py:69` already does the right thing by
   importing rather than re-declaring. Every new consumer (WS-B hygiene, WS-D capture, WS-A engine
   view) imports the same tuple. L251: two spellings of the same tag silently disagree, and the
   thing that disagrees here is *what gets deleted off J's chart*.
3. **Untagged is J by definition, and the default is KEEP.** No heuristic may promote an untagged
   shape to deletable. If a producer wants its shapes cleanable, it tags them. An unrecognised shape
   is a human being, not garbage.


### 9.11 F-item resolution ledger (Opus session 2026-09-09) — append as each resolves

| F | Item | State | Where it landed |
|---|---|---|---|
| F(1) | Ratify the tag taxonomy | ✅ **RATIFIED** | §9.10 above |
| F(2) | Prereg the v2 → `filters.py` swap, with the kill criterion | ✅ **FROZEN** | [`prereg-trendline-fitter-v2-swap-10-30-2026-09-09.json`](../../analysis/recommendations/prereg-trendline-fitter-v2-swap-10-30-2026-09-09.json) — classified SHAPE CHANGE (10-30 only, never 09-29); metric = `go_live_gate.py::statistical_criterion()` reused verbatim; **DEFAULT = v1 stays** |
| F(3) | Zone-width constant from the ATR study | ⚠️ **RE-SCOPED — see §9.13 B.** The premise was wrong: `zone_width`/`zone_width_provenance` already exist per-level, and `_zone_width()` explicitly forbids hand-picking (*"pending a pre-registered A/B study (never hand-picked)"*). Opus must NOT name a constant off WS-C's ATR distribution — the honest F(3) output is a **pre-registered A/B**, with the ATR study as its input. WS-B's merge uses each level's own `zone_width`, flag-OFF meanwhile |
| F(4) | Verify Murphy 3 %/2-day from primary text | ✅ **RESOLVED — see verdict below** | [`TRENDLINE-BREAK-LITERATURE` § "Murphy 3%/2-day rule — provenance check (2026-09-09)"](../research/TRENDLINE-BREAK-LITERATURE-2026-07-14.md) |
| F(5) | Indicator layout | ⏳ **WITH J** — one line, see below |
| — | WS-A state writer | ⛔ **HELD to 2026-10-30** (§9.17). Frozen-path hook blocked it; override NOT used. Verified diff staged at `analysis/recommendations/packages/engine-view-readout-ws-a/` |
| — | WS-A2 `[GE]` chart layer | ⛔ **BLOCKED by the above** — it renders `engine-view.json`, which does not exist until A1 applies |

#### F(4) verdict — the constant may NOT carry Murphy's name

Primary text reached (archive.org full OCR of *Technical Analysis of the Financial Markets*, ch. 4
pp. 71–72; the earlier crew's single fetch had only surfaced the table of contents). Three-part grade:

- **VERIFIED-PRIMARY** — the 3 % figure, a 1 % variant, and the two-day figure are all Murphy's own
  words, quoted verbatim with page numbers in the research doc.
- **SUPPORTED-SECONDARY-ONLY** — the popular "3 % **AND** 2-day, applied together" framing is *not*
  what Murphy wrote. He presents them as **alternatives**: *"An alternative to a price filter… is a
  time filter."* Do not encode them as a joint requirement.
- **UNSUPPORTED AT ANY GRADE for SPY 0DTE** — Murphy is describing daily/weekly closes on
  longer-term trendlines, and disclaims universality even there (*"The 3% rule doesn't apply to some
  financial futures…"*). **3 % of SPY at ~$765 is ~$23** — larger than most entire SPY sessions on a
  5-minute chart. The number cannot transfer.

**Consequence for §9.4 rule 8:** the break-confirmation constant is an **ATR-scaled buffer + N-bar
persistence**, derived at 5-minute/0DTE scale, and must be named accordingly — e.g. a
"Murphy-style filter concept, re-derived for 5m/0DTE", never `MURPHY_3PCT` / `MURPHY_2DAY`. A
constant named for an authority that did not say it is a hallucinated citation with a code path
attached; the naming rule is the guard against that.

#### F(5) — the one line for J (layout is J's taste, not Gamma's)

Canon says VWAP earns a permanent chart slot; and a **9-EMA ribbon + SMA 50/200 + Saty pivot ribbon
on one 15m chart matches no named school** (Brooks / Grimes). That is the canon read, presented once
as §9.4 rule 10 requires — **J names the layout he wants and it gets implemented verbatim.** Until
then the current layout stands unchanged; nothing here is acted on unilaterally.

### 9.12 Accuracy pass (Opus, 2026-09-09) — §9.2's v1 claims re-verified from source

§9.2 was written by the previous session. J asked for an accuracy review, so every load-bearing v1
claim was re-read from `backtest/autoresearch/trendline_engine.py` this session. **All four hold**,
with the exact text now pinned so no future session has to take them on trust:

| §9.2 claim | Verdict | Source line, read this session |
|---|---|---|
| `PIVOT_K = 1` makes nearly every bar a pivot | ✅ **CONFIRMED** | `:67` — `PIVOT_K = 1  # swing pivot = extreme of a +/-PIVOT_K window` |
| Touch tolerance ≈ `max($0.10, 0.15 % × price)` | ✅ **CONFIRMED** | `:66` `TOL = 0.10`; the touch test is `abs(extreme - lv) <= max(TOL, 0.0015 * lv)` — 0.0015 = 0.15 % |
| Closes through only cost −5, not disqualifying | ✅ **CONFIRMED verbatim** | `score = respect - 5 * violations + (i2 - i1) * 0.1` |
| Support must ascend, so a descending support is impossible | ✅ **CONFIRMED** | `if kind == "support" and p2 <= p1: continue  # support must ascend through higher-lows` |

Two refinements §9.2 did not capture:

- **The touch walk is per-BAR, not per-pivot.** The respect/violation loop iterates every bar `j`
  between the anchors and tests `px(bars[j])` — which is exactly why "touch x3" is inflated. This
  *strengthens* §9.2's diagnosis rather than weakening it.
- **v1 already enforces canon rule 7 (wick XOR body)** — by hard `assert` on both anchors sharing
  one field (*"wick-only anchor invariant violated — both anchors of a {kind} line must be the SAME
  wick field"*). So the wick/body rule is **not** a v1 gap; do not spend WS-C effort re-adding it.

**Net:** the v1 defect list shortens to three real items — per-bar touch counting, non-disqualifying
close-throughs, and the ascending-support-only constraint (plus the premarket exclusion, which is
loader-side). Everything else §9.4 asks for already exists somewhere in the repo.

### 9.13 Accuracy pass, part 2 — two defects **in the work order itself** (Opus, 2026-09-09)

Found while scoping WS-E and F(3) against live code. Both were verified from source and from the
live `automation/state/key-levels.json` (15 levels) this session.

#### 🚨 A. WS-E's `role: "context"` design would BREAK THE FREEZE — do not build it as written

§9.5 row E says context levels are *"emitted into `key-levels.json` under a new `role: "context"`
that `_read_levels` ignores (so the gate is unchanged)."* **`_read_levels` would not ignore them.**

- `heartbeat_core._read_level_records(spy)` — the single parse — filters on **exactly two things**:
  `_level_expired(...)` and `abs(p - spy) <= 12`. **There is no role filter anywhere in it.**
- `_read_levels` then appends **every** returned record to `active`:
  `active.append(round(float(p), 2))`, unconditionally. Only the *second* list, `multi`, is
  role-conditional.

So a `role: "context"` row inside the $12 band would land straight in the gate's **active level
list** and change which levels the engine trades against. That is precisely the class of change the
config freeze exists to stop, and row E is labelled freeze-compatible "NOW" work. Building it as
specified would have shipped a silent gate change under a "drawing only" label.

**Corrected design — context levels do NOT go into `key-levels.json` at all.** Write them to a
separate `automation/state/context-levels.json` that only the drawing path reads. Then:
- `_read_levels` and `_read_level_records` need **zero code changes**, so the guard row E asks for
  (*"`_read_levels` output byte-identical with/without context rows"*) is true by construction
  rather than by a new filter added to a frozen path;
- the 10-30 "flip to gate input" prereg becomes an explicit, reviewable merge of one file into
  another, instead of a role string quietly acquiring meaning.

#### B. F(3) is not "pick a zone-width constant" — the repo already pre-committed to a method

`zone_width` and `zone_width_provenance` are **already per-level fields**, live on 11 of 15 levels:

| provenance | count | width |
|---|---|---|
| `shelf_band_observed` | 8 | 0.80 (measured from the actual shelf band) |
| `default_pre_ab` | 3 | ~0.38 (`max(ZONE_WIDTH_MIN, price × ZONE_WIDTH_PCT)`) |
| *(absent)* | 4 | — |

`refresh_levels_intraday._zone_width()` (`:294`) states the standing rule outright: *"This is a
DEFAULT band pending a pre-registered A/B study (never hand-picked) — every level carries
`zone_width_provenance='default_pre_ab'` so a future study knows which levels still run on the
default vs a validated width."*

**Consequences:**
1. Opus must **not** hand-pick a global constant from WS-C's ATR distribution — that is exactly the
   "never hand-picked" this code forbids. F(3)'s honest output is a **pre-registered A/B**, and the
   ATR study is its input, not its verdict.
2. **WS-B's zone merge must use each level's own `zone_width`** where present, falling back to
   `_zone_width(price)` — never a single global number. Eight of fifteen live levels already carry
   an *observed* width; collapsing those onto one constant would discard measured information in
   favour of a guess.
3. The four levels with no `zone_width` at all are a real gap worth closing separately.

### 9.14 Accuracy pass, part 3 — §9.3's "zero consumers" row is wrong, and it is a delete-hazard

§9.3's last table row reads: *"`trendlines.json`, `trendlines-live.json`, `confluence-zones.json` —
zero consumers (doctrine-noted)."* Verified from source this session: **two of the three have live
consumers.** They are all SHADOW consumers — no entry is gated — but "zero consumers" is the kind of
claim that gets a file deleted or a producer switched off.

| File | Actual consumers, read this session |
|---|---|
| `confluence-zones.json` | `heartbeat_core._read_confluence_zones()` (`:532`), **called at `:706` and `:731`** — feeds the conviction score's C7 zone stack |
| `trendlines-live.json` | `heartbeat_core._read_shadow_trendlines()` (`:631`) → the `conviction_tl` SHADOW variant; **and `setup/scripts/confluence_producer.py:45` (`TREND_F`)**, which is what *produces* `confluence-zones.json` |
| `trendlines.json` | `self_check.py:1029` D9 liveness guard; surfaced by `obsidian_vault_sync.py:959`. self_check's own note calls it *"SHADOW, zero code [consumers]"* — so for this file alone the §9.3 claim is roughly right |

**Why this matters more than a footnote:** there is a **chain** — `trendline_engine` →
`trendlines-live.json` → `confluence_producer.py` → `confluence-zones.json` → conviction C7. Acting
on "zero consumers" by retiring `trendlines-live.json` (a tempting cleanup once WS-C's v2 exists)
would silently empty the confluence zone map, and conviction C7 would degrade to 0 while still
reporting a score. `_read_confluence_zones` **fails open by design** (returns `None` on
missing/unreadable/stale), so the breakage would be **invisible** — no exception, no RED, just a
quietly worse score. That is a C7-doctrine silent failure waiting to happen.

**Corrected wording for §9.3:** the row should say **"zero GATE consumers; live SHADOW consumers
exist — see §9.14 before retiring any of them."** WS-C in particular must not assume
`trendlines-live.json` is free to replace: run `/fable-blast-radius` on that chain first.

### 9.15 WS-D/WS-B verification + one bug Opus caught in review (2026-09-09)

#### 🐛 Bug found in WS-D at review: `text: null` was being adopted as one of J's lines

`_is_engine_tagged()` coerces `None → ""` (`t = text or ""`), so a drawing with `text: null`
returned `False` and was **accepted as a hand-drawn line**. `read_chart_drawings.js` fails *soft* to
`null` on any shape exposing neither `properties()` nor `getProperties()` — so an **unreadable
ENGINE line was indistinguishable from an untagged one**, silently reinstating the exact defect WS-D
exists to fix, while every counter still reported health. That is worse than the original bug,
because the original was at least visible in `trendlines.json`.

Discriminator that makes the fix safe: **J's real lines carry `""`, never `null`** — all 23 rows of
`j-drawn-lines-ledger.jsonl` are `text: ""`. So `null` is never J and always "provenance unproven":
dropped, and counted in its **own** bucket (`n_dropped_null_text`) so an unreadable-accessor failure
is distinguishable from the old-schema one.

**RED-proofed, not assumed** — with the check disabled the guard fails exactly as predicted:
```
FAILED test_drawing_with_null_text_is_dropped_not_treated_as_js
FAILED test_empty_string_text_is_js_line_but_null_is_not
2 failed, 5 passed     <- check disabled
7 passed in 0.92s      <- check restored
```

#### ✅ WS-D's UNVERIFIED item is now RESOLVED — live chart, this session

The agent correctly flagged the JS text accessor as unprovable offline. Run live via `ui_evaluate`
against the real chart:

```
total=67  withProps=67  viaProperties=67  viaGetProperties=0
nullText=0  emptyText=39  tagged=16
sample: "[GTL] [WICK] SUPPORT | touch x3 | INTACT | 1788444600"
        "[G] INTRADAY SWING LOW 762.28"   "PDH 776.85 (R)"
```

- The `properties()` accessor works on **67 / 67** shapes; the `getProperties()` fallback is never
  needed on this build (keep it — it costs nothing and this is one TradingView release).
- **`nullText = 0`** today. The guard above is still correct defensive coding, not dead code — it
  converts a future accessor break from *silent misclassification* into a *loud counter*.
- The `[GTL]` sample is J's cyan line, caught in the act: **`touch x3`** on the line he says does not
  touch three times (§9.2).

#### ✅ Two independent reads agree — the shape census reconciles exactly

WS-B counted engine-tagged shapes via `tv_cdp.shape_text` (`getShapeById` path); the check above
used `model.dataSources().properties()` — **completely different accessors, same answer: 16.**

| Bucket | n | Source |
|---|---|---|
| Total shapes on chart | **68** | `draw_list` (Opus, this session) |
| … of which line-tools | 67 | the 1 difference is `MLzAHd`, a `rectangle` — correctly outside the line-tool regex |
| Engine-tagged (`[G]`/`[GTL]`) | **16** | agreed by **both** independent reads |
| J's, registered | **52** | `68 − 16` ✓ — WS-B registry, `newly_registered=52` |
| … empty text `""` | 39 | the classic untagged trendlines/rays |
| … human-labelled text | 12 | `PDH 776.85 (R)`, `SHELF 754.71 - downside target` — the "orphan premarket LLM lines" of §9.2, correctly kept as J's |

J's ray `UvNj5Q` is in the registry with anchors matching §9.5 exactly. **Combined regression suite:
`75 passed in 28.59s`.**

#### ⚠️ Expected, and correct: manual capture reads ZERO until the JS re-runs
On the current on-disk `chart_drawings.json` (pre-`text` schema) `compute()` now returns
`n_dropped_no_text=28`, i.e. **no manual lines at all**. That is the fail-loud design working: the
snapshot cannot prove any line is J's. It self-heals on the next `trendline_manual.refresh()` tick
(5-min RTH). It is called out here so nobody reads that zero tomorrow as "J drew nothing."

### 9.16 WS-C returned a NULL: 0/24. Opus review — the null is real, and it agrees with prior art

WS-C reported **0 of 24 of J's lines reproduced** against an 80 % bar, and correctly refused to tune
until it passed. Because a 0 is exactly as suspicious as a 100, the result was attacked rather than
accepted. **Two hypotheses were raised and both were falsified by measurement.**

#### Hypothesis 1 — the anchor-match tolerance is absurdly tight. FALSIFIED as the cause.

It *is* absurdly tight, and that is a genuine defect worth fixing:

| | |
|---|---|
| 5m ATR across J's 24 lines | **$0.1134 – $0.5457** |
| anchor-match bar actually used (`0.20 × 5m ATR`, floored at $0.01) | **$0.023 – $0.109** |
| SPY tick / typical spread | $0.01 / ~$0.01–0.02 |

A **2.3-cent** bar on a *hand-drawn* anchor is not a test a human can pass. The validator's floor was
`max(0.20 × atr, 0.01)` — a one-cent floor is no floor. **But raising it changes nothing:**

```
floor=$0.01 -> n_pass 0     floor=$0.20 -> n_pass 0     floor=$0.50 -> n_pass 0
floor=$0.10 -> n_pass 0     floor=$0.38 -> n_pass 0
```
*(floor confirmed propagated: `anchor_tol_floor: 0.5`, `tolerance_dollars` all $0.50)*

#### Hypothesis 2 — anchor TIME is the binding constraint. Also FALSIFIED as the cause.

Plausible, because **all 23 ledger rows carry `drift_detected: true`** — J's own capture pipeline
flags that anchor *time* is not reliable to bar precision between the 5m and 15m reads (price
identical, time differs by a non-constant offset), and 3 lines have **no bar within 600 s of anchor1
at all** (nearest 840 s / 1200 s / 1290 s). Requiring a pivot within 600 s of a *drifted* timestamp
tests the capture, not the fitter. Sweeping it:

```
600s -> 0     900s -> 0     1800s -> 1     3600s -> 1     7200s -> 1     21600s -> 1
```
Relaxing time from 10 min to **6 hours** buys exactly **one** line. Not the cause either.

#### The verdict: the null is robust, and it is not new

0/24 survives an ~8× loosening on price and a 36× loosening on time. **v2 is not failing to *match*
J's lines; it is not *constructing* them at all** — while it does produce lines in general (9
CONFIRMED for 2026-09-08). So J draws lines that a pivot-anchored, zero-close-through fitter does not
produce.

**That conclusion already exists in this repo, from a different implementation.**
`analysis/deep-research/2026-09-03-money/trendline-today-exhibit.md` ran `backtest/lib/
trendline_detector.py` — a completely separate fitter — at J's 2026-09-03 rising support and found it
*"could not construct J's specific rising support line… on either 5m or 15m, with or without
premarket bars"*, and that J's literal 08:15 anchor is **never a confirmed swing-low pivot even with
full-day hindsight.** Two independent fitters, same answer. This is a **replication, not an anomaly.**

#### What this actually means for the work order

1. **Do NOT read 0/24 as "v2 is broken."** It is not evidence about v2's quality. It is evidence
   about the *acceptance metric*.
2. **"Reproduce J's hand-drawn lines" may be the wrong acceptance test.** It presumes J's lines are
   pivot-constructible. Two implementations now say they are not. Either J anchors on something that
   is not a fractal pivot (a zone edge, a body, a remembered level, an eyeballed best-fit), or the
   ledger's drifted timestamps make exact reproduction unrecoverable in principle — §9.5's own
   metric cannot distinguish those, which is its defect.
3. **The honest next question is a fork, and it belongs to J** (see §9.17): is the goal to *replicate*
   J's hand, or to build a line whose *breaks trade well*? Those need different tests entirely.
4. **F(2)'s prereg is unaffected and its DEFAULT already handles this correctly:** clause (e)
   requires the WS-C reproduction ledger to have passed its own bar. It did not. So under the frozen
   rule as written, **v1 stays at 10-30** unless the metric itself is re-preregistered. That is the
   prereg working as designed, not a problem to route around.
5. **Correction to canon rule 2 (§9.4):** "0.15–0.25 × ATR" cannot mean **5-minute** ATR on SPY — that
   yields a sub-spread band. The literature's fraction is of the ATR *on the timeframe being drawn*.
   Any tolerance constant must be floored at the repo's own established zone width
   (`TOUCH_TOLERANCE_USD` = `DEFAULT_TOUCH_TOLERANCE_DOLLARS` = **$0.20**), which is also the answer
   F(3) was reaching for — and which the repo already reasoned its way to once.

**Validator changes made at review** (so the sensitivity is measurable, not assumed): tolerance floor
and anchor-time tolerance are now env-overridable (`GAMMA_V2_TOL_FLOOR`, `GAMMA_V2_TOL_ATR_FRACTION`,
`GAMMA_V2_TIME_TOL_SEC`), floor default raised $0.01 → $0.20. Canonical re-run left on disk at
`anchor_tol_floor: 0.2`, `anchor_time_tol_sec: 600`, `n_pass: 0`.

### 9.17 WS-A is HELD to 2026-10-30 — and §9.8's "WS-A adds a read-out, not a gate" was wrong

#### What happened
WS-A's state writer needs two edits to files on `setup/hooks/doctrine.py::FROZEN_TRADING_PATH` —
`backtest/lib/filters.py` and `setup/scripts/heartbeat_core.py`. The doctrine hook **hard-blocked**
them. The agent **refused to use `GAMMA_FREEZE_OVERRIDE`** and escalated instead of self-authorising.
That was the right call and it caught an error in the Opus scoping that sent it.

#### The Opus scoping error, stated plainly
The WS-A spec asserted the trace-sink edit was *"deliberate and bounded: the freeze bars changes to
which trades are taken, and a keyword-only parameter defaulting to `None` … changes nothing about
which trades are taken."* **That is not what the freeze protects.** `markdown/infra/DOCTRINE-HOOKS.md`
names the real mechanism:

> *"A trading-path edit **silently invalidates `go_live_gate.py`'s 20-day score** — the most expensive
> available mistake between those dates."*

The freeze protects the **score**, not merely the behaviour. A provably return-identical edit still
moves a file on the scored path inside the window whose entire value is that nothing on it moved.
Behavioural neutrality is not the test; **untouchedness** is. §9.8's assurance that "WS-A adds a
read-out, not a gate" is therefore not a freeze exemption, and should not be read as one.

#### The ruling

| | |
|---|---|
| **Verdict** | **HELD to 2026-10-30.** Not applied, not overridden. |
| **Why not 09-29** | The 09-29 checkpoint admits **pre-registered kill-type risk REDUCTIONS only**. WS-A is additive instrumentation — neither a risk reduction nor eligible on that date. Both options the agent offered named 09-29; **both were wrong on the date**, and that correction is the point of this section. |
| **Why not override** | `GAMMA_FREEZE_OVERRIDE`'s documented scope is exactly those pre-registered reductions. Stretching it to cover instrumentation is the same failure mode as naming a constant after an authority who did not say it (§9.11 F(4)) — a documented mechanism bent past its stated meaning. |

#### What ships instead of a stall
The verified diff is staged on the shared surface as a checkpoint package —
`analysis/recommendations/packages/engine-view-readout-ws-a/` (scaffolded by
`setup/scripts/checkpoint_package.py`: `README.md`, `apply.ps1` which refuses without the override,
`guard_test.py`, `change.patch`). Held work still lands where the next session finds it (C35);
applying at 10-30 is a one-minute job, not a redesign.

**The design is already verified, on real data, before being held:**
```
[GUARD1] compared=11286 fired=1191 none=10095      <- trace=None vs trace={}, zero mismatches
[GUARD1] exit_reason histogram: {'insufficient_pivots': 6296,
         'rejection_criteria_not_met': 2095, 'trendline_below_spot': 1587,
         'pivots_not_decreasing': 117}
11 passed in 2.00s
records: 14  active: 14  multi: 14   parity active: True   parity multi: True
```
Pre-existing quirk found and deliberately NOT fixed (it is on the frozen path): `slope_not_negative`
is mathematically unreachable — pivot selection is "max of a shrinking subset", so the OLS slope can
never be positive, and ties are caught earlier by `pivots_not_decreasing`.

#### Consequence for WS-A2 and the §9.7 definition of done
**A2 (the `[GE]` chart layer) cannot ship before 10-30 either** — it renders `engine-view.json`, which
does not exist until A1 applies. So §9.7's headline outcome (*"opening the chart shows ONE solid
engine layer"*) is **not reachable inside the freeze**, by construction. What IS reachable now, and
has shipped: J's shapes protected by the registry, engine lines no longer mislabelled as his, the
draw band matched to the gate, and the `[GTL]` shadow lane correctly labelled as shadow.

### 9.18 WS-E shipped on the corrected design + one defect Opus caught (2026-09-10)

Built to §9.13 A, **not** to row E's original wording. Context levels never touch
`key-levels.json`: new producer `setup/scripts/context_levels.py` → a separate
`automation/state/context-levels.json`, read only by `setup/scripts/draw_context_levels.py`.
`heartbeat_core.py`, `filters.py`, `refresh_levels_intraday.py`, `params*.json` — **zero edits.**

**The freeze guard is not vacuous — it has a bite test:**
```
test_read_levels_byte_identical_with_and_without_context_levels_file PASSED
test_bite_merging_context_rows_into_key_levels_json_DOES_change_gate_output PASSED
```
The bite proves the point of §9.13 A empirically: merging a context row into `key-levels.json`
(row E's **original** design) *does* change `_read_levels`' active list. Keeping it in a separate
file does not. The defect was real, and the corrected design provably avoids it.

**All 5 families emitted — including gamma walls, which the work order expected to be skipped.**
C36 paid off: `Gamma_CboeOiBank` (registered 2026-06-22, **$0**, free CBOE CDN) was **already wired
and banking**. Verified by Opus: `BANKED 40530 contracts (native_gamma=True) -> journal/gex-archive/
2026-09-08-cboe.json`. No new vendor, no new fetch — a thin adapter into the existing
`gex_regime.compute_gex_regime`, reading only the local archive. Checking the wired free pipes first
is exactly what C36 asks for.

Every level carries `zone_width` **and** `zone_width_provenance` (`ib_or_range_observed`,
`vwap_sigma_observed`, or the ratified `default_pre_ab` fallback imported from
`refresh_levels_intraday`) — nothing hand-picked, per §9.13 B.

#### 🐛 Defect caught at review: gamma walls had no staleness bound

`_latest_cboe_archive()` returns the newest archive **at or before** the session date with **no lower
bound**. The agent stamped `stale: true` and appended a warning to the source string — good — but a
*two-week-old* archive would still be **drawn**, merely flagged. Gamma walls are a fast-decaying
OI-positioning read; a stale wall is not "stale context", it is a **wrong line on J's chart** — the
precise disease §9 exists to cure.

**Not hypothetical.** `journal/gex-archive/` has **no file for 2026-09-05 or 2026-09-09**, and
`known-gaps.json` records neither, so the banker misses days *silently*. (Two earlier gaps ARE
documented there, both `mechanism: scheduled_task_did_not_fire`, both unbackfillable — the CBOE CDN
is current-day-only, so a missed day is gone forever.)

Fix: `MAX_ARCHIVE_STALENESS_DAYS = 4` (covers a Fri-bank → Tue-read long weekend) — beyond it, emit
**nothing** and record the reason, rather than a quietly-wrong level. Walls now also carry
`staleness_days` as a **number**, not just a bool. RED-proofed:
```
1 failed, 10 passed   <- cap disabled
63 passed in 1.51s    <- cap restored, full regression incl. draw_key_levels,
                         chart_hygiene, level_compiler_v2, audit_fix_heartbeat
```
The **root cause is UNFIXED and flagged** to `automation/overnight/STATUS.md ## Known broken` as
`CBOE-OI-BANK-SILENT-MISSES`: a daily $0 producer that misses days without raising. The staleness cap
is a blast shield, not a repair.

**UNVERIFIED:** `context_levels.main()` and `draw_context_levels.py`'s live TradingView path were not
exercised end-to-end this session (import-sanity only). Verify by running the producer against real
Alpaca bars and drawing to a live chart.

**Deliberate design note:** range families (IB, opening range) draw as a high/low **line pair**, not
a filled rectangle — no zone primitive was invented while `ZONE_MERGE_ENABLED` remains unratified
(F(3)). Flagged because the work order said "zones."

### 9.19 The trade-outcome A/B — v2 is DEAD, and the real finding is about v1 (2026-09-10)

J, on the whole TA dial-in: *"why would nothing you did touch the trading? it needs to be drawing us
better tech analysis to trade off of."* He was right, and it forced the correct question. §9.16
already showed "does v2 reproduce J's lines" was the wrong test. This asked the right one — **do
either fitter's lines gate better trades** — by harness-level A/B (no edit to `filters.py`, no
`GAMMA_FREEZE_OVERRIDE`) over **45 real, already-filled `trendline_rejection` bearish entries**,
4 real-fills arms, **19 days, 2026-07-02 → 2026-09-08**.

#### Result 1 — v2 is dead. Stop polishing it.
**v2 fired on 0 of 45 real-fill bars** (0 of the 16 where the harness confirms v1 reproduces its own
real entry). It is not a broken detector — a 5-day full scan shows it firing 0–9×/day *elsewhere* —
it simply selects a **geometrically disjoint set of lines** from v1. That corroborates §9.16's 0/24
from a completely independent angle. Every ACT clause of the frozen prereg fails; **v1 stays**.

#### Result 2 — production's knobs are already the best cell. No cheap win.
Sweeping the three existing v1 parameters one at a time against the same real-fill bars:
```
lookback_bars   40:-$1069   50:+$49   60:+$104 <-PROD   70:-$1007   80:-$700
min_swings       2:-$4       3:+$104 <-PROD   4:+$160 (n=9, 7d)
proximity_pct  .0005:+$10   .0010:+$104 <-PROD   .0015/.0020:-$60   .0030:-$268
```
No cell clears a material bar; every ex-best-day CI-lower stays under 0.1 and every N sits under the
prereg's own 15-entry / 20-day minimums. The `proximity_pct` 0.0015–0.002 cells show a marginally
higher *as-traded* CI-lower (0.169 vs 0.159) but **worse** total P&L (−$60 vs +$104) — textbook
small-N noise. **No parameter change recommended, no new prereg warranted.**

#### Result 3 — the uncomfortable one: the population we already trade is NET NEGATIVE
`statistical_criterion()` (reused verbatim from `go_live_gate.py`) on v1's **real fills**:
```
as_traded:      ci_lower_2.5 = 0.257   pf_point 0.886   total_pnl  -$271.00
ex_best_day:    ci_lower_2.5 = 0.167   pf_point 0.669   total_pnl  -$784.00  (dropped 2026-08-20)
cost_adjusted:  ci_lower_2.5 = 0.254   pf_point 0.878   total_pnl  -$290.67
WR diagnostic: 33.3% (15/45)
```
**Profit factor below 1 on all three cuts, and it gets materially worse when its single best day is
removed.** So "better TA to trade off of" is not a drawing problem and not a fitter problem — on this
evidence the bear-trendline setup itself may not carry edge.

#### Three caveats that stop this from being a kill order today
1. **Attribution is impure.** These are entries whose `triggers` list *includes* `trendline_rejection`
   — an entry can carry it alongside `confluence` / `level_reclaim`. This is *"entries carrying the
   trigger"*, **not** *"entries caused by the trigger."* A clean attribution study has not been run.
2. **N is under the bar.** 19 scored days vs the prereg's own `n_min_scored_days: 20`.
3. **Prior evidence points the other way on the relative question.** `STATUS.md`'s
   `LOSS-MECHANISMS-READ-2026-09-08`: *"Trendline-only rail HOLDING (n=41, −2.17/tr; rest-of-book
   −4.73/tr, WR 25 pct)."* Trendline-only is the **least bad** rail in the book. Killing it could
   make the book worse, not better — that is the C15 trap (a gate that looks bad alone may be
   carrying the book relative to its alternative).

#### The next question, and its checkpoint
Whether to **throttle or kill trendline-gated entries** is a **kill-type risk reduction**, which makes
it eligible at the **2026-09-29** safety checkpoint — *not* 10-30, unlike the fitter swap. It needs
its own prereg, guard, RED-proof and revert line, and above all a **clean single-trigger attribution
study** to settle caveat 1 first. That study is the next piece of real work on this thread; it is
freeze-compatible (read-only) and does not depend on any drawing work.

**Artifacts:** `analysis/trendline-v2/ab_replay_2026_09_10.py`, `ab_replay_results_2026_09_10.json`,
`param_sweep_results_2026_09_10.json`, `RESULTS-2026-09-10-trade-outcome-ab.md`. The frozen prereg
received an `amendments` entry only (its interim-look clause); `decision_rule` verified byte-unchanged.

**Disclosed limitation:** the harness reproduces only 16 of v1's 45 real entries (single-day bar frame
vs production's continuous cross-day window). The P&L figures above come from the **real fills**, not
from harness reproduction, so they stand; the 16/45 limits only the paired per-bar comparison.
