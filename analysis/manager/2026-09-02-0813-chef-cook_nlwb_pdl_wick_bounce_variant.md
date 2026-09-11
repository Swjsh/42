<!-- gamma_manager (FREE) | role=chef lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=26.577s | action=cook_nlwb_pdl_wick_bounce_variant -->
<!-- reason: Overseer's action #3 is unstarted — strategist/chef lane is free, queue has 6 high-priority pending, and NLWB is a distinct family from the recent vwap/gap/orc candidates so it adds breadth rather than overlap. Concrete gym baseline (N=157, WR=71%) prevents generic hallucination. -->

entry_trigger: touch_PD_low_then_close_above
session_window: 09:35-11:00 ET
stop: ATR*1.5
target: 2R
vix_filter: 20
rvol_filter: 1.5
exit_eod: true
max_trades_per_day: 3