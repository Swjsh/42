---
name: gym-verdicts-baseline
description: Gym scorecard baseline for tracking heartbeat health improvement over time
metadata:
  type: project
---

Gym scorecard baselines for the new $1K paper accounts (live from 5/18):

**5/18 (Day 1):** No gym data retained in memory — first live day, limited audit.

**5/19 (Day 2):**
- Overall: RED
- Crypto gym: GREEN (48/48 pass)
- Heartbeat tick audit: RED — 6/16 live ticks MISALIGNED-CRITICAL (37.5%)
- Pin chain: GREEN (v15.2 all match)
- Chart data verify: GREEN (5 bars, $0 divergence)
- Pulse check: YELLOW (max gap 15.0 min, 25 gaps of 6-15 min)
- MCP self-test: GREEN (TV CDP listening)
- Watcher state: YELLOW (no bars for target date, obs_today=52, 6/7 watchers silent)

**Root cause of RED on 5/19:** Rate-limit gap (L54) + gym_session.py BOM encoding bug (L53) + gym key-name mismatch (L53). Both L53 bugs fixed 5/19 EOD.

**Target state:** Gym GREEN = heartbeat tick audit <10% MISALIGNED-CRITICAL + pulse check GREEN (all gaps ≤6 min) + all watchers active.

**How to apply:** Compare each session's gym verdict against this baseline. A trend of decreasing MISALIGNED-CRITICAL % means the R1 closed-bar fix and stale-cache fixes are working. An increasing trend means a new regression has been introduced.
