# Winner-Day Entry Blocker Diagnosis

> Config: Safe-ATM (strike_offset=0, premium_stop=-8%, no_trade_before=09:35, no dead window)

## Summary Table

| Date | J Entry | Engine First Pass | Engine Entry | Lag (min) | Engine P&L | Top Blocker |
|---|---|---|---|---|---|---|
| 2026-04-29 | 10:25 | 13:40:00 | 13:40:00 | 195 | $-49.68 | F8 |
| 2026-05-01 | 13:36 | NEVER | NEVER | N/A | $-121.60 | F5 |
| 2026-05-04 | 10:27 | 11:20:00 | 11:20:00 | 53 | $-143.20 | F8 |

## Filter Blocker Breakdown

### 2026-04-29

| Filter | Bars blocked | Description |
|---|---|---|
| F8 | 46 | F8 — VIX < 17.30 or not rising |
| F9 | 43 | F9 — Not a breakdown bar (green bar or insufficient volume) |
| F6 | 28 | F6 — Ribbon spread < 30c (EMAs too compressed after gap) |
| F10 | 17 | F10 — No valid trigger (no level rejection / ribbon flip / confluence) |
| F5 | 11 | F5 — Ribbon NOT BEAR-stacked (ribbon EMA lag at open) |
| F7 | 8 | F7 — Volume divergence failed |

**Engine trades:**
- 13:45 → 13:50: 710P  P&L=$-49.68  (ExitReason.EXIT_ALL_PREMIUM_STOP)

### 2026-05-01

| Filter | Bars blocked | Description |
|---|---|---|
| F5 | 47 | F5 — Ribbon NOT BEAR-stacked (ribbon EMA lag at open) |
| F8 | 47 | F8 — VIX < 17.30 or not rising |
| F9 | 43 | F9 — Not a breakdown bar (green bar or insufficient volume) |
| F10 | 23 | F10 — No valid trigger (no level rejection / ribbon flip / confluence) |
| F7 | 14 | F7 — Volume divergence failed |

**Engine trades:**
- 12:20 → 12:25: 723P  P&L=$-72.80  (ExitReason.EXIT_ALL_PREMIUM_STOP)
- 13:55 → 14:00: 723P  P&L=$-48.80  (ExitReason.EXIT_ALL_PREMIUM_STOP)

### 2026-05-04

| Filter | Bars blocked | Description |
|---|---|---|
| F8 | 41 | F8 — VIX < 17.30 or not rising |
| F9 | 40 | F9 — Not a breakdown bar (green bar or insufficient volume) |
| F7 | 17 | F7 — Volume divergence failed |
| F10 | 17 | F10 — No valid trigger (no level rejection / ribbon flip / confluence) |
| F5 | 9 | F5 — Ribbon NOT BEAR-stacked (ribbon EMA lag at open) |
| F6 | 8 | F6 — Ribbon spread < 30c (EMAs too compressed after gap) |

**Engine trades:**
- 11:25 → 11:30: 718P  P&L=$-143.20  (ExitReason.EXIT_ALL_PREMIUM_STOP)

## Root-Cause Hypothesis

Based on blocker frequencies, the primary bottleneck on sustained-trend days is:

- **F6 (spread < 30c) + F5 (ribbon not stacked)**: After a gap-down open, the ribbon EMAs
  need 4-8 RTH bars (~20-40 min) to diverge to >= 30c spread. During this time, EVERY bar
  is blocked regardless of price action or level state.

- **F10 (no trigger)**: Even after ribbon warms up, the engine needs a REJECTION at a level.
  On gap-down days, price is already below most premarket levels at the open. The engine waits
  for price to BOUNCE BACK to a level and reject — which can take 60-120 min more.

**Combined lag**: Ribbon warmup (30-40 min) + bounce-back wait (60-120 min) = 90-160 min
delay vs J's morning open entries.

**Fix candidates:**
1. Reduce spread minimum for the first 10 minutes of RTH (e.g. `spread >= 5c` if F5=BEAR)
2. Allow entry on first 09:35-09:45 bar if HTF (15m) ribbon is BEAR-stacked (uses pre-built warmup)
3. Add a 'gap-down continuation' trigger that fires on gap-down open + first red bar (no bounce required)
4. Wire the PML/PMH rejection as a trigger when price GAPS THROUGH a level (not just bounces to it)