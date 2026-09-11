<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=23.089s | action=critique_ITM-2-lr0-mt2-stop40-tp150-trailing -->
<!-- reason: Latest sweep row just landed and shows op16_reject=true, edge_capture deeply negative, wf -0.829 — exactly the kind of candidate that needs adversarial review before any triage decision. Last three actions were critic/critic/critic on related material; staying critic but rotating to the freshest ITM-2 row with a different angle (structural assumption + stress test spec) so we don't repeat the prior ITM-2 critique. -->

- Edge_capture is –717.6, indicating a negative net profit after costs.  
- Expectancy per trade is only 9.07 despite a aggressive +150% profit target and a low win rate of 0.329.  
- Maximum drawdown reaches –2664.49 while the strategy averages just 1.129 trades per day, showing high risk exposure.  
- Walk‑forward metric wf is –0.829 and op16_reject = true, signalling failure out‑of‑sample validation.  
- qty_frontier is null, meaning no scalable position size was identified for practical deployment.  

Stress‑test: Perform a regime split by separating the sample into high‑VIX and low‑VIX periods (using the same chronological split) and recompute edge_capture, expectancy, and max_dd for each regime; a significant deterioration in either regime would falsify the claim of a robust 0DTE SPY edge.  

REVOKE