# Skill: watcher-state-inspector

For the 2 stateful watchers (ORB + ODF), dump current `_orb_state[date]` and `_odf_state[date]` after a fresh `watcher_live.py`-style invocation. Verify state machines are progressing. AUDIT, DIAGNOSE, optionally HEAL by re-running silent-watcher-days script.

> Per CLAUDE.md OP-25 lesson 2026-05-14 evening (T80/T82) — ORB + ODF have module-level state machines that progress NEUTRAL → BREAKOUT → WAIT_RETEST → ENTRY across bars. Pre-T82, fresh-process invocations reset state on every fire → entries never fired. T82 added warmup loop. This skill verifies the warmup actually advances state today.

---

## When to invoke

- **Daily, automatically** — overnight wake fires post-15:55 ET to verify state advanced before market closed
- **When `watcher-observations.jsonl` shows 0 entries on a session that should have signals**
- **After ANY change to `watcher_live.py` warmup loop** (lines 323-349) or to ORB/ODF detector internals
- **When investigating "why did ORB watcher fire at 10:30 yesterday but not today?"**
- **When a NEW stateful watcher is added** (extend the warmup loop FIRST, then re-run this)

---

## Steps

1. **Run the inspector (defaults to today's date):**

```powershell
cd C:\Users\jackw\Desktop\42\backtest
python -m autoresearch.watcher_state_inspector
```

2. **Inspect a specific date:**

```powershell
python -m autoresearch.watcher_state_inspector --date 2026-05-14
```

3. **Auto-heal (will run audit-silent-watcher-days.ps1 if RED):**

```powershell
python -m autoresearch.watcher_state_inspector --date 2026-05-14 --heal
```

4. **Read structured JSON:**

```powershell
Get-Content "C:\Users\jackw\Desktop\42\automation\state\watcher-state-inspector-2026-05-14.json"
```

---

## Verdict criteria

| Verdict | Trigger | Auto-heal |
|---------|---------|-----------|
| **GREEN** | ORB state progressed past NEUTRAL, ODF state present, ≥1 watcher observation today | n/a |
| **YELLOW** | ODF state empty (may be correct on trending days); OR 0 observations after full session (may be correct on no-setup days); OR warmup errors present | n/a |
| **RED** | ORB state empty after 6+ bars (state machine never advanced — bug); OR could not load bars for date | If `-Heal` flag: runs `setup\scripts\audit-silent-watcher-days.ps1` for cross-day audit |

---

## What "state progressing" means

| Watcher | Healthy state on session-with-breakout |
|---------|----------------------------------------|
| **ORB** | `status` ≥ `BREAKOUT_HIGH` or `BREAKOUT_LOW`; `breakout_high`/`breakout_low` populated; `bars_since_breakout` incrementing |
| **ODF** | `status` ≥ `DRIVE_DETECTED`; `hod` ratchet incrementing on rallies; `lod` ratchet decrementing on selloffs; `stall_count` populated on flat tape |

| Watcher | Legitimately empty state |
|---------|-------------------------|
| ORB | If no clean ORB break occurred (rare — most days have one) |
| ODF | Trending days without a drive-then-fade pattern (gap-and-go) |

---

## Healing actions (auto-applied with `-Heal`)

| Condition | Action | Idempotent? |
|-----------|--------|-------------|
| ORB state empty + RED | Runs `audit-silent-watcher-days.ps1` to audit per-day obs across watcher fleet | YES (read-only audit) |
| Bar load failed | NO auto-heal — likely yfinance rate-limit; will retry next fire | n/a |

**Never modifies:**
- `watcher_live.py` (production code; rule 9)
- ORB/ODF detector logic
- `watcher-observations.jsonl`

---

## Output files

| File | What |
|------|------|
| `automation/state/watcher-state-inspector-{date}.json` | Verdict + ORB state + ODF state + warmup errors + observation count |
| stdout | Human-readable dump |

JSON schema:
```json
{
  "skill": "watcher-state-inspector",
  "target_date": "YYYY-MM-DD",
  "verdict": "GREEN|YELLOW|RED",
  "reason": "human description",
  "today_bars_loaded": 78,
  "bar_idx_in_day_warmed_up": 77,
  "orb_state": {"status": "...", "breakout_high": 745.5, ...},
  "odf_state": {"status": "...", "hod": 749.8, ...},
  "orb_status": "BREAKOUT_HIGH",
  "odf_status": "NEUTRAL",
  "warmup_errors": [],
  "watcher_obs_count_today": 3,
  "heal_action": "no-op"
}
```

---

## Caveats

1. **The skill runs in its OWN Python process** — module state is naturally fresh, mimicking production's per-fire process spawn. No `del sys.modules[...]` hackery needed.
2. **ODF empty state is often correct** — trending days never trigger drive-then-fade. Don't auto-RED on ODF alone.
3. **Bar load uses watcher_live's helpers** — if those helpers change name/signature, this skill needs an update.
4. **Counts observations from `watcher-observations.jsonl` regardless of watcher** — to filter per-watcher, use `audit-silent-watcher-days.ps1` instead.
5. Exit codes: `0` for GREEN/YELLOW, `1` for RED.

---

## Cross-references

- **Tool source:** `backtest/autoresearch/watcher_state_inspector.py`
- **Companion skills:** `watcher-fleet-status` (per-watcher day counts), `chart-data-verify` (bar-level data integrity)
- **Production warmup code:** `backtest/autoresearch/watcher_live.py` lines 309-349 (T82 + T82b)
- **Root-cause docs:** `docs/T80-ORB-BULL-REGRESSION.md`
- **CLAUDE.md OP-25 lesson:** "Stateful watchers + per-tick fresh-process scheduled tasks = silent zero observations" (T80/T82 absorption)
