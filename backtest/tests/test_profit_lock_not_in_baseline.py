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
# NOTE: production params.json uses the v15_ prefix (v15_profit_lock_mode etc.) --
# those REAL key names are included so this guard exercises the actual production
# surface, not a synthetic un-prefixed alias the mapper never sees (the L197/G16
# "the test exercised a key production doesn't use" vacuousness class).
PROFIT_LOCK_FIELDS = [
    "profit_lock_threshold_pct",
    "profit_lock_mode",
    "profit_lock_trail_pct",
    "profit_lock_arm_pct",
    "profit_lock_lock_pct",
    "profit_lock_enabled",
    "chandelier_arm_pct",
    "chandelier_trail_pct",
    # the ACTUAL production param names (automation/state/params.json):
    "v15_profit_lock_mode",
    "v15_profit_lock_threshold_pct",
    "v15_profit_lock_trail_pct",
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


def test_real_params_chandelier_keys_dropped() -> None:
    """Real-data bite (2026-07-02 frame-audit): feed the ACTUAL live params.json
    through _params_to_kwargs and assert its v15_profit_lock_* / chandelier keys
    do NOT survive. This is the anti-misdiagnosis pin.

    Provenance: the PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB queue item (from
    PHASEC RESULTS.md caveat 7) re-labelled this INTENTIONAL, L156-encoded drop
    as a "C14 dead-knob to fix". It is not a dead knob: the chandelier is
    regime-conditional (net-negative on the volume-dominant trending windows),
    so mapping it into the baseline biases EVERY candidate comparison negative.
    The absence is ALSO symmetric across A/B arms (baseline + candidate both go
    through this mapper), so it does not corrupt relative verdicts. A future
    fire that "fixes" the mapping to include the chandelier REDs here.
    """
    import json

    params_path = REPO / "automation" / "state" / "params.json"
    params = json.loads(params_path.read_text(encoding="utf-8"))

    real_pl_keys = sorted(
        k for k in params if "profit_lock" in k or "chandelier" in k
    )
    # Non-vacuous: the live params.json must actually carry chandelier keys, else
    # this test proves nothing. If production drops them entirely, update this.
    assert real_pl_keys, (
        "live params.json carries no profit_lock/chandelier keys -- this "
        "real-data guard is now vacuous; re-anchor it or remove it."
    )

    kwargs = _params_to_kwargs(params)
    leaked = sorted(k for k in kwargs if "profit_lock" in k or "chandelier" in k)
    assert not leaked, (
        "L156 GUARD (real-params bite): the live params.json chandelier keys "
        f"{real_pl_keys} leaked into backtest kwargs as {leaked}. This is the "
        "PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB misdiagnosis applied -- the drop "
        "is BY DESIGN (L156), not a dead knob. Do NOT map the chandelier into "
        "the params->baseline path."
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
