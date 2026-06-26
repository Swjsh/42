---
name: block-conf-lvl-rec-afternoon-revalidated
description: block_conf_lvl_rec_afternoon (Bold gate #12) re-validated on CURRENT engine 2026-06-26 -> UNBLOCK; old-engine ratification sign-flipped, gate now costs +$779 IS and protects nothing OOS
metadata:
  type: project
---

`block_conf_lvl_rec_afternoon` (gates.py #12) blocks confluence+level_reclaim entries from 14:00 ET onward (code does NOT check side, but empirically ALL removed trades are C/bull). Bold params=true with a "KEPT but DEAD, superseded by block_conf_lvl_rej_midday_afternoon" doc.

**Re-validation 2026-06-26 (real fills, ITM-2, managed -50% cap, A/B blocked vs unblocked, tool=`backtest/tools/conf_lvl_rec_afternoon_revalidate.py`, scorecard=`analysis/recommendations/conf_lvl_rec_afternoon_revalidate.json`):**
- IS (287d): gate removes 4 afternoon conf+rec C trades = NET **+$779** (one +$1034 winner 2026-01-02 dominates). Blocking COSTS +779. delta(unblock-block)=+779.
- OOS (74d): A/B total delta = **+$0**. The one afternoon conf+rec loser (2026-05-19 14:00, -$790) is NOT actually blocked even when gate=true -> gate keys on `bt` (decision bar, <14:00) while entry_time_et=14:00 (next-bar after pullback scan). So the gate is leaky and protects nothing OOS.
- Anchors: identical blocked vs unblocked (edge_capture IS 0/0, OOS -2124.5/-2124.5). Gate is orthogonal to the bear source-of-truth (all puts). Unblock does NOT regress anchors.

**Verdict: UNBLOCK.** Old-engine ratification (2026-06-17 IS_delta=+$468/OOS+$176) sign-FLIPPED under real-fills+managed-exits (classic L149/L172 stale-on-new-engine). The "superseded" justification was already void (`block_conf_lvl_rej_midday_afternoon` set false 2026-06-18, and it targeted REJ not REC anyway -- never a superset).

**Why:** J-directed target (2026-06-26) = trade validated set BOTH dirs; every block must justify itself on the CURRENT engine. This one no longer does.
**How to apply:** param diff = `automation/state/aggressive/params.json` `"block_conf_lvl_rec_afternoon": true -> false`. Don't re-cook -- evidence is filed. See [[project_direction_block_inventory]].
