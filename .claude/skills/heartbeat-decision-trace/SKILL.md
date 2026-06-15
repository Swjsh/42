# Skill: heartbeat-decision-trace

For a specific tick on a given date, walk through every filter (1-11) using the recorded state in `decisions.jsonl` + canonical thresholds in `params.json`. Output: per-filter PASS/BLOCK table + final action explanation. Pure DIAGNOSTIC — no healing.

> Per CLAUDE.md OP-25 ("Silent failure is the only true failure"). When J asks "why did the engine SKIP my obvious 11:30 ET reclaim?" this skill answers in 5 seconds against the canonical filter list.

---

## When to invoke

- **When J asks "why did tick #N do X?"** — primary use case
- **When EOD summary flags a SKIP that should have been an ENTRY** (or vice versa)
- **When validating a new rule version** — pick 5 ticks across a backtest day, trace each
- **When the heartbeat reason field is cryptic** (e.g., "ribbon_bull_tight_spread_14c_blocks_both")
- **When `simulator_real.py` and live engine disagree on a bar** — trace both decisions

---

## Steps

1. **Trace by tick_id (most reliable):**

```powershell
cd C:\Users\jackw\Desktop\42\backtest
python -m autoresearch.heartbeat_decision_trace --date 2026-05-14 --tick 27
```

2. **Trace by time-of-day (when you don't know tick_id):**

```powershell
python -m autoresearch.heartbeat_decision_trace --date 2026-05-14 --time 14:24
```

3. **Trace the most recent tick on a date:**

```powershell
python -m autoresearch.heartbeat_decision_trace --date 2026-05-14 --last
```

4. **Read the per-filter table:**

```
=== heartbeat-decision-trace 2026-05-14 tick_id=27 time_et=14:24 ===
action: HOLD
recorded reason: inside no_trade_window 14:00-15:00 ET, all entries blocked filter_1 time gate

  #  name                         dir   verdict  reason
  --------------------------------------------------------------
  1  Time gate                    both  BLOCK    time_et=14:24 in entry window [09:35,15:00) AND blackout [14:00,15:00) active → BLOCK
  2  News blackout                both  PASS     no news blackout indicated in reason field
  ...
```

---

## Verdict criteria (per-filter PASS/BLOCK + final)

| Verdict | Per-filter | Final action implied |
|---------|------------|---------------------|
| **PASS** | All inputs satisfied | Not directly the verdict — depends on full chain |
| **BLOCK** | One specific gate failed | If chain has any BLOCK, side is rejected |
| **N/A** | Filter inputs not recorded in tick | Skipped (e.g., F2 news without snapshot) |

**Final action:**
- All bull-side filters PASS + bull_score ≥ 2 → BULL eligible
- All bear-side filters PASS + bear_score ≥ 1 → BEAR eligible
- Both sides eligible → direction selector picks by ribbon stack + leading score
- Neither side clean → HOLD

---

## Output files

| File | What |
|------|------|
| `automation/state/heartbeat-decision-trace-{date}-tick{N}.json` | Per-filter results + bull/bear blockers + recorded action |
| stdout | Human-readable per-filter table |

JSON schema:
```json
{
  "skill": "heartbeat-decision-trace",
  "target_date": "YYYY-MM-DD",
  "tick_id": 27,
  "time_et": "14:24",
  "recorded_action": "HOLD",
  "recorded_reason": "inside no_trade_window 14:00-15:00 ET",
  "params_rule_version": "v15.1",
  "filter_results": [{"n": 1, "name": "...", "passed": false, "reason": "..."}],
  "bull_blockers": [[1, "Time gate"]],
  "bear_blockers": [[1, "Time gate"]]
}
```

---

## Caveats

1. **Filter 2 (news), 5 (PDT), 6 (per-trade risk) cannot be perfectly reconstructed from tick alone** — they need news.json/account snapshot at tick time. Tool falls back to scanning the `reason` field for hints.
2. **Filter 9 (volume) is inferred from `bear_blocked` / `bull_blocked` lists when present** — older ticks without `filter_state` block-list will show PASS even if vol blocked.
3. **Filter 11 (direction selector)** is computed AFTER all per-filter results, not from a recorded state.
4. **`params.json` is the authoritative threshold source** — if J changes a threshold mid-day (forbidden by rule 9 but possible in dev), trace results may not match the actual heartbeat decision.
5. **NO healing performed.** This is read-only diagnostic. To re-run a tick under different params, use `simulator_real.py`.

---

## Cross-references

- **Tool source:** `backtest/autoresearch/heartbeat_decision_trace.py`
- **Companion skills:** `heartbeat-tick-audit` (chart-data correctness, not filter trace), `heartbeat-pulse-check` (firing schedule)
- **Decisions ledger schema:** `automation/state/decisions.jsonl`
- **Canonical filter source:** `automation/prompts/heartbeat.md` filter 1-11
- **Threshold source:** `automation/state/params.json`
