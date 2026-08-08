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

### P2 SHIPPED 2026-07-08 — `gamma-voicebot/` (awaiting J's first live voice test)

Node app (`bot.js` + `lib/`), sibling of the companion. **Start:** `setup/scripts/run-voice-bot.ps1`
(or `node gamma-voicebot/bot.js`). **Stop by voice/text:** "gamma leave".

- **Join/leave:** joins HQ voice "General" when J joins it or on "gamma join" in any HQ text
  channel; leaves on "gamma leave", when J leaves, or after **5 idle minutes** (mandatory —
  an open Realtime session runs a paid meter). Pin/retune via
  `automation/state/voice-bot-config.json` (voice_channel_id, model, idle_timeout_ms).
- **Mouth:** OpenAI Realtime over WS, model **`gpt-realtime-2.1-mini`** (probed live from the
  key's /v1/models 2026-07-08 — current mini-class slug). Same ephemeral-token mint as the
  companion (`/v1/realtime/client_secrets`; key via `gamma-companion/lib/openai_key.js`, never
  in code). `semantic_vad` + local playback flush + `response.cancel` = barge-in.
- **Facts are tools (OP-33):** `engine_state` (last core-decisions row per account + open
  positions + staleness note) · `funnel_today` (runs `fill_funnel.py`, render_text) ·
  `evening_debrief` (`spoken`→`text` of gamma-narrative.json). Persona = CLAUDE.md "Who I am"
  extracted at session start + spoken-register v1.1 rules; state answers ONLY from tool output.
- **Security:** J's user_id only (from `.discord-config.json` — never hardcoded); bot
  subscribes ONLY to J's audio; tools read-only; no order path; writes = usage meter + log.
- **Meter:** one row per session → `automation/state/voice-bot-usage.jsonl`
  (start/end/seconds/model/session_id/token totals) for spend_summary pricing.
- **Verified 2026-07-08 (harness `gamma-voicebot/test/harness.js`):** 3 tools PASS on real
  ledgers; Realtime session opened (id logged), model called `engine_state` and spoke the real
  state back, usage row written with token counts; gateway login as Chief#2680 (Message
  Content intent already enabled — zero portal clicks needed); `--selftest-join` reached voice
  Ready in "General" and left cleanly. **UNVERIFIED (needs J):** live mic round-trip — J's
  speech → tool answer in Gamma's voice, barge-in feel, idle auto-leave in situ.

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

**Shipped & verified 2026-07-08 evening.** One two-channel model call
(`===WRITTEN===`/`===SPOKEN===`, drift-tolerant splitter — qwen renders the markers as
markdown headings), `already_pinged` = last 15 outbox rows (both row shapes), `gamma_speak.py`
prefers `spoken`. Hardening from live probes, all deterministic guards:
(1) the openrouter-free nemotron lane returns REASONING-AS-CONTENT (21K chars rehearsing the
markers; `max_tokens` 8000 is an instant-empty poison value there) → `_channel_sane()`
marker-echo/size guard, budget stays 4000; (2) a small-lane register rewrite flipped the day's
$382 LOSS into "a total profit" → repair pass is now P&L-truth-anchored + sign-guarded and
keeps the original on any miss. Verified fire: exit 0, spoken = 156 words, zero digits, zero
stage-name jargon, ends with the question; 52s wav synthesized from `spoken` (865-char speech
text matched exactly). Residual, accepted: floor lanes can fuzz a rounded count ("two dozen"
vs a dozen fills) — the written channel remains the exact auditable record.

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
| Voice bot MVP (P2) | BUILT + harness-verified | session sess_DzWwBZGJ5tSeKEDRPl8cy tool round-trip on real state; voice join Ready; **J live-mic test pending** |
| Dashboard panel | **SUPERSEDED** — see Layer 4 below | the "queued panel" idea got absorbed into a whole page, not a panel |

**The test that matters:** J wakes up tomorrow, Discord has Gamma's account of the day in
Gamma's own words at 16:20, with one new idea and one question — no prompting. That either
happens on 2026-07-09 or this doc's Layer 1 is marked broken in STATUS.md.

---

## Layer 4 — The Gamma App: the web presence surface (2026-08-08)

**The ask (J, mid-flight, verbatim spirit):** "full blown gamma app... the ultimate autonomous
gamma... living and breathing, hungry for the money... depth, vision, empathy, determination,
awareness." **Hard constraint:** the GAMMA HQ terminal window (`gamma_hq.py`, shipped hours
earlier the same day as part of the presence program) was explicitly rejected AS A SURFACE — "go
look at 21st.dev, find AI assistant HQ dashboards online" — the web app is now the ONLY presence
surface. This is NOT a reversal of the terminal build: `gamma_hq.py` stays alive as the **state
librarian** (see below); only the ANSI-window-as-the-thing-J-looks-at idea is retired.

### Why the three prior embodiments didn't stick (recon before building)

1. **`dashboard/` "Trade House"** (Next.js + React-Three-Fiber pixel-art trading floor, live since
   May) — a metrics wall + 3D scene: KitchenPanel/AutoresearchPanel/LiveWatchPanel numbers,
   nothing first-person, nothing that initiates. J's own words killed the "make it an input tool"
   direction 2026-06-24: "i just want to talk to you not utilize the dashboard as a tool. i just
   want it for visuals." Visuals-only was accepted, but visuals-only never became something J
   opened daily — an aquarium to glance at, not a colleague.
2. **`gamma-companion/`** (Electron, port 4317, shipped 2026-06-20, iterated through v0.3.0) — grew
   an OpenAI-Realtime voice pipeline, a chat brain, Approve/Reject cards, a GridStack layout, an
   Electron desktop shell. Real engineering, but the **approval bus was never wired to the actual
   actuator** (producers never enqueued real items) and it added machinery (voice meter, SDK
   escalation, a whole second app) without closing the presence gap — matches the standing lesson
   "presence = initiate + visible home + wants; never more machinery."
3. **`gamma-voicebot/` + `gamma_narrative.py` Discord voice** (2026-07-08) — real TTS, real
   barge-in, a genuinely good SAW/DID/LEARNED/CHANGING narrative structure. J's own verdict on the
   first wav: "sounds like he's just reading the messages I get sent in Discord... hard to follow,
   all numbers and commands" — fixed with a `spoken` register, but per the 2026-08-08 presence-doc
   update, **"voice-briefs-alone did NOT create felt presence either."**
4. **GAMMA HQ terminal** (`gamma_hq.py`, shipped earlier 2026-08-08 as part of the same presence
   program) — the first surface that actually WORKED as a legibility exercise (short first-person
   sections, fail-open placeholders, a real render-loop) — but a console window is not where J
   lives, and this session's mid-flight redirect made that explicit.
5. **Common thread across all four:** presence kept getting solved as an ADD-ON channel (a new
   app, a new voice pipeline, a new window) instead of upgrading the ONE surface J might actually
   open unprompted. The Gamma App bets on the opposite: one polished page, real data, no new
   infrastructure class.

### Design patterns stolen from 21st.dev / AI-agent-dashboard research (2026-08-08 WebSearch/WebFetch)

- **Agent Activity Feed** (theskinsfactory.com) — "a real-time, filterable feed of agent actions,
  decisions, and pending items... a timeline for autonomous behavior" → the LIVE ACTIVITY section,
  merging commits + narrative + real fills + shadow fills into one reverse-chron stream.
- **Decision Logs Over Action Logs** (theskinsfactory.com) — explain the WHY, not just the WHAT →
  every trade/shadow-fill card names the setup, not just "ENTER"/"EXIT"; commit cards keep the
  real subject line rather than just "commit pushed."
- **Ambient Agent Patterns** (agentic-design.ai) — "always-present, contextually-aware... operate
  seamlessly in the background while remaining accessible" → informed the calm/no-clutter
  layout choice (generous whitespace, one accent, 20s in-place refresh) over a dense metrics grid.
- **Mission-control style monitoring** (agentic-design.ai) — real-time oversight without alert
  fatigue → the state chip + first-person "right now" sentence at the top, everything else is
  supporting detail below it.
- **Confidence Gradient** (theskinsfactory.com, "high confidence actions get minimal visual
  weight; low confidence gets progressively more prominent") — applied narrowly and honestly: the
  MES-mirror clock's "needs beats-null" caveat gets a visible amber badge (a real uncertainty flag
  from the data), but nothing fabricates a confidence score where the engine doesn't compute one.

### What shipped

- **`gamma_hq.py --json`** (additive-only edit, zero change to the terminal's own render loop) —
  a single-shot mode that runs the SAME pure helpers `render_frame()` uses
  (`derive_state_word`, `_today_focus_text`, `_extract_progress`, `_sanitize_line`,
  `_humanize_commit_subject`, …) and emits the computed 7-section view as JSON. This is the
  **state-librarian contract**: the terminal (deprecated as a surface, kept as a library) and the
  web page render identical semantics because they call the identical code — zero business logic
  duplicated into TypeScript. Caught + fixed live: the JSON branch originally returned before
  `main()`'s UTF-8 stdout reconfigure, mangling every em-dash/middot for the JSON consumer only.
- **`dashboard/app/gamma/`** (route group, new `Section`/`PresenceHeader`/`MoneyView`/
  `ActivityFeed`/`WantsCards`/`ThisWeekCard` components under `dashboard/components/gamma/`) —
  PRESENCE HEADER (identity, pulsing state chip, first-person "right now" sentence, today's
  focus), LIVE ACTIVITY (the centerpiece feed), MONEY VIEW (goal banner, today's tape, animated
  clock bars), I WANT (numbered priority cards from `gamma-wants.json`), THIS WEEK (top-3
  CRITICAL/HIGH items from `automation/overnight/queue.md`'s Active backlog, humanized).
- **`dashboard/lib/{gamma-hq-bridge,activity-feed,wants,this-week,gamma-app,text}.ts`** — the data
  layer. `activity-feed.ts` merges 4 REAL sources: git commits, `discord-outbox.jsonl` (allowlisted
  narrative producers only — standups/prospector/firm-brief/etc — explicitly excluding
  `self_check`, whose live sample rows were 100% raw `DEGRADED:` infra dumps with zero narrative
  value), `journal/trades.csv` real fills, and the futures-mirror/SSR shadow ledgers (always
  labeled "no real money"). **Substituted `journal/trades.csv` for the brief's named
  `decisions.jsonl`**: verified live that both `automation/state/decisions.jsonl` and its
  `aggressive/` sibling are STALE (last written 2026-06-25) — using them would have silently shown
  weeks-old ticks as "live." trades.csv is both the doctrinally-correct source (C1: real-fills is
  the only WR authority) and the one that's actually current.
- **Two bugs caught + fixed in the same build session** (not shipped broken, then fixed later):
  (1) a shared banned-substring filter built for short fields (reject a row containing "DEGRADED")
  was wrongly also applied to long-form `queue.md` prose that legitimately *discusses* a DEGRADED
  flag as its subject — collapsed 2 of 3 THIS-WEEK cards to a blank placeholder; split into
  `isLogSpew()` (a skip decision, used only on raw short fields) vs `sanitizeText()` (pure
  formatting, never refuses); (2) outbox rows are `"<@ID> [TAG] text"` — the bracket-tag strip ran
  BEFORE the mention strip and never matched; reordered.
- **DST-safe timestamp handling**: several state files write bare `"YYYY-MM-DDTHH:MM:SS"` ET
  wall-clock strings with no zone suffix. This box's OS-local zone is Mountain, not Eastern (see
  CLAUDE.md's "Bash TZ broken" lesson) — a naive `new Date(str)` in the Node process would have
  silently skewed every activity-feed timestamp by 1-2 hours. `dashboard/lib/time.ts` gained
  `wallClockInZoneToUtc()` (round-trip through `Intl` to discover the real DST-aware offset, no
  hardcoded offset table) and `parseBareTimestampInZone()`.
- **Deployed live**, not just built: `npm run build` then launched via the SAME invocation
  `Gamma_DashboardKeepalive` uses (`node node_modules/next/dist/bin/next start -p 3000`, hidden,
  no window flash) so it's already serving before this session ends — see verification section of
  this session's own report for exact curl output. `http://localhost:3000/gamma`.

### Phase 2 — honestly scoped, NOT built this session

- **Talk-to-Gamma input.** Wire a text box on the page to the existing `discord-responder.py`
  brain (already the standing "no LLM in the live trade loop" translator per house doctrine) —
  same guardrails that already gate Discord-side intents apply verbatim; this is a transport
  change, not a new brain.
- **Session spawner buttons.** A button that fires a bounded background Claude session (e.g. "run
  the SSR dojo rep", "re-check gate recency") via the existing scheduled-task/background-agent
  plumbing — needs an explicit allowlist of spawnable actions (mirroring
  `gamma-companion/lib/guard.js`'s hard-denylist pattern: never doctrine/params/live-order writes
  from a button click) before it ships, not after.
- **TTS presence on the page itself.** The Kokoro-local voice pipeline already exists
  (`gamma_speak.py`) — a "listen to today's narrative" play button on the Gamma App reusing the
  existing `.wav` artifact is a small, low-risk add; real-time voice conversation (companion's
  OpenAI Realtime pattern) is a bigger, costed decision and stays out of scope until asked for.
- **Decision-log depth** (the "why" behind a trade card): today's trade/shadow-fill cards show
  setup name + P&L, not full gate/filter reasoning. `core-decisions.jsonl` has this detail but is
  47MB and tick-noisy (mostly HOLD/SKIP) — a real "why" card would need a proper byte-offset tail
  reader and a HOLD/SKIP-vs-ENTER/EXIT filter, deliberately deferred rather than half-built.
- **None of this is theater-scoped** — each item names the real file/module it would extend and
  the guardrail it would need before shipping, per OP-33's no-oversell standard.
