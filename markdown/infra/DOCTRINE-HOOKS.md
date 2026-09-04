# Doctrine hooks — the enforcement layer under CLAUDE.md

> Shipped 2026-08-29 (Sat 16:02 ET) after J: *"I'm tired of it not working. I want Gamma to be
> smarter and autonomous."* Off-switch: `GAMMA_HOOKS_OFF=1` → `touch automation/state/hooks/OFF`
> → `git revert`. Registered in git-tracked [`.claude/settings.json`](../../.claude/settings.json).

---

## Why doctrine stopped sticking — the measured root cause

Not a discipline problem. Three mechanisms, all documented by Anthropic:

**1. CLAUDE.md is a suggestion, by construction.**
> "CLAUDE.md content is delivered as a user message after the system prompt, not as part of
> the system prompt itself. Claude reads it and tries to follow it, but there's **no guarantee
> of strict compliance**." — [Anthropic, memory docs](https://code.claude.com/docs/en/memory)

**2. Adherence falls as the instruction payload grows — and ours is ~20K tokens.**
Anthropic's stated target is **under 200 lines per file**. Measured on this box, always-on,
every session:

| File | Lines | ~Tokens |
|---|---:|---:|
| Project `CLAUDE.md` | 279 | 7,801 |
| `MEMORY.md` index | 148 | 4,272 |
| `~/.claude/CLAUDE.md` | 107 | 1,675 |
| `~/.claude/rules/README.md` ← *install guide, loaded as doctrine* | 107 | 1,111 |
| `~/.claude/rules/common/*.md` (11 files) | 450 | 4,975 |
| **TOTAL** | **1,091** | **~19,834** |

Every OP added to fix non-compliance made every *other* rule slightly less likely to be
followed. **The instinct to fix this by adding more doctrine is the thing making it worse.**

**3. The register works against us.**
> "Write the text as **factual statements** rather than imperative system instructions… Text
> framed as out-of-band system commands can trigger Claude's **prompt-injection defenses**."

CLAUDE.md is written in shouted-imperative register (`⛔ BANNED / MUST / NEVER / MANDATORY`).
That is precisely the register the docs warn gets discounted.

**The fix is not more prose. It is enforcement:**
> "Use CLAUDE.md for 'we do it this way here.' Use permissions or **hooks** for … anything that
> **must never happen**, where you need a **guarantee instead of guidance**."

---

## What is wired

All seven handlers live in one dispatcher, [`setup/hooks/gamma_doctrine.py`](../../setup/hooks/gamma_doctrine.py),
with pure tables in [`doctrine.py`](../../setup/hooks/doctrine.py). Deterministic Python, **$0/day** —
no model call anywhere in the layer.

| Event | Does | Enforces |
|---|---|---|
| `SessionStart` | Injects a ~250-token prime card: ET clock, market state, freeze countdown, 5 load-bearing facts | Survives `/compact` — the matcher includes `compact`, which is exactly where in-session doctrine used to die |
| `UserPromptSubmit` | Keyword-routes **one** situational rule; silent by default | Situational beats always-on. A rule that arrives when relevant gets read; one that arrives every turn is wallpaper |
| `PreToolUse` | **Hard block**: frozen trading path, generated surfaces, scarred shell commands. **Warn-only**: a subagent spawn with no boundaries | Freeze integrity, OP-22, L214/C34, `et_clock`; the delegation contract |
| `PostToolUseFailure` | 2nd identical failure → names the loop and the external-kill signature | `debugging.md` "stop repeating the failing action" |
| `Stop` | **Hard block**: turn ends on a permission question, or claims success with zero tool calls | **OP-0** and **OP-33** — J's #1 and #2 documented frustrations |
| `SubagentStart` | Injects the prime card | Built-in `Explore`/`Plan` agents **skip CLAUDE.md entirely** — they had been running doctrine-blind |
| `InstructionsLoaded` | Appends to `automation/state/hooks/instructions-loaded.jsonl` | The instrument for "is my doctrine even loading?" — a repeated question is a missing instrument |

### The three hard blocks

1. **Config freeze** (`2026-08-31 → 2026-10-30`). Edits to `params.json`, `filters.py`,
   `risk_gate.py`, `strategies.py`, `exit_manager.py`, `fleet_executor.py`,
   `build_shared_signal.py`, `heartbeat_core.py`, `accounts.json` are denied inside the window.
   A trading-path edit silently invalidates `go_live_gate.py`'s 20-day score — the most
   expensive available mistake between those dates, and previously guarded by prose alone.
   Pre-registered kill-type risk reductions carry `GAMMA_FREEZE_OVERRIDE`, and may ship only
   from the **safety checkpoint on `2026-09-29`** — which is a date *inside* the freeze, not
   its end. Risk EXPANSIONS wait for `2026-10-30` regardless.
   > ⚠️ This paragraph read `2026-08-31 → 2026-09-29` until 2026-09-03. The code
   > (`setup/hooks/doctrine.py:150/158/162` — `FREEZE_START` / `FREEZE_END` /
   > `FREEZE_SAFETY_CHECKPOINT`) is authoritative and was corrected on 2026-09-02; this doc
   > had kept the pre-correction window, which read as "the freeze is over" a month early.
2. **Generated surfaces.** `MAP.md`, `HOME.md`, `SHADOW.md`, `*/INDEX.md`, `journal/YYYY-MM-DD.md`
   are written only by `obsidian_vault_sync.py`. A hand-edit reads as "done" and is overwritten
   on the next sync — a silent revert. Denied, with the generator named in the message.
3. **Scarred shell commands.** `TZ=America/New_York` (returns UTC on this Mountain-time box —
   the original OP-32 lockout cause), tree-wide `git checkout .` / `git reset --hard`
   (reverts live decision-gating state backward, L214), `git push --force` (OP-0 #3).

### The one warn-only guard — spawn boundaries

`Task`/`Agent` spawns are read, never blocked. A spawn whose prompt is under ~200 characters,
or which contains none of *objective / return / do not / never / schema*, gets a note injected
via `additionalContext` naming the four fields the delegation contract requires
([`AGENT-ORCHESTRATION.md`](../doctrine/AGENT-ORCHESTRATION.md), soul file
[`automation/prompts/orchestrator.md`](../../automation/prompts/orchestrator.md)).

It warns rather than denies because a boundaryless spawn is a **quality** problem — nothing
irreversible, no live money, no secret, no generated surface — and the cost lands in the
*worker's* tokens, where the spawning session never sees it. Failing closed on a quality
signal is the OP-32 shape this layer is not allowed to have. Guards:
[`test_spawn_boundary_guard.py`](../../setup/hooks/test_spawn_boundary_guard.py).

---

## Safety — read before editing

The one failure mode this layer may never have is locking J out (the 2026-05-22 OP-32 scar).

- **Fail open, always.** Every handler is wrapped; any unexpected error exits `0` = allow.
  Unknown event, malformed stdin, unreadable clock, missing state dir → allow.
- **Narrow, suffix-matched denylists.** Anything not explicitly named is allowed. 49 regression
  guards in [`test_doctrine_hooks.py`](../../setup/hooks/test_doctrine_hooks.py), and the
  majority of them assert that *ordinary work is not blocked*.
- **The `Stop` guard cannot loop.** It honours `stop_hook_active` and blocks at most **once per
  session per rule**, ledgered in `automation/state/hooks/session-*.json`.
- **Escalations are never blocked.** A turn mentioning live money, a secret, a force-push, or
  `OP-0 #` is a legitimate ask and passes through.
- **No console flash.** Invoked via `pythonw.exe`; verified 2026-08-29 that it passes stdout,
  stderr and exit codes through Claude Code's pipes.

## Verification (2026-08-29, quoted)

```
49 passed in 0.71s          # setup/hooks/test_doctrine_hooks.py
```
Live end-to-end in the running session — `TZ=America/New_York date` returned:
```
Bash TZ returns UTC on this box (it runs Mountain time), so this reads ~2h wrong.
ET comes from setup/scripts/et_clock.py. Guard: test_et_clock.
```
Every hook event used here was confirmed present in the installed `claude.exe` **v2.1.205**
before being designed on. `PreModelSwitch` was **absent** from this build and is deliberately
unused.

---

## The other half of the fix: the diet

Hooks enforce; they do not shrink the payload. The ranked trims, largest first:

| Trim | ~Tokens back | Note |
|---|---:|---|
| Delete `~/.claude/rules/README.md` from the rules dir | 1,111 | It is an *install guide for the rules system*, loaded as doctrine every session in every project. Pure noise. |
| Resolve `rules/common/agents.md` vs memory | ~400 | agents.md says *"ALWAYS use parallel Task execution"*; auto-memory says *"don't add workers — multi-agent = 3-10× tokens."* Direct contradiction → "Claude may pick one arbitrarily." |
| Path-scope `testing.md` / `coding-style.md` to code paths via `paths:` frontmatter | ~800 | An 80 %-coverage TDD mandate is unfollowable in a research repo of one-off analysis scripts. Unfollowable rules train non-compliance in the followable ones. |
| Move archived OP prose + lesson-cluster table out of `CLAUDE.md` | ~1,500 | The C1–C36 index is a lookup table, not per-turn context. Belongs behind MAP.md. |

Target: **CLAUDE.md under 200 lines**, the five load-bearing facts in the prime card, everything
else situational or on-demand. Not yet done — queued, not claimed.

## Related

[[markdown/infra/CONTEXT-LEANNESS]] · [[markdown/doctrine/LESSONS-LEARNED]] ·
[[markdown/doctrine/OP-33-verify-visibility]] · [[markdown/infra/DOC-ARCHITECTURE]]
