# Gamma Companion — Watch Claude Work Live + Fix the Approval Loop

**Date:** 2026-06-21 · after-4pm work block · plan-of-record
**Scope:** `gamma-companion/` only. No production doctrine, params, or heartbeat touched.
**Author:** research+audit synthesis (4 parallel findings, all cross-checked against the live files read 2026-06-21).

J's two demands:
1. The approval / task loop must work **end to end** — click checkmark/X → card actually clears (and stays cleared) → the underlying work runs → the display reflects it. Today obligation cards regenerate from live state so they bounce back, and approving an obligation runs a read-only *diagnosis* that can never satisfy the obligation.
2. J wants to **SEE Claude working** on his PC in real time — tool calls, file edits, commands, reasoning — like watching Claude Code in a terminal, not a black box.

---

## 0. Ground truth (what the files actually do today)

Verified by reading the real source, not the prose contracts:

| Concern | File:lines | Reality |
|---|---|---|
| Escalation chokepoint | `lib/escalate.js:120-134` | `for await (const message of query(...))` body **only** handles `message.type === "result"`. Every `assistant` (tool_use/text/thinking), `user` (tool_result), and `system/init` message is silently dropped. **No `includePartialMessages`** in the options block (121-127). This is the black box. |
| Abort / cancel | `lib/escalate.js:110-111,126,138` | Already correct: `AbortController` created, passed as `options.abortController`, tracked in `controllers` Map, `cancelTask()` aborts, `ac.signal.aborted` distinguishes cancel vs error. **Survives the streaming refactor unchanged.** |
| Task registry | `lib/escalate.js:33-59` | `tasks` Map tracks status only (running/done/...). `getTasks()` exposes `running`/`recent`. No steps, no `sessionId`. |
| Obligation cards | `server.js:298-334` | `fullState()` calls `checkObligations(ROOT)` **every** `/api/state` poll, rebuilds `obCards` fresh, **prepends** to `state.approvals` (320). Card ids are `oblig-<id>` — synthetic, function of live state only. |
| Approve resolution | `lib/approvals.js:112-152` | `resolveApproval` removes `id` from `companion-approvals.json`. Synthetic obligation cards were **never written there** → it removes nothing → next 5s poll regenerates the card. **Root cause of bounce-back.** |
| Obligation "fix" task | `server.js:310-318` | The approve action is `escalate` with task = "Diagnose ... propose or apply a SAFE fix ... **Report findings.**" — read-only. Even on success the evidence file is still stale → `checkObligations` still `!ok` → card returns. **Approving can never clear it by design.** |
| Desktop UI | `public/app.js:130-146,246-261` | `decide()` **already** calls `trackAsk(j.escalated)` (138); A-1 retry affordance **already** present (140-145). `trackAsk` polls `/api/ask-result` for the FINAL blob only. Cards are cleared by `card.textContent=` mutation + `refresh()`, **not** a `dismissed` map → on desktop the regenerated card visibly returns on the next poll. |
| Mobile UI | `public/m.html:191,230-242` | Has a client-side `dismissed{}` map (191) + optimistic `vanish()` so cards stay hidden. BUT on `j.escalated` it only `addAsk("Gamma","On it…")` — a **static string**; it **never calls `trackAsk`** → the PWA shows zero progress and never the result for a card-approved build. **Mobile dead-end.** |
| Polish doc | `_REMAINING-POLISH-2026-06-21.md` | S-1 (state.js guard) and A-1 (retry affordance) are **already applied** in the current files. Remaining un-applied: A-2, A-3, A-4, A-5, A-6, R-1, C-1..C-7, G-1, G-2, SV-1. |
| SDK | `package.json:13` | `@anthropic-ai/claude-agent-sdk ^0.3.185`. `includePartialMessages` is the documented flag for `stream_event` deltas. `smoke-sdk.js` proves the path works. |

---

## 1. Reuse vs build (do NOT reinvent)

**Decision: build a thin streaming + SSE layer on top of the existing single chokepoint. Reuse the SDK's own streaming API. Do NOT clone any external project.**

| Candidate | Verdict | Why |
|---|---|---|
| **Claude Agent SDK `includePartialMessages` + the `assistant`/`user`/`stream_event` message stream** | **REUSE — this is the whole engine** | Official, documented (code.claude.com/docs/en/agent-sdk/streaming-output), already imported in `escalate.js`, already proven by `smoke-sdk.js`. The data J wants to see (tool names, file paths, commands, reasoning, live typing) is *already emitted* by `query()` — escalate.js just throws it away. One flag + one dispatcher unlocks it. |
| **SSE via Node `http` (`text/event-stream`)** | **REUSE Node built-ins — build the endpoint** | Zero new npm deps (matches the companion's zero-dep server). Browser-native `EventSource`, auto-reconnect, HTTP-only — no WebSocket handshake, no second port, preserves the 127.0.0.1-only safety model. |
| `ninehills/claude-agent-ui`, `hoangsonww/Claude-Code-Agent-Monitor`, `patoles/agent-flow` | **DO NOT clone** | They are full *rewrites* of the orchestrator with their own approval/task systems. Adopting any means ripping out the existing guard/obligation/approval wiring. We borrow one idea only: their per-tool *humanize* rendering ("Reading X", "Ran: cmd") — re-implemented in ~30 lines, not vendored. |
| `xterm.js` + `node-pty` / `ttyd` (real terminal) | **DEFER to Phase 3, probably never** | The escalation is **headless SDK** — there is no shell process and no Claude window to mirror. A PTY would only show a *new* shell we'd have to drive separately; it does not show what the SDK agent is doing. The faithful in-app equivalent of "watch Claude Code" is the streamed tool/edit/command transcript (Phase 1), which needs **zero** new deps. `node-pty` also adds a native-module/conpty build dependency on Windows — fragility we don't need. Only build it if J explicitly wants an interactive shell pane *in addition*. |

**Bottom line:** the leanest path that satisfies both demands is ~entirely first-party. The SDK already produces the feed; we stop discarding it, persist it per-ask, and push it over SSE to a transcript panel that both frontends already have the scaffolding for (`addAsk`/`addMsg` + `trackAsk`).

---

## 2. Watch Claude work live — concrete design

### 2.1 Capture (lib/escalate.js)

Add **one flag** and replace the result-only loop with a **message dispatcher**.

```js
// options block — add:
includePartialMessages: true,

// loop body — replace the single `if (message.type === "result")`:
for await (const m of query({ prompt: task, options: {...} })) {
  if (m.type === "system" && m.subtype === "init") {
    sessionId = m.session_id;
    emit(id, { step: "session", sessionId, model: m.model, tools: (m.tools||[]).length });
  } else if (m.type === "assistant") {
    for (const b of (m.message?.content || [])) {
      if (b.type === "text")     emit(id, { step: "text", text: b.text });
      else if (b.type === "thinking") emit(id, { step: "thinking", text: b.thinking });
      else if (b.type === "tool_use") emit(id, { step: "tool", name: b.name, label: humanize(b.name, b.input) });
    }
  } else if (m.type === "user") {
    for (const b of (m.message?.content || [])) {
      if (b.type === "tool_result") emit(id, { step: "tool_result", ok: !b.is_error, preview: String(b.content||"").slice(0,200) });
    }
  } else if (m.type === "stream_event") {
    const e = m.event;
    if (e.type === "content_block_start" && e.content_block?.type === "tool_use")
      emit(id, { step: "tool_start", name: e.content_block.name });
    else if (e.type === "content_block_delta" && e.delta?.type === "text_delta")
      emit(id, { step: "delta", text: e.delta.text });
    // thinking_delta / input_json_delta optional — text_delta is the live-typing win
  } else if (m.type === "result") {
    resultText = m.result || resultText;
    subtype = m.subtype || "";
    ok = m.subtype === "success" && !m.is_error;
    emit(id, { step: "result", ok, subtype, cost: m.total_cost_usd, ms: m.duration_ms });
  }
}
```

`humanize(name, input)` maps tool calls into J's language:
- `Read` → "Reading " + basename(file_path)
- `Edit`/`Write` → "Editing " + basename(file_path)
- `Bash` → "Ran: " + command.slice(0,80)
- `Grep` → "Searching: " + pattern
- `Glob` → "Finding " + pattern
- `mcp__*` → the MCP tool name
- default → the raw tool name

`emit(id, rec)` does two things, both best-effort/never-throws:
1. **Durable trace:** append `rec` to `automation/state/companion-ask-feed/<id>.jsonl` (mkdir the dir like `appendResult` does). A late-joining or reconnecting client replays this to catch up.
2. **Live push:** write `data: <json>\n\n` to every SSE response currently subscribed to `<id>`. Maintain `Map<id, Set<res>>` plus `subscribe(id,res)`/`unsubscribe(id,res)`, exported from escalate.js.

Capture `sessionId` into the task registry (`setTask(id, { sessionId })`, expose via `slim()`/`getTasks()`) so a future "continue this build" can call `runEscalation` with `options.resume = sessionId`. (Resume UI is optional follow-up, not in this release.)

**Guard interaction (important):** `includePartialMessages` does NOT bypass `makeCanUseTool` (guard.js). A `tool_start` for a denied tool will still stream — the actual execution is gated and the deny surfaces in `result.permission_denials[]`. The transcript will honestly show "Using Edit…" then the result/deny. Fine.

### 2.2 Transport (server.js) — new SSE endpoint

```
GET /api/ask-stream?id=<askId>&tok=<token>
  content-type: text/event-stream; cache-control: no-store; connection: keep-alive
  1. replay existing companion-ask-feed/<id>.jsonl lines as data: frames (catch-up)
  2. subscribe(id, res) for live frames
  3. on req 'close' → unsubscribe(id, res)
```

Auth nuance: `EventSource` **cannot set headers**, so it can't carry `x-gamma-token`. Mirror the existing signed-token pattern (`push.mintApproveToken` / `/api/approve-signed`): mint a short-lived per-ask **stream token** when the ask is created and pass it as `?tok=`. (Or, given the server is 127.0.0.1-only and the stream is read-only telemetry, accept same-origin without a token — but the signed-token path is the consistent, safe choice and reuses existing crypto.)

Keep `/api/ask-result` as the durable final-summary fallback for reconnect.

### 2.3 Render (public/app.js + public/m.html) — the "Gamma sandbox panel"

Both frontends already have a transcript area (`addMsg`/`addAsk`) and `trackAsk`. Upgrade `trackAsk(askId)` to:
1. Open `new EventSource('/api/ask-stream?id=' + askId + '&tok=' + tok)`.
2. Render each step as a live transcript row:
   - `tool` / `tool_start` → "▸ Reading state.js", "▸ Ran: pytest …", "▸ Editing escalate.js"
   - `text` / `delta` → Claude's narration, appended/typed live
   - `thinking` → dimmed reasoning line
   - `tool_result` → "✓ done" / "✗ error" with the short preview
   - `result` → final summary + "Done in 4.2s · $0.03", then `es.close()`
3. **Fall back to the existing `/api/ask-result` polling** if `EventSource` errors (`onerror`) — so a blip degrades gracefully to today's behavior instead of a blank.

This is J's in-app "watch Claude work" surface — it mirrors a Claude Code terminal without a terminal, with zero new deps.

### 2.4 Terminal / real-window extras — explicitly out of this release

- **Phase 3a (optional, only if asked):** `xterm.js` + `node-pty` modal pane for an *interactive* shell — adds a native dep and a second IO model. Not load-bearing; the transcript already proves "Claude is running commands on your PC."
- **Phase 3b (optional, only if asked):** Electron main spawning a visible `claude --print` window. The companion runs as a Node HTTP server today, not the Electron renderer; this fragments into two windows. Skip unless J specifically wants the actual Claude window.

---

## 3. Redesigned approval loop (click → display → work done → reflected)

The current loop conflates two different things: **"I've acknowledged this"** (should clear the card) and **"the evidence is now fresh"** (the real fix the build works toward). Separate them.

### 3.1 Make obligation/derived cards honestly resolvable (server truth, not a client hack)

- **Ack/snooze store:** `automation/state/companion-card-acks.json`, keyed by `oblig-<id>` → `{ until_iso, evidence_sig }` where `evidence_sig` is the obligation's `detail` (or evidence mtime). Written by `resolveApproval` when the id starts with `oblig-`/`act-` (synthetic, not in the file queue): snooze ~30-60 min.
- **`fullState()` suppression** (`server.js:302-320`): before prepending `obCards`, filter out any whose `oblig-<id>` is acked AND not expired AND the `evidence_sig` is unchanged. The card actually clears and **stays** cleared until the snooze lapses OR the evidence genuinely changes (then it correctly re-surfaces — we never permanently hide a real red).
- **Retire the client `dismissed{}` hack** as the *source of truth*: m.html's `dismissed{}` (191) becomes a pure optimistic-paint that the server snooze now backs, so it survives reload. Port the same optimistic-hide into app.js `renderApprovals`/`decide` so the desktop card vanishes immediately and doesn't flicker back on the next 5s poll.

### 3.2 Card ↔ ask ↔ resolution linkage

- `runEscalation` accepts the originating `card_id`; store it on the task and the `companion-ask-results` record.
- `/api/approve` for an obligation card records `decision: "approve_pending"` (not a final clear). On escalation completion, append the terminal decision **plus a re-check** of that one obligation's evidence (re-run `checkObligations` filtered to the id) to record whether it *actually* cleared.

### 3.3 Make the "fix" able to actually meet the obligation (where safe)

For obligations whose remedy is **re-running a producer** (premarket, gym, EOD) rather than editing a denylisted doctrine file, change the escalation task from "diagnose + report" to "**run the producer script and verify its evidence file is fresh**" (e.g. `setup/scripts/run-premarket.ps1`, gym-session). Then completion genuinely clears the card. Keep diagnosis-only for engine-health/params-class obligations that `guard.js` DENY_WRITE forbids touching — those snooze + flag, they don't self-heal.

### 3.4 Fix the mobile dead-end (immediate, one line)

`public/m.html:238` — on `j.escalated`, call `trackAsk(j.escalated)` (as app.js:138 already does) instead of only `addAsk("Gamma","On it…")`. Without this, every card-approved build on the phone is invisible. This is the single highest-value/lowest-effort fix in the whole plan.

---

## 4. Honest effort + fragility

| Area | Effort | Fragility |
|---|---|---|
| `includePartialMessages` flag + dispatcher | Low-med | Low. SDK message shapes are documented + stable; defensive `?.` guards mean an unexpected block type just isn't rendered. |
| `emit` + per-ask JSONL + SSE registry | Med | Low. Best-effort writes; SSE is one-way text. Main risk = leaking subscriber `res` objects → mitigated by `req.on('close')` unsubscribe. |
| SSE endpoint + per-ask stream token | Med | Low-med. EventSource header limitation forces the `?tok=` path; reuse existing HMAC mint/verify to avoid a new auth surface. |
| Frontend transcript (both UIs) | Med | Low. Falls back to existing `/api/ask-result` poll on `EventSource` error. |
| Obligation ack/snooze + fullState filter | Med | **Highest-care item.** Must NOT permanently hide a real red — the `evidence_sig` + expiry guarantees auto-re-surface. Test the still-stale-after-build case explicitly. |
| Card↔ask linkage + approve_pending | Med | Low. Additive record fields. |
| Producer-rerun fix tasks | Med | Med. Re-running PowerShell producers from an SDK Bash call on Windows can be flaky; verify evidence-file freshness as the success gate, not exit code (LESSONS-LEARNED C7). |
| m.html `trackAsk` one-liner | Trivial | None. |
| Remaining polish (A-2..A-6, R-1, C-*, G-*, SV-1) | Low each | Trivial; S-1 + A-1 already shipped. |

**Net:** Phase 1 (streaming + SSE + transcript + mobile one-liner) is a single after-4pm session and satisfies demand 2 immediately. Phase 1b (approval ack/snooze + linkage) satisfies demand 1 and is the same session if time permits, else the next block. Phase 2 (producer-rerun self-heal + polish) follows. Phase 3 (terminal/window) is deferred indefinitely unless J asks.

---

## 5. Build order (ranked)

1. **m.html `trackAsk` one-liner** — kills the mobile dead-end. ~0.3h.
2. **Stream capture in escalate.js** (`includePartialMessages` + dispatcher + `humanize` + `emit` + SSE registry). ~3h.
3. **SSE endpoint in server.js** (`/api/ask-stream`, replay + subscribe + per-ask token). ~2h.
4. **Transcript panel in both frontends** (EventSource in `trackAsk`, render steps, poll fallback). ~3h.
5. **Obligation ack/snooze + fullState filter + server-truth dismissal** (stop bounce-back without hiding real reds). ~4h.
6. **Card↔ask linkage + approve_pending + post-build re-check.** ~2h.
7. **Producer-rerun fix tasks** (premarket/gym/EOD self-heal where guard-safe). ~3h.
8. **Capture `sessionId` for future resume.** ~0.5h.
9. **Remaining polish** (A-2, A-3, A-4, R-1, then A-5/A-6/C-*/G-*/SV-1). ~1.5h.
10. **Smoke + manual verify** (extend `smoke-sdk.js` → assert feed JSONL has a tool/text step + final result + sessionId; `smoke-guard.js` stays green; manual `/api/approve` → watch transcript stream → card clears + result lands; desktop + phone). ~1.5h.

---

## 6. Testing / acceptance

- `node --check` on every edited `.js`; `node gamma-companion/smoke-guard.js` stays green.
- New `smoke-stream.js` (or extend `smoke-sdk.js`): run a tiny escalation with `includePartialMessages:true`, assert `companion-ask-feed/<id>.jsonl` contains ≥1 `tool`/`text` step **and** a final `result` step, and `sessionId` was captured. End-to-end pipe proof without UI.
- Manual: POST `/api/approve` from m.html with a real task → transcript panel populates with "Reading … / Ran: … / Editing …" live → approval card disappears and **stays gone** → final result appears in the feed. Repeat on desktop. Kill the SSE mid-stream → verify graceful fallback to `/api/ask-result` poll, not a blank.
- Obligation regression: approve an obligation whose evidence is still stale after the build → card snoozes, then **correctly re-surfaces** when the snooze lapses (never permanently hidden).
