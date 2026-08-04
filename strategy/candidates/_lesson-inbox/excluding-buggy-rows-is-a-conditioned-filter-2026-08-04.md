# LESSON CANDIDATE: deleting a bug's rows from a historical sample is a CONDITIONED filter, not a clean baseline

**Date:** 2026-08-04 (self-caught, same day, auditing commit `41753b9c` which I shipped
that morning at 09:55 ET)

**Symptom:** Commit `41753b9c` fixed a real bug (the crypto-twin ladder-sim omitted
`time_stop_et` from its `plan_exit_actions` call, so `exit_manager`'s SPY-shaped 15:50 ET
default force-closed positions on a 24/7 BTC instrument). Having fixed it, I re-baselined
the ladder A/B by **excluding every historical `stage == time_stop` close** and reported
the result as "the corrected totals":

> variant n=244→74 (WR 23.0%, **+1.1044%**), baseline n=267→43 (WR 4.7%, **+0.5745%**)

Both lanes positive; variant ahead. That number is in the commit message and in
`analysis/deep-research/EOD-2026-08-03-TWIN.md`.

**What the first genuinely post-fix data showed (same day, 13:55Z→20:00Z):**

| Slice | variant | baseline |
|---|---|---|
| Pre-fix, `time_stop` excluded (what I reported) | n=74 WR 23.0% **+1.1044%** | n=43 WR 4.7% **+0.5745%** |
| **True post-fix window** ⚠ SMALL-n | n=10 WR **0.0%** **-0.3919%** | n=11 WR **0.0%** **-0.4136%** |

Sign flip in both lanes. n=10/11 is far too small to be a verdict — that is not the
lesson. The lesson is that I presented the exclusion-reconstruction as if it were
equivalent to clean data, and it is not.

**Root cause — the exclusion is correlated with trade duration.** The bug's real shape is
worse than "a 15:50 bleed": `exit_manager` closes when *now ≥ 15:50 ET*, which on a 24/7
instrument is TRUE from 15:50 ET until midnight ET. Confirmed empirically — UTC hours that
ever produced a `time_stop` are `[19,20,21,22,23,0,1,2,3]` and hours `[4..18]` **never**
did. That is an **8h05m/day dead zone (34% of every day)** in which no ladder position
could survive.

Therefore `stage == time_stop` was not a random contaminant. It selected:

- every trade that lived long enough to still be open when the dead zone opened
  (i.e. **the longest-held trades**), and
- every trade entered *inside* the dead zone (killed on its first management tick).

Dropping those rows leaves a sample **conditioned on short duration and on entering
outside a specific 8-hour window**. For a trend-continuation ladder whose thesis is that
winners need time, removing the longest-held trades is removing the population the
strategy is supposed to profit from. The surviving +1.10% is a statement about fast
resolvers, not about the strategy.

**Why I did not catch it in the moment:** I verified the *fix* rigorously (guard test
RED-proofed by live revert-and-rerun, correct kwarg, mirrors the live path) and then
treated the re-baseline as bookkeeping. The fix was engineering; the re-baseline was
**statistics**, and I applied engineering-grade care to one and none to the other.

**Generalizable pattern / proposed rule — BUG-EXCLUSION IS A SAMPLE DECISION.**
When a bug is found in a producer of historical results, you may not silently drop the
affected rows and call the remainder a baseline. Required instead:

1. **Characterize the bug's selection function before excluding anything.** State in one
   sentence *which trades the bug could touch*, as a property (duration ≥ X, entered in
   window W, side S). If that property correlates with the outcome, exclusion is biased —
   say so.
2. **Report the exclusion-reconstruction and the true post-fix window as SEPARATE, LABELLED
   rows,** never merged, with the post-fix n stated even when it is embarrassing
   (n=10 here).
3. **Prefer re-running the producer over filtering its output** whenever the inputs still
   exist. The ladder sim is deterministic on stored bars; re-simulating the affected span
   under the fixed code was available and is strictly better than deleting rows.
4. **Never quote an exclusion-reconstruction as "corrected."** Call it what it is: a
   *survivorship-filtered reconstruction*, pending clean forward data.

**Disposition of the bad number:** the `+1.1044% / +0.5745%` figures in commit `41753b9c`
and `EOD-2026-08-03-TWIN.md` should be relabelled *SURVIVORSHIP-FILTERED RECONSTRUCTION —
do not cite as a clean baseline*, alongside the post-fix small-n rows. The underlying code
fix is correct and stays (verified organically — see below); only the re-baseline claim is
overstated.

**Credit where due — the fix itself IS proven, organically:** both ladder lanes entered
18:05:15Z and were still open past 20:00Z, riding straight through the 19:50Z (15:50 ET)
dead-zone boundary that would previously have force-closed them; post-fix `LADDER_CLOSED`
stages are `structure_stop` ×21, `time_stop` ×0; last `time_stop` in the entire file is
`2026-08-04T03:30:16Z`, before the fix landed.

**Cross-reference:** C4 (disclose concentration, normalize OOS, stratify by regime);
C6 L251 (diff parity gaps PER-TRADE by terminal stage, not aggregate $/tr — the same
"terminal stage is not random" insight, here applied to exclusion rather than comparison);
`/fable-too-good` (a re-baseline that turns a bug into two positive lanes is exactly the
shape that protocol exists to catch — and I did not run it).
