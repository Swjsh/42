# Chef inbox

Analyst routes here when an EOD finding proposes a **new strategy variant, parameter tweak, or setup mode** worth backtesting. Also used by Gamma overnight session for findings that need R&D investigation before production ratification.

## Item format

```markdown
# Chef Inbox — {short name}

**Routed by:** {persona} {date}
**Priority:** HIGH / MED / LOW
**Category:** Strategy variant / Parameter sweep / New setup / ...
**Source:** {data point, observation, or J source-of-truth day}

## The Finding
{what was observed — include specific SPY prices, times, scores, blocker reasons}

## Research Question for Chef
{the testable hypothesis}

## Backtest Request
{specific evaluation criteria — what to measure, which days to check, pass/fail gates}

## Files for Reference
{relevant source files}

## Priority / Dependencies
{what must happen first; note if OP-21 Watch-Only applies}
```

## Consumer
`chef` agent (`.claude/agents/chef.md`) — picked up via wake-protocol Stage 1 priority #6 (after validator/skill/lesson inboxes). Chef writes DRAFT proposals to `strategy/candidates/{date}-{slug}.md` and updates `strategy/candidates/_LEADERBOARD.md`. Inbox item DELETED on success, or renamed `*.STALE.md` after 7 days by Manager.

## Output
- `strategy/candidates/{date}-{HHMMSS}-{slug}.md` (DRAFT, OP-20 disclosures included)
- `strategy/candidates/_LEADERBOARD.md` updated with candidate ranking
- **NO production doctrine changes** — proposals require J weekend ratification (Rule 9)
