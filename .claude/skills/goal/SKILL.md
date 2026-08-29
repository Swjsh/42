---
name: goal
description: "Open, check, or close a durable multi-fire GOAL — the one mechanism for work that outlives a single session/context window. Creates automation/state/goals/GOAL-<ID>.md (schema: DONE-WHEN / OPERATING RULES / QUEUE / J-DECISIONS / PROGRESS LOG / HONEST STATE) + points automation/state/active-goal.json at it. Once active, TWO consumers already read the pointer for free: conductor.md STAGE 1 clause 0a routes each scheduled fire to the goal's top `[ ]` QUEUE item, and the Stop hook (gamma_doctrine.py::_check_goal_continuation, already shipped) keeps THIS session going for up to max_continuations_per_session extra turns while work remains. Invoke as `/goal open \"<J's directive, verbatim>\"`, `/goal status`, `/goal next`, or `/goal close [reason]`. disable-model-invocation — fires only on the literal command, never model-initiated, so a goal is never opened without J actually typing it."
allowed-tools: Read Write Edit Bash Grep Glob
disable-model-invocation: true
---

# /goal — durable cross-fire work tracking

A GOAL is for work that needs more than one fire/session to finish and must survive
compaction, a crashed session, or a scheduled-task wake. It is **not** for anything
that fits in one turn — use TodoWrite for that. One goal is active at a time; opening
a new one while another is active requires closing the old one first (or leaving it
`[x]`/DONE and archiving it — see Close, below).

**The consumers already exist — this skill only builds the producer.** Read
`setup/hooks/gamma_doctrine.py::_check_goal_continuation` and
`setup/hooks/doctrine.py::goal_next_open_item` / `goal_expired` /
`goal_should_continue` before changing the schema below — they parse
`active-goal.json` and the goal `.md` by exact field name and exact `## QUEUE`
heading text. Breaking the schema silently breaks both consumers.

## `/goal open "<quote>"`

1. **Check `automation/state/active-goal.json` first.** If it exists and `active:true`
   and not expired, do not silently overwrite it — tell J the current goal (id + top
   open item) and ask whether to close it first. (This is the one branch where asking
   is correct: overwriting another goal's pointer is not reversibly-obvious to the
   next session that reads it.)
2. Pick a short, dated `GOAL-<SLUG>-<YYYY-MM-DD>` id (uppercase, hyphens).
3. Write `automation/state/goals/GOAL-<ID>.md` using the schema template below.
   **`## DONE-WHEN` is written BEFORE any work starts and must be falsifiable** — a
   null/negative result (the thing doesn't work, the edge doesn't exist) is a valid
   terminal state, not a failure to avoid. Do not start the QUEUE until DONE-WHEN is
   written.
4. Write `automation/state/active-goal.json`:
   ```json
   {"id": "GOAL-<ID>", "active": true,
    "opened_at_et": "<et_clock.py output>",
    "expires_at_et": "<YYYY-MM-DD, default +7 days>",
    "file": "automation/state/goals/GOAL-<ID>.md",
    "queue_id": "GOAL-<ID>",
    "max_continuations_per_session": 3,
    "last_next_item": null}
   ```
   `expires_at_et` is a real brake, not decoration — `goal_expired()` stops the Stop-
   hook continuation once it passes, and `active-goal.json` with a stale expiry is
   how a goal quietly stops being routed to. Default 7 days; a bounded weekend push
   can use less, a multi-week research thread can use more — say which and why in
   one line.
5. Add **exactly one** row to `automation/overnight/queue.md` under `## Active
   backlog`, exact grammar (breaking this grammar is the L-class bug that hid
   `PULLBACK-HOLD-BULL-TRIGGER` for days — see `task_scorer.py::_extract_field_last`
   docstring):
   ```
   - [ ] GOAL-<ID> (HIGH, goal) :: <one-line goal> — file: automation/state/goals/GOAL-<ID>.md :: depends:none :: status:in_progress
   ```
   **ONE LINE. No progress prose appended under it, ever** — all progress lives in
   the goal file's own PROGRESS LOG. `task_scorer.py::_extract_field_last` scans the
   whole block and takes the LAST `status:` match; a second line under the row
   silently flips readiness.
6. Report back: goal id, DONE-WHEN, first QUEUE item, expiry. No further action
   needed — conductor STAGE 1 clause 0a and the Stop hook both pick the pointer up
   on their own from here.

## `/goal status` / `/goal next`

Read `active-goal.json` → read the `file` it points at → print: id, DONE-WHEN, the
first `- [ ]` line under `## QUEUE` (this is exactly what `goal_next_open_item()`
returns — reproduce its logic: first unchecked line, `[~]`/`[x]`/`[B]`/`[B-J]` don't
count), continuation count used this session (`automation/state/hooks/session-<sid
first-16-chars>.json` → `goal_continuations`) vs `max_continuations_per_session`,
and days to expiry. `next` alone is the one-line version of the same read.

## `/goal close [reason]`

1. Append a `## HONEST STATE` update to the goal file: DONE-WHEN met / not met (say
   which), what shipped, what's left, and — if not met — the concrete null/negative
   finding rather than a vague "ran out of time."
2. Set `active-goal.json` `"active": false` (keep the file — it's the audit trail;
   never delete a goal pointer, only deactivate it).
3. Flip the `queue.md` row's `status:in_progress` to `status:done` (or
   `status:killed` for a genuine null result) — append, do not rewrite history; the
   row stays ONE line, so replace the whole line in place rather than adding a
   second `status:` field, matching `_extract_field_last`'s "last match wins" scan.
4. Report the closing summary.

## Goal file schema (exact section headers — the Stop hook parses `## QUEUE` by
this literal text, case-insensitive prefix match)

```markdown
# GOAL: <ID>
> J verbatim: "<quote>" — or, if this goal was opened by a build spec / orchestrator
> task rather than a live chat message, say that plainly instead of inventing a quote.

## DONE-WHEN
<falsifiable. Written before work starts. A null result is a valid terminal state.>

## OPERATING RULES
<every goal's rules include, verbatim or paraphrased — never dropped:>
- **CONFIG FREEZE 2026-08-31 → ~2026-09-29**: no trading-path changes except
  pre-registered kill-type risk reductions (STATUS.md 2026-08-29T12:00 ET). A goal
  that queues frozen-path work during the freeze window is illegal — flag it `[B-J]`
  instead of queuing it.
- Every fire that touches this goal calls
  `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n>
  --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"` —
  not bookkeeping: `Test-OutcomeNoop` in `run-gamma-drive.ps1` sums these fields and
  two consecutive no-op fires kill the loop.
- Every `Agent`/`Workflow` fan-out this goal spawns passes `model:"sonnet"`
  explicitly — an in-prompt "run /model sonnet first" is a no-op (2026-07-23 scar,
  2.2M tokens).
- `STATUS.md` gets a line at goal **OPEN and CLOSE only**, never per-fire — it is
  bytes-capped (`status_retention.py`, 45,000-byte cap; ~78KB today) and a per-fire
  line rolls real REVOKE entries off J's surface.
- Never `/loop /goal` — in-session looping accumulates context with nothing
  discarded. One fresh process per fire; the Stop hook's bounded continuation and
  the conductor's fresh-context wake are the two sanctioned continuation paths.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
<items here. The FIRST bare `- [ ] ` line is what the conductor and the Stop hook
both treat as "the next thing to do" — order matters.>

## J-DECISIONS
<items the loop does NOT execute on its own — flag + wait, marked [B-J] above too.>

## PROGRESS LOG
<one line per fire: what happened, what shipped/killed, what's next. Append-only.>

## HONEST STATE
<current truth as of the last fire — what's real, what's UNVERIFIED, what's blocked
and why. Updated at close, and any time the picture materially changes.>
```

## Continuation — you don't have to build this, it already runs

- **Same session, bounded:** `gamma_doctrine.py`'s Stop hook denies the stop (exit 2)
  when `active-goal.json` is active+unexpired and `## QUEUE` has an open item, up to
  `max_continuations_per_session` (default 3) and never on a converged (unchanged)
  next item. This keeps *one* interactive session going a few extra turns — it is
  not infinite autonomy; a looping model can't enforce its own cap, so the hard
  counter lives in the hook, not the prompt.
- **Cross-session:** `automation/prompts/conductor.md` STAGE 1 clause 0a makes the
  goal's top `[ ]` item this fire's task, outranked only by the FUNCTION-FIRST
  fill-funnel check and an Engine RED. `Gamma_Conductor` (alive, scheduled) is what
  actually re-fires — **do not create a new scheduled task**; `Gamma_Drive` is dead
  (`NumberOfMissedRuns 59`) and absent from `quiet-mode-restore.json`'s 114-task
  list, so wiring a goal to it would silently never fire again.

## Fold discipline (OP-22)

A goal file is the ONLY home for durable cross-fire goal state. Do not create a
second ad-hoc `*-goal.md` anywhere else in the repo — that is exactly the drift this
skill exists to end (three of them existed before this build:
`automation/state/overnight-goal.md`, `automation/state/engine-vision-goal.md`,
`automation/overnight/GOAL-REPLAY-TODAY-GREEN.md`, all folded into
`automation/state/goals/` with tombstone pointers left at their old paths).
