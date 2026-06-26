# ROADMAP.md — MCP Connection Hardening

## Milestone: v1.0 — Engine Never Goes Blind

### Phase 01 — MCP Hardening
**Status:** In progress
**Goal:** Harden all MCP connections so a TV hang or Alpaca hiccup never causes a missed setup or silent failure.

Plans in this phase:

| Plan | Name | Wave | Status | Depends On |
|------|------|------|--------|------------|
| 01-01 | TV Fallback + Watchdog | 1 | Planning | — |
| 01-02 | Alpaca Retry Instructions | 2 | Not started | 01-01 |
| 01-03 | Operational Hardening | 1 | Not started | — |

**Wave 1 (parallel):** 01-01 and 01-03 can run concurrently (different file sets).
**Wave 2 (sequential):** 01-02 runs after 01-01 (both touch heartbeat.md; serial edit avoids conflicts).

#### Acceptance Gates for Phase Complete
- [ ] Heartbeat tick with TV error/stale → uses Alpaca bars ribbon, logs `TV_FALLBACK_ACTIVE`, does NOT emit `SKIP_TV_DATA_STALE` unless Alpaca bars also fail
- [ ] Watchdog force-relaunches TV when CDP alive but heartbeat stale > 6 min during RTH
- [ ] Both heartbeat prompts have explicit 3-retry instructions for `place_option_order` 429/503 errors
- [ ] `Gamma_McpDailyAudit` fires every day 18:30 ET (not Sunday-only)
- [ ] `Gamma_Heartbeat_Aggressive` starts at 09:31 ET (not 09:30), staggered from Safe
- [ ] All tests pass: `cd backtest && python -m pytest -x -q`
- [ ] SCHEDULED-TASKS.md reconciles with `python setup/scripts/audit_scheduled_tasks.py`
