# Validator inbox

Analyst routes here when an EOD finding proposes a **deterministic chart-reading correctness check** — a primitive that needs a regression test in `crypto/validators/`.

## Item format

```markdown
# Validator request: {short name}

> Queued by Analyst {date}. validator-author picks up at next wake fire.

## Observation
{what surfaced}

## Primitive to test
{which crypto/lib/ function or heartbeat.md filter}

## Expected behavior
{what offline assertions should hold}

## Live-source check (if applicable)
{which data sources to compare; note if KNOWN_FLAKY}

## Foot-gun this prevents
{cite L## from LESSONS-LEARNED.md if regression is reopening a closed lesson}
```

## Consumer
`validator-author` agent (`.claude/agents/validator-author.md`) — picked up via wake-protocol Stage 1 priority #3 (oldest-first).

## Output
- `crypto/validators/v{NN}_{slug}.py`
- `runner.py` stages list incremented
- `CLAUDE.md` OP-26 stage count bumped on PASS
- Inbox item DELETED on success, or renamed `*.STALE.md` after 7 days by Manager.
