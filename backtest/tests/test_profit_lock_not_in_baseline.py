"""Guard: profit_lock_* must NOT be mapped by `_params_to_kwargs` (L156).

Graduates L156 (markdown/doctrine/LESSONS-LEARNED.md, 2026-06-17). The production chandelier
profit-lock lives in heartbeat.md for LIVE risk management (protect against
disconnects/crashes). In the BACKTEST it is net-NEGATIVE on the dominant
trending sub-windows: the 20% trail clips runners at 80% of HWM in trends where
0DTE winners run 200-800% premium. The whole-period IS is negative because the
trending windows out-volume the choppy window where it helps.

Therefore `_params_to_kwargs()` -- the params.json -> run_backtest translation
that defines every backtest BASELINE -- must NOT translate any profit_lock_*
field. If it did, every future baseline would silently bake in a profit-lock that
biases all candidate comparisons negative (a measurement-integrity foot-gun, C7).

The knobs still EXIST on `run_backtest(...)` so a deliberate research sweep
(autoresearch/profit_lock_sweep.py) can opt in explicitly -- that path is fine.
What is forbidden is the *implicit* params->baseline mapping.

Teeth:
  test_params_to_kwargs_drops_profit_lock -- feed _params_to_kwargs a params dict
      carrying profit_lock_* keys; assert NONE survive into the kwargs. Fails the
      moment someone adds `"profit_lock_threshold_pct": p["..."]` to the mapper.
  test_run_backtest_still_accepts_profit_lock -- the research opt-in path stays
      available (guards against over-correcting by deleting the kwargs entirely).

Run:  cd backtest && python -m pytest tests/test_profit_lock_not_in_baseline.py -q
"""

from __future__ import annotations

import inspect
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from lib.orchestrator import _params_to_kwargs, run_backtest  # noqa: E402

# Every profit-lock knob the params layer could be tempted to translate.
PROFIT_LOCK_FIELDS = [
    "profit_lock_threshold_pct",
    "profit_lock_mode",
    "profit_lock_trail_pct",
    "profit_lock_arm_pct",
    "profit_lock_lock_pct",
    "profit_lock_enabled",
    "chandelier_arm_pct",
    "chandelier_trail_pct",
]


def test_params_to_kwargs_drops_profit_lock() -> None:
    """A params dict carrying profit_lock_* must yield kwargs WITHOUT them."""
    params = {
        # a couple of legit fields so the mapper has normal work to do
        "premium_stop_pct": -0.08,
        "tp1_premium_pct": 0.50,
    }
    # Inject every profit-lock field with a non-default-looking value.
    for f in PROFIT_LOCK_FIELDS:
        params[f] = 0.42 if f.endswith("_pct") else "trailing"

    kwargs = _params_to_kwargs(params)

    leaked = sorted(k for k in kwargs if "profit_lock" in k or "chandelier" in k)
    assert not leaked, (
        "L156 GUARD: _params_to_kwargs mapped profit-lock knob(s) "
        f"{leaked} into the backtest baseline. Adding a profit_lock_* mapping "
        "biases EVERY future baseline negative (the chandelier is net-negative on "
        "trending IS windows). Keep profit-lock in heartbeat.md for live risk "
        "management only; leave it out of the params->baseline translation. The "
        "knobs remain on run_backtest() for explicit research sweeps."
    )


def test_run_backtest_still_accepts_profit_lock() -> None:
    """The explicit research opt-in must stay reachable (don't over-correct by
    deleting the kwargs from run_backtest)."""
    sig = inspect.signature(run_backtest)
    pl_params = [p for p in sig.parameters if "profit_lock" in p]
    assert pl_params, (
        "run_backtest no longer accepts any profit_lock_* kwarg -- the deliberate "
        "research path (autoresearch/profit_lock_sweep.py) is now broken. L156 "
        "forbids the IMPLICIT params->baseline mapping, not the explicit opt-in."
    )
