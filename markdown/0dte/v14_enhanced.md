# v14_ENHANCED — Strategy Spec (DRAFT, WATCH-ONLY)

> Status: **DRAFT — WATCH-ONLY per OP 21**. Backtest pending.
> This is v14 BEARISH_REJECTION_RIDE_THE_RIBBON + the 2 SNIPER innovations from 5/12: drop the 10:00 ET entry gate + add the "winners never go negative" profit-lock.
> All other v14 doctrine inherited unchanged.

**Setup name:** v14_ENHANCED (BEARISH_REJECTION_RIDE_THE_RIBBON + early-entry + profit-lock)
**Direction:** PUTS (the v14 mature setup; bull mirror to be specced separately as v14_ENHANCED_BULL)
**Status:** DRAFT (WATCH-ONLY)
**Date created:** 2026-05-13
**Author:** Gamma (overnight grinder T18)

---

## 1. Diff vs v14 (the only changes)

### Change A: Drop the 10:00 ET entry gate
- **v14 production:** `entry_no_trade_before_et: "10:00"` — no entries before 10:00 ET.
- **v14_ENHANCED:** `entry_no_trade_before_et: "09:35"` — entries allowed from 09:35 ET (skip first 5 min for opening volatility).
- **Rationale:** J's 5/12 09:48 ET entry on the 736.13 ★★★ break would have been blocked by the v14 gate. The trade returned +$400. A material edge.
- **Risk:** opening 30 min has higher noise. Mitigated by keeping ALL OTHER v14 filters (ribbon ≥30¢, asymmetric triggers ≥1, vol gate, body shape, level-tied requirement).

### Change B: Add profit-lock (per J 2026-05-12 rule)
- **v14 production:** stop is fixed at -8% premium for the entire trade life until TP1 fires (then runner moves to BE).
- **v14_ENHANCED:** once `favor_premium >= entry × (1 + profit_lock_threshold_pct)` (default +10%), the stop floor raises to `entry × (1 + profit_lock_stop_offset_pct)` (default +5%). Stop never lowers below the original -8%. A winning trade can no longer go negative.
- **Rationale:** J's 5/11 trade #2 (10× 739P from $0.54 → 8 sold @ $0.76 → 2 runners auto-sold @ $0.28 after dropping back to entry) lost $52 on the runner half. With profit-lock armed at +10% and stop at +5%, the runners would have stopped at +$0.027 instead of -$0.26 = $50+ recovered.
- **Risk:** premature stop on V-shaped intraday — the +10% spike then return-to-entry pattern locks scratch instead of the larger eventual win. Backtest will measure this trade-off.

### Everything else inherits from v14 unchanged
- Ribbon ≥30¢ spread requirement (Filter 5/6)
- Asymmetric triggers (bear ≥1, bull ≥2) per `filter_10_min_triggers_*`
- VIX gates per `vix_entry_thresholds`
- Macro veto per `macro_hard_veto_minutes`
- 14:00-15:00 no-trade window (mid-session chop)
- 15:50 ET hard time-stop
- ITM-2 strike (`strike_offset_itm: 2`)
- v13b sizing tiers (3 / 5+8 / 10+15)
- `first_entry_after_stop_blocked: true`
- All liquidity gates

---

## 2. Knob grid for Stage 1 backtest (~432 combos — focused sweep)

This is a TIGHT sweep around the two new knobs + their interactions with v14's existing exit knobs. We are NOT re-exploring the full v14 knob space (that's what overnight_grinder.py already does for v15).

| Knob | Values | Count |
|---|---|---|
| `entry_no_trade_before_et_min` | 9:35, 9:45, 9:50, 9:55, 10:00 | 5 |
| `profit_lock_threshold_pct` | 0.0 (off), 0.05, 0.10, 0.15, 0.20 | 5 |
| `profit_lock_stop_offset_pct` | 0.0 (BE), 0.05, 0.10 | 3 |
| `tp1_premium_pct` | 0.30, 0.50, 0.75 | 3 |
| `runner_target_premium_pct` | 1.5, 2.0, 3.0 | 3 |

**Total: 5 × 5 × 3 × 3 × 3 = 675 combos.** A bit over budget but acceptable; first run will tell us which knobs matter.

**Locked (NOT swept):**
- `premium_stop_pct` = -0.08 (v14 doctrine — already validated)
- `tp1_qty_fraction` = 0.667 (v14 doctrine)
- `strike_offset` = +2 (ITM-2)
- `min_triggers_bear` = 1 (v14 asymmetric — already validated)
- `ribbon_spread_min_cents` = 30 (v14 doctrine)
- All other v14 filters at production values from `params.json`

---

## 3. Anchor floors (per OP 16 — same as v14 but with sniper additions)

### MUST CATCH (engine_pnl > 0 on each)
- **2026-04-29 SPY 710P (+$342 J)** — engine_pnl ≥ $200 floor (≥ 60% of J — should match v14 baseline closely).
- **2026-05-01 SPY 721P (+$470 J)** — engine_pnl ≥ $300 floor.
- **2026-05-04 SPY 721P (+$730 J)** — engine_pnl ≥ $500 floor (CONFLUENCE day, must perform).
- **2026-05-12 SPY 733P (+$400 J)** — engine_pnl ≥ $200 floor. **NEW anchor — v14 didn't catch this because of the 10:00 gate; v14_ENHANCED MUST catch it.** This is the entire reason this strategy exists.

### MUST SKIP OR LOSE ≤ floor
- **2026-05-05 SPY 722P (-$260 J)** — engine_pnl ≥ $0 (must SKIP, no real setup).
- **2026-05-06 SPY 730P (-$300 J)** — engine_pnl ≥ $0 (must SKIP).
- **2026-05-07 SPY 734C (-$45 J)** — engine_pnl ≥ $0 (counter-trend pre-FOMC — macro veto must SKIP).
- **2026-05-07 SPY 737C (-$120 J)** — engine_pnl ≥ $0 (anticipation, no rejection footprint).

### Aggregate floors
- `winners_capture` ≥ $1,200 (sum of 4 winners). Stretch: full $1,942 (J's $1,542 + 5/12's $400).
- `losers_added` ≤ $50.
- `edge_capture` = `winners_capture - losers_added` ≥ $1,150.
- **The KEY question this backtest answers:** does v14_ENHANCED beat v14 on edge_capture WITHOUT regressing the wide-window aggregate?

### Wide-window floors (per OP 19/20)
- `wide_pnl > v14_baseline_wide_pnl + $500` (must improve, not just match)
- `positive_quarters ≥ 4 of 6`
- `top5_pct ≤ 0.50`
- `wide_wr ≥ 0.30`
- `max_drawdown ≤ $1,800`

---

## 4. Implementation tasks (for downstream wake fires)

### T19 (HIGH) — Wire the new knobs into existing v14 infrastructure
1. **Add to `backtest/lib/simulator.py`** — profit-lock logic in the bracket-fill loop (mirror `sniper_evaluator._simulate_trade()` profit-lock block):
   ```python
   profit_lock_arm_premium = entry_premium * (1.0 + combo.profit_lock_threshold_pct)
   profit_lock_stop_premium = entry_premium * (1.0 + combo.profit_lock_stop_offset_pct)
   profit_lock_armed = False
   # in per-bar loop:
   if not profit_lock_armed and favor_premium >= profit_lock_arm_premium:
       profit_lock_armed = True
       if profit_lock_stop_premium > stop_premium:
           stop_premium = profit_lock_stop_premium
   ```
2. **Add to `backtest/autoresearch/runner.py`** — direct_passthrough list:
   ```python
   "profit_lock_threshold_pct",
   "profit_lock_stop_offset_pct",
   ```
3. **Verify `entry_no_trade_before` kwarg already accepts `dt.time(9, 35)`** — it does, per the existing `runner.py` config.parse_time call. No code change needed.

### T20 (HIGH) — Stage 1 grinder
1. Create `backtest/autoresearch/v14_enhanced_grinder.py` mirroring `overnight_grinder.py` but with knob grid above + 5/12 anchor.
2. Output to `backtest/autoresearch/_state/v14_enhanced_stage1/`.
3. Run for 1-2 hours. ~675 combos ÷ 4 workers × 30s/combo = ~85 min.

---

## 5. Cost / runtime estimate

- **Stage 1:** ~85 min, $0 (pure Python).
- **Stage 2-5:** modeled on sniper pipeline patterns; total ~3-4 hours for full pipeline; $0.
- **Final scorecard:** $0.50 (LLM scorecard generation).
- **Promotion path:** same as OP 21 — watch-only until 3+ live wins + J ratification.

---

## Status footer

**Status:** DRAFT — WATCH-ONLY. Created 2026-05-13.
**Rule version pin:** v14 + 2 enhancements. Drift = kill-switch.
**Next action:** T19 (wire knobs into simulator.py + runner.py) → T20 (run Stage 1 grinder) → review keepers.
