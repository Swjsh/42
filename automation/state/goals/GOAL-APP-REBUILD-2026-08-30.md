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
- [ ] Total Profit opens a real CALENDAR, not a bar chart. J asked for "the calendar
  page" behind Total Profit; what shipped is a day-bar strip. DONE-WHEN: `#/profit`
  renders a month grid of trading days coloured by net, the ramp is CLAMPED so one
  blowout day cannot wash out the month, the true min/max are annotated, and a
  headless shot at 1600px shows a recognisable calendar.
- [ ] Card firing works end to end from the new app. DONE-WHEN: clicking Fire on a
  card in `#/cards` produces exactly ONE new row in
  `automation/state/companion-ask-results.jsonl` with `origin:"app-card"`, and a
  second click within the confirm window produces none extra. Currently UNVERIFIED —
  the button is wired to `/api/ask` but has never been fired from this app.
- [ ] The app degrades honestly when the companion is down. DONE-WHEN: with the
  companion stopped, every view still renders and says the companion is unreachable
  rather than showing a blank region or a stale number presented as current.
- [ ] J can install it. DONE-WHEN: `gamma-companion/public/app/` ships its own web
  manifest + icon and a headless load shows no 404s in the network log, so the app can
  be pinned like a native one.
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

## HONEST STATE

The site exists, is committed, and works. What is NOT yet true, stated plainly:

- **`#/profit` is a bar strip, not the calendar J asked for.** Closest gap to his
  literal words, and the top open item.
- **The Fire button on action cards has never actually been pressed from this app.**
  It is wired to the same `/api/ask` the cockpit uses, and that path was verified
  from the cockpit — but "the same endpoint works elsewhere" is not evidence about
  this button, and it will not be claimed until one real fire is observed.
- **Sign-in cannot authenticate anyone** and says so on the page. That is by design
  until J supplies a Firebase config; it is also why multi-user is blocked on more
  than a credential.
- The cockpit at `analysis/home/index.html` is unchanged and still generated — this
  app is additive, and nothing was deleted to make room for it.
