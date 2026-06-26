---
name: structure-veto-anchor-safety
description: Structure-veto (block direction-vs-classify_trend) is SAFE for all 3 OP-16 PUT winners on all timeframes; 5m-sameday is the best veto TF
metadata:
  type: project
---

Structure-veto safety characterization for OP-16 source-of-truth trades (2026-06-26).

**Veto rule tested:** block BEAR/P when classify_trend==uptrend; block BULL/C when classify_trend==downtrend; range/unknown=NO veto. Pure VETO (only removes trades).

**Decisive result — NO winner is blocked on ANY timeframe (5m-trailing, 5m-sameday, 15m).** Veto is SAFE as-is; no narrowing required for anchor preservation.
- 4/29 710P: classify=downtrend(5m)/downtrend(15m) = WITH-structure, not blocked.
- 5/01 721P: classify=downtrend(5m)/range(15m) = with-structure/no-veto, not blocked.
- 5/04 721P: classify=RANGE on all 3 TFs (chop/reversal-catch) = no-veto by design, not blocked. KEY: 5/04 is NOT a clean downtrend — it's a range-bound rejection; the veto stays safe ONLY because range=no-veto (do-not-over-filter). If the rule ever tightens to "must be confirmed downtrend to allow a PUT", it would block 5/04 (+$730). DO NOT add a require-with-trend variant.

**Loser coverage (weak, as expected for a coarse veto):** 1/4 losers caught per TF.
- 5m (trailing & sameday): catches 5/07 734C (downtrend, counter-trend bull) — the exact 2026-06-26-class wrong-way bug. Misses 5/06 730P (downtrend = with-structure bear loss; the veto can't catch with-structure losers).
- 15m: catches 5/05 722P (uptrend, counter-trend bear) instead. Different loser, also 1/4.
- 5/07 737C (11:14) reads uptrend = with-structure bull => NOT blocked by either TF (correct: veto never over-filters with-structure trades even when they lose).

**Best TF = 5m-sameday.** Catches the headline counter-trend-CALL loser (734C), preserves all 3 winners, matches the live engine's intraday read. 15m only catches a different single loser. Neither dominates on loser-recall, but 5m aligns with the 06-26 wrong-way-PUT failure mode.

**Tool (read-only, no lib edit, gym 89/89 intact):** `backtest/structure_veto_anchor_check.py` — loads spy_5m CSV up to each anchor entry_et, builds Bars, runs classify_trend + analyze_structure on 5m-trailing/5m-sameday/15m. classify_trend (label run) and analyze_structure (BOS/CHoCH state machine) sometimes disagree (e.g. 4/29 classify=downtrend but structure=uptrend on 5m) — the VETO rule keys on classify_trend per the spec; analyze_structure trend is a cross-check only.

**Bottom line for tonight's audit:** structure-veto can ship as a pure safety veto without regressing edge_capture (all 3 winners kept, EC delta on winners = $0). It is a thin loser-filter (1/4), not a profit engine. Pair with the engine reading trend from price-structure (this module) instead of the lagging EMA ribbon.

---

**REAL-FILLS A/B VERDICT (2026-06-26) = IMPROVE_SHIP (confidence 7).** Wired classify_trend(5m-sameday) into the engine entry path via monkey-patch on evaluate_bearish_setup + evaluate_bullish_setup (production untouched); BASE=current prod (real OPRA fills + V15 managed exits) vs CANDIDATE=BASE+veto, full 2025-01-02..2026-06-18.
- **Anchor PASS (cardinal gate):** edge_capture $780 base = $780 candidate, delta $0. NO winner blocked. 5/04 +$730 preserved (RANGE=no-veto).
- **Full:** P&L +7,555 -> +8,138 (**+$583**), sharpe_daily 4.340 -> 4.728 (+9%), final_score 3,385 -> 3,688 (+303), maxDD flat -2,273. Removes **2 wrong-way LOSERS net -$574** (bear PUTs into a confirmed 5m uptrend = the 06-26 wrong-way class), 0 winners. 2/6 Q positive, 0/6 negative.
- **HONEST CAVEAT — OOS-2026 delta = $0** (n unchanged 21->21). 107 bars vetoed full but only 2 -> a removed PLACED trade; the other 105 are ALREADY excluded by quality-lock/cap/escalation gates. So this is primarily a ROBUSTNESS/SAFETY veto (provably kills a known wrong-way class, never a winner), NOT a P&L engine. Entire +$583 is IS-concentrated in 2025Q1.
- **Metric foot-gun:** the metrics object exposes `sharpe_daily` NOT `sharpe` (getattr(m,'sharpe') returns 0.000 silently). And the oracle assert (GAMMA_ENGINE_SCORE_ASSERT) MUST be set to 0 BEFORE orchestrator is imported (the veto sets blocker 999 -> orchestrator-vs-engine score_bar mismatch trips the assert otherwise).
- **Tool (reusable, read-only):** `backtest/autoresearch/structure_veto_ab.py`; output `analysis/recommendations/structure-veto-ab-2026-06-26.json`; candidate `strategy/candidates/2026-06-26-160000-structure-veto-direction-vs-trend.md`. Ship = add params key `structure_veto_enabled` + wire classify_trend into orchestrator entry path replacing the lagging EMA-ribbon trend read. Gym 97/98 PASS before+after.

**SHIP DECISION (2026-06-26): SHIP** (clears OP-22 bar — improves real-fills P&L IS, OOS flat not negative, zero source-of-truth regression, removes the wrong-way class). **CRITICAL WIRING CORRECTION:** the AB monkey-patched the BACKTEST path (`orchestrator.evaluate_bearish_setup`/`evaluate_bullish_setup`). The LIVE engine does NOT call those — `heartbeat_core.py` routes through `engine_cli.decide_payload` -> `score_bar` + `evaluate_gates` (verified). So the validated result is BACKTEST-path evidence; live wiring must reproduce the IDENTICAL predicate at the engine_cli decision boundary or it's a different change (L153 trigger->live-category mapping; OP-16 sim-accuracy gate). EXACT live insertion point: `backtest/lib/engine/engine_cli.py` `decide_payload`, immediately BEFORE line 553 `base["verdict"] = "ENTER_BEAR" ...` (after all 15 gates pass) — compute `classify_trend` on the same-day 5m swings from the payload's `spy_df` up to `ctx.bar_idx`, and if `_veto_side(winning_side, trend)` set `base["verdict"]="SKIP_STRUCTURE_VETO"`, `base["gate"]={gate_id:"structure_veto",...}`, return. Gate behind `gate_params["structure_veto_enabled"]` (engine default False so OFF until params flips it). heartbeat_core already passes `spy_df` and adds the key to GATE_KEYS. After wiring: re-run `replay_heartbeat_core.py` for live-path parity BEFORE arming (REVOKE-note, not a permission gate). Better long-term home = a new gate in `gates.py` GATE_ORDER so it lives with the other 15 (needs spy_df in GateContext, already present). Do NOT tighten to require-confirmed-downtrend (blocks 5/04 +$730).
