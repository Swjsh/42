# Strategy Hunt Log

Bar to clear: positive expectancy AND OOS WF ≥ 0.5 AND profitable in ≥ 4 of 6 quarters AND ≤ 60% P&L concentration in any single quarter.

## 2026-06-03 08:31 ET — FIRST WINNER clears the bar

**v14_enhanced exit config (= leaderboard #12 V14E_PARAM_SWEEP_26K)** — CLEARS all four:
- Quarters: 25Q1 +2,247 / Q2 +172 / Q3 +4,834 / Q4 +8,244 / 26Q1 +6,273 / 26Q2 +4,831 → **6/6 positive, 31% max concentration** (robust across regimes, not one lucky quarter).
- **OOS walk-forward 2.07; real-fills $42,102 (> BS-sim $26,601).** RATIFICATION_READY for 11 days — blocked only on the manual ratification gate J just told me to stop waiting on.
- Exit params: `tp1=0.30, runner=2.5, profit_lock=0.05/0.10` (vs live v15.3 `profit_lock=0.20`). Orthogonal to v15.3's ribbon entry gate → should compound.
- **Numbers are at grinder size (large); the real account is 3-5 contracts — the per-quarter EDGE holds, the dollar figure scales down. Never been live (that's why accounts are down — they ran the older exits).**
- ACTION: ship after today's 16:00 close (sync `params.json` + both `heartbeat.md` + `filters.py`, run pytest). NOT pre-open — Rule 9 timing.

Secondary (does NOT cleanly clear):
- sniper_stage2: in-sample $40,657 6/6 — but OOS is regime-concentrated (#15: 2026-Q1 = 105% of OOS P&L). Fails OOS robustness. Blocked-pending-anchor.
- vwap_stage1: +$588, 4/6 quarters, 53% conc — robust but small. Keep accumulating.
- overnight_grinder (current production ribbon exits): +$1,005 but 1/6 quarters (55% conc) — confirms current exits are break-even/regime-thin.

Grinders running: bullish, sniper_stage2, vwap, sweep_missed. Hunt continues for something that beats v14e robustly.
