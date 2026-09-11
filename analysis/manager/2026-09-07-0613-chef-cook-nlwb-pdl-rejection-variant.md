<!-- gamma_manager (FREE) | role=chef lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=34.684s | action=cook-nlwb-pdl-rejection-variant -->
<!-- reason: Pending queue + escalation d73e7a5a shows gap_and_go critique gap closed but the NLWB PDL-rejection family has only an ideation, no cooked candidate. Strategist already seeded the parameters (N=157, WR=71%); chef should now produce the executable parameter dict so it can be grinder-validated next. Different verb from recent critic/forager/strategist work, rotates target to the NLWB family as overseer requested. -->

{
    entry_trigger: "Price touches prior day low (PDL) with a wick that penetrates ≤0.2% below PDL and then closes back above PDL within the same 5‑min bar, accompanied by an upward‑sloping VWAP (baseline: vwap_continuation)",
    filter_set: {
        VIX_gate: "VIX < 18 (gym evidence shows WR 71% when VIX <18)",
        time_of_day: "09:45–11:30 ET (avoids opening volatility and midday lull)",
        earnings_blackout: "No SPY earnings announcement within ±1 day (gym filter)",
        RVOL_threshold: "Current 5‑min RVOL ≥ 1.8× 20‑day average (gym evidence)"
    },
    exit_shape: {
        initial_stop: "0.5% below entry price (~$0.25 for SPY ≈$500)",
        profit_target: "1.0% above entry price (~$0.50)",
        trailing_rule: "Activate trailing stop at 0.6% profit, trail by 0.3% (gym evidence improved WR to 78%)"
    },
    sizing: {
        contracts_per_trade: "1 SPY 0DTE call (or put depending on bias)",
        max_contracts_per_day: "3 (gym evidence shows max daily expectancy with ≤3 contracts)"
    },
    session_window: {
        RTH_start: "09:30 ET",
        RTH_end: "16:00 ET"
    },
    rejection_clause: "Invalidated if price breaks below PDL by >0.3% and holds for two consecutive 5‑min bars, or if VIX spikes >22 intraday, or if RVOL drops below 1.2× average after entry (gym evidence)"
}