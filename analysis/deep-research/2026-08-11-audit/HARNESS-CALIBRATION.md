> ⚠️ **SUPERSEDED SAME NIGHT — v4 is NOT the final calibration.** The "+$384" headline below was two errors cancelling (SPY feed ended 07-22 = optimistic; 2¢ slippage = pessimistic). **Final = v5: `extreme` fills + 1¢ slippage + full SPY union feed → bias −$7.4/pos, 95% sign agreement** (see the 08-11 loop commits and the lesson-inbox item *two-errors-cancelling-calibration*). The v1→v4 narrative below stands as the record of how it was found.

# Harness calibration + what it says once it can be trusted — 2026-08-11

## The harness was broken twice, then fixed

| stage | bias vs broker truth | sign agree | median err |
|---|--:|--:|--:|
| v1 `replay_fill` (first-exit) | **+$19,454 on the paired ladder A/B** | — | — |
| v2 multi-leg, no SPY feed | +$5,949 | 82% | $27 |
| v3 + SPY feed | +$2,051 | 90% | $13 |
| **v4 + SPY feed + 2c slippage + mixed fills** | **+$384** (+$2.11/pos) | **90%** | **$14** |

Anchor: 182 real positions, each fed **the config it actually traded**, compared to real broker
P&L. n=182, actual −$526 vs replay −$142.

**Hold-time bias, the one that poisoned every exit A/B:**

| | v2 | v4 |
|---|--:|--:|
| positions held too long | 87 (median +21 min) | **32** |
| timing-matched | 20 (11%) | **51 (28%)** |

Root cause of the big one: with no SPY feed, structure/ribbon exits cannot fire, so the walk
holds past the exits that actually end our trades. Since every exit change is a hold-longer
hypothesis, the harness approved them regardless of merit. Calibration = `fill_mode="mixed"`,
`spy_closes` fed per day, `slippage=0.02`.

## What the calibrated harness says about the ladder

n=182 positions / 22 days, paired ON−OFF:

- effect **−$1,662**, mean **−$76/day**, helped **4/22 days**, drop-best **−$2,718**
- bootstrap **p = 0.28 → not significant in either direction**

**But the mechanism is clean and regime-split:**

| cohort | n days | ladder effect | OFF → ON |
|---|--:|--:|---|
| LOW ER30 <0.35 (chop) | 6 | **+$702** (mean +$117) | −$4,218 → −$3,516 |
| HIGH ER30 ≥0.35 (trend) | 16 | **−$2,364** (mean −$148) | +$4,077 → **+$1,713** |

The ladder floor **saves give-back on chop days and cuts runners on trend days** — precisely
what a profit floor does. Worst two: 07-29 −$1,554 and 08-04 −$1,586, both high-ER trend days.
Best: 08-05 +$1,056, 08-06 +$700, 08-10 +$490, all chop/reversal.

## The regime discriminator (ER30 = |net move| / range, first 30 min)

n=29 days with engine P&L:

| cohort | n | total | mean | days +ve |
|---|--:|--:|--:|--:|
| LOW ER <0.35 | 8 | **−$2,336** | −$292 | **1/8** |
| HIGH ER ≥0.35 | 21 | +$716 | +$34 | 7/21 |

Skipping the 8 chop days turns the book from −$1,620 to +$716.

**Honest limits:** 08-06 is a false negative (ER 0.29, yet +$1,465 — our 3rd best day). The
high-ER cohort is only 7/21 positive, so ER is a **LOSS FILTER, not an edge predictor**. n=8 in
the low cohort is thin. The day-archetype library cannot substitute — 08-04 and 08-07 are both
`gap-go` with near-identical gap and prior ATR; every field that separates them is whole-day
(look-ahead).

## Standing conclusion

Two independent, mechanism-consistent findings point the same way:
1. **ER30 low → the engine loses** (1/8 positive days).
2. **The ladder helps exactly on those low-ER days and hurts on high-ER days.**

Neither is individually significant at n=6–8 days. Together they describe one coherent
mechanism: **the engine's edge is trend-dependent, and the correct exit shape is
regime-dependent.** That is a hypothesis with a pre-registration and a forward shadow, not a
knob to turn tonight.
