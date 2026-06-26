---
name: bull-scope-lock-revalidation
description: OP-16 BULLISH_RECLAIM setup-scope lock re-validated on CURRENT real-fills engine = KEEP. Ribbon bull setup fails drop-top5; vwap bull edge is the only valid one and is already side=both.
metadata:
  type: project
---

OP-16 setup-scope lock ("BULLISH_RECLAIM stays DRAFT") re-validated 2026-06-26 on the CURRENT engine (real OPRA fills + production params + managed exits, account_equity=$2,000 Safe-2) → **KEEP, still justified.**

**Why:** A/B `enable_bullish=False` vs `True` over 2025-01-02..2026-06-18 (full OPRA coverage). UNBLOCK adds 25 ribbon BULLISH_RECLAIM trades = +$5,586 AGG / sharpe 0.046→0.156 — looks great until OP-22 cuts: **drop-top5 = -$1,573** (the entire edge is 2025Q3 +$7,308/n9/WR0.89); **positive_quarters 2/6**; OOS(2026+) mean only +$35; **recent ≥2026-05-19 = -$1,247/n4/WR0.25** (bleeding in current regime); maxDD -$910 worse. Classic C4 concentration mirage, NOT a per-trade option edge. Don't re-cook — unblocking just trades more on a one-quarter spike.

**Anchor-no-regression PASS (structural):** All 6 OP-16 anchor-day engine trades are PUT/BEARISH_REJECTION; the bull setup fires on NONE of them. `delta_edge_capture = 0.0`, byte-identical both arms. The bull-scope toggle is orthogonal to the bearish source-of-truth.

**THE KEY DISTINCTION (don't conflate these two bull paths):**
1. **Ribbon BULLISH_RECLAIM** (orchestrator `enable_bullish`, generic OTM ladder) = the FAILING setup OP-16 correctly suppresses (drop-top5 negative).
2. **VWAP-family bull side** (the ITM+tight+managed profile) = the VALIDATED one: vwap_continuation scorecard `j-daily-pattern-LIVE.json` has `both_dirs_positive=True`, **drop_top5_mean +$24.45** (robust). And it's ALREADY `j_vwap_cont_side=both` + `j_vix_dayside_side=both` in params.json — NOT put-locked, NOT suppressed by OP-16. So the validated bull edge already runs both-dirs; only its `enabled` flip is J's call.

**Caveat:** raw engine edge_capture on anchor days is polluted by a pre-existing engine↔J 4/29 divergence (engine takes -$1,065/-$300 bear trades where J took +$342 710P). Identical in both arms → doesn't affect this verdict, but means the J-edge floor number off this engine is unreliable on 4/29.

A/B script: `backtest/autoresearch/_chef_bull_scope_ab.py`. Scorecard: `analysis/recommendations/chef-bull-scope-ab-2026-06-26.json`. Candidate: `strategy/candidates/2026-06-26-143000-bull-scope-lock-revalidation.md`. Note: `run.py --real-fills` runs orchestrator DEFAULTS not prod params — must use `_params_to_kwargs(params, account_equity=...)` to apply production config. See [[direction-block-inventory]].
