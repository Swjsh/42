---
name: midday-trendline-gate-revalidated
description: midday_trendline_gate re-validated under CURRENT engine (2026-06-26) — block is STALE, recommend UNBLOCK (sign-flip from OLD-engine ratification)
metadata:
  type: project
---

`midday_trendline_gate` (gates.py #10, Safe=true, params.json `midday_trendline_gate`) blocks entries whose ONLY trigger is `trendline_rejection` in 11:30-14:00 ET. RE-VALIDATED 2026-06-26 under the CURRENT engine → recommended **UNBLOCK** (candidate `strategy/candidates/2026-06-26-113702-unblock-midday-trendline-gate.md`, leaderboard RV row).

**Why:** Ratified on the OLD engine (OTM + premium_stop −0.08/−0.10, NO chandelier) where the doc cites −$8.6/tr over 307 OOS trades. Under the CURRENT LIVE Safe engine (real OPRA fills, chart-stop −0.50 catastrophe cap, chandelier trail 0.125, tp1 0.50@0.667, runner 2.5×, OTM-2 @ $2K, 30% cap) the 102 removed trades NET **+$849, +$8.33/tr, WR 71%** — a near-perfect SIGN-FLIP. The managed-exit structure converted theta-bled OTM puts into managed winners. BLOCK_DELTA = IS −$371 / OOS −$40 / recent(05-19..06-25) +$23; sub-windows 3/4 hurt.

**Key facts (don't re-cook from scratch):**
- The removed cohort is **100% PUTS (0 calls)** in 2025-01..2026-06 data — this is functionally a stale BEAR-block, NOT a bull block. Unblocking advances "validation is the only scope" (nothing-validated-blocked) but does NOT open a bull setup.
- Anchor-no-regression PASS: gate fires only on SECONDARY same-day trendline-only re-entries, never J's primary level/reclaim anchor trades. Unblocking ADDS bear pnl, regresses nothing.
- Edge is THIN (+$8.33/tr, portfolio block_delta −$371 over 16 mo) — low-magnitude "remove a drag", not a big edge. Confidence 7/10.
- A/B script (read-only, reusable): `backtest/safe_midday_trendline_gate_revalidate_current_engine.py`. Mirrors live config; flips `midday_trendline_gate` ON vs OFF.
- The OLD `safe_bull_midday_gate_ab.py` tests a DIFFERENT thing (11:00-12:00 bull-only block, old −0.08 config) — don't reuse it for this gate.

**How to apply:** This confirms the [[project_direction_block_inventory]] thesis that OLD-engine-ratified blocks go stale under chart-stop-primary + managed exits. When re-validating any block ratified pre-2026-06-18, mirror the LIVE managed-exit config (−0.50 caps + chandelier), not the OTM+premium-stop bracket. Param diff to unblock: `midday_trendline_gate: true → false` (params.json only; J ratifies, never edit yourself).
