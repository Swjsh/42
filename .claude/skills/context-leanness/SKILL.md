---
name: context-leanness
description: Keep CLAUDE.md (and any always-loaded context) under its token budget so the cache-read prefix stays lean. Invoke when the context-budget guard reports YELLOW or RED, when automation/state/context-budget.json status is not GREEN, when CLAUDE.md grows past ~8K tokens, or proactively in the after-4pm work block. Measures, backs up, relocates reference-only blocks to the appropriate markdown/ subfolder with pointers, dedupes, then verifies integrity. NEVER changes rule semantics, account params, the strategy version, or refusals. NEVER edits during market hours.
allowed-tools: Bash Read Grep Glob Write Edit
---

# Skill: context-leanness

> Full spec + file map + loop diagram: `markdown/infra/CONTEXT-LEANNESS.md`.

Gamma's self-maintenance loop for the soul file. Every token in `CLAUDE.md` is
cache-written then **cache-read on EVERY Claude Code turn**. Token forensics
(`analysis/token-forensics/`) show cache reads dominate the bill, so trimming the
always-loaded prefix is the single most-multiplied cost lever in this system.
This skill makes leanness a closed loop: **measure -> back up -> relocate/dedupe
-> verify -> log**, with a hard safety boundary so it can run autonomously.

> J granted Gamma permission to edit CLAUDE.md for leanness (2026-06-16). That
> permission is STRUCTURAL ONLY. This skill never touches what the rules *mean*.

---

## HARD SAFETY BOUNDARY (read first, every time)

NEVER, under any circumstance:
- Change the wording or meaning of **Rules 1-10**.
- Change any **account number, equity, key id, kill-switch %, risk %, or param**.
- Change the **`Current rule version: vNN`** pin or any strategy parameter.
- Change the **`## What I will refuse`** section.
- Edit CLAUDE.md **during market hours** (09:30-15:55 ET, weekdays). This is
  Rule 9 (no mid-session changes). The guard already blocks the auto-trip in
  that window; if invoked manually during market hours, STOP and defer.
- Delete content. Reference material is **relocated** into the appropriate `markdown/` subfolder (per the CLAUDE.md filing rule), never dropped. NEVER write to `docs/`, `doctrine/`, or `workflow/` — they are tombstoned legacy dirs.

ALWAYS:
- **Back up** CLAUDE.md verbatim before the first edit.
- **Verify** with the engine after editing; if any check fails, **restore the
  backup and abort** (flag it in `STATUS.md` `## Known broken`). A failed trim
  is a no-op, never a half-edited soul file.
- **Log** the change to `CHANGELOG.md` and the CLAUDE.md `## Update log`.

---

## Benchmarks / guard scores (source of truth: `setup/scripts/context_audit.py`)

| Score | Tokens (budget 8000) | Meaning | Action |
|---|---|---|---|
| GREEN | < 7600 (<95%) | Lean | none |
| YELLOW | 7600-8000 (95-100%) | Near ceiling | trim at next after-4pm block |
| RED | > 8000 (>100%) | Over budget | trim now (after hours); guard auto-trips |

Token method: `tiktoken cl100k_base` if available, else `bytes/3.6` estimate.
Budget and thresholds live ONLY in the engine -- never hardcode them elsewhere.

---

## The full cycle

### 1. Measure
```bash
python setup/scripts/context_audit.py report
```
Read the section table and the **Movable candidates** list. Candidates are
reference-heavy blocks (>=500 tok OPs, `<details>` archives) -- the right things
to relocate. Confirm current `status` in `automation/state/context-budget.json`.

### 2. Back up (before any edit)
```bash
mkdir -p automation/state/claude-md-backups
cp CLAUDE.md "automation/state/claude-md-backups/CLAUDE-md-pre-trim-$(date +%F).md"
```
(backups live in gitignored `automation/state/` — git already versions CLAUDE.md; never back up into `docs/`)

### 3. Relocate reference-only blocks (the main lever)
For each chosen candidate:
- Move the block **verbatim** into the appropriate `markdown/` subfolder file (e.g.
  `markdown/doctrine/LESSONS-CHRONOLOGICAL-LOG.md`, `markdown/infra/KITCHEN-SPEC.md`, or a new one in the right topic folder),
  with a one-line dated header noting it came from CLAUDE.md.
- Replace it in CLAUDE.md with a **pointer line** linking to that doc.
- Good targets seen historically: pre-consolidation lesson logs, full Kitchen /
  subsystem specs, long `<details>` archives, duplicated paragraphs.

### 4. Dedupe wording
Merge repeated paragraphs (keep one canonical statement). Tighten prose. Do NOT
remove a fact -- only remove repetition.

### 5. KEEP (do not move) -- these are load-bearing in-file
The 10 rules, Account context table, kill switches, strategy/v-pin, the work-
cadence table, the **Lessons index table** (the consolidated quick view), the
refusals. These earn their tokens.

### 6. Verify (the safety net)
```bash
python setup/scripts/context_audit.py verify
```
All checks must PASS (10 rules, both accounts, kill-switch, rule-version pin,
refusals, cadence table, lessons index, all doc pointers resolve, under budget).
If ANY fail: `cp` the backup back over CLAUDE.md, note it in `STATUS.md`, stop.

### 7. Close the loop
```bash
python setup/scripts/context_audit.py check          # refresh state -> should read GREEN
```
Add a one-line entry to `CHANGELOG.md` and the CLAUDE.md `## Update log`
(what moved, where, before/after tokens). Done.

---

## How this gets triggered

- **Autonomously:** `setup/scripts/check-context-budget.ps1 -AutoFix` (scheduled
  after-hours) trips Claude here when status is RED, only outside market hours.
- **In-context alert:** the session-start digest surfaces the budget line on
  every wake -- if it reads YELLOW/RED, invoke this skill in the after-4pm block.
- **Manually:** run the skill any time to proactively trim toward GREEN.

This is the prevention encoded so re-bloat cannot happen silently
(CLAUDE.md OP-25 self-correction mandate).
