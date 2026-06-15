# v14e Edge-Capture Ceiling Analysis
**Date:** 2026-05-24  
**Status:** CLOSED — structural ceiling confirmed, parametric fix ruled out  
**Author:** Gamma (interactive session, per OP-22 engine-benefit autonomy)

---

## The Question

After 535/540 v14e combos, the best `edge_capture` is **499.64 vs the 771 OP-16 gate**.  
Why is there a ceiling, and can parameter tuning break through it?

---

## Per-Bar Trace Methodology

Used `autoresearch.runner.run_with_params` + `BacktestResult.decisions` to compare:
- The engine's actual entry bars (with triggers + blockers recorded)
- J's known entry bars (from `journal/trades.csv`)

Best v14e combo: `strike_offset_bear=0, min_triggers_bear=1, premium_stop_pct_bear=-0.20, tp1_qty_fraction=0.5, no_trade_before=09:35, profit_lock=0.05/0.10, tp1_pct=0.30, runner=2.5`

---

## Per-Day Findings

### 2026-04-29  (J: +$342 · Engine: +$294.15 · Gap: $47.85)

| Time ET | Passed | Score | Ribbon | Triggers | Blockers |
|---------|--------|-------|--------|----------|---------|
| 10:25 ← J entry | False | 7 | BEAR | level_rejection | F6, F8, F9 |
| 12:10 ← engine | True | — | BEAR | trendline_rejection | — |
| 12:25 ← engine | True | — | BEAR | level_rejection | — |

**F6 = ribbon spread < 30c** (early morning, EMAs close together)  
**F8 = VIX not "rising"** (VIX elevated ~26 but falling from tariff highs, not rising)  
**F9 = volume confirmation** (10:25 bar had insufficient volume)  
Gap = 1.5 hours. Three independent blockers. No single-lever fix.

---

### 2026-05-04  (J: +$730 · Engine: +$201.18 · Gap: $528.82)

| Time ET | Passed | Score | Ribbon | Triggers | Blockers |
|---------|--------|-------|--------|----------|---------|
| 10:25 ← J entry | **False** | **9** | BEAR | level+confluence+trendline | **F9 only** |
| 11:15 ← engine | True | 10 | BEAR | level+ribbon_flip+confluence | — |

**F9 = volume confirmation** — only ONE filter blocks at J's exact entry. Score=9, three triggers.

**F9 bypass test:** Setting `f9_vol_mult=0.0` (bypass filter 9 entirely):
- Adds entries at 10:00 (+$116) and 10:25 (**−$344**, massive loser)
- The 10:25 bar on 5/04 is a **GREEN** bar (SPY bouncing), correctly blocked by F9
- Total 5/04 result: +$201 → −$27 (worse by $228)
- Edge_capture: 499 → 272 (catastrophic regression)

**Lesson: F9 is correct.** The 10:25 bar appears to have J's entry time but is a bounce bar, not a breakdown bar. The engine's confirmed 11:15 entry captures the clean breakdown. J's edge is picking the exact level touch; the simulation rewards waiting for confirmation.

---

### 2026-05-01  (J: +$470 · Engine: −$21.56 · Gap: $491.56)

| Time ET | Passed | Score | Ribbon | Triggers | Blockers |
|---------|--------|-------|--------|----------|---------|
| 12:55 | False | 6 | MIXED | level+trendline | F5, F8, F9 |
| 13:09 ← J entry | False | 5 | MIXED | *(none)* | F5, F8, F9 |
| 13:35 ← engine | True | 7 | BULL | trendline_rejection | — |

**Three findings:**
1. At J's 13:09 entry, the level_rejection trigger has **disappeared** (SPY moved through the level by 13:09 — the 12:55 level touch is gone). Score dropped from 6 → 5 with no triggers.
2. Ribbon is MIXED (transitioning) throughout J's entry window.  
3. Engine fires at 13:35 at a **worse spot (722.81 vs J's ~722.15)** on a degraded TRENDLINE-only setup. Immediately stopped out for −$21.56.

**Root cause:** J enters at the FIRST touch of SPY 721 (clean level rejection). The engine waits for confirmation — but by the time confirmation arrives, the level has moved through and the setup is degraded. The engine then fires a low-quality late entry that loses.

---

## Structural Conclusion

The edge_capture ceiling is **architectural, not parametric**:

| Engine architecture | J's architecture |
|--------------------|-----------------|
| CONFIRMATION entries | INITIAL REACTION entries |
| Waits for red bar + volume + ribbon | Enters at first touch of named level |
| Fires 45–90 min after J | Fires on setup formation |
| Higher confirmation = fewer bad entries | Earlier entry = captures full move |

**Parameter sweeps (540 combos) hit the same ~500 ceiling because all v14e combos share this confirmation-first architecture.** Tweaking exit knobs, profit-lock settings, or entry gates doesn't change the fundamental 45-90 min timing gap.

---

## The Fix

**NLWB (Named-Level Wick-Bounce)** — a separate setup designed for INITIAL REJECTION entries:
- Fires when SPY wick reaches a named level (PDH/PDL/VWAP/key MA) with a close-back
- No ribbon stacking required
- No volume confirmation required  
- Focused exclusively on the first-candle level touch

Research groundwork exists (see `memory/project_nlwb_pattern.md`): PDL scan N=157 WR=71%, R5 N=25 WR=68%. Watcher module was the recommended next step.

This is the correct structural complement to v14e:
- v14e handles CONTINUATION setups (confirmed breakdowns after the move starts)
- NLWB handles INITIAL REJECTION setups (entry at the exact level touch)

---

## Edge_Capture by Anchor Day (best v14e combo)

| Date | J P&L | Engine P&L | Gap | Engine entry vs J |
|------|-------|------------|-----|-------------------|
| 4/29 | +$342 | +$294.15 | $47.85 | 1.5h late; 86% capture |
| 5/01 | +$470 | −$21.56 | $491.56 | 26min late, degraded setup |
| 5/04 | +$730 | +$201.18 | $528.82 | 48min late; 28% capture |
| 5/12 | +$400 | +$25.87 | $374.13 | trendline-only late entry |

winners_capture = $499.64 · gate = $771 · gap_to_gate = $271.36

**To close the gap:** NLWB watcher must capture cleanly on ≥1 of the 4 winner days.

---

## Next Actions

1. **Build NLWB watcher** — see `_validator-inbox/` and `_skill-inbox/` pattern  
2. **Kitchen task queued** — `fb3aa952` SNIPER Stage 3 (consecutive escalating days filter)  
3. **v14e closes here** — further parameter sweeps won't improve edge_capture
