# GAMMA-WORKER — from report generator to colleague

> **The brief (J, 2026-07-08, verbatim spirit):** "The 4PM report does not feel like something
> I'm working alongside. I need: this is what I saw today, this is what happened, here's how
> we're changing the engine. And when we mine my thought processes — why did *I* have to think
> of that? Make Gamma a self-learning, self-improving, autonomous, real worker."
>
> Sibling doc: [`BRAIN-SOVEREIGNTY.md`](BRAIN-SOVEREIGNTY.md) (the brains). This doc is the *behavior*.

The complaint decomposes into three gaps. Infrastructure was never the problem — the rig has
Discord, a dashboard, ledgers, R&D loops. What was missing is the layer that turns ledgers into
a **person telling you about their day**, and frames into **new ideas J didn't seed**.

---

## Layer 1 — Presence (a colleague talks; a system emits files)

**Shipped 2026-07-08, verified:**
- **`setup/scripts/gamma_narrative.py`** — nightly first-person narrative: gathers ONLY
  deterministic facts (fill funnel incl. the new `rule_blocked` stage, trades P&L, kitchen R&D
  events, today's commits, known-broken flags), then a free swarm lane writes Gamma's
  SAW / DID / LEARNED / CHANGING account (≤280 words, numbers restricted to the facts block).
  Publishes to `automation/state/gamma-narrative.json` (dashboard surface) + `journal/{date}.md`
  (`## Gamma evening narrative`) + the Discord outbox (bridge delivers to J's phone).
  Deterministic-digest fallback on LLM failure — silent failure banned (OP-25).
- **`setup/scripts/gamma_speak.py`** — the literal voice: Kokoro-82M TTS (Apache-2.0, local, $0,
  `setup/.tts-venv`, weights gitignored in `setup/tts/`) speaks the narrative →
  `automation/state/gamma-voice-{date}.wav`. First voice: 2026-07-08, 93s. Chained
  automatically after the narrative.
- **`Gamma_EveningNarrative`** scheduled task — 16:20 ET weekdays, registered + NextRunTime
  verified (the one-time-trigger-goes-dark trap avoided). Runner: `run-evening-narrative.ps1`.

**Queued (FUTURE-IMPROVEMENTS #28):** dashboard "Gamma speaks" panel (narrative text + play
button reading `gamma-narrative.json` / the wav), voice file attached to the Discord message,
morning variant (premarket brief in the same voice).

## Layer 2 — Narrative self-awareness (the causal chain, told, not logged)

The narrative's fixed spine IS the causal chain J asked for: what I saw → what I did → what I
learned → what I'm changing. Two design rules keep it honest (OP-33):
1. **The model may only narrate the facts block.** Every number is ledger-derived; the
   deterministic digest ships alongside the prose in the state JSON.
2. **Continuity:** each narrative sees the prior one's lever + question, so days build on each
   other instead of resetting (v1: no-repeat rule; v2: a real `gamma-beliefs.json` self-model —
   what I believe / how confident / what evidence — updated nightly, queued #28).

First-night proof this works: tonight's narrative correctly told the PDT-jail story (13 core
ENTERs refused by Rule 7 while fleet arms did 12 round trips) — a story that previously lived
scattered across three ledgers and a false Discord alarm.

## Layer 3 — Generative cognition ("why didn't Gamma think of that?")

Root cause of the gap: every existing loop optimizes *within* frames J already seeded. Nothing
enumerated the frame space itself — that's why J had to notice the DTE axis (2026-07-07 scar,
`GENERATIVE-LENS.md`).

**Shipped v1 (inside the narrative):** an embedded **untested-axes list** (DTE ladder, spreads,
delta bands, session regimes, VIX param-sets, exit ladders, direction-split exits, QQQ,
overnight, confidence-scaled sizing). Every night Gamma must pick ONE cell today's evidence
makes interesting and say why now — plus ask J one genuine question (colleagues ask questions;
the ledger records them). First night it connected PDT jail → overnight-hold axis, unprompted.

**Queued v2 (#28):** `axis_audit.py` as a standing instrument — machine-readable axis × tested-cell
matrix populated from `analysis/recommendations/`, emitting ranked unexplored cells into the
kitchen queue weekly. The nightly lever then comes from live coverage data instead of a static
list, and "we never tested X" becomes structurally impossible to miss. Plus the WeBull-style
nightly "watch the tape like J" replay (what would a trader have noticed today that no rule
encodes?) feeding `_lesson-inbox/` and the kitchen.

---

## Verified state, 2026-07-08 evening

| Piece | Status | Proof |
|---|---|---|
| fill-funnel `rule_blocked` stage | LIVE | 19:39 self_check fire posted "RULE-BLOCKED" (not "PLACEMENT BROKEN"); 37 guard tests green incl. 2 new |
| Evening narrative | LIVE (task registered) | exit 0 under task interpreter; json + journal + outbox artifacts verified |
| Voice | LIVE (chained) | `gamma-voice-2026-07-08.wav`, 83–93s, Kokoro local |
| Generative lever + question | LIVE (v1) | picked verticals / overnight-hold from today's PDT evidence, asked J a real PDT question |
| Dashboard panel | QUEUED | #28 + task chip |

**The test that matters:** J wakes up tomorrow, Discord has Gamma's account of the day in
Gamma's own words at 16:20, with one new idea and one question — no prompting. That either
happens on 2026-07-09 or this doc's Layer 1 is marked broken in STATUS.md.
