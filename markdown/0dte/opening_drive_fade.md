# Setup name: OPENING_DRIVE_FADE (PUTS on HOD-stall / CALLS on LOD-stall)

> Fade exhausted opening drives: when SPY's 09:35-10:30 ET drive establishes a HOD/LOD then stalls within $0.20 of that extreme on declining volume for 2+ bars, enter ITM-2 0DTE in the OPPOSITE direction.

**Status:** **DRAFT — WATCH-ONLY per OP 21.** Zero live trades. Promotion requires 3 historical wins via grader + 3 J-confirmed live observations + positive 16-month expectancy + per-confidence-tier expectancy positive + J ratification.

**Rule version:** v14 — exit values pulled from [`automation/state/params.json`](../../automation/state/params.json). No drift permitted.

**Last updated:** 2026-05-13

---

## 1. Thesis — the mechanism

The opening drive (09:35-10:30 ET) is the highest-conviction directional move of the day; it carries overnight gamma imbalance, opening-auction-driven flow, and the morning macro reaction. By construction, the FIRST extreme of the day is set during this window on roughly 70% of trading sessions.

**Exhaustion signature:** when price prints an HOD (or LOD), then 2+ subsequent 5m bars trade within $0.20 of that extreme **with declining volume vs the thrust bar**, the marginal buyer (or seller) has been spent. The stall is the tape telling us the move is over — every additional bar without follow-through prints absorption from the opposing side. The mechanism is the same one that makes "double-top" and "exhaustion gap" patterns work, but anchored to a specific time window where institutional flow is most concentrated.

**Why post-FOMC mornings especially:** FOMC days end with violent unwind moves. The morning AFTER FOMC, dealer hedges re-bracket, gamma pins reset, and the opening drive frequently overshoots the new equilibrium before reverting. The 09:35-10:30 window catches this overshoot; the stall catches the reversion.

**J historical trades it might have caught:**
- **2026-05-11 ATH 740.43 fade** — SPY drove to ATH 740.43 around 11:15-11:30, then printed distribution bars before reversing into the 12:40 trendline-break-volume PUT signal. An OPENING_DRIVE_FADE that triggered on the HOD stall could have entered puts $1.00+ before the trendline-break-volume signal fired, capturing the early leg. Counterfactual: ITM-2 puts on 740 strike at ~$0.85, target +30% TP1 inside 30 minutes.
- **2026-05-04 721P winner** — J's 5/4 trade was a multi-day-trendline + ribbon-flip CONFLUENCE entry. The morning HOD that preceded it stalled before the ribbon flipped. OPENING_DRIVE_FADE could have caught a complementary earlier entry on the stall, NOT canceling J's later entry (per OP 21 complement-not-cancel requirement).
- **2026-04-29 710P winner** — Similar pattern: morning HOD established before the 711.4 rejection that J entered on. The HOD stall would have signaled before J's chart-level rejection trigger.

**What it is NOT:** This is not a pure mean-reversion play. The trigger requires a STRUCTURAL stall (extreme + 2+ proximity bars + declining volume), not a single reversal candle. It is also not a trend-continuation play — by construction it fades the morning move.

---

## 2. Trigger conditions (ALL required, precise)

**Time window:** thrust bar timestamp must be in `[09:35 ET, 10:30 ET]`. Stall confirmation bars may extend up to 11:00 ET. Entry bar must be ≤ 11:00 ET.

**Trigger sequence (every condition must be true on the entry bar):**

1. **Thrust bar identified.** Within `[09:35, 10:30]`, find the bar whose `high` (for HOD) or `low` (for LOD) is the session extreme so far AND whose body magnitude `abs(close - open) ≥ thrust_bar_min_dollars` (default $0.40). Volume on this bar = `vol_thrust`.
2. **Extreme established.** No subsequent bar through entry has wicked beyond the thrust bar's extreme by more than $0.05 (mechanical extreme-stickiness check).
3. **Stall bars present.** At least `stall_bars_required` (default 2) closed bars after the thrust bar must satisfy:
   - `abs(bar.high - HOD) ≤ stall_proximity_dollars` (for HOD case; mirror for LOD), AND
   - `bar.volume < vol_thrust × vol_decline_ratio` (default 0.70 — i.e., volume must be ≤ 70% of thrust bar).
4. **Entry bar = first bar AFTER stall sequence** that closes back inside the proximity envelope (close within `stall_proximity_dollars` of the extreme but on the fade side). Entry timestamp recorded; entry spot = entry bar close.
5. **Direction:** HOD stall → SHORT (puts). LOD stall → LONG (calls).
6. **No active position.** OPENING_DRIVE_FADE is one-and-done per direction per day; if a fade trade has already entered today on the same side, no second entry.
7. **Daily loss budget remaining > planned $-risk** (per Rule 5).
8. **No counter-trend macro veto** per `macro_hard_veto_minutes`.

**Anticipation entries are forbidden** (Rule 2). The stall sequence must be FULLY PRINTED before the entry bar.

---

## 3. Direction logic

| Extreme made in 09:35-10:30 window | Direction | Strike picker (ITM-2) |
|---|---|---|
| HOD (high of day, with stall) | **PUTS** | strike = `round(spot) + 2` |
| LOD (low of day, with stall) | **CALLS** | strike = `round(spot) - 2` |

If BOTH HOD and LOD stalls fire on the same morning (rare — would require V-shaped morning with two stalls), the FIRST to fire wins. The second is locked out by the one-direction-per-day rule.

---

## 4. Strike + size

**Strike:** ITM-2. Default `strike_offset = 2`. Maps to `_strike_for(direction, spot, offset=2)` per `sniper_evaluator.py` convention.

**Size — per `params.json#position_sizing_tiers` (v13b):**

| Account equity | Base qty | Elite qty | Structure |
|---|---|---|---|
| $0 – $2K | **3** | 3 (no upsize — capital constraint) | 2 TP1 + 1 runner |
| $2K – $10K | **5** | 8 | 3 TP1 + 1 conservative + 1 aggressive runner |
| $10K+ | **10** | 15 | 6 TP1 + 2 conservative + 2 aggressive runners |

**Quality classification:**
- **BASE:** trigger fires with `vol_decline_ratio ≤ 0.70` and `stall_bars_required = 2`.
- **ELITE:** ALL of: `vol_decline_ratio ≤ 0.50` (strong absorption) AND `stall_bars_required ≥ 3` (extended distribution) AND extreme aligns with a pre-identified `today-bias.json` level within $0.30 (level confluence).

ELITE bumps to elite_qty for the tier.

**Liquidity gate** per `params.json#_liquidity_gate_section` applies (bid-ask spread ≤ 8c or ≤ 10% of mid; |delta| in [0.30, 0.55]; OI ≥ 500). ITM-2 0DTE on SPY clears these comfortably during RTH.

---

## 5. Exits — locked to params.json

| Exit knob | Value | Source |
|---|---|---|
| Premium stop | **−8%** (entry × 0.92) | `params.json#premium_stop_pct` |
| TP1 trigger | **+30%** premium OR first chart level past entry | `params.json#tp1_premium_pct` |
| TP1 qty fraction | **0.667** (sell 2 of 3) | `params.json#tp1_qty_fraction` |
| Runner target | **+150% premium** (entry × 2.5) | spec default; honors `runner_max_premium_pct = 3.0` cap |
| Runner stop after TP1 | **breakeven** | `params.json#runner_be_stop_after_tp1` |
| Time stop | **15:50 ET** hard | `params.json#time_stop_et` |

**Profit-lock per J 2026-05-12 rule** (mirrors `SniperCombo.profit_lock_*`):
- Once favor_premium reaches `entry × 1.10` (+10%), arm profit-lock.
- Stop floor raises to `entry × 1.05` (+5%) — guarantees a winning trade never goes negative.
- Profit-lock NEVER lowers the stop below the original −8%.

**Fallback (small-trade catcher):** if a chart-level exit signal fires BEFORE TP1 hits, exit ALL contracts at the signal — same doctrine as BEARISH_REJECTION.

---

## 6. Knob grid for Stage 1 backtest (~864 combos)

| Knob | Values | Count |
|---|---|---|
| `thrust_bar_min_dollars` | 0.30, 0.40, 0.50 | 3 |
| `stall_bars_required` | 2, 3 | 2 |
| `stall_proximity_dollars` | 0.15, 0.20, 0.25 | 3 |
| `vol_decline_ratio` | 0.50, 0.60, 0.70, 0.80, 0.85 | 5 |
| `time_window_end_et` | "10:15", "10:30", "10:45" | 3 |
| `runner_target_pct` | 1.0, 1.5, 2.0 | 3 |

**Locked defaults (not in grid):** `time_window_start_et = "09:35"`, `strike_offset = 2`, `premium_stop_pct = -0.08`.

**Total: 3 × 2 × 3 × 5 × 3 × 3 = 810 combos** (slightly under 864 budget; leaves Stage 2 room to widen one knob).

---

## 7. Anchor floors (per OP 16 — J-edge primary)

**Stage 1 hard floors (combo REJECTED if any fail):**

1. **MUST CATCH 5/11 ATH-fade** if SNIPER missed it. Verify by simulating combo on 2026-05-11 RTH bars; combo passes if it generates a SHORT entry between 11:15-12:00 ET with strike 740 ITM-2 and `dollar_pnl ≥ 0`. Required: at least one fade trade fires on this date with positive P&L.
2. **MUST SKIP choppy days** where there's no clear drive. Define "no drive" days as those where the 09:35-10:30 high-low range is ≤ $1.00 OR no 5m bar in that window has body ≥ $0.30. Combo passes if it generates ZERO trades on these days.
3. **MUST NOT lose money on J's known losing days:** 5/05, 5/06, 5/07. `losers_added` floor: ≤ $50.
4. **MUST capture some J-edge:** `winners_capture ≥ $150` across 4/29 + 5/01 + 5/04.
5. **Edge capture floor:** `edge_capture = winners_capture - losers_added ≥ $100`.

**Stage 2-5 progressively-stricter gates** (per OP 19): refine, regime-robustness, sub-window stability, ratification.

---

## 8. Promotion path per OP 21

OPENING_DRIVE_FADE starts **WATCH-ONLY**; logs to `automation/state/watcher-observations.jsonl` via a new `opening_drive_fade_watcher` in `lib/watchers/`.

**Promotion requirements (ALL must hold):**
1. **3+ historical observations** that would have won, graded via `watcher_grader.py`.
2. **3+ live observations** confirmed by J in real time.
3. **Positive expectancy over the 16-month full backfill** — per-trade EV > $0 net of slippage.
4. **Per-confidence-tier expectancy positive** — both BASE and ELITE quality buckets must have positive expectancy independently. ELITE must show ≥ 1.5× the BASE expectancy.
5. **Per-quality scorecard shows complement, not cancel** — the new setup's daily P&L must NOT correlate negatively with BEARISH_REJECTION_RIDE_THE_RIBBON's daily P&L (Pearson |r| < 0.50).
6. **6-disclosure scorecard** at `analysis/recommendations/opening_drive_fade.json` per OP 20.
7. **J's explicit ratification** — Gamma does not self-promote.

**Default watcher knobs** (active during WATCH phase): `qty=3`, `premium_stop_pct=-0.10`, `tp1_premium_pct=+0.30`, `runner_target_pct=1.5`.

---

## 9. Cost / runtime estimate for Stage 1

**Pure Python, no LLM in the loop** (per OP 11/13). Reuses `multiprocessing.Pool` infrastructure from `sniper_evaluator.py`.

**Per-combo wall time on a single worker:** estimated 4-8 seconds.

**Stage 1 total runtime:**
- 810 combos × 6s mean / 4 parallel workers (`MAX_PARALLEL_RESEARCH_WORKERS = 4` per OP 15) = **~20 minutes** wall clock.
- Worst-case 8s/combo, 3 effective workers = **~36 minutes**.

**Cost in $:** **$0** (pure Python, no Claude calls).

**Disk:** ~1.5 MB Stage 1 results JSON; ~5 MB total including per-combo trade-detail dumps.

---

## Status footer

**Status:** DRAFT — WATCH-ONLY. Created 2026-05-13.
**Rule version pin:** v14. Exit values reference [`params.json`](../../automation/state/params.json). Drift = kill-switch.
**Next action:** Build `lib/watchers/opening_drive_fade_watcher.py` mirroring `sniper_detector.py` structure → wire into heartbeat (read-only, journal-only) → start observation log accrual.
**Eligibility for autonomous paper trading:** **NO** until promotion gates 1-7 above all clear.
