---
name: preflight-gate
description: Standing readiness gate before ANY trading work. Chains the three existing audits (heartbeat-mcp-self-test + chart-data-verify + heartbeat-pulse-check) into ONE GREEN/YELLOW/RED verdict, so you never start a tick on a stale-401 key, wrong-timeframe chart, or dead heartbeat. Invoke at the top of /heartbeat, before any manual pilot fire, and at premarket Step 1.
---

# Skill: preflight-gate

One command that answers a single question: **is the system actually ready to trade right now?**

The `/insights` report (2026-06-18) flagged that the pre-flight pieces already existed as three *separate* skills but were never unified, so ticks kept starting on stale keys / wrong-timeframe charts / a silently-stopped heartbeat. This gate chains them and folds the results into one verdict.

> Per CLAUDE.md OP-25 ("silent failure is the only true failure"). A failed pre-flight is now LOUD, not a dead tick.

---

## When to invoke

- **First step of every `/heartbeat` fire** (the heartbeat skill calls this before reading any state).
- **Before any manual `/pilot` fire** that might place an order.
- **Premarket Step 1**, before drawing levels or seeding the journal.
- **On demand** when J asks "are we ready to trade?" / "is everything wired?".

---

## Steps

1. **Run the gate (defaults to today):**

```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\preflight-gate.ps1"
```

2. **Heal mode** (passes `-Heal` down to the sub-audits: restarts TV if dead, re-enables a disabled heartbeat task; never touches keys or doctrine):

```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\preflight-gate.ps1" -Heal
```

3. **Read the unified verdict:**

```powershell
Get-Content "C:\Users\jackw\Desktop\42\automation\state\preflight-gate-latest.json"
```

---

## Verdict criteria (worst-of the three sub-checks)

| Verdict | Meaning | Action |
|---------|---------|--------|
| **GREEN** | All 3 sub-audits GREEN | Cleared. Proceed with trading work. |
| **YELLOW** | One sub-audit YELLOW, none RED | Degraded but workable. Proceed with caution; note which check is degraded. |
| **RED** | Any sub-audit RED, OR any sub-audit wrote no JSON | **BLOCKED.** Do NOT start trading work. Fix the named check first (or run `-Heal`). |

The three sub-checks:

| Check | Catches | Source script |
|-------|---------|---------------|
| `mcp-self-test` | TV CDP down, alpaca-mcp dead, **stale-401 key not loaded** | `setup/scripts/heartbeat-mcp-self-test.ps1` |
| `chart-data-verify` | stale bars, **wrong timeframe**, source divergence | `backtest/autoresearch/chart_data_verify.py` |
| `heartbeat-pulse` | scheduled task silently stopped firing | `setup/scripts/heartbeat-pulse-check.ps1` |

---

## Exit codes

- `0` for GREEN / YELLOW (caller may proceed).
- `1` for RED (caller MUST halt). The `/heartbeat` skill checks `$LASTEXITCODE` and refuses to tick on a `1`.

---

## What this skill NEVER does

- Modify keys, `params.json`, `heartbeat.md`, or any doctrine (Rule 9).
- Place orders.
- Auto-heal anything beyond what the underlying audits already do with `-Heal` (TV restart, re-enable disabled task). Key fixes always require J.

---

## Cross-references

- **Tool source:** `setup/scripts/preflight-gate.ps1`
- **Sub-audits:** `heartbeat-mcp-self-test`, `chart-data-verify`, `heartbeat-pulse-check`
- **Consumed by:** `heartbeat` skill (Step 0), `pilot` manual fires, premarket Step 1.
- **Companion aggregate:** `gym-session` (the heavier 7-audit physical exam; this gate is the fast 3-audit trading-readiness subset).
