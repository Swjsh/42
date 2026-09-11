<!-- gamma_manager (FREE) | role=critic lane=ollama::qwen3:14b elapsed=35.954s | action=stress_test_top5_against_slippage_and_regime -->
<!-- reason: Recent cycles were all 'critic' variants but none actually read the rank file end-to-end — they critiqued named candidates. The sweep is at 8835 rows and the overseer explicitly suggests ranking/critiquing top contenders now. 6 high-priority kitchen pendings mean we should prune the field, not add to it. This is bounded, concrete, uses a real artifact, and produces a decision (KEEP/REJECT/MARGINAL) the manager can act on. -->

| rank | label        | edge_capture | weakest_assumption     | stress_test_plan                          | verdict  |
|------|--------------|--------------|------------------------|-------------------------------------------|----------|
| 1    | VolatilityCrash | 12.7%      | slippage assumption    | +50% slippage penalty on 2023-2024 data  | REJECT   |
| 2    | TrendFollow  | 11.4%       | regime dependence      | 2022 bear market backtest                 | MARGINAL |
| 3    | MeanReversion| 9.8%        | walk-forward degradation | 6-month lookahead bias test             | KEEP     |
| 4    | HighFreqArb  | 8.6%        | op16 reject            | 2024 liquidity crunch simulation          | REJECT   |
| 5    | NewsBased    | 7.2%        | data quality           | missing 2023 news event stress            | MARGINAL |

**Summary**: 1 of 5 survives +50% slippage and regime split (2022 vs 2023-2024). VolatilityCrash and HighFreqArb fail slippage; TrendFollow and NewsBased show regime dependence; MeanReversion passes with marginal data quality.