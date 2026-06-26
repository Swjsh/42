<!-- gamma_manager (FREE) | role=coder lane=groq::llama-3.3-70b-versatile elapsed=0.743s | action=Write a backtest config/JSON for the con -->
<!-- reason:  -->

```json
{
  "backtest_config": {
    "target_file": "strategy/candidates/",
    "filter_criteria": {
      "edge": {
        "operator": "gt",
        "value": 771
      }
    },
    "sorting_criteria": {
      "final_score": {
        "formula": "edge_capture * aggregate_sharpe",
        "order": "desc"
      }
    },
    "output": {
      "table": {
        "columns": [
          "config_slug",
          "edge",
          "sharpe",
          "final_score"
        ],
        "num_rows": 5
      }
    }
  }
}
```