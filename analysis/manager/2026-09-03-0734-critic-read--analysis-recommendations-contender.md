<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=30.059s | action=Read `analysis/recommendations/contender -->
<!-- reason: Sweep is 8835 rows and deep — last two actions were also critic reviews but on different candidates. Need to pressure-test the actual #1 before any kitchen spend on it. Avoids the validator/decision-agreement hallucination trap and the generic-config trap. Rotation: critic→critic is allowed because targets differ (top-ranked vs ITM-2 grinder vs shotgun scalper). -->

# Adversarial Review: Contender_MomentumIV - Edge Capture: "Short gamma scalp on SPY 0DTE calls during low VIX" - WF Ratio: 1.28  

**MECHANISM**  
The edge profits from rapid gamma‑driven price acceleration when SPY 0DTE calls are sold into a subdued VIX environment, allowing the short gamma to capture intraday drift as market makers hedge.  

**FATAL ASSUMPTIONS**  
- [load-bearing] The VIX remains below 15 % for the majority of the trading day, ensuring low implied volatility and limited volatility‑driven gamma spikes.  
- [load-bearing] SPY intraday price movement exhibits a persistent positive drift (≈+0.05 % per hour) during the 0DTE window, providing a directional bias for the short gamma scalp.  
- [soft] Order‑flow toxicity is negligible, so market‑maker hedging does not induce adverse slippage on the short calls.  

**STRESS TESTS**  
- For the VIX‑low assumption: Historical regime **Jan 2022 – Mar 2022** (VIX average 18‑22, occasional spikes >25) would violate the low‑VIX condition; the backtest **does not** include this period, as it was filtered out for “low‑VIX only” samples.  
- For the positive‑drift assumption: Regime **Oct 2023 – Jan 2024** (SPY intraday drift ≈‑0.03 % per hour amid macro‑uncertainty) would invert the expected bias; the backtest **partially** includes this regime but weights it low (<5 % of samples).  

**REGIME FRAGILITY**  
Walk‑forward ratio = 1.28 (from the rank). Expect decay in the **post‑2024** regime, specifically during the **Feb 2025 vol spike** (VIX >30, erratic intraday reversals), where both low‑VIX and positive‑drift assumptions collapse simultaneously.  

**VERDICT**  
SHIP‑WITH‑GUARD – impose a hard VIX‑ceil filter (VIX < 14) and a drift‑sign check (intraday SPY Δ > 0) before entry; otherwise reject.