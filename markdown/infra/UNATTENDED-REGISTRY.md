# The Unattended Registry — one traffic light per unattended thing

> **Built 2026-08-09** on J's ask: *"we need to find, consolidate, and document all running
> processes, audits, pipelines, etc, anything unattended, then turn it into a nice tile on the
> app that is red or green or yellow light like a traffic light for each bubble. each bubble
> represents an audit or a pipeline. i want to know if things break when they go down now days
> after the facts."*

| Piece | Path |
|---|---|
| **Registry (declarative)** | [`automation/state/unattended-registry.json`](../../automation/state/unattended-registry.json) |
| **Collector** | [`setup/scripts/unattended_health.py`](../../setup/scripts/unattended_health.py) |
| **Snapshot (now)** | `automation/state/unattended-health.json` |
| **Ledger (history)** | `automation/state/unattended-events.jsonl` |
| **Task** | `Gamma_UnattendedHealth` — every 10 min, 24/7, $0 |
| **Surface** | **Vitals** tile on `/gamma` (`dashboard/components/gamma/VitalsTile.tsx` ← `/api/vitals`) |
| **Guard** | [`backtest/tests/test_unattended_health.py`](../../backtest/tests/test_unattended_health.py) — 29 tests |

---

## Why this exists

The rig runs **126 registered Windows tasks and 6 long-lived daemons**. Three partial
instruments already watched pieces of it, and none of them answered *"is all of it alive, and
what broke while I wasn't looking?"*

| Existing instrument | What it covers | Why it didn't answer the question |
|---|---|---|
| `audit_scheduled_tasks.py` | registry-vs-reality bookkeeping for `Gamma_*` tasks | tells you a task is undocumented; says nothing about whether the pipeline it belongs to still produces anything |
| `state_freshness_audit.py` | 17 files on the live decision path | structurally blind to research, audit, comms and infra units |
| `engine_health.py` | the live trading path | is itself one of the unattended things that can die |

And **all three are stateless**. Each run reports *now*. An outage that started Tuesday and
self-healed Thursday left no trace anywhere — exactly the hole J named.

---

## The model: a UNIT, not a task

A bubble is a **unit** — a pipeline, an audit, a daemon, an engine — not a single scheduled
task. `eod-pipeline` is seven tasks; `engine-core` is two tasks plus two artifact contracts
plus two retired tasks that are off on purpose.

Every unit carries a mandatory **`breaks`** field: one sentence naming what *silently
degrades* while it is down.

> A traffic light with no consequence attached is decoration. `breaks` is what turns a red
> bubble into a decision, and it's rendered directly under the failure in the tile.

The guard test enforces it — a unit without `breaks` fails CI.

---

## Three independent axes, worst-wins

| Axis | What it catches | How |
|---|---|---|
| **A — task liveness** | disabled, never-run, nonzero exit code, hasn't fired within its own trigger's cadence | reads the LIVE trigger shape out of Task Scheduler |
| **B — artifact freshness** | the task fires on schedule and writes **yesterday's payload** | delegated verbatim to `state_freshness_audit.evaluate_entry` |
| **C — daemon liveness** | pid file present but the process is gone | pid file → `tasklist` |

Axis B is the one no task-liveness check can see, and it is where this rig's worst outage
lived (2026-07-30: `Gamma_LevelRefresh` disabled → `key-levels.json` frozen → 772 blind ticks).

**Contracts are never copy-pasted.** A unit's artifact can be a bare path string, which is
resolved against `state-freshness-manifest.json` — so a freshness contract lives in exactly
one file. A guard test asserts every string ref resolves (L294).

### Statuses

| Status | Meaning |
|---|---|
| 🟢 **GREEN** | every axis healthy |
| 🟡 **YELLOW** | degraded — or *not yet proven working* (a task that has never fired but is still inside its start-boundary budget) |
| 🔴 **RED** | a critical/high unit failed an axis |
| ⚫ **OFF** | every member is off **by design** (retired / on-demand), with the reason written down |
| 🟣 **UNKNOWN** | the monitor could not look. **Never** rendered as a failure — "I couldn't check" must not read as "it's dead" |

Severity follows unit `criticality`: the same staleness is RED at critical/high and YELLOW at
medium/low — the same ladder `state_freshness_audit` already uses.

---

## Cadence scoring — how false alarms are avoided

A tile that is red every weekend is a tile nobody reads. Three rules keep it honest:

1. **Weekend slack from the live trigger mask.** A `DaysOfWeek`-restricted task (mask 62 =
   Mon–Fri) is legitimately silent all weekend, so unscheduled days are added to its budget.
   A plain daily trigger gets no slack — those tasks *do* fire on weekends even when their
   script self-gates.
2. **A `WeeklyTrigger` carrying a day mask is scored DAILY.** Most of this rig's "weekly"
   triggers are Mon–Fri, i.e. a daily task that skips weekends. Scoring them at 10,080 min
   would hand every one of them a three-week licence to be dead.
3. **An intraday repetition is scored at its daily re-arm.** A `PT1M` repetition running for
   `PT6H30M` of RTH may be quiet all night; scoring it on the 1-minute interval makes it a
   nightly false alarm.

Budget = `cadence × mult + unscheduled-day slack`, where `mult` is 3 for sub-daily tasks
(keepalives skip beats) and 2 for daily/weekly ones — tolerating **exactly one** missed run.

**Never-run tasks** are scored from their trigger's own start boundary, not from epoch. When
the 2026-08-07 task-rebuild wave reset 12 `LastRunTime`s to the sentinel, the naive read
called them 12 chronic outages; they were 12 tasks waiting for Monday. They score YELLOW —
never GREEN — and self-clear on their first real fire.

---

## The memory — the actual ask

Every status **transition** is appended to `unattended-events.jsonl`:

```json
{"ts_et":"2026-08-09 15:23:12","id":"unregistered","name":"Uncovered tasks",
 "from":"GREEN","to":"YELLOW","group":"INFRA","criticality":"low",
 "detail":"Gamma_UnattendedHealth: unclaimed","breaks":"An unclaimed task is UNMONITORED …"}
```

Each unit also carries `since` / `last_green_at` / `down_for` in the snapshot, **carried
forward across runs** — so a unit that went dark on Tuesday still reads `RED · 5.2d` on
Sunday. The ledger is the second, durable source for `since`: if the snapshot is ever missing
or malformed, the collector recovers the timestamp from the ledger rather than resetting every
outage to "just now" (L283 — "carry the field forward" is a convention, not a contract).

Retention cap: 5,000 lines, pruned in place (OP-22).

The tile renders this as the **outage ledger** — newest first, with the transition and its
detail. That is what makes an outage legible days after it ended.

---

## Anti-rot: the scope is computed, never declared

Coverage is diffed against **live truth on every run**:

- a live `Gamma_*` task that no unit claims raises the **Uncovered tasks** bubble (YELLOW)
- a registry task missing from Task Scheduler reddens its own unit

This is the L292 fix (*"a monitor's own coverage SCOPE rots like the thing it monitors"*): the
registry cannot silently narrow behind the rig, because it is re-measured against reality
every 10 minutes rather than declared once at birth.

It proved itself within minutes of shipping — registering `Gamma_UnattendedHealth` before
adding it to the registry flipped the coverage bubble GREEN → YELLOW, and the transition is in
the ledger.

---

## Fail-open contract

**Monitoring fails open; entry fails closed.** This module never gates a trade and never
raises into its caller. An unreadable registry, a dead PowerShell enumeration or a malformed
snapshot degrades that piece to `UNKNOWN` and the run still writes a payload.

A broken monitor must never be able to look like a broken rig, and must never take anything
else down with it.

**The monitor is itself an unattended thing.** The `unattended-health` unit watches its own
task, but a monitor cannot be its own last line of defence — so the tile independently renders
the snapshot's age and warns above 30 minutes: *"These lights are Xm old — the collector itself
may be down."*

---

## Adding a unit

1. Add an entry to `automation/state/unattended-registry.json` with `id`, `name`, `group`
   (`TRADING`/`DATA`/`AUDIT`/`RESEARCH`/`REPORTING`/`INFRA`), `criticality`, `what` and
   **`breaks`**.
2. List its `tasks`. Anything deliberately off goes in `expect_disabled` **with a reason** —
   an un-annotated disable is unambiguously an accident.
3. Prefer an **artifact contract** over task liveness alone: a task that fires and writes
   nothing is the failure mode that costs money. Reference an existing
   `state-freshness-manifest.json` path by string; only inline a contract when the file isn't
   on the live decision path.
4. Run `python setup/scripts/unattended_health.py --no-write` and read the table.
5. `pytest backtest/tests/test_unattended_health.py`.

Never rename a unit `id` without migrating the ledger — the id is the outage history's key.

---

## Reading it

```bash
python setup/scripts/unattended_health.py
```

Or open `/gamma` → **Vitals**. Click any bubble for its failure detail and its `breaks`
consequence; "Show outage ledger" for the history.
