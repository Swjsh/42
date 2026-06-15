# State files — schema and lifecycle

> Persistent state between heartbeat invocations. The heartbeat is **stateless across ticks**; everything it needs is on disk in this folder.

---

## Files

| File | Lifecycle | Purpose |
|---|---|---|
| `mode.json` | Manually edited (rare) | live-paper / dry-run / paused mode |
| `kill-switch` | File-presence flag | If present, heartbeat exits without trading |
| `today-bias.json` | Written by premarket, read by heartbeat | Day's bias and key levels |
| `current-position.json` | Written by heartbeat, read by heartbeat | Open position state |
| `params.json` | Manually edited (occasionally) | Tunable parameters (stops, TPs, sizing) |
| `circuit-breaker.json` | Written by heartbeat | Daily-loss tripped flag |
| `equity-curve.json` | Written by EOD | Rolling equity history |
| `heartbeat.log` | Append-only by heartbeat | One line per tick — auditable trace |
| `cron.log` | Stdout/stderr from cron | Raw log of cron-invoked claude runs |

---

## Schemas

### `mode.json`
```json
{
  "mode": "live-paper",
  "last_changed": "2026-05-04T18:00:00-04:00",
  "changed_by": "J",
  "reason": "Tier 1 launch"
}
```

### `today-bias.json` (see [`automation/prompts/premarket.md`](../prompts/premarket.md) Step 4 for canonical schema)

### `current-position.json`
```json
{
  "status": "open" | "pending_fill" | "null",
  "order_id": "string",
  "fill_id": "string|null",
  "entry_time": "ISO 8601",
  "fill_time": "ISO 8601|null",
  "contract": {
    "symbol": "SPY",
    "expiry": "YYYY-MM-DD",
    "strike": 721,
    "type": "P"
  },
  "qty_initial": 3,
  "qty_remaining": 3,
  "entry_premium": 0.85,
  "current_premium": 1.50,
  "stop_premium": 0.425,
  "tp1_taken": false,
  "tp1_premium_target": 1.275,
  "rejected_level": 721.58,
  "trigger_events": ["rejection at PMH 721.58", "ribbon flipped bearish", "trendline confluence"],
  "thesis_journal_anchor": "journal/2026-05-04.md#trade-1",
  "last_management_check": "ISO 8601"
}
```

When no position is open, file contains: `{"status": "null"}`.

### `params.json` (see `automation/decision-log.md` for canonical schema)

### `circuit-breaker.json`
```json
{
  "tripped": false,
  "tripped_at": null,
  "tripped_reason": null,
  "starting_equity_today": 1000.00,
  "current_equity": 1000.00,
  "max_drawdown_today_dollars": 0,
  "max_drawdown_today_pct": 0
}
```

When tripped: `tripped: true`, reason logged, no new entries until next trading day's premarket resets it.

### `heartbeat.log` (one line per invocation)
```
ISO_TIMESTAMP | MODE | ACTION | DETAIL
2026-05-05T09:33:00-04:00 | live-paper | NO_SIGNAL | filters:bias=bearish,ribbon=bearish,triggers:0/3
2026-05-05T09:36:00-04:00 | live-paper | ENTRY_PLACED | SPY 721P 0DTE x3 @ $1.20 LIMIT order_id=abc123
2026-05-05T09:39:00-04:00 | live-paper | ENTRY_FILLED | fill_premium=1.20 fill_time=09:38:42
2026-05-05T09:42:00-04:00 | live-paper | HOLD | premium=1.30 ribbon=bearish stop=0.60
2026-05-05T10:15:00-04:00 | live-paper | TP1_TAKEN | qty_sold=2/3 fill_premium=1.81 +51%
2026-05-05T11:18:00-04:00 | live-paper | RUNNER_EXIT | reason=ribbon-flip qty_sold=1 fill_premium=2.30 +92%
```

---

## State invariants (always true)

- If `current-position.json.status = "open"`, Alpaca's reported open positions must match.
- If `circuit-breaker.tripped = true`, no new ENTRY actions until reset.
- `today-bias.json.date` must match today's date OR heartbeat refuses to run (forces premarket re-run).
- `heartbeat.log` is append-only; never truncated mid-day.

If any invariant is violated, heartbeat creates `kill-switch` with the violation as the reason.

---

## Manual interventions

- **Pause the system:** `touch state/kill-switch`
- **Resume:** `rm state/kill-switch`
- **Force re-run premarket:** `rm state/today-bias.json` and either wait for cron or run manually
- **Reset circuit breaker (rare — usually next day's premarket does this):** edit `circuit-breaker.json` → `tripped: false`
- **Adjust a parameter:** edit `params.json`. Takes effect on next tick.
- **Switch to dry-run:** edit `mode.json` → `"mode": "dry-run"`. Takes effect on next tick.

All manual interventions are logged to `journal/{today}.md` automatically by the next heartbeat that detects the change.
