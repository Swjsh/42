"""THE DOJO — tick-by-tick replay training room (J + engine, side by side).

Package spec: markdown/specs/DOJO-REPLAY-TRAINING-SPEC.md
Architecture + frozen module contracts: markdown/specs/DOJO-ARCHITECTURE-DECISION.md

HARD FENCE (guard-tested in backtest/tests/test_dojo_fence.py):
  - This package imports NOTHING from any alpaca/broker/live-order path.
  - It writes ONLY under automation/state/dojo/.
  - It performs NO git operations (2026-07-20 STATE-FILE-REVERSION scar).
It is a SIM-ONLY training harness. It never places a broker order.
"""
