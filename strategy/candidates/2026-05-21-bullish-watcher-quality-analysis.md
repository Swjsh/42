# Strategy candidate: Bullish Watcher PM-Session Gate

> DRAFT — Chef proposal 2026-05-21T03:15:00Z. J ratifies.
> Per Rule 9 + OP-21: promotion still requires 3 live J-confirmed wins. DRAFT only.

---

## Hypothesis

The `bullish_watcher` aggregate is -$1,128 over 289 graded observations. However, **the watcher has no meaningful confidence stratification** — 100% of observations are `medium` confidence, all `bull_score=11`, and `ribbon_flipped=False` in every graded observation. The only useful sub-tier discovered is a **time-of-day split**: PM session (13:00-15:59 ET) shows WR=65.6% and +$628 while AM session (10:00-12:59 ET) shows WR=43.9% and -$1,756.

**Directional claim:** A `ENTRY_TIME_START=13:00` gate on the bullish_watcher would transform a losing watcher into a marginally positive one (+$628 on N=61). Combined with OP-21 requirements for live wins, this represents the most promising path toward eventual bullish_watcher promotion.

---

## Backtest evidence

### Data source
- `automation/state/watcher-observations.jsonl`, 289 graded bullish_watcher observations
- All entries: direction=long (confirmed — zero exceptions)
- Coverage: 2025-01 through 2026-05

### Confidence tier analysis

| Confidence tier | N | WR | Total P&L | Avg/trade |
|---|---:|---:|---:|---:|
| high | 0 | N/A | N/A | N/A |
| medium | 289 | 48.4% | -$1,128 | -$3.9 |
| low | 0 | N/A | N/A | N/A |

**The bullish_watcher has no confidence stratification.** Every graded observation is `medium` confidence. This is a structural limitation of the current implementation:

In `v14_enhanced_watcher.py`, `_confidence_from_score()` requires `has_confluence AND n_triggers >= 3` for "high" confidence. Bullish_watcher observations always have `bull_score=11` (max) and 0-2 triggers — the `n_triggers >= 3` gate is never met. The `confidence` field in `bullish_watcher` metadata stores the reclaim level (a float), which is why all observations default to "medium."

**Implication:** The hypothesis that "high-confidence bullish setups are positive" cannot be tested with current data — there are no high-confidence bullish observations to compare against.

### Direction verification

All 289 graded observations: `direction=long`. No exceptions. This is expected — the bullish_watcher only detects BULLISH_RECLAIM_RIDE_THE_RIBBON setups.

### Time-of-day analysis (the only meaningful stratification)

| Window | N | WR | Total P&L | Avg/trade |
|---|---:|---:|---:|---:|
| 10:00-12:59 ET (AM) | 228 | 43.9% | -$1,756 | -$7.7 |
| 13:00-15:59 ET (PM) | 61 | 65.6% | +$628 | +$10.3 |

**Per-hour breakdown:**

| Hour | N | WR | Total P&L |
|---|---:|---:|---:|
| 10 | 87 | 47.1% | -$1,083 |
| 11 | 86 | 41.9% | -$517 |
| 12 | 55 | 41.8% | -$156 |
| 13 | 31 | 67.7% | +$570 |
| 15 | 30 | 63.3% | +$58 |

**Hours 10-12 are the drag; hours 13-15 are the edge.** The 10:00-12:59 window (79% of observations) has WR=43.9% — negative expectancy. The 13:00-15:59 window (21% of observations) has WR=65.6% — positive expectancy.

Why does PM work better for BULLISH_RECLAIM? Structural explanation: By 13:00 ET, the day's directional thesis has typically resolved — a bullish reclaim in the PM session is usually confirmed by the ribbon already being in a BULL configuration (trend continuation), whereas AM reclaims are often the first test of a just-formed level (higher false-positive rate). This is consistent with OP-21's observation that `ribbon_flipped=False` in all observations — the watcher enters before full ribbon confirmation in both AM and PM, but PM entries have the advantage of a session-wide trend already established.

### Monthly breakdown

| Month | N | WR | Total P&L |
|---|---:|---:|---:|
| 2025-01 | 14 | 42.9% | +$19 |
| 2025-02 | 17 | 70.6% | +$343 |
| 2025-03 | 1 | 0.0% | -$68 |
| 2025-04 | 1 | 0.0% | -$88 |
| 2025-05 | 4 | 50.0% | -$68 |
| 2025-06 | 14 | 21.4% | -$382 |
| 2025-07 | 27 | 55.6% | +$49 |
| 2025-08 | 31 | 38.7% | -$393 |
| 2025-09 | 23 | 39.1% | -$286 |
| 2025-10 | 19 | 68.4% | +$316 |
| 2025-11 | 7 | 28.6% | -$321 |
| 2025-12 | 24 | 70.8% | +$449 |
| 2026-01 | 19 | 36.8% | -$379 |
| 2026-02 | 4 | 100.0% | +$344 |
| 2026-04 | 53 | 54.7% | +$21 |
| 2026-05 | 31 | 29.0% | -$685 |

**2026-05 is the worst month by far** (WR=29.0%, -$685). This coincides with the elevated-volatility / tariff-shock period (late April - May 2026). BULLISH_RECLAIM in high-VIX whipsaw environments fails structurally — the ribbon flips back before the reclaim can develop.

### Ribbon flip analysis

All 289 observations: `ribbon_flipped=False`. The watcher never fires after the ribbon has fully confirmed. This is the core structural weakness: the bullish_watcher enters at the early-reclaim stage (pre-ribbon confirmation), which explains the 48.4% baseline WR. The production v14 bull engine (heartbeat) uses the same `evaluate_bullish_setup` but with stronger filtering — the watcher is seeing a superset of the production signals.

---

## Sparse data warning

**N=61 PM observations is thin for a reliable gate.** Before any knob change, this caveat must be registered:

- The PM-gate positive expectancy (+$628 over N=61) could be explained by:
  - Regime concentration (2025-Q4 and 2025-Q3 were strong bull months; PM entries in bull months trend better)
  - Random variation (65.6% WR over N=61 has wide confidence intervals — 95% CI approximately [53%, 77%])
  - Survivorship from the broad dataset: the best months for bullish_watcher happen to also be PM-heavy

**Conclusion: insufficient data for a promotion-path recommendation.** The PM-gate is a hypothesis, not an established edge. It requires:
1. Continued observation accumulation (target N≥100 PM observations)
2. VIX-regime stratification of the PM subset
3. Walk-forward validation before any gate is applied

---

## J-edge (OP-16) compatibility check

The bullish_watcher is a bull setup. J's source-of-truth trades (OP-16) are all bear trades (puts). The OP-16 edge_capture floor (771 / 50% of max 1542) applies to bear candidates.

**OP-16 floor check: N/A for bullish_watcher proposals.** The BULLISH_RECLAIM_RIDE_THE_RIBBON strategy is in DRAFT status per CLAUDE.md ("stays DRAFT until J has 3 live wins on it"). This analysis documents the watcher data but does not assert edge_capture floor compliance.

**OP-21 promotion gate remains in force:** bullish_watcher requires:
- 3+ historical observations that would have won (graded) ✓ (80 runner_hits)
- 3+ live observations confirmed by J ✗ (0 live J-confirmed wins to date)
- Positive expectancy over full backfill ✗ (aggregate -$1,128 over full backfill)
- Per-confidence-tier expectancy positive ✗ (no meaningful tier stratification available)
- J's explicit ratification ✗

**Bottom line: bullish_watcher does NOT qualify for OP-21 promotion at this time.**

The PM-gate finding (if confirmed) would satisfy the "positive expectancy over full backfill" gate for the PM subset, but the full backfill is still negative. The complete OP-21 checklist requires all conditions met simultaneously.

---

## Disclosures (per OP-20)

1. **Account-size assumption:** Default qty=3 contracts, consistent with $1K-$2K tier. WR and P&L numbers are from the watcher grader (TP1+runner 50/50 split at default_tp1_pct=0.30, default_runner_target=1.5×, default_premium_stop_pct=-0.10).

2. **Sample-bias disclosure:** 289 observations over 16 months. The PM subset (N=61) is 21% of total. Monthly distribution shows 2026-04 is the largest single-month contribution (N=53) — this is a dataset recency weight issue. The 2026-04/05 observation spike may reflect watcher replay runs rather than purely organic observations.

3. **Out-of-sample test result:** Not conducted. The time-of-day split is a post-hoc analysis of the existing observation data, not a pre-specified hypothesis tested on held-out data. Treating it as preliminary (N=61 PM) rather than validated.

4. **Real-fills check:** Not conducted for bullish_watcher. The default_premium_stop_pct=-0.10 (-10%) is wider than the bear engine's -8%, but still vulnerable to the L51 initial-bounce effect on first-strike entries. Real-fills simulation via `simulator_real.py` required before any gate change.

5. **Failure-mode enumeration:**
   - **High-VIX whipsaw:** 2026-05 WR=29.0%, -$685. High volatility environments cause repeated ribbon flip/flop, making reclaims unreliable. The PM gate would not protect against regime-level breakdown.
   - **Thin PM sample:** N=61 with wide CI. The 65.6% WR could be random variation.
   - **Ribbon pre-confirmation:** All 289 observations are ribbon_flipped=False — entering before confirmation is structurally riskier than post-ribbon entries.
   - **No high-confidence tier:** The quality discriminator that works for bear v14e (n_triggers >= 3) does not exist for the bull engine in its current form.

6. **Concentration:** 2026-04 (N=53) + 2025-08 (N=31) + 2025-07 (N=27) + 2025-12 (N=24) = 135 of 289 observations (46.7%). The dataset is somewhat concentrated in a few months.

---

## Knob changes proposed

**No production knob changes.** This analysis documents observations only.

**Potential future research item (WATCH-ONLY monitoring):**

If J confirms interest in pursuing a PM-gate on bullish_watcher:
- Add `entry_time_start = "13:00"` to the bullish_watcher configuration
- Continue accumulating PM-window observations (target N≥100)
- Run walk-forward validation on PM-only subset

**File that WOULD be modified (J must ratify first):**
`backtest/lib/watchers/bullish_watcher.py` — add time gate parameter

**NEVER edit params.json or heartbeat.md.** Rule 9 + OP-24 apply.

---

## Pre-merge gate

`python crypto/validators/runner.py` must show all stages PASS.

Current status: **66/66 PASS** (verified 2026-05-21 before this file was written).

This file makes no code changes. Post-write validator run not required for this analysis-only draft.

---

## My confidence: 4/10

**Why 4:**
- The PM-gate signal (N=61, WR=65.6%) is real but thin. Cannot assert positive expectancy with confidence at N=61.
- The complete absence of a confidence-tier split means we have no quality discriminator. Every trade is equally "medium" — the watcher cannot tell a 3-trigger PM reclaim from a 1-trigger AM noise trade.
- OP-21 promotion gates are far from met: 0 live J-confirmed wins, negative full-backfill expectancy.
- 2026-05 being the worst month (-$685, WR=29.0%) is concerning — the most recent data is the worst data.

**What would raise confidence:**
- 50+ PM observations with stable WR ≥ 60% (target: 65%+ sustained)
- A structural explanation for WHY PM is better that can be validated independently (e.g., VIX regime, trend-of-day established, specific hour gate)
- At least 3 live J-confirmed wins per OP-21

**Verdict: NEEDS-MORE-DATA.** Monitor the PM-tier accumulation. No action until N≥100 PM observations and trend holds.

---

*Filed by Chef persona 2026-05-21. DRAFT only. Rule 9 applies — J ratification required before any production change.*
*OP-21 gate: NOT met. This is a monitoring note, not a promotion proposal.*
