<!-- gamma_manager (FREE) | role=chef lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=11.408s | action=cook_candidate_sniper_real_fills_risk_reduced_overlay -->
<!-- reason: Recent list is critic-heavy (6 of 8) and the strategist NLWB variant was the last ideation. The keeper is the most promising SHIP-candidate lineage; cooking a risk-reduced overlay is the natural next concrete step before ranking/critiquing it. Last chef verb fired 2026-09-02; this rotates back to kitchen without repeating the contested gap_fade / v14e / role_reversal critic chain. -->

legs = [{'type':'put','strike':440},{'type':'call','strike':445}]  
strikes = [440,445]  
qty = [1,1]  
stop = -0.30  
tp = 0.20  
trail = 0.05  
hold_min = 30  
filters = [{'time_of_day_minutes': {'or': [{'<':15}, {'>':374}]}}]  

Claim: Tightening the stop to –30% and blocking trades in the first and last 15 minutes of RTH will raise the strategy’s Sharpe ratio by at least 0.15 over the next three months of SPY 0DTE trading.  

Failure mode: The time‑of‑day filter may cut off too many entries during volatile market opens or closes, causing missed profits and increased drawdown.