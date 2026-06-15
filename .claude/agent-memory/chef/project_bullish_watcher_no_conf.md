---
name: project_bullish_watcher_no_conf
description: bullish_watcher has no confidence stratification — all 289 graded obs are medium/score=11. Only useful split is PM session (13-15h): WR=65.6% vs AM 43.9%. Too thin (N=61) for a gate.
metadata:
  type: project
---

The bullish_watcher emits observations that are uniformly `medium` confidence with `bull_score=11` because:
- `_confidence_from_score()` requires `n_triggers >= 3` for "high" — bull entries have 0-2 triggers max
- The `confluence` metadata field is a float (reclaim_level), not a bool — always truthy

Observations: 289 graded, all direction=long, all ribbon_flipped=False, all bull_score=11.

**The only meaningful split found:** Time-of-day
- AM 10:00-12:59: N=228, WR=43.9%, -$1,756
- PM 13:00-15:59: N=61, WR=65.6%, +$628

PM works better because by 13:00h the day's directional thesis is resolved — reclaims in PM trend better. AM reclaims are first-tests with higher noise.

**2026-05 is the worst month:** WR=29.0%, -$685. High-VIX whipsaw environment destroys bullish reclaims.

**OP-21 status: NOT met.** 0 live J-confirmed wins. Full backfill is negative (-$1,128). High-conf tier doesn't exist structurally.

**DO NOT propose for promotion** until: N≥100 PM observations with stable WR≥60%, VIX regime stratification run, and J confirms interest.

**Filed:** `strategy/candidates/2026-05-21-bullish-watcher-quality-analysis.md` (DRAFT, NEEDS-MORE-DATA)
