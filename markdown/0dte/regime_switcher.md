# REGIME_SWITCHER — Strategy Spec (DRAFT, WATCH-ONLY)

> Status: **DRAFT — WATCH-ONLY per OP 21**. Backtest pending. Not auto-tradable.
> Numeric values are NOT canonical here — they live in [`automation/state/params.json`](../automation/state/params.json) once promoted.
> Hard rules + operating principles inherited from [`CLAUDE.md`](../CLAUDE.md).
> Mirrors the Setup Template in [`markdown/0dte/playbook.md`](markdown/0dte/playbook.md). Sub-strategies inherit from their own specs.

**Setup name:** REGIME_SWITCHER
**Direction:** EITHER (delegated to selected sub-strategy)
**Status:** DRAFT (WATCH-ONLY)
**Date created:** 2026-05-13
**Author:** Gamma (architect agent — pattern mining cycle)
**Sub-strategies orchestrated:** SNIPER_LEVEL_BREAK (spine), v14_ENHANCED (gap-day patch), VWAP_REJECTION_PRIME (chop-trend patch), OPENING_DRIVE_FADE (post-event patch).

---

## 1. Setup name + 1-line summary

**REGIME_SWITCHER** — a lookahead-safe macro-regime classifier that runs ONCE at 09:30:00 ET, consumes only premarket + prior-session data (overnight gap, prior-day range, VIX level, prior-day-close vs MAs), assigns the day to one of four regimes {EVENT_VOL, TREND_DAY, GAP_DAY, CHOP}, and activates EXACTLY ONE of {ODF, SNIPER, v14_ENHANCED, VWAP} for the entire RTH session — eliminating cross-strategy double-trade risk while capturing 7/7 J anchor days via complementary specialization.

---

## 2. Thesis — the mechanism

### The pattern-mining seed (load-bearing observation)

Tonight's grinder produced the highest-information observation in Project Gamma's history: **four strategies, near-zero overlap on J anchor days, union = 7/7.**

| Date | Sniper | v14_enhanced | VWAP | ODF | Sole catcher | J PnL |
|---|---|---|---|---|---|---|
| 4/29 | +$181 | +$294 | $0 | $0 | sniper + v14e | +$342 |
| 5/01 | $0 | -$22 | **+$40** | $0 | **VWAP ONLY** | +$470 |
| 5/04 | +$192 | +$5 | $0 | $0 | sniper | +$730 |
| 5/05 | **+$202** | **-$153** | +$41 | $0 | **regime flip** | -$260 |
| 5/06 | $0 | $0 | $0 | **+$122** | **ODF ONLY** | -$300 |
| 5/07 | +$235 | +$250 | $0 | $0 | sniper + v14e | -$165 |
| 5/12 | $0 | **+$241** | $0 | $0 | **v14e ONLY** | +$400 |

**The naive blender (run all 4 in parallel) catches 7/7 but exposes two failure modes:**
1. **Correlated-loss days (5/05):** sniper +$202, v14e -$153 = a $355 daily swing on the SAME direction (both bear). Running both fires two losing setups on one chart.
2. **Capital concentration:** four parallel positions on a $1K paper account violates per-trade risk caps. Even at $10K with qty=10, two simultaneous positions can exceed the daily loss budget.

### Why a switcher beats a parallel blender (mechanism)

A switcher transforms multi-strategy coverage from a **simultaneous-OR** (any strategy can fire) into a **mutually-exclusive selection** (exactly one strategy is "armed" today). Trade-offs:

| Property | Parallel blender | REGIME_SWITCHER |
|---|---|---|
| Coverage potential | 7/7 anchors | 7/7 anchors (if classifier correct) |
| Cross-strategy chop loss (5/05) | sniper + v14e BOTH fire = net -$153 added | one fires, classifier picks the winner |
| Capital concentration | up to 4 positions | one position max |
| Required research | overlap dedupe rules | a regime classifier |
| Failure mode | overlapping signals double-trade | misclassification = wrong strategy active |
| Position sizing | must scale down or veto | full size on selected strategy |

The switcher trades one risk (correlated losses + capital concentration) for another (classifier error). The classifier error is **measurable and bounded** — once we have a backtest of the regime rules, we know exactly which days were misclassified and can pay to fix them.

### The lookahead-safe regime indicator (the one knob that matters)

The classifier MUST run before 09:30:01 ET. It can use:
- **Overnight gap:** `today_open_at_09:30 − prior_session_close_at_16:00`. Available at 09:30:00 ET via Alpaca/TradingView quote.
- **Prior-day RTH range:** `prior_session_high − prior_session_low`. Available 16:00 ET prior day.
- **VIX level:** spot VIX at 09:30:00 ET. Available at 09:30:00 ET.
- **Prior-day close vs 20-bar daily SMA(close):** trend orientation. Available 16:00 ET prior day.
- **Macro-calendar event:** is FOMC / CPI / NFP within ±1 day? Available from `today-bias.json#macro` set at 08:30 ET premarket.

It **CANNOT** use:
- The opening-range break (that's 09:35-10:00 data — leaks into RTH).
- Today's first 5m candle (09:30-09:35).
- Any indicator computed from a bar that closes AFTER 09:30:00 ET.

### Hard reasoning: what is structurally different about each J anchor day?

Using strictly pre-09:30 data, each anchor day's defining feature:

| Date | Overnight gap | Prior-day range | VIX | Macro context | Defining feature | Captured by |
|---|---|---|---|---|---|---|
| 4/29 | small (≤ $1) | medium (~$5) | normal (~16-18) | clean tape | level-break momentum day | sniper, v14e |
| 5/01 | small | medium-small | low-normal | clean tape | VWAP-pinned chop-then-trend (gap-down leg 2) | **VWAP** |
| 5/04 | small | large (>$5) — wide range from 5/01 | normal | clean tape | sniper-style multi-day-trendline + level confluence | sniper |
| 5/05 | small | medium | rising | clean tape | CHOP day — sniper's strict 2-star + body filter saves it; v14e's looser triggers blow it up | sniper (only because it's stricter) |
| 5/06 | small-medium | medium | elevated | post-mini-event (overshoot/revert) | exhausted opening drive that stalls | **ODF** |
| 5/07 | small | small | rising into FOMC | pre-FOMC | counter-trend chop into event — most strategies should SKIP | sniper + v14e (both took the bear side) |
| 5/12 | small-medium | medium-large | falling | clean tape | early-AM trend-down sustained (v14's 10:00 gate misses it; v14e early-entry catches it) | **v14e** |

**Key learnable signals:**

1. **VIX rising or > 20:** correlates with post-event days where opening drives exhaust (5/06 — ODF's home turf).
2. **Prior-day range expansion (>$5):** preserves trend energy → sniper-style level breaks compound (5/04 — sniper's home turf).
3. **Small overnight gap + low VIX + small prior range:** chop with trend tilts via VWAP rejection (5/01 — VWAP's home turf).
4. **Small gap + medium range + early-AM directional setup:** v14e early-entry window captures the move that v14 misses (5/12).
5. **Pre-FOMC ≤ 1 day:** all strategies should skip (5/07).

### Why the 5/05 problem becomes manageable

5/05 was the highest-information disagreement: sniper +$202, v14e -$153. The pattern-mining report identifies the root cause: **v14e fires on weaker triggers (`min_triggers_bear=1`)** so it enters during chop windows before the real bear leg develops. Sniper's `min_stars=2 + body filter` rejects the false signal.

In REGIME_SWITCHER terms, **5/05 is a CHOP regime day**, NOT a sniper-spine day. The classifier should route it to either:
- **SNIPER** (because sniper's strict filters survive chop) — pragmatic choice, +$202.
- **VWAP_REJECTION_PRIME** (designed for VWAP-pinned chop) — +$41.

Picking sniper for "chop with bias" maximizes 5/05's edge. The rule: **CHOP regime → SNIPER (strict-filter survivor)**, not VWAP. VWAP is reserved for the specific "VWAP-rejection-with-volume" days like 5/01.

### Why this works better than running all 4 in parallel (the core claim)

1. **Eliminates 5/05 v14e false fire** ($153 loss avoided): classifier routes 5/05 to SNIPER, not v14e.
2. **Caps position concentration at 1**: no scenario where 2+ strategies fire on the same day.
3. **Preserves coverage at 7/7** via specialization to a single regime per day.
4. **Capital-efficient on small accounts**: single position fits $1K paper account at qty=3 without per-trade-risk-cap violation.
5. **Composable error model**: misclassification is bounded by 7 historical anchor days; we can directly compute classification accuracy from the backtest.

Expected edge_capture: **≥ $1,000** (target 65% of J's $1,542). Stretch: **≥ $1,300** (85% of J).

---

## 3. Regime classification rules (decision logic, ALL fields lookahead-safe)

### Inputs (frozen at 09:30:00 ET)

| Variable | Source | Computation | Latency |
|---|---|---|---|
| `gap_abs` | Alpaca quote at 09:30:00 ET | `abs(spy_open - spy_prior_close)` | Available 09:30:00 |
| `gap_signed` | same | `spy_open - spy_prior_close` (positive = gap-up) | Available 09:30:00 |
| `prior_range` | TradingView daily bar | `prior_high - prior_low` (RTH only) | Available 16:00 prior day |
| `vix_spot` | TradingView VIX quote | spot price at 09:30:00 ET | Available 09:30:00 |
| `vix_change_1d` | TradingView VIX daily | `vix_today_open - vix_prior_close` | Available 09:30:00 |
| `prior_close_vs_sma20` | TradingView daily | `(prior_close - sma20_daily) / sma20_daily` | Available 16:00 prior day |
| `macro_event_proximity_hr` | `today-bias.json#macro` (08:30 ET) | hours until/since next FOMC/CPI/NFP | Available 08:30 |

### Decision tree (evaluated TOP-DOWN; first match wins)

```
DECISION ORDER (precedence locked):

1. MACRO_VETO regime
   IF macro_event_proximity_hr <= 24 AND event in {FOMC, CPI, NFP}:
      regime = MACRO_VETO
      active_strategy = NONE   (skip the day entirely)

2. EVENT_VOL regime  (post-event reversion or elevated-vol day)
   ELSE IF vix_spot > vix_high_thresh (default 22) OR (vix_change_1d > vix_jump_thresh (default +1.5)):
      regime = EVENT_VOL
      active_strategy = ODF (opening_drive_fade)

3. GAP_DAY regime
   ELSE IF gap_abs > gap_thresh (default $1.00):
      regime = GAP_DAY
      active_strategy = v14_ENHANCED  (early-entry catches the morning trend)

4. TREND_DAY regime
   ELSE IF prior_range > range_thresh (default $5.00) AND vix_spot < vix_low_thresh (default 17):
      regime = TREND_DAY
      active_strategy = SNIPER (level-break momentum)

5. CHOP regime  (default — small gap, normal vol, normal range)
   ELSE IF gap_abs < gap_chop_thresh (default $1.00) AND vix_spot < vix_chop_thresh (default 20):
      sub-decision:
      IF prior_range < range_chop_thresh (default $4.00):
          active_strategy = VWAP_REJECTION_PRIME  (tight-range chop with VWAP magnet)
      ELSE:
          active_strategy = SNIPER  (chop-with-bias; sniper's strict filters survive)

6. FALLBACK regime  (nothing matched — defensive)
   ELSE:
      regime = UNCLASSIFIED
      active_strategy = SNIPER  (spine default — sniper has the most positive quarters)
```

### Anchor-day cross-check (mapping with default knobs)

| Date | gap_abs | prior_range | vix | macro | Regime | Active | J PnL | Expected catch |
|---|---|---|---|---|---|---|---|---|
| 4/29 | ~$0.5 | ~$5 | ~17 | clean | CHOP→SNIPER (range ≥ 4) | SNIPER | +$342 | YES (sniper +$181) |
| 5/01 | ~$0.6 | ~$3 | ~16 | clean | CHOP→VWAP (range < 4) | VWAP | +$470 | YES (vwap +$40, leg 2) |
| 5/04 | ~$0.8 | ~$5.5 | ~16 | clean | TREND_DAY | SNIPER | +$730 | YES (sniper +$192) |
| 5/05 | ~$0.4 | ~$4.5 | ~18-rising | clean | CHOP→SNIPER (range ≥ 4) | SNIPER | -$260 | YES SNIPER (+$202 vs J's -$260 = engine BEATS J by $462) |
| 5/06 | ~$1.0 | ~$4 | ~22+ | post-event | EVENT_VOL | ODF | -$300 | YES (odf +$122) |
| 5/07 | ~$0.3 | ~$3 | rising | pre-FOMC (≤24hr?) | MACRO_VETO if proximity ≤ 24 else CHOP→SNIPER | NONE or SNIPER | -$165 | If MACRO_VETO: skip both J losses. If CHOP→SNIPER: takes the +$235 sniper trade. |
| 5/12 | ~$1.2 | ~$5 | ~16 | clean | GAP_DAY (gap > $1) | v14_ENHANCED | +$400 | YES (v14e +$241) |

**Expected coverage: 7/7 anchor days. Engine-vs-J: SNIPER's +$202 on 5/05 BEATS J's -$260 by $462 — a structural improvement, not just edge capture.**

> **Caveat per OP 2 (speculative — needs evidence):** the gap/range/VIX values in the table above are estimated from contextual memory, not pulled from frozen historical data. Stage 1 backtest MUST recompute these from real bars before any classification claim is final.

### Knob defaults (Stage 1 starting points — all swept)

| Knob | Default | Stage 1 sweep |
|---|---|---|
| `vix_high_thresh` | 22 | 18, 20, 22, 24 |
| `vix_jump_thresh` | +1.5 | +1.0, +1.5, +2.0 |
| `vix_low_thresh` | 17 | 15, 17, 19 |
| `vix_chop_thresh` | 20 | 18, 20, 22 |
| `gap_thresh` | 1.00 | 0.75, 1.00, 1.25 |
| `gap_chop_thresh` | 1.00 | (mirror of `gap_thresh`) |
| `range_thresh` | 5.00 | 4.00, 5.00, 6.00 |
| `range_chop_thresh` | 4.00 | 3.00, 4.00, 5.00 |
| `macro_proximity_hr` | 24 | 18, 24, 36 |

---

## 4. Trigger conditions (inherited from active sub-strategy)

The switcher does NOT generate triggers. It picks a sub-strategy at 09:30:00 ET; that sub-strategy's full trigger conditions apply unchanged for the rest of RTH.

| Active strategy | Trigger source | Time window | First entry after stop |
|---|---|---|---|
| **SNIPER** | `sniper_detector.py` — named-level break/reclaim w/ vol × body + ribbon | 09:35–14:00 ∪ 15:00–15:35 | Blocked |
| **v14_ENHANCED** | v14 ribbon + asymmetric triggers (bear ≥1, bull ≥2) + body + vol gate, early-entry from 09:35 | 09:35–14:00 ∪ 15:00–15:35 | Blocked |
| **VWAP_REJECTION_PRIME** | VWAP rejection footprint + vol_mult + ribbon agreement + body | 09:35–14:00 ∪ 15:00–15:35 | Blocked |
| **ODF (OPENING_DRIVE_FADE)** | Thrust bar + extreme sticky + stall bars + volume decline | 09:35–11:00 (entry); thrust window 09:35–10:30 | Blocked |
| **NONE (MACRO_VETO)** | No entries | — | — |

Hard rules preserved across ALL active strategies:
- No-active-position guard (Rule 6 — only one 0DTE leg open).
- Anticipation entries forbidden (Rule 2).
- 15:50 ET hard flatten (Rule 5 / time-stop doctrine).
- Macro hard veto (`macro_hard_veto_minutes` from `today-bias.json`).
- First-entry-after-stop blocked (params.json doctrine).
- Daily loss kill switch −50% SOD equity (Rule 5).

The switcher's only intervention beyond strategy selection: **once a strategy fires and stops out, the switcher does NOT re-arm a different strategy.** One regime per day, one strategy per regime, one stop-out = day done. This matches Rule 4 (no adding without new confirmed trigger) interpreted at the strategy layer.

---

## 5. Direction + Strike + Size (inherited)

Direction, strike picker, and quality-tier classification are passed through from the active sub-strategy unchanged. No switcher-level overrides.

### Strike summary (cross-strategy reference)

| Strategy | Direction logic | Strike |
|---|---|---|
| SNIPER | level break/reclaim direction + ribbon | ITM-2 (`strike_offset=2`) |
| v14_ENHANCED | bear/bull rejection direction | ITM-2 |
| VWAP_REJECTION_PRIME | rejection-bar direction + ribbon | ITM-2 |
| ODF | OPPOSITE of established opening extreme | ITM-2 |

### Size (v13b tiers, inherited from each sub-strategy)

| Account equity | Base qty | Elite qty | Structure |
|---|---|---|---|
| $0–$2K | 3 | 3 | 2 TP1 + 1 runner |
| $2K–$10K | 5 | 8 | 3 TP1 + 1 cons + 1 agg runner |
| $10K+ | 10 | 15 | 6 TP1 + 2 cons + 2 agg runners |

Quality tier (ELITE vs BASE) computed by each sub-strategy's own rules. Switcher does NOT bump tier.

**Liquidity gates** (bid-ask ≤ 8¢ or ≤ 10% mid; |delta| ∈ [0.30, 0.55]; OI ≥ 500) apply unchanged.

---

## 6. Exits (inherited from active sub-strategy)

Each active strategy uses its OWN exit knobs. The switcher does NOT override exits.

| Knob | SNIPER | v14_ENHANCED | VWAP_PRIME | ODF |
|---|---|---|---|---|
| Premium stop | -10% | -8% | -10% | -8% |
| TP1 trigger | +40% | +30%/+50%/+75% (swept) | +30% | +30% |
| TP1 qty fraction | 0.667 | 0.667 | 0.667 | 0.667 |
| Profit-lock arm | +0% (always-on) | +10% (sweep 0–20%) | +10% | +10% |
| Profit-lock stop offset | +8% | +5% (sweep 0–10%) | +5% | +5% |
| Runner target | +125% | +150%/+200%/+300% (swept) | +150% | +150% |
| Runner stop after TP1 | BE | BE | BE | BE |
| Time stop | 15:50 ET | 15:50 ET | 15:50 ET | 15:50 ET |

Shared doctrine across all strategies:
- Profit-lock NEVER lowers stop below original premium stop.
- Runner ribbon-flip exit (full opposite stack + spread ≥ 30¢) applies if the active strategy specifies it.
- Premium ≥ entry × 3.0 → market sell (`runner_max_premium_pct = 3.0` cap).

---

## 7. Knob grid for Stage 1 backtest

The switcher's Stage 1 sweeps **only the regime-classification boundaries**. Sub-strategy internal knobs are LOCKED to each strategy's current best-known combo (sniper-v1 winner, v14_enhanced default, vwap default, odf default). This isolates the switcher's signal from internal sub-strategy noise.

| # | Knob | Values | Count |
|---|---|---|---|
| 1 | `vix_high_thresh` | 18, 20, 22, 24 | 4 |
| 2 | `vix_jump_thresh` | +1.0, +1.5, +2.0 | 3 |
| 3 | `vix_low_thresh` | 15, 17, 19 | 3 |
| 4 | `gap_thresh` | 0.75, 1.00, 1.25 | 3 |
| 5 | `range_thresh` | 4.0, 5.0, 6.0 | 3 |
| 6 | `range_chop_thresh` | 3.0, 4.0, 5.0 | 3 |
| 7 | `macro_proximity_hr` | 18, 24, 36 | 3 |
| 8 | `chop_default_strategy` | SNIPER, VWAP | 2 |

**Combo count:** 4 × 3 × 3 × 3 × 3 × 3 × 3 × 2 = **3,888 combos**.

**If over budget, drop to ~1,944 by removing `vix_jump_thresh` sweep (lock at +1.5) and `macro_proximity_hr` sweep (lock at 24).** Final reduced count: 4 × 3 × 3 × 3 × 3 × 2 = **1,296 combos**.

**Recommended Stage 1 grid: 1,296 combos** (matches sniper's 1,728 stage 1 budget envelope).

**Locked (NOT swept):**
- Sub-strategy internal knobs (loaded from each strategy's best-known combo as of 2026-05-13).
- `tp1_qty_fraction = 0.667` (universal doctrine, per Section 1 knob-convergence finding in pattern-mining report).
- Time gate 09:35–15:35 excluding 14:00–15:00 (per each sub-strategy).
- `qty = 3` (paper account binding constraint).
- Strategy mutual exclusion (one strategy active per day, full stop).

---

## 8. Anchor floors (per OP 16 — should now satisfy 7/7)

### MUST CATCH (engine_pnl > 0)

| Date | Active strategy | J PnL | Floor (engine_pnl ≥) |
|---|---|---|---|
| 2026-04-29 | SNIPER | +$342 | $150 (≥ 44% of J) |
| 2026-05-01 | VWAP | +$470 | $30 (vwap's known +$40 baseline) |
| 2026-05-04 | SNIPER | +$730 | $180 (≥ 25% of J — sniper's known +$192) |
| 2026-05-05 | SNIPER | -$260 J | **$150** (engine ≥ +$150; sniper's +$202 BEATS J by $462) |
| 2026-05-06 | ODF | -$300 J | $100 (odf's known +$122; engine BEATS J by ≥ $400) |
| 2026-05-07 | NONE (MACRO_VETO) or SNIPER | -$165 J | **$0** (must SKIP via macro_veto OR engine_pnl ≥ -$50) |
| 2026-05-12 | v14_ENHANCED | +$400 | $200 (≥ 50% of J — v14e's known +$241) |

### Aggregate floors (per OP 16, hardened)

- **`winners_capture` ≥ $1,000** (target 65% of J's $1,542). Stretch: $1,300.
- **`losers_added` ≤ $50** total.
- **`edge_capture` ≥ $950**. Stretch: ≥ $1,250.

### Wide-window floors (per OP 14, OP 20)

- `wide_pnl > 0` over 16 months — REQUIRED.
- `positive_quarters ≥ 5 of 6`.
- `top5_pct ≤ 0.40` (concentration — switcher should distribute load, not concentrate).
- `max_drawdown ≤ $1,500`.
- `wide_wr ≥ 0.30` (hard floor per OP 14; higher than the OP 14 minimum 0.10 because switcher must be less random than sniper-alone).
- `validate_sharpe ≥ 1.5` on a held-out 2025-Q4 window.

### Per-regime classification accuracy (NEW — switcher-specific)

The switcher introduces a new failure mode: **misclassification**. Stage 1 must measure it explicitly.

- `regime_label_per_day` recorded for every backtest day.
- For each anchor day, verify the assigned regime matches the expected regime in Section 3's anchor-day cross-check table.
- **Classification accuracy on anchor days: 6/7 minimum**. 5/7 = combo REJECTED.

### Sub-window stability (per OP 19, OP 11)

Each quarter (2025-Q1 through 2026-Q2) must have `quarter_pnl > 0`. Same gate as sniper-v1 ratification standard.

---

## 9. Promotion path (per OP 21)

**ALL gates required for live promotion.** WATCH-FIRST is non-negotiable.

1. **Backfill grader (historical):** 3+ anchor days where the switcher would have armed the correct strategy AND that strategy would have won. Graded via `lib/watchers/regime_switcher_watcher.py` using OPRA fills (not just BS sim).
2. **Live observation (J co-witness):** 3+ live observations where Gamma announces the regime + active strategy at 09:30 ET, posts the rationale to journal, and J confirms or contests.
3. **Full-backfill expectancy:** positive per-trade expectancy over the 16-month window AND positive expectancy WITHIN each of the 4 regime buckets (EVENT_VOL, GAP_DAY, TREND_DAY, CHOP) — if any one regime is net-negative, that regime route is broken.
4. **Per-regime scorecard:** `analysis/recommendations/regime_switcher.json` includes per-regime breakdown of {n_days, wr, expectancy, P&L, max_drawdown}.
5. **Complement not cancel:** the switcher's daily P&L must NOT correlate negatively with sniper-v1's standalone P&L (Pearson |r| < 0.50 over the wide window). If switcher consistently picks the WORSE strategy when sniper alone would have won, |r| will spike negative — that's a sign the classifier is anti-correlated with the spine and must be fixed.
6. **Six-disclosure scorecard (per OP 20):** account-size assumption + sample-bias + walk-forward OOS + real-fills check on top-3 anchor days + failure-mode enumeration + concentration disclosure.
7. **J's explicit ratification.** Gamma does NOT self-promote.

### Default watcher knobs (WATCH-ONLY phase)

The watcher logs the regime decision + would-have-fired sub-strategy outcome WITHOUT placing orders.

| Setting | Value |
|---|---|
| `qty` | 3 (paper account) |
| `premium_stop_pct` | inherited per sub-strategy |
| `tp1_premium_pct` | inherited per sub-strategy |
| `runner_target` | inherited per sub-strategy |
| `tp1_qty_fraction` | 0.667 (universal) |
| `log_path` | `automation/state/watcher-observations.jsonl` |

### Watcher implementation location

`lib/watchers/regime_switcher_watcher.py`. Daily replay via `Gamma_WatcherReplay` task at 17:00 ET. Hooks:
- 09:30:00 ET: classify regime, log {regime, active_strategy, classifier_inputs}.
- 09:35–15:50 ET: delegate observation logging to the active sub-strategy's watcher; tag entries with `parent_strategy: "regime_switcher", child_strategy: "<sniper|v14e|vwap|odf>"`.
- 17:00 ET: replay grader assigns win/loss credit to the switcher's regime call, NOT just the sub-strategy.

### Eligibility for autonomous paper trading

**NO** until ALL 7 gates above clear. Gamma must NOT route any live order through REGIME_SWITCHER until ratified.

---

## 10. Cost / runtime estimate

**Pure Python, `multiprocessing.Pool(processes=4)` per OP 15.** No LLM in loop.

### Per-combo cost

Switcher's per-combo evaluation is **strictly cheaper than any single sub-strategy** because it executes ONE strategy per day, not four. Per-day work:
1. Compute classifier inputs (5 numbers from prior-day data + 09:30 quote) — O(1) per day.
2. Apply decision tree (5 comparisons) — O(1) per day.
3. Run the selected sub-strategy's evaluator over RTH bars — ~6–15 seconds per day (matches existing per-day sniper/v14e cost).

### Optimization (mandatory for Stage 1 feasibility)

**Cache the per-strategy daily P&L matrix first**, then have the switcher select per-day. This is the standard backtester optimization:

1. **Pre-pass (~3.5 hours total):** Run each sub-strategy's evaluator ONCE over all 340 days with its locked best-known knob set. Output a matrix `strategy_daily_pnl[strategy_id][date] = pnl`.
2. **Per-combo (~5 seconds):** Each switcher combo just applies its decision tree to assign `regime[date]`, then looks up `strategy_daily_pnl[regime_to_strategy[regime[date]]][date]` for the aggregate.

**Optimized total:**
- Pre-pass: ~3.5 hours wall-clock (4 strategies × ~50 min each).
- Per-combo: 5 seconds.
- 1,296 combos / 4 workers = 324 combos per worker × 5s = ~27 minutes.
- **Total: ~4.0 hours wall-clock.**

### Validation gate before Stage 2

- Scorecard MUST disclose all 6 OP 20 items.
- Per-regime expectancy table MUST be present.
- Anchor-day classification table MUST show 6/7+ correct.

### Dollar cost

**$0** (pure Python, no Claude calls).

### Disk

- Pre-pass cache: ~25 MB (4 strategies × 340 days × per-trade detail).
- Per-combo results: ~120 MB (1,296 combos × scorecard).
- Stage scorecard + keepers: ~5 MB.

### Output paths

- Pre-pass cache: `backtest/autoresearch/_state/regime_switcher_stage1/strategy_pnl_matrix.json`.
- Per-combo results: `backtest/autoresearch/_state/regime_switcher_stage1/combos/*.json`.
- Stage scorecard: `backtest/autoresearch/_state/regime_switcher_stage1/scorecard.json`.
- Top-5 keepers: `backtest/autoresearch/_state/regime_switcher_stage1/keepers.json`.
- Per-regime breakdown: `backtest/autoresearch/_state/regime_switcher_stage1/regime_breakdown.json`.

---

## Appendix A — Open questions (per OP 2 — speculative)

1. **(speculative — needs evidence)** The anchor-day regime estimates in Section 3 use contextual memory, not frozen historical inputs. The pre-pass MUST recompute `gap_abs`, `prior_range`, `vix_spot`, `vix_change_1d` from real bars. If any anchor day's TRUE regime classification flips, expected coverage may drop from 7/7.
2. **(speculative — needs evidence)** The CHOP→SNIPER vs CHOP→VWAP sub-decision is the highest-leverage knob. Two-knob A/B in `chop_default_strategy` is in the Stage 1 grid; Stage 2 should sweep finer.
3. **5/05 verification.** The hypothesis that sniper +$202 vs v14e -$153 stems from sniper's stricter trigger filters must be verified by replaying 5/05 with both strategy detectors and tracing exactly which bar fired each entry. If sniper's win is luck (single-bar timing variance), the regime claim weakens.
4. **Macro veto vs SNIPER on 5/07.** The 5/07 J trades (both losers, both counter-trend pre-FOMC) ideally route to MACRO_VETO (skip). But sniper +$235 fired on this day from the BEAR side — the same direction J's CALLS fought. So the engine's profitable trade on 5/07 was the OPPOSITE direction from J's losses. This means MACRO_VETO = $0 vs SNIPER = +$235; the better choice is SNIPER. Sweep `macro_proximity_hr` to find the boundary.
5. **Real-fills uncertainty.** BS sim is the Stage 1 evaluator; final ratification REQUIRES `simulator_real.py` cross-check on top-3 anchor days (per OP 20 disclosure 4).
6. **(speculative — needs evidence)** Walk-forward held-out window: train on 2025-01 → 2026-Q1, test on 2026-Q2. If switcher overfits to specific J anchor days in the training set (which include 5/12 from 2026-Q2), held-out performance will degrade. Stage 4 sub-window stability gate handles this.
7. **Daily-decision instability.** A small change in `vix_spot` at 09:30:00 (e.g., 21.9 vs 22.1) flips the regime. Add `vix_dead_zone` (default $0.20) — if VIX is within the dead zone of a threshold, default to the more conservative regime (SNIPER spine). NOT in Stage 1 grid; address in Stage 2 if classifier instability surfaces.

---

## Status footer

**Status:** DRAFT — WATCH-ONLY. Created 2026-05-13.
**Rule version pin:** v14 inherited per sub-strategy. Drift = kill-switch.
**Sub-strategies orchestrated:** SNIPER_LEVEL_BREAK (spine), v14_ENHANCED (gap), VWAP_REJECTION_PRIME (chop-tight), OPENING_DRIVE_FADE (event-vol).
**Next action:** Stage 1 pre-pass (cache per-strategy daily P&L matrix) → Stage 1 grinder (1,296 combos / ~4 hrs / $0) → Stage 2 refine top-5 → Stage 3 regime-robustness → Stage 4 sub-window stability → Stage 5 ratification scorecard → J review.
**Eligibility for autonomous paper trading:** **NO** until ALL 7 promotion gates clear.
