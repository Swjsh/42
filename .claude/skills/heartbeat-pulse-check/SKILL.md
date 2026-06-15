# Skill: heartbeat-pulse-check

Verify the `Gamma_Heartbeat` scheduled task is firing on schedule (every 3 min during market hours). AUDIT log timestamps, DIAGNOSE gap severity, optionally HEAL by restarting the scheduled task, REPORT structured JSON.

> Per CLAUDE.md OP-25 ("silent failure is the only true failure mode"). Heartbeat that silently stops firing is the worst-case — engine misses entries, exits, kill-switch checks. This skill catches it.

---

## When to invoke

- **Daily, automatically** — overnight wake fires before 09:30 ET premarket; included in EOD pipeline at 16:05 ET via `eod_deep/main.py`
- **On-demand** when J asks "is the heartbeat firing?"
- **After ANY scheduled-task config change** to `Gamma_Heartbeat`
- **When `automation/state/decisions.jsonl` shows zero entries for a market session** (suspicious silence)
- **Mid-session if Discord goes silent on heartbeat-related alerts**

---

## Steps

1. **Run the audit on the target date (defaults to today):**

```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\heartbeat-pulse-check.ps1"
& "C:\Users\jackw\Desktop\42\setup\scripts\heartbeat-pulse-check.ps1" -Date 2026-05-14
```

2. **Auto-heal mode (use only when RED — adds Discord alert):**

```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\heartbeat-pulse-check.ps1" -Heal
```

3. **Read structured JSON output:**

```powershell
Get-Content "C:\Users\jackw\Desktop\42\automation\state\heartbeat-pulse-check-2026-05-14.json"
```

---

## Verdict criteria

| Verdict | Trigger | Auto-heal action |
|---------|---------|------------------|
| **GREEN** | All gaps between consecutive FIREs ≤ 6 min during 09:30-15:55 ET, scheduled task Ready/Running | no-op |
| **YELLOW** | 1+ gaps 6-15 min (one missed tick), task healthy | no-op (transient throttle is OK) |
| **RED** | Any gap > 15 min, OR zero market-hour fires, OR task Disabled/Missing | If `-Heal` flag: re-enable task if Disabled; emit Discord alert; if task missing → flag for J |

---

## Healing actions (auto-applied with `-Heal`)

| Condition | Action | Idempotent? |
|-----------|--------|-------------|
| Task state = Disabled | `Enable-ScheduledTask Gamma_Heartbeat` | YES |
| Task state = Missing | NO auto-heal (logs `needs-J-to-recreate-via-setup-scripts`); Discord alert emitted | n/a |
| Task state = Ready/Running but RED gaps | NO auto-heal (run-time issue not config); writes `investigate-windows-task-scheduler-history`; Discord alert | n/a |

**Never modifies:**
- Production heartbeat.md (rule 9)
- params.json (rule 9)
- The scheduled task's command-line / triggers (J authorization required)

---

## Output files

| File | What |
|------|------|
| `automation/state/heartbeat-pulse-check-{date}.json` | Verdict + reason + gap stats + heal action |
| stdout | Human-readable verdict + sample gaps |
| `automation/state/discord-outbox.jsonl` | (if `-Heal` and RED) Alert line for J's morning review |

JSON schema:
```json
{
  "skill": "heartbeat-pulse-check",
  "run_at": "ISO-timestamp",
  "target_date": "YYYY-MM-DD",
  "verdict": "GREEN|YELLOW|RED",
  "reason": "human description",
  "fire_count_total": 99,
  "market_fire_count": 46,
  "max_gap_minutes": 6.05,
  "gaps_over_15_min": 0,
  "gaps_6_to_15_min": 1,
  "scheduled_task_state": "Ready",
  "heal_action": "no-op",
  "sample_gaps": [...]
}
```

---

## Caveats

1. The 09:30-09:39 startup window may have one delayed FIRE due to PowerShell startup overhead — first interval can be up to 9 min. Treat as YELLOW only if it persists.
2. SKIP throttle entries are NOT counted as FIREs — by design (throttle skipped this tick, will re-evaluate next). Only `FIRE` lines count.
3. After 15:55 ET no FIREs are expected (EodFlatten takes over). The audit ignores post-15:55 absences.
4. Exit codes: `0` for GREEN/YELLOW, `1` for RED (so wake fires can chain on exit).

---

## Cross-references

- **Tool source:** `setup/scripts/heartbeat-pulse-check.ps1`
- **Companion skills:** `heartbeat-mcp-self-test` (verifies MCPs reachable), `heartbeat-decision-trace` (per-tick filter walk)
- **Related preflight script:** `setup/scripts/preflight-readiness-audit.ps1` (full daily-task audit)
- **CLAUDE.md OP-25 lesson:** "Silent failure is the only true failure" — this skill prevents that for heartbeat scheduling
