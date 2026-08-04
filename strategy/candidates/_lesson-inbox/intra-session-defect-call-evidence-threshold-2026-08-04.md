# LESSON CANDIDATE: an intra-session P&L window is not evidence for a mid-session revert proposal

**Date:** 2026-08-04 (live session, ~09:57 ET call / retracted same session)

**Symptom:** At 09:57 ET I observed `risky-3` logging `ENTER_BULL` on seven ticks in
eleven minutes (09:46/48/49/50/53/54/57), all `vwap_continuation` C (BASE), all with
`trigger_level=None`. I read that as seven entries losing money, called it "a defect
losing money", and stated I would stage `RUN_VWAP=False` — a mid-session revert of a
setup that had shipped the previous evening. I then retracted the call. Both the alarm
and the retraction were made under time pressure, on the same 11 minutes of evidence.

**FIRST ERROR — the trigger count was wrong, and the disproof was in the same row.**
Only **FOUR of those seven rows were PLACED**. 09:48 / 09:49 / 09:53 carry
`placement.placed=false, reason=SKIP_DUPLICATE_CLAIM`. `action` is written as
`ENTER_BULL` even when placement is refused, so counting `action` rows overstates
entries — here by **75%**. `placement.placed` sits in the *same JSON object* as
`action`. This was not a judgment failure; it was a field that was never read.

**What the full day actually showed (broker-verified + real OPRA, close of 2026-08-04;
full adjudication in `analysis/deep-research/EOD-2026-08-04-REENTRY.md`):**

- The **4th placed** entry of that cluster (09:57 @ 1.40 — the 7th decision row, not the
  "fifth" as originally written here) became the trade of the day: **+$524.00**.
- The three placed round trips before it lost **-$288.00** combined.
- `VWAP_CONTINUATION` closed the day at **10 legs / 7 round trips, +$721.00** across
  risky-1 + risky-3 — its first live fleet session, net positive.
- **CORRECTION (was wrong here):** `risky-1` took the signal **2x, not 3x**, and its gate
  is **`gate_override.full_send=true` — the LOOSEST gate in the fleet**, not a tighter
  one (risky-3 is `min_triggers:1`). Its **+$1,039.54 was the whole-day figure**; its
  actual `vwap_continuation` P&L was **+$565.00**. Attributing the day number to this
  signal overstated the case.
- risky-1 did not *decline* the later signals — it was **holding a position and was not
  flat**, so re-entry was structurally impossible. The re-entry difference was never an
  entry-gate difference.

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

**Third failure — the proposed action did not follow from the diagnosis even if the
diagnosis had been right.** `RUN_VWAP=False` disarms the **entry producer**. The
mechanism driving the cluster is the **exit**: `vwap_continuation` carries
`premium_stop_pct=-0.06`, and its `stop_mode="structure"` patch is a guaranteed **no-op**
because `exit_manager.ExitState.from_entry` requires `trigger_level is not None` — which a
continuation setup never has. So every position ran a raw **-6% premium stop** against a
**10.3% median 1-min noise band** (93% of individual minutes had a range wider than the
stop itself). The arm re-entered because it kept being *returned to flat* by a stop
narrower than the instrument's noise. Killing the signal to fix a stop is a category
error — and it would have removed the winners along with the churn.

**Generalizable pattern / proposed rule — MID-SESSION REVERT EVIDENCE BAR.**
No mid-session revert of a shipped, pre-registered setup may be proposed on intra-session
realized P&L alone. A mid-session revert proposal requires ONE of:

1. **A mechanism defect, not a P&L defect** — the setup is doing something it is not
   specified to do (wrong side, wrong instrument, ignoring a gate, entering while not
   flat, sizing past the risk cap). This is verifiable in one tick and needs no n.
   *This is the only same-day-actionable trigger.*
   **1a. COUNT PLACED, NEVER LOGGED.** Any claim of the form "it fired N times" must be
   sourced from `placement.placed == true`, never from the `action` field. A decision row
   records what was *decided*, not what was *executed*; the two differ by every
   `SKIP_*` reason. State the placed count and the logged count separately or not at all.
   **1b. NAME THE MECHANISM BEFORE NAMING THE FIX.** A proposed revert must identify which
   component is misbehaving and the proposed change must act on *that* component. Disarming
   an entry producer for an exit-side pathology is not a fix, it is a guess with side
   effects.
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

**Status:** lesson candidate. The re-entry question itself is now **ADJUDICATED** —
`analysis/deep-research/EOD-2026-08-04-REENTRY.md` (2026-08-04 after the close, real
broker fills + real OPRA). Verdict: **(c) underpowered — do NOT arm a re-entry cooldown**.
Every cooldown cell loses money on today's real fills (best cell -$456 vs live; the 10-min
cell that "wins" for risky-3 alone survives only in a 2-minute-wide window and is a
single-day artifact). risky-1's +$640 winner — the arm nominated as the well-behaved
control — was itself a **4-minute re-entry**, and it survived its stop by **0.34 cents**.
The 24-day population points the other way (tight re-entries bled -$846 ex-today with a 0%
rescue rate), and the cooldown sweep is non-monotonic across the grid. Two opposite
signals at n=1 trend day. The recommended work is a **stop-width A/B**, pre-registered
only, nothing armed.

**Revision note:** this item was written during/after the session and originally carried
three factual errors (entry count, the "fifth fire" ordinal, and "risky-1 … tighter gate"
plus its whole-day P&L attributed to one signal). Corrected in place 2026-08-04 after the
close against the decision ledgers and broker fills. The count error has been promoted
into the rule body (1a) because it is the reusable failure: **the alarm's urgency came
from a number that a single unread field in the same row would have corrected.**
