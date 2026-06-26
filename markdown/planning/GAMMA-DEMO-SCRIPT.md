# Gamma — "Show a Friend" Demo Script

> The exact 2–3 minute sequence J runs to wow someone, with nothing failing.
> Written 2026-06-21 on top of the demo-hardened companion (guard + token + halt shipped 14/14;
> 8 demo-killers patched + verified). Sources: `markdown/planning/GAMMA-NIGHT-BRIEF-2026-06-20.md`,
> `analysis/_demo-polish-2026-06-21.md`, `analysis/_demo-reliability-2026-06-21.md`.
>
> **The one rule of this demo:** lead with what's *instant and live* (status → instant diagram → voice),
> and keep the live "ask Claude to build something" escalation as the **finale**, never the opener.
> Everything in the green path below answers in <2s from already-loaded state. The slow paths are flagged.

---

## 0. The 60-second pitch (say this while it opens)

> "This isn't a mockup. It's a real autonomous 0DTE SPY options trading system that's been running 24/7
> for weeks — two live paper accounts, a heartbeat that ticks every few minutes during market hours, and
> a research 'kitchen' that's quietly run **800+ jobs** improving the strategy overnight. This app is its
> face — I can talk to it, ask it how it works, and watch it build *itself* safely while I hold the off-switch."

That's the whole story. The screen backs every clause of it. Now run the four beats.

---

## 1. Pre-flight (do this BEFORE the friend is watching — ~30 seconds)

A short checklist that removes every known live-demo failure. Do it once, then close the laptop and reopen it in front of them.

1. **Launch the desktop app** — double-click **`LAUNCH-GAMMA.vbs`** on the Desktop (path: `C:\Users\jackw\Desktop\42\LAUNCH-GAMMA.vbs`).
   - It runs the Electron shell (`npx electron .`), not a browser tab. **This matters:** Electron auto-grants the microphone, so voice "just works" with no permission popup. A browser tab would block the mic.
   - You get its own window + taskbar entry. No terminal, no tabs.
2. **Wait for the status pill (top-right) to read "live"**, not "connecting…". It starts amber ("connecting…") and goes green on the first state poll (a few seconds). If it stays amber >10s, the server didn't boot — close and relaunch.
3. **Seed the approval loop** so the "Needs your OK" panel has something real to click:
   `node gamma-companion/seed-demo.js`
   (Drops two clearly-labelled DEMO approvals — a "ship VWAP v2 live?" and a "Bold down 18%, keep trading?" — into the queue.)
4. **If you plan to demo voice:** confirm the machine has internet and the OpenAI key has Realtime credit. If you're unsure, **skip voice and type instead** — the typed path is identical and 100% reliable. (See Known Limits.)
5. **Optional, only if you'll do the live "build something" finale:** run `node gamma-companion/smoke-sdk.js` once to confirm the Claude SDK auth works headlessly. If it errors, skip the finale and end on the diagram instead.

> If you skip the checklist entirely, the app still degrades gracefully (amber not red, offline rows instead of frozen "Loading…", voice falls back to typed). But 30 seconds of pre-flight removes the *one* thing that could make it look fake.

---

## 2. THE DEMO (2–3 minutes, four beats)

### Beat 1 — "This is a real, live system" (point, don't click — ~30s)

Open cold in front of them. The robot greets, the tiles fill in. Walk their eye across the screen:

- **Top-right status pill** → "It's connected to the live market data feed right now — see, *live*."
- **The four status chips along the bottom-right** → **Safe** and **Bold** (the two real paper accounts with live equity), **Engine** (the heartbeat — is it ticking), **Kitchen** (the 24/7 research loop).
  - "Two accounts — a conservative one and an aggressive one — running the *same* strategy at different risk so we can see which compounds better."
- **The Live feed (big tile, right)** → real rows from the kitchen and the engine. "This is its actual activity, not filler."
- **The "Kitchen" chip / feed** is the kill-shot line: *"That research loop has run over 800 jobs overnight — for about $0, on free models — hunting for a better strategy while I sleep. This is a system that improves itself."*

> Why this beat first: it's all already-loaded state, zero latency, and it earns the word "real" before you touch anything.

### Beat 2 — "Gamma, show me how you work" (the instant diagram — ~30s)

Tap the **"▦ Diagram it"** quick-action chip (top-left, under the robot). It's pre-wired to the phrase *"Draw me a diagram of how the whole system works."*

- **This renders the INSTANT hand-crafted system diagram** — it appears immediately, no waiting. (This is the one to use in a live demo; see Known Limits about *custom* diagrams.)
- The diagram opens in a focus pane. **Tap a node to drill in** — each node has follow-up chips ("Explain this", "Show me the code path") that ask Gamma about that piece.
- Narrate one node: "Tap the heartbeat — that's the loop that reads the chart every few minutes and decides whether to trade. Tap the guard — that's the safety rail I'll show you in a second."
- Tap the **back/close** (top-right of the focus pane) to return.

> Why this beat: it makes the abstract concrete in five seconds, and the tap-to-drill interaction feels like a real product, not a slide.

### Beat 3 — "Talk to it" (voice if the venue allows, otherwise type — ~45s)

**If internet + mic are good:** tap the **mic** button (bottom ask-bar). The robot lip-syncs — rings pulse, it shows "Listening…". Ask one of the safe, fast prompts below out loud. It answers in its own warm, brief voice and the robot "talks" back.

**If the venue mic is sketchy or you skipped voice:** just **type** the same prompt into "Ask Gamma anything…". The robot still lip-syncs the spoken reply (if spoken replies are toggled on, top-right speaker icon), so it still feels alive. The typed path is the reliable one — don't be shy about using it.

**Safe prompts that answer fast from live state** (these don't need the slow free-model brain to think hard — they read loaded numbers):

- *"How are both accounts doing right now?"* (also a quick-chip: **★ Accounts**)
- *"What are today's key levels?"* (quick-chip: **☰ Key levels**)
- *"What's the plan today?"* (quick-chip: **⚡ What's the plan?**)
- *"What did the kitchen work on overnight?"*

> Use the quick-chips rather than typing where you can — they're pre-written to hit the fast paths. Tapping **★ Accounts** is the single best "wow, it knows its own state" moment.

### Beat 4 — "It builds itself overnight — safely" (the story + the finale — ~45s)

This is the closer. Two parts: the *safety story* (always safe to tell), then an *optional live build* (only if you ran the smoke test).

**The safety story (always do this):**
- Point at the **"Needs your OK"** panel (the seeded demo approvals). "Gamma proposes changes — like shipping a new strategy — but it can't ship them itself. I approve or reject. Watch." **Tap "Not yet" / "Approve"** on a demo card — it logs the decision and clears.
- The line that lands: *"There's a hard guard in the code — not a promise, actual code, tested 14 out of 14 — that physically stops Gamma from editing its own trading rules, touching the account keys, or placing a real order. It can build and propose all day. The dangerous surface is closed at the code level. And there's a single kill-switch file that halts the whole thing."*
- "Every morning I wake up to a brief: here's what I built overnight, here's what it costs, here's what needs your call. That's the loop."

**The optional live finale (only if `smoke-sdk.js` passed in pre-flight):**
- In the ask-bar, type something like: *"Build me a tiny status badge that shows the kitchen job count."*
- This escalates to the real Claude Agent SDK. **It takes 30–90 seconds** — narrate while it works ("this is the real model, actually writing code against the project, behind the guard"). When it lands, the result appears in chat / the feed.
- **If it's slow or you're short on time, DON'T start this.** End on the safety story instead — it's the stronger, safer close.

---

## 3. The closing line

> "So that's Gamma. A real autonomous trading system, a face I can talk to, a picture of how it works, and a guard that lets it improve itself overnight without ever being able to do anything dangerous — while I keep the off-switch. It's been running this whole time."

---

## 4. KNOWN LIMITS — what to avoid in a live demo (read this)

Honest list. None of these break the demo *if you follow the script*; they break it if you go off-script.

| # | The trap | What to do instead |
|---|---|---|
| 1 | **Custom live diagrams take ~1–2 minutes.** If you ask "draw me a diagram of *the kitchen's model ladder*" (anything specific), it escalates to Claude and you stare at a spinner. | **Stick to the "Diagram it" chip** → it routes to the *instant* hand-crafted diagram. Only the instant one is demo-safe. The app falls back to the instant diagram on timeout, but don't rely on that live. |
| 2 | **Voice needs internet + OpenAI Realtime credit.** No connection, dead/no-credit key, or a churned model id → the mic can't connect. | The app auto-falls-back to typed and shows a friendly "just type to me" message — but **if you're on flaky venue wifi, plan to type from the start.** Voice is a bonus, not a dependency. Verify the key has Realtime credit in pre-flight if you want it. |
| 3 | **Don't ask it to place a trade.** ("Buy me some SPY calls.") | It will **correctly refuse** — that's actually a great moment if you *frame it as a feature* ("watch, it won't — the guard blocks order placement"). But don't expect a trade to happen; nothing will, by design. |
| 4 | **Don't ask it to edit its own rules / params / the soul file.** | Same as above — the guard blocks it. Good to *demonstrate* the refusal on purpose; bad to expect it to comply. |
| 5 | **The free-model typed brain can be slow / rate-limited** if you fire many heavy questions back-to-back. First question of the session can be a cold start. | Pre-warm in pre-flight (the app fires a throwaway hello on open). Keep demo questions to the **fast state-reading prompts** in Beat 3. A watchdog swaps "thinking…" to "still thinking — the free brain is slow" so it never looks frozen, but don't push it. |
| 6 | **The live "build something" escalation takes 30–90s** and depends on SDK auth. | Only attempt it if `smoke-sdk.js` passed in pre-flight, and only if you have the time + attention budget. Otherwise close on the safety story. |
| 7 | **Bottom-nav tabs (Today / Tasks / Reminders / Notes) are stubs** — they say "coming soon." | Don't tap them. Mention "Home is the live cockpit" if asked. |
| 8 | **After-hours / weekend, the live feed and accounts are quieter** (market closed). | The status pill honestly reads "live · market closed." That's fine — the *kitchen* is still 24/7, so lean on the 800+ jobs + the diagram + voice, which don't depend on market hours. Run `seed-demo.js` so the approvals panel isn't empty. |

---

## 5. One-glance cheat sheet (tape this next to the laptop)

```
PRE-FLIGHT (before they watch)
  1. Double-click  LAUNCH-GAMMA.vbs
  2. Wait for top-right pill → "live"  (amber→green)
  3. node gamma-companion/seed-demo.js
  4. Voice? need internet + OpenAI credit, else just TYPE
  5. Live-build finale? run smoke-sdk.js once

THE 4 BEATS (2–3 min)
  1. POINT: status pill (live) · Safe/Bold/Engine/Kitchen chips · feed · "800+ jobs"
  2. TAP "▦ Diagram it" → instant diagram → tap a node to drill in → close
  3. TALK (mic) or TYPE → "★ Accounts" / "☰ Key levels" / "⚡ What's the plan?"
  4. "Needs your OK" → tap Approve/Not-yet → the guard story (14/14, can't trade/edit/place orders)
     [optional finale: type "build me a tiny X" → live Claude, 30–90s]

DON'T
  - custom diagrams (slow) — use the chip
  - rely on voice on bad wifi — type
  - expect a trade or a rule-edit — it refuses (frame as a feature)
  - tap the stub nav tabs
```
