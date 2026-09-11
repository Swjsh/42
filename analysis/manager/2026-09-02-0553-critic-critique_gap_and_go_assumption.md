<!-- gamma_manager (FREE) | role=critic lane=ollama::qwen3:14b elapsed=12.18s | action=critique_gap_and_go_assumption -->
<!-- reason: Overseer item #4 next-fire; gap_and_go is a named candidate in recommendations/ and hasn't been critiqued yet this cycle. Critic lane is fresh (last critic was on v14e_trail_loosen_020 and the ITM-2 contender, two fires ago). -->

(1) "Historical volatility patterns will repeat in future market conditions."  
(2) This assumption is load-bearing because the strategy's risk management and position sizing rely on volatility clustering observed in backtests; if future volatility diverges significantly, drawdowns could exceed expectations.  
(3) {"stress_test": {"filter": "volatility_filter", "parameters": {"historical_volatility_threshold": 0.15, "lookback": 252, "volatility_metric": "ATR(20)"}}}  
(4) Strategy's maximum drawdown during periods where ATR(20) exceeds 1.5x historical median (calculated over the same lookback) > 25%.