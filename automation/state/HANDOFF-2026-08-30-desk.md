# HANDOFF — the desk / command center, 2026-08-30 evening

Paste the block under **PROMPT** into a fresh session. Everything below it is the
evidence that prompt is standing on, kept here so the next session can verify rather
than trust.

---

## PROMPT

> You are picking up Project Gamma's single-pane-of-glass desk at
> `http://127.0.0.1:4317/app/#/desk`, served by `gamma-companion` from
> `gamma-companion/public/app/`. Read `CLAUDE.md`, then `MAP.md`, then this file's
> STATE section before touching anything.
>
> **The standing instruction from J, in his words:** *"keep improving and testing and
> looking for little things like this I am mentioning. if you think you are done you are
> not — take another screenshot and run another process and look again."* Treat that as
> the loop: build → drive the page yourself → screenshot → find the next small lie →
> fix → repeat. Do not hand him one fix at a time and do not ask him to test.
>
> **How to drive it** (this is the part that actually finds bugs): open the page in the
> in-app browser, `resize_window` to 1600x950, and CLICK EVERYTHING via
> `javascript_tool` — every button, the ✕ on a card, the calendar, the palette, Esc,
> the model picker. Then assert over the DOM: computed font sizes, page scroll, centre
> overflow, machine text on glanceable rows. Screenshot with
> `python setup/scripts/web_shot.py <url> --name x --width 1600 --height 950 --wait 16`
> (retry if the PNG comes back ~1970KB — that is a blank render) and then LOOK at it.
>
> **First item, and J asked about it directly: THERE IS NO COMPACTION CONTROL.** The
> orchestrator hero reads `100% memory · compacting soon` and offers nothing to do about
> it. Two separate facts: (1) the page CANNOT compact session `42-dd` — that is J's own
> Claude Code desktop process, a different process entirely; only auto-compaction or J
> running `/compact` there will do it. (2) The page CAN start the console's own session
> fresh — `/api/orchestrator-chat` accepts `fresh: true` and **the client never sends
> it** (`grep -n fresh gamma-companion/public/app/js/chat.js` → nothing). So there is a
> real, unexposed capability and a warning with no action. Decide honestly which of
> those to build and say plainly which sessions a button can and cannot touch.
>
> Everything you claim must quote a check you ran this session. Never invent an API —
> two were invented today (`/api/ask-token`, `chat.note`) and caught before shipping
> only because they were verified first.

---

## STATE (all verified 2026-08-30, quote these rather than re-deriving)

**26 commits today.** Four goals opened and closed, all in
`automation/state/goals/`, each with an honest CLOSE section naming what it did NOT do:

| goal | what it did |
|---|---|
| `GOAL-APP-REBUILD` | the app itself, from J's five 21st.dev components |
| `GOAL-DAILY-DRIVER-GLASS` | readable org (no text in scaled SVG), humanized feed, live wire |
| `GOAL-COMMAND-CENTER` | put TRADING on the glass — it rendered 3 of 18 payload sections |
| `GOAL-DESK-LEGIBILITY` | name the running session, fill its card, header reports the run |

**The page today.** Full-width trading band (book $23,660 · net +$1,815/39 sessions ·
equity curve · today · position · live SPY tape). Left rail: engine mind, 4 arms, 5
research lanes. Centre: autonomy line, the org, the console. Right rail: decision queue
with Run + ✕, then the activity feed. Click NET → P&L by session (also `#/pnl`).

**Data flow.** `/api/desk` (4s cache) shells `setup/scripts/desk_live.py`, which returns
four fast slices: `army`, `autonomy`, `lanes`, `glass` (+`card_runs`). `data.js` overlays
them on the baked `payload.json` and additionally joins `/api/state` into
`G.sessionJobs` and `G.cardRuns`. **The baked payload is the floor, the live path is
authoritative** — an equity or a position at payload age is a wrong answer, not a stale
one.

**Guards (94 green).** `backtest/tests/test_{gamma_glass,gamma_lanes,app_motion_law,
companion_guard_trading_path,quiet_mode_weekend_research}_2026_08_30.py`. The motion-law
file is the one that catches design regressions statically.

## LAWS THIS SURFACE OBEYS — breaking one is a defect, not a style choice

1. **Every number is sourced or absent.** `money()` returns null for a missing value;
   `dash()` renders an em-dash naming the file it wanted. A fabricated $0.00 P&L is
   indistinguishable from a flat session.
2. **Never animate a property whose from-state is invisible, and never let motion own a
   value.** A suspended animation (hidden tab, headless capture) never leaves its active
   period, so `from{opacity:0}` pins an element at invisible forever — the P&L sheet
   shipped that and measured opacity 0 three times. `roll()` writes the final number
   *before* the first rAF for the same reason.
3. **--pos/--neg are RESERVED for money.** State uses `--live`/`--warn`/`--alarm`.
   POSITION:UNKNOWN is amber, not red — nobody lost money.
4. **Text never inside a scaled SVG viewBox.** That shipped twice as "size two font".
5. **No machine text on a glanceable row.** Everything goes through `humanize.js`
   (`scrub`, `broken`, `commit`, `step`); raw records live in `title` attributes.
6. **Nothing under 12px**, no page scroll, columns scroll internally.

## KNOWN OPEN — not hidden, deliberately listed

- **No compaction control** (the prompt's first item).
- `cost_meter` is the one payload section still not surfaced — absent by choice.
- A prior card run that is **still running** is reported, not re-attached: no endpoint
  mints a stream token for a run this page did not start.
- Card run-state after a companion restart comes from `companion-asks.jsonl` and reads
  "outcome not recorded" — the in-memory registry has the outcome and dies with the process.
- **Autofire's first real unattended fire is still unproven** (Mon 23:30 ET). It was
  mis-scheduled inside the quiet window and that is fixed but never observed firing.
- `[B-J]` across three goals: Firebase credential, the admin/multi-user boundary (the
  sign-in is an identity surface, NOT an authorization boundary — nothing may gate on it
  until token verification exists), and whether `/` becomes this app (it would repoint
  J's installed phone PWA).

## TRAPS THAT COST REAL TIME TODAY

- **A `\b` written through a shell heredoc can land as a literal 0x08 byte.** grep,
  JSON.stringify and the terminal all render it as `\b`, so the source looks right and
  the regex matches nothing. Three were live. `test_app_motion_law` now scans for stray
  control bytes — keep that guard.
- **`cat >> file` chained behind a failing command silently does nothing** (`&&`
  short-circuits). Shipped unstyled CSS that way once.
- **`el(...)` in the app takes a CLASS NAME, not a tag** — `el('details')` builds
  `<div class="details">`.
- **Verify test harnesses before believing them.** Two of mine were wrong before the code
  was: dispatching Escape at the window when the handler was on an input, and
  `document.body.focus()` (body is not focusable, so focus never moved).
- **Screenshots**: a ~1970KB PNG is a blank render; retry.
- **Never restart the companion mid-verification** — it wipes the in-memory task registry
  and card state reverts to "new".
