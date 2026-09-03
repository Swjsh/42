"""Guard: WATCHER_OPEN_GRACE_TOO_SHORT (queue, filed 2026-09-02).

`WATCHER_OPEN_GRACE_MIN = 11` covered only to ~09:41 ET, but watcher-observations.jsonl's
real first-row time is NOT a stable ~09:41 -- measured over the last 10 sessions (first
bar_timestamp_et per date + its observed_at, converted MT-box-local -> ET via +2h) it
ranged 5.05-20.08 minutes past the 09:30 open:

    2026-08-20=20.07  2026-08-21=10.09  2026-08-24=10.08  2026-08-25=5.05
    2026-08-26=15.06  2026-08-27=10.06  2026-08-28=20.06  2026-08-31=5.10
    2026-09-01=5.09   2026-09-02=20.08

p95 of those 10 values = 20.08m; +2m margin = 22.08m -> the constant was set to 23. Source:
automation/state/watcher-observations.jsonl + its automation/state/archive/watcher-
observations-autoheal-*.jsonl rotations (the live file alone only retains ~3 days).

This guard pins the constant at-or-above the measured floor so a future edit cannot
silently shrink the grace back under real observed variance and reopen the false-RED
window (11 was itself a real observation once -- see the module's own 2026-06 comment --
so "it passed before" is not evidence it covers now)."""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_EH_PATH = _REPO / "setup" / "scripts" / "engine_health.py"
_spec = importlib.util.spec_from_file_location("engine_health_under_test_grace", _EH_PATH)
engine_health = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine_health)

# The measured floor this session established (p95=20.08m + 2m margin, see module docstring
# above WATCHER_OPEN_GRACE_MIN). A future re-measurement may raise this pin; it must never
# silently drop below it.
MEASURED_P95_PLUS_MARGIN_MIN = 22.08


def test_grace_constant_covers_the_measured_p95_plus_margin():
    assert engine_health.WATCHER_OPEN_GRACE_MIN >= MEASURED_P95_PLUS_MARGIN_MIN, (
        f"WATCHER_OPEN_GRACE_MIN={engine_health.WATCHER_OPEN_GRACE_MIN} regressed below the "
        f"measured p95(last 10 sessions)+2min floor of {MEASURED_P95_PLUS_MARGIN_MIN}m -- "
        "this reopens the 09:41-ish false-RED window the 2026-09-02 re-measurement closed."
    )


def _write_obs(state_dir: Path, bar_date_et: str) -> None:
    line = (
        '{"observed_at": "x", "bar_timestamp_et": "%sT15:45:00", '
        '"watcher_name": "t", "setup_name": "T"}\n' % bar_date_et
    )
    (state_dir / "watcher-observations.jsonl").write_text(line, encoding="utf-8")


@pytest.fixture()
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_health, "STATE", tmp_path)
    return tmp_path


def test_2026_09_02_actual_first_row_time_no_longer_false_reds(state_dir):
    """RED-PROOF of the exact incident: 2026-09-02 RED at 09:46 ('newest bar 2026-09-01'),
    GREEN at 09:56 once the producer wrote (nothing else changed in between). With the old
    11-min grace, 09:46 (16m into the open) already falls OUTSIDE the grace -> RED. With the
    fix, 16m < 23m -> still warming-up YELLOW, not a critical RED."""
    _write_obs(state_dir, "2026-09-01")  # yesterday's bar = the observed 09:46 state
    et = datetime(2026, 9, 2, 9, 46, 0)
    chk = engine_health.check_watcher_feed(market_open=True, et=et)
    assert chk["status"] == "YELLOW", chk
    assert chk["critical"] is False
    assert "warming up" in chk["detail"]


def test_still_reds_once_the_new_grace_budget_elapses():
    """The grace must never become amnesty for a genuinely dark producer -- a session open
    longer than WATCHER_OPEN_GRACE_MIN with yesterday's bar still on top must RED."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        orig_state = engine_health.STATE
        engine_health.STATE = state_dir
        try:
            _write_obs(state_dir, "2026-09-01")
            et = datetime(2026, 9, 2, 9, 30 + int(engine_health.WATCHER_OPEN_GRACE_MIN) + 5, 0)
            chk = engine_health.check_watcher_feed(market_open=True, et=et)
            assert chk["status"] == "RED", chk
            assert chk["critical"] is True
            assert "PRODUCER DARK" in chk["detail"]
        finally:
            engine_health.STATE = orig_state


def test_boundary_just_under_grace_is_still_warming_up(state_dir):
    _write_obs(state_dir, "2026-09-01")
    et = datetime(2026, 9, 2, 9, 30 + int(engine_health.WATCHER_OPEN_GRACE_MIN) - 1, 0)
    chk = engine_health.check_watcher_feed(market_open=True, et=et)
    assert chk["status"] == "YELLOW", chk
    assert chk["critical"] is False


def test_boundary_at_grace_is_red():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        orig_state = engine_health.STATE
        engine_health.STATE = state_dir
        try:
            _write_obs(state_dir, "2026-09-01")
            et = datetime(2026, 9, 2, 9, 30 + int(engine_health.WATCHER_OPEN_GRACE_MIN), 0)
            chk = engine_health.check_watcher_feed(market_open=True, et=et)
            assert chk["status"] == "RED", chk
        finally:
            engine_health.STATE = orig_state


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
