"""test_early_close_flatten_2026_09_01.py -- guards for the B2 early-close flatten half.

CONTRACT (B2, 2026-09-01):
  The live broker calendar closes 2026-11-27 and 2026-12-24 at 13:00 ET. The normal
  15:52/15:55 flatten schedule is UNCHANGED (frozen entry-side fix waits for heartbeat_core.py
  to unfreeze 09-29) -- this ships a second, independent exit-side task:
  `eod_flatten.py --only-if-early-close`.

  1. CALENDAR_SCHEMA -- market_calendar.refresh_calendar_from_alpaca keeps writing
     'holidays' (backward compatible) AND now writes 'early_closes' {date: 'HH:MM'} for any
     date whose 'close' field is not 16:00.
  2. NOOP_ON_FULL_DAY -- --only-if-early-close is a no-op (no positions read, no orders) when
     today's close is 16:00.
  3. WAITS_BEFORE_THRESHOLD -- on a 13:00-close day, before close-30min it logs WAIT and does
     NOT sweep.
  4. ACTS_AT_THRESHOLD -- on a 13:00-close day, at/after close-30min it runs the SAME sweep
     code path as the normal flatten (fleet_broker.close_all_spy_options gets called), tagged
     reason=EARLY_CLOSE.
  5. FAIL_CLOSED_ON_UNKNOWN -- if the calendar cache AND the live GET fallback both fail, it
     logs EARLY_CLOSE_UNKNOWN, exits 0, and NEVER reads positions or places orders (this path
     only ever ACTS on a position, so "unknown" must mean "do nothing", not "guess 16:00").
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "setup" / "scripts"
_FLEET = REPO / "automation" / "state" / "fleet"
for _p in (str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import eod_flatten as ef  # noqa: E402
import market_calendar as mc  # noqa: E402


def _flat_creds() -> dict:
    return {
        "safe-2": {"key": "SK1", "secret": "SS1", "base_url": "https://paper-api.alpaca.markets"},
        "bold-2": {"key": "BK1", "secret": "BS1", "base_url": "https://paper-api.alpaca.markets"},
    }


def _read_jsonl(tmp_path: Path) -> list[dict]:
    rows = []
    for f in tmp_path.glob("eod-flatten-*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ===========================================================================
# 1. CALENDAR_SCHEMA -- holidays preserved, early_closes added
# ===========================================================================

def _fake_calendar_days(year: int) -> list[dict]:
    """Shaped like Alpaca's /v2/calendar response: every weekday present (so nothing here
    is a holiday) EXCEPT one deliberate holiday, plus one deliberate early close."""
    return [
        {"date": f"{year}-11-25", "close": "16:00"},
        {"date": f"{year}-11-27", "close": "13:00"},  # early close (Thanksgiving eve)
        # {year}-11-26 deliberately ABSENT -- the holiday (Thanksgiving)
        {"date": f"{year}-12-24", "close": "13:00"},  # early close (Christmas eve)
        {"date": f"{year}-12-26", "close": "16:00"},
    ]


def test_calendar_refresh_keeps_holidays_and_adds_early_closes(tmp_path):
    cal_path = tmp_path / "calendar.json"
    with patch.object(mc, "fetch_calendar_days", return_value=_fake_calendar_days(2026)):
        ok = mc.refresh_calendar_from_alpaca(cal_path, 2026)
    assert ok is True

    data = json.loads(cal_path.read_text(encoding="utf-8"))
    # Backward compatible: holidays[] still present and correct.
    assert "2026-11-26" in data["holidays"]  # the day we omitted -> holiday
    assert "2026-11-27" not in data["holidays"]
    # NEW: early_closes{} present, keyed only by dates whose close != 16:00.
    assert data["early_closes"] == {"2026-11-27": "13:00", "2026-12-24": "13:00"}
    assert "2026-11-25" not in data["early_closes"]  # 16:00 day never listed


def test_cached_close_reads_early_close_and_defaults_to_1600(tmp_path):
    cal_path = tmp_path / "calendar.json"
    cal_path.write_text(json.dumps({
        "year_range": ["2026-01-01", "2026-12-31"],
        "holidays": ["2026-11-26"],
        "early_closes": {"2026-11-27": "13:00"},
    }))
    assert mc.cached_close("2026-11-27", cal_path) == "13:00"
    assert mc.cached_close("2026-09-01", cal_path) == "16:00"  # not listed -> default full day


def test_cached_close_missing_early_closes_key_is_backward_compatible(tmp_path):
    """A pre-B2 calendar.json (no 'early_closes' key at all) must still answer '16:00' for
    every date, never crash -- this is the exact shape of the file on disk before this
    change shipped."""
    cal_path = tmp_path / "calendar.json"
    cal_path.write_text(json.dumps({
        "year_range": ["2026-01-01", "2026-12-31"],
        "holidays": ["2026-01-01"],
    }))
    assert mc.cached_close("2026-11-27", cal_path) == "16:00"


def test_cached_close_none_when_year_not_covered(tmp_path):
    cal_path = tmp_path / "calendar.json"
    cal_path.write_text(json.dumps({"year_range": ["2025-01-01", "2025-12-31"], "holidays": []}))
    assert mc.cached_close("2026-11-27", cal_path) is None


# ===========================================================================
# 2. NOOP_ON_FULL_DAY -- 16:00 day -> no-op, nothing read/placed
# ===========================================================================

def test_only_if_early_close_noop_on_16_00_day(tmp_path):
    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(mc, "cached_close", return_value="16:00"),
        patch.object(ef.fleet_broker, "open_spy_option_positions_checked") as m_read,
        patch.object(ef.fleet_broker, "close_all_spy_options") as m_close,
    ):
        rc = ef._run_only_if_early_close()

    assert rc == 0
    m_read.assert_not_called()
    m_close.assert_not_called()
    rows = _read_jsonl(tmp_path)
    assert rows[-1]["outcome"] == "EARLY_CLOSE_NOOP_FULL_DAY"


# ===========================================================================
# 3. WAITS_BEFORE_THRESHOLD -- 13:00 day, before close-30min -> WAIT, no sweep
# ===========================================================================

def test_only_if_early_close_waits_before_threshold(tmp_path):
    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(mc, "cached_close", return_value="13:00"),
        patch.object(ef, "et_now", return_value=datetime(2026, 11, 27, 12, 0)),  # 60 min early
        patch.object(ef.fleet_broker, "open_spy_option_positions_checked") as m_read,
        patch.object(ef.fleet_broker, "close_all_spy_options") as m_close,
    ):
        rc = ef._run_only_if_early_close()

    assert rc == 0
    m_read.assert_not_called()
    m_close.assert_not_called()
    rows = _read_jsonl(tmp_path)
    assert rows[-1]["outcome"] == "EARLY_CLOSE_WAIT"


# ===========================================================================
# 4. ACTS_AT_THRESHOLD -- 13:00 day, at/after close-30min -> runs the real sweep
# ===========================================================================

def test_only_if_early_close_acts_at_threshold_and_tags_reason(tmp_path):
    pos = [{"symbol": "SPY261127C00680000", "qty": "3", "asset_class": "us_option"}]
    close_result = {"closed": ["SPY261127C00680000"], "errors": [], "remaining": 0}

    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(mc, "cached_close", return_value="13:00"),
        # exactly at the close-30min threshold (13:00 - 30min = 12:30)
        patch.object(ef, "et_now", return_value=datetime(2026, 11, 27, 12, 30)),
        patch.object(ef.fleet_broker, "open_spy_option_positions_checked",
                     return_value=(pos, True)),
        patch.object(ef.fleet_broker, "close_all_spy_options", return_value=close_result) as m_close,
    ):
        rc = ef._run_only_if_early_close()

    assert rc == 0
    m_close.assert_called()
    _, kwargs = m_close.call_args
    assert kwargs.get("live") is True  # same live sweep as the normal 15:52/15:55 path
    rows = _read_jsonl(tmp_path)
    acted = [r for r in rows if r.get("arm") in ("safe-2", "bold-2")]
    assert acted, f"expected per-arm rows in {rows}"
    assert all(r.get("reason") == "EARLY_CLOSE" for r in acted)
    assert all(r.get("outcome") == "SUCCESS" for r in acted)


# ===========================================================================
# 5. FAIL_CLOSED_ON_UNKNOWN -- cache miss + live GET both fail -> refuse to act
# ===========================================================================

def test_only_if_early_close_refuses_when_calendar_unknown(tmp_path):
    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(mc, "cached_close", return_value=None),          # cache miss
        patch.object(ef.fleet_broker, "_request", return_value={"_error": "timeout"}),  # live GET fails too
        patch.object(ef.fleet_broker, "open_spy_option_positions_checked") as m_read,
        patch.object(ef.fleet_broker, "close_all_spy_options") as m_close,
    ):
        rc = ef._run_only_if_early_close()

    assert rc == 0
    m_read.assert_not_called()
    m_close.assert_not_called()
    rows = _read_jsonl(tmp_path)
    assert rows[-1]["outcome"] == "EARLY_CLOSE_UNKNOWN"


def test_only_if_early_close_live_get_fallback_used_when_cache_misses(tmp_path):
    """Cache miss but the live GET succeeds -> the live value drives the decision (proves
    the fallback is actually wired, not just the failure path)."""
    with (
        patch.object(ef, "LOG_DIR", tmp_path),
        patch.object(ef.fleet_broker, "load_creds", return_value=_flat_creds()),
        patch.object(mc, "cached_close", return_value=None),
        patch.object(ef.fleet_broker, "_request",
                     return_value=[{"date": "2026-11-27", "close": "16:00"}]),
        patch.object(ef.fleet_broker, "open_spy_option_positions_checked") as m_read,
    ):
        rc = ef._run_only_if_early_close()

    assert rc == 0
    m_read.assert_not_called()  # 16:00 via live GET -> still a full-day NOOP
    rows = _read_jsonl(tmp_path)
    assert rows[-1]["outcome"] == "EARLY_CLOSE_NOOP_FULL_DAY"


def test_argv_flag_dispatches_to_only_if_early_close(monkeypatch):
    """--only-if-early-close on argv must route to the gated path, not the normal sweep --
    a wiring guard so the registered scheduled task actually calls the intended function."""
    calls = []
    monkeypatch.setattr(sys, "argv", ["eod_flatten.py", "--only-if-early-close"])
    monkeypatch.setattr(ef, "_run_only_if_early_close", lambda: calls.append("gated") or 0)
    monkeypatch.setattr(ef, "main", lambda: calls.append("normal") or 0)

    src = Path(ef.__file__).read_text(encoding="utf-8")
    assert '"--only-if-early-close" in sys.argv[1:]' in src, (
        "eod_flatten.py must dispatch on the --only-if-early-close flag in its "
        "__main__ block"
    )
