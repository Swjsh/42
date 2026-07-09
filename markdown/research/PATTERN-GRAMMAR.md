# Pattern Grammar — chart patterns as a grammar over existing primitives

> Spec + design record for `backtest/lib/patterns/`, `backtest/tools/pattern_prescreen.py`,
> and the C27 pre-screen run of 2026-07-09. **NO WIRING**: nothing described here is
> imported by the live engine, `setup_dispatch.py`, or any watcher. This is a research
> foundation — one registry, one pre-screen, one battery path — not 30 bespoke detectors.
>
> Companion reference: [`TA-PATTERN-REFERENCE.md`](TA-PATTERN-REFERENCE.md) (detection
> geometry + Bulkowski/StockCharts citations). This doc does not repeat that one's
> citation discipline — it inherits it: a published number is quoted verbatim with its
> source page; where none exists, the text says so plainly. Nothing here invents a
> failure-rate statistic.

---

## 0. The thesis

A chart pattern is not a bespoke piece of code — it is a **named boolean composition of
primitives the codebase already computes**: market structure (swings, HH/HL/LH/LL,
BOS/CHoCH), named/memory levels, VWAP, Bollinger-bandwidth compression, volume expansion,
wick geometry, and gaps. Before this build, every new "pattern idea" in this codebase
became its own file (`crypto/lib/chart_patterns.py`, `ribbon_rejection_wick_detector.py`,
`gap_and_go_watcher.py`, `market_structure_watcher.py`, ...) — each re-deriving its own
notion of "level," "wick," "volume spike," sometimes 3-4 times over (see 1.7). That is
fine for a handful of hand-tuned, individually-validated setups; it does not scale to
testing dozens of textbook chart-pattern candidates.

**`backtest/lib/patterns/` is the grammar layer.** A `PatternRule` = a name + a pure
boolean composition of ~15 small, orthogonal predicates, evaluated on closed bars only.
`backtest/tools/pattern_prescreen.py` is the **cheap filter**: it runs every registered
rule over 18 months of cached SPY history in about 100 seconds, for $0, and tells you
which ones are even worth a real (expensive) P&L battery run. Section 3 is the exact
handoff into that battery.

---

## 1. Primitive inventory

Everything below is **read, not rebuilt**. Where a primitive has more than one
implementation, that duplication is called out explicitly — it is direct evidence for
why a shared grammar layer is worth building.

### 1.1 Memory levels / role-flips

| | |
|---|---|
| **Live feed** | `automation/state/key-levels.json` (schema v3) — array of level dicts: `price, type, role, tier ("Active"\|"Reference"), source, verified_at, expires_at, memory_score?, touches?, role_flips?, flipped_at?, reasoning, entity_id, draw_needed`. |
| **Shadow feed** | `automation/state/key-levels-memory.json`, written by `setup/scripts/level_memory_producer.py`. |
| **Producer** | `setup/scripts/level_memory_producer.py` — `select_levels(raw: list[Level]) -> list[dict]` (filter `memory_score>=MIN_MEMORY(20)`, dedup into $0.60 zones, cap TOP_N=12); `apply_role_flip(levels, raw, df, up_to_idx, sustain_bars=3, memory_threshold=50.0) -> list[dict]`; `build_levels(df) -> list[dict]`; `prior_rth_close(df) -> float\|None` (the gap-fill magnet feed, see 1.5). |
| **Engine** | `backtest/lib/watchers/level_memory.py::class LevelMemory(df)` — `.levels_at(up_to_idx, lookback_days=5) -> list[Level]`, `.snapshot(up_to_idx, lookback_days=5) -> Snapshot`. `Level` dataclass: `price, role, memory_score, touches, wicks, bars_consolidated, role_flips, first_seen_idx, last_touch_idx, last_flip_idx`. Free function `detect_role_flip(level, df, up_to_idx, sustain_bars=3, memory_threshold=50.0) -> (role, flipped_at, provenance)` — a SECOND, stricter confirmation gate (3 consecutive bars unchanged) layered on top of the fast/causal `role` field, so a single-bar whipsaw never gets reported as a regime change. |
| **G11 live wire** | Confirmed directly in the live `key-levels.json` read on 2026-07-09: a level's `reasoning` field literally reads *"merged live via G11 wire (level_memory_live_merge): nearest-6 to spot, score>=60, within +/-1.5%."* — the shadow feed is now a live consumer, not just telemetry. |
| **Look-ahead safety** | Module docstring's own DESIGN CONTRACT: **STATELESS** (no persisted state — everything derived from the input `df`) and **LOOK-AHEAD-SAFE** (`.levels_at(i)`/`.snapshot(i)` use only bars `<= i`; swing-pivot detection uses a half-window `SWING_HALF=2` so a pivot at `p` is only visible starting at `p+SWING_HALF`, matching the fractal confirmation-lag pattern used everywhere else in this codebase). Guard: `backtest/tests/test_level_memory.py` (not modified by this build). |
| **This build reuses it via** | `backtest/lib/patterns/context.py::levels_from_level_memory()` (adapter) + `backtest/tools/pattern_prescreen.py::build_levels_by_date()` (one `LevelMemory` call per historical trading day, using only bars strictly before that day). |

### 1.2 Swings / BOS / CHoCH (market structure)

| | |
|---|---|
| **Engine** | `crypto/lib/market_structure.py::analyze_structure(bars: Sequence[Bar], *, window=2, swing_finder=None) -> MarketStructureRead`. Fields: `trend, trend_basis ("structure_breaks"\|"labels"\|"insufficient"), labeled_swings: tuple[LabeledSwing,...], events: tuple[StructureEvent,...], last_event, last_swing_high, last_swing_low, confidence (HEURISTIC, not outcome-calibrated), notes`. Supporting pure functions: `label_swings(swings) -> tuple[LabeledSwing,...]` (assigns HH/HL/LH/LL vs the prior swing of the *same kind*), `walk_structure(bars, swings, window) -> (Trend, tuple[StructureEvent,...])` (the authoritative BOS/CHoCH state machine — a swing only becomes a breakable reference `window` bars after its own pivot), `classify_trend(labeled) -> Trend`, `signal_tier(confidence) -> "low"\|"medium"\|"high"`. |
| **Swing pivot source (2 implementations — see 1.3)** | Default: `crypto/lib/trendlines.py::find_swing_points(bars, window=2, inclusive_right=True)` — simple window-comparison fractal. Live engine's own: `backtest/lib/trendlines.py` (scipy `find_peaks`). `analyze_structure`'s `swing_finder=` parameter exists *specifically* so a live caller can inject the second one instead of forking the structure logic. |
| **Live wiring** | `backtest/lib/watchers/market_structure_watcher.py::detect_market_structure_setup(ctx) -> Optional[WatcherSignal]` — WATCH-ONLY (OP-21), gym-validated (`crypto/validators/v46_market_structure.py`, 13/13), **0/3 live confirmations**, explicitly blocked from a live trigger until the live swing primitive is injected via `swing_finder=`. |
| **Look-ahead safety** | Proven by construction and re-derived independently for this build (`backtest/lib/patterns/context.py` module docstring): `walk_structure` only ever compares the bar being walked to the most recently *confirmed* swing (confirmation keyed on `bar_index + window`), so a swing/event at position `i` is identical whether you run `analyze_structure` on `bars[:N]` (any `N > i`) or on `bars[:i+1]` — this is what lets this build **precompute structure ONCE over the full history** instead of re-scanning per bar, without breaking C6. |

### 1.3 Trendlines — two parallel implementations

| | Gym-side | **Live production** |
|---|---|---|
| File | `crypto/lib/trendlines.py` | `backtest/lib/trendlines.py` |
| Pivot method | window-comparison (`find_swing_points`) | `scipy.signal.find_peaks` with prominence + min-distance |
| Output | `SwingPoint`, `Trendline` (`.price_at(t)`) | `Trendline` (`.price_at(ts)`, `.slope_per_hour()`, `.to_dict()`) |
| Constants | — | `TOUCH_TOLERANCE_USD=0.20, MIN_PROMINENCE_USD=0.15, MIN_DISTANCE_BARS=3, MIN_TOUCHES=3, MIN_SLOPE_USD_PER_HOUR=0.05` |
| Used by | `crypto/lib/market_structure.py` default `swing_finder`, gym validators | the premarket trendline-drawing pipeline (scipy version is what a live swing-injection into `analyze_structure` would use) |

This build's `PatternContext` follows `market_structure_watcher.py`'s own precedent and
uses the **default** (`crypto.lib.trendlines`) swing source for all grammar predicates —
same "observe-only, inject the live primitive before any live trigger" posture. See
sec. 3 for what changes at promotion time.

### 1.4 Squeeze / compression

| | |
|---|---|
| **Engine** | `backtest/lib/watchers/bollinger_squeeze_watcher.py::bollinger_session(rth, n=20, k=2.0) -> (mid, up, lo, bw)` — per-session BB(20,2), population stdev (TradingView `ta.stdev` convention). `squeeze[k] = bw[k] <= trailing 20-bar 20th-percentile of bw` (causal, within-session). `detect_bollinger_squeeze_frame(rth) -> list[dict]` is a **byte-for-byte port** of the validated `backtest/autoresearch/family_detectors.py::detect_bollinger_squeeze`. |
| **Validation status** | The **one survivor** of the 2026-06-25 four-family grind on real OPRA fills: 316 signals, 13/13 P4 cells PASS, two-sided positive (calls +$4,531 / puts +$6,037), direction-controlled null SURVIVES (`analysis/recommendations/family-grind-bollinger_squeeze.json`). Currently WATCH-ONLY pending the `WIRE-BOLLINGER` conductor-proposal apply. |
| **Look-ahead safety** | Module docstring, stated explicitly: *"decision at bar i reads only bars <= i (C6)."* |
| **This build reuses it via** | `backtest/lib/patterns/context.py::_bollinger_bandwidth_array()` — same BB(20,2) formula, ported from a pandas-DataFrame contract to this module's `Sequence[Bar]` contract, precomputed once per `PatternContext.build()`. `predicates.py::compression()` reads it. |

### 1.5 Gaps

| | |
|---|---|
| **Engine** | `backtest/lib/watchers/gap_and_go_watcher.py::detect_gap_and_go_core(prior_rth_close, first_open, first_high, first_low, first_close, min_gap=0.0025, max_gap=0.015) -> Optional[GapAndGoResult]` (pure) + `detect_gap_and_go_setup(ctx, prior_rth_close=None) -> Optional[WatcherSignal]`. |
| **Gap-fill feed** | `setup/scripts/level_memory_producer.py::prior_rth_close(df)` also writes `automation/state/prior-rth-close.json` (V2 fix for `gap_and_go`'s prior `SKIP_NO_FEED` failure mode), consumed by `setup_dispatch._get_prior_rth_close`. |
| **Validation status** | Real-fills PASS (`n=84, exp+$41.6/trade, WR 72.6%, chart-stop-only, DSR PASS, WF_PASS`, `analysis/recommendations/gap-and-go-LIVE.json`) — but `gap_and_go_enabled` is **not exec-armed** (a 2026-06-28 re-validation found 0 robust cells under a different config; validated-but-unarmed is a disclosed, deliberate current state, not a contradiction). |
| **Look-ahead safety** | Module docstring: *"audited — `_gap_and_go_causality_audit.py`, 96/96 signals PASS ... nothing after the trigger bar is consulted; the fill is strictly the next bar open."* |
| **This build reuses it via** | `predicates.py::gap_event()` — same `MIN_GAP`/`MAX_GAP` defaults, same `open[t]/close[t-1] - 1` math, ported to a session-boundary check over `Sequence[Bar]`. |

### 1.6 Wick rejection

| | |
|---|---|
| **Research-only, killed** | `backtest/lib/watchers/ribbon_rejection_wick_detector.py::detect(bars, idx, params, direction, ribbon_df=None) -> Optional[dict]` — **UNREGISTERED**, full battery FAIL 2026-07-02 (0/24 survivors on real OPRA fills; expectancy negative despite WR~65% — the C3 "SPY-price edge != option edge" failure signature). The *shape* (structural break + rejection wick + volume) is disclosed as a possible future EXIT/veto signal, not an entry. |
| **Live, named-level-anchored** | `crypto/lib/chart_patterns.py::failed_breakdown_wick(bars, lookback_for_support=10, min_wick_to_body_ratio=2.0, min_close_back_pct=0.0005, min_volume_mult=1.3, support_price=None) -> Optional[PatternHit]` and its mirror `rejection_at_level(...)`. Ships with `PatternHit` (pattern, bar_index, bias, confidence, key_price, notes), a `contra_regime_only()` wrapper (16-mo backtest: contra-trend hits lift +2.5–15.5pp), and `enrich_hit_with_proximity()` (near-named-level tagging). |
| **Look-ahead safety** | Pure function over `Sequence[Bar]` — no external index parameter, so it structurally cannot read beyond what is passed in. |
| **This build reuses it via** | `predicates.py::wick_rejection(side, min_wick_frac, at_level_role=None, max_level_distance)` — the geometry of `failed_breakdown_wick`/`rejection_at_level`, generalized with an *optional* named-level anchor so one primitive covers both the bare-rolling-window and the named-level-anchored cases. |

### 1.7 VWAP relation — four independent implementations

| File | Function |
|---|---|
| `backtest/lib/watchers/vwap_trend_pullback_watcher.py:101` | `_session_rth_vwap(prior_bars, today)` |
| `backtest/lib/watchers/vwap_continuation_watcher.py:279` | `_session_rth_vwap(prior_bars, today)` (near-identical copy) |
| `backtest/lib/watchers/vwap_reclaim_failed_break_watcher.py:262` | `_session_rth_vwap(prior_bars, today)` (near-identical copy) |
| `backtest/lib/vwap_rejection_detector.py:65` | `compute_session_vwap(spy_bars, as_of_idx) -> float` |
| `backtest/lib/level_strength.py:387` | `compute_vwap(bars, ...) -> VWAPSnapshot \| None` (adds ±1σ/±2σ bands) |

All five compute the *same* cumulative typical-price VWAP; the first three are
near-verbatim copies of each other. This is exactly the "computed three times"
symptom the grammar exists to retire. `vwap_continuation_watcher.py`'s own docstring
even says so: *"Mirrors `vwap_trend_pullback_watcher._session_rth_vwap` and
`session_vwap_asof`."* Live wrapper: `backtest/lib/watchers/vwap_watcher.py::detect_vwap_setup(...)`.

**Look-ahead safety:** `compute_session_vwap`'s docstring states it outright: *"Causal:
VWAP at row i uses only rows[0..i] of the session."*

**This build reuses it via** `context.py::_session_vwap_array()` — one cumulative,
per-session-resetting implementation, ported to `Sequence[Bar]`, computed once per
`PatternContext.build()`. `predicates.py::near_vwap()` reads it.

### 1.8 Volume expansion

No dedicated module — computed inline wherever a detector needs it:

- `crypto/lib/chart_patterns.py::momentum_acceleration` — `vol_mult = latest.volume / avg_vol`, `min_volume_mult=2.0` default, 10-bar trailing average.
- `backtest/lib/watchers/bollinger_squeeze_watcher.py` — `VOL_MULT=1.3`, 20-bar trailing mean, `vol_ok = volavg[k] > 0 and vol[i] >= VOL_MULT * volavg[k]`.
- `backtest/lib/watchers/ribbon_rejection_wick_detector.py::_break_bar_vol_ratio` — median (not mean) of today's prior RTH bars.

Three slightly different trailing-window conventions for the same 3-line calculation.
**This build reuses it via** `predicates.py::volume_expansion(lookback, mult)` — one
mean-based implementation, parameterized so a rule can match any of the above defaults.

### Inventory summary

| # | Primitive | Canonical source(s) | Duplication found | Look-ahead note |
|---|---|---|---|---|
| 1 | Memory levels / role-flips | `level_memory.py` + `level_memory_producer.py` | none (single engine) | STATELESS + LOOK-AHEAD-SAFE by design contract |
| 2 | Swings / BOS / CHoCH | `crypto/lib/market_structure.py` | 2 swing sources (by design — `swing_finder=`) | proven causal by construction (walk_structure) |
| 3 | Trendlines | `crypto/lib/trendlines.py` + `backtest/lib/trendlines.py` | 2 full implementations | premarket-computed; not a live look-ahead risk |
| 4 | Squeeze / compression | `bollinger_squeeze_watcher.py` | none (the ONE validated survivor) | explicit C6 statement in module docstring |
| 5 | Gaps | `gap_and_go_watcher.py` | none | audited 96/96 PASS |
| 6 | Wick rejection | `chart_patterns.py` + `ribbon_rejection_wick_detector.py` (killed) | 2 (1 live-shaped, 1 killed) | pure function, no over-read possible |
| 7 | VWAP relation | 5 near-identical implementations | **4x duplication** | causal by construction (cumulative) |
| 8 | Volume expansion | inlined in 3+ files | **3x duplication, 3 conventions** | trivially causal (trailing window) |

**8 primitive categories catalogued; 2 of them (VWAP, volume expansion) show direct,
measurable duplication (4x and 3x respectively) — this is the concrete evidence for
"grammar, not 30 bespoke detectors."**

---

## 2. The grammar

### 2.1 Files

| File | Responsibility |
|---|---|
| `backtest/lib/patterns/context.py` | `PatternContext` — precomputes `structure`, `vwap`, `bandwidth` ONCE per bar sequence; `LevelLike` + role-matching; level adapters. |
| `backtest/lib/patterns/combinators.py` | 5 generic composition operators: `all_of`, `any_of`, `negate`, `within_n_bars_after`, `then_break`. |
| `backtest/lib/patterns/predicates.py` | 15 domain predicates (below). |
| `backtest/lib/patterns/grammar.py` | `PatternRule` dataclass, `GrammarHit`, `evaluate_rule`, `evaluate_rule_over_range`. |
| `backtest/lib/patterns/registry.py` | The 11 seeded Tier-1/2 rules. |

### 2.2 The C6 contract (bars <= t only)

Every predicate reads `ctx.bars[t]`, `ctx.bars[t-k]` (k>=0), or a precomputed array
(`ctx.structure`, `ctx.vwap`, `ctx.bandwidth`) filtered to entries whose own index is
`<= t`. The precomputed arrays are themselves produced by strictly left-to-right /
causal algorithms (walk-once for structure, cumulative/rolling-window for VWAP and
bandwidth), so precomputing once over an entire multi-year array and filtering per-`t`
is **provably equivalent** to truncating to `bars[:t+1]` and recomputing from scratch at
every `t` — just far cheaper (one `O(n)` pass instead of `O(n^2)`). This argument is
written out in full in `context.py`'s module docstring.

`backtest/tests/test_pattern_grammar.py::TestC6NoLookahead` is the enforcement harness:
it (a) proves the harness itself has teeth by showing it catches a deliberately
future-peeking predicate, then (b) mutates every bar strictly after a fixed evaluation
index `t` into an adversarial extreme (price spike to $5000 or crash to $1, 50x volume)
and asserts every one of the 11 registry rules' output **at `t`** is byte-identical
before/after — for two independent mutation directions, at 6 checkpoints, 11 rules =
132 assertions.

### 2.3 The 15 domain predicates

| # | Predicate | Wraps / models | Key params |
|---|---|---|---|
| 1 | `swing_label(kind, labels)` | market_structure HH/HL/LH/LL | `kind, labels, window` |
| 2 | `structure_event(kind, direction)` | market_structure BOS/CHoCH | `kind, direction` |
| 3 | `close_above(level_role, require_cross, max_distance)` | level_memory / key-levels.json | `level_role` (`any\|support\|resistance\|flipped_support\|flipped_resistance`) |
| 4 | `close_below(...)` | mirror of 3 | " |
| 5 | `level_proximity(max_distance, level_role)` | level_memory (state, not event) | " |
| 6 | `compression(percentile_lookback, percentile_threshold)` | bollinger_squeeze_watcher | `percentile_lookback=20, percentile_threshold=20.0` |
| 7 | `volume_expansion(lookback, mult)` | momentum_acceleration / bollinger_squeeze | `lookback=20, mult=1.5` |
| 8 | `wick_rejection(side, min_wick_frac, at_level_role, max_level_distance)` | chart_patterns.py failed_breakdown_wick/rejection_at_level | `min_wick_frac=0.33` |
| 9 | `engulfing(direction)` | standard OHLC engulfing (new; see 2.5) | `direction` |
| 10 | `inside_bar()` | TA-PATTERN-REFERENCE.md sec D preface | — |
| 11 | `monotone_swings(kind, non_decreasing, n)` | drives triangle/wedge family | `n=2` |
| 12 | `flat_side(kind, n_touches, tolerance)` | drives triangle/rectangle/neckline family | `tolerance=0.20` (= level_memory `TOUCH_TOL`) |
| 13 | `pullback_depth(max_pct, lookback)` | TA-PATTERN-REFERENCE.md sec C.1 (flag) | `max_pct=0.38` |
| 14 | `gap_event(min_gap_pct, max_gap_pct, direction)` | gap_and_go_watcher | `0.0025..0.015` (= gap_and_go `MIN_GAP`/`MAX_GAP`) |
| 15 | `near_vwap(max_distance)` | vwap_rejection_detector / vwap watchers | `max_distance=0.15` |

That is 15, not the ~10-14 the brief suggested — `near_vwap` was added deliberately
because VWAP relation is one of the 8 catalogued Step-1 primitive categories and earning
direct grammar support (rather than an awkward workaround) was judged worth the small
overshoot.

Every predicate is a **factory**: calling it with its knobs returns
`Callable[[PatternContext, int], Optional[dict]]` — `None` means "does not hold at bar
t"; a dict (possibly empty) means "holds," and *is* the evidence merged into the
eventual `GrammarHit.notes`. `bool(result)` is literally the boolean value — this is
the "boolean composition over primitive predicates" the brief asked for; the payload
rides along for free instead of needing a second extraction pass.

### 2.4 The 5 combinators

`all_of`, `any_of`, `negate` are the expected AND/OR/NOT. Two are specific to this
grammar's needs:

- **`within_n_bars_after(later, earlier, n)`** — the brief's *"sequence operators: A
  within N bars after B"*. `later` (A) must hold at the bar being evaluated; `earlier`
  (B) must have held at some bar in the trailing `n` bars. Powers
  `flag_pullback_continuation` (impulse, *then* pullback within 8 bars) and
  `island_reversal` (the first gap, *then* the isolation window, *then* — via a
  rule-local search — the opposing gap).
- **`then_break(base, side, require_cross)`** — chains a *structurally-computed* level
  (e.g. `flat_side`'s cluster price, or `monotone_swings`'s most-recent swing price) into
  a break check. `all_of()`'s branches cannot see each other's evidence, so without this
  combinator the triangle/wedge family could not express "break of THIS side's own
  computed level" declaratively. Documented gotcha: `all_of()` merges evidence via
  `dict.update()` in argument order, so when two composed predicates both set
  `trigger_level` (see `wedge_rising_into_resistance` below), the *later* argument wins —
  used deliberately, called out inline where it matters.

### 2.5 The 11 seeded rules

The brief's 10-item list writes `triangle_ascending/descending` with a slash;
TA-PATTERN-REFERENCE.md sec C.3/C.4 documents them as genuinely different patterns
(different bias, different Bulkowski stats, different composition), so this registry
seeds **both** as separate entries — 11 rules total, matching the brief's coverage
exactly.

| Rule | Tier | Direction | Composition | Citation (thresholds are objective, disclosed — see `registry.py::thresholds`) |
|---|---|---|---|---|
| `failed_break_spring` | 1 | bullish | `wick_rejection(side=lower, at_level_role=support)` | TA-PATTERN-REFERENCE §D.4 (pin bar) + `chart_patterns.failed_breakdown_wick`. "Spring" = standard Wyckoff vocabulary; no failure-rate stat invented. |
| `double_top_bottom_at_level` | 2 | bidirectional | rule-local: 2 swings within tolerance + neckline break, anchored near a level (mirrors `chart_patterns.double_bottom_detector`/`double_top_detector`, re-expressed over the shared structure read) | TA-PATTERN-REFERENCE §B.1 (Bulkowski BE-failure 25%/20% — **daily-only, explicitly flagged "Marginal" intraday** — that stat is NOT claimed for this rule). |
| `neckline_base_break` | 1 | bullish | `flat_side(swing_low, n=3) & close_above(level, cross) & volume_expansion(1.5x)` | TA-PATTERN-REFERENCE §B.2 (neckline) + §C.3 (>=3-touch convention) + StockCharts' mandatory volume-on-breakout rule for bottoms. |
| `triangle_ascending` | 1 | bullish | `then_break(flat_side(high,n=2) & monotone_swings(low,rising,n=2), above)` | TA-PATTERN-REFERENCE §C.3 — BE-failure **17% up** (best up-breakout in section C), breaks up 63% of the time. |
| `triangle_descending` | 1 | bearish | mirror | TA-PATTERN-REFERENCE §C.4 — BE-failure 22%/23%. |
| `flag_pullback_continuation` | 1 | bidirectional | `within_n_bars_after(later=pullback_depth(<=38%) & near_vwap, earlier=volume_expansion(2x), n=8)` | TA-PATTERN-REFERENCE §C.1 — flagged **"Strong"** intraday applicability, the doc's primary Section-C candidate. 38% pullback is a common heuristic, **not** a Bulkowski stat (flags carry no rank). |
| `rectangle_range_break` | 1 | bidirectional | rule-local: flat top AND flat bottom simultaneously, break either side | TA-PATTERN-REFERENCE §C.8 (channel/rectangle cross-ref). Bulkowski publishes **no stat** for channels — none claimed. |
| `inside_day_nr7_break` | 2 | bidirectional | rule-local: narrowest-range-of-7 bar, later broken | Toby Crabel's NR7 — standard mechanical vocabulary, **no published failure-rate stat** (same disclosed-unmeasured treatment as TA-PATTERN-REFERENCE §C.8). |
| `wedge_rising_into_resistance` | 2 | bearish | `then_break(monotone_swings(high,rising,n=3) & monotone_swings(low,rising,n=2), below)` | TA-PATTERN-REFERENCE §C.6 — **bearish bias despite rising slope**; BE-failure 19%/**51%** — Bulkowski's **worst-ranked pattern (36/36)** for the down-breakout. This rule fires on exactly that break, so the 51% caveat is carried in the citation, not dropped. |
| `engulfing_at_level` | 1 | bidirectional | `engulfing(direction) & level_proximity(role matching direction)` | Standard OHLC engulfing geometry (not yet a TA-PATTERN-REFERENCE subsection — closest cousin is §D.3 Harami, opposite containment direction) + the `chart_patterns.rejection_at_level` named-level-anchoring convention. |
| `island_reversal` | 2 | bidirectional | rule-local: `gap_event` away from a level, isolated run, opposing `gap_event` back | Standard "island reversal" vocabulary + `gap_and_go_watcher`'s gap math. TA-PATTERN-REFERENCE §D preface: literal intraday gaps are rare outside the session open — disclosed as the reason this rule is expected to be the registry's rarest firer (confirmed: **0 fires in 18 months**, sec 4). |

**Tier split (locked by `test_tier_split_matches_intraday_applicability_design`):**
Tier-1 (7) = the rules with the strongest existing-primitive backing *and* the clearest
"Strong"/"Good"/best-ranked intraday applicability per TA-PATTERN-REFERENCE's own notes.
Tier-2 (4) = weaker documented applicability (`double_top_bottom_at_level` is explicitly
"Marginal" intraday; `wedge_rising_into_resistance` carries Bulkowski's single worst
down-breakout ranking) or higher-complexity/more-speculative geometry
(`inside_day_nr7_break`, `island_reversal`).

**Deliberately excluded: harmonics (Gartley/Bat/Butterfly) and Elliott Wave.** Both
require multi-leg Fibonacci-ratio fitting with several free parameters and no
mechanically falsifiable failure condition (a "wrong" wave count is reinterpreted, not
refuted) — precisely the "unfalsifiable/overfit priors" shape this codebase has killed
before under a different name (see `CLAUDE.md` C22/C24: backward-looking classifiers and
anchor-day overfitting). Neither has a Bulkowski-grade published statistic either.
Nothing in the primitive inventory (sec 1) supports them without inventing new
curve-fitting machinery, which is out of scope for a grammar over *existing* primitives.

### 2.6 Design notes worth keeping

- **Rule-local predicates are allowed and used** (`_double_top_bottom_predicate`,
  `_rectangle_predicate`, `_nr7_break_predicate`, `_engulfing_at_level_predicate`,
  `_island_reversal_predicate` in `registry.py`) for geometry specific enough to one
  rule that forcing it into the shared 15-predicate library would have strained "small
  and orthogonal." The dividing line: a primitive earns a slot in `predicates.py` when
  **>= 2 rules** need it; otherwise it stays local to the one rule that does.
- **Every primitive that identifies a structurally relevant price populates
  `trigger_level` in its evidence** (swing_label, structure_event, close_above/below,
  level_proximity, flat_side, monotone_swings, gap_event, wick_rejection's
  level-agnostic branch) — this is what lets `then_break` chain generically onto *any*
  of them.
- `PatternRule.direction="bidirectional"` rules must have their predicate return a
  resolved `bias` key when they fire; `grammar.py::evaluate_rule` raises loudly
  (`ValueError`) if a bidirectional rule fires without one — an authoring bug, never a
  silent `None`.

---

## 3. The handoff — from TESTABLE to armed

This section names the **exact files** so the kitchen/overnight loops (or a future
session) can pick up a TESTABLE rule without a human re-deriving the pipeline.

```
pattern_prescreen.json (this build)
        │  rule marked TESTABLE (not NOISE-KILL, not TOO-RARE)
        ▼
backtest/autoresearch/discovery_shadow_ledger.py   -- shadow BOTH directions, $0, no orders
        │  generate(start,end) logs forward-move-with-stop for (setup, direction, stop, regime)
        │  fdr_screen(alpha=0.10)  -- Benjamini-Hochberg FDR across every group
        ▼  survivors -> candidate edges
backtest/autoresearch/backtest_design_swarm.py     -- the CANONICAL BATTERY (real OPRA fills)
        │  canonical_battery(hypothesis_disable, side) always runs:
        │    WR-only (the wrong-by-itself framing) / expectancy full / expectancy stop-sweep /
        │    payoff ratio / max-drawdown / OOS walk-forward / VIX-regime-stratified expectancy
        │  + swarm_propose_designs() (free 5-model swarm) + smart_review_design() gate
        │  runs via backtest.lib.orchestrator.run_backtest — the SAME production sim
        ▼  a scorecard in analysis/recommendations/{rule_id}.json
backtest/autoresearch/pipeline_promoter.py         -- OP-22 auto-ship gates
        │  walk_forward.passed AND wf_ratio>=0.70 AND sub_window_stable AND
        │  anchor_no_regression AND concentration_ok (top5<=50%)
        │
        ├─ setup HAS a setup_dispatch.py roster row  -> writes its enable-flag key into
        │                                               automation/state/params.json (WATCH mode
        │                                               only; extra_setup_exec_armed is NEVER
        │                                               written here — that stays a separate,
        │                                               J-independent-but-explicit arming step)
        │
        └─ setup has NO roster row (the case for every rule seeded here today) -> appends a
           structured "WIRE-DETECTOR-<rule>" proposal row to
           automation/state/conductor-proposals.jsonl with the scorecard evidence, so the
           wiring gap is a visible, pickable work item instead of a silently-dead key.
        ▼
A human/agent writes backtest/lib/watchers/<rule>_watcher.py implementing
  detect_<rule>_setup(ctx: BarContext) -> Optional[WatcherSignal]  (backtest/lib/watchers/__init__.py's contract),
registers the import + __all__ entry in backtest/lib/watchers/__init__.py, and adds a
  (setup_name, flag_key, method) tuple to setup/scripts/setup_dispatch.py's
  SetupDispatcher.run() roster.
        ▼
LIVE PAPER EXECUTION requires a SEPARATE, explicit flip:
  automation/state/params.json["extra_setup_exec_armed"]["<rule>"] = True
  gated in setup/scripts/heartbeat_core.py::_extra_exec_armed() / _route_extra_setups()
  (~line 1349-1397). Paper arming needs no J sign-off (2026-07-01 mandate); LIVE MONEY
  arming is OP-0 gate #1 and always needs J.
```

**Why the swing primitive matters again here:** `PatternContext` (this build) uses the
*default* `crypto.lib.trendlines` swing source, same posture as
`market_structure_watcher.py`. Per that file's own note, **any live trigger must inject
the live engine's swing primitive** (`backtest/lib/trendlines`, scipy `find_peaks`) via
`swing_finder=` before wiring — this build's `PatternContext.build()` does not currently
expose that parameter; adding it is a one-line change (`analyze_structure(bars,
window=swing_window, swing_finder=...)` in `context.py`) that the promotion step should
make, not something to pre-guess here.

**Sim accuracy gate (CLAUDE.md OP-16):** before any ratification, verify
`backtest_design_swarm`'s strike picker matches production (OTM/ITM via
`strike_offset`) — the BS-sim-ignored-strike-offset incident invalidated a full weekend
of research once already.

---

## 4. Prescreen results (2026-07-09 run)

Run: `backtest/tools/pattern_prescreen.py` over
`backtest/data/spy_5m_2025-01-01_2026-07-08.csv` (2025-01-02 .. 2026-07-08, ~380 trading
days), 5m/15m/30m, 101.7s wall-clock, $0. Full output:
`analysis/recommendations/pattern-prescreen.json`.

**Timestamp note:** this tool parses timestamps *correctly* (`utc=True` then
`tz_convert("America/New_York")`) rather than the codebase's usual wall-v1 naive-strip
convention — see the tool's module docstring for why (wall-v1 silently clips the true
first RTH hour on ~35% of days, verified directly against this exact file, and there is
no pre-existing validated fire-count to stay byte-compatible with). Any rule that
proceeds past TESTABLE gets **re-measured** under the battery's own (currently wall-v1)
convention before anything is claimed as an edge.

### Verdict table (rule x timeframe)

| Rule | TF | Verdict | %days fired | fires/day | fires/month | top5-day % | Recent-90d verdict |
|---|---|---|---:|---:|---:|---:|---|
| failed_break_spring | 5m | TESTABLE | 56.2 | 4.095 | 86.00 | 6.9 | TESTABLE |
| double_top_bottom_at_level | 5m | TESTABLE | 48.3 | 0.910 | 19.11 | 9.0 | TESTABLE |
| neckline_base_break | 5m | TESTABLE | 7.2 | 0.111 | 2.34 | 33.3 | TOO-RARE (drift) |
| triangle_ascending | 5m | TESTABLE | 29.2 | 0.361 | 7.58 | 8.8 | TESTABLE |
| triangle_descending | 5m | TESTABLE | 21.5 | 0.247 | 5.18 | 11.8 | TESTABLE |
| flag_pullback_continuation | 5m | TESTABLE | 52.0 | 0.973 | 20.44 | 7.1 | TESTABLE |
| rectangle_range_break | 5m | TESTABLE | 48.8 | 0.841 | 17.66 | 8.2 | TESTABLE |
| inside_day_nr7_break | 5m | **NOISE-KILL** | 99.7 | 43.528 | 914.09 | 1.8 | NOISE-KILL |
| wedge_rising_into_resistance | 5m | TESTABLE | 51.7 | 0.663 | 13.93 | 5.6 | TESTABLE |
| engulfing_at_level | 5m | TESTABLE | 76.1 | 2.496 | 52.42 | 4.7 | TESTABLE |
| island_reversal | 5m | **TOO-RARE** | 0.0 | 0.000 | 0.00 | 0.0 | TOO-RARE |
| failed_break_spring | 15m | TESTABLE | 49.9 | 1.623 | 34.09 | 8.0 | TESTABLE |
| double_top_bottom_at_level | 15m | TESTABLE | 16.7 | 0.210 | 4.40 | 13.9 | TESTABLE |
| neckline_base_break | 15m | TOO-RARE | 1.3 | 0.019 | 0.39 | 100.0 | TOO-RARE |
| triangle_ascending | 15m | TOO-RARE | 5.0 | 0.053 | 1.11 | 30.0 | TOO-RARE |
| triangle_descending | 15m | TOO-RARE | 4.5 | 0.045 | 0.95 | 29.4 | TESTABLE (drift) |
| flag_pullback_continuation | 15m | TESTABLE | 38.7 | 0.538 | 11.31 | 8.4 | TESTABLE |
| rectangle_range_break | 15m | TOO-RARE | 5.0 | 0.050 | 1.06 | 26.3 | TOO-RARE |
| inside_day_nr7_break | 15m | **NOISE-KILL** | 99.7 | 14.541 | 305.36 | 2.2 | NOISE-KILL |
| wedge_rising_into_resistance | 15m | TESTABLE | 23.6 | 0.252 | 5.29 | 10.5 | TESTABLE |
| engulfing_at_level | 15m | TESTABLE | 50.4 | 0.828 | 17.38 | 7.4 | TESTABLE |
| island_reversal | 15m | TOO-RARE | 0.0 | 0.000 | 0.00 | 0.0 | TOO-RARE |
| failed_break_spring | 30m | TESTABLE | 40.6 | 0.905 | 19.00 | 10.0 | TESTABLE |
| double_top_bottom_at_level | 30m | TOO-RARE | 7.2 | 0.082 | 1.73 | 29.0 | TOO-RARE |
| neckline_base_break | 30m | TOO-RARE | 0.0 | 0.000 | 0.00 | 0.0 | TOO-RARE |
| triangle_ascending | 30m | TOO-RARE | 1.3 | 0.013 | 0.28 | 100.0 | TOO-RARE |
| triangle_descending | 30m | TOO-RARE | 0.5 | 0.008 | 0.17 | 100.0 | TOO-RARE |
| flag_pullback_continuation | 30m | TESTABLE | 31.3 | 0.414 | 8.69 | 10.3 | TESTABLE |
| rectangle_range_break | 30m | TOO-RARE | 1.3 | 0.013 | 0.28 | 100.0 | TOO-RARE |
| inside_day_nr7_break | 30m | **NOISE-KILL** | 99.2 | 7.374 | 154.85 | 2.3 | NOISE-KILL |
| wedge_rising_into_resistance | 30m | TESTABLE | 10.3 | 0.109 | 2.28 | 17.1 | TOO-RARE (drift) |
| engulfing_at_level | 30m | TESTABLE | 34.2 | 0.419 | 8.80 | 7.6 | TESTABLE |
| island_reversal | 30m | TOO-RARE | 0.0 | 0.000 | 0.00 | 0.0 | TOO-RARE |

**Totals (full history, 33 rule x timeframe cells): 18 TESTABLE, 3 NOISE-KILL
(`inside_day_nr7_break` on all 3 timeframes — consistent, exactly as its "no published
stat, purely mechanical" citation predicted), 12 TOO-RARE.** `island_reversal` fired
**zero times in 18 months on every timeframe** — the registry's most speculative rule by
design (sec 2.5), confirmed rather than contradicted by the data.

### Top 3 rules to send to the battery first

Selected for: TESTABLE on **all three** timeframes (robustness, not a single-timeframe
curiosity), Tier-1 (strongest existing-primitive backing), and a fire-rate comfortably
clear of both the NOISE-KILL (80% days) and TOO-RARE (2/month) boundaries.

1. **`failed_break_spring`** — TESTABLE 5m/15m/30m (56/50/41% days, 86/34/19 fires-month);
   reuses the already-validated named-level wick geometry (`chart_patterns.py`), the
   cleanest primitive-to-rule mapping in the registry.
2. **`flag_pullback_continuation`** — TESTABLE 5m/15m/30m (52/39/31% days); the doc's own
   flagged "Strong" intraday Section-C candidate, and the best showcase of the grammar's
   compositional design (sequence combinator + VWAP relation + pullback-depth all in one
   rule).
3. **`engulfing_at_level`** — TESTABLE 5m/15m/30m (76/50/34% days); simplest rule in the
   registry (2 predicates), but its 5m fire-rate (76.1%) sits closest to the NOISE-KILL
   line of any TESTABLE rule — sending it to the battery first also answers "is this
   genuinely selective or borderline noise" before more effort goes into it.

`triangle_ascending` (best single-timeframe stat in the registry — Bulkowski's 17%
BE-failure, the best up-breakout in TA-PATTERN-REFERENCE section C) and
`neckline_base_break` (TESTABLE full-history but flips to TOO-RARE in the recent 90
days — a live regime-drift flag) are the next candidates once the top 3 clear or fail.

---

## Appendix — file map

```
backtest/lib/patterns/
  __init__.py       public exports
  context.py        PatternContext, LevelLike, level adapters, VWAP/bandwidth precompute
  combinators.py    all_of / any_of / negate / within_n_bars_after / then_break
  predicates.py     15 domain predicates
  grammar.py        PatternRule, GrammarHit, evaluate_rule(_over_range)
  registry.py       11 seeded rules + rule-local predicates + thresholds

backtest/tools/
  pattern_prescreen.py   the C27 pre-screen CLI

backtest/tests/
  test_pattern_grammar.py     C6 bite, determinism, registry schema, predicate units (54 tests)
  test_pattern_prescreen.py   synthetic fire counts, verdict thresholds, resample, CSV picking (15 tests)

analysis/recommendations/
  pattern-prescreen.json   the 2026-07-09 run's full output (sec 4 is its human-readable digest)
```
