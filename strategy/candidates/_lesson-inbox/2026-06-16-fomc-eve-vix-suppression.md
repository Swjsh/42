# Lesson: FOMC-eve VIX suppression — filter_8 is a friend, not an obstacle

> Queued by Analyst 2026-06-16.

## Symptom

2026-06-16: Bear score 8-9/10 sustained from 10:33 ET to 15:00 ET. SPY fell ~$4.77 from session high to low. Engine took 0 trades. Without context, this looks like a missed day.

## Root cause

FOMC Day-1 sessions trigger institutional hedge-stripping: dealers who are long volatility (puts, VIX calls) unwind those positions the day before a binary event (rate decision) they expect to be benign. This mechanically suppresses VIX even when the underlying drifts lower. Result: "price down / VIX down" — the inverse of the normal correlation.

Filter_8 (VIX ≥17.30 AND rising) blocked all bear entries. VIX was 15.82–16.16 all session, 140bps below gate.

## Why filter_8 was CORRECT here

A declining VIX on a declining SPY day means:
1. IV is being compressed — any bear put bought at 16.0 IV will see further IV compression dragging against the position
2. The fear premium that makes 0DTE puts valuable is absent
3. Premium decay (theta) runs against the position in both directions
4. Any stop hit would occur at a premium already depressed by falling IV

Entering a bear position in this regime would have worse fill quality, wider bid-ask spreads, and elevated theta-vs-delta risk. The VIX gate protecting against this is correctly calibrated.

## Fix

No parameter change. Doctrine encoding only:

**When reviewing EOD digests or pattern mining:** a day with high bear scores + 0 trades + VIX declining is NOT a miss. It is the engine correctly abstaining from a low-premium, high-theta-drag environment. Do not flag these as "missed opportunities."

**For hypothesis grading:** add category `FOMC_EVE_VIX_SUPPRESSION` to hypothesis-grades.jsonl tracking. Track whether the prediction "0 trades is correct on FOMC Day-1 + VIX declining" validates over multiple FOMC cycles.

**Cross-reference:** L73 (VIX character > VIX level), L93 (BEARISH_REVERSAL fires in declining VIX for mean-reversion; bear continuation in declining VIX is a different and weaker setup).

## Encoded in

- `analysis/eod/2026-06-16.md` — Pattern observations section
- `journal/2026-06-16.md` — EOD reflection
- This lesson file
- (Proposed) `docs/LESSONS-LEARNED.md` — add as L113 or next available

## Candidate lesson number

L113 (pending LESSONS-LEARNED.md append by Lesson Author persona)
