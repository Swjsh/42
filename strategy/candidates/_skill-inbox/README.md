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

## Inline correction queue (`_correction-queue.jsonl`)

Whenever J corrects Gamma (e.g. "stop doing X", "that's wrong", "do it this way") a JSONL entry is appended here. This is the **inline skill self-improvement** path — ported from Hermes Agent's per-turn `background_review`: dumb capture by the channel; all judgment + Rule-9 routing happen in **skill-author Stage 0**.

**Two channels feed it (same schema, same queue):**
- `setup/hook-detect-correction.ps1` — UserPromptSubmit hook on the interactive terminal (`source` absent/`terminal`).
- `setup/scripts/discord-responder.py` `_capture_correction()` — J's Discord messages, captured even during RTH ($0, pure Python), `source:"discord"`.

Entry schema (one JSON object per line):
```json
{"ts":"2026-06-21T18:04:11-06:00","source":"discord","hash":"…","matched_phrase":"stop doing","prompt":"<verbatim, ≤1200 chars>","skills_named":["chart-data-verify"],"denylist_hit":false,"processed":false}
```

skill-author drains it **first** each fire (Stage 0): attributes a target skill, then either patches that skill's `SKILL.md` (safe) or files a `_lesson-inbox/` ratification note (Rule-9 denylist — heartbeat/params/pin-chain-verify). Handled entries get `processed:true` + an `outcome`; the hook caps the file at 500 lines. NEVER hand-delete it.

## Consumer
`skill-author` agent (`.claude/agents/skill-author.md`) — picked up via wake-protocol Stage 1 priority #4 (oldest-first).

## Output
- `.claude/skills/{slug}/SKILL.md`
- `backtest/autoresearch/{slug}.py`
- `markdown/infra/SKILLS-CATALOG.md` row added under right category + tool-selection-guide row
- Inbox item DELETED on success, or renamed `*.STALE.md` after 7 days by Manager.
