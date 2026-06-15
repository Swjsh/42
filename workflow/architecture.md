# Architecture — Project Gamma

> How the rig actually works. Updated as we add capability.

---

## Hard constraints (do not try to engineer around)

1. **Gamma executes paper trades autonomously. Real-money trades require J confirmation.** Paper account (Alpaca paper API) = Gamma places orders directly when trigger fires. Real money = Gamma prepares the order, J clicks submit. This was confirmed by J on 2026-05-05.
2. **Gamma is not a continuous daemon.** Gamma responds to triggers — user prompts, scheduled tasks, or webhooks. There is no "watch the chart for 6.5 hours straight" — there are only discrete invocations. The fix is the scheduled heartbeat (Task Scheduler / loop), not a persistent process.

These constraints define the design.

---

## Components

### TradingView MCP
- **Read access** to charts, levels, indicators, ribbon state, alerts.
- Used for: pre-market level read, in-trade chart scans, ribbon-flip checks, post-trade context.
- Configured in `~/.claude/.mcp.json`. Requires TradingView desktop running with `--remote-debugging-port=9222`.

### Alpaca MCP (paper)
- **Read access** to account equity, positions, P&L, option chains, Greeks, fills, day-trade count.
- **Write access (ACTIVE for paper account):** Gamma places paper option orders directly when playbook trigger fires. No J involvement required on paper. Real-money orders still require J to submit manually.
- Configured in `~/.claude/.mcp.json` with paper API keys.

### Claude Code (host)
- Runs Gamma as the persona defined in `CLAUDE.md`.
- Loads MCPs at session start.
- Reads/writes the workspace folder for journal, playbook, rules.

### Workspace folder (`C:\Users\jackw\Desktop\42`)
- Source of truth: `CLAUDE.md`, `strategy/`, `journal/`, `analysis/`, `workflow/`, `setup/`.
- Both Claude Code and Cowork (this session) can read/write here. Single source of truth across environments.

---

## Phased architecture

### Phase 1 — Manual session (this is what we ship tomorrow)

```
[J] ──► Claude Code ──► [Gamma] ──► TV MCP / Alpaca MCP ──► [chart + account state]
                            │
                            ▼
                   [analysis + order prep]
                            │
                            ▼
                          [J]  ──►  Alpaca UI  ──► [order submitted]
                            │
                            ▼
                   [Gamma logs the fill, manages via TV MCP]
```

- Pre-market: J asks for pre-market routine, Gamma reports bias + levels.
- During day: J pings when something looks like a setup, Gamma scans and confirms/denies.
- Order prep: Gamma writes exact strike/qty/limit/stop/target.
- Order submission: J clicks in Alpaca paper UI.
- Post-trade: Gamma logs fill, manages via ribbon checks when J pings.
- EOD: Gamma runs end-of-day routine, journal updated.

**This is sufficient for the first 5–10 paper trades.** Get reps in before adding automation.

### Phase 2 — Scheduled heartbeat

```
[OS cron / Task Scheduler] ──every 5-15 min during market hours──► claude --prompt "scan check"
                                                                          │
                                                                          ▼
                                                                  [Gamma scans TV MCP]
                                                                          │
                                              ┌───────────────────────────┼───────────────────────────┐
                                              ▼                           ▼                           ▼
                                  [no setup → log to file]    [setup forming → ping J]    [in-trade → ribbon check, ping J if exit signal]
```

- Cron / Task Scheduler runs `claude --prompt "Gamma, scan-check"` on a schedule.
- Each invocation: Gamma pulls TV state, checks ribbon + key levels, account state.
- Output routes:
  - No relevant change → append to a log file (no notification).
  - Setup forming or in-trade signal change → ping J via push channel (Slack webhook, SMS, ntfy, Discord, etc — J chooses).

**Build this once Phase 1 is humming and the routine is internalized.**

### Phase 3 — TradingView webhook-driven

```
[TradingView alert: ribbon flip / level test] ──webhook──► [local webhook endpoint] ──spawns──► claude session
                                                                                                      │
                                                                                                      ▼
                                                                                          [Gamma evaluates against playbook]
                                                                                                      │
                                                                                          ┌───────────┴───────────┐
                                                                                          ▼                       ▼
                                                                              [false positive → log]    [real trigger → ping J]
```

- TradingView alerts set on the indicators that matter to the setup (ribbon transitions, level breaks).
- Webhook target: a tiny local server (Flask / Express) on J's machine.
- Server spawns a Claude Code session with the alert payload.
- Gamma evaluates: does this match a playbook trigger? Does context confirm? Then notify J.

**This is the endgame UX.** Latency from alert → notification ≈ seconds. J can be at work and still catch the setup.

---

## What Gamma does NOT do (architectural commitments)

- Submit orders on Alpaca. Paper or live. Ever.
- Run autonomous decision loops without a triggering event.
- Modify rules mid-session.
- Recommend specific trades as investment advice (analysis only).
- Hide signals from J — every trigger Gamma sees gets surfaced.

---

## Data flow / journaling

Every Gamma invocation that produces analysis or a decision writes to the journal:

- Pre-market scan → appends to `journal/YYYY-MM-DD.md` under "Pre-market"
- Trade thesis → appends under "Trades"
- Mid-trade scan / management decision → appends to current trade entry
- Post-trade exit → appends fill, P&L, lesson; updates `journal/trades.csv`
- Rule break flagged → appends to `journal/mistakes.md`
- EOD summary → appends end-of-day reflection

The journal is the system of record. The MCPs are the eyes; the journal is the brain's notebook.

---

## Failure modes (what we'll watch for)

- **MCP connection drops mid-trade.** Gamma flags loudly; J reverts to manual chart read. Don't trade blind.
- **TV chart paused / desktop crashed.** Same as above; verify before any trade decision.
- **Stale data.** Gamma always timestamps the data it reads; J should not act on data > 90 seconds old.
- **Gamma misreads the ribbon / level.** Cross-checks: Gamma states the ribbon color and key levels in chat; J confirms visually before acting.
- **The cron heartbeat runs while J is asleep / market closed.** Heartbeat schedule must respect market hours (9:30–16:00 ET, weekdays, no half-days unattended).
