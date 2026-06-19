---
proposed_id: L78
title: Premarket must self-heal TV connection, not silently exit
date_observed: 2026-06-01
source: First trading day back (2026-06-01) — TV not up at premarket, engine held all day
severity: HIGH
cross_ref: [L41, L35]
---

## Symptom
2026-06-01: TV was running (12 processes) but not with CDP port 9222.
Gamma_LaunchTV (08:00 task) failed to attach. Premarket ran at 08:39, found TV_NOT_RUNNING,
set bias=no-trade, and exited without drawing levels. The entire session — including a
+4.21 SPY bull run from 755.32 to 759.53 — was sat out because key-levels.json was
empty (all levels expired after 10-day offline). Engine held correctly by rules,
but the rules needed level context that premarket failed to provide.

## Root cause
premarket.md Step 1 says: if tv_health_check fails, write error and EXIT.
Silent exit without levels = engine has no reclaim triggers = can't fire bull entries
even when ribbon, spread, VIX, and price all qualify.

## Fix (applied 2026-06-01)
premarket.md Step 1 updated: if TV not connected, attempt self-heal (run launch_tv_debug.ps1,
retry 3x with 10s gaps). Only if truly unreachable after retries, continue with
bias=no-trade-tv-fail (do NOT exit — at minimum get PDT/budget/kill-switch state).
This ensures levels are always seeded when TV is available, and the session-context
is always known even when TV fails.

## Prevention
- Gamma_LaunchTV task should also verify CDP port after launch (not just process start)
- Add a CDP health check in the launch script — if port not responding after 30s, kill and relaunch
- premarket self-heal is the backstop
