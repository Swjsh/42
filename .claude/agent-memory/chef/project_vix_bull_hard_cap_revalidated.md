---
name: vix-bull-hard-cap-revalidated
description: VIX_BULL_HARD_CAP (filter 9) re-validated 2026-06-26 on the CURRENT engine — verdict UNBLOCK (stale, now suppresses winners). Do not re-cook.
metadata:
  type: project
---

RESOLVED 2026-06-26: `VIX_BULL_HARD_CAP` (filter 9, hardcoded `filters.py:805` =18.0 + `params.json#vix_entry_thresholds.bull_hard_cap`=18.0) re-validated on the CURRENT engine → verdict **UNBLOCK** (raise 18.0→22.0). See [[direction-block-inventory]] (this was its "re-validate first / weakest evidence" flag).

**Why:** Ratified 2026-06-17 on the OLD engine (OTM + −8%/−10% premium-stop bracket) where VIX-18-22 bull calls lost. On the CURRENT engine (real OPRA fills + −50% catastrophe cap both sides + chart-stop-primary + managed exits + Safe $2K cap-admission) the **sign flipped**: the block contributes **−$471 FULL and −$471 OOS** — it suppresses 2 confirmed bull WINNERS: `2026-04-09` +$205 (VIX ~20.5), `2026-04-22` +$266 (VIX ~19.2). Both inside the 18-22 band. Textbook "gate that blocked a losing OTM config now blocks a winner under ITM+managed exits."

**Anchor:** EC INVARIANT (−1379 both BASE/CAND); every J source-of-truth day delta=$0 (gate is bull/18-22-VIX, anchors are bear/sub-cap). No bearish regression. So the decision is EC-neutral; the only delta is +$471 aggregate.

**How to apply:**
- The re-validation A/B is `backtest/autoresearch/vix_bull_hardcap_revalidate.py` — reusable TEMPLATE for re-validating ANY direction-block on the current engine. It uses `autoresearch.runner.run_with_params` (the params-driven path that reaches the engine + does cap-admission) with the CURRENT-engine BASE dict (premium_stop_pct_bear/bull=−0.50, tp1 0.50@0.667, runner 2.50, all live gates ON, vix_bull_max patched via `_patched_filter_constants`). DO NOT use the old `vix_bull_max_ab.py` — its BASE is the stale −10/−8 bracket (wrong engine).
- Candidate write-up: `strategy/candidates/2026-06-26-vix-bull-hard-cap-revalidate.md` (leaderboard #22, conf 8/10, PROMISING-UNBLOCK).
- To unblock (J ratifies, REVOKE-only): `params.json#vix_entry_thresholds.bull_hard_cap` 18→22 **AND** `filters.py:805 VIX_BULL_HARD_CAP` 18→22 (hardcoded, NOT in params audit — both move together or they drift) **AND** heartbeat.md filter 9 `VIX<18`→`VIX<22` + cache refresh 18.00→22.00.
- Gym green before+after (97/98, overall_pass=True). Caveat = n=2 (thin, but the original ratification was also n_oos=1; the sign flip is the load-bearing finding, not the magnitude).

**Pattern for the other stale bull-blocks** (block_elite_bull VIX[0,25), block_bull_1100_1200, bull_min_triggers=max(2,..) floor): same method — copy the BASE dict, flip the one knob, check for suppressed winners on the current engine. Most were ratified pre-2026-06-18 chart-stop flip or on BS-sim.
