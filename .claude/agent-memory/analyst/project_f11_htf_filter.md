---
name: f11-htf-filter-pattern
description: F11 HTF 15m filter is systematically late on reversal days — pattern observed 5/18 and 5/19
metadata:
  type: project
---

F11 (HTF 15m stack must not be BEAR for bull entries) has a multi-bar lag on genuine intraday reversal days.

**5/18:** HTF lag visible pre-09:57 entry but cleared before valid entry window.
**5/19:** HTF never cleared to MIXED/BULL during the valid entry window (09:35-15:00 ET). SPY rallied $5.77 (732.33 → 738.10) with the engine reading 10/11 bull scores but unable to enter. All afternoon: HOLD_DEV waiting for F11 to clear.

**Pattern:** On days where session low is set before 11:00 ET and SPY recovers more than $2.00, the 15m ribbon may stay in BEAR stack for 1-2 hours after the 5m ribbon has clearly flipped BULL. F11 prevents bull entries during this period.

**Chef item queued 5/19:** `_chef-inbox/2026-05-19-f11-htf-latency-on-reversal-days.md` — backtest F11 bypass on confirmed reversal days.

**Why:** The 5m vs 15m lag is by design (prevents counter-trend entries into macro bear structure). The question is whether reversal-day conditions (session low set early + >$2 recovery) are sufficient to safely relax F11.

**How to apply:** When auditing future sessions where engine had 10/11 scores but no entries, check if F11 was the sole blocker. If yes and the day was a genuine reversal day, flag this pattern. Don't re-queue the Chef item — it's already there. Reference this memory when answering J's weekend questions about missed entries.
