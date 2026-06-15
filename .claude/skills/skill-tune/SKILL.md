---
name: skill-tune
description: Fine-tuning loop for chart-reading and audit skills. Replays a target skill across N historical weekdays with monkey-patched parameter values, measures detection rate at each value, recommends the best threshold. Writes DRAFT update to `_skill-inbox/` (or `_lesson-inbox/` if skill is in LIVE_DOCTRINE_DENYLIST per Rule 9). Pure Python, $0 cost. Use when J asks "is X's threshold mis-calibrated" or Analyst suspects a skill is flagging too many false positives.
context: session
allowed-tools: Bash Read
---

# skill-tune — sweep a skill parameter to find the best threshold

## When to invoke

- When a chart-reading or audit skill produces too many false-positive RED verdicts.
- When Analyst suggests a threshold needs review (queues `_skill-inbox/` item with `kind: tune`).
- Before ratifying a candidate strategy whose primitives depend on tuned thresholds.

## How to invoke

- **Direct:** `python -m autoresearch.skill_tune --skill {slug} --param {name} --range start,stop,step --window N`
- Example: `python -m autoresearch.skill_tune --skill chart-data-verify --param tolerance --range 0.05,0.30,0.05 --window 30`

## What it does

1. Parses `--range` into a list of values (e.g., `0.05,0.10,0.15,0.20,0.25,0.30`).
2. Pulls the last N weekdays (Mon-Fri only).
3. For each (value, date) pair, calls the target skill's `evaluate_at(date, **overrides)` adapter and classifies the verdict.
4. Computes a sweep table: param_value × {days_green, days_yellow, days_red, days_missing, false_positive_rate}.
5. Recommends the value with lowest RED rate (ties broken by highest GREEN count).
6. Writes `analysis/skill-tune/{skill}-{ts}.md` (narrative table + recommendation).
7. Writes `automation/state/skill-tune-{skill}-latest.json` (machine-readable).
8. If `recommended != current` AND skill is NOT in `LIVE_DOCTRINE_DENYLIST` → writes DRAFT `_skill-inbox/{date}-tune-{skill}.md` with `kind: tune` so the next wake fire's skill-author applies it.
9. If skill IS in `LIVE_DOCTRINE_DENYLIST` → writes DRAFT to `_lesson-inbox/` instead, requiring J ratification per Rule 9.

## Output

- `analysis/skill-tune/{skill}-{ts}.md`
- `automation/state/skill-tune-{skill}-latest.json`
- `strategy/candidates/_skill-inbox/{date}-tune-{skill}.md` (if safe to auto-apply)
- `strategy/candidates/_lesson-inbox/{date}-tune-{skill}.md` (if denylisted)

## Live-doctrine denylist (Rule 9 protected)

These skills' parameters can NOT be auto-tuned — sweep results route to `_lesson-inbox/` for explicit J ratification:

- `heartbeat-pulse-check` — touches heartbeat task scheduling
- `heartbeat-decision-trace` — tied to live `params.json` filter thresholds
- `pin-chain-verify` — rule 9 by definition (rule_version drift)

## Skill adapter contract (target skill must expose this)

For a skill to be tunable, its `backtest/autoresearch/{skill}.py` module must expose:

```python
def evaluate_at(date: str, **overrides) -> dict:
    """Return at minimum {"verdict": "GREEN"|"YELLOW"|"RED"|"NOT_APPLICABLE"|"MISSING"}.

    overrides: keyword args matching the param name being swept.
    """
    ...
```

Without this adapter, the sweep returns `MISSING` for every (date, value) pair and the recommendation is empty. Adding `evaluate_at` to a skill is per-skill work that promotes the skill to tunable status.

## Cost

$0 — pure Python sweep. No LLM call.

## Invocation steps (when J runs `/skill-tune`)

1. Run `python -m autoresearch.skill_tune --skill {slug} --param {name} --range {start,stop,step}` from `backtest/` cwd.
2. Read the printed report.
3. Report back:
   ```
   SKILL TUNE {skill}
     param:             {name}
     range:             {start,stop,step}
     window:            {N} weekdays
     current value:     {x}
     recommended value: {y}
     denylist blocked:  {true/false}
     inbox draft:       {_skill-inbox or _lesson-inbox path}
     report:            analysis/skill-tune/{file}.md
   ```
