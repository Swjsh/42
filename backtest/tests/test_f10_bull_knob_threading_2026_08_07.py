"""Guard: bull filter-10 volume-multiplier knob threading (STAGED 2026-08-07).

Pins the plumbing staged in analysis/staged/f10-bull-knob-threading-2026-08-07.diff:
a dedicated ``filter_10_vol_multiplier_bull`` params key that drives bull filter 10's
``f10_vol_mult`` INDEPENDENTLY of the shared ``filter_9_vol_multiplier`` knob, in BOTH
engines (live heartbeat_core + backtest orchestrator, OP #4 no-drift).

Why: heartbeat_core.py (~647-654) and orchestrator.py (1030/1075) both tie
``f10_vol_mult = f9_vol_mult`` -- so the frozen prereg
analysis/recommendations/bull-f10-buyer-pressure-prereg-2026-08-04.json (which varies
f10_vol_mult ONLY) is UN-SHIPPABLE without this threading: flipping the shared key
would silently relax bear filter 9 too, a cell no battery ever tested.

RED-proof protocol (it IS the red proof):
  - PRE-apply : run with GAMMA_STAGED_2026_08_07=1  -> FAILS (helper/param absent).
  - POST-apply: same command                        -> PASSES.
  - The env gate keeps the standing suite green while the diff is staged; the apply
    checklist's final step applies analysis/staged/f10-guard-activation-2026-08-07.diff
    which deletes the gate so this guard runs unconditionally from then on.

Behavior-neutrality pin: when the dedicated key is ABSENT, both engines must resolve
to the shared f9 knob exactly as before (byte-identical fallback).
"""
from __future__ import annotations

import importlib
import inspect
import os
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# STAGED-GATE (deleted by f10-guard-activation-2026-08-07.diff at apply time):
pytestmark = pytest.mark.skipif(
    os.environ.get("GAMMA_STAGED_2026_08_07") != "1",
    reason="staged guard for f10-bull-knob-threading diff; run with "
           "GAMMA_STAGED_2026_08_07=1 (pre-apply=RED, post-apply=GREEN)",
)


@pytest.fixture(scope="module")
def hc():
    return importlib.import_module("heartbeat_core")


@pytest.fixture(scope="module")
def orch():
    from lib import orchestrator
    return orchestrator


# --- live engine: heartbeat_core -------------------------------------------------
class TestHeartbeatCoreHelper:
    def test_key_absent_falls_back_to_f9_knob(self, hc):
        assert hc._bull_f10_vol_mult({"filter_9_vol_multiplier": 0.55}) == 0.55

    def test_key_present_wins_bull_only(self, hc):
        p = {"filter_9_vol_multiplier": 0.7, "filter_10_vol_multiplier_bull": 0.5}
        assert hc._bull_f10_vol_mult(p) == 0.5

    def test_both_absent_signature_default(self, hc):
        assert hc._bull_f10_vol_mult({}) == 0.7

    def test_bull_kwargs_call_site_uses_helper(self, hc):
        src = inspect.getsource(hc)
        assert re.search(
            r'"bull_kwargs":\s*dict\(_times,\s*f10_vol_mult=_bull_f10_vol_mult\(account_params\)',
            src,
        ), "heartbeat_core bull_kwargs must route f10_vol_mult through _bull_f10_vol_mult"


# --- backtest engine: orchestrator ------------------------------------------------
class TestOrchestratorThreading:
    def test_params_to_kwargs_threads_key(self, orch):
        kw = orch._params_to_kwargs({"filter_10_vol_multiplier_bull": 0.5})
        assert kw.get("f10_vol_mult_bull") == 0.5

    def test_params_to_kwargs_absent_stays_absent(self, orch):
        kw = orch._params_to_kwargs({"filter_9_vol_multiplier": 0.7})
        assert "f10_vol_mult_bull" not in kw

    def test_run_backtest_accepts_param_default_none(self, orch):
        sig = inspect.signature(orch.run_backtest)
        assert "f10_vol_mult_bull" in sig.parameters
        assert sig.parameters["f10_vol_mult_bull"].default is None

    def test_both_bull_call_sites_use_fallback_expression(self, orch):
        """Primary evaluate_bullish_setup call AND the assert-agree mirror must carry
        the identical fallback expression -- a partial revert (one site only) REDs here
        and would also trip the engine-score assert at runtime."""
        src = inspect.getsource(orch)
        expr = ("f10_vol_mult=(f10_vol_mult_bull if f10_vol_mult_bull "
                "is not None else f9_vol_mult)")
        assert src.count(expr) == 2, (
            f"expected the bull f10 fallback expression at exactly 2 call sites, "
            f"found {src.count(expr)}"
        )
