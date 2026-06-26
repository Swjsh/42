# Plan 1 — Gate-Count Sweet Spot (gym/backtest the fleet table)

> Spawned from the 2026-06-24 breakthrough: the 6-tier looseness table proved (in WATCH) that a *loose* bold arm catches the 11/11 reclaim the tight gates vetoed all day. J: "figure out the sweet spot for the amount of gates that would have played today's key levels like a violin."

## Question
Across the looseness spectrum (control → tight → medium → loose), **what gate count maximizes edge-capture on key-level plays without overtrading?** Today says *looser caught the winner* — but does looser bleed on other days? Find the knee of the curve.

## Method
1. Take the 6 differentiated configs (`automation/state/fleet/accounts.json` arms + their `gate_override`/`params_patch`).
2. Run each through the backtest engine on the **historical day set**: the J source-of-truth days (4/29, 5/01, 5/04 winners; 5/05–5/07 losers — OP-16) + recent days incl. **today 6/24** (the anchor reclaim).
3. Use `backtest/autoresearch/backtest_fleet.py` (real-fills fidelity, not BS-sim — C1).
4. Score each config: `edge_capture × expectancy`, **and disclose the overtrade rate** (trades/day, theta bleed) per config — looseness that churns is disqualified (J's caveat).

## Deliverable
- Ranked config table: gate-count → edge_capture, expectancy, WR, trades/day, max DD.
- The **sweet-spot recommendation** + an A/B scorecard at `analysis/recommendations/fleet_gate_sweetspot.json` (OP-11 eval-first gate).
- Feeds back into which `gate_override` each of the 5 live arms should run.

## Owner / status
Gym-backtest workflow (launched 2026-06-24). Read-only research; no live changes. Ships under OP-22 once the scorecard clears.
