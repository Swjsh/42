# The Reframe Engine — encoding the Operator's meta-cognition into Gamma

> Born 2026-06-29 when J, after months with the system, generated the "discovery fleet"
> reframe. He then asked the real question: *dissect HOW I came to that, name it, and turn it
> into something **Gamma** does.* This is the answer + the architecture. (Opus-dissected.)

## The named process: **Constraint Provenance Audit** (Friction-Gated Constraint Inversion)
Detecting that a rule you've been *optimizing under* is actually a rule you should be
*auditing*. Two beats:
- **Beat 1 (reframe):** when progress stalls in the **same shape** repeatedly, stop optimizing
  inside the frame. Locate the constraint all the failures died at, trace its **provenance**
  ("where did this rule come from, what context was it built to protect, does that context
  apply to what I'm doing *right now*?"), and if it's borrowed/mis-scoped, **invert it** (turn
  the gate into a sensor — stop paying to *decide* what you could cheaply *measure*).
- **Beat 2 (self-critique):** pressure-test it ("what would you even call this / could we have
  thought of it months ago?") to separate a real frame-change from a relabeled obvious thing.

**The crux — why it's friction-gated, not intelligence-gated:** *intelligence proposes
dropping the constraint; only metabolized friction **authorizes** it.* The idea is cheap to
generate; the permission to discard a virtue that's still ostensibly earning its keep is paid
for only in lived, repeated cost. A fresh model — free swarm OR Opus cold — cannot have the
insight, because it lacks the **calibrated, felt prior** ("the validate-first pipeline keeps
handing me mirages") that only exists after months. That prior is experiential, not
propositional — a derivative, not a level.

## How J got there (this instance)
1. **Accumulated friction** — the object grind kept returning the same shape (filter-5 = +EV but
   OOS-fail; double-bottom washes out; engine HOLDs / "no armable edge"). Each failure was
   individually correct; the signal was the failures **rhyming**.
2. **Altitude change** — stopped asking "why did THIS fail?" → "why does EVERYTHING fail the
   same way?"
3. **Keystone** — located the gate they all died at: *validate-before-trade.*
4. **Provenance check** (the non-obvious move) — that gate protects **real capital**; he's on
   **paper.** Live discipline leaked into the research layer where it's pure tax.
5. **Inversion** — validation flips from a filter applied *before* into an output harvested
   *after*; the fleet's real function is **manufacturing the dense label stream the discovery
   machine was starving on.**
6. **Self-critique** — "could've thought of this months ago" correctly flags the *mechanic* as
   obvious; what's novel is the **permission** + the fact the **consumer now exists.**

## The discovery fleet, re-verdicted (Opus tier): a COUNTERFACTUAL LABEL ENGINE
Not a fleet of traders (paper P&L has no slippage; "$100K all-strategies both-sides" is a
different distribution than what survives at $2K — as a *trading* proposal it's noise). The
defensible form: every signal today yields a **censored** outcome (HOLD → learn nothing; CALL
→ put counterfactual unobserved). Firing **both directions on every signal** → each bar
becomes `(features at t) → (call_pnl, put_pnl, hold=0)` — the dense, symmetric,
decision-complete dataset the FDR screen has been starving on. The "$100K/all-strategies" part
removes the **notional cap + HOLD-gate as label suppressors.** Product = the label ledger;
equity = discardable byproduct. **NON-NEGOTIABLE GUARD:** the labels must feed the *same*
OOS + real-fills + anchor-no-regression gauntlet, decided **at signal time, never hindsight** —
else "in hindsight something always worked" survivorship = the filter-5 mirage in a lab coat.

## Two pipelines, hard-separated (so neither overshadows the other)
| | **Pipeline 1 — Strategy Discovery & Validation** | **Pipeline 2 — Meta-Ideation / Big-Bet** |
|---|---|---|
| Job | generate many disposable *strategies*, let backtest+FDR label them | question the *box itself*: frame-changes, infra/capital bets |
| Model | **FREE SWARM** (design_swarm) — high-volume, disposable | **OPUS** — rare, high-leverage, expensive-to-reverse |
| Lives | backtest/autoresearch/, strategy/candidates/_chef-inbox/ | markdown/meta/, automation/state/meta_ideation/ |
| Trigger | continuous (KitchenSeeder cadence) | Reframe Engine — weekly / friction-threshold |
| Gate | auto-ratify rail (OOS+ ∧ WF≥0.70 ∧ sub-window-stable ∧ anchor ∧ FDR) | propose-only → conductor backlog |

**Routing rubric** (score Stakes / Reversibility / Leverage — ANY single 'high' → Opus/P2):
*Strategies are cheap and many → free swarm. Frames are rare and load-bearing → Opus. A
strategy candidate is P1; a new way to GENERATE or MEASURE strategies is P2.*

**The hard interface:** separate dirs/ledgers/triggers; the ONLY coupling is one-directional
**P2→P1** via a typed `infra_spec` (a build-order); the ONLY P1→P2 flow is a **scalar pressure
gauge** (mirage-counter / FDR pass-rate, read in aggregate — a gauge, not a firehose). Cadence
asymmetry (P1 continuous / P2 rare) is itself the firebreak; if P2 ever fires on P1's cadence,
the firewall leaked → graduate to a guard. The discovery-fleet is **conceived in P2** (the
frame-change, Opus-authored) but **run in P1** (the cheap label instrument). That split is the
point.

## Encoding it into Gamma — the organ it lacks
Gamma today has NO organ that accumulates friction across time and reads it as a pattern
(self_audit finds point-in-time gaps; the conductor *drains* work; nobody asks "what constraint
have we ground against for weeks, and is the frame wrong?"). Two artifacts:

- **(A) Friction Distiller** — `setup/scripts/friction_distiller.py` (free-tier, nightly after
  self_audit). HARVESTS recurring friction (does not generate it) + COUNTS recurrence from:
  mistakes.md ('Pattern? Yes'), STATUS '## Known broken' (persisting ≥N days), LESSONS clusters
  gaining new L## (a re-violated constraint), recurring gap-log gaps, conductor-outcomes
  "still-not-trading / no-armable-edge / HOLD / OOS-fail / regime-flip" bucket (the project's
  **signature** friction), recency/recommendations rejections ("dies on fresh OPRA / dead-knob
  / null-reproduces").
- **(B) Friction Ledger** — `automation/state/friction-ledger.jsonl`, append-only, deduped into
  **patterns not events**. A pattern is **step-back-eligible at occurrences≥5 across ≥2 sources
  spanning ≥14 days** — that threshold IS the encoded form of "metabolized for months."
- **(C) Step-Back Ritual** — `automation/prompts/step-back.md` (OPUS, weekly Sun after-hours,
  `Gamma_StepBack`). Inherits the conductor's four rails verbatim. Runs the four-beat on the
  highest-recurrence pattern: name the constraint → is the frame wrong → invert the sacred
  assumption → what's illusory → self-critique. Emits 1–3 surviving reframes tagged
  {infrastructure | strategy-frame} + a falsifiable first test each.
- **(D) Divergence fan-out** — Opus judges (rare, correct seat); the free swarm adds breadth
  (attack the reframe + propose 2 orthogonal reframes of the same constraint); Opus re-collapses.
- **(E) Routing (keeps P1 pristine):** P2 NEVER writes analysis/recommendations/. {infrastructure}
  → conductor priority-3 backlog (STEP-BACK-PROPOSALS.md); {strategy-frame} → _chef-inbox as a
  plain hypothesis with no special status. (J's $100K idea lands here as "build the counterfactual
  label engine," NOT as a scorecard.)
- **(F) Guard** — `test_friction_distiller.py`: golden recurrence-count + eligibility threshold +
  the firewall assertion (no P2 row in analysis/recommendations/).
- **(G) Acceptance test:** backfill the ledger from real 2026-04→06 friction, run `Gamma_StepBack`
  once, confirm beat-3 **re-derives J's own $100K-all-strategies reframe automatically** — the
  mirror of Pipeline 1's acceptance test (the funnel re-deriving the filter-5 REJECT by itself).

## The lesson (→ CLAUDE.md OP-25 via lesson-author)
**Constraint Provenance Audit:** when stalled in the same shape repeatedly, audit the
constraint's PROVENANCE before optimizing under it — a money/safety rule that leaked into the
research layer is an idea-source, not a law.
