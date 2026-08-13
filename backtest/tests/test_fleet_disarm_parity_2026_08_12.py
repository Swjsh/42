"""Guard: a DISARM recorded in params must reach the FLEET arms, not just core (2026-08-12).

WHAT HAPPENED. vwap_continuation was disarmed on 2026-07-25 by commit e0356fb1, whose own message
reads: "DISARM vwap_continuation + vix_regime_dayside (0-for-12 live, -$357, caused 2 of 3 losing
days)". That commit touched ONLY automation/state/params.json.

params.json governs the CORE arms (safe-2, bold-2). The FLEET arms never read it: strategies.fired()
matched on REGISTRY membership alone and build_shared_signal.py hardcodes RUN_VWAP = True. So a kill
made for cause landed on 2 of 5 arms, and the setup kept trading on the rest for 18 days.

MEASURED from journal/trades.csv, fills dated after the disarm:
    risky-3   26 fills   -$646
    risky-1   17 fills   -$400
    TOTAL     43 fills  -$1,046      still filling on 2026-08-12

The half-landed kill cost roughly 3x the -$357 that motivated the kill.

L287 class: an imperative fix applied to ONE surface expires the moment a second surface
regenerates the same decision independently. The fix is therefore structural -- params
extra_setup_exec_armed is now the single switch governing BOTH paths -- and this guard exists so
the next disarm cannot half-land the same way.

THE ASYMMETRY THAT MUST NOT ROT: absence != disarmed. RIBBON_RIDE is the CORE setup and correctly
appears nowhere in extra_setup_exec_armed. If the check ever keys off absence instead of an
explicit False, it disarms the entire engine. That case is pinned below.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STRATEGIES = REPO / "automation" / "state" / "fleet" / "strategies.py"
PARAMS = REPO / "automation" / "state" / "params.json"


@pytest.fixture(scope="module")
def strat():
    spec = importlib.util.spec_from_file_location("_fleet_strategies_probe", STRATEGIES)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_fleet_strategies_probe"] = mod  # dataclass needs the module registered
    spec.loader.exec_module(mod)
    return mod


def _fired(strat, setup: str) -> list[str]:
    return [s.name for s in strat.fired(
        {"passed": True, "triggers_fired": ["x"], "setup_name": setup})]


# --------------------------------------------------------------- the disarm reaches the fleet


def test_a_disarmed_setup_can_never_be_SELECTED_for_an_order(strat):
    """THE REGRESSION, asserted at the point that actually places orders.

    RE-POINTED 2026-08-12, same session, after two wrong placements of this fix:
      1. strategies.fired() -- INERT in production. build_shared_signal always emits a top-level
         "strategies" key, so plan_all takes the FIX2 branch and fired() is never reached live.
      2. _plan_from_strategies -- money-correct but wrong layer: it suppressed the PLAN, breaking
         a dozen exit-A/B tests that legitimately use vwap as the second strategy to prove
         per-arm exit-shape plumbing.

    select_plan is where exactly one plan becomes an order, so it is the narrowest cut that
    protects money while leaving planning observable.
    """
    import importlib.util as _iu
    import sys as _sys
    fleet_dir = REPO / "automation" / "state" / "fleet"
    if str(fleet_dir) not in _sys.path:
        _sys.path.insert(0, str(fleet_dir))
    spec = _iu.spec_from_file_location("_fleet_exec_probe", fleet_dir / "fleet_executor.py")
    fx = _iu.module_from_spec(spec)
    _sys.modules["_fleet_exec_probe"] = fx
    spec.loader.exec_module(fx)

    armed = json.loads(PARAMS.read_text(encoding="utf-8")).get("extra_setup_exec_armed", {})
    assert armed.get("vwap_continuation") is False, (
        "fixture assumption broken: vwap_continuation is no longer disarmed in params. If it was "
        "deliberately RE-armed, that needs its own evidence and this test should be re-pointed.")

    def _plan(strategy_name):
        return fx.EntryPlan("risky-1", "ENTER", "C", "VWAP_CONTINUATION", 600, 1.0, "ELITE",
                            "test", strategy=strategy_name)

    # A disarmed strategy alone -> nothing selectable, so no order can be built from it.
    only_disarmed = fx.select_plan([_plan("vwap_continuation")])
    assert only_disarmed is None or only_disarmed.action != "ENTER", (
        "a DISARMED strategy was selected for an order -- the 2026-07-25 kill is half-landed "
        "again (it cost -$1,046 across 43 fills over 18 days the first time)")

    # Mixed: the armed strategy must still win, proving we suppressed the right one only.
    mixed = fx.select_plan([_plan("vwap_continuation"), _plan("ribbon_ride")])
    assert mixed is not None and mixed.strategy == "ribbon_ride"


def test_the_legacy_path_stays_unreachable_in_production(strat):
    """WHY fired() carries no disarm: production never reaches it. plan_all branches on a
    top-level "strategies" key and build_shared_signal ALWAYS emits one, so the legacy
    fired() branch is dead in production. If that ever stops being true, this test goes RED and
    the legacy branch needs its own disarm before it can trade a killed setup."""
    bss = (REPO / "automation" / "state" / "fleet" / "build_shared_signal.py").read_text(
        encoding="utf-8")
    assert 'sig["strategies"] =' in bss, (
        "build_shared_signal no longer always emits a top-level 'strategies' key -- plan_all may "
        "now take the LEGACY fired() branch, which carries NO disarm. Add one before shipping.")
    live = REPO / "automation" / "state" / "fleet" / "shared-signal.json"
    if live.exists():
        assert "strategies" in json.loads(live.read_text(encoding="utf-8")), (
            "the live shared-signal.json has no 'strategies' key -- production is on the legacy "
            "branch, which has no disarm")


def test_fired_actually_consults_params(strat):
    """Pins the mechanism, not just today's outcome -- removing the read would pass the test above
    only because REGISTRY happened to change."""
    src = STRATEGIES.read_text(encoding="utf-8")
    assert "extra_setup_exec_armed" in src, "strategies.py no longer reads the arm switch at all"
    assert "_disarmed_setups" in src


def test_the_params_path_actually_resolves(strat):
    """The first cut of this fix built automation/automation/state/params.json (miscounted
    parents[]), failed to read, and fell through the fail-open path -- the disarm would have
    silently done NOTHING while looking installed. A non-empty disarmed set proves the read works;
    an empty one here would mean either a bad path or a genuinely empty policy."""
    got = strat._disarmed_setups()
    assert got, ("_disarmed_setups() is empty -- either params.json is unreadable from this "
                 "module (check the parents[] count) or nothing is disarmed")
    assert "vwap_continuation" in got


# --------------------------------------------------------------- what must NOT be disarmed


@pytest.mark.parametrize("core_setup", [
    "BEARISH_REJECTION_RIDE_THE_RIBBON",
    "BULLISH_RECLAIM_RIDE_THE_RIBBON",
])
def test_the_core_setup_is_never_disarmed_by_absence(strat, core_setup):
    """ABSENCE IS NOT DISARMED. ribbon_ride is the core edge and appears nowhere in
    extra_setup_exec_armed. A check keyed on absence rather than an explicit False would silently
    disarm the entire engine -- the worst possible failure of this guard's own mechanism."""
    assert _fired(strat, core_setup) == ["ribbon_ride"], (
        f"{core_setup} no longer fires -- the disarm check is keying off ABSENCE from "
        "extra_setup_exec_armed and has switched off the core engine")


def test_an_explicitly_armed_setup_still_fires(strat):
    armed = json.loads(PARAMS.read_text(encoding="utf-8")).get("extra_setup_exec_armed", {})
    assert armed.get("vwap_reclaim_failed_break") is True, "fixture assumption broken"
    assert _fired(strat, "VWAP_RECLAIM_FAILED_BREAK") == ["vwap_reclaim_failed_break"]


# --------------------------------------------------------------- failure behaviour


def test_it_fails_OPEN_when_params_cannot_be_read(strat, monkeypatch, capsys):
    """A guard that halts trading because a config read hiccupped is worse than the bug it
    prevents (OP-25). Fail open, but say so out loud -- never silently."""
    import pathlib

    real_read = pathlib.Path.read_text

    def _boom(self, *a, **k):
        if self.name == "params.json":
            raise OSError("simulated unreadable params")
        return real_read(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", _boom)
    assert strat._disarmed_setups() == set()
    assert "WARN" in capsys.readouterr().out, "failed open SILENTLY -- must announce it"


def test_registry_still_contains_the_disarmed_strategy(strat):
    """Scope guard: we disarmed via the switch, we did NOT delete the strategy. Deleting it would
    lose the definition and make re-arming a code change instead of a config flip."""
    assert any(s.name == "vwap_continuation" for s in strat.REGISTRY), (
        "vwap_continuation was removed from REGISTRY rather than disarmed via params -- re-arming "
        "is no longer a one-flag operation")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
