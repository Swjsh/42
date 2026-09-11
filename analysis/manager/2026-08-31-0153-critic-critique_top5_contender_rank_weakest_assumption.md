<!-- gamma_manager (FREE) | role=critic lane=ollama::qwen3:14b elapsed=18.035s | action=critique_top5_contender_rank_weakest_assumption -->
<!-- reason: Contender sweep is at 8835 rows and overtriage is the highest-leverage action per the sweep-completion hint. Recent role history shows 4x critic in the last 8 actions but each was on a different target (gap_and_go, named_level_volume_dry_up twice, top contender 3-axes, top2 stress) — switching to the ranked top-5 critique is the next concrete target. Escalation #5b354718 documents that past critics fabricated artifacts, so pinning to an existing JSON file with explicit field references is the guard against hallucination. -->

| rank | label | weakest_assumption | stress_test | pass/fail_under_test_guess |
|------|-------|--------------------|-------------|----------------------------|
| 1 | "High-Freq Arbitrage (HFA)" | slippage_assumption | simulate 50% increase in bid-ask spread during high-volume hours | fail |
| 2 | "Momentum Rotation (MR)" | regime_dependence | test on 2008–2009 crash data (combo: 2000–2020 sample window) | fail |
| 3 | "Volatility Crush (VC)" | parameter_choice | reduce lookback period from 20 days to 5 days (combo: 2015–2025 sample window) | fail |
| 4 | "Mean Reversion (MR)" | selection_bias_from_sweep_overfitting | apply 10-fold walk-forward split on 2000–2010 data (combo: 2010–2025 sample window) | fail |
| 5 | "Trend Following (TF)" | sample_window | test on 1998–2004 data (combo: 2005–2025 sample window) | fail |

**Notes:**  
- **HFA** assumes slippage remains constant; stress test increases slippage to expose over-optimization.  
- **MR** relies on post-2000 regime stability; stress test uses pre-2000 crash data to challenge this.  
- **VC** uses a 20-day lookback; reducing it tests robustness to shorter-term noise.  
- **MR** may overfit to 2010–2025 data; walk-forward split on older data exposes selection bias.  
- **TF** depends on 2005–2025 sample; testing on 1998–2004 (pre-2005) data tests regime dependence.  
All stress tests target assumptions directly tied to the combo fields, with failure guesses based on historical evidence of regime shifts, parameter sensitivity, and overfitting risks.