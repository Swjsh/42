# Post-Mortem — Two Missed Setups, 2026-06-29 (SPY 5m)

> Status: N=1. This document produces detector SPECS + VALIDATION PLANS. It does **not** arm anything. Per CLAUDE.md C3/C4 — a pattern a random-entry null reproduces is not alpha; beat the null on real OPRA fills before paper, paper before live.

## TL;DR
- Engine HELD every tick (bear 5-9 / bull 5-9, never ENTER) while two J-readable, data-validated setups played out.
- **One deterministic bug explains ~85% of both misses:** `key-levels.json` was FROZEN at the premarket draw, so the engine's top resistance was PMH 738.10 — it never saw 739.73/739.86 (rejections) or 732 (support) as levels. Every level-tied trigger (`level_rejection`, `level_reclaim`, `sequence_*`) was starved of input.
- **Two genuine viewpoint gaps remain even after the level fix:** (a) the engine has no PRE-break twin-rejection aggregator, and (b) double-bottom is watch-only + structurally blind to adjacent-bar W's.

## The two setups (data-validated)
- **Setup A (puts):** 09:45 + 09:50 twin shooting-star rejections at 739.73/739.86, then 09:55 breakdown O=738.89 C=736.83 on vol 31978 (1.92x the 09:50 bar). Ride to 733 ≈ $5/share.
- **Setup B (calls):** 10:10 L=733.03 / 10:15 L=732.12 double bottom, 10:25 reclaim to 736.06, rode the ribbon +$5 all afternoon.

## Why the engine missed — mechanism, not theory

### Shared root cause: frozen levels (deterministic bug)
`heartbeat_core._read_levels()` reads `key-levels.json` each tick but does not reject a stale timestamp; the file was last drawn ~08:39 ET. `detect_level_rejection` / `detect_level_reclaim` only iterate `levels_active`, so levels formed intraday (739.80 resistance, 732 support) were invisible. This is the primary blocker for BOTH setups and for any level-based trigger.

### Setup A — missing viewpoint: PRE-break twin-rejection
`detect_sequence_rejection` (filters.py L465) is **post-break**: it needs `role=='broken_to_resistance'` AND 3+ strictly-decreasing highs *after* price already traded below the level. It cannot see two rejections that both happen AT/ABOVE a level *before* any break — exactly 06-29. `is_shooting_star` exists (L198) but is captured-and-ignored (never a trigger). `breakdown_bar_bearish` checks vol>=1.3x of the 20-bar MA — it has **no bar-to-bar expansion ratio**, so the 09:55 ~2x spike read identical to a 1.3x bar.

### Setup B — missing viewpoint: adjacent-bar double-bottom, and it's watch-only
`double_bottom_detector` (crypto/lib/chart_patterns.py L99) **structurally rejects** 06-29's W: `min_separation_bars=2` plus `between = window[low1_idx+1:low2_idx]` → empty for adjacent lows → `if not between: return None`. Compounding it, `_is_local_low` requires the bar's low < BOTH neighbors, so in the stair-step down (10:10 > 10:15 < 10:20) only the 10:15 bar qualifies → one local low → None. And double-bottom lives ONLY in `double_bottom_base_quiet_watcher` (WATCH-ONLY, OP-21, 0/3 live confirmations) — the core `evaluate_bullish_setup` has no double-bottom trigger at all. The watcher's proximity gate is also `NOT_NEAR_NAMED` (rejects when near a level) — the opposite of wanting a mapped support.

## Missing-viewpoints table (audited against code)
| Primitive | Exists? | Where | Gap |
|---|---|---|---|
| Body/wick geometry | YES | filters.py L165 `_bar_geometry` | None — fully computed |
| Shooting-star / hammer | YES | filters.py L198/L212 | Exists but captured-and-IGNORED; never a trigger |
| Volume baseline (20-bar) | YES | filters.py L117 | None |
| Volume EXPANSION (bar-to-bar / N-bar ratio) | NO | — | **Missing** — only vol>=mult×20barMA; 2x spike invisible |
| Pre-break twin-rejection at a level | NO | — | **Missing** — sequence_rejection is post-break + needs 3 lower-highs |
| Failure-to-break aggregator | NO | — | **Missing** — no "tested+rejected N times" memory pre-break |
| Double-bottom in CORE engine | NO (watch-only) | watcher only | **Missing from evaluate_bullish_setup**; adjacent-bar W structurally rejected |
| Intraday level discovery | NO | premarket draw only | **Missing** — the shared root cause |

## The two detector specs (summary)
- **DUAL_REJECTION_SEQUENCE_BREAKDOWN** (bearish): 2 consecutive shooting-star rejections at the same level (±0.15) that both close below it, then a breakdown bar with `vol_expansion_ratio>=1.5`, `close<min(rej closes)`, `body_pct>=0.60`. Entry = bar AFTER breakdown closes (Rule 2). Stop = final_rejection_high+0.50. Reuses `is_shooting_star`; adds `vol_expansion_ratio`. Depends on the level fix.
- **DOUBLE_BOTTOM_ADJACENT_RECLAIM** (bullish): relax `min_separation_bars` to 1 + neckline=max(low1.high,low2.high) for empty-between + tolerate stair-step first low; reclaim >=0.1% above neckline; gate to fire AT a mapped support. Wire into `evaluate_bullish_setup` as a level-tied trigger. Depends on the level fix.

## GO / NO-GO bar each detector must clear before ARMING (none cleared today)
1. **Beat the null ≥2σ** on real OPRA fills (C1/C3): random-entry baseline with the same exit structure must NOT reproduce the P&L. Setup A needs TWO nulls (random vol-expansion red bar; single-rejection). Setup B needs random green-reclaim entry with the same ribbon-ride exit.
2. **Trade count ≥ 20** over the 2024-01→2026-06 backtest (C13 reachability).
3. **False-positive base rate disclosed** — twin shooting-stars / adjacent double-bottoms are common; the breakout/reclaim filter must demonstrably filter the losers.
4. **Per-trade expectancy ≥ threshold, NOT WR** (C4) — mean R reported with stdev/min/max.
5. **Mapped-level subgroup lift** (C26) — at-level vs open-space must beat by ≥15% WR or the level gate is decorative.
6. **OOS sign-stable** — walk-forward train 2024→2026-02 / test 2026-03→06 positive (C6).
7. **Strike-offset matches production picker** (C16 sim-accuracy gate) and is realizable at historical OPRA bid/ask (C11) — no BSM-mid fantasy fills.
8. **Anchor no-regression** — the level fix + detectors must keep `edge_capture ≥ 771` on J's anchor trades (OP-16).

Auto-ship rail (OP-11/OP-22): only if OOS_positive AND WF≥0.70 AND sub-window-stable AND anchor-no-regression AND A/B scorecard filed. Until then: WATCH-ONLY. The intraday-level-discovery fix is a **deterministic bug fix** (not a new pattern) and can ship on the anchor-no-regression gate alone, independent of the two pattern detectors.

## Sequencing
1. Ship + backtest the intraday-level-discovery fix FIRST (unblocks everything; anchor-no-regression gate). 
2. Re-run 06-29 with the fix — confirm whether existing `level_rejection`/`level_reclaim` already fire (the swarm's redundancy question). 
3. Only the residual edge BEYOND the level fix justifies the two new candle-structure detectors — develop + null-test those in the kitchen, ship behind the GO/NO-GO bar.

---

## Swarm verdict (5-model free panel, 2026-06-29, 5/5)

The free 5-model swarm adversarially reviewed the two detectors. **Consensus + most-rigorous line:**
1. **~85% of the miss = the frozen-levels bug (already fixed), NOT a novel candle signal.** Both setups are largely a data-ingestion failure.
2. **Redundancy is the live question:** ship the level-fix alone, re-run 06-29 + the anchor tape, and check whether the EXISTING level_rejection (bear) / level_reclaim (bull) triggers already fire on the same bars. If they do, the two new candle-structure detectors are **redundant**.
3. Only the **residual edge BEYOND the level fix** justifies building DUAL_REJECTION / DOUBLE_BOTTOM_ADJACENT — and each must still beat its null (the breakdown-bar-alone null for A; the random-green-reclaim-with-same-ribbon-exit null for B) and disclose the twin-wick / adjacent-W false-positive base rate.

**THE next action (swarm-confirmed + queued to kitchen):** the level-fix-only redundancy backtest on 06-29 + the anchor tape. Build the candle detectors only for what it leaves on the table.


---

## REDUNDANCY BACKTEST RESULT (ran it — this CORRECTS the post-mortem)

Re-ran 06-29 through run_backtest (which caches today session H/L, so 739.9/732 ARE in levels_active) with REAL VIX. Finding:

**The PUT side is NOT a missing-detector problem.** With the level present, the existing `level_rejection` trigger FIRED at **bear_score 8** (+confluence at 10:00) on every rejection bar 09:45-10:05. The engine SAW the rejection. It HELD because of **two filters**:
- **Filter 5 (ribbon must be BEAR-stacked)** — ribbon was BULL the entire window. A top/rejection forms WHILE the ribbon is still bull; it only flips bear AFTER the breakdown. So filter 5 structurally forbids entering on a rejection-at-top. **This is the mechanism behind "theorize before the move": the engine is forced to wait for ribbon confirmation that lags the rejection.**
- **Filter 9 (breakdown bar required)** — the shooting-star rejection bars are not breakdown bars; only 09:55 was, and by then filter 5 still blocked.
- Filter 8 (VIX) only blocked 1 bar with real VIX — mostly a flat-VIX test artifact, NOT a real blocker.

**=> The DUAL_REJECTION candle detector is largely REDUNDANT (level_rejection already fires at bear 8). The REAL lever is a controlled relaxation of filter 5 / filter 9 for a HIGH-CONFIDENCE rejection-at-mapped-resistance (bear>=8 + confluence + level_rejection + shooting-star/volume structure).**

**DANGER (why this is gated, not shipped):** filter 5 (ribbon-must-be-bear) is one of the most load-bearing filters — it blocks counter-trend losers (shorting into an uptrend is mostly a loser). Relaxing it lets in counter-trend trades. 06-29 is N=1 survivorship. The swarm's exact warning applies: how many twin-rejections-at-resistance-while-ribbon-bull RIP HIGHER instead? This MUST beat the null with the false-positive base rate disclosed, on real OPRA fills, OOS-stable, anchor-no-regression, before any arming.

**Revised next task:** an A/B on relaxing filter 5/9 for the strong-rejection-at-resistance case (NOT a new candle detector). The candle-structure (shooting-star + volume) becomes the QUALITY GATE that makes the counter-trend relaxation safe — that is where it earns its place, if at all.

---

## BASE-RATE TRIAGE RESULT (ran it) — the filter-5 relaxation is KILLED by data

Ran the forward-direction base rate over 2025-07..2026-06-18 (1 year). The "signal" = every
bar with bear_score>=8 + level_rejection that was blocked ONLY by filter 5/8/9 (i.e. the
exact relaxation candidates, n=1298):

| set | n | breakdown% (put wins, +30min) | mean fwd move |
|---|---|---|---|
| signal (filter-5/9-blocked strong bear rejection) | 1298 | **48%** | -0.003% |
| signal + confluence | 673 | 48% | -0.009% |
| NULL (all RTH bars) | 15884 | **47%** | +0.002% |

**The signal is a COIN FLIP** — 48% breakdown vs 47% random null, mean forward move ~zero.
There is NO directional edge. **Filter 5 (ribbon-must-be-BEAR) is CORRECTLY blocking
counter-trend noise.** Relaxing it would add ~1300 coin-flip counter-trend trades/year =
a guaranteed loser after theta/costs. 06-29 was **N=1 survivorship** — the one instance that
worked, out of a population that nets to nothing (exactly the anti-overfit agent's warning).

**CONCLUSION: the engine's HOLD on 06-29 was CORRECT PROCESS, not a bug.** It declined a
setup that is a coin flip in general. Process > outcome (CLAUDE.md). The pattern we "missed"
loses money in aggregate. Do NOT relax filter 5 on this signal. If any edge exists it is in a
narrow sub-slice (specific VIX character / time-of-day / tighter geometry) that must beat the
null on its own — but the aggregate sitting exactly at the null is a strong prior against it.
The CALL side (double-bottom-at-mapped-support) is a separate, still-open question — its
existing trigger path (level_reclaim, ribbon already bullish so filter-5-equivalent passes)
was not the same coin flip and is worth its own triage.

---

## CALL-SIDE TRIAGE RESULT (ran it too) — weak edge, washes out, also not the trade

Slid the production `double_bottom_detector` over the same ~1yr (n=318 confirmed
neckline reclaims), measured forward direction:

| set | n | up% +60min | mean +60min | up% +to-EOD | mean +to-EOD |
|---|---|---|---|---|---|
| double-bottom reclaim | 318 | **56%** | +0.028% | 53% | +0.039% |
| null (all bars) | 16113 | 53% | +0.003% | 55% | +0.017% |
| null (GREEN bars, +to-EOD) | 8111 | — | — | 55% | +0.016% |

**Findings:** (1) a WEAK ~60-min edge — 56% up vs 53% null, mean +0.028% vs +0.003%
(~10x the drift but still only ≈$0.21 on SPY). (2) **The "ride the ribbon all afternoon"
thesis is NOT supported** — by EOD the double-bottom (53% up) is no better than a random
green bar (55%). 06-29's all-day ride was again survivorship. (3) The adjacent-bar patch
made ZERO difference (identical n=318) — the blind spot is real but empirically irrelevant.

**Conclusion:** the 60-min lift is real but marginal and almost certainly too small to beat
0DTE call theta/spread (a $0.21 move in 60min won't move an OTM call enough). Low-priority:
only a real-OPRA-fills test of the 60-min-exit variant could confirm, but the prior is it's
theta-eaten. The all-day-ride framing is dead.

## NET OF THE ENTIRE 06-29 MISSION
- ✅ **Intraday level feed** — a genuine bug, genuinely fixed (the ONLY real shippable win).
- ❌ DUAL_REJECTION candle detector — redundant (level_rejection already fires at bear 8).
- ❌ Filter-5 relaxation — coin flip (48% vs 47% null). Filter 5 correctly blocks it.
- ⚠️ Double-bottom calls — weak 60-min lift that washes out by EOD; likely theta-eaten.
- **Both setups J flagged are mirages in aggregate. The engine's HOLD on both was correct
  process, not a bug.** N=1 winners drawn from coin-flip / wash populations. Process > outcome.

---

## CORRECTION (J's challenge): I measured DIRECTION, not EXPECTANCY — the asymmetry is real

J caught the error: the "48% coin flip" was win-RATE, not expectancy. With filters 5/9 OFF
(take the rejection regardless of ribbon/breakdown) + a TIGHT stop + the real exit engine,
real-OPRA P&L (bear/PUT, 2025-07..2026-06, n≈72):

| config | n | WR | total | exp/trade | avg win / loss | max DD |
|---|---|---|---|---|---|---|
| baseline (filters on) | 54 | 46% | -$1151 | -$21 | $208/-$219 | -$3027 |
| 5+9 off, -50% stop | 66 | 47% | -$861 | -$13 | $199/-$201 | -$3230 |
| 5+9 off, -30% stop | 71 | 35% | -$663 | -$9 | $221/-$135 | -$1556 |
| **5+9 off, -20% stop** | 72 | 32% | **+$473** | **+$6.6** | $224/-$95 (2.3:1) | -$1006 |
| 5+9 off, -12% stop | 72 | 24% | +$71 | +$1.0 | $206/-$62 | -$624 |

So **the asymmetry IS real** — a 32% WR with a tight -20% stop is +EV on the full period
because the tight stop caps the counter-trend losers and the runners pay. My direction-only
"coin flip = dead" was the wrong metric (C4: expectancy, not WR).

## BUT — the OOS split KILLS arming it (regime-dependent)

Walk-forward, real fills, -20% stop:
- **TRAIN 2025-07..2026-02: +$1235 (exp +$27, WR 31%)**
- **TEST  2026-03..2026-06: -$762 (exp -$28, WR 33%)** — NEGATIVE.
- -15% stop same shape: TRAIN +$665 / TEST -$801.

The full-period positive was carried ENTIRELY by the older regime; in the recent quarter it
LOSES at every stop. **Why it makes sense:** 2026-Q2 is a bull-RECOVERY regime — failed
gap-ups that sell off then get bought back (06-29 IS one: rejected 739 -> dropped to 732 ->
recovered to 738). A counter-trend put held with a runner gives the gains back on the
recovery. **06-29 was the exact regime where this strategy is net-negative.**

**FINAL VERDICT: real asymmetry (J was right on the metric), but NOT OOS-stable, and the
current regime is precisely where it loses. Do NOT arm.** It fails the WF gate (test window
negative). Revisit if/when the regime shifts to trend-down (where counter-trend-down = with-
trend). The level feed remains the only shippable win of the mission.
