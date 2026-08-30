# GOAL: APP-REBUILD-2026-08-30

> J verbatim: "im going to sleep so you need to use the right tools and build the brand
> new site from scratch using the elemnts i provided dont stop until it looks like a
> professional site and note a basic claude html site, nothing stock. all custom."
>
> And, the turn before: "i want this to be my daily driver, only talking to the
> orchestrator panel using full claude code capabilities, hooks for following all my
> rules, agent orchestration etc. go nuts you are on ultra code and have the whole
> internet at your fingertips make the best site ever."
>
> The five elements he provided are 21st.dev components — jelly-animated-hero (landing),
> sign-in-page, prediction-market-card (action cards), dashboard-1 (agent cards),
> ai-assistat (the orchestrator console).

## DONE-WHEN

The app at `gamma-companion/public/app/` is something J opens every day instead of a
terminal. Falsifiable, each check runnable by a fresh session:

1. **Every view renders real data or names the file it wanted.** `python
   setup/scripts/web_shot.py http://127.0.0.1:4317/app/#/<view> --name check-<view>`
   for each of `/ profit cards agents chat signin`, and a walk of all six routes with
   an `onerror` trap reports ZERO runtime errors.
2. **The console is a working daily driver.** A message sent through `#/chat` resumes
   the stored session, runs at least one real tool, streams markdown that renders as
   markup (not escaped source), and ends with a terminal frame. A run can be stopped
   with Esc and says stopped, never done.
3. **Nothing on it lies.** No panel shows a plausible default in place of missing data;
   present-tense agent counts come from `worker_active` only; the sign-in refuses to
   authenticate rather than accepting anything while unconfigured.
4. **It survives being looked at on a phone.** At a 375px viewport,
   `documentElement.scrollWidth === innerWidth` and no element exceeds the viewport.
5. **It is reachable without ceremony** — a single URL or shortcut J can open half
   asleep, with the companion auto-started by its existing keepalive.

A finding that one of J's five components does not transfer to a no-CDN vanilla page
(e.g. a framer-motion behaviour with no CSS equivalent worth the bytes) is a VALID
terminal state for that element IF the finding is written down and the substitute is
named — not silently dropped and not faked with a worse imitation.

## OPERATING RULES

- **CONFIG FREEZE 2026-08-31 → ~2026-09-29**: no trading-path changes except
  pre-registered kill-type risk reductions (STATUS.md 2026-08-29T12:00 ET). This goal
  is a PRESENTATION goal — it reads trading state and must never write it. Any item
  that would touch the trading path gets flagged `[B-J]`, not queued.
- Every fire that touches this goal calls
  `python setup/scripts/conductor_outcome.py record --task-id GOAL-APP-REBUILD-2026-08-30
  --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"` —
  `Test-OutcomeNoop` sums these and two consecutive no-op fires kill the loop.
- Every `Agent`/`Workflow` fan-out passes `model:"sonnet"` explicitly. An in-prompt
  "run /model sonnet first" is a no-op (2026-07-23 scar, 2.2M tokens).
- `STATUS.md` gets a line at goal OPEN and CLOSE only, never per-fire — it is
  bytes-capped and per-fire lines roll real REVOKE entries off J's surface.
- Never `/loop /gamma-goal`. One fresh process per fire.
- **Commit messages go through `setup/scripts/commit_msgfile.py`**, never as a shell
  argument. Backticks around a field name are correct prose and command substitution
  in bash; this hung a commit for two minutes on 2026-08-30 waiting on a volume-label
  prompt (`_lesson-inbox/2026-08-29-shell-quoting-and-stale-process.md`).
- **Look at it before claiming it.** Every visual claim in this goal is backed by a
  headless screenshot (`web_shot.py` / `cockpit_shot.py`) or a live DOM measurement,
  because the in-app browser pane cannot composite frames while J is away. Four real
  bugs on 2026-08-30 were invisible to code review and obvious in a screenshot.

## QUEUE

`[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J`

- [x] Build the six views from J's five components, ported to vanilla. DONE-WHEN: all
  six routes render and a walk with an onerror trap reports zero errors. VERIFIED
  2026-08-30 03:3x — six routes walked in the live page, `errors: []`, every route
  returning substantial content (cards 2157 chars, agents 1720). Commits 01b14348,
  ebb24b9b, 39e220d8, 9c166595.
- [x] Make the orchestrator a console, not a chat. DONE-WHEN: a real message runs a
  real tool and renders markdown as markup. VERIFIED twice 2026-08-30: resumed the
  stored session, ran Glob, returned an actual `<ul>`, "Done in 12.8s".
- [x] Total Profit opens a real CALENDAR, not a bar chart. VERIFIED 2026-08-30 03:51
  by headless shot at 1600px (`analysis/home/_shots/web/app-cal3.png`): three month
  grids (June/July/August 2026), Monday-first, each with its own month net, days
  coloured by net, faded squares where no trades were scored, and the annotation
  naming the clamp ($754 = 80th percentile of |net|) plus the true range
  -$2,067..+$2,813. Three defects fixed in the same pass, each caught by looking:
  values over $1k clipped to "-$2,06" (now compact "-$2.1k"); the lead paragraph and
  a source line still described the bar strip that no longer existed; and every
  winning day under ~$600 rendered OLIVE, because mixing a bright green toward
  near-black in OKLCH drags lightness through a muddy region -- cells now composite
  the hue at partial alpha instead.
- [x] Card firing works end to end from the new app. VERIFIED 2026-08-30 03:53 by
  actually pressing it. Fired "CANDIDATES-UNTRACKED" from `#/cards`:
  companion-ask-results.jsonl went 82 -> 83, exactly ONE row, `origin:"card"` with
  `card_id` naming the fired card, and exactly one new `ask-*` feed file in the
  window. A second fire on the same card returned "Already fired" and spawned no
  second session. The spawned run was cancelled immediately rather than left to edit
  the repo unattended while J slept; the cancel landed mid-tool ("Stream closed").
  DEVIATION FROM THE WRITTEN CHECK, stated: this item predicted `origin:"app-card"`,
  but the server sets origin itself on the approve path and writes `"card"` -- the
  producer owns that field, not the caller, and the check was wrong, not the code.
  THE BUG THIS FOUND: the button posted to `/api/ask`, which DOES NOT EXIST on the
  companion -- there is no POST /api/ask route at all, so J's first real click would
  have 404'd. It read plausible because "the cockpit already fires cards", but the
  cockpit posts an APPROVAL decision to /api/approve and the server distinguishes a
  card fire by `id` naming a row in action-cards.json. Now also honours the two
  server behaviours the cockpit does: the RTH gate (fires refused 09:30-15:55 ET) and
  idempotency (a repeat approve returns ok WITHOUT an `escalated` id, which is a
  double-tap absorbed, not a success).
- [x] The app degrades honestly when the companion is down. VERIFIED 2026-08-30 04:0x
  by actually stopping it. With the companion killed: the view still rendered (2157
  chars, nothing blanked), the app kept its last payload, and an amber banner appeared
  reading "The companion is not answering. Everything below is from 01:59 AM and is
  not being updated." On restart it cleared. Amber not red — red belongs to P&L and a
  dead companion is degraded, not a loss. Made EVENT-DRIVEN mid-test: the banner was
  first tied to the 30s poll, so it could linger up to 30 seconds after the companion
  came back, and a stale "we are down" is the same class of lie as a stale number.
  data.load() now dispatches gamma:data and the chrome reacts to THAT load; both
  directions verified to flip within 120ms.
- [x] J can install it. VERIFIED 2026-08-30 04:0x: all 13 assets return 200
  (`app/`, manifest, icon, one css, nine js, payload.json). One SVG serves every icon
  size — no icon set to keep in sync — padded to ~78% so it survives a maskable crop.
  BUG CAUGHT IN THE SAME CHECK: the manifest was served as
  `application/octet-stream`, which Chrome IGNORES, so the app would have been
  silently NOT installable while every asset still returned 200 and nothing looked
  wrong. `.webmanifest` added to the server's MIME map; now
  `application/manifest+json`.
- [B-J] Firebase sign-in. Needs J's GCP project. DONE-WHEN:
  `automation/state/.firebase-config.json` exists and an email/password sign-in
  returns a token. Everything else is built — `auth.js` speaks the Identity Toolkit
  REST API and reads `/api/auth-config`; only the credential is missing.
- [B-J] Multi-user / admin portal. BLOCKED ON A REAL BOUNDARY, not just config: the
  companion does not verify the Firebase ID token against Google's public keys, so
  today's sign-in is an identity surface and NOT an authorization boundary. Nothing
  that matters may be gated on it until that verification plus per-user scoping of
  every existing endpoint exists. Do not ship friends access before then.
- [B-J] Should `/` become the app? J said the hero "will be the main landing page
  after sign in page", but `/` currently serves the phone PWA (`m.html`) — it is the
  manifest `start_url` and the target push notifications open. Swapping it silently
  repoints his installed phone app. One-line change in `serveStatic` once he says so.
- [B-J] ARM AUTONOMOUS CARD-FIRING? Gamma_AutofireCards is registered WEEKLY while
  its runner is written for weekdays, and it has NEVER executed once (last result
  267011 = never run). So "Gamma chooses a recommended card by itself" -- the thing J
  asked for by name on 2026-08-30 -- has never happened. The fix is one schtasks
  re-registration. NOT taken unilaterally for two reasons: the config freeze opens
  2026-08-31, and turning on unattended repo-editing sessions the day before a
  scoring window is bad timing regardless of the guards (which are real: RTH refusal,
  quiet mode, per-run and per-day caps, and a dangerous-prompt check at fire time).
- [B-J] RAISE THE CONDUCTOR'S RUN CAP? It stopped today at 6 fires against
  max_fires=4 having spent $3.67 of a $30 daily cap. The RUN COUNT is the binding
  constraint, not the money, and the count cap exists because the conductor family was
  once 93.3% of automation burn. Raising max_fires in
  automation/state/conductor-budget.json costs real tokens per extra fire, so it is a
  spend decision, not a config tweak.
- [B-J] VERIFY-A (carried from GOAL-COCKPIT-BUILD-2026-08-29) — a pulse visibly
  travels on a REAL cross-session message. Needs J to send one while watching.
- [B-J] VERIFY-B (carried) — one card click spawns exactly one escalation and a
  double-tap spawns none extra, observed by a human.

## J-DECISIONS

- The four `[B-J]` items above. Two are credentials/permissions (Firebase, friends
  access), one is a routing decision with a side effect on his phone, and two are
  human-in-the-loop verifications.
- **Nothing here needs J to keep the build moving.** The three open `[ ]` items are
  all buildable and checkable without him.

## PROGRESS LOG

- 2026-08-30 03:46 ET — goal opened, immediately after the first build night. Six
  views shipped and verified; console verified end-to-end twice. Opened with three
  open items rather than a blank queue because the work was already underway when J
  invoked the skill — the ledger is catching up to the work, not starting it.

- 2026-08-30 03:51 ET — calendar shipped.
- 2026-08-30 03:54 ET — card firing verified by pressing it; found and fixed a
  404 (the button pointed at a route that does not exist).
- 2026-08-30 04:05 ET — offline degradation and installability both shipped and
  verified against a really-stopped companion. ALL non-[B-J] items are now [x];
  every remaining item is genuinely J's.

## HONEST STATE

**Updated 2026-08-30 04:05 ET. Every open `[ ]` item is done; everything left is
genuinely J's.** The five DONE-WHEN checks:

1. **Every view renders or names its file** — MET. Six routes walked with an onerror
   trap, `errors: []`.
2. **The console is a working daily driver** — MET. Verified twice by sending real
   messages: resumed the stored session, ran a real Glob, streamed markdown that
   rendered as markup, terminal frame, state back to ready.
3. **Nothing on it lies** — MET, and this is where the night's real work went. Four
   bugs were found by LOOKING that code review would not have caught: `/api/army` is
   a pulse-delta feed and not a roster; the sign-in art's reveal left an empty panel;
   every tool logged twice; the stop button never hid. Two more were found by
   PRESSING: the Fire button pointed at `/api/ask`, a route that does not exist, and
   the manifest was served as octet-stream, which Chrome ignores — both would have
   looked fine forever while being broken.
4. **375px has no overflow** — MET by direct measurement
   (`scrollWidth === innerWidth`). A 430px headless screenshot LOOKED clipped; that
   is Chrome's minimum window width in headless, not a layout bug. Noted so nobody
   "fixes" a phantom.
5. **Reachable without ceremony** — MET. `http://127.0.0.1:4317/app/`, companion
   auto-started by its existing keepalive, and now installable.

**What is still NOT true, plainly:**

- **Sign-in cannot authenticate anyone**, by design, until J supplies a Firebase
  config. The page says so rather than accepting anything.
- **There is no authorization boundary.** The companion does not verify the Firebase
  ID token, so friends access and the admin portal are blocked on real work, not on a
  credential. Do not ship multi-user before that exists.
- **`/` is still the phone PWA.** Deliberate: swapping it would silently repoint J's
  installed app, which is his call, not mine.
- The two carried human-in-the-loop verifications (a pulse observed travelling; a
  card double-tap observed by a person) still need eyes on the screen.
