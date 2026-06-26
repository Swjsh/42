# VWAP_REJECTION_PRIME — Strategy Spec

> Status: **DRAFT — WATCH-ONLY per OP 21**. Backtest pending. Not auto-tradable.
> Numeric values are NOT canonical here — they live in [`automation/state/params.json`](../../automation/state/params.json) once promoted.
> Hard rules + operating principles inherited from [`CLAUDE.md`](../../CLAUDE.md).
> Mirrors the Setup Template in [`markdown/0dte/playbook.md`](playbook.md). Detector mirrors [`backtest/lib/sniper_detector.py`](../../backtest/lib/sniper_detector.py). Evaluator pattern from [`backtest/autoresearch/_archive/sniper/sniper_evaluator.py`](../../backtest/autoresearch/_archive/sniper/sniper_evaluator.py).

**Setup name:** VWAP_REJECTION_PRIME
**Direction:** PUTS (resistance side) or CALLS (support side) — fires both sides symmetrically
**Status:** DRAFT (WATCH-ONLY)
**Date created:** 2026-05-13
**Author:** Gamma (architect agent)

---

## 1. Setup name + 1-line summary

**VWAP_REJECTION_PRIME** — SPY pulls back to session VWAP within $0.10, the prior 1-2 bars REJECTED VWAP (closed on the opposite side after testing it), volume on the rejection bar ≥ 1.3× 20-bar avg, and the EMA ribbon agrees with the rejection direction → enter ITM-2 0DTE in the rejection direction.

---

## 2. Thesis

**Mechanism.** Session VWAP is the institutional cost basis. On directional days, price tests VWAP intraday and the side that defended it (buyers below for bull regimes, sellers above for bear regimes) re-engages. A "rejection" is the footprint of that defense: a bar that wicks through VWAP but closes back on the original side. When that rejection prints with elevated volume AND the EMA ribbon is already stacked in the rejection direction, the next leg compounds gamma on a 0DTE strike that's already ITM (delta ~0.55-0.65), capturing both directional move and IV stability.

**Why ITM-2 vs ATM/OTM.** ITM-2 has higher delta, lower theta sensitivity, tighter bid-ask, and survives chop better than OTM. (Speculative: the ITM-2 doctrine has been validated for SNIPER and seed10095 patterns; reasonable assumption it carries to VWAP rejections — backtest will confirm.)

**Which J trades it would have caught (anchor analysis).**

| J trade | VWAP touch happened? | VWAP-Prime would catch? |
|---|---|---|
| **2026-04-29 SPY 710P (+$342)** | Yes — 711.4 was at-or-above VWAP after morning push. Rejection bar at 10:25 ET tested VWAP from above and closed below. | **YES — high-confidence catch.** |
| **2026-05-01 SPY 721P (+$470)** | Yes — leg 2 at 13:36 was a re-test of a falling VWAP after AM gap-down. | **YES — leg 2 only**, not the anticipation leg 1. |
| **2026-05-04 SPY 721P (+$730)** | Yes — premarket level was VWAP-aligned at the test. | **YES** — confluence already encoded. |
| 2026-05-05 SPY 722P (-$260) | Chop day, VWAP whipsaw | Should SKIP — ribbon spread filter and 1.3× vol gate should reject |
| 2026-05-06 SPY 730P (-$300) | No clean VWAP rejection | Should SKIP — no rejection bar pattern |
| 2026-05-07 SPY 734C (-$45) | Pre-FOMC decay day | Should SKIP — macro veto inherited |
| 2026-05-07 SPY 737C (-$120) | Anticipation entry, no VWAP context | Should SKIP — anticipation forbidden |

**Edge-capture target (per OP 16):** ≥ $771 on J winners (50% of $1,542 floor). Stretch: $1,542 (full).

---

## 3. Trigger conditions (ALL required)

A signal fires on a 5-minute SPY bar (closed) when **every** condition below is true:

- **VWAP proximity:** `|bar.close − session_vwap| ≤ proximity_dollars` (default $0.10). Session VWAP = cumulative sum of (typical_price × volume) / cumulative volume from 09:30 ET that day.
- **Rejection footprint on prior 1-2 bars (look-back window = `lookback_bars`, default 2):**
  - **Bear case (rejection from above → enter PUTS):** within the last `lookback_bars` closed bars, at least one bar had `bar.high > vwap_at_bar` AND `bar.close < vwap_at_bar`.
  - **Bull case (rejection from below → enter CALLS):** within the last `lookback_bars` closed bars, at least one bar had `bar.low < vwap_at_bar` AND `bar.close > vwap_at_bar`.
  - The current trigger bar's **close** must be on the side of VWAP that matches the rejection direction.
- **Volume confirmation:** `current_bar.volume ≥ vol_mult × avg(prior 20 bars volume)` (default `vol_mult` = 1.3).
- **Ribbon agreement:** EMA ribbon stack on 5m matches direction. For bears: `Fast EMA < Pivot EMA < Slow EMA` (red stack). For bulls: `Fast EMA > Pivot EMA > Slow EMA` (cyan stack). Compressed ribbons (spread < 30¢) DO NOT qualify — chop = no entry.
- **Body commitment:** trigger bar's body ≥ `body_min_cents` (default $0.08). Wick-only touches without body commit = REJECT.
- **Time gate:** `bar_time ∈ [09:35 ET, 14:00 ET) ∪ [15:00 ET, 15:35 ET)` — note: per J 2026-05-12, NO 10:00 gate for this strat (drops the v14 gate per the SNIPER finding).
- **No-active-position guard:** no current 0DTE leg open.
- **First-entry-after-stop guard:** if a prior VWAP_REJECTION_PRIME today already stopped out, NO RE-ENTRY today.
- **Macro veto inheritance:** if `today-bias.json` macro flag is HARD VETO (event ≤ 120 min counter-trend), SKIP.
- **VIX confirmation:** PUTS → VIX rising or > 20; CALLS → VIX falling or < 17.20.

**Anticipation entries are forbidden.** All conditions must have just printed on the most recently closed bar.

---

## 4. Direction logic

| Condition on most-recent rejection bar | Current bar close | Ribbon stack | Resulting direction |
|---|---|---|---|
| `high > vwap` AND `close < vwap` | `≤ vwap` | bear stack | **PUT** |
| `low < vwap` AND `close > vwap` | `≥ vwap` | bull stack | **CALL** |
| Both conditions present (whipsaw) | — | — | **SKIP** — ambiguous |
| Rejection direction does not match ribbon | — | — | **SKIP** — directional disagreement |

**Tie-break:** if a bull and bear rejection both fired in the lookback window, the **most recent** rejection wins ONLY IF the ribbon agrees. If ribbon disagrees, **SKIP**.

---

## 5. Strike + size

- **Strike rule:** ITM-2 (params.json `strike_offset_itm` = 2):
  - PUTS: `strike = round(spot) + 2`
  - CALLS: `strike = round(spot) − 2`
- **DTE:** 0
- **Order type:** limit at mid; reassess in 30s if not filled.
- **Premium ceiling:** ≤ $3.30. If exceeded, fall back to ITM-1 — log fallback in journal.
- **Size (v13b sizing tiers):**

| Account equity | base_qty | elite_qty | Structure |
|---|---|---|---|
| $0 – $2,000 | **3** | **3** | 2 TP1 + 1 runner |
| $2,000 – $10,000 | **5** | **8** | 3 TP1 + 1 conservative + 1 aggressive runner |
| $10,000+ | **10** | **15** | 6 TP1 + 2 conservative + 2 aggressive runners |

**Quality tier:**
- **ELITE** if VWAP rejection coincides with a named key-level (premarket H/L, prior-day H/L, multi-day trendline within $0.50). VWAP itself does NOT count as a level — confluence requires a SEPARATE level.
- **BASE** otherwise.

---

## 6. Exits

### Premium stop (initial)
- **Default:** `−10%` of entry premium.
- **Rationale:** wider than v14's −8% because VWAP rejections are more sensitive to intraday wobble. −10% gives the wobble room. Will sweep in Stage 1.

### TP1
- **Trigger:** premium ≥ entry × 1.30 (+30%) OR SPY reaches first major intraday support/resistance from `today-bias.json`.
- **Size:** sell `tp1_qty_fraction = 0.667`.

### Profit-lock (per J's 2026-05-12 rule)
- **Arm at:** `favor_premium ≥ entry × 1.10` (+10%).
- **Action when armed:** raise stop to `entry × 1.05` (+5%). Stop never lowers below original premium stop.
- **Effect:** once a trade ticks +10%, it can no longer go negative.

### Runner (after TP1 fires)
- **Stop:** breakeven (entry premium).
- **Target:** `runner_target_pct = 1.5` (premium ≥ entry × 2.5 = +150%).
- **Ribbon-flip-back exit:** runner sells if ribbon transitions to opposite stack with spread ≥ 30¢.
- **Hard cap:** premium ≥ entry × 3.0 → market sell.

### Time stop
- 15:50 ET hard flatten.

### Fallback (small-trade catcher)
- If runner-exit signal fires BEFORE TP1 → exit ALL contracts at signal price.

---

## 7. Knob grid for backtest Stage 1

**Target:** ~864 combos (matches sniper Stage 1 budget).

| # | Knob | Values | Count |
|---|---|---|---|
| 1 | `vol_mult` | 1.1, 1.3, 1.5 | 3 |
| 2 | `proximity_dollars` | 0.05, 0.10, 0.15 | 3 |
| 3 | `lookback_bars` | 1, 2 | 2 |
| 4 | `body_min_cents` | 0.05, 0.10 | 2 |
| 5 | `strike_offset` | +1, +2, +3 | 3 |
| 6 | `premium_stop_pct` | −0.06, −0.10, −0.14 | 3 |
| 7 | `tp1_premium_pct` | 0.20, 0.30, 0.50 | 3 |
| 8 | `runner_target_pct` | 1.0, 1.5, 2.0 | 3 |

**Combo count:** 3 × 3 × 2 × 2 × 3 × 3 × 3 × 3 = **972 combos**.

**Locked (NOT swept in Stage 1):**
- `tp1_qty_fraction = 0.667`
- `profit_lock_threshold_pct = 0.10` and `profit_lock_stop_offset_pct = 0.05`
- `ribbon_min_spread_cents = 30`
- Time gate 09:35–15:35 ET excluding 14:00–15:00
- `qty` = 3 (paper account binding constraint)

---

## 8. Anchor floors (must catch / must skip)

### MUST catch (engine_pnl > 0)
- **2026-04-29 SPY 710P (+$342 J)** — Floor: engine_pnl ≥ $100 (≥ 30% of J).
- **2026-05-01 SPY 721P (+$470 J)** — Floor: engine_pnl ≥ $100 (leg 2 only).
- **2026-05-04 SPY 721P (+$730 J)** — ELITE tier. Floor: engine_pnl ≥ $250 (≥ 35% of J).

### MUST skip OR lose ≤ floor
- **2026-05-05 SPY 722P (−$260 J)** — Floor: engine_pnl ≥ −$50.
- **2026-05-06 SPY 730P (−$300 J)** — Floor: engine_pnl ≥ $0 (must SKIP).
- **2026-05-07 SPY 734C (−$45 J)** — Floor: engine_pnl ≥ $0 (macro veto must SKIP).
- **2026-05-07 SPY 737C (−$120 J)** — Floor: engine_pnl ≥ $0.

### Aggregate floors (per OP 16)
- `winners_capture` ≥ $450 (~30% of J's $1,542). Stretch: $771.
- `losers_added` ≤ $100 total.
- `edge_capture` = winners_capture − losers_added ≥ $350. Stretch: ≥ $700.

### Wide-window floors
- `wide_pnl > 0` over 16 months
- `positive_quarters ≥ 4 of 6`
- `top5_pct ≤ 0.50` (concentration)
- `max_drawdown ≤ $1,500`
- `wide_wr ≥ 0.10` (per OP 14 hard floor)

---

## 9. Promotion path (per OP 21)

**ALL of the below required for live promotion:**

1. **Backfill grader (historical):** 3+ days where the watcher would have fired AND won (graded via `lib/watchers/watcher_grader.py` using OPRA fills, NOT just BS sim).
2. **Live observation (J co-witness):** 3+ live observations.
3. **Full-backfill expectancy:** positive per-trade expectancy over the 16-month window.
4. **Per-confidence-tier expectancy positive:** BASE and ELITE each independently positive.
5. **Per-quality scorecard complement:** does NOT cancel BEARISH_REJECTION_RIDE_THE_RIBBON's wins.
6. **J's explicit ratification.**

**Default watcher knobs during WATCH-ONLY phase:**
- `qty = 3`, `premium_stop_pct = −0.10`, `tp1_premium_pct = +0.30`, `runner_target_pct = 1.5`, `tp1_qty_fraction = 0.667`.

**Watcher implementation location (when built):** `lib/watchers/vwap_watcher.py`. Daily replay via `Gamma_WatcherReplay`.

---

## 10. Cost / runtime estimate for Stage 1

**Pure Python**, `multiprocessing.Pool(processes=4)` per OP 15. No LLM in loop.

**Per-combo cost:** ~35-50 seconds (data pre-loaded, BS pricing per bar dominates).

**Total runtime:**
- 972 combos / 4 workers = 243 combos per worker
- 243 × 45s ≈ **3.0 hours wall-clock.**
- Add data load + scorecard write → **~3.25 hours total.**

**Dollar cost:** $0 (pure Python).

**Disk:** ~80 MB intermediate + ~5 MB final scorecards.

**Output paths:**
- Per-combo results: `backtest/autoresearch/_state/vwap_stage1/combos/*.json`
- Stage scorecard: `backtest/autoresearch/_state/vwap_stage1/scorecard.json`
- Top-5 keepers: `backtest/autoresearch/_state/vwap_stage1/keepers.json`

**Validation gate before Stage 2:** scorecard MUST disclose all 6 OP 20 items.

---

## Appendix — Open questions (per OP 2 — speculative)

1. **(speculative — needs evidence)** VWAP whipsaw on chop days (e.g., 5/05) may still fire false positives. Stage 1 sweep on `vol_mult` and `body_min_cents` should disambiguate.
2. **(speculative — needs evidence)** Anchored-VWAP variants (overnight low / premarket high) may capture a different setup family. NOT in scope for v1.
3. **Real-fills uncertainty.** BS sim is the Stage 1 evaluator; final ratification requires `simulator_real.py` cross-check.
