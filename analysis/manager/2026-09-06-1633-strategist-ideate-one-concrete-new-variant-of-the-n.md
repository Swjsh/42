<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=3.637s | action=Ideate ONE concrete new variant of the N -->
<!-- reason: Recent work is critic-heavy and the NLWB family is the only one showing gym WR=71% N=157 — a level-rejection variant with explicit regime filters is the highest-EV new edge to draft now, distinct from yesterday's relax-bearish-rejection-filter and shotgun-scalper grinder output. -->

entry_trigger: close back inside PDL +/- 6 ticks after wick pierce  
RVOL_gate: RVOL > 1.8  
VIX_regime_filter: VIX < 18  
hard_stop: 1.2R  
profit_target: 2.5R fixed with 50% trail after 1.5R  
time_of_day_window: 09:45-12:00 ET  
max_trades_per_day: 4  

Hypothesis: tighter tick buffer and higher RVOL gate filter noise, yielding ~12 bps higher expectancy vs baseline NLWB.