# Context Leanness -- Auto-Fix Fire

The context-budget guard reported the always-loaded prefix is OVER budget
(see `automation/state/context-budget.json` -> `status: RED`). Every token in
CLAUDE.md is cache-written then cache-read on EVERY Claude Code turn, so this is
real recurring cost across thousands of fires.

Your task: invoke the **context-leanness** skill and run its full procedure to
bring CLAUDE.md back to GREEN (<= 8000 tokens) WITHOUT changing any rule semantics.

Non-negotiable (the skill spells these out in full):
- Do NOT alter rules 1-10, account numbers/params, kill-switch values, the
  "Current rule version" pin, or the refusals. Their MEANING must be preserved.
- Back up CLAUDE.md to `docs/archive/CLAUDE-md-pre-trim-{date}.md` FIRST.
- Relocate only reference-only blocks to `docs/` and leave a pointer; dedupe wording.
- Run `python setup/scripts/context_audit.py verify` -- if ANY check fails,
  RESTORE from the backup and abort, flagging it in STATUS.md `## Known broken`.
- On success: log to CHANGELOG.md and re-run the guard to clear the alert.

Skill file: `.claude/skills/context-leanness/SKILL.md`
