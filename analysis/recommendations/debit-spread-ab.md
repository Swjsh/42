# EDGE-2 — Debit-spread vs naked single-leg A/B

Pre-registration: `analysis\recommendations\prereg-debit-spread-ab-2026-07-14.json` (preflight ok=True). Cost: $0 (local OPRA cache only). Generated 2026-07-14T22:03:15.897458.

**CONTROL (naked ATM single-leg):** n=244 exp=$-5.24 WR=0.516 OOS+=True WF=None qpf=0.5 friction%=0.0582

## Variants

| variant | n | exp | WR | OOS+ | WF | qpf | friction% | theta-bleed | p_null | BH-FDR | verdict |
|---|--:|--:|--:|:--:|--:|--:|--:|--:|--:|:--:|---|
| OTM-1 | 244 | $-63.06 | 0.455 | N | None | 0.0 | 0.2571 | -0.5434 | 0.0764 | Y | **KILL** |
| OTM-2 | 244 | $-52.65 | 0.48 | N | None | 0.0 | 0.1695 | -0.6781 | 0.092 | Y | **KILL** |

## OP-16 anchor check (non-negotiable, checked FIRST)

3 J_WINNERS ride-the-ribbon days, naked ATM total = $-674.0.

| variant | variant total (3d) | shortfall | shortfall % of naked | ANCHOR REGRESSION |
|---|--:|--:|--:|:--:|
| OTM-1 | $-98.0 | $-576.0 | 0.8546 | no |
| OTM-2 | $-10.0 | $-664.0 | 0.9852 | no |

- 2026-04-29: J's real fill pnl $342.0 | naked-ATM-convention $-1263.0 | variants {'OTM-1': -176.0, 'OTM-2': -246.0}
- 2026-05-01: J's real fill pnl $470.0 | naked-ATM-convention $267.0 | variants {'OTM-1': 140.0, 'OTM-2': 214.0}
- 2026-05-04: J's real fill pnl $730.0 | naked-ATM-convention $322.0 | variants {'OTM-1': -62.0, 'OTM-2': 22.0}

**Caveat (read before trusting 'no regression' at face value):** the naked-ATM-convention total across these 3 days is ITSELF negative (\$-674.0), far from J's real +\$1,542 across the same 3 days — because this study's ATM-long-leg convention is NOT J's actual historical strike/qty (see the pre-reg's anchor_check_op16.signal_match_method). The spreads losing LESS than an already-losing ATM baseline on these specific days is not evidence spreads protect J's real edge; it means neither structure, replayed at ATM, reproduces what actually made these days winners. The anchor check's real job — did adding a short leg cap a payoff that was otherwise working — could not be meaningfully exercised here because the naked baseline itself doesn't reproduce the win. Treat `anchor_regression: no` as 'not disproven', not as a validated pass.

## Corroboration (110 real-fill episodes, disclosure only)

n_positions=110, n_replayed=92. Naked exp=$-85.57 (n=92).
- OTM-1: primary delta $-57.82, corroboration delta $-46.86, same sign: True
- OTM-2: primary delta $-47.41, corroboration delta $-69.11, same sign: True

## Disclosures

- premium-only exit replay (structure_stop/ribbon-flip collapse to the -50% catastrophe cap)
- fill-bar-INCLUDED convention (bar-0 open is the entry fill), same as t4_exit_matrix
- qty=10 flat (per-episode expectancy is the primary metric, not edge_capture)
- corroboration population's entry_spot is a nearest-prior-5m-bar SPY close lookup, not the engine's own recorded spot (the ledger does not persist it) -- secondary/disclosure only
- spread net-premium walk treats the 2-leg combo as one synthetic instrument for the exit_manager pct-of-entry-premium math -- a simplification, not a per-leg fill reconstruction at each trigger level (no tool in this repo does that for a 2-leg combo under live-shape replay)
- POST-FREEZE CORRECTION (see prereg): the spread's exit trigger uses bar-CLOSE net premium (a real simultaneous joint quote), not the intrabar long.low-short.high/long.high-short.low combo -- the v1 run fed that combo directly into the touch-based stop test and produced an implausible ~95% catastrophic-stop rate; simulator_debit.py itself only uses that combo as a disclosure flag, gating its actual PT/STOP on the same close-based figure this study now uses.

---
_Source: `backtest/tools/debit_spread_ab_study.py`. Nothing ships from this file — a CANDIDATE_PASS still owes a J-visible REVOKE window per standing doctrine._
