---
name: skill-author
description: Invoke skill-author — converts Analyst's recurring-diagnostic-pattern findings into re-usable Claude Code skills. Reads one item from `_skill-inbox/`, writes `.claude/skills/{slug}/SKILL.md` + `backtest/autoresearch/{slug}.py` + appends `markdown/infra/SKILLS-CATALOG.md` row + symptom→diagnostic table row. If item has `kind: tune`, routes to `skill_tune.py` for fine-tuning. NEVER edits live doctrine. Per OP-22 engine-benefit work — ships without ratification.
context: fork
agent: skill-author
allowed-tools: Bash Read Grep Glob Write Edit
---

# skill-author — author one skill from inbox

You are running as skill-author in a forked subagent context. Full persona in `.claude/agents/skill-author.md`.

## Your task this fire

Pick ONE item from `strategy/candidates/_skill-inbox/` (oldest first, README excluded). If `kind: tune` → run `skill_tune.py` against the named target. Otherwise → author new SKILL.md + module + catalog row + smoke test.

Argument (optional): `$ARGUMENTS` — specific filename or skill-name to target. Otherwise oldest-first.

## Required output shape

```
SKILL SHIPPED
  inbox item:    {date}-{slug}.md
  SKILL.md:      .claude/skills/{slug}/SKILL.md
  module:        backtest/autoresearch/{slug}.py
  catalog row:   section {N}
  smoke test:    PASS
  cost usd:      $0.XX
```

Or `SKILL TUNED` (tune-mode), `SKILL TUNE DEFERRED` (live-doctrine denylist hit), or `NO WORK`.

## What you should NOT do this fire

- Touch validators in `crypto/validators/` — file _validator-inbox/ + EXIT
- Touch live doctrine (`heartbeat.md`, `params*.json`) — refuse with denylist
- Edit other skills unless the inbox item is `kind: tune`
- Skip the smoke-test step — the skill must run before the fire ends
- Spend >25 turns
