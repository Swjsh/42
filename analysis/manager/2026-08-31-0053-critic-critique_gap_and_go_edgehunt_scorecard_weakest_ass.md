<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=19.273s | action=critique_gap_and_go_edgehunt_scorecard_weakest_assumption -->
<!-- reason: Sweep is at 8835 rows and likely near saturation; the queue tail + recent chef output shows level-rejection family already killed twice and a structure-shift null still standing. The most leveraged R&D right now is a hard adversarial critique of an existing named candidate (gap_and_go) rather than another ideation — gap_and_go is a high-variance 0DTE setup where a single bad assumption (e.g. gap-fill rate, opening-range breakout reliability, slippage at 9:30) can wreck the edge. Per overseer rule, this is a 'critique a SPECIFIC named candidate' verb and I have not done this exact target this week (last critic jobs were gap_and_go v2 and next_top_contender, not the raw edgehunt scorecard). Keeps verb rotation honest while attacking the highest-leverage assumption in the live contender set. -->

analysis/recommendations/edgehunt-gap_and_go.json
{
  "edge_claim": {
    "variant": "gap_and_go",
    "context": "SPY 0DTE",
    "assumptions": [
      {
        "id": "A1",
        "statement": "Morning gap direction predicts same‑day intraday trend with >60% accuracy",
        "support": "Backtest shows 62% win rate on gaps >0.5% over 2022‑2024"
      },
      {
        "id": "A2",
        "statement": "Liquidity remains sufficient to enter/exit at the open without slippage >2 bps",
        "support": "Average bid‑ask spread 1.2 bps, volume >5M shares"
      },
      {
        "id": "A3",
        "statement": "Volatility regime is stable; VIX <20 ensures gap persistence",
        "support": "During backtest period VIX averaged 18"
      }
    ],
    "stress_tests": [
      {
        "parameter": "gap_threshold",
        "range": "[0.3%, 0.7%]",
        "metric": "win_rate",
        "threshold": "<55%",
        "window": "250 sessions"
      },
      {
        "parameter": "max_slippage_bps",
        "range": "[1, 5]",
        "metric": "net_expectancy",
        "threshold": "<0",
        "window": "250 sessions"
      }
    ]
  }
}