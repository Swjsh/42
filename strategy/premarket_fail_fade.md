# PREMARKET_FAIL_FADE — Strategy Spec (DRAFT, WATCH-ONLY)

> Status: **DRAFT — WATCH-ONLY per OP 21**. Live observation needed before promotion.
> Extracted from J's real-money trade 2026-05-13 09:30 ET (SPY 736P × 5, +$443 / +115% in 18 min).
> This is the INVERSE of SNIPER_LEVEL_BREAK. SNIPER waits for a level *break* with volume. PREMARKET_FAIL_FADE waits for a level *fail* — gap-up open NEAR but BELOW a major resistance, opening bar tests but never clears, immediate reversal cascade to lower-bound support.

**Setup name:** PREMARKET_FAIL_FADE
**Direction:** SHORT-only initially (will mirror to long if J's edge supports)
**Status:** DRAFT (WATCH-ONLY)
**Date created:** 2026-05-13
**Author:** Gamma (live-pickup from J trade)

---

## 1. Motivation — J's 2026-05-13 09:30 ET trade

**Premarket thesis (J):** "739 rejection → 736 target"

**Tape facts:**
- Overnight ES high ~738.90 (cluster with 5/12 ATH zone). Resistance level identified as ★★+ in premarket bias (`today-bias.json#key_levels.resistance` = [738.86, 738.10]).
- SPY 09:30 RTH OPEN gapped UP near but BELOW the 738.86 level.
- The 09:30 5-min bar opened near the level, briefly probed up, but the HIGH NEVER REACHED 738.86 — the level held without even being tested cleanly.
- 09:30 bar closed lower than it opened, putting in a small red body of ~20-30 cents.
- Cascade short followed immediately: bar 2 + bar 3 both broke lower, premium on 736P ran $0.77 → $1.50 → $1.89 in 18 minutes.

**Trade:** BUY 5× SPY 736P @ $0.77 (09:30:33), SELL 3 @ $1.50 (09:36), SELL 2 @ $1.89 (09:48). **+$443 / +115% in 18 min.**

**Why all 7 existing watchers missed it:**
- **SNIPER** requires a level *break* (close beyond level by body_min_cents); here the level was never even *touched*. Failure-to-test is invisible to a break detector.
- **VWAP_REJECTION** needs price to test then reject VWAP; this bar formed at the open with no VWAP history.
- **ORB** needs 30-min range establishment first — fires earliest at 10:00 ET.
- **ODF (opening_drive_fade)** needs HOD/LOD ratchet + stall counter — needs 2+ bars before it can fire.
- **PIN_FADE** is disabled (-$7,900 net per 2026-05-10 verdict).
- **BULLISH_RECLAIM** is the wrong direction.
- **v14_ENHANCED** still gated by ribbon ≥30¢ spread and asymmetric trigger count; opening bar has no meaningful ribbon yet.

**The edge:** premarket-identified resistance + gap-up-but-below + first-bar-fails-to-test = compressed-energy reversal. The level acts as a magnet from above before any new buying can confirm.

---

## 2. Trigger conditions

A signal fires on a RTH 5-min bar when ALL conditions are met:

1. **Bar-in-window:** bar timestamp ∈ [09:30, 09:45] ET inclusive (first 3 RTH bars only — strictly an opening setup).
2. **Proximity to resistance:** bar OPEN is within `proximity_to_level_dollars` (default $0.50) of ANY known resistance level. "Known" means:
   - Levels in `today-bias.json#key_levels.resistance` (premarket-identified)
   - PLUS prior-day RTH high (`compute_levels` in `sniper_detector.py` returns this as a ★★ level)
   - PLUS 5-day RTH high (★★★)
3. **Open is BELOW the level (not above):** `bar.open ≤ level + 0.05`. We are fading a gap-up failure, not chasing a break.
4. **Failed to test:** `bar.high < level + 0.05`. The high stayed below the level (or barely flicked it, ≤5 cents over).
5. **Body commitment:** `bar.close < bar.open - body_min_cents` (default $0.20). The bar closed at least 20 cents below its open — a committed red body, not a wick.
6. **Level strength:** `level.stars ≥ min_stars` (default 2).
7. **NO volume requirement** (vol_mult=1.0 means baseline; signal fires regardless). Fails happen on light volume because the level itself does the work.
8. **Direction:** SHORT only (puts) for the DRAFT. Long mirror deferred to second pass.

**Entry price:** `bar.close` of the failing bar.

**Stop price:** the resistance level + a safety buffer (default level + $0.10), OR premium stop `-10%` — whichever hits first.

**TP1:** nearest support from `today-bias.json#key_levels.support` if ≤ entry - $1.00, else entry - $1.00 default.

**Runner target:** 2× initial premium move OR the support level if more aggressive. Profit-lock arms at +10% favor (stop floor moves to +5% favor — winners never go negative, per J 2026-05-12 rule).

---

## 3. Knobs (entry side)

| Knob | Default | Notes |
|---|---|---|
| `proximity_to_level_dollars` | 0.50 | How close OPEN must be to the level. |
| `body_min_cents` | 0.20 | Minimum red-body size in dollars. |
| `vol_mult` | 1.0 | Baseline — no high-vol gate (fails happen on light vol). |
| `min_stars` | 2 | Level must be ★★+ to qualify. |
| `lookback_bars` | 3 | Number of RTH bars eligible (09:30, 09:35, 09:40). |
| `direction` | "short_only" | Calls deferred until J live edge proven on bull mirror. |
| `level_upper_tolerance` | 0.05 | High may flick this many cents over level and still count as a fail. |
| `stop_buffer_dollars` | 0.10 | Stop sits this many cents above the level. |
| `tp1_distance_dollars` | 1.00 | Default TP1 if no premarket support level within range. |

## 4. Knob grid for Stage 1 backtest (~108 combos — focused)

| Knob | Values | Count |
|---|---|---|
| `proximity_to_level_dollars` | 0.25, 0.50, 0.75, 1.00 | 4 |
| `body_min_cents` | 0.10, 0.20, 0.30 | 3 |
| `min_stars` | 2, 3 | 2 |
| `tp1_premium_pct` | 0.50, 0.75, 1.00 | 3 |
| `runner_target_premium_pct` | 1.5, 2.5 | 2 |

**Total: 4 × 3 × 2 × 3 × 2 = 144 combos** (round down to 108 by dropping rare `tp1_premium_pct=0.50` and `runner=1.5` low-corner combos).

**Locked (NOT swept):**
- `vol_mult` = 1.0 (no volume gate)
- `lookback_bars` = 3
- `direction` = "short_only"
- `level_upper_tolerance` = 0.05
- `premium_stop_pct` = -0.10
- `tp1_qty_fraction` = 0.50 (half off at TP1, half rides as runner)
- `strike_offset` = +2 (ITM-2)
- `profit_lock_threshold_pct` = 0.10, `profit_lock_stop_offset_pct` = 0.05 (per J 5/12 rule)

---

## 5. Anchor-day expected hits

### MUST CATCH (DRAFT — single anchor for now)
- **2026-05-13 SPY 736P (+$443 J, +115%)** — engine_pnl ≥ $200 floor (≥45% of J). This is the DEFINING anchor — the entire reason this setup exists.

### MUST SKIP (the 4 v14 known losers — same as SNIPER spec)
- **2026-05-05 SPY 722P (-$260 J)** — no 09:30-09:45 level-fail footprint. Engine should NOT fire.
- **2026-05-06 SPY 730P (-$300 J)** — opening bars never tested a major level. Engine should NOT fire.
- **2026-05-07 SPY 734C (-$45 J)** — counter-trend pre-FOMC; engine should NOT fire (wrong direction anyway, since SHORT-only).
- **2026-05-07 SPY 737C (-$120 J)** — anticipation; wrong direction.

### Wide-window floors (per OP 19/20 — applies once Stage 5 reached)
- `wide_pnl > 0` on full 16-month backfill (not optional; cherry-pick = veto)
- `positive_quarters ≥ 3 of 6`
- `top5_pct ≤ 0.50`
- `wide_wr ≥ 0.25`
- `max_drawdown ≤ $1,500`

---

## 6. Promotion path (per OP 21)

1. **DRAFT live ship 2026-05-13** — detector + watcher wired into watcher_live. Logs to `watcher-observations.jsonl`.
2. **Historical sweep** — Stage 1 grinder on 16-month dataset (TBD wake fire).
3. **Real-fills replay** — `simulator_real.py` against OPRA cache once anchor reproduces (T30/T31 OPRA expansion in progress).
4. **3+ live wins observed by J** — required.
5. **Stage 5 ratification scorecard** + walk-forward + Monday-Ready Checklist.
6. **J explicit ratification.**

Until step 6, this is OBSERVATION-ONLY. Watcher fires → Discord ping → J reviews → manual trade (or not).

---

## 7. Caveats / known unknowns

- **Single-anchor risk.** One live trade ≠ proven setup. Backtest must validate across regimes.
- **Direction asymmetry.** SHORT-only for now. Bull mirror (call premium on gap-down fail of support) requires its own anchor + sweep.
- **Bias-file dependency.** Detector reads `today-bias.json#key_levels.resistance` if present; falls back to prior-day/5-day high if file missing or stale. If premarket fails to populate the resistance list, the detector still has historical-level fallback.
- **Premarket high handling.** 738.86 was J's "premarket cluster" level. Today's bias file has it listed under resistance. If future days have the premarket high in a different field (e.g., `session_structure.premarket_high`), detector logic will need adjustment.
- **Vol-mult gate disabled.** Unlike SNIPER, no volume confirmation required. RATIONALE: failures happen on absorption/exhaustion, not high-volume rejection. This may produce false positives — backtest will measure.
- **No ribbon agreement gate.** Opening bar has no meaningful ribbon yet — including a ribbon filter would block valid fires.

---

## Status footer

**Status:** DRAFT — WATCH-ONLY. Created 2026-05-13. Live ship same-day.
**Rule version pin:** v14 unchanged (this is a new watcher, not a v14 modification).
**Next action:** observe live fires today + tomorrow → Stage 1 grinder over weekend → Stage 5 scorecard before next CPI-week.
