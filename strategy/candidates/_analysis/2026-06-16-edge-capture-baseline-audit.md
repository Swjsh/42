# Edge Capture Baseline Audit — 2026-06-16

**Filed:** 2026-06-16 (overnight session)  
**Author:** Gamma (interactive session)  
**Purpose:** Correct edge_capture formula bug, audit current baseline, identify gap to 771 floor.

## Key Finding: Formula Bug in A/B Script

The A/B comparison script `ribbon_flip_confirm_ab.py` had an INVERTED formula for loser days:

```python
# WRONG: penalizes winning on loser days
- sum(max(0, day_pnl[d]["pnl"]) for d in losers)

# CORRECT per OP-16: penalizes LOSING on loser days
- sum(max(0, -day_pnl[d]["pnl"]) for d in losers)
```

Impact: edge_capture was reported as 598 but correct value is **672**.

## Correct Baseline (V15_J_EDGE_OVERRIDES, BS-sim, current params)

| Day       | Type   | J P&L | Engine P&L | Engine contribution |
|-----------|--------|-------|------------|---------------------|
| 2026-04-29 | winner | +342  | +372       | +372 (to winner sum) |
| 2026-05-01 | winner | +470  | -22        | -22 (to winner sum) |
| 2026-05-04 | winner | +730  | +322       | +322 (to winner sum) |
| 2026-05-05 | loser  | -260  | 0          | 0 (no penalty: engine flat) |
| 2026-05-06 | loser  | -300  | 0          | 0 (no penalty: engine flat) |
| 2026-05-07 | loser  | -165  | +74        | 0 (no penalty: engine WON) |

**edge_capture = (372 - 22 + 322) - (0 + 0 + 0) = 672**  
**Floor = 771, gap = 99**

## ribbon_flip_price_confirm A/B Result

`ribbon_flip_price_confirm=True` has ZERO effect on all 6 J anchor days (delta=$0 for each).
Root cause: the 5/01 exit is `EXIT_ALL_PREMIUM_STOP` at 13:40 (not `EXIT_ALL_RIBBON_FLIP_BACK`).
The $0.50 price buffer is already preventing ribbon flip-back on anchor days.
**Verdict: ribbon_flip_price_confirm is NOT the fix for the 5/01 gap.**

## 5/01 Entry Miss — Root Cause

- Engine enters at 13:35 via `trendline_rejection`, exits at 13:40 (-$22)
- J entered at 13:09 as anticipation/rule break
- CORRECT engine signal was BEARISH_REVERSAL at **11:50 ET** (+$175 per watcher candidate)

5/01 bar at 11:50: O=724.30, H=724.38, L=722.72, C=723.48, V=1,014,537  
This is a massive rejection bar at the 724+ level — $1.66 range, closed $0.90 off high.

Unknown: why didn't the engine fire BEARISH_REVERSAL at 11:50? Candidates:
- Ribbon still BULL at 11:50 (countertrend fade requires BULL ribbon)
- 45-min gap rule blocking (prior entry?)
- Filter_11 requires 2 triggers and only 1 available
- MIDDAY_TRENDLINE_GATE blocks single-trigger trendline entries 11:30-14:00

Kitchen task queued (5a3c6ac9) to investigate.

## 5/07 Engine Behavior

Engine made +$74 via P733 at 12:45 (triggers: ribbon_flip + trendline_rejection, TP1 hit 12:55).
J's 5/07 trades were CALLS (+734C, +737C) that both lost. Engine traded opposite direction and won.
Per corrected formula: this is NOT penalized (engine didn't LOSE on loser day).

## Gap Closure Path

Current: 672, floor: 771, gap: 99

Required to reach 771:
- Fix 5/01 to earn +$99 more (from -$22 → +$77), OR
- Improve 5/04 from +$322 to +$421 (+$99), OR
- Small improvements across both winner days

If the BEARISH_REVERSAL at 11:50 ET would give +$175 on 5/01, the contribution would be:
edge_capture = (372 + 175 + 322) - 0 = **869** → PASSES floor

## 5/01 Root Cause — FULLY RESOLVED (session 2026-06-16)

**Root cause #1: 724 NOT in levels_active.** The backtest `_detect_from_history` builds levels from prior price action. On 5/01, the 724 level was the day's NEW high (H=724.38 at 11:45-11:50) — no historical basis → not in level set. `levels_active` max = 723.0 all day. `detect_level_rejection` requires `bar.high > level AND bar.close < level`; at 11:50 (C=723.48 > 723.0) the 723.0 level doesn't fire.

**Root cause #2: BULL ribbon blocks even if 724 were present.** At 11:50, ribbon=BULL. Filter 5 blocks BEAR entries (requires BULL stack). The trendline-chop relaxation (removes filter 5 when ONLY trendline fires) doesn't apply because level_rejection would fire — not trendline_only_setup. So engine STILL wouldn't enter at 11:50 even with 724 in the level set.

**Why 13:35 works:** `trendline_rejection` fires as the ONLY trigger → `trendline_only_setup=True` → filters 5+8+9 removed → B=[] → passed=True. The -$22 is the trendline setup's loss.

**Stop sweep:** -$56 at every stop from -8% to -40% (the 13:35 entry loses more than 40% in 1 bar). No stop setting can save this trade.

**Closure path:** Requires either (a) level-chop relaxation (analogous to trendline-chop but for named-level breaks in BULL ribbon env) OR (b) improved historical level detection to include intraday highs as real-time levels. Kitchen task queued: `3f0b80df`.

## Filter-6 Discovery (session 2026-06-16)

**Filter 6 blocks J's 10:25 4/29 entry.** At 10:25 on 4/29, ribbon=BEAR, T=['level_rejection'], B=[6, 8, 9]. Spread=**2.4 cents** — filter 6 requires ≥30c. J's actual +$342 entry missed.

**Threshold sweep on J anchor days:**

| Threshold | EC     | 4/29  | 5/01 | 5/04   | 5/05 | 5/06 | 5/07 |
|-----------|--------|-------|------|--------|------|------|------|
| 30c (base)| +673   | +372  | -22  | +322   | 0    | 0    | +74  |
| 20c       | +2057  | -412  | -22  | +2491  | 0    | 0    | +74  |
| 15c       | +2024  | -445  | -22  | +2491  | 0    | 0    | +74  |
| 10c       | +2024  | -445  | -22  | +2491  | 0    | 0    | +74  |

**5/04 at 20c:** enters 11:10 (5 min earlier) at P720 → TP1_THEN_RUNNER_TARGET (2.5x runner hit!) vs 11:15 P719 → TP1_THEN_RUNNER_BE_STOP (runner stopped at BE). +$2169 improvement.

**4/29 at 20c TRAP:** enters 11:50 (spread=29.1c) with 3 triggers (ELITE, quality=3), stops out at -$412. Quality lock then blocks the profitable 12:25 level_rejection trade (quality=2 < 3). Net: -$412 vs +$372 baseline.

**Key research question:** What differentiates 5/04 11:10 (valid, wins big) from 4/29 11:50 (trap, stops out)? Kitchen task queued: `8e49a73f`.

**Loser days (5/05, 5/06, 5/07) unchanged** at 0/0/+74 across all spread thresholds — no new entries on bad days. IS-only favorable signal.

## OOS Validation — filter-6@20c: REJECTED (same session)

OOS window: 2026-05-08 to 2026-05-22 (11 trading days, 16 trades each)

| Version | n | Total | WR | Expectancy |
|---------|---|-------|-----|------------|
| BASELINE (30c) | 16 | -$709 | 25.0% | -$44.3 |
| CANDIDATE (20c) | 16 | -$1,483 | 18.8% | -$92.7 |

The exact same trap repeats: on one day in OOS, 20c opens a 13:15 entry (-$244) that quality-locks the profitable 13:20 entry (+$529). The IS gain is entirely a quality-lock cascade artifact — the earlier (lower-spread) entry blocks a later better entry via the ELITE quality lock.

**Verdict: filter-6@20c fails OOS. REJECTED.** The IS gain on anchor days is backfit, not robust edge. Kitchen task `8e49a73f` updated with OOS-FAIL verdict.

Key takeaway encoded as L92 candidate: "IS quality-lock cascades on anchor days can falsely inflate edge_capture when a threshold change opens an earlier ELITE entry that quality-blocks the true profitable signal." Need discriminator research to find what makes 5/04 11:10 valid (the earlier entry IS the better trade) vs 4/29 11:50 / OOS (earlier entry is a trap).

## VIX-Escalating Compound Test (2026-06-16 — REJECTED)

**Script:** `backtest/autoresearch/f6_vix_escalating_compound.py`

Hypothesis: VIX-escalating (prior_day_VIX >= prior_5d_avg_VIX, L73 SNIPER discriminator) would
gate out the 4/29 11:50 trap while preserving the 5/04 11:10 valid entry.

**Phase 1 — VIX character per anchor day:**

| Day | Type | PriorVIX | 5dAvg | Escalating |
|---|---|---|---|---|
| 4/29 | winner | 17.81 | 18.47 | NO (FLAT) |
| 5/01 | winner | 16.93 | 17.98 | NO (FLAT) |
| 5/04 | winner | 17.00 | 17.65 | NO (FLAT) |
| 5/05 | loser  | 18.18 | 17.66 | YES |
| 5/06 | loser  | 17.43 | 17.58 | NO (FLAT) |
| 5/07 | loser  | 17.25 | 17.36 | NO (FLAT) |

**CRITICAL FINDING:** ALL 3 J winner days have DECLINING VIX. The VIX-escalating gate would
block ALL 3 winner days → EC = 0. **BEARISH_REVERSAL fires on DECLINING-VIX days, not
escalating ones.** This is the OPPOSITE of SNIPER (L73). The tariff-shock period (Apr-May 2026)
was a post-spike mean-reversion environment; VIX was falling from its peak through the best
BEARISH_REVERSAL trading days.

**Phase 2 — Anchor day summary:**

| Config | 4/29 | 5/01 | 5/04 | EC |
|---|---|---|---|---|
| baseline (30c) | +372 | -22 | +322 | +673 |
| 20c only | -412 | -22 | +2491 | +2057 |
| 20c + VIX-escalating | 0 (gated) | 0 (gated) | 0 (gated) | 0 |
| 15c + VIX-escalating | 0 (gated) | 0 (gated) | 0 (gated) | 0 |

**Phase 3 — OOS (2026-05-08 to 2026-05-22):**

| Config | n | WR | Total | Exp/trade | L92 gate |
|---|---|---|---|---|---|
| baseline (30c) | 16 | 25.0% | -$709 | -$44.3 | — |
| 20c | 16 | 18.8% | -$1483 | -$92.7 | FAIL |
| 20c + VIX-escalating | 7 | 28.6% | -$489 | -$69.8 | PASS* |
| 15c + VIX-escalating | 8 | 25.0% | -$984 | -$123.0 | FAIL |

*OOS L92 gate "passes" only because VIX-escalating skips 6 of 11 trading days, removing most
bad trades by exclusion. Per-trade exp = -$69.8 is WORSE than baseline -$44.3. IS EC = 0.
This is not genuine edge improvement — it is day-level removal masquerading as quality gate.

**Verdict: filter-6 threshold research direction EXHAUSTED.**
- filter-6@20c standalone: REJECTED (OOS FAIL, quality-lock cascade, L92)
- filter-6@20c + VIX-escalating: REJECTED (gates out all 3 J winner days, EC=0, per-trade worse)
- VIX character is NOT a valid discriminator for BEARISH_REVERSAL (opposite regime from SNIPER)

**Key doctrine update (encodes as L93):** BEARISH_REVERSAL fires on DECLINING-VIX days.
Do not apply SNIPER regime filters (VIX-escalating, VIX>=18) to BEARISH_REVERSAL. These are
orthogonal strategies with opposing VIX-regime profiles.

## Actionable Next Steps (updated after RIBBON_MOMENTUM_GATE OOS run 2026-06-16)

1. **Exhausted:** Filter-6 threshold direction. Do not revisit without a new discriminator
   hypothesis that doesn't rely on VIX character. (Ribbon spread TREND/momentum could be next:
   "is the spread growing at entry?" rather than "what is the absolute spread?")
2. Kitchen task `3f0b80df`: level-chop relaxation design for 5/01 BULL-ribbon entry (primary path)
3. Kitchen task `8e49a73f`: filter-6 discriminator — confirm that VIX is NOT the answer; suggest
   ribbon-spread TREND (growing vs declining) as next hypothesis
4. **L92 encoded** (2026-06-16): IS quality-lock cascade false positive
5. **L93 encoded** (2026-06-16): BEARISH_REVERSAL VIX regime = declining, not escalating

## RIBBON_MOMENTUM_GATE Analysis (2026-06-16 session — KEY FINDING)

**Corrected production baseline:** `midday_trendline_gate=True` is already live in production
(heartbeat.md line 411). The audit baseline of EC=673 was computed WITHOUT midday_trendline_gate.
True production EC = **718** (gap = 53, not 99).

**Anchor-day decomposition (BS-sim, V15_J_EDGE_OVERRIDES):**

| Config | 4/29 | 5/01 | 5/04 | EC |
|---|---|---|---|---|
| BASELINE (no gate) | +372 | -22 | +322 | +673 |
| MIDDAY_ONLY (live prod) | +396 | +0 | +322 | +718 |
| MOMENTUM_ONLY (min_ribbon_momentum_cents=5, max_bars=20) | +396 | +0 | +322 | +718 |
| ALL_THREE (midday + momentum) | +396 | +0 | +322 | +718 |

**Key finding:** MIDDAY_GATE and MOMENTUM_ONLY give IDENTICAL anchor-day results — they both block
the same 4/29 bad secondary trade and the 5/01 13:35 trendline entry. Adding momentum params on
top of midday gate adds zero incremental EC. The two mechanisms hit the same trades.

**OOS test (2026-05-08 to 2026-05-22, BS-sim):**

| Config | n | WR | Total | Exp/trade |
|---|---|---|---|---|
| BASELINE | 16 | 25.0% | -$709 | -$44.3 |
| MIDDAY_ONLY (live prod) | 12 | 25.0% | -$816 | -$68.0 |
| MOMENTUM_ONLY | 5 | 40.0% | +$389 | +$77.8 |
| MIDDAY + MOMENTUM | 5 | 40.0% | +$389 | +$77.8 |

**CRITICAL: The MOMENTUM gate (min_ribbon_momentum_cents=5, max_ribbon_duration_bars=20) is doing
ALL the work.** Midday gate alone is WORSE than baseline (-$816 vs -$709 because it blocks 4 net
positive afternoon trendline entries). The momentum gate alone swings OOS by +$1,098 (-$709 → +$389)
and makes the midday gate redundant. The combination achieves the same result as momentum alone.

**Implication for RIBBON_MOMENTUM_GATE ratification (rank 22):**
- EC impact: 0 (production already at 718 via midday gate)
- OOS impact: +$1,098 vs true production baseline (-$816 → +$389) or +$1,098 vs no-gate baseline
- This is the strongest OOS signal found. WF ratio=3.736 (from candidate walk-forward) confirmed here.
- **NEEDS J Rule 9 ratification** for params.json: add `min_ribbon_momentum_cents: 5, max_ribbon_duration_bars: 20`
- Note: midday_trendline_gate is already live so no additional heartbeat.md change needed for the gate itself.

**Remaining gap:** Production EC = 718, floor = 771, gap = **53**.
Primary closure path: 5/01 currently $0 — requires BEARISH_REVERSAL at 11:50 ET (level 724, ribbon=BULL).

## 5/01 Level and Ribbon Deep Dive (2026-06-16 session)

**PMH finding**: 5/01 premarket high was only $721.99 (PML=$718.66). 724 is NOT a premarket level.
PDH from 4/30 was $719.79. No historical level in the $723-$725 range.

**First-hour RTH high is the 724 level:**
- 09:55 bar: high=$724.24 (first time SPY crossed 724)  
- 10:00-10:20: price spent 20+ minutes in the $724-$724.87 range  
- RTH day high: $724.87 at 10:20
- 11:50: price retested 724.30, rejected to 722.72 ($1.66 range bar)

The 724 level is the RTH first-hour range high — detectable if engine adds `first_hour_high` (session high from 09:30-10:00) as a named level type. Kitchen task `f0c2a1b5` queued.

**Ribbon at 11:50:**
| Time | Fast EMA | Slow EMA | Spread | Direction |
|---|---|---|---|---|
| 11:35 | 723.19 | 722.25 | +93.4c | BULL |
| 11:40 | 723.30 | 722.32 | +98.0c | BULL |
| 11:45 | 723.45 | 722.40 | +104.1c | BULL |
| 11:50 | 723.45 | 722.45 | **+100.2c** | **BULL** |
| 11:55 | 723.44 | 722.49 | +95.4c | BULL |
| 12:00 | 723.43 | 722.52 | +90.7c | BULL |

**Ribbon was BULL with 100c spread at 11:50. It never flipped to BEAR during the entire morning window.**

Two structural blockers for 5/01 are CONFIRMED and COMPOUND (both required together):
1. **Level 724 not in level set** — PMH=$721.99, PDH=$719.79, no historical 724. Fix: first_hour_high detection
2. **Ribbon=BULL blocks BEAR entry** — filter 5 requires ribbon=BEAR for BEAR trades (unless trendline_only_setup=True). Fix: level-chop relaxation (analogous to trendline-chop)

Kitchen tasks addressing both:
- `f0c2a1b5`: first_hour_high level detection design
- `3f0b80df`: level-chop relaxation design
