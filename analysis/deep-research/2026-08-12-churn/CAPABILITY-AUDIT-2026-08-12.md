# The Capability Audit — what the engine cannot even SAY (2026-08-12 night)

> **Why this exists.** J: "Everything that was an issue today seems like a very obvious thing
> that should have been caught in an audit… take the thinking philosophy that allowed us to
> discover this and run it across the engine. Find our unknown unknowns."

## Why no audit ever caught "it can't sit out" — three reasons, stated honestly

1. **Every audit we run is a CONFORMANCE audit** — "does X behave as specified?" On 08-12
   every conformance check PASSED: 38/38 exits fired from named stages, orders reconciled,
   guards held, zero error rows. **A missing capability produces no failing test, no RED
   status, no anomaly — it produces plausible-looking activity.** Conformance audits can only
   inspect code that exists.
2. **Participation was the explicit goal of the paper phase — anti-participation machinery was
   legislated AGAINST, not merely unbuilt.** The repo contains THREE separate mechanisms whose
   entire purpose is converting silence into trades: the PROBE arm (J 07-10: "6 arms and
   nothing took a trade... why isn't 1 arm set to take riskier trades?"), the SCORE LADDER
   (J 07-27: "the riskiest arm can hop in at a seven out of ten"), and FULL-SEND (J 07-31:
   "we should just be getting in shit and seeing if it works"). Each was reasonable for a
   learning fleet. Their sum is an engine with a whole subsystem for finding MORE reasons to
   trade and zero vocabulary for declining. This was not an oversight; it was the accumulated
   result of participation-seeking directives — which means going live requires deliberately
   REVERSING a posture, not patching a bug.
3. **The 5-arm aggregate hid per-decision quality.** 38 entries/day read as "learning rate"
   (FULL-SEND's own doc literally prices its negative P&L as the COST of learning rate).
   Nobody stares at one account's 8 entries and asks "would a human have taken these?" when
   the book is framed as an experiment matrix.

## The method (so it can be re-run, not just admired)

Enumerate the decision inventory of a disciplined discretionary 0DTE trader — every distinct
judgment they make in a session. For each, ask ONE question: **does any component in the
engine have the vocabulary to express this decision?** Not "does it work" — "can it be said
at all." Gaps are unknown unknowns by construction: nothing that exists refers to them.

## The register — 17 human decisions vs the engine

Status: ✅ EXISTS · 🟡 PARTIAL (exists but not on the decision path, or wrong shape) ·
❌ ABSENT (no vocabulary). Verification: each ❌ was grep/code-verified tonight, not recalled.

| # | human decision | engine status | evidence |
|---|---|---|---|
| 1 | "What KIND of day is this?" (trend/range/event) | ❌ | only trend logic exists; ER30 shadow + context_bundle + market_structure all LOGGED-ONLY, nothing on the decision path reads them |
| 2 | "Is there an event today?" (CPI/FOMC) | ❌ | 0 matches for calendar terms in heartbeat_core.py; calendar was built for the retired LLM heartbeat, never ported |
| 3 | "This is a RANGE — trade edges or stand down" | ❌ | tonight's finding: ribbon is a trend gauge working correctly; no range mode exists, so range days become 38 false trend-triggers |
| 4 | **"No setup worth taking — sit out"** | ❌ | THE 08-12 finding. No conviction floor, no trade budget, no no-trade-day verdict |
| 5 | "I got my one good trade — done for the day" | ❌ | grep-verified: no daily profit lockout anywhere; the kill switch is loss-only |
| 6 | "Wrong about the same idea 3× — stand down that thesis" | ❌ | 11 structure-stopped CALLS in 3 waves across 4 arms; nothing counts consecutive same-direction failures (C31's live sibling) |
| 7 | "We're at the TOP of the 3-day range — longs need extra conviction" | ❌ | levels stored individually; no position-in-range modifier on scoring |
| 8 | "Third rejection at the same shelf = rising conviction" | 🟡 | G11 merges multi-day levels but no repeat-touch scoring |
| 9 | "Size up on A+ setups, down on B setups" | 🟡 | quality tiers gate entries but barely shape size; recency clamp is book-level backward-looking, not per-setup conviction |
| 10 | "The reason I entered is gone — leave" (thesis invalidation) | 🟡 | ribbon_flip IS a thesis check but contradicts the entry's own waiver (bug #1); no other trigger-condition re-check exists |
| 11 | "It's not doing what it should — leave" (stagnation exit) | ❌ | grep-verified: no stagnation/thesis-decay exit; only hard 15:50 time stop. (Note: exit knobs measured wash-or-worse this week — this is absent VOCABULARY, not a promised edge) |
| 12 | "First trade's result updates my read of the day" | ❌ | decisions are memoryless tick-to-tick; only cross-DAY memory is the recency clamp |
| 13 | "Am I overtrading right now?" | ❌ | PDT inert on fleet arms (`pdt_enforced: false`, `day_trades_true: 12`); no budget of any kind |
| 14 | "Each trade costs ~$8 friction — is the edge bigger than the toll?" | 🟡 | NBBO capture exists for LOGGING; nothing gates entry on cost-vs-edge; min_entry_premium is a crude proxy |
| 15 | "Is my data feed lying to me?" | ✅ | SKIP_STALE_SIGHT / staleness guards — present and firing |
| 16 | "Never add to a loser" | ✅ | NOT_FLAT one-position rule, guard-pinned (C31) |
| 17 | "All out by close" | ✅ | EOD flatten 15:50/15:55, verified daily |

**Score: 3 ✅ · 4 🟡 · 10 ❌.** The engine's vocabulary covers execution hygiene almost
perfectly and trade JUDGMENT almost not at all. That is the precise shape of "a Python script
rapid-firing trades" — J's phrase is the audit's conclusion.

## The merged queue (gaps + open bugs, ONE list — no parallel piles)

| rank | item | why this rank | size |
|---|---|---|---|
| 1 | **Sit-out / conviction floor** (#4, feeds #1/#3) | biggest lever; Fable design in flight | design → build |
| 2 | **Range-vs-trend day mode** (#3) | tonight's root cause; the conviction score's key input | medium |
| 3 | **Bug #1 entry-side** (don't open trades the exit logic already rejects) | removes 18 of 38 entries, zero new exposure | small, prereg'd |
| 4 | **Same-thesis strike-out rule** (#6) | −$579 of 08-12; C31's live sibling | small |
| 5 | **Daily profit lockout** (#5) | trivially cheap; "one clean trade pays the day" is already doctrine | tiny |
| 6 | **Repeat-touch level scoring** (#8) | J's own edge, mechanizable | small |
| 7 | **Calendar port to live path** (#2) | CPI days exist; currently invisible | small |
| 8 | Trade budget / overtrade meter (#13) | subsumed partly by rank 1 | tiny |
| 9 | Cost-vs-edge gate (#14) | matters at live, paper hides it | small |
| 10 | Orphan safe-2 09:58 fill trace + BTC/USD on options account | unexplained execution paths | probe |
| 11 | Stagnation exit (#11) | absent vocabulary, but exit-knob class = prove it first | study |
| 12 | Intraday memory (#12) | real but needs design care (C22 backward-looking trap) | design |

Items 1–7 are the "focus on actual trading" list. Everything below is hygiene or study.

## Standing rule going forward

The **capability audit is now a recurring instrument**, not a one-off: re-run the decision
inventory against the engine after any major phase change (paper→live, new strategy family,
sizing tier change). A conformance-green week means the code does what it says — it says
nothing about whether the code can say what the trader needs. Lesson filed to make this stick.
