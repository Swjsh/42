---
name: vix-filter-f8-sensitivity
description: F8 VIX rising filter blocks bear entries on days with small VIX drift — potential over-sensitivity
metadata:
  type: project
---

F8 (VIX must be rising for bear entries) uses a short-term 3-5 bar VIX trend signal.

**5/19 observation:** VIX opened at 18.02 (elevated, MID regime), drifted to 17.80-17.93 (-22bps). F8 classified this as "declining" and blocked all bear entries despite a valid $3.07 bear move (SPY hit session low 732.33). The ghost ENTER_BEAR at 10:03 was the one tick where F8 briefly showed not-blocked — then VIX continued to drift and F8 re-activated.

**Hypothesis:** A 22bp VIX decline from an elevated 18.02 level is noise, not a genuine volatility collapse. F8 should only block when VIX drops >0.50 points from session high, or drops below the premarket opening level by >0.30.

**Chef item queued 5/19:** `_chef-inbox/2026-05-19-vix-declining-bear-filter-false-negatives.md`

**Do NOT re-queue this item.** It is already in the Chef inbox. Reference this memory when J asks why bear entries were blocked on bear days.

**How to apply:** When auditing future sessions where the premarket bias was bearish but no bear entries fired, check F8 status. If F8 was blocking because VIX drifted <0.50 points, flag the pattern but don't create a new Chef item — the existing item covers this. If a different VIX pattern emerges (e.g., VIX at 16.x on a bear day), that would be a new finding worth a separate item.
