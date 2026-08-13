"""Guard: the exit-coverage detector must reproduce the 2026-08-13 bold-2 incident.

A detector that has only ever printed GREEN is not evidence of anything. This file replays the
measured incident as a fixture and asserts the detector fires on it -- and, just as importantly,
asserts it stays silent on the four FLAT arms that carried 34-121 minute exit-state ages at the
same instant. Alarming on staleness alone would have produced four false positives that day, so
the conjunction (held AND uncovered-or-stale) is the thing under test, not the staleness.

INCIDENT, measured (journal/2026-08-13.md):
    bold-2 held 5x SPY260813P00776000 @0.64, stop 0.32. /v2/positions and /v2/account hung at
    15s for that arm alone while /v2/clock and /v2/orders answered in 0.2s. exit-state went 14
    minutes without refreshing, no stop sell was attempted while the bid sat at 0.28 through the
    0.32 stop, and every tick logged exit=0. Recovered 13:12 ET: -$200 realized, -$40 of it
    attributable to the delay.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "exit_coverage_check.py"

PUT = "SPY260813P00776000"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("_exit_coverage_probe", MOD_PATH)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_exit_coverage_probe"] = m
    spec.loader.exec_module(m)
    return m


def _arm(mod, tmp_path, monkeypatch, *, held, tracked, age_min, read_ok=True):
    """Build one arm's world: what the broker returns, and what exit-state looks like."""
    fleet = tmp_path / "fleet"
    (fleet / "testarm").mkdir(parents=True, exist_ok=True)
    st = fleet / "testarm" / "exit-state.json"
    st.write_text(json.dumps({s: {"symbol": s} for s in tracked}), encoding="utf-8")
    old = time.time() - age_min * 60
    import os
    os.utime(st, (old, old))
    monkeypatch.setattr(mod, "FLEET", fleet)
    monkeypatch.setattr(
        mod, "read_positions",
        lambda arm, creds: (([{"symbol": s} for s in held], "ok") if read_ok else (None, "TimeoutError")),
    )
    return mod.assess_arm("testarm", {"key": "k", "secret": "s"}, time.time())


# --------------------------------------------------------------- the incident must fire


def test_the_bold2_incident_is_detected(mod, tmp_path, monkeypatch):
    """THE POINT OF THE FILE. Held position, exit-state 14 minutes cold -> must alarm."""
    row = _arm(mod, tmp_path, monkeypatch, held=[PUT], tracked=[PUT], age_min=14.0)
    assert row["status"] == "STALE", (
        f"the detector reports {row['status']} for the exact bold-2 incident state "
        "(holding a position with a 14-minute-cold exit-state). It would not have caught it.")
    assert "14.0 min" in row["why"]


def test_a_held_position_absent_from_exit_state_is_UNCOVERED(mod, tmp_path, monkeypatch):
    """The worse sibling: the exit manager does not know the position exists at all."""
    row = _arm(mod, tmp_path, monkeypatch, held=[PUT], tracked=[], age_min=0.1)
    assert row["status"] == "UNCOVERED"
    assert PUT in row["why"]


def test_a_failed_read_is_BLIND_and_never_FLAT(mod, tmp_path, monkeypatch):
    """C7. Treating an unreadable arm as empty is the defect being detected; reproducing it
    inside the detector would make it blind to its own failure mode."""
    row = _arm(mod, tmp_path, monkeypatch, held=[], tracked=[], age_min=0.1, read_ok=False)
    assert row["status"] == "BLIND", f"unreadable arm reported as {row['status']}"
    assert row["held"] is None, "an unreadable arm must not present as an empty position list"


# --------------------------------------------------------------- and must NOT false-positive


@pytest.mark.parametrize("age", [34.3, 50.3, 109.3, 121.3])
def test_flat_arms_with_stale_exit_state_do_NOT_alarm(mod, tmp_path, monkeypatch, age):
    """MEASURED 2026-08-13 13:46 ET: four flat arms carried exactly these exit-state ages, all
    correct -- nothing writes exit-state when flat. A staleness-only alarm fires 4 false
    positives here, which is why the conjunction exists."""
    row = _arm(mod, tmp_path, monkeypatch, held=[], tracked=[], age_min=age)
    assert row["status"] == "FLAT", f"flat arm at age {age}m alarmed as {row['status']}"


def test_a_held_and_freshly_tracked_position_is_OK(mod, tmp_path, monkeypatch):
    row = _arm(mod, tmp_path, monkeypatch, held=[PUT], tracked=[PUT], age_min=0.5)
    assert row["status"] == "OK"


def test_the_threshold_is_three_missed_ticks_not_arbitrary(mod):
    """The exit loop ticks every 60s; the threshold must be a small multiple of that, or it is
    either jittery or too slow to matter."""
    assert 2.0 <= mod.STALE_MIN <= 5.0, f"STALE_MIN={mod.STALE_MIN} is not ~3 missed 60s ticks"


def test_read_timeout_exceeds_the_measured_recovery_latency(mod):
    """During the incident a recovering /v2/positions took 24.0s. fleet_broker's own timeout is
    15s -- BELOW that -- which is why a recovering endpoint still failed its read. The detector
    must not inherit the same blind spot."""
    assert mod.READ_TIMEOUT_S > 24.0, (
        f"READ_TIMEOUT_S={mod.READ_TIMEOUT_S} is at or below the 24.0s recovery latency measured "
        "on 2026-08-13; the detector would go BLIND in exactly the window it exists to cover")
    assert mod.READ_ATTEMPTS >= 2, "a single attempt cannot distinguish a blip from an outage"


def test_it_is_read_only(mod):
    """It must never place, cancel, or mutate exit state -- it runs while positions are live."""
    src = MOD_PATH.read_text(encoding="utf-8")
    for banned in ("place_order", "market_sell", "close_position", "DELETE", '"POST"', "method='POST'"):
        assert banned not in src, f"exit_coverage_check contains {banned} -- it must be read-only"


def test_main_always_exits_zero(mod):
    """A monitor that can break its caller will eventually be removed from the schedule."""
    src = MOD_PATH.read_text(encoding="utf-8")
    assert "return 0  # fail-open by contract" in src


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
