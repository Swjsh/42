---
name: update-docs
description: "Close the loop on any improvement by syncing the documentation. Invoke immediately AFTER shipping a build/fix/validated-edge/new-task/doctrine-change — before declaring the work done. An improvement is NOT finished until the docs reflect it, because the next session (and every autonomous agent) only knows what the docs say. Routes each change to the right home: CLAUDE.md (doctrine the engine must USE), the canonical markdown/ doc (detail), the registries (SCHEDULED-TASKS.md / SKILLS-CATALOG.md + counts), memory (cross-session facts), a graduated guard (for fixes), CHANGELOG.md. NEVER bloats CLAUDE.md past its 8K budget; NEVER edits CLAUDE.md/params during market hours."
allowed-tools: Bash Read Grep Glob Write Edit
---

# Skill: update-docs  ("improvement = update documents")

> The discipline J named 2026-06-29: *"improvement = update documents."* A build that
> isn't documented is invisible — the next session re-derives it, mis-uses it, or never
> uses it at all. The work is done when the docs can DRIVE it without you in the room.

The test for "documented enough": **could a cold session, reading only the docs, find the
new thing and use it correctly?** If no, you're not done.

---

## When to invoke
Right after you ship ANY of: a new module/tool, a scheduled task, a bug fix, a validated
edge, a doctrine/OP change, a new skill/agent, or a meaningful architectural decision.
Make it the closing step of the work, not a someday-task.

---

## The routing table — each change has exactly one right home (don't scatter)

| What you built/changed | Update | How |
|---|---|---|
| A tool/pipeline future SESSIONS must USE | **CLAUDE.md** (tech-stack row or an OP) | Surgical pointer ONLY; detail lives in the markdown/ doc. Respect the 8K budget. |
| The detail / spec / how-it-works | **`markdown/<topic>/`** doc | The canonical record. New doc → matching subfolder + a line in `markdown/README.md`. |
| A new/changed scheduled task | **`automation/state/SCHEDULED-TASKS.md`** | Add the Active-table row AND bump the `NN registered` summary to match (the guard checks both). Reconcile vs the live count (`Get-ScheduledTask Gamma_*`). |
| A new skill | **`markdown/infra/SKILLS-CATALOG.md`** | Append a catalog row. |
| A cross-session fact / lesson learned | **memory** (`~/.claude/.../memory/`) + `MEMORY.md` pointer | One file per fact; link related with `[[name]]`. |
| A bug fix | **a graduated guard** (`backtest/tests/test_graduated_guards.py`) | Engine-wins-loop rule: every fix REDs a pytest on regression. |
| Any doctrine evolution | **`CHANGELOG.md`** | Append an entry; never inline history into CLAUDE.md. |

Rule of thumb: **CLAUDE.md = "this exists, use it";  markdown/ = "here's how";  registries =
"it's wired";  memory = "remember next time";  guard = "it can't regress."**

---

## HARD boundaries
- **CLAUDE.md is lean (8K-token budget).** Add a pointer, not prose; push detail to `markdown/`.
  Check `backtest/.venv/Scripts/python.exe setup/scripts/context_audit.py report` (or chars//4)
  — keep < 7600 (GREEN). If adding pushes it over, relocate something stale (see `context-leanness`).
- **NEVER edit CLAUDE.md / params*.json during market hours** (09:30–15:55 ET, weekdays — Rule 9).
- **Doctrine/OP additions** are J-sanctioned or after-hours; the `lesson-author` agent is the
  canonical OP-25 Lessons-index writer — route lesson L## entries there.
- **Don't duplicate.** One canonical statement per fact. If it's in a markdown/ doc, CLAUDE.md
  links it; it does not restate it.

---

## The cycle
1. **Inventory** what changed this work block (files added/edited, tasks registered, edges validated).
2. **Route** each item via the table above. CLAUDE.md gets only the load-bearing "use-it" pointers.
3. **Reconcile counts/registries** — task count vs live `Get-ScheduledTask`; SKILLS-CATALOG row; `MEMORY.md` pointer line.
4. **Verify**: every new doc pointer resolves (the file exists); CLAUDE.md budget GREEN; the
   scheduled-tasks summary count == the Active-table row count (the doc guards enforce this).
5. **Guard** (for fixes): add/confirm the graduated pytest.
6. **Commit** with a `docs(...)`/`feat(...)` message naming what was documented where.

> This skill is itself an instance of its own rule: it was created the moment "improvement =
> update documents" became doctrine. If you ever build without documenting, that gap is the
> bug — invoke this and close it.
