"""One-combo smoke test for the sniper evaluator.

Runs evaluate_sniper_combo on a single sensible combo and prints the result
so we can verify wiring before committing to a 432-combo overnight grind.

Run:
    python -m autoresearch.sniper_smoketest
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch.sniper_evaluator import evaluate_sniper_combo


def main() -> int:
    combo = {
        "vol_mult": 1.5,
        "body_min_cents": 0.10,
        "min_stars": 2,
        "strike_offset": 0,
        "premium_stop_pct": -0.10,
        "tp1_premium_pct": 0.30,
        "runner_target_pct": 1.5,
        "profit_lock_threshold_pct": 0.10,
        "profit_lock_stop_offset_pct": 0.05,
        "tp1_qty_fraction": 0.667,
        "qty": 10,
        "proximity_dollars": 1.5,
        "require_break_above_open": True,
    }
    print(f"Running smoke combo: {combo}")
    result = evaluate_sniper_combo(combo)
    print(json.dumps(result, indent=2, default=str))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
