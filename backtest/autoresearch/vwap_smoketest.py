"""One-combo smoke test for the VWAP rejection evaluator.

Runs evaluate_vwap_combo on a single sensible combo and prints the result
so we can verify wiring before committing to a 972-combo overnight grind.

Run:
    python -m autoresearch.vwap_smoketest
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch.vwap_evaluator import evaluate_vwap_combo


def main() -> int:
    combo = {
        "vol_mult": 1.3,
        "proximity_dollars": 0.10,
        "lookback_bars": 2,
        "body_min_cents": 0.08,
        "premium_stop_pct": -0.10,
        "tp1_premium_pct": 0.30,
        "runner_target_pct": 1.5,
        "strike_offset": 2,
        "qty": 3,
        "tp1_qty_fraction": 0.667,
        "profit_lock_threshold_pct": 0.10,
        "profit_lock_stop_offset_pct": 0.05,
        "require_ribbon_agreement": True,
        "ribbon_min_spread_cents": 30.0,
    }
    print(f"Running smoke combo: {combo}")
    result = evaluate_vwap_combo(combo)
    print(json.dumps(result, indent=2, default=str))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
