---
kind: lesson
theme: C4 (disclose concentration, normalize OOS) + C27 (detectors that measure noise)
date: 2026-08-20
source: analysis/deep-research/MULTI-LANE-STAGE-A-VERDICT-2026-08-20.md
---

# When a signal fails a null gate, the FIRST rebuttal is always "wrong timeframe" — test it once, then the excuse is spent

**Symptom.** The weekly lane's level-interaction + structure-shift trigger failed its null gate
on five cuts (2026-08-18). The leading rebuttal — reasonable, and worth one test — was that the
signal was fine but the *expression* was wrong: a 1H trigger held for multiple days is a
timeframe mismatch with a trigger designed for a 5-minute intraday engine. That hypothesis
justified an entire six-work-package programme to rebuild the trigger on its native timebase.

**What happened.** The rebuild was done properly: 5-minute bars, full context parity (real VIX
and its MAs, HTF-15m stack, persistent per-symbol level-state memory), 9 symbols, a frozen
pre-registration written before the harness ran once. It produced **7,489 signals — 149× the
pre-registered minimum** — and **failed the random-entry null at every horizon**, hit rate
49.1–49.4%, 2 of 9 symbols positive.

**Root cause of the original null: the trigger, not the expression.** The transplant carried
absolute-move information (+7.6 to +12.6% lift) and zero directional information. It marks
"something is about to move" without saying which way — and a direction-blind signal expressed
as long directional premium loses the spread and the theta every time.

**The lesson, which is about EPISTEMICS, not this signal.**

1. **A null result's most attractive rebuttal is a confound, and confounds deserve exactly one
   properly-powered test.** Timeframe mismatch was a real, falsifiable alternative explanation.
   Testing it was correct. What would NOT be correct is generating a third variant of the same
   excuse ("wrong hold model", "wrong strike", "wrong regime filter") after two independent
   nulls on different timebases with different hold models. **Two independent kills close the
   family.** At that point the burden flips: the next test needs a new MECHANISM, not a new
   parameterization of the dead one.

2. **Power the confound test hard enough that its own null is decisive.** 463 signals invited a
   "small sample" rebuttal. 7,489 does not. When you spend a programme testing a confound,
   over-power it deliberately — the whole point is to *end* the argument, not to add a data
   point to it.

3. **Pre-commit to the volatility-vs-direction distinction BEFORE looking.** The prereg named
   "significant abs-move lift with insignificant signed return = volatility detector = NOT a
   pass" in advance. Without that clause written first, a +12.5% abs-move lift is exactly the
   shape of result a motivated reader converts into a pivot ("we found a straddle strategy!").
   The weekly lane already proved that reading can be a single-symbol artifact.

4. **Separate the transplant's verdict from the original's.** SPY appeared in the failing sample
   at −0.007% — but that was the FORKED scoring on 5m bars with lane-computed levels, not the
   production engine with curated levels, trendlines and multi-day memory. A null on a transplant
   is evidence about the transplant. Letting it contaminate the original's ledger (in either
   direction) is evidence-blending.

**Guard-shaped takeaway.** Any pre-registration for a signal family that has already failed a
null gate once must state, in the prereg itself, **what result would close the family** — and a
second independent null on a different timebase should be the default answer.
