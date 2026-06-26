# STATE.md — MCP Connection Hardening

## Current Position

Milestone: v1.0 Engine Never Goes Blind
Phase: 1 of 1 (MCP Hardening) — COMPLETE
Status: APPLY complete, UNIFY complete (summary files written)
Last activity: 2026-06-24 — All three plans applied and summarized

Progress:
- Milestone: [██████████] 100% (code complete; 2 manual steps pending for J)
- Phase 01: [██████████] 100%

## Loop Position

```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓
```

## Pending manual steps (J applies after 16:00 ET today)

1. `.\setup\install-mcp-daily-audit.ps1` — registers Gamma_McpDailyAudit, unregisters Gamma_McpWeeklyAudit
2. Bold stagger — run PowerShell command in STAGGER PENDING block of `automation/state/SCHEDULED-TASKS.md`

After J runs both: `python setup/scripts/audit_scheduled_tasks.py` to confirm no ORPHAN_TASK.

## Session Continuity

Last session: 2026-06-24
Stopped at: UNIFY complete — all summary files written
Next action: None (phase complete). J runs 2 manual steps above after 16:00 ET.

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D-01 | TV fallback uses Alpaca `get_stock_bars` MCP (not REST) | Already available in heartbeat context; no new credentials needed |
| D-02 | Ribbon CLI wrapper lives in `automation/scripts/ribbon_cli.py` | Close to heartbeat prompt; uses system Python (stdlib only after import) |
| D-03 | Watchdog restart on stale+CDP-alive after 6 min grace | CDP alive + frozen heartbeat = hung MCP bridge; 6 min > 1 watchdog cycle avoids false triggers |
| D-04 | 01-02 (Alpaca retry) runs after 01-01 | Both touch heartbeat.md; serial edit prevents merge conflicts |
| D-05 | McpWeeklyAudit task renamed McpDailyAudit | Breaking change to task name avoids old Sunday-only task silently co-existing |
| D-06 | Bold stagger = 09:31 ET start (+1 min vs Safe 09:30) | Minimum viable stagger to break correlated API calls |
