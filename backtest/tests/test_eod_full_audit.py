"""Tests for setup/scripts/eod_full_audit.py -- the FULL-AUDIT generator.

Root incident (2026-07-14, strategy/candidates/_validator-inbox/2026-07-14-tick-audit-
zero-count-bug.md, finding #3): the ENGINE section read the dead root decisions.jsonl
(unwritten since 2026-06-25) and the FLEET section globbed the frozen fleet/decisions/
mirror dir (a WATCH-DEMO fixture snapshot) -- both silently returned 0 rows on a day the
live engine ran 772+ real decisions. These tests pin the fix: real ticks are counted from
core-decisions.jsonl / fleet/<arm>/decisions.jsonl, using ts_et as the date key (the only
timestamp field those rows carry), with a non-vacuity staleness guard for a genuinely dead
source path.

`setup/scripts` is added to sys.path the same way eod_full_audit.py itself does (it inserts
REPO/setup/scripts for et_clock) -- these tests import the module directly by path so they
don't depend on backtest/'s package layout.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "setup" / "scripts" / "eod_full_audit.py"


def _load_module():
    """Import eod_full_audit.py fresh (module-level TODAY/STATE are computed at import
    time from the real clock/repo -- tests monkeypatch them per-test rather than relying
    on a cached import)."""
    spec = importlib.util.spec_from_file_location("eod_full_audit_under_test", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod():
    m = _load_module()
    yield m
    sys.modules.pop("eod_full_audit_under_test", None)


# ---------------------------------------------------------------------------
# _today(): the shared date-matching primitive (the inbox item's "primitive to test")
# ---------------------------------------------------------------------------

def test_today_matches_ts_et_prefix_when_no_date_field(mod):
    mod.TODAY = "2026-07-13"
    rows = [
        {"ts_et": "2026-07-13T15:55:05", "account": "safe", "action": "HOLD"},
        {"ts_et": "2026-07-13T09:32:03.657473-04:00", "account": "bold", "action": "HOLD"},
        {"ts_et": "2026-07-12T15:55:05", "account": "safe", "action": "HOLD"},  # different day
    ]
    out = mod._today(rows)
    assert len(out) == 2, f"expected 2 rows matching 2026-07-13, got {len(out)}"


def test_today_still_matches_legacy_date_field(mod):
    # Backward compat: the old dead decisions.jsonl format carried a bare 'date' field.
    mod.TODAY = "2026-06-25"
    rows = [{"date": "2026-06-25", "action": "HOLD"}, {"date": "2026-06-24", "action": "HOLD"}]
    out = mod._today(rows)
    assert len(out) == 1


def test_today_zero_rows_for_a_genuinely_quiet_day_stays_zero(mod):
    # Non-regression: the fix must not inflate counts -- a day with no matching rows is 0.
    mod.TODAY = "2026-07-14"
    rows = [{"ts_et": "2026-07-13T15:55:05", "action": "HOLD"}]
    assert mod._today(rows) == []


# ---------------------------------------------------------------------------
# _stale_source_note(): the non-vacuity guard
# ---------------------------------------------------------------------------

def test_stale_source_flags_old_mtime_during_market_hours(mod, tmp_path):
    mod.TODAY = "2026-07-14"
    p = tmp_path / "core-decisions.jsonl"
    p.write_text("{}\n", encoding="utf-8")
    old_ts = datetime(2026, 6, 26, 15, 0, tzinfo=timezone.utc).timestamp()
    import os
    os.utime(p, (old_ts, old_ts))
    now = datetime(2026, 7, 14, 14, 0)  # 10:00 ET on a weekday, well past market open
    note = mod._stale_source_note(p, now)
    assert note is not None
    assert "STALE SOURCE" in note


def test_stale_source_silent_before_market_open(mod, tmp_path):
    mod.TODAY = "2026-07-14"
    p = tmp_path / "core-decisions.jsonl"
    p.write_text("{}\n", encoding="utf-8")
    import os
    old_ts = datetime(2026, 6, 26, 15, 0, tzinfo=timezone.utc).timestamp()
    os.utime(p, (old_ts, old_ts))
    now = datetime(2026, 7, 14, 8, 0)  # 08:00 ET, premarket -- no fires expected yet
    assert mod._stale_source_note(p, now) is None


def test_stale_source_silent_on_weekend(mod, tmp_path):
    mod.TODAY = "2026-07-18"  # a Saturday
    p = tmp_path / "core-decisions.jsonl"
    p.write_text("{}\n", encoding="utf-8")
    now = datetime(2026, 7, 18, 14, 0)
    assert mod._stale_source_note(p, now) is None


def test_stale_source_none_when_fresh(mod, tmp_path):
    # Time-bomb fix (found by conductor 2026-07-21, 7 days after this test was authored on
    # 2026-07-14): the file's mtime is set by the REAL filesystem clock at write-time, which
    # only ever equals a hardcoded "2026-07-14" literal on the day the test was written --
    # this test silently went RED on 2026-07-21 with zero code change. Derive TODAY/`now` from
    # the file's own real mtime instead of a frozen literal, so "fresh" stays fresh forever.
    p = tmp_path / "core-decisions.jsonl"
    p.write_text("{}\n", encoding="utf-8")  # mtime = now = today
    mtime_et = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).astimezone(mod._ET_TZ)
    mod.TODAY = mtime_et.strftime("%Y-%m-%d")
    now = mtime_et.replace(hour=14, minute=0, second=0, microsecond=0, tzinfo=None)
    assert mod._stale_source_note(p, now) is None


def test_stale_source_flags_missing_file(mod, tmp_path):
    mod.TODAY = "2026-07-14"
    p = tmp_path / "does-not-exist.jsonl"
    now = datetime(2026, 7, 14, 14, 0)
    note = mod._stale_source_note(p, now)
    assert note is not None
    assert "does not exist" in note


# ---------------------------------------------------------------------------
# build(): end-to-end with a fixture STATE dir -- the inbox item's literal ask
# ("seed a small JSONL fixture with known-date rows... assert count == N")
# ---------------------------------------------------------------------------

def test_build_counts_real_core_and_fleet_rows_not_zero(mod, tmp_path, monkeypatch):
    """Seed a fixture core-decisions.jsonl (account-labeled, ts_et-only) + one fleet arm's
    decisions.jsonl with known-date rows; assert build() reports the REAL non-zero counts,
    not the 0/0 the dead-path bug produced on every populated day."""
    fake_state = tmp_path / "automation" / "state"
    (fake_state / "fleet" / "risky-3").mkdir(parents=True)
    fake_repo = tmp_path

    core_rows = [
        {"ts_et": "2026-07-13T09:35:03", "account": "safe", "action": "HOLD",
         "spy": 748.0, "vix": 17.0, "ribbon": "BEAR", "setup": None},
        {"ts_et": "2026-07-13T09:36:04", "account": "safe", "action": "ENTER_BEAR",
         "spy": 747.5, "vix": 17.1, "ribbon": "BEAR", "setup": "BEARISH_REJECTION"},
        {"ts_et": "2026-07-13T09:35:04", "account": "bold", "action": "HOLD",
         "spy": 748.0, "vix": 17.0, "ribbon": "BEAR", "setup": None},
        {"ts_et": "2026-07-12T09:35:03", "account": "safe", "action": "HOLD"},  # different day
    ]
    core_path = fake_state / "core-decisions.jsonl"
    core_path.write_text("\n".join(json.dumps(r) for r in core_rows) + "\n", encoding="utf-8")

    fleet_rows = [
        {"ts_et": "2026-07-13T09:35:02.5-04:00", "arm_id": "risky-3", "action": "HOLD"},
        {"ts_et": "2026-07-13T09:36:03.5-04:00", "arm_id": "risky-3", "action": "ENTER_BULL"},
    ]
    fleet_path = fake_state / "fleet" / "risky-3" / "decisions.jsonl"
    fleet_path.write_text("\n".join(json.dumps(r) for r in fleet_rows) + "\n", encoding="utf-8")

    # Simulate "written today" for the fixture's simulated TODAY (2026-07-13), not the
    # real wall-clock date the test happens to run on.
    import os
    fresh_ts = datetime(2026, 7, 13, 15, 0, tzinfo=timezone.utc).timestamp()
    os.utime(core_path, (fresh_ts, fresh_ts))
    os.utime(fleet_path, (fresh_ts, fresh_ts))

    monkeypatch.setattr(mod, "STATE", fake_state)
    monkeypatch.setattr(mod, "REPO", fake_repo)
    monkeypatch.setattr(mod, "TODAY", "2026-07-13")
    monkeypatch.setattr(mod, "_et_now", lambda: datetime(2026, 7, 13, 10, 0))

    out = mod.build()

    assert "safe ticks today: **2**" in out, out
    assert "bold ticks today: **1**" in out, out
    assert "risky-3**: 2 decisions" in out, out
    # ENTER ticks are counted from core-decisions.jsonl only (the safe ENTER_BEAR row);
    # fleet rows have their own "placed/ENTER" count in the FLEET ARMS section above.
    assert "ENTER ticks: 1" in out, out
    assert "STALE SOURCE" not in out, out
    # The old bug's exact false-clean signature must NOT appear.
    assert "ticks today: **0**" not in out


def test_build_flags_stale_core_source_when_market_open_and_file_dead(mod, tmp_path, monkeypatch):
    """The non-vacuity guard end-to-end: a core-decisions.jsonl that exists but hasn't
    been touched today, checked well after market open, must render a STALE SOURCE flag
    rather than a bare, indistinguishable-from-clean 0."""
    import os
    fake_state = tmp_path / "automation" / "state"
    (fake_state / "fleet").mkdir(parents=True)
    core_path = fake_state / "core-decisions.jsonl"
    core_path.write_text('{"ts_et": "2026-06-26T15:00:00", "account": "safe", "action": "HOLD"}\n',
                          encoding="utf-8")
    old_ts = datetime(2026, 6, 26, 15, 0, tzinfo=timezone.utc).timestamp()
    os.utime(core_path, (old_ts, old_ts))

    monkeypatch.setattr(mod, "STATE", fake_state)
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "TODAY", "2026-07-14")
    monkeypatch.setattr(mod, "_et_now", lambda: datetime(2026, 7, 14, 14, 0))

    out = mod.build()
    assert "STALE SOURCE" in out, out
    assert "safe ticks today: **0**" in out
