# LESSON CANDIDATE: an intra-session P&L window is not evidence for a mid-session revert proposal

**Date:** 2026-08-04 (live session, ~09:57 ET call / retracted same session)

**Symptom:** At 09:57 ET I observed `risky-3` logging `ENTER_BULL` on seven ticks in
eleven minutes (09:46/48/49/50/53/54/57), all `vwap_continuation` C (BASE), all with
`trigger_level=None`. The first four round-tripped for **-$289 in under 2 minutes each**.
I called this "a defect losing money" and stated I would stage `RUN_VWAP=False` — a
mid-session revert of a setup that had shipped the previous evening. I then retracted the
call. Both the alarm and the retraction were made under time pressure, on the same
11 minutes of evidence.

**What the full day actually showed (broker-verified, close of 2026-08-04):**

- The FIFTH fire of that same cluster (09:57 @ 1.40) became the trade of the day
  (out 1.99 / 2.25).
- `VWAP_CONTINUATION` closed the day at **10 legs, +$721.00** across risky-1 + risky-3
  (`journal/trades.csv`, ET day 2026-08-04) — its first live fleet session, net positive.
- `risky-1` took the same signal only 3x on a tighter gate and made **+$1,039.54**,
  the best arm of the day.

Had the 09:57 revert shipped, it would have disarmed a setup that finished the session
**+$721** on the strength of a fire that had not yet happened when the call was made.

**Root cause of the bad call:** I used *realized P&L over an 11-minute window* as the
decision statistic. That statistic is dominated by the fact that losers resolve FAST and
winners resolve SLOW. Four sub-2-minute round-trip losses and one 7-minute-old open
position is exactly what a working trend-continuation setup looks like at minute 11 —
the losses have printed and the winner has not. Reading the partial sum as "the setup is
losing money" is a **survivorship artifact inverted in time**: the sample is censored at
the moment of measurement, and the censoring is correlated with the sign of the outcome.

**Why the retraction was ALSO not a good process step:** I retracted on judgment, not on
a stated threshold. An alarm raised on bad evidence and withdrawn on vibes leaves no
record of what *would* have justified the revert, so the next session inherits nothing.
Retracting a wrong call is correct; retracting it without writing down the rule is not.

**Generalizable pattern / proposed rule — MID-SESSION REVERT EVIDENCE BAR.**
No mid-session revert of a shipped, pre-registered setup may be proposed on intra-session
realized P&L alone. A mid-session revert proposal requires ONE of:

1. **A mechanism defect, not a P&L defect** — the setup is doing something it is not
   specified to do (wrong side, wrong instrument, ignoring a gate, entering while not
   flat, sizing past the risk cap). This is verifiable in one tick and needs no n.
   *This is the only same-day-actionable trigger.*
2. **A kill-switch / risk-cap breach** — already covered by Rule 5 / Rule 6 and fires
   deterministically without my judgment.
3. **Otherwise: no mid-session action.** P&L-based disarm decisions wait for the close
   and go through the setup's own pre-registered kill criterion (e.g. the SHIP-B
   `block_elite_bull` form: *n ≥ 10 fills/arm* or *N sessions net negative*).

Corollary: censored-window P&L must never be quoted to J as a verdict during RTH. If it
is mentioned at all it is labelled **PARTIAL / CENSORED** with the count of still-open
positions, because open positions are the winners-in-waiting that the sum omits.

Corollary 2: Rule 9 ("no mid-session rule changes") already forbids the *action*. The gap
this lesson patches is that it did not stop me from forming and voicing the *conclusion*,
which is what a future session would have acted on.

**Cross-reference:** the same censoring logic is why C1 ("real fills is the only WR
authority") insists on completed round trips — a partial window is not a small sample, it
is a *biased* one.

**Status:** lesson candidate only. The 7x-re-entry question itself (is the cluster a
defect on its own merits, independent of that day's P&L?) is being adjudicated separately
on real fills + real OPRA and is NOT resolved by this item — this item is only about the
evidence threshold that should gate a mid-session revert proposal.
