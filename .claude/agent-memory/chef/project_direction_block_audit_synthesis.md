---
name: direction-block-audit-synthesis
description: 2026-06-26 full direction-block audit synthesis — the matrix, what unblocks, what J is actually missing. TARGET STATE = trade validated set both dirs, validation is the only scope.
metadata:
  type: project
---

J-directed 2026-06-26 TARGET STATE: per account the engine trades EXACTLY the validated setup set in BOTH directions. Direction is NOT a scope; validation status is. Every direction-block justifies under the CURRENT engine (real OPRA fills + per-tier strikes + chart-stop-primary + -50% caps + chandelier managed exits) or is removed.

**Why:** J feels we're missing trades. The audit answers which are stale-block false-negatives vs genuinely unvalidated vs not-built.

**How to apply:** Before re-cooking any direction block, check this synthesis + the per-block memories. The 13 re-validations are DONE.

THE BIG STRUCTURAL FINDING: most of J's "missing trades" are NOT bull false-negatives. The stale blocks that unblock tonight are predominantly BEAR blocks (midday_trendline_gate, entry_bar_body_pct_min bear, require_bearish_fill_bar Bold). On the BULL side, the suppressed setups SPLIT: (a) vwap-family bull = VALIDATED and ALREADY running side=both (j_vwap_cont_side/j_vix_dayside_side both already "both" in params — NOT suppressed by OP-16, only their enabled=true flip is outstanding = J's call); (b) ribbon BULLISH_RECLAIM = FAILS current engine (drop-top5 -$1,573, posQ 2/6, recent WR 0.25) → OP-16 lock KEEPS.

UNBLOCK NOW (3 stale, all evidence-backed, ship after-hours):
- midday_trendline_gate true->false (params.json) — BEAR, sign-flipped +8.33/tr, removed set +$849/WR71%
- entry_bar_body_pct_min 0.20->0.0 (params.json) — BEAR doji gate, removes net-winner set, direct delta -$200, amputates 5 fat-tail winners
- require_bearish_fill_bar true->false (aggressive/params.json, Bold) — BEAR look-ahead, removed set +$917 IS net-winner; CAVEAT OOS still leans gate's way n=5, conf 6
- block_conf_lvl_rec_afternoon true->false (aggressive/params.json, Bold) — bull/C, IS +$779 cost / OOS $0 protection (leaky gate keys on bt<14:00)
- VIX_BULL_HARD_CAP 18->22 (BOTH params.json bull_hard_cap AND filters.py:805 — drift if not paired) — bull/C, sign-flipped, suppresses 2 winners (+$205,+$266), n=2 thin

KEEP (still block losers under current engine):
- filter_10_min_triggers_bull=2 (Safe) — unblock costs -$26,572; 47 single-trig bulls -$577/tr
- VIX_BULL_LOW_THRESHOLD f8 (Safe, hardcoded) — unblock -$892, 3 bull losers
- block_bull_1100_1200 (Safe) — 5 surviving midday bulls all -50%-stop losers -$1,299
- block_level_rejection (Safe) — counter-trend resistance-fade PUTs, +$1,843, killed 3 ways prior
- vix_bear_hard_cap=23 (Safe) — high-VIX bears net losers even w/ wide cap, +$144.91 bear, halves sharpe if unblocked
- block_elite_bull (both) — INCONCLUSIVE: unblock +$1,602 AGG but 74%-one-tail mirage; needs narrowed loser/tail carveout, not blind unblock
- OP-16 ribbon BULLISH_RECLAIM lock — fails OP-22 on current engine

BUILD (validated/promising, not yet expressed live):
- Flip enabled=true on the 4 DORMANT validated setups: vwap_continuation (side=both), vwap_reclaim_failed_break (both validated), vix_regime_dayside (both), gap_and_go (both validated). These are J's standing-authorization SHIP candidates — the real "missing trades."
- Level-bounce / named-level trigger (RIBBON-LAG counter-ribbon) — BLOCKED on OPRA cache gap (stops 06-18, no anchor option bars). Real-fills harness exists (simulate_trade_real driven like mass_grind_vwap).
