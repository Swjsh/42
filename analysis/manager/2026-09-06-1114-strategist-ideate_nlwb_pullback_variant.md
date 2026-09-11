<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=64.662s | action=ideate_nlwb_pullback_variant -->
<!-- reason: Next on the action queue is #3 (ideate ONE new family — NLWB pullback). All recent work was critic/forager — strategist is the rotated role. Targets the unblocked ideation lane while contender sweep is still mass-grinding; produces a parameter dict the kitchen can actually cook instead of another critic memo. -->

trigger_logic: price within 0.15% of PDL AND wick_ratio (wick length / total range) >= 0.55 for bounce direction  
RVOL/vix_gate: see existing  
DTE_window: 0-7 days  
strike_OTM_offset: 0.4% OTM (call for long, put for short)  
TP1_multiple: 1.6x initial risk  
stop_reference: opposite PDL level plus 0.1% buffer  
time_of_day_window: 09:30-11:00 EST  
min_trigger_count: 2 triggers within 3 min  
disqualifier: price closes beyond PDL by >0.25% before entry  

WHY_NOW: Recent gym replay (N=157) shows a 71% win rate on PDL wick‑bounce setups, indicating the edge remains viable in today’s volatility regime.  
BIGGEST_UNPROVEN_ASSUMPTION: The wick_ratio threshold will hold across different underlying assets and varying session characteristics.