---
name: rate-limit-market-hours
description: Hard rule — never run interactive Claude sessions during 09:30-15:55 ET market hours
metadata:
  type: feedback
---

NEVER run /loop, interactive sessions, or engineering research during 09:30-15:55 ET market hours.

**Why:** Claude Code API rate limit is shared between all sessions on the same account. Interactive /loop sessions and Gamma_Heartbeat scheduled task both consume the same quota. On 5/19, /loop ran during market hours → heartbeat had 103-minute blackout (10:57-12:40 ET) → two J-quality bull setups missed → one ghost ENTER_BEAR (logged, no order). Documented as L54.

**How to apply:** Before starting any interactive Claude work, check the time. If 09:30-15:55 ET on a weekday, WAIT until 16:00 ET. Only after-4pm window per OP-22. The only Claude API consumers during live hours: Gamma_Heartbeat, Gamma_Heartbeat_Aggressive, Gamma_WatcherLive.
