<!-- gamma_manager (FREE) | role=chef lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=19.388s | action=cook_PDL_wick_bounce_pullback -->
<!-- reason: Recency bias check: last 7 actions were 5 critic + 2 forager. Need fresh ideation lane to balance. PDL-wick-bounce NLWB variant is a concrete, named family the firm already validated in-gym (N=157, WR=71%) -- high-value ideation target with bounded scope. Avoids retired coder backtest-config action and validator-without-state action. -->

Parameter dict  
- Entry: long on a 1‑min bar that prints ≤2 pts below the Prior Day Low (PDL) and then closes back above PDL within the next ≤ 3 bars (including the bar that broke below).  
- Stop: PDL − 1.5 pts.  
- Target: +0.8 R (where R = entry‑stop distance) **or** a hard time‑stop at 10:30 ET, whichever occurs first.  
- Filter: underlying 5‑min RVOL (5‑min bar volume vs. 20‑day average 5‑min volume) ≥ 1.2 **AND** VIX 9‑day EMA ≤ 17.  
- No‑trade window: 08:25‑10:00 ET (covers today’s NFP release).  
- Max trades: 1 per day.  
- Flatten: all positions closed by 15:55 ET.  

In‑sample window used for the NLWB gym read: 2024‑01‑02 through 2025‑12‑31 (≈ 500 trading days, 157 qualifying setups).  

Expected performance from the NLWB gym:  
- Win‑rate (WR) ≈ 71 %  
- Average win ≈ 1.2 R, average loss ≈ 0.6 R  
- Expectancy ≈ 0.71 × 1.2 − 0.29 × 0.6 ≈ 0.68 R per trade  
- Sample size n = 157 trades.  

One specific OOS failure mode: during abrupt macro shocks (e.g., surprise FOMC move or geopolitical headline) the price can gap through the PDL by >2 pts before any 1‑min bar forms. In that case the entry condition never triggers, the stop (PDL − 1.5 pts) is already breached, and the trade would incur an immediate loss. The RVOL filter may also misfire because volume spikes on news can inflate the 5‑min RVOL ratio, generating false longs that get stopped out quickly. This gap‑through scenario is the primary OOS risk to monitor.