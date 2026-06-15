"""Autoresearch loop for Gamma — Karpathy-style self-improving filter parameters.

The "weights" being optimized are the numerical thresholds in lib/filters.py
and lib/orchestrator.py. The loss function is negative Sharpe ratio of trades
over a rolling training window.

Pattern (Karpathy autoresearch -> Gamma):
    Karpathy           | Gamma
    -------------------|--------------------------------------
    modifies train.py  | modifies one filter parameter value
    5-min GPU run      | one backtest over training window
    val loss           | trade Sharpe ratio on training window
    git commit/revert  | state.json keep/revert + history.jsonl
"""

from . import config, metrics, proposer, runner, state

__all__ = ["config", "metrics", "proposer", "runner", "state"]
