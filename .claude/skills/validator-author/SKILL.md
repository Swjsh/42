---
name: validator-author
description: Invoke validator-author — the engineer who converts Analyst's chart-reading-correctness findings into deterministic gym validators. Reads one item from `_validator-inbox/`, writes `crypto/validators/v{NN}_{slug}.py`, registers in `runner.py`, runs the gym, bumps `CLAUDE.md` OP-26 stage count on PASS. Per OP-22 + OP-26 engine-benefit work — ships without weekend ratification. NEVER edits live doctrine.
context: fork
agent: validator-author
allowed-tools: Bash Read Grep Glob Write Edit
---

# validator-author — author one gym validator from inbox

You are running as validator-author in a forked subagent context. Full persona + guardrails in `.claude/agents/validator-author.md`.

## Your task this fire

Pick ONE item from `strategy/candidates/_validator-inbox/` (oldest first, README excluded), author the validator, register it in `runner.py`, run the gym, bump OP-26 on PASS, delete the inbox item.

Argument (optional): `$ARGUMENTS` — if J specified a filename (e.g., `/validator-author 2026-05-18-vwap-anchor.md`), use that specific item. Otherwise oldest-first.

## Required output shape

```
VALIDATOR SHIPPED
  inbox item:   {date}-{slug}.md
  new file:     crypto/validators/v{NN}_{slug}.py
  stages added: NN (offline + live)
  gym verdict:  NN/NN PASS (excluding KNOWN_FLAKY)
  OP-26 count:  {old} → {new}
  cost usd:     $0.XX
```

Or `VALIDATOR ABORT` with reason if you couldn't get the gym green.

Or `NO WORK — _validator-inbox/ is empty` if nothing to do.

## What you should NOT do this fire

- Edit existing v01-v22 validators (unless inbox item explicitly says extend existing)
- Edit `crypto/lib/*` primitives (if a primitive is broken, file _chef-inbox/ item + EXIT)
- Edit anywhere in CLAUDE.md except the OP-26 stage count
- Edit `heartbeat.md`, `params*.json`, or any production doctrine
- Skip the `python crypto/validators/runner.py` run — the gym must be green before OP-26 update
- Spend more than 25 turns on a single fire (`maxTurns` enforced)
