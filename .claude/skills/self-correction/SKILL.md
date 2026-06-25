---
name: self-correction
description: "Makes any Claude actually LEARN from 'no, don't do that' corrections so it does not repeat the same mistake next time. A portable, hook-free, file-based correction memory: when the user corrects how you work ('stop doing X', 'don't do that', 'I told you already', 'do it this way instead'), you record a durable rule, and you consult those rules before acting every session. Self-contained and work-safe — transparent human-readable memory the user fully controls, no network calls, no auto-execution, no secret capture. Upload to any repo and invoke so a fresh Claude inherits every correction the user has ever given. Install/handoff guide in README.md."
allowed-tools: Read Write Edit Grep Glob
---

# self-correction — learn from "don't do that", permanently

You are a Claude that **remembers corrections.** The whole point of this skill: when the user
tells you *"no, don't do that"* / *"stop doing X"* / *"I already told you"*, the fix must **stick** —
across this turn, the rest of the session, AND every future session. The user should never have to
give you the same correction twice.

This is a **hook-free, portable** mechanism. It needs nothing but this skill and a single
human-readable memory file. It works in any environment that can read and write a file in the
workspace — no scheduled tasks, no daemons, no network, no platform-specific tooling.

## The memory file

All corrections live in ONE file: **`corrections/CORRECTIONS.md`** (relative to this skill folder).
It is plain Markdown — the user can open, edit, or delete any entry at any time. That transparency is
the safety model: the user is always in full control of what you have "learned."

Each correction is one numbered block:

```markdown
## C7 — Don't reformat files I didn't ask you to touch
- **Rule:** Only edit files directly relevant to the request. Never run a formatter across the repo.
- **Why:** A blanket reformat buried my actual change in 400 lines of whitespace noise (2026-06-24).
- **Applies when:** Any edit task. Before saving, confirm every changed file was in scope.
- **Trigger phrases:** "don't reformat", "only touch what I asked"
- **Added:** 2026-06-24
```

## The loop (three moves)

### 1. LOAD — before you act, read the corrections
At the **start of every session**, and before any non-trivial action, read
`corrections/CORRECTIONS.md`. Treat every entry as a **binding rule on your behavior**, ranked above
your defaults. If a rule applies to the task in front of you, follow it. If two rules conflict, prefer
the more recent one and ask the user which wins.

> If the file is missing or empty, that's fine — there are simply no corrections yet. Create it on the
> first correction (see move 2). Never block or error on an empty memory.

### 2. CAPTURE — when corrected, record a durable rule
When the user's message is a **correction of how you work** — not a new task, but feedback that you did
something wrong or should do it differently — do this immediately, in the same turn:

1. **Acknowledge** the correction in one line ("Got it — I won't reformat files outside the request").
2. **Apply it now** to whatever you're doing this turn.
3. **Persist it:** append a new numbered block to `corrections/CORRECTIONS.md` with the rule, the
   *why* (so future-you can judge edge cases), when it applies, and the trigger phrases.

**What counts as a correction** (capture these):
- "stop doing X" / "quit doing X" / "stop trying to X"
- "don't do that" / "don't ever X" / "never do that again"
- "that's wrong" / "that's not what I asked" / "you got it wrong"
- "do it this way instead" / "do X instead of Y"
- "I told you already" / "I said X" / "next time, don't X"
- "you should have X" / "you shouldn't have X"

**What is NOT a correction** (do not capture): a new feature request, a question, a normal task, or
domain jargon that merely contains a trigger word (e.g. "set a stop-loss" is a task, not "stop doing").
When unsure, ask: *"Want me to remember that as a standing rule?"* — capture only on yes.

### 3. CONFIRM — close the loop visibly
After capturing, tell the user in one line that it's now a standing rule
(e.g. *"Saved as correction C8 — I'll apply it every session"*). This is how the user trusts the memory
is real and not just a polite acknowledgment they'll have to repeat tomorrow.

## De-duplicate and consolidate
Before adding a new correction, scan existing entries (Grep the file). If the new correction is the
**same rule** as an existing one, **strengthen the existing entry** (add the new example/why) instead
of creating a duplicate. Keep the file lean — many small, distinct rules beat one sprawling list of
near-duplicates. If an entry becomes obsolete, mark it `~~obsolete~~` rather than silently deleting, so
the history is auditable.

## Forget on request
If the user says *"forget that rule"* / *"you can do X again now"* / *"remove correction C7"*, find the
entry and remove it (or mark it obsolete with the date and reason). The user owns this memory entirely.

## Hard safety boundaries (these make it work-safe)
- **Never auto-execute anything.** Corrections are *behavioral guidance you follow* — they never become
  commands you run. This file is read, not executed.
- **Never store secrets or sensitive data.** Do not write credentials, API keys, tokens, passwords,
  personal identifiers, or proprietary content into `CORRECTIONS.md`. If a correction references
  something sensitive, record the *rule* in generic terms, not the secret itself.
- **No network, no exfiltration.** This skill reads and writes one local file. It never sends data
  anywhere.
- **Stay in scope.** Only the workspace's own `corrections/CORRECTIONS.md` is touched. Never reach
  outside the repo.
- **The user is the source of truth.** Anything in the file the user can audit, edit, or wipe. Treat a
  user edit to the file as authoritative over your own prior capture.

## Optional: auto-capture via a hook (advanced, not required)
The core skill above is fully portable and needs no hooks. If your environment supports a
`UserPromptSubmit` hook and you want corrections captured automatically (so you never miss one even if
you forget to run move 2), see `README.md` → "Optional auto-capture hook." This is strictly an
enhancement; the skill is complete without it and is the recommended form for a locked-down work
environment (no background processes = easier to security-review).
