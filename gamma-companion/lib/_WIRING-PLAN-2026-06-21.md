# Wiring plan — 4 autonomy modules into the live companion (2026-06-21)

> READY-TO-APPLY, surgical old→new edits for the integrator. Verified against the
> CURRENT files (post guard/token/soul/ladder changes already shipped tonight).
> Nothing here is applied by the overnight session — it is a spec.
>
> Modules covered: `lib/activity.js`, `lib/obligations.js`, `lib/autobuild.js`.
> (The 4th "module" — the soul `GAMMA-VOICE.md` — is ALREADY wired into
> `server.js#loadVoiceHead` + face; no edit needed. See §5.)

## Module-correctness verdict (read first)

| module | verdict | note |
|---|---|---|
| `activity.js` | CORRECT | leaf module, never-throws, no companion imports. `todaySpend` keys on **UTC** day (by design; doc §"UTC day"). |
| `obligations.js` | CORRECT | never-throws; missing-evidence ⇒ `ok:false`; weekend-exempt; et_date/iso/dated_file freshness all handled. Registry file `automation/state/obligations.json` exists (4.8KB). |
| `autobuild.js` | CORRECT (queue reader only) | atomic tmp+rename `markStep`; `nextBuildStep` returns only `pending`; never spawns Claude. Queue `companion-build-order.jsonl` exists (7 tasks). **NOTE:** task #1 in the seeded queue is `wire-activity-ledger` — i.e. the queue would have the autobuild loop RE-DO §1–§3 below. If the integrator applies §1–§3 by hand, mark that queue line `done` to avoid a duplicate pass. |

No bugs found in any of the three modules. One pre-existing gap that AFFECTS the
activity wiring is called out in §1 (the chat/diagram escalations don't pass `origin`).

---

## §1. `lib/escalate.js` — emit a row on every escalation result

`appendResult` is the single chokepoint (all 4 exit paths route through it:
success, error, halted, busy). One `logActivity` call there = full coverage.

### Edit 1a — add the import

OLD:
```js
const fs = require("fs");
const path = require("path");
const { makeCanUseTool, isHalted } = require("./guard");
```
NEW:
```js
const fs = require("fs");
const path = require("path");
const { makeCanUseTool, isHalted } = require("./guard");
const { logActivity } = require("./activity");
```

### Edit 1b — log inside `appendResult`

OLD:
```js
function appendResult(root, rec) {
  try {
    fs.appendFileSync(resultsPath(root), JSON.stringify(rec) + "\n");
  } catch {
    /* best effort */
  }
}
```
NEW:
```js
function appendResult(root, rec) {
  try {
    fs.appendFileSync(resultsPath(root), JSON.stringify(rec) + "\n");
  } catch {
    /* best effort */
  }
  logActivity(root, {
    source: "escalate",
    origin: rec.origin || "text",
    tier: "agent",
    model: rec.model || null,
    cost_usd: 0,
    action: rec.task ? "ran escalation" : "escalation skipped",
    outcome: rec.ok
      ? "success"
      : "error: " + String(rec.summary || rec.error || "failed").slice(0, 120),
  });
}
```

Why it covers all 4 paths: the halted and busy early-returns call `appendResult`
directly (those `rec`s have no `task`/`origin` → guarded by `rec.origin || "text"`
and `rec.task ?`), the catch path calls it with `error`, and the success path with
`task`+`summary`+`origin`. `logActivity` never throws, so it cannot break a result
write.

### Edit 1c (REQUIRED for correct `origin` on the feed) — pass `origin` from server.js

The success `rec` already carries `origin`, but the two `runEscalation` calls in
`server.js` for chat and diagram DON'T pass an `origin`, so every chat/diagram row
logs `origin:"text"`. To distinguish them in the ledger, thread origin through.

In `gamma-companion/server.js`:

OLD (in `/api/chat`):
```js
          runEscalation(ROOT, { id: askId, model: face.model, task: face.task });
```
NEW:
```js
          runEscalation(ROOT, { id: askId, model: face.model, task: face.task, origin: "chat" });
```

OLD (in `/api/diagram`):
```js
      runEscalation(ROOT, { id, model: "sonnet", task });
```
NEW:
```js
      runEscalation(ROOT, { id, model: "sonnet", task, origin: "diagram" });
```

OLD (in `/api/approve`):
```js
        runEscalation(ROOT, { id: escalated, model: action.model || "sonnet", task: action.task });
```
NEW:
```js
        runEscalation(ROOT, { id: escalated, model: action.model || "sonnet", task: action.task, origin: "card" });
```

(Optional but harmless — if skipped, those rows just read `origin:"text"`. Edits
1a/1b are the load-bearing pair; 1c is polish.)

**Guard/token conflict check:** NONE. `escalate.js` is upstream of the guard
(`makeCanUseTool` is built inside `runEscalation` and unchanged). Adding a logging
side-effect to `appendResult` does not touch `canUseTool`, the denylist, or the
session token. `logActivity` writes only `automation/state/gamma-activity.jsonl`,
which is NOT on `DENY_WRITE` — but that's irrelevant anyway because `logActivity`
is plain Node `fs`, not an SDK tool call, so the guard never sees it.

---

## §2. `lib/approvals.js` — emit a row on resolve

### Edit 2a — add the import

OLD:
```js
const fs = require("fs");
const path = require("path");

function approvalsPath(root) {
```
NEW:
```js
const fs = require("fs");
const path = require("path");
const { logActivity } = require("./activity");

function approvalsPath(root) {
```

### Edit 2b — log just before the return in `resolveApproval`

OLD:
```js
  fs.appendFileSync(decisionsPath(root), JSON.stringify(record) + "\n");

  return { resolved: id, decision, remaining: remaining.length };
```
NEW:
```js
  fs.appendFileSync(decisionsPath(root), JSON.stringify(record) + "\n");

  logActivity(root, {
    source: "approvals",
    origin: "card",
    tier: "approval",
    model: null,
    cost_usd: 0,
    action: "resolved approval " + id,
    outcome: decision,
  });

  return { resolved: id, decision, remaining: remaining.length };
```

**Acyclic-deps check:** `state.js → approvals.js → activity.js`, and
`escalate.js → activity.js`. `activity.js` imports nothing from the companion
(leaf). `approvals.js` must NOT `require("./state")` — it doesn't, and this edit
keeps it that way. No cycle introduced.

**Decision value note:** the UI/server posts `decision` as `"approve"|"reject"`
(see server.js `/api/approve` validation), NOT `"approved"|"rejected"`. The
integration doc's example said `"approved"|"rejected"` — the REAL value passed is
`"approve"|"reject"`. The edit above logs the real value verbatim (`outcome: decision`),
which is correct; just don't "fix" it to the doc's wording.

---

## §3. `lib/state.js#buildState` — tail the ledger into the feed

### Edit 3a — add the import

OLD:
```js
const fs = require("fs");
const path = require("path");
const { readApprovals } = require("./approvals");
```
NEW:
```js
const fs = require("fs");
const path = require("path");
const { readApprovals } = require("./approvals");
const { readActivity, todaySpend } = require("./activity");
```

### Edit 3b — push ledger rows into `feed` before the sort

OLD:
```js
  if (kitchen && kitchen.recent) {
    for (const r of kitchen.recent) {
      feed.push({ ts: r.at, kind: "kitchen", name: "kitchen", text: tidy(r.task) });
    }
  }
  feed.sort((a, b) => timeOf(b.ts) - timeOf(a.ts));
```
NEW:
```js
  if (kitchen && kitchen.recent) {
    for (const r of kitchen.recent) {
      feed.push({ ts: r.at, kind: "kitchen", name: "kitchen", text: tidy(r.task) });
    }
  }
  for (const a of readActivity(root, 10)) {
    feed.push({
      ts: a.ts,
      kind: "activity",
      name: a.source || "gamma",
      text: tidy((a.action || "did something") + " — " + (a.outcome || "")),
    });
  }
  feed.sort((a, b) => timeOf(b.ts) - timeOf(a.ts));
```

### Edit 3c — surface today's spend on the returned state

OLD:
```js
  return {
    updated_at: new Date().toISOString(),
    market_open: !!(health && health.market_open),
```
NEW:
```js
  return {
    updated_at: new Date().toISOString(),
    spend_today_usd: todaySpend(root),
    market_open: !!(health && health.market_open),
```

### Edit 3d (optional) — show spend on the one-screen FACE summary

OLD:
```js
  if (Array.isArray(state.approvals) && state.approvals.length) {
    lines.push("Needs OK: " + state.approvals.map((x) => x.title).join(" | "));
  }
```
NEW:
```js
  if (typeof state.spend_today_usd === "number") {
    lines.push("Spend today: $" + state.spend_today_usd.toFixed(2));
  }
  if (Array.isArray(state.approvals) && state.approvals.length) {
    lines.push("Needs OK: " + state.approvals.map((x) => x.title).join(" | "));
  }
```

**Front-end check:** `feed` rows already render generically (kind/name/text); a new
`kind:"activity"` needs zero front-end change. `spend_today_usd` is an additive
field — existing `app.js` ignores unknown keys. No conflict with the token meta tag
or the soul wiring.

---

## §4. `lib/obligations.js` → `/api/state` as red cards (server.js)

This is the ONLY server.js route edit (besides the optional origin polish in 1c).
Reuse the existing card shape so the UI renders them with no front-end change.

### Edit 4a — add the import at the top of server.js

OLD:
```js
const { buildState, summarize } = require("./lib/state");
const { resolveApproval } = require("./lib/approvals");
const { runEscalation } = require("./lib/escalate");
const { loadOpenAIKey } = require("./lib/openai_key");
```
NEW:
```js
const { buildState, summarize } = require("./lib/state");
const { resolveApproval } = require("./lib/approvals");
const { runEscalation } = require("./lib/escalate");
const { loadOpenAIKey } = require("./lib/openai_key");
const { checkObligations } = require("./lib/obligations");
```

### Edit 4b — build red-obligation cards and merge into the /api/state response

OLD (the entire `/api/state` GET handler body):
```js
  if (req.method === "GET" && u === "/api/state") {
    try {
      return sendJSON(res, 200, { ok: true, voice: !!loadOpenAIKey(ROOT), ...buildState(ROOT) });
    } catch (e) {
      return sendJSON(res, 500, { ok: false, error: String((e && e.message) || e) });
    }
  }
```
NEW:
```js
  if (req.method === "GET" && u === "/api/state") {
    try {
      const state = buildState(ROOT);
      const allObligations = checkObligations(ROOT);
      const obCards = allObligations
        .filter((o) => !o.ok)
        .map((o) => ({
          id: "oblig-" + o.id,
          severity: o.severity === "critical" || o.severity === "high" ? "warn" : "info",
          title: "Obligation unmet: " + o.label,
          detail: o.detail,
          source: "obligations",
          action: {
            type: "escalate",
            model: "sonnet",
            task:
              "Daily obligation '" + o.id + "' (" + o.label + ") is UNMET: " + o.detail +
              ". Diagnose which scheduled task/producer stopped writing its evidence file " +
              "(see automation/state/obligations.json -> expect_evidence) and propose or apply " +
              "a SAFE fix. Do NOT place trades or edit live params/heartbeat. Report findings.",
          },
        }));
      state.approvals = [...obCards, ...state.approvals];
      state.obligations = allObligations;
      return sendJSON(res, 200, { ok: true, voice: !!loadOpenAIKey(ROOT), ...state });
    } catch (e) {
      return sendJSON(res, 500, { ok: false, error: String((e && e.message) || e) });
    }
  }
```

Notes:
- Card id is namespaced `oblig-*` so it never collides with `act-*` derived cards
  or file approvals.
- Severity maps `critical|high → warn`, `medium → info` (the UI vocabulary is
  `info|warn`).
- Prepending `obCards` makes unmet obligations sit ABOVE softer info cards AND bumps
  `state.approvals.length`, which `buildState`'s `speech` line already turned into
  "N things need your OK" — so the face goes to attention-state automatically. (The
  speech was computed inside `buildState` BEFORE we prepend here, so the spoken count
  won't include obligations. If you want the spoken count to include them, instead
  recompute speech here, or move the obligation merge INTO buildState. Acceptable as-is
  for the visual cards; flagged so it's a conscious choice — see §6.)

**Guard conflict check:** the obligation card's `action.task` is a benign
read/diagnose prompt that, IF approved, runs through `runEscalation` → `guard.js`.
The guard already denies any doctrine/params/heartbeat/filters/key write and all
Alpaca order tools, so even this auto-generated task cannot break the safety
envelope. The card itself only appears; it does nothing until J taps Approve.

**Token conflict check:** `/api/state` is a GET that is intentionally UNAUTHED
(no `authed(req)` gate — same as today). Obligations are read-only local file
reads, so exposing them on the unauthed read endpoint is consistent with the
existing `buildState` exposure. No new secret is leaked.

---

## §5. Autobuild — expose the build-order (read-only) + the trigger contract

`autobuild.js` is a pure queue reader; nothing is "wired" until a fire calls it.
Two safe, additive surfaces for J to SEE the queue without turning the loop on:

### Edit 5a — expose `queueSummary` on /api/state (read-only)

In `server.js`, add the import:

OLD:
```js
const { checkObligations } = require("./lib/obligations");
```
NEW:
```js
const { checkObligations } = require("./lib/obligations");
const { queueSummary, readQueue } = require("./lib/autobuild");
```

Then inside the same `/api/state` handler (after `state.obligations = allObligations;`):
```js
      state.build = {
        summary: queueSummary(ROOT),
        next: (readQueue(ROOT).find((t) => (t.status || "pending") === "pending") || null),
        queue: readQueue(ROOT).map((t) => ({ id: t.id, title: t.title, tier: t.tier, status: t.status || "pending" })),
      };
```

This gives the cockpit a `state.build.summary` ("3 pending, 1 in_progress, 9 done"),
the next step, and the ordered list — all read-only. The front-end can render a
"Build queue" strip; unknown keys are ignored by the current `app.js` so this is
non-breaking even before any UI is added.

### Edit 5b — the FIRE is NOT wired here (by design / safety envelope)

Per `_INTEGRATION-autobuild.md`, the bounded fire (`nextBuildStep → runEscalation →
verify → markStep`) ships as a separate `run-build-step.js` wrapper + a
`Gamma_CompanionBuild` after-hours scheduled task. That is OUT OF SCOPE for this
wiring pass (it places no orders but it DOES spawn Claude autonomously, so J turns
it on). This plan exposes the queue read-only only.

---

## §6. Soul module — ALREADY WIRED (no edit)

The 4th "module" is the soul `automation/presence/GAMMA-VOICE.md`. It is ALREADY
loaded into the realtime voice preamble via `server.js#loadVoiceHead` (lines 169–177,
used at 295–296) and into the face brain (per tonight's prior pass). No further
wiring needed. Listed here only so the integrator doesn't re-do it (queue line
`wire-soul-face-brain` can be marked `done`).

---

## §7. Conflict summary vs tonight's already-shipped changes

| already-shipped | does this plan touch it? | verdict |
|---|---|---|
| `guard.js` (14/14) denylist + DENY_TOOL | NO edits to guard.js | SAFE — obligation/autobuild tasks still pass through it unchanged |
| per-session `GAMMA_TOKEN` on `/api/*` | `/api/state` stays UNAUTHED (as today); no token logic changed | SAFE |
| soul `GAMMA-VOICE.md` wired into face+voice | NO edit (§6) | SAFE — explicitly NOT re-wired |
| OpenRouter ladder fix (nemotron/minimax) | NOT touched | SAFE — face_brain.py unchanged by this plan |
| instant hand-crafted system diagram | `/api/diagram` only gains `origin:"diagram"` (1c, optional) | SAFE |

No edit in this plan modifies `CLAUDE.md`, `params*.json`, `heartbeat*.md`,
`filters.py`, or any `*.key`; no order tool is called. All edits are additive
JS wiring in `escalate.js`, `approvals.js`, `state.js`, and `server.js`.

## §8. Post-apply verification (run after integrator applies)

```bash
cd gamma-companion
node --check lib/escalate.js && node --check lib/approvals.js \
  && node --check lib/state.js && node --check server.js
node smoke-guard.js            # must still print 14 passed, 0 failed
node -e 'const s=require("./lib/state");console.log(JSON.stringify(s.buildState(process.cwd()+"/.."),null,0).slice(0,400))'
node -e 'console.log(require("./lib/obligations").checkObligations(process.cwd()+"/..").filter(o=>!o.ok).map(o=>o.id))'
node -e 'console.log(require("./lib/autobuild").queueSummary(process.cwd()+"/.."))'
```

Expect: all `--check` pass; guard 14/14 unchanged; buildState now carries
`spend_today_usd` + `kind:"activity"` feed rows; obligations lists current reds
(e.g. `scheduled_tasks`); queueSummary shows `total:7`.
</content>
</invoke>
