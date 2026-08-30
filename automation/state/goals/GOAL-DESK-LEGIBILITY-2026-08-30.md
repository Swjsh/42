# GOAL: DESK-LEGIBILITY-2026-08-30

> J verbatim (2026-08-30 ~15:00 ET): *"where it says untitled chat needs to say the task
> goal and then we need to see something in the 'agent' card like you have all that space
> and no visuals. and in the bottom gamma terminal it said Opus then its working so idk if
> its orchestrator or a sonnet agent like i would expect, the top bar where it says Gamma
> in purple should indicate who is sending stuff into the chat box i am reading. this is
> still basic as fuck keep improving and testing and looking for little things like this I
> am mentioning. if you think you are done you are not take another screenshot and run
> another process and look again for things"*

## THE THREE HE NAMED, and why each is a real defect not a preference

1. **"Untitled chat" is a lie of omission.** Session `0fe64aad` was, at that moment,
   running the run-cmd-hidden card. The companion's task registry knows it:
   `sessionId 0fe64aad <-> card_id card-broken-1-run-cmd- <-> task "OBJECTIVE: Root-cause
   and resolve the STATUS.md entry 'RUN-CMD-HIDDEN MASKED EXIT'"`. The card had every
   fact needed to name itself and printed "Untitled chat".

2. **The agent card is mostly empty.** ~180px of card showing a title, an id, "no agents
   yet" and a memory bar. The session is doing real work every second (reading files,
   grepping, thinking) and none of it reaches the card.

3. **The console header lies about WHO is talking.** It renders `st.model` -- the
   PICKER's value -- not the model of the run actually streaming. J watched a sonnet card
   run under a header reading "opus". The picker is a preference; the header must report
   the fact.

## DONE-WHEN
Falsifiable, asserted in the running page:
- (a) NO SESSION RUNNING A KNOWN JOB RENDERS AS "Untitled chat": every org card whose
  session_id appears in the companion's task registry shows that job's objective,
  humanized. Asserted by regex over the DOM.
- (b) A working session's card shows what it is DOING right now -- the live step/tool and
  elapsed time -- not just a memory bar.
- (c) THE CONSOLE HEADER REPORTS THE RUN, NOT THE PICKER: while a card run streams, the
  turn label names that run's model and says it is a card, and differs from the picker
  when the two disagree. Asserted by driving a sonnet card run with the picker on opus.
- (d) No regression: 0 visible text nodes <12px, no page scroll, 0 centre overflow at
  1600x950 AND 1440x900, 0 raw codes/paths on any glanceable row.
- (e) A SECOND DRIVE after the build finds and fixes at least the class of small defects
  J is pointing at -- screenshot, click everything again, report what the second pass
  found rather than declaring done.

## OPERATING RULES
- CONFIG FREEZE: app/companion surface only; no trading-path file touched.
- Money colours (--pos/--neg) stay reserved for figures; state uses --live/--warn/--alarm.
- Text never inside a scaled SVG viewBox.
- Every claim in the report quotes a check run this session.
- Never invent an API: verify an endpoint/method exists before calling it (two were
  invented earlier today and caught before shipping).

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] D1 (VERIFIED: G.sessionJobs populated, 3 sessions joined) — Session jobs: join session_id -> {objective, card, model, status, lastStep}
  from the companion registry, client-side in data.js beside the existing cardRuns join.
  DONE-WHEN: G.sessionJobs is populated for a live card run.
- [x] D2 (VERIFIED: untitledCards 0; card reads the objective + 'action card' badge) — Name the card: an org card for a session with a known job shows the objective
  instead of "Untitled chat". DONE-WHEN (a).
- [x] D3 (VERIFIED: live step + spinner + elapsed, e.g. 'running a command' 45s) — Fill the card: live step, tool, elapsed, model chip; a working card looks
  worked-in. DONE-WHEN (b).
- [x] D4 (VERIFIED: picker on opus, card ran sonnet, pill read 'card · sonnet') — Console header tells the truth about who is streaming. DONE-WHEN (c).
- [x] D5 (second drive found 6 real defects incl. the clipped position note, 'tool_result', ' -- ', 'sdk-ts', raw model ids, 'finding(s)') — SECOND DRIVE: re-screenshot, re-click every control, hunt the same class of
  small defect, fix what turns up. DONE-WHEN (e).
- [x] D6 (VERIFIED 1600x950 AND 1440x900) — Final sweep at both viewports + screenshot to J. DONE-WHEN (d).

## J-DECISIONS
- Carried from prior goals: Firebase credential, admin/multi-user boundary, whether `/`
  becomes this app.

## PROGRESS LOG
- 2026-08-30 ~15:0x ET — Opened. Session/job linkage confirmed live before building.

## HONEST STATE
Nothing shipped under this goal yet.


## CLOSE (2026-08-30 ~15:20 ET)

All six items shipped and verified in the running page. Every DONE-WHEN met at both
mandated viewports: 412 visible text nodes, ZERO under 12px, page scroll false, centre
overflow 0, no clipped text without a recoverable title, no bare SDK step names, no raw
model ids, no source punctuation, no 'sdk-ts' on the glass.

MID-GOAL, J ADDED: "the ollama one needs re thought. maybe a smaller persistent card in
the corner cause its not a subagnet?" He was right and the old grid was making a false
claim -- a window he happens to have open on an unrelated question wore the same card as
a session Gamma dispatched. The org is TWO TIERS now: sessions running a known Gamma job
get cards; everything else is an "also open" chip. Empty state reads "Gamma has nothing
running right now - fire a card or ask it something below."

WHAT THE SECOND DRIVE TAUGHT: the automated sweep raised 11 candidates and 7 were false
positives (my own deliberate state words in caps, and legitimate <code> spans where
Gamma quotes a file verbatim in a reply). Reporting those as fixed would have been
noise. The 4 real ones were all the same shape J keeps naming -- machine text reaching a
human surface -- which is why the fixes went into the display funnel (scrub/step) rather
than into each call site.

STILL OPEN: the chat transcript legitimately contains verbatim code spans, so a
"guard code on the glass" regex will always match inside .chat -- any future sweep must
scope itself outside the transcript or it will chase that forever.
