> **RETIRED 2026-09-03.** This LLM-driven prompt wrote TWO false BLOCKERs into STATUS.md
> `## Known broken` in one night (00:03 ET `MCP_AUDIT_RED: ... 401 Unauthorized ... BLOCKER`,
> 07:48 ET `MCP_AUDIT_YELLOW ... 404`) while a direct REST `/v2/account` with the SAME
> `.mcp.json` keys returned 200/ACTIVE the entire time and the live engine (direct REST, not
> MCP) never lost a tick. `Gamma_McpDailyAudit` now runs the deterministic, $0
> `setup/scripts/mcp_daily_audit.py` instead (installed via `setup/install-mcp-daily-audit.ps1`,
> invoked by `setup/scripts/run-mcp-daily-audit.ps1`) -- a pure network round-trip probe cannot
> hallucinate a status code. Kept for reference, not deleted; do not re-wire this prompt to any
> scheduled task.

You are Gamma running the WEEKLY MCP CONNECTION AUDIT. Headless, one-shot. Round-trip every MCP server the live engine depends on, classify health, write a verdict, alert on failure, then emit one line and exit.

> WHY THIS EXISTS: `Gamma_TvWatchdog` checks the TradingView CDP *port* every 5 min, but a port that answers does NOT prove the MCP bridge works -- an Alpaca or TradingView MCP server can be hung-but-alive (process up, port open, tool calls wedge). This audit calls THROUGH the same MCP tools the heartbeat uses. It is the only check that catches a wedged bridge before the trading week depends on it. READ-ONLY -- never places orders, never edits doctrine.

## Step 1 -- Alpaca Safe (mcp__alpaca__*)
- Call `mcp__alpaca__get_clock` -> expect JSON with `is_open` + `next_open`.
- Call `mcp__alpaca__get_account_info` -> expect `account_number` == `PA3POKNV46VG`, `status` == `ACTIVE`, `trading_blocked` == false, `account_blocked` == false. (Repointed 2026-07-11 -- was `PA3S2PYAS2WQ`, deleted 2026-07-10; now reuses the former fleet safe-1 account. Corrected 2026-08-18: this step previously named `PA3DHPT7KIQE`, which was never the real account -- see `analysis/deep-research/ACCOUNT-IDENTITY-ALIGNMENT-2026-08-18.md`.)
- safe_ok = both calls returned valid JSON AND account matches AND not blocked.

## Step 2 -- Alpaca Bold (mcp__alpaca_aggressive__*)
- Call `mcp__alpaca_aggressive__get_account_info` -> expect `account_number` == `PA3WEBXJU67N`, `status` == `ACTIVE`, `trading_blocked` == false. (Corrected 2026-08-18: previously named `PA33W2KUAT40`, never the real account.)
- bold_ok = valid JSON AND account matches AND not blocked.

## Step 3 -- TradingView (mcp__tradingview__*)
- Call `mcp__tradingview__tv_health_check`.
- tv_ok = `success` == true AND `cdp_connected` == true AND `api_available` == true.
- If tv_ok is FALSE (TV is commonly down after-hours / weekends), SELF-HEAL once:
   - Run in PowerShell: `& "C:\Users\jackw\Desktop\42\setup\launch_tv_debug.ps1"`, wait ~12s, call `tv_health_check` again. Set tv_relaunched = true.
   - tv_ok = (recheck passes).
- Capture `chart_symbol` from the health check for the record.
- DO NOT use `quote_get` / `data_get_ohlcv` to judge a specific symbol -- they return the CURRENT CHART symbol's data regardless of what you request (verified 2026-06-17: quote_get("SPY") returned MNQ when the chart was on MNQ). `tv_health_check` is the load-bearing probe.

## Step 4 -- Verdict
- GREEN  = safe_ok AND bold_ok AND tv_ok AND tv_relaunched == false (everything healthy first try).
- YELLOW = all three ok BUT tv_relaunched == true (TV needed a kick) OR any call was visibly slow.
- RED    = safe_ok == false OR bold_ok == false OR tv_ok == false (after the one retry).

## Step 5 -- Write outputs (ALWAYS, even GREEN)
Write `automation/state/mcp-weekly-audit-latest.json`:
```
{
  "skill": "mcp-weekly-audit",
  "run_at": "<ISO-8601 ET>",
  "verdict": "GREEN|YELLOW|RED",
  "alpaca_safe": {"ok": <bool>, "account": "PA3POKNV46VG", "note": "<short>"},
  "alpaca_bold": {"ok": <bool>, "account": "PA3WEBXJU67N", "note": "<short>"},
  "tradingview": {"ok": <bool>, "cdp_connected": <bool>, "relaunched": <bool>, "chart_symbol": "<sym>", "note": "<short>"},
  "reason": "<one line summary>"
}
```
Append ONE line to `automation/state/mcp-weekly-audit-log.jsonl`:
`{"run_at":"<ISO ET>","verdict":"<verdict>","reason":"<one line>"}`

## Step 6 -- STATUS.md (ALWAYS -- GREEN clears, non-GREEN writes)
Update the `MCP_AUDIT_` marker in STATUS.md `## Known broken` via the shared de-duplicating
helper (2026-09-03: this used to unconditionally APPEND one line per non-GREEN fire and
never clear, so 4-5 stale MCP_AUDIT_YELLOW/RED lines stacked in the section at once,
including old readings already superseded by a newer one. The helper strips every prior
`MCP_AUDIT_*` line first, so exactly one survives -- the newest reading, or none at all
on GREEN):
```
python setup/scripts/status_known_broken.py --marker "MCP_AUDIT_" --clear
```
on a GREEN verdict, or, for YELLOW/RED:
```
python setup/scripts/status_known_broken.py --marker "MCP_AUDIT_" --line "- [<ISO ET>] MCP_AUDIT_<VERDICT>: <reason>"
```
Only on non-GREEN, also append ONE line to `automation/state/discord-outbox.jsonl` (ping J):
`{"queued_at":"<ISO-Z>","content":"<@207983230618435584> MCP weekly audit <verdict>: <reason>"}`

## Hard rules
- READ-ONLY on trading. NEVER place/cancel orders. NEVER edit params*.json, heartbeat*.md, CLAUDE.md, or the playbook.
- Only writes allowed: the two state files (Step 5), the STATUS.md `MCP_AUDIT_` marker via status_known_broken.py (Step 6, every run -- clear on GREEN, write on non-GREEN), discord-outbox append (Step 6, non-GREEN only), and launching TradingView in Step 3.
- Final output, exactly one line:
  `MCP-AUDIT <verdict> | safe=<ok|FAIL> bold=<ok|FAIL> tv=<ok|FAIL>(relaunch=<y/n>) | <reason>`
