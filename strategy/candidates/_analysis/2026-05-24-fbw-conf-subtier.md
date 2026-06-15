# FBW_MORNING_MID Confidence Sub-Tier Analysis

**Date:** 2026-05-24  
**Source:** Inline computation from `analysis/recommendations/fbw_timing_split.json`  
**Prerequisite:** FBW timing split analysis (same date) — LATE window established as the edge band

---

## Motivation

After isolating the LATE window (10:30–11:30 ET) as the FBW edge in the timing split, the LATE band showed WR=75.9% but some unexplained variance. Within the MID conf band [0.65, 0.80), the watcher already assigns 3 internal labels:
- `"high"`: conf ≥ 0.73 — both sweep depth AND close-back-margin factors near saturation
- `"medium"`: conf ∈ [0.68, 0.73) — one factor saturated, one partial
- `"low"`: conf ∈ [0.65, 0.68) — MID floor (both factors partially active)

Do these sub-tiers have meaningfully different performance in the LATE window?

---

## Results

| Sub-tier | N | WR | exp | P&L | IS N | IS WR | IS exp | OOS N | OOS WR | OOS exp | WF |
|----------|---|----|----|-----|------|-------|--------|-------|--------|---------|-----|
| **HIGH_MID (≥0.73)** | 12 | **91.7%** | **+$78.05** | **+$937** | 5 | 100.0% | +$102.96 | 7 | 85.7% | +$60.26 | **0.585** |
| LOW_MID ([0.65,0.73)) | 17 | 64.7% | −$7.68 | −$131 | 8 | 62.5% | −$38.65 | 9 | 66.7% | +$19.84 | 0.000 |

WF gate: ≥ 0.50. LOW_MID WF=0.000 because IS exp is negative (guard fires).  
conf ranges: HIGH_MID spans [0.735, 0.797], LOW_MID spans [0.651, 0.726].

---

## The Critical Finding

**HIGH_MID (conf ≥ 0.73) IS the FBW edge. LOW_MID is noise.**

### HIGH_MID: Elite tier
- WR=91.7% across 12 completed LATE-window trades
- **IS period: WR=100% (5/5 wins), exp=+$102.96** — zero losses in-sample
- OOS period: WR=85.7% (6/7 wins), exp=+$60.26 — one loss, strongly positive
- WF ratio = 0.585 (gate ≥ 0.50) — PASS
- Conf range [0.735, 0.797] = full sweep depth + full close-back-margin — both wick quality factors fully active

### LOW_MID: Noise
- N=17, WR=64.7%, **P&L=−$131** (net negative)
- IS period: WR=62.5%, exp=−$38.65 (negative IS)
- OOS period: WR=66.7%, exp=+$19.84 (marginally positive but not meaningful)
- The LOW_MID trades have partial wick quality — one factor is weak

### P&L Cascade
- HIGH_MID alone: +$937 (from 12 trades = 41% of LATE trades)
- LOW_MID alone: −$131 (from 17 trades = 59% of LATE trades)
- Combined (LATE ALL): +$806 (17% higher P&L from 41% fewer HIGH_MID trades)

Removing LOW_MID would increase P&L by 16% (+$937 vs +$806) while reducing trade count by 59%. On an expectancy-per-trade basis: +$78.05 vs +$27.79 — **2.8× higher expectancy per trade**.

---

## Why the Sub-Tier Gap Exists

The `failed_breakdown_wick` detector scores confidence as:
- Base: 0.50 (structural signal — bar sweeps below rolling support, closes above)
- Sweep depth factor: +0.05 to +0.15 (how far price penetrated below support)
- Close-back-margin factor: +0.05 to +0.13 (how decisively price reclaimed support)
- Volume factor: small bonus for above-average volume

**HIGH_MID (≥0.73) requires BOTH sweep + close-back factors to be near saturation.** This means:
1. Price swept **significantly** below the rolling support level (not just a tick)
2. Price reclaimed **decisively** above support by session end of the bar

These bars represent genuine false breakdown events — the market tested support aggressively, found genuine buyers, and closed above support with conviction. In the 10:30–11:30 window, this setup benefits from:
- Post-opening-range stability (structure is cleaner)
- Real buyer interest at a tested level (not just a first-touch probe)
- Full day-ahead for the bullish thesis to develop

**LOW_MID (< 0.73) has one weak factor** — either the sweep was shallow (price barely dipped) or the close-back was marginal. These are weaker false breakdowns that may just be noise.

---

## Implication for J's 3-Live-Observation Gate

The watcher already assigns `confidence="high"` to conf ≥ 0.73 signals. So J's 3-live-observation gate should target:

> **3 live `confidence="high"` FBW_MORNING_MID signals in the 10:30–11:30 window.**

This is observable in real-time: when the heartbeat logs an FBW_MORNING_MID observation with `confidence="high"`, that counts toward the gate.

- HIGH_MID fires ~12 times per 16 months = **~0.75/month = ~1 signal every 5-6 weeks**
- To accumulate 3 live HIGH_MID signals: ~4 months estimated lead time
- LOW_MID adds ~1.1/month but should NOT count toward the gate (it's noise)

---

## No Watcher Code Change Needed

The confidence labeling is already correct:
- conf ≥ 0.73 → `confidence="high"` in `WatcherSignal`
- conf ∈ [0.68, 0.73) → `confidence="medium"`
- conf ∈ [0.65, 0.68) → `confidence="low"`

The watcher can continue emitting all MID-band signals (both high and low sub-tiers) for observation accumulation. The 3-live-J-observation gate is now specified as targeting `confidence="high"` signals only.

---

## Summary

| Dimension | Before this analysis | After |
|-----------|---------------------|-------|
| LATE window WR | 75.9% (full MID band) | 91.7% (HIGH_MID only) |
| Expected P&L per trade | +$27.79 | +$78.05 |
| IS expectancy | Positive | Even more positive |
| J gate target | Any LATE MID signal | "high" confidence LATE signal |

---

## Files

- `backtest/lib/watchers/fbw_morning_mid_watcher.py` — Sub-tier comments updated with empirical finding
- `strategy/candidates/_LEADERBOARD.md` #19 — Updated with conf sub-tier results
- Source data: `analysis/recommendations/fbw_timing_split.json` (per_trade_records with conf_score field)
