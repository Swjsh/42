# Lesson: a standing "want" is an unverified CLAIM, and this repo let three run for weeks

**Symptom.** J, reading the command center's I-WANT section: "why do I need to rotate the key?
It's a fucking training [account]. Can you just use it? Shut up about it."

**What was actually true.** The priority-1 want had read, for ~8 weeks:
"Rotate the Tastytrade PROD tokens (owed since 06-22) — it unlocks mes-mnq-div, a validated
+$71/trade futures edge that's been parked for 6 weeks."

Every clause was false:
1. **Wrong broker.** `accounts.json`'s `key_ref: "docs/futures/ (TT sandbox wiring)"` means
   **Trading Technologies**, not Tastytrade. The two got conflated into the want text.
2. **Not PROD.** The Tastytrade account in play (5WW73759) is a sandbox.
3. **Nothing to unlock.** The TT-credential dependency was RETIRED 2026-07-18 when
   `futures_edge3_sim.py` replaced it with an own-book SIM lane.
4. **Not parked.** That lane has run since 2026-07-20 — 30 fills, 10 closed round trips,
   +$376 / +$37.60 mean, rail PENDING_MORE_DATA at 10/20.

**Root cause.** A want is a *claim about the world* that gets re-rendered every fire without ever
being re-tested. Nothing in the pipeline ever asked "is this still true?", so a claim that was
wrong on the day it was written survived two months of daily display — on the ONE surface built
to be the thing J trusts without checking.

**Second-order failure (mine, same thread).** Asked to fix it, I "corrected" the want twice and
was wrong both times — blaming sandbox futures approval, then futures buying power. Both times
the probe JSON I was quoting from contained `dry_run_ok: true`, `errors: null`,
`verdict: H2_SESSION_ARTIFACT` (10/10 runs across 11 days). **I trusted a descriptive account
FIELD over the FUNCTIONAL test printed next to it** — the C11 lesson ("broker behaviour is the
source of truth, not the account object's self-description") applied to my own reading. And I
never opened the arm's own module docstring, which states the retirement in its first paragraph.

**Fix shipped.**
- Wants now carry `verified_at`; the command center badges anything unverified >14 days as
  "⚠ unverified since <date>" (RED-proofed: stale date → True, missing date → True, today → False).
- Wants may carry a `verify_cmd` that PROVES the blocker still exists.
- Three wants retired with their reasoning recorded in `gamma-wants.json._retired`.

**Rule.** Before surfacing a want, re-verify its claim — preferably by running something. A want
whose blocker cannot be demonstrated on demand is not a want, it is a rumour. And when an
instrument has already emitted a verdict, READ THE VERDICT before re-deriving one from its raw
fields.
