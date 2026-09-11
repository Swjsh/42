<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=6.62s | action=Ideate ONE concrete new variant of the l -->
<!-- reason: Overseer has this on the docket (item #3 in next-4 list) AND there's a live manager-flagged ESCALATION for it. I just did critic work twice running; rotating to strategist fulfills the level-rejection ideation that the null queue demands, with concrete parameters the coder can later run. Bounded: one variant dict + null definition. -->

trigger_wick_reject_pct=0.34
entry_offset_ticks=1
stop_basis=ATR
stop_atr_mult=1.1
target_basis=structure
target_structure_mult=1.8
time_stop_min=20
null_test="zone_entry_reclaim_after_move_net_losers <= 0"