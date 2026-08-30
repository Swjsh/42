# The app — Gamma's daily driver

> Built 2026-08-30 on J's instruction: *"completely redesign the site from scratch"*,
> then *"i want this to be my daily driver, only talking to the orchestrator panel
> using full claude code capabilities, hooks for following all my rules, agent
> orchestration etc."*
>
> Sibling docs: [`COCKPIT-DESIGN-SPEC.md`](COCKPIT-DESIGN-SPEC.md) (the ratified colour
> and motion law this obeys) · [`ARCHITECTURE.md`](../specs/ARCHITECTURE.md) (how the rig
> is wired).

## Where it is

```
http://127.0.0.1:4317/app/
```

Served by `gamma-companion` from `gamma-companion/public/app/`. The companion must be
up — `Gamma_CompanionKeepalive` restarts it, and `schtasks /run /tn Gamma_CompanionKeepalive`
starts it by hand.

`/` still serves the phone PWA (`m.html`) because that is the manifest's `start_url` and
the target push notifications open. Swapping the root to this app is a one-line change in
`serveStatic`, deliberately **not** taken without J saying so — it would silently
repoint his installed phone app.

## What it is made of

Real static files that FETCH their data, not a generated blob. `gamma_home.py` writes
`gamma-companion/public/payload.json` alongside the cockpit HTML, so there is one source
of truth and the app can refresh without a rebuild.

| File | Owns |
|---|---|
| `index.html` | the shell: ambient layer, top bar, `#view` |
| `css/app.css` | the whole design system + every view's styling |
| `js/data.js` | the ONLY source of facts. Exposes `miss()`, never a fallback number |
| `js/views.js` | hero, profit/calendar, action cards, agent cards, sign-in |
| `js/chat.js` | the console |
| `js/md.js` | markdown rendering for agent replies |
| `js/art.js` | the sign-in artwork, drawn in-page |
| `js/auth.js` | Firebase sign-in over the Identity Toolkit REST API |
| `js/app.js` | hash routing, chrome, card firing |

## The five components it was built from

J chose these on 21st.dev. Each was **looked at** (via `setup/scripts/web_shot.py`,
which points headless Chrome at any URL — the in-app browser pane cannot composite
frames while he is away, which is why earlier attempts only ever read prose summaries).
The port keeps each original's *anatomy* and replaces its palette and copy.

| Reference | Ported into | Anatomy kept |
|---|---|---|
| `kinfe123/jelly-animated-hero` | the landing | ultralight giant headline over an aurora; **stat panels riding the hero's bottom edge** |
| `bhomikproductivitylab/sign-in-page` | `#/signin` | split panel, art left, form right, social auth under a divider |
| `isaiahbjork/prediction-market-card` | `#/cards` | pill row + countdown chip, headline, 3-up stat band, severity rail across the foot |
| `ravikatiyar162/dashboard-1` | `#/agents` | two stat tiles (one accent-tinted), segmented bar, CTA banner |
| `coderislive07/ai-assistat` | `#/chat` | tinted header, deep body, floating-glyph empty state, pill composer with a round send |

**The hero panels are the navigation.** J: *"I dont want a million nav panels just make
it hero panels like this and then the total profit we can click into and the calendar
page is behind that."* There is no sidebar and no tab bar; Total Profit → the calendar,
Agents Running → the agent cards, Needs a Decision → the action cards.

## The console

`#/chat` is a real Claude Code session running in this repo with the full tool set,
resumed across reloads (the sessionId is persisted server-side in
`automation/state/orchestrator-chat.json` **and** client-side, so a cold browser
continues the same conversation).

What it shows that a chat does not:

- **A tool timeline.** Every call, humanised as it happens (`Finding *.md`, not
  `mcp__x__y`). A daily driver has to be auditable *while* it works.
- **Rules, loudly.** A hook that blocks something renders as its own amber
  `BLOCKED BY A RULE` row instead of being swallowed as a generic tool error. The
  guards exist so the thing can be trusted; the silent block is the failure mode.
- **Interrupt.** `Esc` or the stop button cancels through `/api/cancel-task`. A stopped
  run is labelled stopped, never done.
- **Model switch**, which starts a fresh session — resuming a conversation onto a
  different model would be a lie about continuity.

### Keyboard

`Ctrl`/`Cmd`+`K` opens the command palette from anywhere — fuzzy-matched (prefix, then
substring, then subsequence, so `tp` finds *Total profit*), arrows + Enter, click-outside
to dismiss. Two kinds of entry: **GO** switches view instantly; **ASK** loads a question
into the composer and *deliberately does not send it* — a palette entry that starts a
Claude run on the shared Max pool from one keystroke is a footgun, and one keystroke is
exactly how it would get pressed by accident.

In the console: `Enter` sends, `Shift`+`Enter` newlines, `Esc` stops the current run.

`md.js` is hand-written because every usable markdown library arrives over a CDN. Its
order is **escape-then-format**: the input is a model reply that may contain anything a
user pasted, so it is HTML-escaped first and formatting applied afterwards. Verified in
the live page: `<img src=x onerror=…>` renders as visible text, and a `javascript:` link
stays plain text. **Do not "improve" this by letting inline HTML through.**

## Sign-in / Firebase — what is and is not wired

The surface is real; the credential is absent, and the page says so rather than
pretending. To turn it on, create the file (gitignored):

```json
{ "apiKey": "...", "authDomain": "your-app.firebaseapp.com", "projectId": "your-app" }
```

at `automation/state/.firebase-config.json`. The companion echoes **only** those three
public fields at `/api/auth-config`; `auth.js` picks it up with no further changes and
email/password sign-in starts working. For Google/GitHub, also add `127.0.0.1` to
Firebase Auth → Settings → Authorized domains and enable those providers.

> ⚠️ **This is an identity surface, NOT an authorization boundary.** The companion does
> not verify the ID token against Google's public keys yet, so nothing that matters may
> be gated on it. Multi-user and the admin portal J wants need that verification first,
> plus per-user scoping of every existing endpoint — none of which exists today.

## Honesty rules baked in

Carried over from the cockpit, because a prettier surface that lies is worse than an
ugly one:

- A panel with no number names the **file it wanted**; it never shows a plausible default.
- Present-tense agent counts come from `worker_active` only. `worker_count` is a lifetime
  total and may be spoken of strictly in the past.
- The sign-in refuses to authenticate rather than accept anything.
- No animation may own whether content exists. The sign-in artwork used to reveal itself
  over ~150 frames and an early screenshot caught an empty panel — the path is now always
  drawn and only the marker sweeps it.
