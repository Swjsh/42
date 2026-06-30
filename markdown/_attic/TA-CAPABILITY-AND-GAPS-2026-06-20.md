# TA Capability Map & Gap Analysis — 2026-06-20

> **Mandate:** "Become the Chart Master." Audit what TA the engine *sees today*, find the gaps, fill them. Docs-first.
> **Scope:** technical analysis only (chart reading / pattern + structure detection). Not sizing, not doctrine, not infra.
> **Method:** read the docs first ([chart-anatomy.md](../0dte/chart-anatomy.md), [ARCHITECTURE.md](../specs/ARCHITECTURE.md), [GAMMA-AUTONOMY-BLUEPRINT](../planning/GAMMA-AUTONOMY-BLUEPRINT-2026-06-18.md)), then mapped every TA surface in code via four parallel reads.

---

## 0. Architecture note (read this first)

- The formal **[markdown/specs/ARCHITECTURE.md](../specs/ARCHITECTURE.md) is content-stale** (internal date 2026-05-09; predates the entire watcher fleet; still references the old `strategy/` paths and "9 tasks"). It was only *moved* in the 06-20 consolidation, not refreshed. **The newest architecture-class doc is [GAMMA-AUTONOMY-BLUEPRINT-2026-06-18.md](../planning/GAMMA-AUTONOMY-BLUEPRINT-2026-06-18.md).**
- The blueprint's charting-relevant findings frame this audit:
  - **"The engine couldn't see 26 of its own 28 watchers"** — the eyes existed but weren't wired. A *wiring/visibility* failure, not a detection failure.
  - **TradingView/CDP:9222 is a single point of failure** — "a frozen-but-200 chart passes the watchdog." The eye **fails green**. This is exactly why every charting skill must run a **connectivity + freshness check first** (constraint #2 of this mandate).
  - **Part 3 #7 — Detector→Insight registry**: the recommended pattern so "a detector that emits nothing does so VISIBLY."

---

## 1. How the engine "sees" — four layers

| Layer | Where | What it sees | Status |
|---|---|---|---|
| **L1 Live read (per tick)** | [`automation/prompts/heartbeat.md`](../../automation/prompts/heartbeat.md) | SPY 5m closed bars (closed-bar filtered, R1 v15.1), Saty Ribbon EMAs (Fast/Pivot/Slow → BULL/BEAR/MIXED stack + spread), SPY 15m HTF (every 5th tick), VIX (cached) | Production — drives entries |
| **L2 Prose filters + Gates** | `heartbeat.md` §Scoring; [`backtest/lib/filters.py`](../../backtest/lib/filters.py) | 10 bear + 11 bull filters + Gates A–I. Triggers: level rejection/reclaim, ribbon flip, multi-day confluence, trendline rejection, **sequence rejection/reclaim** (HL/LH *at a level*), wick rejection, fhh rejection | Production — **this is what gates a live entry** |
| **L3 Watcher fleet (WATCH_ONLY)** | [`backtest/lib/watchers/`](../../backtest/lib/watchers/) (~25 registered) | double bottom ×2, H&S top, RSI divergence (bull), VWAP ×3, ORB 30m/15m, gap&go, ERL/IRL (ICT), named-level break/wick/2nd-test/ceiling-fade/floor-hold, momentum accel, opening-drive fade, premarket-fail fade, shotgun scalper, TBR | Observe-only → `watcher-observations.jsonl`. **Not trigger-eligible** (OP-21: needs 3 J live wins) |
| **L4 Gym pattern library** | [`crypto/lib/chart_patterns.py`](../../crypto/lib/chart_patterns.py) + [`crypto/validators/v22_chart_patterns.py`](../../crypto/validators/v22_chart_patterns.py) | double_bottom, double_top, failed_breakdown_wick, rejection_at_level, momentum_acceleration, inside_bar, head_and_shoulders + contra-regime wrappers + disambiguate | Offline detection + validation (29 offline tests) |

**Key structural fact (the keystone gap):** trend is read from the **EMA ribbon stack** and the **regime classifier** ([`backtest/lib/regime_classifier.py`](../../backtest/lib/regime_classifier.py)) — **never from price swing structure.** Swing pivots are computed *transiently* inside [`trendlines.py:100`](../../backtest/lib/trendlines.py) (scipy `find_peaks`, prominence 0.15, min-dist 3) and [`levels.py:394`](../../backtest/lib/levels.py) (5-bar rolling extrema, for anchored VWAP only). **There is no labeled swing-pivot registry and no market-structure layer.**

---

## 2. Gap analysis — full TA taxonomy (HAVE / PARTIAL / MISSING)

### Market structure
| Concept | Status | Evidence |
|---|---|---|
| Swing high/low (labeled pivots) | ⚠️ PARTIAL | computed transiently `trendlines.py:100`, `levels.py:394`; never surfaced/labeled |
| HH / HL / LH / LL sequence labeling | ❌ MISSING (general) · ⚠️ PARTIAL at a single level | `filters.py` sequence_rejection/reclaim (~:942,:1178); `named_level_second_test_watcher.py` — only *at one named level*, not chart-wide |
| Trend from structure | ❌ MISSING | trend comes from ribbon stack + `regime_classifier.py`, not swings |
| Break of Structure (BOS) | ⚠️ PARTIAL/IMPLICIT | level-break watchers (`level_break_first_strike_watcher.py`, `sniper_detector.py`) fire on close beyond a *level*, not beyond the last *swing* |
| Change of Character (CHoCH) | ⚠️ PARTIAL/IMPLICIT | ribbon-flip ≈ character change; not a structure-based CHoCH |

### Reversal patterns
| Pattern | Status | Evidence |
|---|---|---|
| Double bottom | ✅ HAVE | `chart_patterns.double_bottom_detector`; live `double_bottom_morning_low_vol_watcher.py`, `double_bottom_base_quiet_watcher.py` |
| Double top | ⚠️ PARTIAL | `chart_patterns.double_top_detector` + v22 tests exist, but **no live watcher** (mirror gap) |
| Head & shoulders (top) | ✅ HAVE | `hs_watcher.py`; `chart_patterns.head_and_shoulders_detector` |
| Inverse H&S | ❌ MISSING | no detector |
| Rounding bottom | ❌ MISSING | — |
| Cup & handle | ❌ MISSING | — (double-bottom is the closest analog) |

### Continuation patterns
| Pattern | Status | Evidence |
|---|---|---|
| Inside-bar consolidation | ✅ HAVE | `chart_patterns.inside_bar_consolidation` |
| Bull/bear flag | ❌ MISSING | (retired `stairstep_continuation` was the closest; anti-edge) |
| Pennant | ❌ MISSING | — |
| Triangles (asc/desc/sym) | ❌ MISSING | — |
| Wedges (rising/falling) | ❌ MISSING | — |
| Channels | ❌ MISSING | `trendlines.py` finds single lines, not parallel channel pairs |

### Candlestick
| Pattern | Status | Evidence |
|---|---|---|
| doji, hammer, shooting star, marubozu, bull/bear engulfing | ✅ HAVE (awareness-only) | [chart-anatomy.md](../0dte/chart-anatomy.md) §Candlestick — **deliberately NOT triggers** (v4 backtest: −56% P&L as triggers) |
| Pin bar | ⚠️ PARTIAL | hammer/shooting-star wick logic ≈ pin bar |
| Morning/evening star (3-bar) | ❌ MISSING | not defined |
| Harami | ❌ MISSING | not defined |

### Levels & lines
| Concept | Status | Evidence |
|---|---|---|
| Support/resistance + strength scoring | ✅ HAVE | `levels.py`, `level_strength.py`, [key-levels-protocol.md](../0dte/key-levels-protocol.md) (★ tiers) |
| Trendlines | ✅ HAVE (detect) · ⚠️ PARTIAL (break) | `trendlines.py`; break only via `shotgun_scalper` T3 + filter trendline_rejection — no clean break primitive |
| VWAP / AVWAP | ✅ HAVE | `vwap_*_watcher.py`, `levels.py` aVWAP anchors |
| EMA ribbon / MAs | ✅ HAVE | `ribbon.py` (Fast 13 / Pivot 20 / Slow 48) |
| Prior-day H/L | ✅ HAVE | `levels.py` |
| Opening range | ✅ HAVE | `orb_watcher.py`, `orb15_watcher.py`, `level_strength` ORH/ORL |
| Round numbers | ✅ HAVE | `levels.py` (capped at ★) |

### Volume / momentum
| Concept | Status | Evidence |
|---|---|---|
| Volume spike / confirmation / divergence | ✅ HAVE | `vol_baseline_20bar`, breakdown-bar vol gates, [chart-anatomy.md](../0dte/chart-anatomy.md) §Volume |
| Momentum acceleration | ✅ HAVE | `chart_patterns.momentum_acceleration`, `momentum_acceleration_highvol_watcher.py` |
| RSI divergence | ✅ HAVE (bull only) | `rsi_divergence_watcher.py` (bearish excluded — no edge) |
| MACD divergence | ❌ MISSING | only RSI |

---

## 3. The verdict — what to build (priority order)

1. **Market structure module (the keystone).** A deterministic detector that labels swing highs/lows, emits the HH/HL/LH/LL sequence, derives **trend-from-structure**, and flags **BOS** and **CHoCH**. This is the #1 gap and the direct answer to "are we doing higher highs and lower lows." Pure-Python, gym-validatable, $0, touches no live doctrine.
2. **A connectivity-gated "chart read" skill** (morning + intraday modes) that runs the structure + pattern detectors on real bars and writes a structured read — *after* verifying the chart feed is live and fresh (no writing to thin air).
3. **Cited TA pattern reference** ([TA-PATTERN-REFERENCE.md](TA-PATTERN-REFERENCE.md)) filling the doc gaps: market structure + the missing classical patterns, with reputable citations. Cross-links chart-anatomy.md rather than duplicating it.
4. **Gym validator** proving the new detector fires correctly on fixtures + historical bars (no look-ahead — C6).

**Explicitly NOT in scope this session** (would change live doctrine — DRAFT recommendations only): wiring a market-structure *watcher* into the live WATCH_ONLY fleet; demoting the missing classical patterns into live triggers; double-top live watcher. These are noted for J / the conductor.

---

## 4. Shipped this session

| Artifact | Path | Proof |
|---|---|---|
| **Market-structure detector** (keystone — closes the #1 gap) | [`crypto/lib/market_structure.py`](../../crypto/lib/market_structure.py) | reused validated `find_swing_points`; labels HH/HL/LH/LL, trend-from-structure, BOS, CHoCH |
| **Gym validators** | [`v46_market_structure.py`](../../crypto/validators/v46_market_structure.py) (19 tests) + [`v47_chart_read.py`](../../crypto/validators/v47_chart_read.py) (10 tests) | **offline + live BTC**; full gym **91/91, overall_pass=True**; **93 real SPY days → 0 indecisive, 0 crashes, 9.8 events/day** |
| **Chart-read skill** (morning/intraday/backtest, connectivity-gated) | [`.claude/skills/chart-read/SKILL.md`](../../.claude/skills/chart-read/SKILL.md) + [`backtest/autoresearch/chart_read.py`](../../backtest/autoresearch/chart_read.py) | two-layer no-thin-air guard verified (exit 2 + STATUS flag); epoch-ms crash / UTC-date / STATUS-spam hardened; reader now tested |

### Hardening pass (3-angle self-critique → fixes, 2026-06-20)
Three adversarial reviews (TA-soundness, code, architecture) drove a second pass:
- **TA logic is now sequence-based, not snapshot:** CHoCH flips the working trend (first counter-trend break only); breaks are scanned across all bars; `classify_trend` reads the swing *run* (a single noisy swing no longer flips it). Equal-level double-tops/bottoms now register (tie-break). Confirmation lag surfaced (`bars_since_last_swing`).
- **`chart_read.py` fail-loud hardened:** the epoch-ms crash that bypassed the guard is fixed (ms/µs normalized); UTC→ET session-date fix (no wrong-day filename); `_flag_broken` is idempotent (no STATUS spam); malformed/duplicate rows counted not silent.
- **Architecture:** swing detection is now **injectable** (`swing_finder`) so live-wiring uses the engine's own pivot primitive — no third swing system forked; `signal_tier()` bridges to the `WatcherSignal` contract; `chart-anatomy.md` updated with the structure section + ribbon-vs-structure precedence rule.
- **Empirical:** `window=2` validated on 93 real SPY days (Jan–May 2026) — decisive trend every day, 0 crashes. The 2026-05-04 read now correctly says **downtrend** (matches J's bearish winner); the pre-hardening snapshot wrongly said uptrend.
| **Cited TA reference** | [`TA-PATTERN-REFERENCE.md`](TA-PATTERN-REFERENCE.md) | Bulkowski/StockCharts/ChartSchool sourced; intraday caveat stated |
| **Catalog entry** | [`SKILLS-CATALOG.md`](../infra/SKILLS-CATALOG.md) | `chart-read` row added |

### Elite layer — confluence + measured edge (2026-06-20)
The synthesis + measurement pass that separates a chartist from an elite desk:
- **Confluence engine** [`crypto/lib/confluence.py`](../../crypto/lib/confluence.py) — fuses structure + ribbon (EMA stack) + VWAP side + candlestick + chart pattern + level proximity + MTF into ONE read: bias, conviction (0-100), confirming/conflicting factor stack, invalidation level, scenario line. Validated by [`v50_confluence.py`](../../crypto/validators/v50_confluence.py) (10/10); full gym **97/97**. Wired into `chart-read` (the "wizard read"). On J's bearish winners it reads BEARISH (5/1 = 89/100, 5/4 = 40/100).
- **Causal edge calibration** [`structure_edge_study.py`](../../backtest/autoresearch/structure_edge_study.py) — ran the engine causally over **342 days / 18,161 reads**. Honest verdict ([STRUCTURE-EDGE-STUDY-2026-06-20.md](STRUCTURE-EDGE-STUDY-2026-06-20.md)): **conviction is awareness, NOT alpha** (non-monotonic vs forward edge); the one robust effect is the **bull tilt** (52% vs 48%, n=18k), independently corroborating the J-data campaign. We deliberately did NOT overfit weights to chase it. Conviction is a screen/narration, never a trigger; real-fills sim remains the option authority (C3/L58).

**Still gaps (DRAFT recommendations for J / the conductor — NOT shipped, would touch live doctrine):** double-top live watcher (detector already exists in the gym); inverse H&S; wiring a market-structure WATCH_ONLY watcher into the live fleet; triangles/wedges/flags/pennants if a J-edge backtest justifies them; MACD divergence. Per the reference doc's caveat, **any classical-pattern failure rate must be re-measured on our own SPY intraday sample before it informs a live trigger** — the published Bulkowski stats are daily/weekly.

---

*Built by Gamma in Chart-Master mode, 2026-06-20. Companion: [TA-PATTERN-REFERENCE.md](TA-PATTERN-REFERENCE.md) (cited geometry) and the `chart-read` skill + `market_structure.py` detector.*
