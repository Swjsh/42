# LESSON CANDIDATE: "validated" describes a backtest; only a fill proves the code path runs

**Date:** 2026-08-04 (found auditing my own 2026-08-03 report)

**Symptom:** On 2026-08-03 I reported the vwap lane as shipping "a validated edge." The
setup had a real pre-registration and a real A/B behind it. What it did **not** have was
any evidence that the code path could execute at all: `vwap_continuation` emission had
been **import-dead since 2026-06-25** on the fleet lane and produced **zero rows in
3,865**. 2026-08-04 was its first-ever live fleet session. I described a never-executed
code path in the vocabulary of a proven one.

**The sharper version of the error (found today, and it makes the original claim worse
in one direction and better in another):**

`vwap_continuation` was **not** a setup with no live history. It had live history, and it
was bad:

- CORE lane, real broker fills: **7 live trades, 0% WR, -$204** (07-16, 07-21, 07-22).
- It was **DISARMED on 2026-07-25**, J-approved, for exactly that record
  (`params.json#_extra_setup_exec_armed_disarm_doc_2026_07_25`).
- Then on 2026-08-03 the **fleet** emission path for the same setup name was un-deadened,
  and on 2026-08-04 it traded 10 legs for **+$721** on risky-1/risky-3.

So the honest statement is not "first ever live" and not "validated edge." It is: *a
setup name that was disarmed on one lane for 0/7 and -$204 was re-activated on a
different lane, in a different risk shell, and had a good first day.* That may well be
legitimate — different arm, different strike tier, different exits, and C29 says cells do
not transfer across strike tiers — but it is a **materially different claim** than the one
I made, and it carries a prior that I omitted entirely.

**Root cause:** two distinct failures compounding.

1. **Vocabulary collapse.** "Validated" (a property of a backtest) was used where
   "armed" (a property of config) and "exercised" (a property of production) were the
   load-bearing facts. A setup can be validated, armed, and still structurally incapable
   of firing — which is precisely what an import-dead emitter is.
2. **Lane-blind provenance.** I checked whether *this lane* had fills. I did not check
   whether the *setup name* had fills anywhere else. The disarm doc recording the
   0/7 / -$204 history was sitting in `params.json` the whole time.

**Generalizable pattern / proposed rules.**

**(a) Three-state vocabulary, never collapsed.** Every setup carries three independent
facts and a report must not substitute one for another:
| State | Means | Proven by |
|---|---|---|
| VALIDATED | clears the backtest bar | pre-reg + A/B scorecard |
| ARMED | config would route an order | the params key |
| EXERCISED | the path actually ran in production | **a real broker fill** |

**(b) FIRST-LIVE SHADOW SESSION (proposed, needs J or an auto-ratify decision).** A setup
whose code path has **never produced a live fill** is not in the same risk class as one
with a live record, regardless of backtest strength — an unexercised path can be
import-dead, mis-wired to the wrong exit shape (the 2026-07-02 vwap_continuation bug and
the 2026-07-18 gap_and_go bug were both exactly this), or emit at the wrong cadence.
Proposal: the first session after un-deadening runs **shadow/log-only**, and arming
requires only that the emitter demonstrably fired — a one-session cost that buys proof
the path is alive before it can lose money. *Counter-argument to weigh, not dismiss: on
paper, J's standing bias is toward TAKING the trade (2026-07-31 recency memo), and a
shadow session costs a live day of learning. This is a genuine trade-off and should be
decided explicitly, not defaulted.*

**(c) LANE-BLIND PROVENANCE CHECK (no trade-off, ship it).** Before describing any setup
as new/first-live, grep the setup NAME across `journal/trades.csv` and every
`extra_setup_exec_armed` disarm doc. If the name has prior live fills on any lane, the
report must quote that record — including a negative one — next to the new claim. This is
cheap, mechanical, and would have caught today's error outright.

**Cross-reference:** C7 (silent success is failure — audit outputs, not exit codes);
C14 L234 (an arm-scope filter can go synthetic-by-omission when the live lineup moves on);
C35 (built+tested ≠ shipped). This lesson is the entry-side sibling: **armed ≠ exercised.**
