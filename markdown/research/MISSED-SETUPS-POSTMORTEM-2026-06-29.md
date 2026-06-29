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
