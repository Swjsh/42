---
title: Higher-Timeframe Context Layer — Research SPEC (the zoom-out)
parent_plan: markdown/planning/PLAN-2-HTF-CONTEXT-LAYER.md
date: 2026-06-24
author: background research agent (Opus)
status: SPEC — research/advisory only. NO live edits (Rule 9 / OP-22 observability).
cost_class: engine-benefit / read-only research
trigger: J 2026-06-24 — "do we even zoom out ever to like the 4h chart and see what the
  market has done over the past week or 2, like where larger supply/demand zones are, or
  where key levels have been respected for the past X days."
---

# HTF Context Layer — Research SPEC

> Read-only deliverable. This SPEC audits what the engine reads today, designs a 4H+daily
> structure read, assesses today (2026-06-24) as the case study, and proposes concrete signal
> additions with exact data sources. It changes **nothing** live. Every proposed signal is a
> **confluence-modifier or regime input, never a hard veto** (C20: a directional gate that
> anti-correlates with the setup is a foot-gun).

---

## 1. AUDIT — what HTF the engine reads today

**Finding: the engine never zooms out above 15-minute. J's instinct is correct — there is no
4H or daily structure read anywhere in the live path.**

### The only HTF read is `htf_15m`, a single 2-bar 15m stack snapshot:

- **Heartbeat prompt** [`automation/prompts/heartbeat.md:220-224`](../../automation/prompts/heartbeat.md):
  > "## SPY 15m HTF (only on tickIndex % 5 == 1) … `chart_set_timeframe("15")` →
  > `data_get_ohlcv(count=2, summary=true)` → `data_get_study_values` → `chart_set_timeframe("5")`
  > to restore. Update `loop-state.htf_15m`." It reads **2 bars** of 15m and the ribbon stack only.
- **Used as a SOFT score-modifier, not context** — `heartbeat.md:453`: "htf_15m_stack … == "BULL"
  → -1 score-modifier (NOT a hard block)". Filter 10/11.
- **Backtest engine mirrors it** — [`backtest/lib/filters.py:85`](../../backtest/lib/filters.py)
  `htf_15m_stack: Optional[str]` is the **only** HTF field on `SetupContext`; consumed at
  `filters.py:902-962` (bearish filter 11) and `filters.py:1140-1338` (bullish filter 10) as a
  ±1 modifier. No 4H/1D/swing/zone field exists.
- **Aggressive tick** [`automation/scripts/heartbeat_aggressive_tick.py:70-72`](../../automation/scripts/heartbeat_aggressive_tick.py):
  `htf = loop_state.get("htf_15m")` — same single field, nothing else.
- **loop-state schema** `heartbeat.md:835`: `"htf_15m": {last_close_time, fast, pivot, slow,
  spread_cents, stack}` — the entire HTF memory of the engine.

### What it does NOT read (grep-confirmed, repo-wide):
- No `data_get_ohlcv` / `chart_set_timeframe` call at `"240"` (4H), `"60"` (1H), or `"1D"`/`"D"`
  anywhere in `automation/prompts/`, `automation/scripts/`, or `backtest/lib/`.
- No multi-day swing-structure (HH/HL/LH/LL) read in the live path. The structure code that
  *exists* ([`crypto/lib/market_structure.py`](../../crypto/lib/market_structure.py)) is gym/
  chart-read-skill only and runs on **5m** bars — its own docstring (lines 29-32) flags it as
  "telemetry only … wiring structure into the LIVE fleet" is an open blocker.
- `respect_count` / `broken_count` on each level are **dead placeholders** (PLAN-2 §2.4, A1) —
  initialized 0, never incremented. So there is no per-level "respected vs broken over X days"
  memory either. (Phase 0 of the KEY-LEVELS plan builds the outcome scorer but it isn't wired.)
- PLAN-2-HTF §gap and the key-levels handoff D2 both already name this: heartbeat "sees ~15 min
  of 5m + 30 min of 15m" — **no multi-hour / multi-day context**.

**Verdict: confirmed. Nothing above 15m, and the 15m it does read is 2 bars used as a ±1 nudge.**

---

## 2. DESIGN — a 4H + daily structure read

Three independent reads, each a self-contained pure function over OHLCV bars, written to a new
`loop-state.htf_context` block (read-only telemetry first). All reuse existing primitives — no
new structure/level engine.

### 2A. Swing structure (HH/HL/LH/LL) over the past 1-2 weeks

- **Reuse as-is:** [`crypto/lib/market_structure.py`](../../crypto/lib/market_structure.py)
  `analyze_structure(bars, window=…, swing_finder=…)`. It already returns labeled swings
  (HH/HL/LH/LL), a walked working-trend (BOS/CHoCH state machine, no look-ahead), and a heuristic
  confidence. It is **timeframe-agnostic** — feed it **daily RTH bars** (≈10 bars = 2 weeks) and
  **4H bars** (≈20-30 bars) instead of 5m.
- **Swing-finder injection (the drift guard the module's own docstring demands, lines 29-32):**
  pass the live engine's pivot primitive via `swing_finder=` so there is ONE structure
  implementation across gym + live. Use `window=1` for daily (10 bars is too few for a 2-per-side
  fractal), `window=2` for 4H.
- **Output:** `{daily_trend: uptrend|downtrend|range, daily_trend_basis, recent_label_sequence:
  ["LH","LL","LH","LL"...], last_swing_high, last_swing_low, last_event: BOS|CHoCH}` — answers
  J's literal question "are we making higher highs and lower lows" at the daily scale.

### 2B. Larger supply/demand zones (bands, not lines)

The key-levels generator draws **lines** (single prices). HTF S/D zones are **bands**
(consolidation-before-impulse). New pure function `htf_zones.py`:

- **Method (deterministic, no look-ahead):** over the trailing N daily/4H bars, find
  *consolidation-before-impulse* — a run of ≥2 bars whose ranges overlap within a tolerance
  (the base), immediately followed by an impulse bar (range > k×ATR) leaving the base. The base's
  `[min(low), max(high)]` is the zone band; demand if the impulse is up, supply if down.
- **Reuse:** the swing pivots from 2A bracket candidate bases; `crypto/lib/` already has ATR-style
  range math in the indicators layer. Tag each zone `{lo, hi, kind: demand|supply, n_touches,
  formed_date, mid}`. Draw as a **rectangle** band (`mcp__tradingview__draw_shape` rectangle —
  already used for J's manual zones per key-levels.json `chart_cleanup_log`), never a horizontal
  line.
- **Output:** `daily_zones[]` sorted by distance from spot, nearest demand below + nearest supply
  above surfaced first.

### 2C. Per-named-level "respect score" (respected vs broken over past X days)

- **Reuse the already-built outcome scorer:**
  [`analysis/level-quality/score_level_outcomes.py`](../../analysis/level-quality/score_level_outcomes.py)
  + `benchmark_level_quality.py` `classify_level()` (RESPECT / BREAK / CHOP, no look-ahead) — this
  is exactly the "respected vs broken" classifier, already validated on 219 days (PLAN-2 §3).
- **The level loader is already shared:** [`backtest/lib/watchers/level_source.py`](../../backtest/lib/watchers/level_source.py)
  `load_named_levels()` / `level_stars()` — feed each named level from `key-levels.json` into the
  scorer over the trailing X RTH sessions.
- **Respect score = respect_touches / total_touches over trailing X days** (X=10 proposed),
  written to a SEPARATE `level-memory.json` (PLAN-2 Task 0.3 already specs this exact file — do
  **not** mutate `key-levels.json`; that is premarket's job / Rule 9). This finally makes
  `respect_count`/`broken_count` real (PLAN-2 A1/A3) — the HTF layer is the consumer that
  justifies wiring Phase 0.
- **Output per level:** `{price, respect_score: 0..1, n_touches, n_respect, n_break, last_touch,
  verdict: RESPECTED|BROKEN|UNTESTED}`.

> **Honest caveat (OP-20 / L58):** the 219-day benchmark already showed levels have ~2.4× touch
> (placement) edge but **~0 reaction edge** once touched (−2.4pp vs random). So a high respect
> score is a *descriptive prior*, useful as a confidence tint — **not** proof the level will
> bounce. Hence: confluence-modifier, never veto.

---

## 3. ASSESS — today (2026-06-24) as the case study

J's case: SPY dipped to **734.11 (~10:20 ET)** and reclaimed/trended to **739.95 (~11:00 ET)**,
a ~$5.85 move. Question: where did that sit in the 4H/daily picture, and would HTF context have
raised conviction?

**Data (real, from `backtest/data/spy_5m_2026-05-19_2026-06-24.csv`; TV CDP + Alpaca SIP/IEX were
all in outage today, so local CSV is the source — see §4 note):**

Daily RTH OHLC, trailing 2 weeks:

| Date | O | H | L | C | note |
|---|---|---|---|---|---|
| 06-15 | 751.9 | 754.1 | 751.8 | **753.5** | local top |
| 06-16 | 754.6 | 755.4 | 750.1 | 750.6 | LH |
| 06-17 | 751.3 | 752.2 | 739.2 | 741.0 | impulse down |
| 06-18 | 747.8 | 748.2 | 743.9 | 747.9 | bounce |
| 06-22 | 747.7 | 750.2 | 743.1 | 744.3 | LH, reversal day |
| 06-23 | 733.8 | 739.6 | 732.3 | 733.7 | **gap down, broke 743 shelf** |
| 06-24 | 735.2 | **739.95** | **730.84** | 732.4 | the case day |

**Daily structure read = DOWNTREND** (closes 753.5→750.6→…→744.3→733.7→732.4 = LH/LL run;
06-23 close broke the 743.35 double-bottom shelf — a daily CHoCH→BOS-down).

**Where the 734.11 dip sat:** squarely inside a **730-735 multi-day DEMAND shelf** —
06-12 L=735.03, 06-23 L=732.30, 06-24 L=730.84 all cluster here, plus prior-day close 734.97 and
PML 734.80. → **HTF context WOULD have raised conviction on the long-side bounce**: the dip tagged
a real multi-day demand band, not no-man's-land.

**Where the 739.95 reclaim peaked:** **exactly at a multi-day SUPPLY shelf** — 06-11 H=740.00,
06-23 H=739.63, and still **below the broken 743.35 support-turned-resistance**. → **HTF context
would have CAPPED the target and flagged the move as a countertrend bounce into supply.** And it
was: price faded all afternoon back to **730.84** and **closed 732.36** (a down day, below prior
close).

**Verdict (today):** HTF context helps — but the value is **two-sided and exactly the
confluence-modifier shape J's plan calls for, not a veto:**
1. It **raises conviction on the entry** (dip into a multi-day demand shelf) — would have nudged a
   bull/long score up.
2. It **lowers conviction on holding for more** (peak into multi-day supply + below broken
   support + daily downtrend) — would have argued *take profit at 739-740, don't chase the runner*.
   The afternoon fade to 730.84 confirms the runner had no HTF room.

A pure 5m engine saw a clean $5.85 reclaim and no reason to be cautious at 740. The HTF layer is
precisely what distinguishes "a reclaim with daily room to run" from "a countertrend bounce into a
2-week supply shelf, in a daily downtrend, below broken support." Same 5m trigger, very different
trade — which is the core thesis of PLAN-2.

---

## 4. PROPOSE — concrete signal additions + data sources

All three land in a new `loop-state.htf_context` block, refreshed **once per ~30 min** (every 10th
tick, same cadence pattern as the existing 15m %5 read) — HTF bars move slowly, so this is near-
zero marginal cost (~1-2 extra `data_get_ohlcv` calls per refresh). **Each is a confluence-modifier
or regime input. None is a hard veto (C20).**

| Signal | Shape | Role | Data source |
|---|---|---|---|
| `htf_4h_stack` | `{trend, label_seq, last_event, last_swing_hi/lo}` from `analyze_structure` on 4H bars | **Regime input** — extends the existing `htf_15m` ±1 nudge to a 4H/daily ladder (15m→4H→1D agreement = stronger modifier) | **TV MCP** `chart_set_timeframe("240") → data_get_ohlcv(count=30, summary=false) → restore("5")` (the existing 15m read pattern, one timeframe up). **Fallback: Alpaca** `get_stock_bars(SPY, "4Hour"?→use "1Hour" ×4 or "1Day")` |
| `daily_trend` | `uptrend\|downtrend\|range` + `label_seq` from `analyze_structure` on ~10 daily RTH bars | **Regime input** — tints score: a long into a daily downtrend gets −1 conviction (NOT blocked), a long with daily uptrend gets +1 | **TV MCP** `chart_set_timeframe("1D") → data_get_ohlcv(count=12)`. **Fallback: Alpaca** `get_stock_bars(SPY, "1Day", days=21)` (the §3 table was built this way) |
| `daily_zones[]` | bands `{lo, hi, kind: demand\|supply, n_touches, mid}` from `htf_zones.py` | **Confluence-modifier** — a 5m trigger *inside / at the edge of* a same-direction HTF zone gets +1; a trigger whose target runs into an opposing zone caps the runner target | Derived from the **same daily+4H bars** as above (no extra fetch). Draw as **rectangle** band via `mcp__tradingview__draw_shape` |
| `level_respect_score` | per named level `{respect_score, n_touches, verdict}` | **Confluence-modifier** — a trigger at a level with high trailing respect score gets a small confidence tint; UNTESTED/BROKEN levels get none | **Local/offline** — `score_level_outcomes.py` over trailing X days of 5m CSV (`backtest/data/`), written to `level-memory.json` (PLAN-2 Task 0.3). **Wiring Phase-0 of the key-levels plan is the prerequisite.** |

### Data-source recommendation
- **Primary: TradingView MCP** `data_get_ohlcv` at `"240"` and `"1D"`, reusing the exact
  set→read→restore discipline already in `heartbeat.md:222` (and the connectivity-gate
  `TV_DATA_LIVE` freshness check in `.claude/skills/tradingview-ops/SKILL.md:35`). It is the live
  engine's existing chart source — least new surface area.
- **Fallback: Alpaca** `get_stock_bars(SPY, "1Day"/"1Hour")`. **Caveat surfaced today:** both TV
  CDP **and** Alpaca SIP+IEX were down/401 on 2026-06-24 (broader usage-cap outage), so the §3
  numbers came from the **local `backtest/data/` 5m CSV aggregated to daily**. That CSV merge is a
  third, always-available source and the natural one for the offline `level_respect_score` backfill
  regardless. A robust HTF read should try TV → Alpaca → local-CSV-aggregate in order.

### Wiring guidance (for the eventual build — NOT this SPEC)
1. Ship `htf_zones.py` + the daily/4H structure read as **pure functions** with gym validators
   first (OP-26), exactly as `market_structure.py` was shipped read-only.
2. Surface `htf_context` into `loop-state` as **telemetry** (WATCH_ONLY) for ≥1-2 weeks; log it on
   every decision row alongside the 5m read. Measure: does HTF agreement separate winners from
   losers on the existing decision ledger (the same A/B method as the level benchmark)?
3. Only after that shows separation, propose the ±1 modifier wiring as a DRAFT scorecard for J
   (OP-11 gates). The modifier must be **soft** (score nudge + runner-target cap), per C20 and the
   −2.4pp reaction-edge caveat.

### Anti-foot-gun checklist
- **No look-ahead (C6):** filter bars to closed only; `analyze_structure` already lags swings by
  `window` bars. Daily "current" bar must be excluded until RTH close.
- **No veto (C20):** every signal is additive ±1 / target-cap, never a block.
- **One structure impl (autonomy blueprint):** inject the live swing primitive via `swing_finder`,
  don't fork.
- **Respect-score is a prior, not a guarantee (L58):** levels have placement edge, ~0 reaction
  edge — tint confidence, don't gate.
- **Cost (OP-3):** ~1-2 extra `data_get_ohlcv` per 30 min ≈ negligible; the respect-score backfill
  is offline pure-Python ($0).

---

## 5. Reuse map (what's already built — do not rewrite)

| Need | Existing asset | Action |
|---|---|---|
| Swing HH/HL/LH/LL + BOS/CHoCH | `crypto/lib/market_structure.py` `analyze_structure` | Feed daily/4H bars + inject swing_finder |
| Named-level loading + stars | `backtest/lib/watchers/level_source.py` | Reuse `load_named_levels` |
| Respected-vs-broken classifier | `analysis/level-quality/{score_level_outcomes,benchmark_level_quality}.py` | Reuse `classify_level` over trailing X days |
| `respect_count`/`level-memory.json` plumbing | PLAN-2 Phase 0 Tasks 0.1-0.3 (specced, partly built) | Wire Phase 0 — it's the prerequisite consumer |
| HTF S/D bands | none — `htf_zones.py` is the one new module | Build as pure function + gym validator |
| TV set→read→restore HTF read | `heartbeat.md:222` (15m), `tradingview-ops` SKILL | Clone pattern at "240"/"1D" |

---

_Evidence: repo grep audit (htf_15m only — heartbeat.md:220-224/453, filters.py:85/902/1140,
heartbeat_aggressive_tick.py:70-72); crypto/lib/market_structure.py + level_source.py +
analysis/level-quality/ read; today's daily structure aggregated from
backtest/data/spy_5m_2026-05-19_2026-06-24.csv (TV+Alpaca both in outage 2026-06-24). Changes
nothing live; makes HTF context buildable as a confluence-modifier under OP-22/OP-11._
