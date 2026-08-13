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


def test_a_setup_disarmed_in_params_does_not_fire_on_the_fleet(strat):
    """THE REGRESSION. If this goes green-to-red, a params disarm is once again core-only and a
    killed setup is trading real fills on risky-1/risky-3."""
    armed = json.loads(PARAMS.read_text(encoding="utf-8")).get("extra_setup_exec_armed", {})
    assert armed.get("vwap_continuation") is False, (
        "fixture assumption broken: vwap_continuation is no longer disarmed in params. If it was "
        "deliberately RE-armed, that needs its own evidence and this test should be re-pointed.")
    assert _fired(strat, "VWAP_CONTINUATION") == [], (
        "vwap_continuation still fires on the fleet path despite params disarming it -- the "
        "2026-07-25 kill is half-landed again (cost -$1,046 over 18 days the first time)")


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
