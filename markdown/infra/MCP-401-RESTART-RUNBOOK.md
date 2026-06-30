# Runbook: broker key 401 / stale-key recovery

> Triggered when `self_check.py` (Gamma_SelfCheck, every 30 min) flags **`BROKER KEY STALE/REVOKED: <arm> account-ping HTTP 401`** → STATUS.md `## Known broken` + a Discord ping. A 401 on a live engine key = **no trades can place** until fixed. This is the documented restart path (insight "On the Horizon" — the 401 detector already exists in self_check; this is its runbook).

## What a 401 means
The Alpaca key in `.mcp.json` (engine arms) or `automation/state/fleet/secrets.json` (fleet arms) is **rotated, revoked, or expired**. The engine + MCP server still hold the OLD key in memory, so every account/order call returns HTTP 401. Exit codes lie (a task can exit 0 while every API call 401s) — that's why `self_check` pings the live `/v2/account` instead of trusting the task.

## Recovery steps (after-hours; never rotate a secret without J — OP-0 #2)
1. **Confirm which arm + which key.** Run `backtest/.venv/Scripts/python.exe setup/scripts/accounts_status.py` — it pings every arm live and prints `HTTP 401` next to the broken one. `safe-2` = mcp `alpaca` (`.mcp.json` key `PK7WRO5T…`); `bold-2` = mcp `alpaca_aggressive` (`PKQMQD2N…`).
2. **Get the current key from J** (he rotates in the Alpaca dashboard). NEVER hand-transcribe a long key — have J paste it or read it from a file (CLAUDE.md secrets rule).
3. **Update the canonical secret location** (gitignored — never a tracked file): `.mcp.json` for the engine arms, `automation/state/fleet/secrets.json` for fleet arms.
4. **RELOAD the dependent MCP server before verifying** (the #1 miss — a stale key 401s until the server reloads): the MCP servers are launched per-task via the pythonw/uvx chain; restart the consuming task (or the interactive session that holds the MCP connection) so it re-reads `.mcp.json`. CLAUDE.md rule: *"reload a rotated key's MCP server before verifying."*
5. **Re-verify (don't claim):** re-run `accounts_status.py` (expect `ACTIVE`, no 401) AND `self_check.py` (expect GREEN). Only then is it fixed.

## Why exit codes can't be trusted here
A rotated key produces HTTP 401 on every call but the wrapper task still exits 0 (the 06-29 premarket silent-failure was the same class). `self_check`'s live `/v2/account` ping is the source of truth, not `lastResult=0`. Same OP-33 discipline: verify the work, not the exit code.

## Related
- Detector: `setup/scripts/self_check.py` → `check_broker_keys()`
- Live view: `setup/scripts/accounts_status.py`, `gamma_status.py`
- Secrets discipline: CLAUDE.md GitHub/Secrets section.
