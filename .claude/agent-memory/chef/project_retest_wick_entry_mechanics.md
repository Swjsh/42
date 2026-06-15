---
name: retest-wick-entry-mechanics
description: 8 sniper entry designs to eliminate retest-wick premium stops on BULLISH_RECLAIM (and BEARISH_REJECTION). Motivated by 2026-05-28 missed bull day. Kitchen should cook Design 6 first.
metadata:
  type: project
---

**Fact:** The engine enters BULLISH_RECLAIM on next-bar fill (bar N+1 open). In low-VIX slow-grind
(VIX 15-16), bar N+1 routinely wicks back to the reclaimed level, firing the -8% premium stop
before SPY resumes. 2026-05-28 (+$4.39 bull day): all 3 configs stopped at the retest wick.

**Why:** Entry on bar N+1 open puts the fill directly into the retest wick. The stop reference
is set from the post-retest-recovery open price, not the reclaim level itself.

**8 designs ranked by impact x implementability (filed 2026-05-31 as leaderboard #21):**

1. Design 6 (CANDLESTICK_QUALITY_GATE) — HIGHEST implementability, zero new code. Requires
   trigger bar to be hammer/marubozu or is_decisive_bar(body_ratio>=0.65). All primitives
   already in backtest/lib/filters.py. Screens out "contested reclaim" bars that produce wicks.
   **Cook this FIRST.**

2. Design 1 (LIMIT_AT_TRIGGER_CLOSE) — Fill at trigger bar close instead of next-bar open.
   Eliminates structural next-bar retest exposure. One param change in simulator_real.py.
   Combined with Design 6: highest expected WR of any combo.

3. Design 2 (RETEST_WICK_TOLERANCE) — Suppress premium stop for 1 bar post-entry IF bar
   closes above the reclaim level (healthy retest). Chart stop always active.

4. Design 5 (VOLUME_ABSORPTION_CONFIRM) — Wait for bar N+1 to wick to level AND close above
   it with vol >= 1.5x before entering at bar N+1 close. ORB watcher already implements this
   exact state machine. Port from orb_watcher.py.

5. Design 7 (LEVEL_TIERED_STOP) — Widen chart stop by level quality: star-3 gets 0.75 buffer
   vs flat 0.50 current. 3 lines, needs level_stars in BarContext.

6. Design 4 (CONSOLIDATION_ANCHOR) — Enter at consolidation base before breakout bar. High
   miss rate on V-launch days, research direction not near-term cook.

7. Design 3 (PRE_RIBBON_FLIP_LIMIT) — Enter on MIXED ribbon if strong green bar (vol>=2x,
   close at top 80%). Requires validator changes, higher false-positive risk.

8. Design 8 (RIBBON_STRENGTH_GATE) — Require >=3 prior consecutive BEAR bars before BULL flip.
   Blocks chop entries. Risk: may miss 4/29 or 5/04 if ribbon didn't have 3 prior BEAR bars.

**Critical falsification for any design:** If anchor days (4/29 +$342, 5/04 +$730) are blocked
or if edge_capture drops below 771, the design is REJECTED per OP-16.

**Key context:** BULLISH_RECLAIM is still DRAFT scope (OP-16 scope lock, 0/3 live J wins).
These designs apply symmetrically to BEARISH_REJECTION. The low-VIX bull-grind finding
motivates bull-reclaim fixes but the designs generalize.

**Files:**
- Proposal: strategy/candidates/2026-05-31-111020-sniper-entry-designs.md
- Leaderboard: #21
- Existing primitives: backtest/lib/filters.py (is_decisive_bar, is_hammer, is_bullish_marubozu)
- ORB watcher state machine analog: crypto/lib/ (ORB_RETEST_LONG implementation)

**Why:** 2026-05-28 single-day failure in a low-VIX grind regime. The regime (VIX 15-16, bull
slow grind) is different from J's confirmed anchor wins (VIX high, sharp reversal). Fix must
not break anchor days.

**How to apply:** When a cook task for BULLISH_RECLAIM entry improvement comes in, reference
this memory. Design 6 + Design 1 combo is the recommended first Kitchen cook. Edge_capture
floor check (>=771) is mandatory before any ratification.
