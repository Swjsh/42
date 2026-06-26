---
name: vix-bear-hard-cap-revalidated
description: vix_bear_hard_cap (Safe gate 15, blocks BEAR/P when VIX>=23) re-validated KEEP under the CURRENT real-fills+managed-exit engine 2026-06-26
metadata:
  type: project
---

vix_bear_hard_cap=23.0 (Safe gate #15, blocks BEAR/P entries when VIX>=23) — re-validated **KEEP** under the CURRENT engine 2026-06-26. Originally ratified 2026-06-18 on the OLD engine (static OTM-2 + TIGHT -10% bear premium stop). The stated original mechanism (high IV -> -10% stop misfires) would have been undone by the new -50% wide cap — but it was NOT.

**Why KEEP:** real-fills A/B (`run_backtest --real-fills`, params_overrides path, initial_equity=2000 -> OTM-2, premium caps -0.50 both sides, chandelier trailing 0.125, tp1 0.50@0.667) over 2025-01-02..2026-06-16, blocked(cap=23) vs unblocked(None):
- FULL: cap removes **11 bears worth -$144.92 (-$13.17/tr)**, block delta bear P&L +$144.91, bear WR 0.25 vs 0.236, **all-strategy sharpe 0.040 vs 0.019** (unblocking HALVES sharpe).
- IS (..2026-02-27): 8 removed @ -$112.11. OOS (2026-03-02..): 3 removed @ -$32.80. removed-trade P&L negative in **3/3 windows**.
- The high-VIX bears are net losers EVEN with the -50% wide cap + managed exits -> the new exit structure did NOT flip them to winners. **Rare bear-direction block whose mechanism survives the chart-stop-primary migration** (most OLD-engine blocks are stale; this one is not).
- Anchor-no-regression PASS: 4/29, 5/01, 5/04 all had VIX<23 so cap removes none (delta=0, 0 anchor bear trades fire in either arm in this Safe gate-path config).

**How to apply:** when asked to prune/re-validate Safe direction-blocks, this one is DONE — KEEP, no param change. UNBLOCK diff would be `vix_bear_hard_cap: 23.0 -> null` but is NOT warranted (adds 11 losers for -$145, halves sharpe). Caveat: n is thin (11 lifetime blocked, 3 OOS) — sign robust, magnitude small (~$13/tr); a high-VIX-heavy future regime warrants a recheck. Candidate: strategy/candidates/2026-06-26-113500-vix-bear-hard-cap-revalidation.md. Evidence JSON: backtest/_chef_vix_bear_cap_result.json. Contrast with [[direction-block-inventory]] (this is the one stale-looking block that re-validated positive). Note real-fills A/B harness pattern: pass full Safe config via `params_overrides` + `initial_equity` so `_params_to_kwargs` does per-tier strike pick (line 363); need repo-root on sys.path for `crypto.lib.strike_selection` import.
