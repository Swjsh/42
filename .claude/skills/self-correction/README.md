# self-correction — one-shot handoff skill

A portable Claude skill that makes Claude **actually learn from your corrections.** When you say
*"no, don't do that"* or *"I already told you"*, Claude records a durable rule and follows it every
session afterward — so you stop having to give the same correction twice.

This is the standalone, work-safe version of the inline self-improvement loop. It is **self-contained**:
no trading code, no daemons, no scheduled tasks, no network. Just a skill file plus one human-readable
memory file you fully control.

## What's in here
```
self-correction/
├── SKILL.md                 # the skill itself (Claude reads this)
├── README.md                # this file — install + safety review
└── corrections/
    └── CORRECTIONS.md       # your correction memory (starts empty, grows as you correct Claude)
```

## Install (any computer, any repo)
1. Copy the whole `self-correction/` folder into your project's `.claude/skills/` directory.
2. That's it. Invoke it with `/self-correction`, or just tell Claude at the start of a session:
   *"Use the self-correction skill — load my corrections and remember any new ones."*
3. From then on: whenever you correct Claude, it writes the rule to `corrections/CORRECTIONS.md` and
   confirms. Every future session, it reads that file first and follows your rules.

## How to use it day-to-day
- **Correct normally.** Say *"stop doing X"* / *"don't do that"* / *"do it this way instead."* Claude
  acknowledges, applies it now, and saves it as a standing rule.
- **Check what it learned.** Open `corrections/CORRECTIONS.md` anytime — it's plain Markdown.
- **Edit or wipe.** Change or delete any rule by hand. Your edit wins over Claude's memory.
- **Forget a rule.** Say *"forget correction C7"* / *"you can do X again."*

## Safety review (for a locked-down / work environment)
Hand this section to your work Claude (or your security reviewer) — the skill is designed to pass:

| Concern | How this skill handles it |
|---|---|
| **Code execution** | None. The skill never runs commands. Corrections are guidance Claude *follows*, never a script it *executes*. `allowed-tools` is read/write/search only — no Bash, no shell. |
| **Network / exfiltration** | None. It reads and writes exactly one local file (`corrections/CORRECTIONS.md`). No HTTP, no external calls. |
| **Secrets / PII** | Explicitly prohibited. SKILL.md instructs Claude to never write credentials, keys, tokens, or personal data into the memory; record the *rule* in generic terms, not the sensitive value. |
| **Auditability** | Total. The memory is plain human-readable Markdown in your repo. You can read every rule, edit it, or delete it. Nothing is hidden or encoded. |
| **Scope** | Confined to the workspace's own `corrections/` folder. The skill never reaches outside the repo. |
| **Reversibility** | Full. Delete the folder and all "learning" is gone; delete one entry and that one rule is gone. No residual state anywhere else. |
| **Background processes** | None in the core skill. The optional hook below is opt-in and clearly marked; omit it for the easiest review. |

The security-review summary in one line: *it is a structured note-taking convention, not an automation
— Claude writes your rules to a file you own and reads them back; it cannot run, send, or hide anything.*

## Optional auto-capture hook (advanced — omit for the simplest review)
The core skill is complete without this. If your environment supports a Claude Code `UserPromptSubmit`
hook and you want corrections captured automatically (belt-and-suspenders, so a correction is never
missed even if Claude forgets to record it), add a small hook that:
1. Reads the user prompt from stdin (the hook contract passes it as JSON).
2. Matches it against the same correction phrases listed in SKILL.md.
3. On a match, appends a one-line "correction candidate" to a queue file and emits a single context
   line nudging Claude to honor and persist it this turn.
4. **Fails open and silent:** any error exits 0 with no output — it must never block your prompt.

Keep the hook **dumb** (capture only); all judgment about whether something is really a standing rule
stays in the skill (move 2), where you can see and approve it. A reference implementation of exactly
this pattern lives in the source project at `setup/hook-detect-correction.ps1` (PowerShell). Port it to
your shell of choice, or skip it entirely — the skill works fine on its own and is easier to
security-clear without it.

## Why this exists
The default failure mode of an AI assistant is *amnesia*: you correct it, it agrees, and tomorrow it
does the exact same thing because the correction lived only in a context window that got discarded.
This skill gives corrections a durable home so "I told you already" stops being true.
