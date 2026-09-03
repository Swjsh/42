"""Guards for quiet_mode.py's HEAVY catch-up tier (GUARDS-FULL-NEVER-RUNS-ON-A-GAMING-EVENING,
queue.md 2026-09-02, implemented 2026-09-03).

THE SCAR. Live repro 2026-09-03 00:22 ET: `Gamma_GuardsFull` (daily 23:15 ET) showed
`Missed=1, LastRun 2026-09-02 08:45 MT` -- the 23:15 fire was skipped while quiet mode's
presence hold (J gaming) had it Disabled, and the light catch-up sweep
(QUIET-HOLD-CATCH-UP-SWEEP) deliberately excluded it as HEAVY. So the ~11,700-test full
regression suite had no verdict on any evening J games, and it had already gone dark
08-31 -> 09-02 the same way.

THE CORRECTED JUDGMENT this pins: the ORIGINAL exclusion comment's stated reason --
"would hit the same 'started, then killed mid-run by the next hold' failure" -- was a
PROVENANCE ERROR. `_stop_heavy_processes()` only kills a process whose CommandLine matches
HEAVY_PROCESS_MARKERS (kitchen_daemon.py, autoresearch., multiprocessing-fork,
shotgun_scalper, _grind); a pytest run launched by guard_runner_full.py matches none of
them, so a later hold DISABLES the scheduled task (blocking its next trigger) but never
kills an in-flight run. The real constraint is only "never launch a core-pegger while J is
at the machine", which the presence gate already encodes -- so Gamma_GuardsFull moved into
its own HEAVY_CATCHUP_ELIGIBLE tier instead of being excluded outright.

THE DESIGN CONSTRAINTS THIS PINS (queue item's own a-f):
  (a) same hold-attribution as the light tier -- a genuine daily-trigger miss inside a hold.
  (b) no presence hold active now AND none in the last 15 minutes (reusing presence_hold(),
      which folds in the PRESENCE_LINGER_MIN window via _presence_linger).
  (c) ET inside the narrow 23:00-06:30 heavy-safe band -- never the weekend research band,
      never the weekday trading band.
  (d) no HEAVY_PROCESS_MARKERS process currently running.
  (e) idempotency -- a task that already ran since the hold closed is skipped.
  (f) counts against the shared CATCHUP_MAX_STARTS cap and runs LAST, after the light tier.

Also pinned: the light tier (CATCHUP_ELIGIBLE) is completely unaffected by this change.
"""
from __future__ import annotations

import datetime as dt
import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

qm = importlib.import_module("quiet_mode")
sts = importlib.import_module("scheduled_task_staleness")
ET = qm.ET

GUARDS_FULL = "Gamma_GuardsFull"

# 00:45 ET Wednesday -- deep inside the 23:00-06:30 heavy band, never trading, never weekend.
NOW = dt.datetime(2026, 9, 2, 0, 45, tzinfo=ET)
HOLD_START = dt.datetime(2026, 9, 2, 0, 7, tzinfo=ET)
HOLD_END = dt.datetime(2026, 9, 2, 0, 25, tzinfo=ET)
HOLDS = [(HOLD_START, HOLD_END)]


def _row(name: str, *, missed: int = 1, last_run: str | None = None,
         start_bound: str = "2026-08-20T23:15:00-04:00", kind: str = "MSFT_TaskDailyTrigger",
         state: str = "Ready") -> dict:
    return {
        "name": name, "state": state, "lastRun": last_run, "nextRun": None,
        "lastResult": 0, "missedRuns": missed, "triggerKind": kind,
        "startBound": start_bound, "repeat": None, "repeatFor": None,
    }


@pytest.fixture(autouse=True)
def _isolate_log_file(monkeypatch, tmp_path):
    """MANDATORY isolation: _log() always appends to LOG_FILE on disk, with no mock unless
    one is installed. A first cut of this file omitted this in several tests and leaked real
    lines (fake 'game.exe' presence holds, fabricated 'started Gamma_GuardsFull' entries)
    into the LIVE automation/state/quiet-mode.log during a live pytest run 2026-09-03 --
    caught by noticing timestamps in the live log matching this file's own test names.
    Autouse so no test in this file can reintroduce that leak by omission."""
    monkeypatch.setattr(qm, "LOG_FILE", tmp_path / "quiet-mode.log")


def _ok_gates(monkeypatch):
    """Force constraints (b)/(c)/(d) all GREEN so a test can isolate the one it cares about."""
    monkeypatch.setattr(qm, "_in_loud_heavy_band", lambda now: True)
    monkeypatch.setattr(qm, "presence_hold", lambda now=None: None)
    monkeypatch.setattr(qm, "_heavy_process_running", lambda: False)


# ---------------------------------------------------------------------------------------
# Composition: the heavy tier is a strictly separate, single-member (for now) allowlist.
# ---------------------------------------------------------------------------------------

def test_heavy_allowlist_is_guards_full_only():
    assert qm.HEAVY_CATCHUP_ELIGIBLE == {GUARDS_FULL}


def test_heavy_allowlist_never_overlaps_the_light_allowlist():
    assert not (qm.HEAVY_CATCHUP_ELIGIBLE & qm.CATCHUP_ELIGIBLE), (
        "the two tiers must stay independent -- merging them would let an edit to one "
        "silently widen the other's safety envelope"
    )


def test_heavy_allowlist_never_overlaps_essential():
    assert not (qm.HEAVY_CATCHUP_ELIGIBLE & qm.ESSENTIAL)


def test_guards_nightly_and_gym_session_are_not_in_the_heavy_tier():
    """The queue item's own scope limit: only Gamma_GuardsFull, nothing else copied in."""
    assert "Gamma_GuardsNightly" not in qm.HEAVY_CATCHUP_ELIGIBLE
    assert "Gamma_GymSession" not in qm.HEAVY_CATCHUP_ELIGIBLE


# ---------------------------------------------------------------------------------------
# Constraint (c): the 23:00-06:30 band function itself.
# ---------------------------------------------------------------------------------------

class TestHeavyBand:
    @pytest.mark.parametrize("hour", [23, 0, 1, 5])
    def test_inside_band_hours(self, hour):
        now = dt.datetime(2026, 9, 2, hour, 0, tzinfo=ET)  # Wednesday
        assert qm._in_loud_heavy_band(now) is True

    def test_inside_band_at_06_29(self):
        now = dt.datetime(2026, 9, 2, 6, 29, tzinfo=ET)
        assert qm._in_loud_heavy_band(now) is True

    def test_outside_band_at_06_30(self):
        now = dt.datetime(2026, 9, 2, 6, 30, tzinfo=ET)
        assert qm._in_loud_heavy_band(now) is False

    def test_outside_band_at_22_59(self):
        now = dt.datetime(2026, 9, 2, 22, 59, tzinfo=ET)
        assert qm._in_loud_heavy_band(now) is False

    def test_never_true_during_the_weekday_trading_band(self):
        for hour in (8, 12, 17):
            now = dt.datetime(2026, 9, 2, hour, 0, tzinfo=ET)  # Wednesday
            assert qm._in_trading_band(now) is True
            assert qm._in_loud_heavy_band(now) is False

    def test_never_true_during_the_weekend_research_band(self):
        sat = dt.datetime(2026, 9, 5, 12, 0, tzinfo=ET)  # Saturday
        assert qm.in_research_band(sat) is True
        assert qm._in_loud_heavy_band(sat) is False


# ---------------------------------------------------------------------------------------
# Constraint (b)/(c)/(d): each gate individually blocks the start.
# ---------------------------------------------------------------------------------------

class TestEachGateBlocksIndependently:
    def test_band_gate_blocks(self, monkeypatch):
        monkeypatch.setattr(qm, "_in_loud_heavy_band", lambda now: False)
        monkeypatch.setattr(qm, "presence_hold", lambda now=None: None)
        monkeypatch.setattr(qm, "_heavy_process_running", lambda: False)
        rows = [_row(GUARDS_FULL)]
        with patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
             patch.object(qm, "_ps") as mock_ps:
            started = qm._heavy_catchup_pass(rows, HOLDS, HOLD_END, NOW)
        assert started == []
        mock_ps.assert_not_called()

    def test_presence_hold_active_now_blocks(self, monkeypatch):
        monkeypatch.setattr(qm, "_in_loud_heavy_band", lambda now: True)
        monkeypatch.setattr(qm, "presence_hold", lambda now=None: "fullscreen app in foreground (game.exe)")
        monkeypatch.setattr(qm, "_heavy_process_running", lambda: False)
        rows = [_row(GUARDS_FULL)]
        with patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
             patch.object(qm, "_ps") as mock_ps:
            started = qm._heavy_catchup_pass(rows, HOLDS, HOLD_END, NOW)
        assert started == []
        mock_ps.assert_not_called()

    def test_presence_linger_within_15_minutes_blocks(self, monkeypatch):
        """presence_hold() itself folds in the 15-minute linger -- proving this reuses it
        rather than re-deriving a foreground probe."""
        monkeypatch.setattr(qm, "_in_loud_heavy_band", lambda now: True)
        monkeypatch.setattr(qm, "_heavy_process_running", lambda: False)
        monkeypatch.setattr(qm, "_in_trading_band", lambda now=None: False)
        monkeypatch.setattr(qm, "_manual_hold", lambda: None)
        monkeypatch.setattr(qm, "_foreground_fullscreen", lambda: None)
        monkeypatch.setattr(qm, "_presence_linger", lambda now: "linger: game.exe was foreground 5m ago (<15m)")
        rows = [_row(GUARDS_FULL)]
        with patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
             patch.object(qm, "_ps") as mock_ps:
            started = qm._heavy_catchup_pass(rows, HOLDS, HOLD_END, NOW)
        assert started == [], "a sighting inside the last 15 minutes must still hold the heavy tier"
        mock_ps.assert_not_called()

    def test_heavy_process_already_running_blocks(self, monkeypatch):
        monkeypatch.setattr(qm, "_in_loud_heavy_band", lambda now: True)
        monkeypatch.setattr(qm, "presence_hold", lambda now=None: None)
        monkeypatch.setattr(qm, "_heavy_process_running", lambda: True)
        rows = [_row(GUARDS_FULL)]
        with patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
             patch.object(qm, "_ps") as mock_ps:
            started = qm._heavy_catchup_pass(rows, HOLDS, HOLD_END, NOW)
        assert started == [], "a HEAVY_PROCESS_MARKERS process already running must defer, not stack"
        mock_ps.assert_not_called()

    def test_no_hold_attribution_blocks(self, monkeypatch):
        _ok_gates(monkeypatch)
        rows = [_row(GUARDS_FULL)]
        with patch.object(sts, "attribute_quiet_hold", return_value=None), \
             patch.object(qm, "_ps") as mock_ps:
            started = qm._heavy_catchup_pass(rows, HOLDS, HOLD_END, NOW)
        assert started == []
        mock_ps.assert_not_called()

    def test_already_ran_since_hold_closed_blocks(self, monkeypatch):
        _ok_gates(monkeypatch)
        ran_after_hold = (HOLD_END + dt.timedelta(minutes=5)).isoformat()
        rows = [_row(GUARDS_FULL, last_run=ran_after_hold)]
        with patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
             patch.object(qm, "_ps") as mock_ps:
            started = qm._heavy_catchup_pass(rows, HOLDS, HOLD_END, NOW)
        assert started == [], "constraint (e): idempotency must match the light tier"
        mock_ps.assert_not_called()

    def test_not_on_the_heavy_allowlist_blocks(self, monkeypatch):
        _ok_gates(monkeypatch)
        rows = [_row("Gamma_GuardsNightly")]
        with patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
             patch.object(qm, "_ps") as mock_ps:
            started = qm._heavy_catchup_pass(rows, HOLDS, HOLD_END, NOW)
        assert started == []
        mock_ps.assert_not_called()


# ---------------------------------------------------------------------------------------
# All gates satisfied -> actually starts, via Start-ScheduledTask.
# ---------------------------------------------------------------------------------------

def test_all_gates_satisfied_starts_guards_full(monkeypatch):
    _ok_gates(monkeypatch)
    rows = [_row(GUARDS_FULL, last_run=None)]
    with patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
         patch.object(qm, "_ps") as mock_ps:
        started = qm._heavy_catchup_pass(rows, HOLDS, HOLD_END, NOW)
    assert started == [GUARDS_FULL]
    mock_ps.assert_called_once()
    assert f"'{GUARDS_FULL}'" in mock_ps.call_args[0][0]
    assert "Start-ScheduledTask" in mock_ps.call_args[0][0]


def test_never_ran_sentinel_does_not_block_heavy_catchup(monkeypatch):
    _ok_gates(monkeypatch)
    rows = [_row(GUARDS_FULL, last_run="1999-11-30T00:00:00-04:00")]
    with patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
         patch.object(qm, "_ps") as mock_ps:
        started = qm._heavy_catchup_pass(rows, HOLDS, HOLD_END, NOW)
    assert started == [GUARDS_FULL]


def test_start_failure_fails_open_to_empty_list(monkeypatch):
    _ok_gates(monkeypatch)
    rows = [_row(GUARDS_FULL)]
    with patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
         patch.object(qm, "_ps", side_effect=RuntimeError("powershell failed")):
        started = qm._heavy_catchup_pass(rows, HOLDS, HOLD_END, NOW)  # must not raise
    assert started == []


def test_heavy_process_probe_failure_fails_closed_not_open(monkeypatch):
    """Deliberate deviation from this file's usual fail-open doctrine: an unknown process
    state must BLOCK a new heavy start, not permit one."""
    monkeypatch.setattr(qm, "_in_loud_heavy_band", lambda now: True)
    monkeypatch.setattr(qm, "presence_hold", lambda now=None: None)
    with patch.object(qm, "_ps", side_effect=RuntimeError("powershell unreachable")):
        assert qm._heavy_process_running() is True


# ---------------------------------------------------------------------------------------
# Constraint (f): wired into _catchup_sweep, runs LAST, shares the cap with the light tier.
# ---------------------------------------------------------------------------------------

class TestWiredIntoCatchupSweep:
    def test_heavy_start_only_attempted_after_light_tier_processed(self, monkeypatch):
        """No light-eligible rows present -> the heavy pass still runs and can start alone."""
        _ok_gates(monkeypatch)
        rows = [_row(GUARDS_FULL, last_run=None)]
        with patch.object(qm, "LOG_FILE") as mock_log_file, \
             patch.object(sts, "query_tasks", return_value=rows), \
             patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
             patch.object(sts, "parse_quiet_holds", return_value=HOLDS), \
             patch.object(qm, "_ps") as mock_ps:
            mock_log_file.exists.return_value = False
            started = qm._catchup_sweep(NOW)
        assert started == [GUARDS_FULL]
        mock_ps.assert_called_once()

    def test_heavy_tier_gets_no_budget_once_light_tier_fills_the_cap(self, monkeypatch):
        """Constraint (f): heavy runs LAST and only with leftover budget."""
        _ok_gates(monkeypatch)
        light_names = sorted(qm.CATCHUP_ELIGIBLE)[:qm.CATCHUP_MAX_STARTS]
        rows = ([_row(n, missed=10) for n in light_names]
                + [_row(GUARDS_FULL, missed=1, last_run=None)])
        with patch.object(qm, "LOG_FILE") as mock_log_file, \
             patch.object(sts, "query_tasks", return_value=rows), \
             patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
             patch.object(sts, "parse_quiet_holds", return_value=HOLDS), \
             patch.object(qm, "_ps") as mock_ps:
            mock_log_file.exists.return_value = False
            started = qm._catchup_sweep(NOW)
        assert len(started) == qm.CATCHUP_MAX_STARTS
        assert GUARDS_FULL not in started, (
            "the light tier already used the entire shared cap -- heavy must not exceed it"
        )
        assert mock_ps.call_count == qm.CATCHUP_MAX_STARTS

    def test_light_tier_unaffected_by_the_heavy_tier_existing(self):
        """The light-tier-only regression file's own assertions still hold verbatim (run
        together with this file as part of the report)."""
        name = sorted(qm.CATCHUP_ELIGIBLE)[0]
        rows = [_row(name, last_run=None)]
        # Force the heavy gates closed so only the light tier can possibly start anything --
        # proves the two tiers are independent, not that the heavy tier happens to agree.
        with patch.object(qm, "_in_loud_heavy_band", lambda now: False), \
             patch.object(qm, "LOG_FILE") as mock_log_file, \
             patch.object(sts, "query_tasks", return_value=rows), \
             patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
             patch.object(sts, "parse_quiet_holds", return_value=HOLDS), \
             patch.object(qm, "_ps") as mock_ps:
            mock_log_file.exists.return_value = False
            started = qm._catchup_sweep(NOW)
        assert started == [name]


# ---------------------------------------------------------------------------------------
# go_loud() / go_research() status-JSON wiring: caught_up_heavy is populated and separate
# from caught_up (light).
# ---------------------------------------------------------------------------------------

def test_go_loud_writes_caught_up_heavy_separately(tmp_path, monkeypatch):
    monkeypatch.setattr(qm, "RESTORE_FILE", tmp_path / "restore.json")
    monkeypatch.setattr(qm, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(qm, "LOG_FILE", tmp_path / "quiet-mode.log")
    qm._save_restore_list(["Gamma_Something"])

    with patch.object(qm, "_set_tasks", return_value=1), \
         patch.object(qm, "_catchup_sweep", return_value=["Gamma_McpDailyAudit", GUARDS_FULL]):
        rc = qm.go_loud()
    assert rc == 0

    import json as _json
    status = _json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["caught_up"] == ["Gamma_McpDailyAudit"]
    assert status["caught_up_heavy"] == [GUARDS_FULL]
