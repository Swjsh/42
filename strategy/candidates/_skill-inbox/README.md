# Skill inbox

Analyst routes here when an EOD finding shows a **recurring audit pattern** worth promoting to a re-runnable Claude Code skill (3+ ad-hoc invocations of the same shape).

## Item format

```markdown
# Skill request: {short name}

> Queued by Analyst {date}. skill-author picks up at next wake fire.

## Recurring pattern observed
{what audit shape keeps re-appearing}

## Proposed slash invocation
`/{slug} [args]`

## What the skill should do
1. Step 1
2. Step 2
3. Step 3

## Inputs (state files / dates / params)
{file paths the skill reads}

## Outputs
{what files the skill writes; what JSON schema}

## Foot-gun this prevents
{which class of investigation does this remove the ad-hoc-rebuild step from}

## kind: tune (optional)
If set, skill-author routes to skill_tune.py instead of authoring new — used for fine-tuning thresholds on an existing skill.
```

## Consumer
`skill-author` agent (`.claude/agents/skill-author.md`) — picked up via wake-protocol Stage 1 priority #4 (oldest-first).

## Output
- `.claude/skills/{slug}/SKILL.md`
- `backtest/autoresearch/{slug}.py`
- `docs/SKILLS-CATALOG.md` row added under right category + tool-selection-guide row
- Inbox item DELETED on success, or renamed `*.STALE.md` after 7 days by Manager.
