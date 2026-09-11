<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=17.139s | action=ideate_gap_and_go_v2 -->
<!-- reason: Escalation d73e7a5a is open and notes gap_and_go is the most-shippable contender in the 8835-row sweep but has not been adversarially critiqued then iterated. My last 4 actions were 3x critic + 1 validator on the same edge — overdue for an ideator turn that turns the critique into a next-gen variant. Strategist role, not coder (no backtest config per overseer rule), not critic (just did), not forager (just did 2x). -->

gap_and_go_v2_vix_tight = {
    "entry_window_et": "09:30-10:00",
    "min_gap_pct": 0.8,
    "volume_mult": 2.0,
    "vix_gate": 25,
    "stop_pts": 3,
    "target_pts": 6,
    "time_stop_min": 45,
    "max_trades_per_day": 2,
    "session_filter": "AM",
    "conflict_with": ["opening_reversal", "news_spike"]
}
If the market experiences a strong gap with high volume but VIX remains above 25, this variant fails to trigger, missing profitable trades.