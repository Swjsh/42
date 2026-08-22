# Lesson Inbox — a hand-curated allowlist drifts stale without a maintenance trigger

**Routed by:** conductor (WEEKEND) 2026-08-22
**Category:** producer/consumer contract, OP-22 compound-not-accumulate

## The finding

`prospector.py`'s `FAMILY_KEYWORDS` concept-family dedupe was built 2026-07-22
specifically to stop the free-swarm prospector beat from re-promoting the same
idea under fresh LLM wording every few days. It shipped with exactly 2 families
(`vix1d`, `volume_profile`) and an explicit comment: "extend this dict whenever
a new duplicate family is caught." Nobody extended it. By 2026-08-22 (31 days
later) the chef-inbox backlog had grown to 106 open items, oldest dated
2026-07-10 (43 days stale) — 69 of which reduced to 27 NEW duplicate families
(TRIN, NYSE TICK, DXY, ORB, gap-fill, turn-of-month, VWAP reversion, the 10Y-2Y
spread, max pain, put/call ratio, IV skew, COT positioning, market
profile/TPO, FRED macro, WSB sentiment, auto support/resistance, harmonic
patterns, order-flow/cumulative-delta, FINRA short volume, credit spreads, EIA
crude inventory, WTI price, CME open interest, futures curve/basis, lunch-lull,
advance-decline, dealer gamma exposure, IEX Cloud) that the allowlist should
have caught but structurally could not, because it only ever knew about the 2
families present the day it was written.

**Why this is a distinct lesson from "the fix was too narrow" (obvious in
hindsight):** the fix's own doc comment correctly predicted its own staleness
("extend this dict whenever a new duplicate family is caught") and named the
exact maintenance action needed — but named it as a MANUAL trigger with no
owner and no cadence. A fail-open guard that depends on someone noticing and
extending it by hand is not a guard, it's a to-do note with better formatting.
The same author inbox (chef-inbox) was ALSO independently starved for an
unrelated reason: conductor STAGE 1 priority order puts author inboxes at
tier 5, so 30+ consecutive fires (2026-07-23 to 2026-08-21) always found a
higher-priority item and never reached the chef-inbox at all — meaning even a
perfectly-maintained allowlist would not have been RUN against the backlog
until this fire.

## Generalizable guidance

1. **A hand-curated allowlist that gates a recurring producer needs either (a)
   a periodic drift check (a test/report that counts un-familied duplicates
   above some threshold and fails/flags), or (b) an owner + cadence, not just a
   comment asking nicely.** Prose that says "extend this whenever" is doctrine,
   not enforcement — the same OP-25 principle already applied to code
   assertions applies to allowlists.
2. **A low-priority queue tier (STAGE 1 priority-5 "author inboxes") can starve
   indefinitely if higher tiers are never empty.** Worth watching whether this
   recurs elsewhere (skill-inbox, validator-inbox) — those inboxes happened to
   stay near-empty because their upstream producers are lower-volume, but the
   STRUCTURAL starvation risk is the same for any tier-5+ item.
3. **QA any new keyword-substring guard against short/generic strings before
   trusting it.** Three real false positives were caught during THIS fire's own
   QA pass before the fix was applied: bare `"trin"` matched inside
   "doc**trin**e"; bare `"cme group"` matched a boilerplate "Data source: CME
   Group..." attribution line in an unrelated item; a broad
   `"10-year treasury yield"` phrase pulled a generic FRED-macro item into the
   narrower 10Y-2Y-spread family. All three were substring collisions with
   PROSE, not with the concept being matched — the failure mode for any
   plain-substring (non-regex, non-word-boundary) text match.

## Fix applied this fire (not proposed, already shipped)

`setup/scripts/prospector.py` `FAMILY_KEYWORDS` extended 2 -> 31 families;
`backtest/tests/test_prospector.py` +28 assertions (`test_idea_family_matches_new_2026_08_22_families`);
one-time retroactive consolidation applied to the real backlog (106 -> 37 open
items, 69 folded with fold-notes). Does not yet address guidance #1/#2 above
(the drift-detection / starvation-prevention mechanism) — that is the
still-open, undone part of this lesson for a future fire or lesson-author to
turn into a graduated guard (e.g. a `self_check.py` check that warns when
`_chef-inbox` open-item count exceeds N, or a periodic un-familied-duplicate
scan).
