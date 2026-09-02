"""Guards for quiet_mode.py's catch-up sweep (QUIET-HOLD-CATCH-UP-SWEEP, queue.md 2026-09-02).

THE SCAR. A trigger that fires while its task is Disabled is SKIPPED, and because the task
was Disabled rather than merely unavailable, Windows' StartWhenAvailable cannot recover it --
proven 7/7 over 2026-09-01 (Gamma_GuardsFull et al went dark exactly this way while every
State/LastTaskResult surface stayed green). Promoted from hygiene to gate-blocking the same
day: the go-live gate's registered prod-shadow window (2026-09-01..2026-09-29, PRE-REGISTERED
before any result existed) has zero slack against its own 20-scored-day bar.

THE DESIGN CONSTRAINTS THIS PINS (queue.md's own a-d):
  (a) allowlist, not a denylist -- CATCHUP_ELIGIBLE never contains an order-placing or
      broker-touching task.
  (b) HEAVY tasks are never restarted by the sweep.
  (c) only a hold-attributed DAILY trigger can produce a candidate.
  (d) capped starts, most-overdue first, and NEVER inside the weekday trading band.
Plus the idempotency property the sweep needed to be safe on a 5-minute enforcer cadence:
a task that already ran since the hold closed is never re-started.
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

# A Wednesday deep in the LOUD maintenance band -- never the trading day, never a weekend.
NOW = dt.datetime(2026, 9, 2, 0, 45, tzinfo=ET)
# A hold that closed 20 minutes before NOW, wide enough to have swallowed a 00:30 daily fire.
HOLD_START = dt.datetime(2026, 9, 2, 0, 7, tzinfo=ET)
HOLD_END = dt.datetime(2026, 9, 2, 0, 25, tzinfo=ET)
HOLDS = [(HOLD_START, HOLD_END)]


def _row(name: str, *, missed: int = 1, last_run: str | None = None,
         start_bound: str = "2026-08-20T00:30:00-04:00", kind: str = "MSFT_TaskDailyTrigger",
         state: str = "Ready") -> dict:
    return {
        "name": name, "state": state, "lastRun": last_run, "nextRun": None,
        "lastResult": 0, "missedRuns": missed, "triggerKind": kind,
        "startBound": start_bound, "repeat": None, "repeatFor": None,
    }


# ---------------------------------------------------------------------------------------
# Constraint (a): allowlist composition -- must never include a trading/order/broker task.
# ---------------------------------------------------------------------------------------

def test_allowlist_excludes_order_placing_names():
    banned_substrings = ("kalshi", "trader", "broker", "mirror", "conductor")
    hits = [n for n in qm.CATCHUP_ELIGIBLE
            if any(b in n.lower() for b in banned_substrings)]
    assert not hits, f"catch-up allowlist contains a trading/order-adjacent name: {hits}"


def test_allowlist_excludes_kalshi_by_name():
    """The exact example the queue item named as unsafe."""
    assert "Gamma_KalshiAuto" not in qm.CATCHUP_ELIGIBLE


def test_allowlist_is_nonempty():
    """An empty allowlist would make this whole feature a silent no-op."""
    assert qm.CATCHUP_ELIGIBLE


# ---------------------------------------------------------------------------------------
# Constraint (b): HEAVY tasks and ESSENTIAL tasks are never in the allowlist.
# ---------------------------------------------------------------------------------------

def test_allowlist_never_overlaps_heavy_tasks():
    assert not (qm.CATCHUP_ELIGIBLE & qm.HEAVY_TASKS), (
        "a HEAVY task in the catch-up allowlist would get started late and then killed "
        "mid-run by the next hold -- constraint (b)"
    )


def test_allowlist_never_overlaps_essential():
    """ESSENTIAL tasks are never disabled in the first place -- they cannot be 'caught up'."""
    assert not (qm.CATCHUP_ELIGIBLE & qm.ESSENTIAL)


# ---------------------------------------------------------------------------------------
# Constraint (d): never inside the weekday trading band.
# ---------------------------------------------------------------------------------------

def test_sweep_refuses_during_the_trading_band():
    trading_now = dt.datetime(2026, 9, 2, 10, 0, tzinfo=ET)  # Wed 10:00 ET
    assert qm._in_trading_band(trading_now)
    with patch.object(sts, "query_tasks") as mock_query:
        result = qm._catchup_sweep(trading_now)
    assert result == []
    mock_query.assert_not_called()  # must short-circuit before even touching the scheduler


# ---------------------------------------------------------------------------------------
# Core behaviour: a genuinely hold-attributed candidate gets started; a clean one does not.
# ---------------------------------------------------------------------------------------

def test_sweep_starts_a_hold_attributed_eligible_task():
    name = sorted(qm.CATCHUP_ELIGIBLE)[0]
    rows = [_row(name, missed=1, last_run=None)]
    with patch.object(qm, "LOG_FILE") as mock_log_file, \
         patch.object(sts, "query_tasks", return_value=rows), \
         patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
         patch.object(sts, "parse_quiet_holds", return_value=HOLDS), \
         patch.object(qm, "_ps") as mock_ps:
        mock_log_file.exists.return_value = False
        started = qm._catchup_sweep(NOW)
    assert started == [name]
    mock_ps.assert_called_once()
    assert f"'{name}'" in mock_ps.call_args[0][0]
    assert "Start-ScheduledTask" in mock_ps.call_args[0][0]


def test_sweep_skips_a_task_with_no_hold_attribution():
    """attribute_quiet_hold() returning None must never be guessed past."""
    name = sorted(qm.CATCHUP_ELIGIBLE)[0]
    rows = [_row(name, missed=1)]
    with patch.object(qm, "LOG_FILE") as mock_log_file, \
         patch.object(sts, "query_tasks", return_value=rows), \
         patch.object(sts, "attribute_quiet_hold", return_value=None), \
         patch.object(sts, "parse_quiet_holds", return_value=HOLDS), \
         patch.object(qm, "_ps") as mock_ps:
        mock_log_file.exists.return_value = False
        started = qm._catchup_sweep(NOW)
    assert started == []
    mock_ps.assert_not_called()


def test_sweep_ignores_a_task_not_on_the_allowlist():
    rows = [_row("Gamma_KalshiAuto", missed=1)]
    with patch.object(qm, "LOG_FILE") as mock_log_file, \
         patch.object(sts, "query_tasks", return_value=rows), \
         patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
         patch.object(sts, "parse_quiet_holds", return_value=HOLDS), \
         patch.object(qm, "_ps") as mock_ps:
        mock_log_file.exists.return_value = False
        started = qm._catchup_sweep(NOW)
    assert started == []
    mock_ps.assert_not_called()


def test_sweep_no_holds_means_no_candidates():
    """No parsed holds -- do not guess a cause into existence."""
    name = sorted(qm.CATCHUP_ELIGIBLE)[0]
    rows = [_row(name, missed=1)]
    with patch.object(qm, "LOG_FILE") as mock_log_file, \
         patch.object(sts, "query_tasks", return_value=rows), \
         patch.object(sts, "parse_quiet_holds", return_value=[]), \
         patch.object(qm, "_ps") as mock_ps:
        mock_log_file.exists.return_value = False
        started = qm._catchup_sweep(NOW)
    assert started == []
    mock_ps.assert_not_called()


# ---------------------------------------------------------------------------------------
# Idempotency: already-ran-since-the-hold candidates must not be re-started.
# ---------------------------------------------------------------------------------------

def test_sweep_skips_a_task_that_already_ran_since_the_hold_closed():
    name = sorted(qm.CATCHUP_ELIGIBLE)[0]
    ran_after_hold = (HOLD_END + dt.timedelta(minutes=5)).isoformat()
    rows = [_row(name, missed=1, last_run=ran_after_hold)]
    with patch.object(qm, "LOG_FILE") as mock_log_file, \
         patch.object(sts, "query_tasks", return_value=rows), \
         patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
         patch.object(sts, "parse_quiet_holds", return_value=HOLDS), \
         patch.object(qm, "_ps") as mock_ps:
        mock_log_file.exists.return_value = False
        started = qm._catchup_sweep(NOW)
    assert started == [], (
        "a task whose LastRunTime already moved past the hold has already been caught up "
        "(by this sweep or its own next natural trigger) -- restarting it again would let a "
        "5-minute enforcer cadence hammer the same task for as long as the hold stays in "
        "the 7-day attribution lookback"
    )
    mock_ps.assert_not_called()


def test_sweep_never_ran_sentinel_does_not_block_catchup():
    """Windows' 1999-11-30 never-ran sentinel must not be read as 'ran after the hold'."""
    name = sorted(qm.CATCHUP_ELIGIBLE)[0]
    rows = [_row(name, missed=1, last_run="1999-11-30T00:00:00-04:00")]
    with patch.object(qm, "LOG_FILE") as mock_log_file, \
         patch.object(sts, "query_tasks", return_value=rows), \
         patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
         patch.object(sts, "parse_quiet_holds", return_value=HOLDS), \
         patch.object(qm, "_ps") as mock_ps:
        mock_log_file.exists.return_value = False
        started = qm._catchup_sweep(NOW)
    assert started == [name]


# ---------------------------------------------------------------------------------------
# Constraint (d): capped, most-overdue first.
# ---------------------------------------------------------------------------------------

def test_sweep_caps_starts_and_orders_most_overdue_first():
    names = sorted(qm.CATCHUP_ELIGIBLE)
    assert len(names) > qm.CATCHUP_MAX_STARTS, (
        "this test needs more eligible names than the cap to prove capping actually bites"
    )
    # Missed-run counts descending is NOT alphabetical, so a pass here proves real sorting.
    rows = [_row(n, missed=(idx + 1)) for idx, n in enumerate(names)]
    with patch.object(qm, "LOG_FILE") as mock_log_file, \
         patch.object(sts, "query_tasks", return_value=rows), \
         patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
         patch.object(sts, "parse_quiet_holds", return_value=HOLDS), \
         patch.object(qm, "_ps") as mock_ps:
        mock_log_file.exists.return_value = False
        started = qm._catchup_sweep(NOW)
    assert len(started) == qm.CATCHUP_MAX_STARTS
    assert mock_ps.call_count == qm.CATCHUP_MAX_STARTS
    # Highest missedRuns (the last `qm.CATCHUP_MAX_STARTS` names, since idx ascends with names)
    expected_most_overdue = list(reversed(names))[:qm.CATCHUP_MAX_STARTS]
    assert started == expected_most_overdue


# ---------------------------------------------------------------------------------------
# Fail-open: a broken query or a broken start must never raise.
# ---------------------------------------------------------------------------------------

def test_sweep_fails_open_on_query_error():
    with patch.object(sts, "query_tasks", side_effect=RuntimeError("scheduler unreachable")):
        started = qm._catchup_sweep(NOW)  # must not raise
    assert started == []


def test_sweep_fails_open_on_a_single_start_failure_and_continues():
    names = sorted(qm.CATCHUP_ELIGIBLE)[:2]
    rows = [_row(n, missed=1) for n in names]

    def _flaky_ps(cmd: str) -> str:
        if names[0] in cmd:
            raise RuntimeError("powershell failed")
        return ""

    with patch.object(qm, "LOG_FILE") as mock_log_file, \
         patch.object(sts, "query_tasks", return_value=rows), \
         patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
         patch.object(sts, "parse_quiet_holds", return_value=HOLDS), \
         patch.object(qm, "_ps", side_effect=_flaky_ps):
        mock_log_file.exists.return_value = False
        started = qm._catchup_sweep(NOW)
    assert started == [names[1]], "one bad start must not stop the rest of the sweep"


def test_sweep_no_rows_returns_empty():
    with patch.object(sts, "query_tasks", return_value=None):
        assert qm._catchup_sweep(NOW) == []
    with patch.object(sts, "query_tasks", return_value=[]):
        assert qm._catchup_sweep(NOW) == []


# ---------------------------------------------------------------------------------------
# Wiring: go_loud() and go_research() must actually call the sweep, after the restore.
# ---------------------------------------------------------------------------------------

def test_go_loud_calls_catchup_sweep_after_restoring(tmp_path, monkeypatch):
    monkeypatch.setattr(qm, "RESTORE_FILE", tmp_path / "restore.json")
    monkeypatch.setattr(qm, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(qm, "LOG_FILE", tmp_path / "quiet-mode.log")
    qm._save_restore_list(["Gamma_Something"])

    call_order = []
    with patch.object(qm, "_set_tasks", side_effect=lambda names, enable: (
        call_order.append("restore"), len(names))[1]) as _mock_set, \
         patch.object(qm, "_catchup_sweep", side_effect=lambda now: (
             call_order.append("catchup"), [])[1]) as mock_sweep:
        rc = qm.go_loud()
    assert rc == 0
    assert call_order == ["restore", "catchup"], (
        "constraint (d): the sweep must run AFTER the restore so a bug in it can never "
        "block the re-enable"
    )
    mock_sweep.assert_called_once()


def test_go_research_calls_catchup_sweep(tmp_path, monkeypatch):
    monkeypatch.setattr(qm, "RESTORE_FILE", tmp_path / "restore.json")
    monkeypatch.setattr(qm, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(qm, "LOG_FILE", tmp_path / "quiet-mode.log")
    qm._save_restore_list([])

    with patch.object(qm, "_gamma_tasks", return_value={"Gamma_Something": qm.STATE_READY}), \
         patch.object(qm, "_set_tasks", return_value=0), \
         patch.object(qm, "_catchup_sweep", return_value=[]) as mock_sweep:
        rc = qm.go_research()
    assert rc == 0
    mock_sweep.assert_called_once()
