# GOAL: DAILY-DRIVER-GLASS-2026-08-30

> J verbatim (2026-08-30 10:46 MT, after the retrospective he ordered): *"you're not
> really going out to the Internet and finding what other people are doing... you just
> keep regurgitating the same shit... the visual needs to be bigger. Like, right now, I
> can't even see what the orchestrator says. The text is, like, literally size two font.
> I want one single pane of glass for all my... whole trading engine. The orchestrator, I
> wanna be able to talk into... when I'm trading, I wanna just be talking to the thing on
> the website... It should know every single thing that's going on with trading... good
> animations that show clearly the agent sending information... It's pulsing because it's
> working... agent one sent mail to Orchestrator five minutes ago... everything needs to
> be human readable, intuitive, layman's terms, broken down, so it's easy to see at a
> glance."*

## THE VISION (synthesized from all 46 of J's messages this session — the spec his
## prompts have been describing since 2026-08-29 evening)

1. **One pane of glass, no scroll.** The whole trading engine on one screen: engine,
   lanes, agents, orchestrator, activity, P&L. (asked 6x)
2. **Gamma is a PRESENCE, not a page.** The orchestrator sits big at the top; J talks to
   it right there while trading, and it already knows the live trading state — positions,
   P&L, bias, heartbeat verdict — without being told. (asked from the first message:
   "I want gamma to be smarter and autonomous")
3. **The org is ALIVE and legible.** Agents are named cards a human can read: who they
   are, what they're doing in plain words. Working = visibly pulsing. Messages =
   animated packets travelling the beam, AND a plain-English feed line ("Agent 1
   reported back to the orchestrator · 5m ago"). (asked 9x)
4. **Everything human-readable.** No commit-speak, no task codes, no file paths on the
   glass. Every event is actor + verb + plain English. Detail on hover/click only.
5. **Readable sizes.** ~13px real-pixel floor on the glass. NEVER text inside a scaled
   SVG viewBox — that is exactly how "size two font" happened, twice.
6. **Custom, not stock.** Grounded in real external references, cited per change.
   (asked 6x: "nothing stock. all custom" / "make it epic")

## DONE-WHEN
Falsifiable, checked in the running page:
- (a) computed font-size of every visible text node on `#/desk` ≥ 12px, orchestrator
  name/status ≥ 15px — measured by JS assertion, not eyeballed;
- (b) `document.body.scrollHeight <= innerHeight+1` at 1600×950 AND 1440×900;
- (c) the activity feed + "on its own" rows render ZERO raw `type(scope):` commit
  prefixes, task codes, or absolute file paths (regex-checked against the DOM);
- (d) agent→orchestrator message events drive BOTH a travelling packet on the beam and
  a feed sentence, from the same real event source (companion pulses), verified live;
- (e) the console's replies demonstrate injected trading context (answers "what's our
  P&L today / are we in a position" without J pasting anything);
- (f) `markdown/infra/COCKPIT-DESIGN-SPEC.md` carries the external-reference dossier and
  every design commit in this goal cites ≥1 reference from it.
A null result on any item is reported as a null, not silently shipped around.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 → ~2026-09-29**: no trading-path changes; this goal is
  app/companion surface only and touches no frozen path.
- **Design passes START with external reference-gathering** (the 8x-repeated
  correction, now memory `design-starts-at-external-reference`). Iterating from own
  prior output without fresh references violates this goal.
- Every fire that touches this goal records `conductor_outcome.py record`.
- Any Agent/Workflow fan-out passes `model:"sonnet"` explicitly.
- STATUS.md line at OPEN and CLOSE only.
- Never `/loop /gamma-goal`.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] R1 — External-reference dossier: sweep agent-orchestration UIs (LangGraph Studio,
  AgentOps, Flowise), animated-beam/packet components (Magic UI AnimatedBeam, Aceternity),
  activity-feed patterns (Linear/GitHub/Vercel), 21st.dev agent/feed/bento components.
  DONE-WHEN: dossier section appended to COCKPIT-DESIGN-SPEC.md with ≥8 cited entries,
  each carrying an extracted TECHNIQUE (not a vibe). VERIFIED 2026-08-30 (conductor
  continuation): dossier already had R1-R9 (9 entries, ≥8 met) from a concurrent session
  by the time this fire read it — LangGraph Studio (R4) and AgentOps (R5) already covered
  by name, Flowise and Linear/GitHub/Vercel activity-feeds were not yet named. Rather than
  duplicate R1-R9, fetched real source for the two missing named items (curl, not
  training-data recall): Flowise's own `package.json` (reactflow ^11.5.6 — and the repo
  itself now reads "has been archived", a real disclosed finding) and GitHub Primer's
  actual `Timeline.module.css` (rail = N per-row `::before` 2px segments, not one SVG
  line). Appended R10, R11, and one explicit GAP line (Linear/Vercel activity-feed markup
  is closed-source, not found within budget — disclosed, not fabricated). Table now 11
  entries + 1 disclosed gap, all real fetches with citation URLs.
- [ ] B1 — Stage rebuild: orchestrator + agent nodes as real HTML (big type), SVG kept
  ONLY for beam paths drawn between DOM rects (AnimatedBeam pattern). DONE-WHEN: the
  DONE-WHEN (a) font assertions pass on the stage.
- [ ] B2 — Humanizer: `js/humanize.js` translating commits ("fix(quiet-mode): …" →
  "Fixed — …"), task codes, autonomy-fire notes into plain sentences; applied to the
  activity feed AND "what Gamma did on its own". DONE-WHEN: DONE-WHEN (c) regex passes.
- [ ] B3 — Message-flow events: drive beam packets + feed sentences from companion
  pulse rows (the real agent→orchestrator traffic). DONE-WHEN: DONE-WHEN (d) verified
  with a live spawned agent.
- [ ] B4 — Console knows trading: /api/ask prepends a compact live-state block
  (positions, day P&L, bias, heartbeat verdict, lane states) so the web console answers
  trading questions cold. DONE-WHEN: DONE-WHEN (e) demonstrated in the page.
- [ ] B5 — Fit + verify pass at 1600×950 and 1440×900; screenshot to J. DONE-WHEN:
  DONE-WHEN (b) at both sizes.
- [B-J] Firebase credential, admin/multi-user boundary, `/` root repoint — carried over
  from GOAL-APP-REBUILD, still J's.

## J-DECISIONS
- Whether `/` becomes the app (repoints the phone PWA).
- Firebase project credential + any friends-access before token verification exists.

## PROGRESS LOG
- 2026-08-30 12:5x ET — Goal opened after transcript-mined retrospective (1,236 calls,
  2.5% external web, 8x-repeated research ask). Memory rule written.
- 2026-08-30 ~13:0x ET (conductor Stop-hook continuation 1/3) — R1 closed. Found the
  dossier already at R1-R9 from a concurrent session; verified the bar was genuinely
  met rather than assuming, then added real value instead of a duplicate pass: fetched
  live source (curl) for the two explicitly-named items still missing (Flowise,
  GitHub Primer activity-feed rail), disclosed one honest gap (Linear/Vercel markup is
  closed-source) rather than fabricating a citation. Dossier now 11 entries + 1 disclosed
  gap. B1-B5 remain untouched — did not start a build item this continuation (R1 was
  the assigned next item; stopping here per the hook's own "then stop" instruction
  rather than self-continuing into B1 unassigned).

## HONEST STATE
R1 (external-reference dossier) is DONE and verified — 11 real, source-cited entries
with extracted techniques, not vibes. B1-B5 (the actual stage rebuild, humanizer,
message-flow wiring, console context injection, fit-and-verify pass) are UNSTARTED.
The four `[B-J]` items are unchanged, still genuinely J's.
