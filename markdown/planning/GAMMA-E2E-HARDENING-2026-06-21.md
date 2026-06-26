# Gamma Companion — Phone-Driven E2E Hardening (2026-06-21)

> Goal: a phone-driven Gamma that (1) reliably starts a REAL Claude session on every typed build/do request, (2) reliably starts one on every approval, (3) runs WITH its soul (CLAUDE.md + the 10 rules + guard boundary) as the actual system prompt — not incidental context, and (4) has no rough edges (no strands, no leaks, no corrupt writes, no zombie builds).
>
> Audited against the REAL files. SDK pinned at `@anthropic-ai/claude-agent-sdk@0.3.185` (verified in node_modules). All file+line references below are real.

---

## SOUL VERDICT (crisp)

**Does the escalation get CLAUDE.md today?** YES — but only by ACCIDENT, and as the wrong KIND of context.

- `runEscalation` (`gamma-companion/lib/escalate.js:223-231`) calls `query({ prompt, options:{ model, cwd, canUseTool, abortController, includePartialMessages } })` with **NO `systemPrompt`** and **NO `settingSources`**.
- Per the bundled SDK type defs (`node_modules/@anthropic-ai/claude-agent-sdk/sdk.d.ts:1880-1882, 1929-1934`): the `claude_code` preset is **opt-in**. Omitting `systemPrompt` yields a **minimal** system prompt — the escalation Claude is therefore **NOT** the Claude Code coding agent (no agentic identity/tool-use scaffolding), does **not** know it is Gamma, and never sees the 10 rules / guard boundary as authoritative soul.
- CLAUDE.md *does* load today only because omitting `settingSources` currently defaults to all sources in 0.3.185 — but (a) it lands as **project CONTEXT (a user message)**, not the soul/system prompt, and (b) the SDK default has flip-flopped across versions (v0.1.0 defaulted to `[]` = isolated), so a future bump can **silently** drop the soul with no error.

**Exact injection fix** — in `escalate.js`, add to the `options` block:

```js
const SOUL = [
  "You are Gamma, J's autonomous 0DTE SPY research + build agent.",
  "The repo CLAUDE.md is your soul — read and obey it, especially the 10 rules and the Operating Principles.",
  "You run inside a HARD guard (lib/guard.js): you MAY build/edit code, run backtests, and use project MCP servers,",
  "but you can NEVER write CLAUDE.md / params*.json / heartbeat*.md / filters.py / *.key, and NEVER place/cancel/close",
  "live orders — propose those as TEXT for J. Act autonomously within that boundary: do the work, verify it, report",
  "concisely. Never claim unverified work is done."
].join(" ");

options: {
  model: fullModel,
  cwd: root,
  systemPrompt: { type: "preset", preset: "claude_code", append: SOUL }, // SOUL FIX
  settingSources: ["user", "project"],                                   // deterministic CLAUDE.md load
  canUseTool: makeCanUseTool(root, org),
  abortController: ac,
  includePartialMessages: true,
  maxTurns: 60,                                                          // bound a runaway loop
}
```

This makes the role + rules part of the actual system prompt (matching the documented "Load CLAUDE.md with preset system prompt" pattern), pins soul-loading deterministically, and caps a runaway loop on the shared Max pool.

---

## PRIORITIZED FIX LIST

### P0 — Soul / autonomy (demand 3)

1. **[CRITICAL] Escalation runs soulless (minimal system prompt).** `lib/escalate.js:223-231`. Fix: add `systemPrompt:{type:'preset',preset:'claude_code',append:SOUL}` (SOUL string above).
2. **[CRITICAL] CLAUDE.md load is incidental, not pinned.** `lib/escalate.js:223-231`. Fix: add `settingSources:['user','project']` so a future SDK default flip can't silently drop the soul.

### P0 — Reliable session start (demand 1 & 2)

3. **[HIGH] Typed build/do requests do NOT reliably start a session.** `server.js:478-486` blindly trusts `face.escalate`, decided by a prose-fragile FREE model (`face_brain.py parse_escalation`, exact ```escalate fence). The model may chat instead, drop the fence, truncate at `max_tokens=420`, or rate-limit → request silently degrades to a chat reply, NO Claude session. Fix: add a deterministic intent classifier in `server.js` `/api/chat` BEFORE trusting the face. Regex the raw message for imperative verbs at clause start: `/^(\s*(please|hey gamma)[,:]?\s*)?(build|implement|add|create|write|fix|patch|refactor|run|backtest|wire|ship|make|generate|analyze|investigate|debug|optimize|port)\b/i`. If it matches AND the face did not escalate, force one: synthesize `{model:'sonnet', task:'J asked via companion: '+message}`, call `runEscalation`, return `escalate:true + ask_id + stream_token`. Keep the face's sentence as the human reply.
4. **[HIGH] Approve-then-build-fails: the obligation card stays hidden ~45 min.** `lib/approvals.js:201-203` snoozes the synthetic `oblig-*` card UNCONDITIONALLY on `decide('approve')`, before/independent of whether `runEscalation` succeeded. A failed producer-rerun leaves the obligation unmet but the card suppressed → "nothing needs you" (the fail-green trap obligations.js exists to prevent). Fix: for an escalating approve, do NOT snooze 45 min in `resolveApproval`; instead snooze a short 2-3 min grace, and let the escalation completion callback clear/snooze only when `recheckObligationCleared` confirms fresh evidence (escalate.js already computes `cleared`). Plumb a `skipLongSnooze` flag from `/api/approve` (server.js:520-528) when `action.type==='escalate'`.

### P1 — Stream / strand / leak (demand 4)

5. **[HIGH] SUBSCRIBE-GAP RACE strands the phone on "On it…".** `server.js:441-461` reads the feed (`fs.readFileSync`, line 443) BEFORE `subscribeAskStream` (line 453). Any `emit` in that window — including the terminal `result` of a fast/already-busy build — is delivered by NEITHER replay nor live stream, no EventSource error fires, so `es.onerror→startPoll` never runs and the line hangs forever. Fix: subscribe FIRST, then read+replay, de-dup with a monotonic per-id `seq` (add `seq` in `emit`, drop already-seen seqs client-side). Minimal: after `subscribeAskStream`, re-read the feed tail once and replay any new lines. ALSO: if `tasks.get(id).status` is already terminal (done/failed/cancelled/blocked/busy) at connect time, synthesize+write a final `result` SSE frame immediately so a post-completion connect always settles.
6. **[HIGH] EventSource native auto-reconnect defeated + no server heartbeat.** Client (`public/app.js:337`, `public/m.html:346-351`) treats the FIRST `onerror` as terminal (`fellBack=true; es.close(); startPoll()`), but EventSource fires `onerror` on every transient blip and is designed to self-reconnect. Server SSE route (`server.js:435-461`) writes NO periodic heartbeat, so idle Tailscale/proxy hops drop long builds → permanent downgrade to polling (J loses the live transcript). Fix — **Server:** `setInterval` writing `res.write(': ping\n\n')` every ~15s per open SSE res, cleared in `done()`; a throwing heartbeat write is also the cheapest dead-socket detector (unsubscribe+clearInterval on throw — also fixes the subscriber leak, #9). **Client:** on first `onerror`, start a 10-15s grace timer; only `close()+startPoll()` if `es.readyState===2` (CLOSED) or still erroring when it fires; clear the timer on the next `onmessage`. Preserves native reconnect for blips.
7. **[MED] Long build → no wall-clock timeout → zombie that holds an inflight slot.** `lib/escalate.js:221-359` has no hard cap; if `query()` hangs without throwing or yielding `result` (network stall to Anthropic), NO result record/frame is ever written, the poll fallback caps out ("Still working…") and gives up, and the inflight slot is pinned (next 2 asks go `busy`). Fix: `const killer = setTimeout(()=>{try{ac.abort()}catch{}}, 15*60*1000)` at the top of the try; `clearTimeout(killer)` on every exit path. A stalled query then always lands on the catch/abort path → writes a result + emits a terminal frame + frees the slot.
8. **[MED] Stream token expires mid-build.** `lib/push.js:435` TTL=60min but builds can run longer; reconnect after `exp` → `verifyStreamToken` `expired` → route 403s → permanent polling, and a page reload can't re-watch (no fresh token). Fix: raise TTL to 4-6h (read-only 127.0.0.1 telemetry, grants no write power) — one-line change at push.js:435.
9. **[MED] Subscriber leak on phone background / unclean FIN.** `server.js:452-460` relies on `req 'close'/'end'` / `res 'error'`; a backgrounded PWA may not FIN promptly and `emit`'s `res.write` buffers without throwing, pinning the res for the build's life. Fix: the #6 heartbeat write surfaces the dead socket (unsubscribe+clearInterval on throw); also `res.socket.setTimeout(...)` + a max-lifetime, and cap subscribers per id (drop oldest beyond ~5).
10. **[MED] Result frame/record can report a failure as a cheery "Done in Ns".** `lib/escalate.js:264-276, 335-347`: on `subtype==='error_max_turns'`/`'error_during_execution'`, `result` text is often empty but the summary is still `"Done in Xs"` and `appendResult` writes `(no output)`. Fix: when `subtype!=='success'` or `is_error`, build an explicit failure summary (`ok ? 'Done…' : 'Stopped: '+subtype`) in both the emitted frame and the appended record. Client (`app.js:300`, `m.html:301/336`) already prefers the durable record — keep that, just make both honest.

### P1 — Input / concurrency / write-safety (demand 4)

11. **[HIGH] Oversized POST body HANGS the request forever.** `server.js:193-206` `readBody`: on `body.length > 2e5` it calls `req.destroy()` inside the `'data'` handler → the `'end'` event never fires → `cb()` never called → no response is ever sent. A typed prompt just over 200KB silently dead-ends the phone. Affects `/api/chat`, `/api/approve`, `/api/diagram`, `/api/push/subscribe`. Fix: reply 413 then stop, guaranteeing exactly one response: `let aborted=false; req.on('data',c=>{ if(aborted)return; body+=c; if(body.length>2e5){aborted=true; sendJSON(res,413,{ok:false,error:'request too large'}); req.destroy();} }); req.on('end',()=>{ if(aborted)return; try{cb(JSON.parse(body||'{}'))}catch{cb({})} });`.
12. **[HIGH] Escalation askId collision.** All three id mints (`server.js:482` chat, `:510` card, `:546` diagram) use `'ask-'+Date.now().toString(36)` (ms only). Two near-simultaneous escalations get the SAME id → `logAsk`, `runEscalation`, the SSE feed file (`askFeedPath`), and `findAskResult` all collide → one build's transcript/result is attributed to the other. Fix: add entropy at all three sites — `'ask-'+Date.now().toString(36)+'-'+crypto.randomBytes(4).toString('hex')` (or `crypto.randomUUID()`).
13. **[MED] Non-atomic `writeApprovals` → torn file + lost cards under concurrency.** `lib/approvals.js:124-131` plain `fs.writeFileSync` with NO temp+rename; `enqueueApproval` (engine) and `resolveApproval` (http) both do load→mutate→write, racing. A crash mid-write leaves a truncated `companion-approvals.json` that `loadPending` swallows → every pending real approval silently disappears. (`writeCardAcks` already uses temp+rename — mirror it.) Fix: write to `approvalsPath(root)+'.tmp.'+process.pid` then `fs.renameSync` over target (atomic same-volume), removing the torn-file mode.
14. **[MED] Server-side double-decision unguarded.** `/api/approve` (`server.js:500-531`) has no idempotency: two POSTs for one id (double-tap, app-then-wrist, retried fetch) BOTH run `resolveApproval` → TWO `companion-decisions.jsonl` lines (possibly approve AND reject) and TWO `runEscalation`s (duplicate builds). Fix: make `resolveApproval` idempotent — for real queued cards, if `pending.find(id)` is null AND not synthetic, return `{resolved:id, already:true}` and skip the decision line + escalation; for synthetic cards, `isCardSnoozed(root,id,sig)` first and no-op if already snoozed for the same evidence.
15. **[MED] Forced/auto-escalation de-dup (pairs with #3).** Once the intent net (#3) exists, a double-tap send or face-AND-intent-net both firing could spawn two concurrent sessions for one message (`MAX_INFLIGHT=2` allows it). Fix: escalate ONCE — prefer the face's structured task when `face.escalate`, else the intent-net task, never both. Add a ~10s de-dup in `escalate.js` keyed on a hash of the task text: if an identical task is already running/just-started, return the existing `ask_id` instead of starting a second session.
16. **[MED] `m.html` decide-catch strands a failed-to-send card.** `public/m.html` `decide()` catch only `setStatus(...)`+`setTimeout(refresh)` and does NOT `delete dismissed[a.id]` (app.js does). On an offline POST the card vanishes and stays in `dismissed{}` for the session → won't return on refresh, yet the decision was never logged. Fix: in the catch, `if(a&&a.id) delete dismissed[a.id]; lastApprovalsSig='__changed__';` so it re-renders next poll (matching app.js).

### P2 — Hardening / hygiene (demand 4)

17. **[MED] `face_brain.py max_tokens=420` truncates the escalation block.** `face/face_brain.py:148`. A rich self-contained task + the human sentence can exceed 420 → the ```escalate JSON is truncated → `parse_escalation` `json.loads` fails → `(None, text)` → NO escalation. The richer the task, the likelier the silent failure. Fix: raise non-fast `max_tokens` to ~700-900; best combined with #3 so a truncated face block still yields a real session via the deterministic net.
18. **[MED] No maxTurns / market-hours pool guard.** `lib/escalate.js:223-231` omits `maxTurns`; a runaway autonomous loop burns the Max pool which (per CLAUDE.md) the heartbeat SHARES — a phone-triggered build 09:30-15:55 ET can starve heartbeat ticks. Fix: `maxTurns:60` (in the #1/#2 options block); consider warning/queueing market-hours escalations.
19. **[LOW] Whitespace-only face task spawns a near-empty build.** `server.js:481` only checks `face.escalate && face.task` truthiness. Fix: `if (face && face.escalate && String(face.task||'').trim().length > 3)`. Same check on the forced intent-net path.
20. **[LOW] `/api/approve action.task`/`action.model` unvalidated.** `server.js:509-520` passes `action.task` straight into the escalation; `action.model` coerces silently to sonnet via `MODEL_MAP` fallback (`escalate.js:192`). Fix: validate `action` shape — `if (action && action.type==='escalate'){ if (typeof action.task!=='string' || !action.task.trim()) action=null; else action={...action, task:action.task.slice(0,8000)} }`; clamp `model ∈ {opus,sonnet,haiku}` at the `runEscalation` boundary and log a coercion.
21. **[LOW] Feed-file growth never pruned (OP-22 violation).** `lib/escalate.js:30-60` appends to `companion-ask-feed/<id>.jsonl` per step and NOTHING deletes them — the dir leaks disk forever (every chat/approval/diagram = a new file). Fix: on server start and/or after each escalation finishes, prune `askFeedDir` to the most recent ~50 by mtime and/or delete files older than ~24h (best-effort, try-catch like the rest).
22. **[LOW] MCP surface for 3am autonomous runs.** `cwd=root` inherits the project `.mcp.json` (alpaca, alpaca_aggressive, tradingview). `guard.js DENY_TOOL` holds the order wall (regex `/^mcp__alpaca(_aggressive)?__(place|cancel|close|replace|exercise|do_not_exercise)/` matches the real tool names — verified), but `get_*` + any future write tool auto-allow. Not a money bug — a cost/surface concern. Fix: keep full MCP (builds may need TradingView reads) but document it, or pass an explicit `mcpServers` allowlist for escalations that don't need trading MCP. Keep `DENY_TOOL` as the hard wall.

---

## SUMMARY

Two of J's four demands are NOT met today:

- **Demand 1 (typed prompts reliably start a session): FAILS.** `/api/chat` (server.js:478-486) blindly trusts a prose-fragile FREE model's exact ```escalate fence (face_brain.py); chat-instead / no-fence / `max_tokens=420` truncation / rate-limit all silently degrade a do-request to a chat reply with NO session. There is zero server-side build-intent safety net. → Fix #3 (deterministic intent classifier) + #17 (raise face max_tokens).
- **Demand 3 (read the soul, be autonomous): FAILS as designed.** The escalation runs with a MINIMAL system prompt (no `systemPrompt` preset) — not the Claude Code agent, doesn't know it's Gamma, never sees the 10 rules / guard as soul. CLAUDE.md loads only incidentally as project context and can silently vanish on an SDK default flip (no `settingSources`). → Fix #1 + #2.

Demand 2 (approvals start sessions) works on the happy path but #4 (fail-green snooze) and #14 (double-decision) are real holes. Demand 4 (no bugs) is broadly violated by the strand/leak/race/zombie set (#5-#16) and the hygiene items (#17-#22). The single highest-leverage change is the SOUL block (#1+#2) — one options edit fixes demands 3 and a chunk of 4 at once. The single highest-leverage reliability change is the intent classifier (#3), which makes demand 1 deterministic regardless of the free model's mood.
