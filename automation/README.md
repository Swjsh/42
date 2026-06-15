# Automation — Project Gamma

> Gamma runs the strategy autonomously on the Alpaca paper account during market hours. J does not need to be at the screen.

---

## What this folder is

The orchestration layer that turns Gamma from "AI you talk to" into "AI that scans the chart, makes decisions, places paper trades, and writes the journal — on a schedule."

## Architecture (one paragraph)

A cron-driven loop (the **heartbeat**) invokes Claude Code at fixed intervals during market hours. Each invocation reads persistent state from `automation/state/`, pulls live chart data via the TradingView MCP, pulls account data via the Alpaca paper MCP, runs the playbook decision tree, takes one action (or no action), updates state, writes to the journal, and exits. The user is not in the loop. Tier 2 adds TradingView alert webhooks to fire the agent immediately on key events instead of waiting for the next polling tick. Tier 3 (real money) adds per-trade chat confirmation.

## Files in this folder

| File | Purpose |
|---|---|
| `heartbeat.md` | The agent loop spec — what runs every 3 min during market hours |
| `premarket.md` | 08:30 ET routine — pull levels, set bias, write daily plan |
| `eod.md` | 15:55 ET routine — flatten 0DTE positions, write daily summary |
| `cron.md` | Exact crontab entries for the trading rig |
| `decision-log.md` | The decision tree in plain English — auditable, reviewable, modifiable |
| `state/README.md` | Schema and lifecycle for the persistent state files |
| `state/*.json` | Live state — current position, today's bias, kill switch |

## Tier status

- **Tier 1 (polling-based autonomy):** **building now.** Ships before Monday market open.
- **Tier 2 (webhook acceleration):** target within 2 weeks of Tier 1 going live.
- **Tier 3 (live deployment, hybrid confirmation):** gated on 20 paper trades clearing thresholds.

## Hard constraints

- Paper account only until thresholds clear. No real money.
- Daily kill switch is enforced by the heartbeat — when triggered, `state/kill-switch` is created and no further trades enter.
- Manual override: J can drop a `state/kill-switch` file at any time to pause the system. Heartbeat checks for it on every invocation.
- All actions logged to `journal/YYYY-MM-DD.md` and `journal/trades.csv`.
