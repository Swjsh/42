# Lesson inbox

Analyst routes here when an EOD finding is a **one-off foot-gun worth encoding** into `markdown/doctrine/LESSONS-LEARNED.md` + CLAUDE.md OP-25 absorbed-lessons list — per the self-correction mandate.

## Item format

```markdown
# Lesson candidate: {short name}

> Queued by Analyst {date}. lesson-author picks up at next wake fire.

## Symptom
{what was observed, including dates and metrics}

## Root cause
{the underlying mechanism — cite file paths and line numbers}

## Fix
{what was changed; cite commit / file paths}

## Encoded in
{which file / OP / skill / validator now enforces this lesson permanently}

## L## (optional)
Suggested L number; lesson-author greps for max and assigns next.
```

## Consumer
`lesson-author` agent (`.claude/agents/lesson-author.md`) — picked up via wake-protocol Stage 1 priority #5 (oldest-first).

## Output
- `markdown/doctrine/LESSONS-LEARNED.md` L## entry appended
- `CLAUDE.md` OP-25 absorbed-lessons bullet appended (the only doctrine write this author makes, justified by OP-25 self-correction mandate)
- `journal/mistakes.md` cross-reference appended if matching date entry exists
- Inbox item DELETED on success, or renamed `*.STALE.md` after 7 days by Manager.
