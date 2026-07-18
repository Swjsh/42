# Lesson candidate: task_scorer's #1 pick was a 24-day-stale item the underlying infra had already resolved

> Queued by conductor-weekend fire 2026-07-18, ~12:10 ET. lesson-author picks up at next wake fire.

## Symptom
`task_scorer.py --top` returned `POSITION-MONITOR-1MIN` as the single highest-ROI
ready item in `automation/overnight/queue.md` (HIGH priority, engine-design). Its two
downstream dependents (`TRAILING-STOP-WIRING`, `DYNAMIC-EXIT-LOGIC`) were also still
`status:pending`, blocked on it. All three were written 2026-06-24, describing gaps in
the (then-live) 3-min LLM `Gamma_Heartbeat`.

## Root cause
The 3-min LLM heartbeat this item's design was scoped against was **retired on
2026-06-25** — one day after the item was filed — and replaced by the deterministic
`Gamma_HeartbeatCore`, which independently ships the exact behavior the item asked
for: 1-min full-scan+management ticks (verified live this fire: real
`Get-ScheduledTaskInfo`/action-chain read, `every 1 min, 09:30-15:55 ET wd`), tick-driven
`exit_manager` position management (`GAMMA_CORE_MANAGES_EXITS=1` confirmed live in
`run-heartbeat-core.ps1`), and a software chandelier trailing-stop
(`automation/state/fleet/exit_manager.py`'s `hwm_premium`/`profit_lock_mode="trailing"`
ratchet, byte-matching CLAUDE.md's documented "+5% arm / 15% trail" doctrine) that
functionally satisfies `TRAILING-STOP-WIRING`'s ask without ever using Alpaca's native
`trailing_stop` order type. `DYNAMIC-EXIT-LOGIC`'s exact "chart-signal > fixed-%"
priority hierarchy is CLAUDE.md's own live-ratified v15.3 "chart-stop-primary"
doctrine (2026-06-18) — it also carried a MIS-SCOPED dependency on
`RIBBON-LAG-PRICE-STRUCTURE-TRIGGER` (an entry-side gap, unrelated to the exit-side ask
it was coupled to), which nobody had noticed was a false coupling until traced this fire.

None of these three items were ever re-audited against the infra that made them moot,
because nothing in the queue format or `task_scorer.py` checks "is the described gap
still real" — only "is this item syntactically ready" (depends satisfied, not
`in_progress`). A `HIGH` item that describes a real problem on the day it's filed can
silently become false 24 hours later and then sit at the top of the ranked backlog for
weeks, actively misdirecting the next several conductor fires toward re-solving an
already-solved problem instead of the genuinely-open items beneath it.

## Fix (this fire, 2026-07-18)
Closed all three items in `automation/overnight/queue.md` with `[x]` + `CLOSED_SUPERSEDED`
+ the specific evidence quoted (scheduled-task cadence, live env vars, exit_manager
code, CLAUDE.md doctrine cross-ref), original text preserved verbatim for audit trail.
No code changed — this was a queue-hygiene / evidence-gathering task, not an engine edit.

## Encoded in
Nothing graduated to code yet — this is a **first occurrence**, not (yet) a
re-violated pattern, so per OP-25 it should land as prose in LESSONS-LEARNED.md first.
If this class recurs (another queue item found stale-by-superseding-infra), the
graduation target is `setup/scripts/task_scorer.py`: add a lightweight staleness flag —
e.g., diff the item's filed-date against `SCHEDULED-TASKS.md`'s most recent
reconciliation date for any task/infra it names, or a periodic (weekly, $0,
`Gamma_SelfAudit`-adjacent) "does this HIGH item's described gap still reproduce"
sweep — rather than trusting `depends:`/`status:` alone to mean "still real."

## L## (optional)
Next available L# — lesson-author greps LESSONS-LEARNED.md for current max (index runs
through ~L201+ per CLAUDE.md OP-25 as of this writing). Suggested class: new class, or
fold into **C14** (dead/translated-but-unapplied knobs — this is the same family, one
level up: a dead *queue item* instead of a dead *knob*, caught by the same "vary and
assert against current reality" discipline) or **C22** (compound don't accumulate —
queue hygiene as a form of compounding).
