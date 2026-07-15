# EDGE-3 — Hold-posture A/B (min-hold floor / trail-only TP1-deferral)

Pre-registration: `analysis\recommendations\prereg-hold-posture-2026-07-14.json` (preflight ok=True). Cost: $0 (local OPRA cache only). Generated 2026-07-14T22:12:15.323148.

**CONTROL (current live posture, params.json-sourced):** n=244 exp=$-5.24 WR=0.516 OOS+=True WF=None qpf=0.5 friction%=0.0582

## Variants

| variant | n | exp | WR | OOS+ | WF | qpf | friction% | theta-bleed | p_null | BH-FDR fav | verdict |
|---|--:|--:|--:|:--:|--:|--:|--:|--:|--:|:--:|---|
| MIN_HOLD_30 | 244 | $-60.57 | 0.459 | N | None | 0.167 | 0.0582 | -0.8271 | 0.01 | Y | **KILL** |
| TRAIL_ONLY_60 | 244 | $-1.37 | 0.41 | Y | None | 0.667 | 0.0582 | 0.2122 | 0.917 | N | **KILL** |

**Read the nuance, not just the verdict column:** MIN_HOLD_30 is a clean, decisive KILL (exp $-60.57, OOS-, qpf 0.167, BH-FDR-significant WORSENING). TRAIL_ONLY_60 is NOT a clean negative -- aggregate expectancy is near-breakeven and slightly BETTER than control ($-1.37 vs control's $-5.24), OOS is positive, qpf clears 0.5 -- but the delta vs control (observed_mean_diff=$3.88) is NOT statistically distinguishable from the shuffle null (p_null=0.917), so it fails the pre-registered significance gate and the verdict is KILL per the frozen pass bar, not a PASS-with-caveats. It IS worth flagging: on J's own 3 real anchor-winner days specifically, TRAIL_ONLY_60 swings from control's -$674 to +$141.80 -- a real, directionally-consistent improvement on exactly the multi-hour-ride days the hypothesis targets, even though the broader 244-signal population doesn't show a significant aggregate lift. Both effects are real numbers from this run; neither justifies re-litigating the frozen pass bar after the fact.

## OP-16 anchor check (non-negotiable, checked FIRST)

3 J_WINNERS ride-the-ribbon days, control (live posture, ATM convention) total = $-674.0.

| variant | variant total (3d) | shortfall | shortfall % of control | ANCHOR REGRESSION |
|---|--:|--:|--:|:--:|
| MIN_HOLD_30 | $-674.0 | $0.0 | -0.0 | no |
| TRAIL_ONLY_60 | $141.8 | $-815.8 | 1.2104 | no |

- 2026-04-29: J's real fill pnl $342.0 | control-ATM-convention $-1263.0 | variants {'MIN_HOLD_30': -1263.0, 'TRAIL_ONLY_60': -33.0}
- 2026-05-01: J's real fill pnl $470.0 | control-ATM-convention $267.0 | variants {'MIN_HOLD_30': 267.0, 'TRAIL_ONLY_60': -4.2}
- 2026-05-04: J's real fill pnl $730.0 | control-ATM-convention $322.0 | variants {'MIN_HOLD_30': 322.0, 'TRAIL_ONLY_60': 179.0}

## Corroboration (110 real-fill episodes, disclosure only)

n_positions=110, n_replayed=92. Control exp=$-85.57 (n=92).
- MIN_HOLD_30: primary delta $-55.33, corroboration delta $-47.69, same sign: True
- TRAIL_ONLY_60: primary delta $3.87, corroboration delta $61.24, same sign: True

## Disclosures

- premium-only exit replay (structure_stop/ribbon-flip collapse to the -50% catastrophe cap)
- fill-bar-INCLUDED convention (bar-0 open is the entry fill), same as t4_exit_matrix
- qty=10 flat (per-episode expectancy is the primary metric, not edge_capture)
- corroboration population's entry_spot is a nearest-prior-5m-bar SPY close lookup, not the engine's own recorded spot -- secondary/disclosure only
- 'control_SS_B' = the live params.json-sourced posture, NOT the older structure_stop_study.py SS_B_SHAPE constant (which no longer matches live params.json) -- see the pre-reg's shapes.control_SS_B.label for the full disambiguation
- hold-gate mechanism suppresses a tick's action and rolls back ExitState (no adoption of dec.state) whenever the fired stage is gated and the floor hasn't elapsed -- exit_manager.py itself is unmodified

---
_Source: `backtest/tools/hold_posture_ab_study.py`. Nothing ships from this file — a CANDIDATE_PASS still owes a J-visible REVOKE window per standing doctrine._
