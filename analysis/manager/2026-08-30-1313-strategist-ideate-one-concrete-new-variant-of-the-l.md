<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=10.492s | action=Ideate ONE concrete new variant of the l -->
<!-- reason: Pending queue.md tail item #1-3 explicitly demands a level-rejection pullback variant that survives the structure-shift null; the manager_flagged escalation [71b11ddf50de3d1b] has been pending since 2026-08-30 05:53 ET; strategist lane is fresh (last strategist action was the same family ideation 24h ago, but the overseer's structured next-action list item #3 explicitly retires 'write backtest JSON' and this ideation slot, plus we have not produced a differentiated variant yet). Picking strategist over coder because the failure mode is design differentiation, not parameter tuning. -->

{
 entry_trigger: "price reclaims PDL by >=0.12% within 4m after a wick-bounce where the low penetrates ATR*0.9",
 wick_min_atr_mult: 0.9,
 reclaim_window_min: 4,
 stop_placement_rule: "2 ticks below the wick low (or 0.08% below PDL, whichever is lower)",
 target_rule: "1.5R or next intraday HOD if reached before 11:30 ET, otherwise exit at 1.0R",
 time_of_day_window: "09:30-11:00 ET",
 vix_gate: 13.5,
 rvol_min: 1.3,
 max_trades_per_day: 2,
 forced_exit_time: "11:30 ET"
}

- Prior kill #1 used a loose wick threshold (ATR*1.2) and a 10‑minute reclaim window, causing delayed entries and whipsaws; this variant tightens the ATR multiplier to 0.9 and shortens the window to 4 min for faster, higher‑probability captures.  
- Prior kill #2 applied a high VIX gate (20) and allowed trading all day, exposing the strategy to afternoon noise; we lower the VIX gate to 13.5 and restrict activity to the 09:30‑11:00 ET morning session when liquidity and structure are strongest.  
- Earlier attempts fixed the target at a flat 2R regardless of market context, often leaving profit on the table; here the target adapts to 1.5R or the next intraday HOD, capturing stronger moves while preserving a defined risk‑reward floor.

Null hypothesis: The strategy’s expectancy (net of slippage and commissions) is zero or negative.