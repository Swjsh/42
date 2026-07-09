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

## Layer 1b — Real-time voice presence: "talk to Gamma in the HQ Discord" (PLAN, J 2026-07-08)

**What J already tasted (recon 2026-07-08):** `gamma-companion/public/realtime.js` — mic ↔
**OpenAI Realtime API over WebRTC** (speech-native model: ~sub-second turns, barge-in, natural
prosody), ephemeral tokens minted by `/api/realtime-token` (real key never in browser), with a
`/api/chat → Claude SDK` bridge. That "alive" feel is a property of speech-to-speech models —
an STT→LLM→TTS chain (whisper→qwen→kokoro) runs 2–5s/turn with no barge-in and feels like a
walkie-talkie. The PWA route's blocker was HTTPS-on-LAN (Tailscale); **Discord as transport
deletes that problem** — J's phone Discord app carries the audio from anywhere.

**Recommended architecture (hybrid — the mouth is rented, the facts are owned):**
1. **Mouth/ears:** Discord voice bot in the HQ server; joins on J's join/command; pipes audio
   Discord ↔ OpenAI Realtime (reuse the companion's key + token-minting pattern).
2. **Facts are TOOLS, never model memory (OP-33):** Realtime function-calls into deterministic
   readers — `engine_state` (last core-decisions row + positions + armed/kill-switch),
   `account_pnl` (trades CSVs), `funnel_today` (fill_funnel), `whats_cooking` (cook-queue tail),
   `evening_debrief` (gamma-narrative.json spoken text). The voice model may narrate ONLY tool
   output for state questions — it never invents rig state.
3. **Deep asks queue honestly:** `ask_gamma_deep` tool → writes to a queue consumed by a Claude
   fire (`claude -p --agent gamma`) → answer posted to the channel (and spoken if J still
   connected). The bot SAYS "digging in, give me a few minutes" instead of hallucinating depth.
4. **Sovereign fallback lane (BRAIN-SOVEREIGNTY tie-in):** same tool interface behind a local
   chain (faster-whisper on the 5080 → qwen3.6 persona → Kokoro). Slower but $0 and offline —
   the blackout-drill voice. Built LAST, kept warm.

**Guardrails:** J's user-ID allowlist only; voice tools are READ-ONLY v1 (no flatten/arm/param
changes by voice until an explicit confirm protocol exists — rules 9/10); per-minute cost meter
into the spend ledger (Groq scar: meter before trusting "cheap"); barge-in on, sessions
time-boxed (auto-leave after idle) so an open mic never runs a meter overnight.

**Cost honesty (as-of 2026-07, verify current):** Realtime-mini-class ≈ cents/minute of
conversation; casual daily use = single-digit $/month; the meter line makes it visible. Local
lane is $0 forever.

**Build order:** (P1) narrative spoken-register v1.1 (below) → (P2) Discord voice MVP: join +
Realtime bridge + 3 read-only tools → (P3) `ask_gamma_deep` + evening debrief on join →
(P4) local fallback lane. Sonnet-army work against this spec; Fable reviews the seams
(token minting, tool contracts, allowlist) and runs first end-to-end contact.

## Narrative register v1.1 — "sounds like a mind, not a stat dump" (J feedback on first wav)

First wav verdict from J: "sounds like he's just reading the messages I get sent in Discord...
hard to follow, all numbers and commands." Root cause: one text serves two channels — the
WRITTEN narrative optimizes for factual density; SPOKEN Gamma needs a different register.

Spec (small change to `gamma_narrative.py` + `gamma_speak.py`):
- Generate a second field `spoken`: same facts, radio-debrief register — story first ("the
  thing that mattered today..."), **≤3 numbers total, all rounded**, no ticker symbols / order
  IDs / stage names, 45–75 seconds (~120–170 words), reflective first person, ends with the
  question for J. `gamma_speak.py` prefers `spoken` over `text`.
- **Interpret, don't re-read:** the facts block gains today's outbox history with the
  instruction "J already received these pings — reference and EXPLAIN them, never repeat them."
- Written `text` + deterministic digest stay exactly as-is (the auditable channel).

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
