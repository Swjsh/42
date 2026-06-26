# Integration: surfacing obligations as companion cards

> Additive wiring note. `server.js` is **not** edited by the overnight build — this
> documents exactly how to wire `checkObligations` into `/api/state` when J (or a
> daytime session) is ready. Drop-in, ~8 lines.

## What this gives you

`gamma-companion/lib/obligations.js` answers the one question the companion could
not answer before: **did the rig actually do its job today?** It reconciles each
declared obligation in `automation/state/obligations.json` against the *content*
freshness of its evidence file (mtime + an internal timestamp/field + verdict /
sub-check gates), not mere file-existence. A missing evidence file is a FAILED
obligation — this is the fail-green trap the registry exists to close.

```js
const { checkObligations } = require("./lib/obligations");
const obligations = checkObligations(ROOT); // ROOT = repo root, same one buildState uses
// -> [ { id, label, ok, detail, severity }, ... ]   (never throws)
```

## Wiring into /api/state (no behavior change to existing fields)

In `server.js`, inside the `/api/state` handler, after `buildState(ROOT)` returns
its object, append the red obligations as cards. Reuse the **existing approvals
card shape** (`{ id, severity, title, detail, source }`) so the companion UI
renders them with zero new front-end code:

```js
const { checkObligations } = require("./lib/obligations");

// ...inside the /api/state route, after `const state = buildState(ROOT);`
const obCards = checkObligations(ROOT)
  .filter((o) => !o.ok)                       // only RED obligations become cards
  .map((o) => ({
    id: "oblig-" + o.id,                       // namespaced so it never collides
    severity: o.severity === "critical" ? "warn" : (o.severity === "high" ? "warn" : "info"),
    title: "Obligation unmet: " + o.label,
    detail: o.detail,
    source: "obligations",
    // Optional: an escalate action mirroring derivedCards() in state.js
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

// Surface them: prepend so unmet obligations sit ABOVE softer info cards.
state.approvals = [...obCards, ...state.approvals];

// Optional: a dedicated strip so they also show even when approvals are collapsed.
state.obligations = checkObligations(ROOT);
```

That's the whole change. `state.approvals` already drives the "N things need your
OK" speech line in `buildState`, so unmet obligations automatically bump the
companion face into an attention state.

## Severity mapping rationale

| obligation severity | card severity | why |
|---|---|---|
| `critical` | `warn` | heartbeat dead = trading blind; loudest the card vocabulary allows |
| `high`     | `warn` | premarket / EOD / scheduled-tasks / watchers — load-bearing daily |
| `medium`   | `info` | gym YELLOW/missing — degraded, not blind |

(The companion card vocabulary is `info | warn`. If a `crit` tier is added to the
front-end later, map `critical -> crit` here.)

## Freshness semantics (so nobody re-introduces fail-green)

- **`et_date` field** (premarket): the internal `date` must equal **ET today**, not
  just "a recent mtime" — a file touched by an unrelated process can't fake it.
- **`iso` field** (heartbeat, scheduled-tasks, gym): parses the declared timestamp
  field; **falls back to mtime** only when the field is absent, and says so in the
  detail.
- **`dated_file` / `dated_json`** (EOD review, gym scorecard): the `{today}`
  placeholder resolves to the ET date, so the obligation passes only when **today's**
  file exists (and is within `fresh_within`).
- **`expect_on: "weekday"`**: obligations that only fire on trading days return
  `ok:true` with `detail:"not due (weekend)"` on Sat/Sun — no false reds.
- **Missing evidence ⇒ `ok:false`.** Always. This is the core anti-fail-green
  invariant.

## Verification

```bash
node -e 'console.log(JSON.stringify(require("./gamma-companion/lib/obligations").checkObligations(process.cwd()),null,2))'
```

Against live state on 2026-06-21 this correctly flags `scheduled_tasks` RED
(12 SILENT_TASK flags in `scheduled-tasks-audit.json`) while passing the fresh
heartbeat/watcher beacons and weekend-exempting premarket/EOD/gym. No throw.

## Cost / safety

Pure local file reads on each `/api/state` poll — no network, no model calls,
no order placement, no production-doctrine writes. Same cost profile as the
existing `buildState`.
