# Skill: mcp-weekly-audit

Weekly round-trip health check of the MCP servers the live engine depends on: Alpaca (Safe + Bold accounts) and TradingView. Calls THROUGH the MCP tools (not just the CDP port) to catch a hung-but-alive bridge, classifies GREEN/YELLOW/RED, logs a verdict, and alerts on failure.

> Fills the gap left by `Gamma_TvWatchdog` (only checks that CDP port 9222 is listening) and `heartbeat-mcp-self-test` (only checks process existence). Neither calls a tool, so neither catches an MCP server that is up-but-wedged. This does.

---

## When to invoke
- **Auto:** Sunday 18:30 ET via `Gamma_McpWeeklyAudit` (after `Gamma_WeeklyReview`), so connection health is confirmed before the trading week.
- **Manual:** any time you suspect MCP flakiness, after restarting an MCP server, or before a high-stakes session.

## Run it
```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\run-mcp-weekly-audit.ps1"
```
Or, interactively, round-trip the tools yourself per `automation/prompts/mcp-weekly-audit.md`.

## What it round-trips
| Subsystem | Tools | PASS condition |
|---|---|---|
| Alpaca Safe | `get_clock`, `get_account_info` | account `PA3S2PYAS2WQ`, ACTIVE, not blocked |
| Alpaca Bold | `get_account_info` | account `PA33W2KUAT40`, ACTIVE, not blocked |
| TradingView | `tv_health_check` (+ self-heal `launch_tv_debug.ps1` if down) | success && cdp_connected && api_available |

## Verdict
- **GREEN** — all three pass first try.
- **YELLOW** — all pass but TV needed a relaunch, or a call was slow.
- **RED** — any subsystem fails after one retry → STATUS.md `## Known broken` + Discord ping.

## Gotcha (encoded 2026-06-17)
`quote_get` / `data_get_ohlcv` return the **current chart symbol's** data regardless of the symbol you request (`quote_get("SPY")` returned MNQ when the chart was on MNQ). Do NOT use them to validate SPY specifically. `tv_health_check` is the load-bearing TV probe.

## Output
| File | What |
|---|---|
| `automation/state/mcp-weekly-audit-latest.json` | latest full verdict |
| `automation/state/mcp-weekly-audit-log.jsonl` | one line per run (weekly history) |
| `automation/overnight/STATUS.md` `## Known broken` | appended only on non-GREEN |
| `automation/state/discord-outbox.jsonl` | J ping only on non-GREEN |

## Not covered (future extension)
The futures broker (Tastytrade) is a Python adapter (`backtest/futures/tastytrade_paper.py`), not an MCP server — not audited here. Add a Tastytrade connectivity check when futures goes live.

## Cross-references
- Prompt: `automation/prompts/mcp-weekly-audit.md`
- Runner: `setup/scripts/run-mcp-weekly-audit.ps1`
- Installer: `setup/install-mcp-weekly-audit.ps1`
- Companion: `heartbeat-mcp-self-test` (port/process check), `Gamma_TvWatchdog` (CDP relaunch every 5 min)
