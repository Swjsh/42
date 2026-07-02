# E6 — J structure-read: RESULTS (2026-07-02, single pre-registered test evaluation)

## Verdict: **NO_SEPARATION**

The frozen structure-read score does NOT separate J's 2023 (held-out) entries on the
primary metric. Test top-quartile direction hit-rate is 17.6pp WORSE than bottom-quartile
(Δhit = −0.1765, permutation p = 0.876). Per the registered ladder this kills the structure
hypothesis as tested: **J's directional read is not recoverable from 5m-bar
rejection/reclaim/BOS-CHoCH structure features at his entry timestamps.** The E1 conclusion
(coordinates are dry) now extends to behavior-at-levels on 5m bars.

Registration: [REGISTRATION.md](REGISTRATION.md), committed at `00376e6` BEFORE any
feature↔outcome correlation was computed. Script: [scripts/e6_structure_read.py](scripts/e6_structure_read.py).
Full numbers: [results.json](results.json). Per-episode features+scores: `episodes-scored.csv`.

## Train vs test (quartile cohorts by frozen score)

| Cohort | n | Direction hit | P&L/trade | Δhit (top−bot) | Δpnl | perm p (hit) | perm p (pnl) |
|---|---|---|---|---|---|---|---|
| TRAIN top Q (2021-06..2022-12) | 101 | 69.3% | +$13.8 | **+21.8pp** | +$65.5 | (descriptive) | |
| TRAIN bottom Q | 101 | 47.5% | −$51.7 | | | | |
| **TEST top Q (2023, once)** | 17 | 52.9% | +$43.5 | **−17.6pp** | +$140.1 | **0.876** | 0.105 |
| **TEST bottom Q** | 17 | 70.6% | −$96.5 | | | | |

Test n = 65 (≥ 40 required — met). Train n = 402.

## Reading the sign-flip honestly

1. **The in-sample separation was an ensemble artifact of uniformly weak features.** Every
   registered feature's train point-biserial is |r| < 0.10 (strongest: `abs_level_dist`
   −0.0995 — closer to a PD level = better, consistent with the at-level fingerprint;
   `level_sweep_favor` +0.081; `touch_count` +0.077, i.e. RETEST beat first-test, opposite
   of the freshness hypothesis; `hold_bars` NEGATIVE −0.064). Summing ten ~0.05-strength
   weights produced a +21.8pp train spread that had no stable signal underneath — it
   inverted on the primary metric out-of-sample.
2. **The test-year P&L curiosity is not a finding.** Test Δpnl = +$140/trade in the
   registered direction (p = 0.105, not significant), while Δhit went the other way — the
   top-score cohort made money while being directionally WORSE (52.9% vs 70.6%). With n=17
   cells and J's heavy-tailed management this is exactly the direction-vs-option-P&L
   decoupling TRAITS #3 documented (his 59% read became a 41% option WR). It cannot rescue
   the hypothesis under the frozen ladder and is reported only for completeness.
3. **What survives:** nothing new ships from E6. The at-level *coordinate* (abs_level_dist)
   was the strongest single train correlate — consistent with, and already covered by, the
   TRAITS at-level fingerprint and the LEVEL_REJECT family. No J_STRUCT_LEVEL detector is
   commissioned (that follow-up was gated on SEPARATES).

## Registered sanity checks

| Check | Result |
|---|---|
| Recomputed nearest_level vs CSV | **100% agreement** (≥99% required) |
| C6 causality assertion (no feature bar closes after entry) | PASS (asserted per episode) |
| Overall hit-rate reproduces TRAITS 59.2% ± 2pp | 61.7% on the studied population — **outside the band, RECONCILED EXACTLY**: the ungated join yields 321 correct of 513 joinable episodes; TRAITS' 59.2% = 321/542 — the same joins with the 29 unjoinable-exit episodes counted as misses in the denominator. Same data, same join convention; the deviation is denominator composition (the registered band was mis-specified against a different denominator), not a bug. The ≥3-bar gate accounts for the rest (the dropped <3-bar cohort hits 71.7% on n=46). |

## Drops (per C7)

| Reason | n |
|---|---|
| Start: closed family, ctx_ok, bias+pnl present | 542 |
| Early entry, <3 completed RTH bars (registered gate; mostly 09:30-09:45 — J's worst-P&L window) | 50 |
| No completed RTH bar strictly after the entry bar before exit (sub-5-min round-trips / same-bar exits) | 25 |
| No entry bar / no prior daily | 0 |
| **Studied** | **467** (402 train / 65 test) |

## Caveats

- Direction hit is measured bar-close-to-bar-close (entry b0 close → last completed bar ≤ exit);
  intrabar moves inside a 5m bar are invisible — sub-bar reads (if J has them) are outside
  this study's resolution by construction. The honest statement is "not recoverable from
  **5m bars**", exactly as the verdict ladder words it.
- Test year 2023 is one regime (n=65, VIX crush / trend-up); no sub-regime split was
  registered and none is claimed.
- The score is a linear train-weighted sum (registered); nonlinear interactions were not
  tested and are NOT licensed for post-hoc exploration against this same test set — 2023 is
  burned for this hypothesis family.
- The studied population excludes J's open-window entries (<3 bars of tape); the verdict
  covers "J past ~09:45", disclosed by design.

## What this kills / what it licenses

- **Kills:** further mining of 2021-23 J entries for 5m structure-read features
  (rejection wicks, reclaim-hold, BOS/CHoCH state, ribbon slope, VWAP streaks) as the
  carrier of his direction alpha. Two independent expressions (E1 coordinates, E6 behavior)
  are now dry on held-out data.
- **Licenses (unchanged from E2/TRAITS):** the management-side conclusions (Rule 4 no-adds,
  −50% cap, strike normalization) — J's alpha existed in-era but its *mechanism* is not
  identifiable from 5m bars; the engine's own validated detectors on 2025-26 OPRA remain
  the only armable path.
