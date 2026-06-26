<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=12.706s | action=A strategy scored edge=1692, WF=1.98, WR -->
<!-- reason:  -->

- Extremely high edge (1692) relative to modest win‑rate (12%) suggests the metric is being driven by a few large outliers rather than consistent performance.  
- Win‑rate of only 12% combined with a profit factor (WF) near 2.0 indicates the strategy relies on rare, large wins that are unlikely to generalize.  
- The sample size (2557 bars) is insufficient to reliably estimate such a skewed distribution, making the results highly susceptible to over‑fitting to noise.