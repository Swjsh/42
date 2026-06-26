# `_INTEGRATION-autobuild.md` — the overnight self-build runner

> How a **bounded** fire (a scheduled task, or the after-hours conductor) picks the
> next safe build step, runs it through the **already-guarded** `runEscalation`,
> verifies it, and marks it done — or queues an Approve card. **Draft / design doc.
> This wires nothing on its own and ships no scheduler.** It documents the contract
> for the day J (or the conductor) turns it on.

## What this is

`gamma-companion/lib/autobuild.js` is the **queue reader** for Gamma's self-build
loop. It does exactly two things, both pure:

- `nextBuildStep(root)` → the first `pending` task in `automation/state/companion-build-order.jsonl`, or `null`.
- `markStep(root, id, status, extra?)` → atomically flips one task's `status`
  (`pending|in_progress|done|failed|blocked`) and stamps `updated_at`.

It **never** spawns Claude, **never** touches doctrine/params/orders, and **never
throws** on a malformed queue line (it skips + logs to stderr). All the muscle —
and all the danger — lives behind the existing chokepoint: `runEscalation`
(`escalate.js`) → `makeCanUseTool` (`guard.js`). `autobuild.js` only decides
*which* one safe step runs next.

## The five invariants (non-negotiable)

1. **BOUNDED — one step per fire.** A fire runs `nextBuildStep` once, escalates
   that single task, marks it, and **exits**. No `while` loop, no "drain the
   queue." The next fire picks up the next item. This caps blast radius and Max-pool
   spend, and means a hung step can't stall the loop forever (the fire just ends).
2. **GATED — through `runEscalation` only.** The task's `task` string is handed
   verbatim to `runEscalation(root, {id, model, task, origin:'autobuild'})`. The
   guard's denylist (`CLAUDE.md` / `params*.json` / `heartbeat*.md` / `filters.py` /
   `*.key` writes + all Alpaca order tools) holds at the SDK `canUseTool` boundary —
   so even a poisoned queue line **cannot** edit doctrine or place a trade.
3. **LOGGED — every step to `gamma-activity.jsonl`.** Spawn and outcome each emit a
   row (`{ts,source:'autobuild',origin:'autobuild',tier,model,cost_usd,inflight,action,outcome}`).
   This is the same spine the `$`-cap reads and the cockpit tails. No silent steps.
4. **VERIFIED — fail-loud, never `done` on red.** A step is only marked `done`
   after its verification command exits 0. On red it is marked `failed` (not retried
   blindly) and surfaced to `STATUS.md ## Known broken`.
5. **FAIL-OPEN for J / the engine.** The runner is a background producer. It must
   never block J's interactive session, the dev server (:3000), or any heartbeat
   tick. RTH defers (see below). The `companion-halt.flag` kills it. J holds the
   off-switch (OP-25 / OP-32).

## The fire's order of operations (one invocation)

```
1.  HALT GATE      isHalted(root) (guard.js) || exists(companion-halt.flag) -> exit 0, log "halted"
2.  RTH GATE       market open 09:30-15:55 ET ? -> DEFER: append the task title to
                   automation/overnight/queue.md for the after-hours conductor, log
                   "deferred-rth", exit 0. (L54 starvation scar: ALL tiers defer, not
                   just Opus -- the free face is the only thing live during RTH.)
3.  PICK           step = nextBuildStep(root); if null -> log "idle (queue drained)", exit 0
4.  CLAIM          markStep(root, step.id, "in_progress")   // so a second fire can't double-run it
5.  LOG SPAWN      logActivity({source:'autobuild', action:'spawn', tier:step.tier, ...})
6.  ESCALATE       runEscalation(root, {id:step.id, model: routeModel(step.tier),
                                        task: step.task, origin:'autobuild'})
                   // guard.js is built INSIDE runEscalation -- callers cannot bypass it.
7.  READ RESULT    tail companion-ask-results.jsonl for id==step.id -> {ok, summary, cost_usd}
8.  VERIFY         run step's verify cmd (see "Verification" below) -> exit code
9.  MARK + LOG     ok && verify==0 -> markStep(step.id,"done",{outcome,ask_id})  + logActivity "done"
                   else            -> markStep(step.id,"failed",{outcome})       + logActivity "failed"
                                      + append a line to STATUS.md ## Known broken
10. APPROVE CARD   if step.tier == "doctrine" (or origin would be voice): DO NOT auto-apply.
                   The escalated Claude returns proposed text only (guard denies the write);
                   the runner writes the shadow/diff and enqueues a companion-approvals.json card.
                   markStep(step.id,"blocked") until J taps Approve.
11. EXIT           one step done. Next fire handles the next pending item.
```

## Model routing (`routeModel(tier)`)

Maps the queue's `tier` onto `MODEL_MAP` in `escalate.js` (`{opus, sonnet, haiku}`):

| `tier`      | model    | why |
|-------------|----------|-----|
| `readonly`  | `haiku`  | rote read / tabulate / log-lookup |
| `authoring` | `sonnet` | graded build/fix under the guard's safe surfaces |
| `doctrine`  | `opus`   | hard reasoning for a DRAFT — **propose-only, RTH-deferred** |

(All three already exist in `MODEL_MAP`; no new wiring needed.)

## Verification — how each step proves itself

The runner does **not** trust the SDK's `ok` alone (OP-25: audit outputs, not exit
codes). Each queued task's `task` string ends with an explicit `Verify:` clause; the
runner runs the matching command and requires exit 0:

- **JS the step touched** → `node --check <file>` for each edited `.js`, and
  `node gamma-companion/smoke-guard.js` must still print `14 passed, 0 failed`
  (the guard must never regress as a side effect of a build step).
- **Python the step touched** → `backtest/.venv/Scripts/python -m pytest <targeted test>`
  (use the **backtest venv**, not system Python — pandas/pytest live there), or a
  `python -c` import smoke for face/presence-only edits.
- **A new node smoke** the step shipped → run it; exit 0 required.
- If the step edited nothing verifiable (e.g. it only wrote a `markdown/` doc),
  verification is "file exists + non-empty."

Verification **failing** marks the step `failed` and writes a `STATUS.md` flag — it
does **not** silently mark `done`. A `failed` step does not re-enter `nextBuildStep`
(only `pending` does), so it waits for a human to inspect, fix the queue line, and
reset its status to `pending`.

## Who fires it (NOT wired here — design only)

- **Option A — a `Gamma_CompanionBuild` scheduled task** (after-hours only, e.g.
  hourly 16:00–08:00 ET) using the headless pythonw→node chain pattern from the
  window-leak fix, calling a thin `node gamma-companion/run-build-step.js` wrapper
  that performs steps 1–11 above **once**. (Wrapper + task install are a *future*
  step — do not create the scheduler in this pass.)
- **Option B — the after-hours conductor** calls `nextBuildStep` as one STAGE in
  its existing loop, reusing its STAGE-3 backpressure (pytest/gym) as the verify
  step and its proposal bus for doctrine-tier cards.

Either way the bounded/gated/logged/verified contract above is identical; only the
*trigger* differs. **This doc wires no scheduler** — per the safety envelope, J (or
the conductor) turns it on.

## The seeded queue (`automation/state/companion-build-order.jsonl`)

Seeded with the blueprint's next safe items, all `tier:authoring`, all `pending`:

1. `wire-activity-ledger` — `lib/activity.js` + `logActivity()` spine (the meter steps 5/9 log to).
2. `wire-obligations-state` — surface `companion-obligations.json` in `/api/state` (read-only).
3. `wire-soul-face-brain` — `automation/presence/GAMMA-VOICE.md` on `SOUL.md`, loaded by `face_brain.py`.
4. `tag-origin-chat` — tag `origin` at `/api/chat` so the guard can force voice→propose-only.
5. `proactive-loop-narrate` — face narrates obligation gaps (narrate only, never auto-fire).
6. `diagram-stream-nodes` — `lib/artifact.js` (`parseArtifact`+`sanitizeSvg`) + sandboxed-iframe node-by-node render.
7. `build-task-store` — `lib/buildtasks.js` + threaded `build_id`/`task_id` so BUILD-mode checkboxes auto-tick.

Add new safe items by appending one JSONL line (`{id,title,task,tier,status:"pending"}`).
**Never** queue a task whose `task` asks to edit `CLAUDE.md` / `params*.json` /
`heartbeat*.md` / `filters.py` / place an order — the guard would deny it anyway, but
the queue should not even ask. Doctrine work goes in as a `tier:doctrine` **DRAFT**
that lands an Approve card (step 10), never an auto-apply.

## API surface (`autobuild.js`)

| fn | returns | notes |
|----|---------|-------|
| `nextBuildStep(root)` | next `pending` task or `null` | queue order; skips failed/blocked/done |
| `markStep(root, id, status, extra?)` | updated task or `null` | atomic tmp+rename write; refuses invalid status / unknown id; `extra` may carry `outcome`, `ask_id` |
| `readQueue(root)` | array of tasks | malformed lines skipped + logged, never thrown |
| `queueSummary(root)` | `{pending,in_progress,done,failed,blocked,total}` | one-line snapshot for STATUS/activity |
| `orderPath(root)` | absolute path to the JSONL | |

Verified by dry-run: 7 tasks parse, `nextBuildStep` returns `wire-activity-ledger`,
`markStep` round-trips `in_progress`→`done` advancing the pointer, invalid status and
unknown id both refused, queue restored intact.
