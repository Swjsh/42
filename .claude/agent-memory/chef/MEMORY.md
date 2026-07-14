# Chef Agent Memory

## DTE / exit-knob findings (2026-07-07 batch)
- [2DTE-ATM DTE override STAGED but HOLD](project_vwapcont_dte_override_atm_hold_2026_07_07.md) — DTE lever on LIVE ATM Safe-2 cell reproduces $28.90→$45.04 OOS (+56%) but HOLD: fails 2/6 OP-22 (WF 0.556; 2 much-worse Q) + loses 4/4 recent months + null p=0.0647 + sizing 2.33× breaks min-3-lot floor. Picker = heartbeat_core:1088 `expiry=_et_now()`. Wiring staged (params `j_vwap_cont_dte_override` + `_expiry_for_setup` + guard). FOOT-GUN: multiday scorecard is ITM-2, armed cell is ATM — re-run ATM + check RECENCY.
- [DYNAMIC stop LOSES to static — STATIC-IS-FINE](project_dynamic_stop_static_is_fine_2026_07_07.md) — J's "make 8% stop dynamic": every rule-based dynamic premium stop (ATR/IV/struct) loses OOS to a good fixed number; 2 "wins" = fat-tail settlement mirages; lone survivor degenerate (IV collapses to ~-0.061 const). Wider stop doesn't help more at longer DTE. Don't re-cook adaptive stops. Harness dynamic_stop_ab.py.
- [vwapcont walk-forward: STATIC justified, number stale](project_vwapcont_walkforward_static_justified.md) — WF re-opt beats current static -0.08/0.30 but LOSES to best-fixed -0.06/0.40 (adaptation tax); one-time re-pick is the fix not re-opt machinery. FOOT-GUN: always add best-fixed-cell comparison when WF "beats static". Harness walkforward_optimizer.py.
- [WEEKLY (1-2 DTE) beats 0DTE — C3 nail is 0DTE artifact](project_weekly_dte_not_0dte_2026_07_07.md) — same vwap_continuation ITM-2, only DTE varies: OOS monotone $36→$59→$66 (+82%); null crushed; drop3 near mean; cross-family confirm. held%~0 = lower-theta-on-entry not hold-days. DATA-GATED on 3-4DTE OPRA backfill. NEW capability, not a params knob. Leaderboard ★★.

## Killed structural levers (don't re-cook)
- [CONFLUENCE_MATRIX killed — 5th confluence kill + MTF refutes J](project_confluence_matrix_killed.md) — no lens subset captures J's 3 winners correct-side; J's edge is DIRECTIONAL/regime not 5m confluence. MTF: more-TF agreement → SMALLER reaction (corr -0.267). Harness confluence_matrix.py.
- [LEVEL_MEMORY: PERCEPTION yes, SIGNAL no-lift](project_level_memory_perception_layer.md) — stateless multi-day level+role-flip engine sees J's 750.92 role-flip but naive rejection ENTRY beats random-ENTRY not random-LEVEL; reusable as veto/input, don't re-cook naive-rejection entry. level_memory.py + 5 guards.
- [Ribbon-rejection DEBIT SPREAD KILLED](project_ribbon_rejection_spread_killed.md) — full-window +$131-228/spread but MIRAGE (OOS neg all 9, long null +$132, mostly bull not bear, thin N). 4th ribbon-rejection entry kill. FOOT-GUN: don't trust positive full-window mean w/o null.
- [Ribbon-wick selective rescue KILLED](project_ribbon_wick_selective_killed.md) — 3rd kill; combined +$2.03 but n=29 underpowered + drop3 -$408 fat-tail. VETO/exit only, don't re-cook entry rescues.
- [SHORT level-rejection KILLED](project_short_level_rejection_killed.md) — counter-ribbon resistance-fade beats NO null; killed 3 ways. No historical named-level store (live snapshot only).
- [Volume-profile/VPVR — DON'T build](project_volume_profile_data_verdict.md) — POC FAILED (loses to random null); SPY volume col MIXED (thin IEX pre-2026-03, SIP after, 44x seam); SIP-backfill FIRST if revisited.

## Reusable infra / capabilities
- [Futures deterministic tick BUILT dry-run-green](project_futures_tick_built_2026_07_07.md) — futures_heartbeat_core.py + futures_exit_manager.py + 17 guards; ARM gate fails-safe (dry unless FUTURES_ARMED=1 AND bp>0). ONE FLIP: J provisions + arms. Not scheduled.
- [structure-veto anchor safety + guard](project_structure_veto_anchor_safety.md) — veto (block dir-vs-classify_trend; range/unknown=no-veto) SAFE for all 3 PUT winners; 5/04 safe ONLY because range=no-veto, NEVER require-downtrend. Guard test_structure_veto.py 29/29. Prod diff = engine_cli.decide_payload. OOS Δ=$0 (robustness not P&L).
- [End-to-end wired map + autonomy scorecard](project_end_to_end_wired_2026_06_26.md) — ~75% loop unattended; 2 blockers to 100% (ARM=J + APPLY hop never fired). Blueprint markdown/planning/AUTONOMY-ROADMAP.md.
- [Research-kitchen subsystem map](project_research_kitchen_subsystem_map.md) — seeder→queue→daemon→candidates→reviewer→leaderboard; reviewer globs only *chef-nemo*.md (Chef files skip auto-review); TZ bugs in grade_decisions/audit_scheduled_tasks. task_health_et.ps1 authoritative.
- [Named-level trigger scope](project_named_level_trigger_scope.md) — 3 WATCH_ONLY counter-ribbon detectors; real-fills via simulate_trade_real. BLOCKER: OPRA cache stops 06-18.

## Setup characterizations
- [Direction-block inventory](project_direction_block_inventory.md) — trade validated set BOTH dirs; 15-gate battery (7 bull-suppressors); lever = `filter_10_min_triggers_bull` (params, Safe=2/Bold=1); most bull-blocks ratified on OLD engine = stale.
- [Direction-block audit SYNTHESIS](project_direction_block_audit_synthesis.md) — 3-4 stale BEAR blocks unblock + VIX_BULL_HARD_CAP 18→22; KEEP 7; most "missing bull trades" NOT false-negatives (vwap bull already side=both).
- [v14e structural split](project_v14e_structural_split.md) — score=11 all bull; 6-10 short/bear. Short +$1,492 WR58.5%; bull -$3,642. Bear-only gate is the fix.
- [bullish_watcher no confidence tier](project_bullish_watcher_no_conf.md) — all 289 obs medium; n_triggers>=3 for "high" unreachable. PM 13-15h WR65.6% vs AM 43.9%; too thin (N=61).
- [ORB runner-dependent](project_orb_characterization.md) — runner hits = 165% of P&L; narrow OR (<=2.00) WR88.1% vs wide 48.9%; long WR69.3% vs short 44.4%; regime-sensitive.
- [Retest wick entry mechanics](project_retest_wick_entry_mechanics.md) — 8 designs for next-bar retest-wick stop on BULLISH_RECLAIM; Design 6 (candle quality gate) first; 1+6 combo best.

## Block re-validation series (CURRENT real-fills engine; 3 UNBLOCK, 5 KEEP, 1 INCONCLUSIVE)
- [entry_body_gate BEAR stale → UNBLOCK](project_entry_body_gate_bear_stale.md) — #13 doji block; delta -$200 (removes net-winner set); 0.20→0.0.
- [require_bearish_fill_bar → UNBLOCK](project_fill_bar_gate_reval.md) — #7 look-ahead; removed-set +$917 IS suppresses winners; true→false (Bold). Method = removed-set net-PnL by identity, not aggregate (cascade L15).
- [midday_trendline_gate → UNBLOCK](project_midday_trendline_gate_revalidated.md) — #10; 102 removed net +$849/+$8.33tr; true→false. Thin edge, 100%-bear.
- [block_conf_lvl_rec_afternoon → UNBLOCK](project_block_conf_lvl_rec_afternoon_revalidated.md) — #12 Bold; costs +$779 IS, protects $0 OOS; true→false.
- [VIX_BULL_HARD_CAP → UNBLOCK](project_vix_bull_hard_cap_revalidated.md) — filter 9 (=18); suppresses 2 bull winners; params bull_hard_cap 18→22 + filters.py:805.
- [block_bull_1100_1200 → KEEP](project_block_bull_1100_1200_revalidated.md) — #5; 5/5 midday bulls are -50%-stop losers; block earns keep.
- [bull_min_triggers floor → KEEP](project_bull_min_triggers_floor_keep.md) — Safe bull>=2; unblock adds 72 losers -$3,421; KEEP. Lever = filter_10_min_triggers_bull.
- [F8 bull-VIX gate → KEEP](project_f8_bull_vix_gate_kept.md) — filter 8; unblock admits 3 net-loser bulls -$892; KEEP. FOOT-GUN: P&L field is `dollar_pnl` NOT `pnl_dollars`.
- [vix_bear_hard_cap → KEEP](project_vix_bear_hard_cap_revalidated.md) — #15 (VIX>=23); removed bears net losers even at -50% cap; KEEP.
- [OP-16 bull-scope lock → KEEP](project_bull_scope_lock_revalidation.md) — unblock adds 25 ribbon bulls +$5,586 AGG but drop-top5 -$1,573 (C4 mirage); validated vwap bull already side=both.
- [block_elite_bull → INCONCLUSIVE](project_block_elite_bull_revalidate.md) — unblock +$1602 but 74%-one-trade fat-tail; gate stays, next = tail-discriminator carveout.
