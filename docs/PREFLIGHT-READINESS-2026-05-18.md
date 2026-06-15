# 5/18 Dual-Account Go-Live Pre-Flight Readiness

> Created 2026-05-16 evening. J reviews before 08:30 ET Monday 5/18.
> This is the first trading session with TWO live paper accounts running simultaneously.

---

## Accounts being activated

| Account | Alias | Style | MCP Prefix | Starting Balance |
|---|---|---|---|---|
| Account 1 | Gamma-Safe | Conservative (ATM, 30% risk, +30% TP1) | `mcp__alpaca__*` | $1,000 (fresh reset) |
| Account 2 | Gamma-Bold | Aggressive (ITM-2, 50% risk, +75% TP1) | `mcp__alpaca_aggressive__*` | $1,000 (pre-seeded) |

---

## J's 5/18 morning checklist (before 08:30 ET)

### Account setup (MANUAL — Alpaca paper dashboard)
- [ ] **Account 1 (Safe) reset**: Verify Alpaca paper Account 1 balance = ~$1,000. If still showing ~$101K, reset it.
- [ ] **Account 2 (Bold) verify**: Log into Alpaca paper with the aggressive key (`PKANCBMIY...`) and confirm balance shows $1,000.
- [ ] **No open positions on either account** before market open.

### Task Scheduler (ENABLE one task)
- [ ] **Enable `Gamma_EodFlatten_Aggressive`**: This task is currently DISABLED. Before 5/18 market open:
  ```powershell
  Enable-ScheduledTask -TaskName "Gamma_EodFlatten_Aggressive"
  Get-ScheduledTask -TaskName "Gamma_EodFlatten_Aggressive" | Select-Object TaskName, State
  # Should show State = Ready
  ```
  Fires at 15:55 ET to close any open Bold position. Path fixed to read `current-position-bold.json`.

### Architecture decision (READ BEFORE ENABLING ANYTHING ELSE)
- [ ] **Keep `Gamma_Heartbeat_Aggressive` DISABLED.**
  The main `heartbeat.md` (run by `Gamma_Heartbeat`) already handles BOTH accounts in dual-account mode.
  Enabling `Gamma_Heartbeat_Aggressive` ALSO would double-trade Bold (place 2x orders).
  **DO NOT enable `Gamma_Heartbeat_Aggressive`.**

---

## Gamma's automation readiness (all GREEN as of 2026-05-16 21:00 ET)

| Item | Status | File / Evidence |
|---|---|---|
| params.json rule_version | **v15.1** | `automation/state/params.json` |
| params_safe.json | **v1.0, effective 5/18** | `automation/state/params_safe.json` |
| params_bold.json | **v1.0, effective 5/18** | `automation/state/params_bold.json` |
| heartbeat.md RULE_VERSION | **v15.1** | `automation/prompts/heartbeat.md` line 16 |
| premarket.md RULE_VERSION_EXPECTED | **v15.1** | `automation/prompts/premarket.md` line 39 |
| aggressive/heartbeat.md RULE_VERSION | **v15.1** | (backup file, not run by scheduler) |
| aggressive/params.json rule_version | **v15.1** | `automation/state/aggressive/params.json` |
| current-position-safe.json | **status=null** | Account 1 flat, ready |
| current-position-bold.json | **status=null** | Account 2 flat, ready |
| aggressive/eod-flatten.md path | **FIXED** | Reads `current-position-bold.json` (L40) |
| run-heartbeat-aggressive.ps1 path | **FIXED** | `$posStatePath` = `current-position-bold.json` |
| heartbeat.md dual-account mode | **ACTIVE** | Lines 95-111, reads both params_safe.json + params_bold.json |
| Gamma_Heartbeat | **Enabled, Ready** | Fires every 3 min 09:30-15:50 ET |
| Gamma_EodFlatten | **Enabled, Ready** | Fires at 15:55 ET (Safe account) |
| Gamma_EodFlatten_Aggressive | **Disabled** | J must enable before 5/18 open |
| Gamma_Heartbeat_Aggressive | **Disabled** | Keep disabled — dual-account mode handles Bold |

---

## Kill switch configuration

| Account | Daily loss kill switch | Per-trade risk cap | Isolation |
|---|---|---|---|
| Gamma-Safe | -30% of day-start equity | 30% | Safe stopping does NOT halt Bold |
| Gamma-Bold | -50% of day-start equity | 50% | Bold stopping does NOT halt Safe |

Both kill switches are isolated per CLAUDE.md Rule 5. If Bold blows up, Safe keeps trading.

---

## What's different on 5/18 vs prior sessions

1. **Two MCP prefixes per tick**: heartbeat reads `mcp__alpaca__*` for Safe AND `mcp__alpaca_aggressive__*` for Bold.
2. **Two params files**: `params_safe.json` + `params_bold.json` overrides loaded on top of base `params.json`.
3. **Two position state files**: `current-position-safe.json` (Safe) + `current-position-bold.json` (Bold).
4. **Two decisions.jsonl rows per trade**: each with `account_id="safe"` or `account_id="bold"`.
5. **Bold can enter ALL setups** (including DRAFT + WATCH-ONLY). Safe is CONFIRMED-only.
6. **Bold uses ITM-2 at $1K tier** (max delta). Safe uses ATM (defined risk).
7. **EOD flatten: TWO tasks** — `Gamma_EodFlatten` (Safe) + `Gamma_EodFlatten_Aggressive` (Bold, needs enabling).

---

## If something breaks at open

**Safe account stuck**: check `current-position-safe.json` + `mcp__alpaca__get_all_positions`
**Bold account stuck**: check `current-position-bold.json` + `mcp__alpaca_aggressive__get_all_positions`
**Heartbeat not firing both accounts**: check `automation/state/loop-state.json#session_id` == today's date
**Kill switch tripped on one account**: read `automation/state/kill-switch.json` (Safe) or `automation/state/kill-switch-bold.json` (Bold) for reason. Kill switches are isolated.
**Bold position not closed at 15:55**: `Gamma_EodFlatten_Aggressive` must be Enabled — verify with `Get-ScheduledTask -TaskName "Gamma_EodFlatten_Aggressive"`

---

## Design reference

Full dual-account design: `strategy/dual-account-design.md`
L40 anti-pattern (state file path migration): `docs/LESSONS-LEARNED.md#L40`
Pin-chain verification (automated): run `/pin-chain-verify` skill
