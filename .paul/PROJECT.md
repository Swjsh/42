# PROJECT.md — MCP Connection Hardening

## Problem
The Gamma trading engine can go blind or silent when TradingView MCP or Alpaca MCP hiccup.
The 2026-06-24 morning proved it: TV hung for ~280s → heartbeat fired but was entirely blind →
missed a clean PMH-rejection scalp that was live the whole time on Alpaca bars.

## Value
An engine that never loses sight of price or account state = no missed setups + no unprotected
positions + no ghost orders. Every missed setup is real P&L left on the table.

## Scope
Three sub-problems, one phase:

1. **TV sight (P0)** — When `data_get_ohlcv` returns an error OR TV is stale: fall back to Alpaca
   `get_stock_bars` + `ribbon_fallback.compute_ribbon()`. Compute core already exists (11/11 tests).
   Needs: ribbon CLI wrapper + heartbeat.md fallback branch + watchdog hung-bridge detection.

2. **Alpaca resilience (P1)** — Single `place_option_order` / `get_account_info` failure currently
   drops silently; GhostOrderReconciler catches it after the fact. Needs: retry instructions in
   both heartbeat prompts (3-retry exp-backoff for 429/503/network errors).

3. **Operational hardening (P2)** — Gamma_McpWeeklyAudit runs Sunday only (5-day RTH blind gap).
   Gamma_Heartbeat + Gamma_Heartbeat_Aggressive fire at identical :00 offsets (correlated rate-limit
   risk). Needs: promote audit to daily 18:30 ET + stagger Bold start to 09:31 ET.

## Constraints
- NO changes to `automation/state/params.json` or any params*.json files
- NO changes to production doctrine (rule version, entry gates, risk caps)
- Market-hours discipline: do NOT restart scheduled tasks during 09:30–15:55 ET
- All new Python scripts use `backtest/.venv` interpreter for anything importing pandas/engine
- New standalone scripts that only use stdlib + Alpaca REST can use system pythonw
- PowerShell 5.1 syntax only (no PS7+ features, no em-dashes)
- All new scheduled tasks must follow the wscript→pythonw chain (no bare powershell.exe)
- Rule 9: no mid-session doctrine changes; these wiring changes are infrastructure, not doctrine
