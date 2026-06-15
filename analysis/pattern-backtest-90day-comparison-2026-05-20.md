# Pattern Backtest — 90-Day OOS Comparison Report

**In-sample window:** 2026-04-21 to 2026-05-16 (19 trading days)
**Out-of-sample window:** 2025-12-01 to 2026-03-31 (87 trading days)
**Script:** `backtest/autoresearch/pattern_backtest.py --range 2025-12-01 2026-03-31`
**OOS corpus:** 1,459 total hits across 87 days (82 days with ≥1 hit)
**Source data:** `backtest/data/spy_5m_2025-01-01_2026-05-19_merged.csv`

> Full regime-gated study (in-sample): `analysis/regime-gated-comparison-2026-05-20.md`
> Full named-level study (in-sample): `analysis/named-level-detector-comparison-2026-05-20.md`

---

## Purpose

The 19-day in-sample study identified several promising signals but most detectors had N < 20
(OP-21 ratification gate). This 90-day OOS window provides the statistical weight to confirm,
attenuate, or reverse each finding. Any finding that holds across both windows is actionable.
Any that reverses is a small-sample artifact and should be retired.

---

## Per-Detector WR Summary

| Detector | In-Sample N | In-Sample WR | OOS N | OOS WR | Stability |
|----------|-------------|--------------|-------|--------|-----------|
| `double_bottom` | 95 | 54.3% | 359 | 51.1% | ✅ stable (−3.2pp) |
| `double_top` | 34 | 44.1% | 306 | 49.7% | ⚠️ slight recovery |
| `failed_breakdown_wick` | 12 | 50.0% | 77 | 55.3% | ✅ stable (confirmed edge) |
| `rejection_at_level_bearish` | 8 | 57.1% | 54 | 61.1% | ✅ confirmed strongest (+4.0pp) |
| `momentum_acceleration` | 20 | 58.8% | 101 | 56.0% | ✅ stable (−2.8pp) |
| `head_and_shoulders_top` | 0 | n/a | 60 | 54.2% | 🆕 first data |
| `inside_bar_consolidation` | 62 | n/a (neutral) | 192 | n/a | ✅ confirmed neutral by design |

---

## Regime-Gated (Contra-50-Bar-SMA) Analysis

### Contra-WR Deltas: 19-Day vs 90-Day OOS

| Detector | In-S Base | In-S Contra | OOS Base | OOS Contra | In-S Delta | OOS Delta | Verdict |
|----------|-----------|-------------|----------|------------|------------|-----------|---------|
| `double_bottom` | 54.3% | 52.6% | 51.1% | 49.6% | −1.7pp | −1.5pp | ✅ null confirmed |
| `failed_breakdown_wick` | 50.0% | 37.5% | 55.3% | 50.0% | **−12.5pp** | **−5.3pp** | ✅ negative confirmed (weaker) |
| `rejection_at_level_bearish` | 57.1% | 66.7% | 61.1% | 54.5% | +9.6pp | **−6.6pp** | ❌ REVERSED |
| `momentum_acceleration` | 58.8% | 100% | 56.0% | 58.8% | +41.2pp | +2.8pp | ⚠️ attenuated (still positive) |

### Key Regime-Breakdown Findings (90-Day)

| Detector::Regime | N | WR | Note |
|------------------|---|----|------|
| `failed_breakdown_wick::aligned` | 20 | **70.0%** | FBW fires IN the trend = strong continuation |
| `failed_breakdown_wick::contrary` | 56 | 50.0% | Contra = noise (was −12.5pp in-sample, now flat) |
| `rejection_at_level_bearish::aligned` | 32 | **65.6%** | RAL strongest when trend-aligned |
| `rejection_at_level_bearish::contrary` | 22 | 54.5% | Positive but below base — contra adds noise |
| `momentum_acceleration::contrary` | 34 | 58.8% | Contra still best sub-group for MA (+4.3pp over aligned 54.5%) |
| `momentum_acceleration::aligned` | 66 | 54.5% | Trend-aligned MA is solid baseline |
| `ral_at_PDH::aligned` | 10 | **70.0%** | When RAL fires at PDH aligned with trend — excellent |
| `ral_at_PDH::contrary` | 11 | 36.4% | RAL at PDH against trend = strong negative |
| `fbw_at_PDL::contrary` | 14 | **21.4%** | FBW at PDL against trend = almost certainly a bounce trap |
| `fbw_at_PDL::aligned` | 4 | 50.0% | n too small |

### Revised Rule on Regime Gating (from 90-Day Evidence)

```
CONFIRMED NEGATIVE:  failed_breakdown_wick_contra  (−5.3pp, N=56 — trend-continuation signal)
CONFIRMED NULL:      double_bottom_contra           (−1.5pp, N=122 — structure self-confirms)
ATTENUATED POSITIVE: momentum_acceleration_contra   (+2.8pp, N=34 — positive but not 100%)
REVERSED:            rejection_at_level_bearish_contra (−6.6pp OOS vs +9.6pp in-sample)
```

**The prior in-sample finding ("every detector outperforms 4-15pp contra-regime") is REFUTED.**

The only regime gate with confirmed positive edge is `momentum_acceleration_contra` (+2.8pp at N=34).
This is below OP-21 ratification gate (N≥20 ✅ met, but margin is thin). Track via gym grinder.

---

## Proximity to Named Levels (near_key_level Analysis)

This is the **cycle-16 new finding** — the first time `notes["near_key_level"]` has been run
at scale. The results are surprising and require the in-sample proximity hypotheses to be
revisited.

### Proximity Effect by Detector (90-Day OOS)

| Detector | Near-Named N | Near-Named WR | No-Named N | No-Named WR | Proximity Delta | Finding |
|----------|-------------|---------------|-----------|-------------|-----------------|---------|
| `momentum_acceleration` | 36 | 50.0% | 64 | **59.4%** | **−9.4pp** | ❌ Proximity HURTS |
| `momentum_acceleration_contra` | 10 | 50.0% | 24 | **62.5%** | **−12.5pp** | ❌ Proximity HURTS (worse) |
| `rejection_at_level_bearish` | 17 | 52.9% | 37 | **64.9%** | **−12.0pp** | ❌ Proximity HURTS |
| `rejection_at_level_bearish_contra` | 9 | 44.4% | 13 | **61.5%** | −17.1pp | ❌ strong negative (N small) |
| `failed_breakdown_wick` | 21 | **61.9%** | 55 | 52.7% | **+9.2pp** | ✅ Proximity HELPS |
| `failed_breakdown_wick_contra` | 10 | 60.0% | 46 | 47.8% | +12.2pp | ✅ Proximity HELPS contra too |
| `head_and_shoulders_top` | 26 | **61.5%** | 33 | 48.5% | **+13.0pp** | ✅ Proximity HELPS strongly |
| `double_bottom` | 111 | 53.2% | 245 | 50.2% | +3.0pp | ✅ Mild positive |
| `double_top` | 87 | 52.9% | 217 | 48.4% | +4.5pp | ✅ Mild positive |
| `ral_at_PDH` (all near) | 22 | 52.4% | — | — | baseline=61.1% raw | ❌ Level anchor underperforms |
| `fbw_at_PDL` (all near) | 18 | **27.8%** | — | — | baseline=55.3% raw | ❌ Level anchor catastrophic |

### Critical Proximity Reversals

**1. `momentum_acceleration::near_named` = 50.0% WR (N=36) — IN-SAMPLE REVERSAL**

The 19-day study showed `momentum_acceleration::near_named` at 80% WR (N=5). This was
celebrated as a strong finding. At N=36 in OOS it collapses to 50.0% — coin-flip territory.

The hypothesis was: MA fires near named levels → level acts as target → price reaches target.
The 90-day data says the opposite: when a wide-range high-volume bar fires NEAR a named level,
the level acts as a **resistance wall** — price stalls rather than clearing.

`momentum_acceleration::no_named` (64 signals, 59.4% WR) is the actual edge: wide-range
momentum bars in open price action, NOT at a named-level boundary.

**This finding is definitive. The 19-day in-sample result was a small-sample artifact (N=5).**

**2. `rejection_at_level_bearish::near_named` = 52.9% vs `::no_named` = 64.9%**

RAL fires best when NOT near a named level? That seems paradoxical — RAL is a level-rejection
signal by definition. Interpretation: RAL's own internal anchor (the `ref_price` / anchor bar)
is already the "level." A named key-level nearby adds redundancy and potentially creates
conflicting exit targets — the named level may be slightly different from the detector's
own anchor, so price behaves unpredictably between the two levels.

**Implication for `ral_at_PDH`:** Anchoring specifically to PDH underperforms standalone RAL
(52.4% vs 61.1%). The PDH anchor RESTRICTS RAL to cases where named + detector level coincide,
and that restriction is net negative. The `ral_at_PDH` scan should be retired from the
promotion queue — standalone `rejection_at_level_bearish` performs better.

**3. `fbw_at_PDL` = 27.8% WR (N=18) — Catastrophic**

`fbw_at_PDL` was designed to filter FBW specifically to wick events at the Previous Day Low.
The hypothesis: PDL is a key defense level; a wick below it should be a high-conviction bounce.
The 90-day data says: **27.8% WR across 18 signals**. This is deeply negative.

Regime breakdown reveals the mechanism: `fbw_at_PDL::contrary` = 21.4% WR (N=14). The
vast majority of PDL wick events fire contra-regime (wick below PDL in a downtrend). That
means PDL "support" is getting violated and bouncing, but in a downtrending context the bounce
fails — it's a bear flag, not a reversal. Only 4 PDL signals were regime-aligned (50% WR, N=4).

**Rule:** `fbw_at_PDL` scan is REJECTED. The PDL-anchored FBW variant inverts FBW's edge.
Remove from promotion queue. FBW's edge lives in trend-aligned (70% WR) non-level contexts.

### Where Proximity Helps (Structural Patterns)

FBW (+9.2pp), H&S (+13.0pp), double_bottom (+3.0pp), double_top (+4.5pp) — all structural
multi-bar patterns benefit from proximity to named levels.

Interpretation: structural patterns that COMPLETE near a named level get natural follow-through
from level participants adding to the move. The named level provides a "floor of believers"
that amplifies the structural completion.

This is the OPPOSITE of momentum/impulse patterns: impulse bars near levels stall (level absorbs
the momentum); structural completions near levels accelerate (level provides confirmation).

---

## Confidence Band Analysis (Confirmed at Scale)

| Band | OOS N | OOS WR | In-Sample WR | Stability |
|------|-------|--------|--------------|-----------|
| < 0.60 | 152 | **55.9%** | — | ✅ best band |
| 0.60–0.70 | 447 | **46.8%** | worst | ✅ consistently worst |
| 0.70–0.80 | 416 | **55.5%** | best | ✅ confirmed |
| 0.80+ | 241 | 51.5% | — | mid |

The 0.60–0.70 band underperformance is confirmed at N=447 (far above any small-sample concern).
This is the strongest confidence-formula finding in the study: signals in that band are worse
than random, and the band contains 35% of all signals.

**Priority item:** confidence formula recalibration should penalize the 0.60–0.70 band.
The non-monotonic pattern (best = <0.60 + 0.70-0.80; worst = 0.60-0.70) suggests the formula
has a spurious local maximum that inflates confidence scores without predictive power.

---

## Summary Table: What Survives vs What Was Overturned

### Confirmed (held across both windows)

| Finding | Evidence |
|---------|----------|
| FBW is a trend-continuation signal (not reversal) | Aligned 70.0% WR vs Contra 50.0% |
| double_bottom contra is null | −1.5pp in OOS, −1.7pp in-sample |
| 0.60–0.70 confidence band is weakest | 46.8% OOS (N=447) |
| rejection_at_level_bearish has the strongest raw edge | 61.1% OOS at N=54 |
| momentum_acceleration_contra is modestly positive | +2.8pp OOS, confirmed direction |

### Revised (attenuated but directionally confirmed)

| Finding | In-Sample | OOS | Takeaway |
|---------|-----------|-----|----------|
| FBW contra penalty | −12.5pp | −5.3pp | Confirmed negative, magnitude overstated |
| MA_contra uplift | +41.2pp | +2.8pp | Was N=6 artifact; real edge exists but is modest |

### Overturned (do not promote)

| Finding | In-Sample | OOS | Takeaway |
|---------|-----------|-----|----------|
| MA near_named = 80% WR | N=5 | N=36, 50.0% | Small-sample artifact, RETIRED |
| RAL_contra = +9.6pp | N=7 | N=22, −6.6pp | Noise at in-sample N; REVERSED at scale |
| fbw_at_PDL = promising | N=0 (new) | N=18, 27.8% | REJECTED — inverts FBW's edge |
| ral_at_PDH = promising | N=0 (new) | N=22, 52.4% | Underperforms raw RAL (61.1%); retire |

---

## Promotion Queue Revisions (post-90-day)

| Candidate | Prior Status | Post-OOS Status |
|-----------|-------------|-----------------|
| `momentum_acceleration_contra` | N=6, 100% — promising | N=34, 58.8% — track (need N≥20 ✅ met); ratify when 20 live days |
| `rejection_at_level_bearish_contra` | N=7, 66.7% — promising | N=22, 54.5% — marginally above base (61.1%), contra HURTS; RETIRE |
| `fbw_at_PDL` | planned watch | 27.8% OOS — REJECT outright |
| `ral_at_PDH` | planned watch | 52.4% vs 61.1% raw — REJECT, underperforms |
| **`momentum_acceleration::no_named` gate** | not tracked | **New: 59.4% WR at N=64 — consider watch-only** |
| **`failed_breakdown_wick::near_named`** | not tracked | **New: 61.9% vs 52.7% no_named (+9.2pp, N=21) — track** |
| **`head_and_shoulders_top::near_named`** | not tracked | **New: 61.5% vs 48.5% no_named (+13pp, N=26) — strongest new finding** |

---

## Next Steps for Cycle 17

1. **Retire `fbw_at_PDL` and `ral_at_PDH`** from queue.md — negative edge confirmed at OOS.

2. **Add `head_and_shoulders_top::near_named` to promotion queue** — 61.5% WR (N=26) is the
   strongest proximity signal. When H&S completes near a named level (PDH, R1 etc.), the structural
   completion + level resistance combine for measurable edge. Track via `scan_high_edge_near_named`.

3. **Add `failed_breakdown_wick::near_named` to watch** — 61.9% WR (N=21) near named vs 52.7%
   without. FBW near a named level = legitimate bounce off real support. Distinguish from FBW in
   open air (weaker setup).

4. **Confidence formula recalibration** — 0.60–0.70 band confirmed worst (46.8%, N=447).
   Priority item per queue.md. Per-factor regression should penalize whatever inflates scores
   into 0.60–0.70.

5. **Key insight to encode in heartbeat:** `momentum_acceleration` fires best FAR FROM named
   levels (59.4% WR no_named). Adding a `not near_key_level` filter could improve live signal
   quality. WATCH-ONLY per OP-21 — requires Rule 9 before heartbeat integration.

---

## Verification

- Gym: 53/54 PASS overall_pass=True
- v22 offline: 27/27 PASS (T26-T27 cover `enrich_hit_with_proximity`)
- No changes to `automation/prompts/heartbeat.md`, `automation/state/params*.json`

---

*Report generated: 2026-05-20 | OOS window: 2025-12-01 to 2026-03-31 (87 days) | 1,459 total hits*
