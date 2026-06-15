---
name: project_orb_characterization
description: ORB watcher characterization — runner-dependent (+165% of P&L from runners), 10:00h dominates, long WR=69.3% vs short 44.4%, narrow OR sharply better, regime-sensitive (2026-Q2 = 105% of P&L).
metadata:
  type: project
---

ORB watcher is the fleet's top performer (+$7,161, N=391). Key structural facts:

**Runner dependence:** runner_hit (N=120) contributes +$11,795 = 164.7% of total P&L. Stops (-$7,136) and tp1_then_be_stop (+$2,343) roughly cancel. The ORB watcher is profitable IFF it catches genuine breakouts that run.

**Time concentration:** 83 of 120 runner hits fire in the 10:00h window (+$8,852, 75% of runner P&L). The ORB mechanism is strongest in the first 30-60 minutes after the ORB window closes (09:30-10:00 ET).

**Long vs short:** Long WR=69.3% (+$7,378) vs Short WR=44.4% (-$218). Short ORB is near-zero drag. The market's structural upward bias makes bear ORB breakdown signals less reliable.

**OR range:** Narrow OR (≤$2.00 SPY): WR=88.1%, +$4,597, avg=+$32.1. Wide OR (>$2.00): WR=48.9%, +$2,781, avg=+$21.2. Narrow ORs concentrate early-session energy.

**Regime sensitivity (CRITICAL):** 2025-Q1=-$624, 2025-Q2=-$18, 2025-Q3=+$1,612, 2025-Q4=-$378, 2026-Q1=-$982, 2026-Q2=+$7,551. 2026-Q2 alone = 105% of total P&L. The ORB's "STABLE" status is current-regime-dependent. If SPY enters a sustained bear or chop regime, ORB will turn negative.

**Next research items for ORB:**
1. OR-range gate (max_or_range=2.00) — would filter ~45% of long trades, sharply improving quality
2. Direction filter (long-only) — removes short drag (-$218, 30% of observations)
3. VIX regime filter — understand what regime conditions ORB thrives in

**Filed:** `analysis/watcher-fleet-analysis-2026-05-21.md`
