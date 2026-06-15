# Skill: heartbeat-mcp-self-test

Verify TradingView and Alpaca MCP servers are reachable from the heartbeat process's perspective. AUDIT TV CDP port + TV process count + alpaca-mcp-server process; DIAGNOSE; HEAL the TV side automatically (Alpaca needs J for key validation); REPORT structured JSON.

> Per CLAUDE.md OP-25 lesson 2026-05-14 01:14 ET (TV CDP silent death after long runtime). TV processes alive but port 9222 NOT listening means heartbeat reads `data_get_ohlcv` returns "fetch failed" → ERROR_TV all session → silent missed entries. This skill catches it before the next heartbeat tick.

---

## When to invoke

- **Every overnight wake fire after midnight** (Stage 0 self-test, per `wake-protocol.md`)
- **Pre-market 08:30 ET** before premarket runs (covered separately by `preflight-readiness-audit.ps1`, but this is faster + more focused)
- **Mid-session if heartbeat log shows ERROR_TV or ERROR_ALPACA** for 2+ consecutive ticks
- **After ANY restart of TradingView Desktop**
- **When overnight grinder spawns Claude session and needs to verify chart-read capability**

---

## Steps

1. **Run probe (default = read-only, no heal):**

```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\heartbeat-mcp-self-test.ps1"
```

2. **Run with auto-heal (will restart TV if CDP down):**

```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\heartbeat-mcp-self-test.ps1" -Heal
```

3. **Read structured JSON output:**

```powershell
Get-Content "C:\Users\jackw\Desktop\42\automation\state\heartbeat-mcp-self-test-latest.json"
```

---

## Verdict criteria

| Verdict | Trigger |
|---------|---------|
| **GREEN** | Both: TV CDP port 9222 listening AND ≥1 TV process alive AND ≥1 alpaca-mcp process alive |
| **YELLOW** | First probe failed but retry-after-5s succeeded (transient); OR `-Heal` succeeded after RED |
| **RED** | After retry: either TV CDP probe fails OR alpaca-mcp process not found |

---

## Healing actions (auto-applied with `-Heal`)

| Subsystem | Failure | Auto-heal | Idempotent? |
|-----------|---------|-----------|-------------|
| **TV CDP down** | Port 9222 not listening | (1) Stop all TradingView processes via `Stop-Process -Force`; (2) `& "setup\launch_tv_debug.ps1"`; (3) wait 8s; (4) re-probe | YES — kill+relaunch is safe |
| **TV processes missing** | Same as above | Same fix (launcher creates fresh CDP-enabled instance) | YES |
| **Alpaca MCP missing** | No `*alpaca-mcp*` process | NO auto-heal — key validation requires J. Logs `CANNOT-AUTO-HEAL-alpaca-mcp-needs-J-to-restart-with-key-validation`; emits Discord alert | n/a |

**Never modifies:**
- Production heartbeat.md, params.json (rule 9)
- Alpaca API keys / `~/.claude.json` (security)
- Active heartbeat process (kill+restart of TV happens BEFORE next heartbeat tick — race-free if you run between scheduled ticks)

---

## Output files

| File | What |
|------|------|
| `automation/state/heartbeat-mcp-self-test-latest.json` | Most-recent verdict + probe results + heal actions |
| stdout | Human-readable verdict |
| `automation/state/discord-outbox.jsonl` | (if `-Heal` and RED-after-heal) Alert line for J |

JSON schema:
```json
{
  "skill": "heartbeat-mcp-self-test",
  "run_at": "ISO-timestamp",
  "verdict": "GREEN|YELLOW|RED",
  "reason": "human description",
  "tv_cdp_listening": true,
  "tv_proc_count": 12,
  "alpaca_proc_count": 1,
  "retried": false,
  "tv_heal_action": "no-op",
  "alpaca_heal_action": "no-op"
}
```

---

## Caveats

1. The TV process count typically shows 10-14 processes (parent + child renderers). Any count > 0 means TV is alive — the CDP-port check is the load-bearing part.
2. Alpaca MCP probe uses Win32_Process WMI query (NOT `Get-Process`) per OP-25 lesson — `Get-Process` silently misses console-less pythonw processes.
3. The `-Heal` TV restart kills ALL TradingView processes, including any J might have open. Use only when CDP is confirmed dead and J isn't actively viewing the chart.
4. Exit codes: `0` for GREEN/YELLOW, `1` for RED. Wake fires can chain on exit.

---

## Cross-references

- **Tool source:** `setup/scripts/heartbeat-mcp-self-test.ps1`
- **Companion skills:** `heartbeat-pulse-check` (sched task firing), `chart-data-verify` (TV vs CSV cross-check), `pin-chain-verify` (rule_version pin)
- **Related TV launcher:** `setup/launch_tv_debug.ps1`
- **CLAUDE.md OP-25 lessons absorbed:** "TradingView CDP port 9222 dies silently after long runtime" (2026-05-14 01:14 ET)
- **Related preflight:** `setup/scripts/fire-stage0-selftest.ps1` (broader self-test for wake fires)
