# Wiring the activity ledger (`lib/activity.js`)

The ledger is **additive**: `activity.js` already exists and never throws. The three
edits below make `escalate.js`, `approvals.js`, and `state.js` *emit into* and
*read from* it. None of these files are on the doctrine/params denylist, so they
are safe companion edits — but **this doc only describes them; do not apply them
from the overnight session.** A human (or a later authorized pass) wires them in.

Import in every consumer:

```js
const { logActivity, readActivity, todaySpend } = require("./activity");
```

`root` is the same repo-root path every other companion function already receives.

---

## 1. `escalate.js` — log on each escalation result

`runEscalation(root, { id, model, task, origin })` has **three** exit points that
call `appendResult(...)`. Add a `logActivity` call beside **each** so every result —
success, error, halted, and busy — lands one row. Put the call immediately after
the existing `appendResult(...)`.

The clean place is inside `appendResult` itself, since every path already routes
through it AND the two early-return guards (halted/busy) call it directly. Change:

```js
function appendResult(root, rec) {
  try {
    fs.appendFileSync(resultsPath(root), JSON.stringify(rec) + "\n");
  } catch {
    /* best effort */
  }
}
```

to:

```js
function appendResult(root, rec) {
  try {
    fs.appendFileSync(resultsPath(root), JSON.stringify(rec) + "\n");
  } catch {
    /* best effort */
  }
  logActivity(root, {
    source: "escalate",
    origin: rec.origin || "text",          // "card" | "text" | "discord" etc.
    tier: "agent",
    model: rec.model || null,              // already the full id (MODEL_MAP value)
    cost_usd: 0,                           // SDK result carries no cost yet; 0 = unknown
    action: rec.task ? "ran escalation" : "escalation skipped",
    outcome: rec.ok
      ? "success"
      : "error: " + String(rec.summary || rec.error || "failed").slice(0, 120),
  });
}
```

Notes:
- The halted path passes `summary: "(halted...)"` and the busy path
  `summary: "(busy...)"` with no `origin`/`task`; `origin || "text"` and the
  `rec.task ?` guard handle that gracefully.
- `logActivity` never throws, so it cannot break the result write.
- If a real per-run cost becomes available from the SDK `result` message later,
  thread it into `rec` and pass `cost_usd: rec.cost_usd` here.

---

## 2. `approvals.js` — log on resolve

`resolveApproval(root, id, decision, note)` is the one place a card is
approved/rejected. Add a single `logActivity` call just before the `return`,
after the decision line is appended to `companion-decisions.jsonl`:

```js
  fs.appendFileSync(decisionsPath(root), JSON.stringify(record) + "\n");

  logActivity(root, {
    source: "approvals",
    origin: "card",
    tier: "approval",
    model: null,
    cost_usd: 0,
    action: "resolved approval " + id,
    outcome: decision,                     // "approved" | "rejected"
  });

  return { resolved: id, decision, remaining: remaining.length };
```

Add the import at the top of `approvals.js`:

```js
const { logActivity } = require("./activity");
```

(One direction only — `approvals.js` must not `require` `state.js`; `state.js`
already requires `approvals.js`, so importing `activity.js` here keeps the
dependency graph acyclic: `state -> approvals -> activity`.)

---

## 3. `state.js#buildState` — tail the ledger into the feed

`buildState` assembles `feed` from dialogue agents + kitchen recents, then sorts
by `ts` and slices to 4. Fold the ledger in as a third source so the companion
feed reflects *everything Gamma has been doing*, not just kitchen + dialogue.

Add the import at the top:

```js
const { readActivity, todaySpend } = require("./activity");
```

Inside `buildState`, after the kitchen loop that pushes feed rows and **before**
`feed.sort(...)`:

```js
  for (const a of readActivity(root, 10)) {
    feed.push({
      ts: a.ts,
      kind: "activity",
      name: a.source || "gamma",
      text: tidy(`${a.action || "did something"} — ${a.outcome || ""}`),
    });
  }
```

The existing `feed.sort((a, b) => timeOf(b.ts) - timeOf(a.ts))` and
`feed.slice(0, 4)` then interleave ledger rows by recency automatically — no
other change needed. `tidy(...)` is already defined in `state.js`.

Optionally surface today's spend in the returned object (the FACE model can read
it via `summarize`):

```js
  return {
    updated_at: new Date().toISOString(),
    ...
    spend_today_usd: todaySpend(root),
    feed: feed.slice(0, 4),
  };
```

And, if you want it on the one-screen summary, add to `summarize(state)`:

```js
  if (typeof state.spend_today_usd === "number") {
    lines.push(`Spend today: $${state.spend_today_usd.toFixed(2)}`);
  }
```

---

## Why this shape

- **Single chokepoint per file.** Escalations all funnel through `appendResult`;
  approvals all funnel through `resolveApproval`; the feed is built in one place.
  One `logActivity` call at each chokepoint = full coverage, no scattering.
- **Never-throw contract preserved.** `logActivity` swallows its own errors, so
  none of these edits can crash a result write, a resolve, or a state build.
- **Acyclic deps.** `state.js -> approvals.js -> activity.js`, and
  `escalate.js -> activity.js`. `activity.js` imports nothing from the companion,
  so it is a clean leaf module.
- **UTC day for spend.** `todaySpend` keys on the UTC calendar date to match the
  `ts` stamp; if a future ET-day rollover is wanted, convert before slicing — do
  it in one place (`todaySpend`), not at every call site.
