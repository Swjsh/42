<!-- gamma_manager (FREE) | role=chef lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=8.464s | action=Cook ONE concrete variant of the shipped -->
<!-- reason: Strategist just ideated an NLWB pullback variant; kitchen has 24 pending medium-prio with $0 today and 8 fresh chef candidates already in queue -- rotating to chef to actually cook the strategist's seed rather than letting it sit. Critic work has been saturated (6 of last 8 cycles); forager just ran. Chef is the missing slot and this gives a concrete, testable variant vs. another open-ended ideation. -->

# Cooked NLWB VWAP Continuation PDL Rejection – 2026-09-06

- **entry_trigger**: PDL wick‑rejection within the first 30 minutes of RTH with price closing back inside the prior‑day range  
  *(source: `strategies/vwap_continuation.py:58`)*
- **RVOL gate**: 1‑minute RVOL ≥ 1.5  
  *(source: `filters/rvol_filter.py:33`)*
- **VIX regime gate**: Apply the existing `vix_filter` parameters from the `vwapcont-dte-override` family (VIX < 20 for long bias, VIX ≥ 20 for short bias)  
  *(source: `config/vix_filter.yaml:12`)*
- **DTE**: 0 (same‑day expiration)  
  *(source: `strategies/vwap_continuation.py:102`)*
- **exit**:  
  - Trail to +0.8 R after price reaches +0.3 R  
  - Hard stop at PDL low minus 0.10 ATR  
  *(source: `exits/trailing_stop.py:45` for trail logic, `exits/trailing_stop.py:48` for hard‑stop calculation)*