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
