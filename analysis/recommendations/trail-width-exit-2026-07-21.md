# TRAIL-WIDTH / TP1-SIZE exit A/B -- real-fills anchor (2026-07-21)

Generated 2026-07-21T23:34:06.847359. Runner: `backtest/tools/trail_width_exit_ab.py`. Pre-reg: `analysis/recommendations/trail-width-exit-prereg-2026-07-21.json`.

**Control shape** (`strategies.RIBBON_RIDE.exit.to_dict()`): `{'premium_stop_pct': -0.2, 'tp1_premium_pct': 1.0, 'tp1_qty_fraction': 0.667, 'profit_lock_mode': 'trailing', 'runner_target_pct': 99.0, 'trail_pct': 0.15, 'profit_lock_arm_pct': 0.05, 'stop_mode': 'structure', 'catastrophe_stop_pct': -0.5, 'profit_lock_arm_scope': 'post_tp1'}`

Population: 113 real-fills positions (84 recoverable trigger_level), 11 trading days, 2026-06-26..2026-07-17, arms=['safe-1', 'safe-3', 'risky-1', 'risky-3', 'safe-2', 'bold-2']. CONTROL total = $-947.43.

## Reconciliation vs the frozen structure-stop-reference-level NO-SHIP

structure-stop-reference-level-2026-07-20.json rejected widening the structure-stop REFERENCE LEVEL (trigger-exact/zone-boundary/none -- WHERE the chart-stop is anchored). Every candidate in THIS study still uses trigger-exact recovery (byte-identical to that study's REF-EXACT), varying only trail_pct/tp1_qty_fraction/tp1_premium_pct -- a disjoint knob. That axis is not re-opened here.

## Prior evidence on this axis (synthetic population, cited not reused)

analysis/recommendations/exit-variant-ab-wider-trail25-2026-07-17.json already tested trail_pct=0.25 vs 0.15 on a much larger SYNTHETIC detector-fired population (n=188, IS2025+OOS2026YTD) and found -$813.30 aggregate, FAIL on every regime-conditioned gate. Cited as prior evidence to reconcile against; not this study's population (this study uses the REAL-FILLS anchor per task instruction).

## Candidates

| id | trail_pct | tp1_qty_fraction | tp1_premium_pct | n | control $ | candidate $ | agg delta | gate1 agg | gate2 days | gate3 drop-best1 | gate4 OOS | verdict |
|---|--:|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|:--:|:--:|
| TRAIL-20 | 0.2 | 0.667 | 1.0 | 113 | $-947.43 | $-1,097.78 | $-150.35 | False | False | False | False | **CONTROL_HOLDS** |
| TRAIL-25 | 0.25 | 0.667 | 1.0 | 113 | $-947.43 | $-584.38 | $+363.05 | True | False | True | True | **CONTROL_HOLDS** |
| TRAIL-30 | 0.3 | 0.667 | 1.0 | 113 | $-947.43 | $-778.98 | $+168.45 | True | False | True | False | **CONTROL_HOLDS** |
| TP1Q-050 | 0.15 | 0.5 | 1.0 | 113 | $-947.43 | $-997.43 | $-50.00 | False | False | False | False | **CONTROL_HOLDS** |
| TP1Q-033 | 0.15 | 0.333 | 1.0 | 113 | $-947.43 | $-1,935.58 | $-988.15 | False | False | False | False | **CONTROL_HOLDS** |
| RIDE-BUNDLE | 0.3 | 0.5 | 0.5 | 113 | $-947.43 | $-1,568.98 | $-621.55 | False | False | False | False | **CONTROL_HOLDS** |

## Give-back accounting (honesty requirement -- both sides of the ledger)

| id | extra captured on beats | n beats | extra given back on losses | n losses | net |
|---|--:|--:|--:|--:|--:|
| TRAIL-20 | $+0.00 | 0 | $-150.35 | 17 | $-150.35 |
| TRAIL-25 | $+571.95 | 6 | $-208.90 | 11 | $+363.05 |
| TRAIL-30 | $+481.80 | 6 | $-313.35 | 11 | $+168.45 |
| TP1Q-050 | $+82.50 | 7 | $-132.50 | 10 | $-50.00 |
| TP1Q-033 | $+218.70 | 7 | $-1,206.85 | 10 | $-988.15 |
| RIDE-BUNDLE | $+733.70 | 8 | $-1,355.25 | 11 | $-621.55 |

## Disclosure: BH-FDR + concentration

| id | BH-FDR p | significant (a=0.10) | delta ex-top3 | survives ex-top3 |
|---|--:|:--:|--:|:--:|
| TRAIL-20 | 0.99997 | False | $-150.35 | False |
| TRAIL-25 | 0.07731 | True | $-18.25 | False |
| TRAIL-30 | 0.23476 | False | $-152.75 | False |
| TP1Q-050 | 0.80598 | False | $-94.05 | False |
| TP1Q-033 | 0.92781 | False | $-1,144.15 | False |
| RIDE-BUNDLE | 0.87257 | False | $-973.55 | False |

## Disclosed limitations

- ribbon_flip_back is OFF (no historical ribbon-state reconstruction for arbitrary past dates) -- same disclosed limitation exit_variant_ab.py and structure_stop_study.py both carry for the ribbon-flip secondary exit only; structure_stop/premium_stop/tp1/trail/runner_target/time_stop are ALL modeled via the real exit_manager.plan_exit_actions core.
- The shared candidate shape is applied UNIFORMLY to every real-fills option position regardless of which strategy (ribbon_ride vs vwap_continuation) actually fired live -- fills-ledger.jsonl carries no strategy/setup tag. Same convention structure_stop_study.py / structure_stop_reference_level_ab.py already used for their real-fills anchor layer.
- Trigger-level recovery is a backward-scan heuristic (lookback=8 bars/~40min), identical to structure_stop_study.recover_trigger_level_real_position. Positions with no recoverable trigger_level fall back to stop_mode=premium IDENTICALLY across control and every candidate -- never a fabricated level, never dropped.
- C6 fill-mark convention (exit_manager_walk.py): market-style stages (structure_stop/ribbon_flip/time_stop) fill at that bar's CLOSE minus $0.02 slippage; limit-style stages (tp1/premium_stop/trail/runner_target) fill exactly at the triggered premium level.
- Frictionless fills at trigger/stop/target levels beyond the $0.02 market-stage slippage above (no bid/ask spread or queue modelled) -- matches every prior study in this codebase (T3/T4/T5/T-W8/structure_stop_study/exit_variant_ab).
- ALL_LIVE_ARMS (fleet_rest + core) population per exit_shape_parity_study.py's own 2026-07-21 sanctioned opt-in -- a NEW study, not a silent extension of an already-verdicted one (the frozen structure-stop studies keep their own pinned FLEET_REST_ARMS-only anchors untouched).

---
_Source: `backtest/tools/trail_width_exit_ab.py`. Full per-position detail in the companion `.json`._
