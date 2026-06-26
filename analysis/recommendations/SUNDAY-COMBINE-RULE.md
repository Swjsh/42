# SUNDAY COMBINE RULE — how to trade the 3 overlapping VWAP edges live

- Run: 2026-06-21  |  Window: 2025-01-01..2026-06-16  |  Trading days: 363
- Fills: real OPRA via lib.simulator_real.simulate_trade_real (C1)  |  OOS split: IS=2025 / OOS=2026
- OPRA cache last day: 2026-06-18  |  realized last fill: 2026-06-15
- Config: -8% premium stop, qty 3/edge, v15 exits; kill switch {'Safe-2': -600.0, 'Bold': -836.0}; edge#4 vix cfg = {'slope_rule': 'not_rising', 'low_margin': 0.25, 'source': 'b5 robust_clearing_cell'}

## THE QUESTION

All 3 edges are VWAP-native and call/bull-biased on the 2026 tape; B8/B9 found they fire the SAME days SAME side. So on a signal day you may get 2-3 edges pointing the same way. The live COMBINE RULE — take 1 / best / all-stacked / first — IS the risk profile, and was never decided. This A/Bs all four on real fills, within the kill switch.

## RECOMMENDATION (per account)

_Eligibility guard (C4/L174): a rule must be OOS-positive AND not degrade OOS exp/tr vs the ONLY_1 baseline by more than $5/tr — a rule that wins on IS but fades on the live 2026 tape is a curve-fit, not shippable. Among eligible rules, rank by annualized Sharpe._

- **Safe-2 (ATM): `FIRST_TO_FIRE`** — OOS exp/tr $53.15 (baseline ONLY_1 $46.02), annualized Sharpe 4.0, L175 return/maxDD 16.45, total $7477.12
    - rejected — TAKE_BEST: OOS exp $34.42 degrades vs ONLY_1 $46.02 (>5.0)
    - rejected — TAKE_ALL_STACK: OOS exp $34.98 degrades vs ONLY_1 $46.02 (>5.0)
- **Bold (ITM-2): `ONLY_1`** — OOS exp/tr $76.61 (baseline ONLY_1 $76.61), annualized Sharpe 4.1, L175 return/maxDD 11.78, total $11060.04
    - rejected — TAKE_BEST: OOS exp $67.25 degrades vs ONLY_1 $76.61 (>5.0)
    - rejected — TAKE_ALL_STACK: OOS exp $64.55 degrades vs ONLY_1 $76.61 (>5.0)

> **Headline finding:** TAKE_BEST and TAKE_ALL_STACK both post higher IS totals/Sharpe but their OOS (2026 live tape) per-trade expectancy DEGRADES below the ONLY_1 baseline — the multi-edge ranking/stacking is curve-fit to 2025. The OOS-honest winner is the rule that holds up on the live tape, NOT the one with the prettiest full-window Sharpe.

## Day-overlap (how often edges stack)

- **Safe-2**: 158 signal days; by #edges firing = {'1': 43, '2': 72, '3': 43}; multi-edge days = 115; same-side multi-edge days = 115
- **Bold**: 157 signal days; by #edges firing = {'1': 76, '2': 81}; multi-edge days = 81; same-side multi-edge days = 81

## Safe-2 (ATM) — combine-rule A/B (real OPRA fills, kill-switch-clipped)

- IS-2025 expectancy ranking key (TAKE_BEST): {'1': 43.82, '2': 61.0, '4': 29.97}
- kill switch daily limit: $-600.0

| rule | n | exp/tr | total$ | OOS exp/tr | OOS$ | ann.Sharpe | maxDD$ | L175 ret/maxDD | worst day$ | day-WR% | KS breach days |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ONLY_1 | 156 | $44.51 | $6943.56 | $46.02 | $2254.88 | 3.84 | $-454.56 | 15.28 | $-211.68 | 49.4 | 0 |
| TAKE_BEST | 158 | $52.15 | $8240.28 | $34.42 | $1686.8 | 4.28 | $-573.28 | 14.37 | $-211.68 | 51.3 | 0 |
| TAKE_ALL_STACK | 316 | $41.86 | $13227.56 | $34.98 | $3322.88 | 4.08 | $-1007.16 | 13.13 | $-423.36 | 53.8 | 0 |
| FIRST_TO_FIRE | 158 | $47.32 | $7477.12 | $53.15 | $2604.56 | 4.0 | $-454.56 | 16.45 | $-211.68 | 50.0 | 0 |

## Bold (ITM-2) — combine-rule A/B (real OPRA fills, kill-switch-clipped)

- IS-2025 expectancy ranking key (TAKE_BEST): {'1': 67.56, '2': 100.36}
- kill switch daily limit: $-836.0

| rule | n | exp/tr | total$ | OOS exp/tr | OOS$ | ann.Sharpe | maxDD$ | L175 ret/maxDD | worst day$ | day-WR% | KS breach days |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ONLY_1 | 157 | $70.45 | $11060.04 | $76.61 | $3830.64 | 4.1 | $-939.12 | 11.78 | $-223.68 | 49.0 | 0 |
| TAKE_BEST | 157 | $84.07 | $13198.52 | $67.25 | $3362.44 | 4.6 | $-1053.12 | 12.53 | $-223.68 | 51.0 | 0 |
| TAKE_ALL_STACK | 238 | $74.63 | $17762.16 | $64.55 | $4711.96 | 4.25 | $-1635.0 | 10.86 | $-447.36 | 53.5 | 0 |
| FIRST_TO_FIRE | 157 | $70.45 | $11060.04 | $76.61 | $3830.64 | 4.1 | $-939.12 | 11.78 | $-223.68 | 49.0 | 0 |

## Over-stake check — TAKE_ALL_STACK vs ONLY_1 (the concentration penalty)

| account | total delta$ | maxDD delta$ | worst-day delta$ | Sharpe delta | KS-breach delta | overstakes? |
|---|---|---|---|---|---|---|
| Safe-2 | $6284.0 | $-552.6 | $-211.68 | 0.24 | 0 | False |
| Bold | $6702.12 | $-695.88 | $-223.68 | 0.15 | 0 | False |

## How to read this

- **The recommended rule** maximizes annualized Sharpe (risk-adjusted return inside the kill switch), tiebroken by L175 return-per-maxDD then total$. That is the rule to ship live.
- **TAKE_ALL_STACK overstakes** when it deepens maxDD without improving Sharpe — the same-side same-day concentration the brief warned about. The over-stake table quantifies it.
- **Kill-switch-clipped**: every day's loss is capped at the per-account halt, so these are the realistic books — a rule that only wins by ignoring the halt is not shippable.
- **Live-sizing kill-switch caveat:** this sim holds qty=3/edge, so even TAKE_ALL_STACK (2-3x position) never breaches the daily halt here. At LIVE sizing (Safe-2 risks 30%/edge, Bold 50%/edge), stacking 2-3 same-side edges the same day would multiply day risk and CAN breach the halt — another reason TAKE_ALL_STACK is not shippable beyond its OOS degrade.
- Real OPRA fills; SPY-direction != option edge (C3/L58). Per-trade EXPECTANCY, not WR (OP-14).
