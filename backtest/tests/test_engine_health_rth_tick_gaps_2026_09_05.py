"""Guard: engine_health.py's `rth_tick_gaps` check + its shared detector, engine_gaps.py.

WHY THIS EXISTS: on 2026-09-04 the box lost power at 09:51 ET while safe-2 (3x
SPY260904P00772000) and bold-2 (5x SPY260904P00770000) held open 0DTE positions
(entered 09:46 ET). core-decisions.jsonl has NO rows for either core account
09:51:03 -> 10:46:15/16 ET -- a 55-minute hole in a 1-minute engine, during RTH, while
both accounts were exposed. J closed both positions from the Alpaca web dashboard at
10:46:06/07 ET. engine_health.py's EXISTING liveness checks (check_engine_core) only
ask "is the newest row fresh RIGHT NOW" -- by the time any post-blackout fire ran, the
newest row was fresh again and the interior hole was invisible; engine-health.json read
GREEN 18/18 all day (checked live 2026-09-05).

This pins:
  1. engine_gaps.find_rth_gaps / find_gaps_with_position_flag against the REAL
     2026-09-04 safe-account rows (09:44-10:50 ET, copied verbatim from
     automation/state/core-decisions.jsonl) -- the exact ~55m gap, flagged as
     overlapping an open position via the REAL fills-ledger.jsonl rows for safe-2.
  2. engine_health.check_rth_tick_gaps returns RED (critical) on that fixture, and
     GREEN on a no-gap fixture (evenly-spaced 1-min ticks, no hole).
  3. Fail-open: a corrupt core-decisions.jsonl degrades to a benign YELLOW, never a
     crash.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import engine_gaps as eg  # noqa: E402
import engine_health as eh  # noqa: E402

# --------------------------------------------------------------------------- #
# REAL 2026-09-04 safe-account rows, 09:44-10:50 ET, copied verbatim (minified) from
# automation/state/core-decisions.jsonl. The gap is 09:51:03 -> 10:46:15 (~55.2m) --
# rows at 09:50:03 and 09:51:03 exist (the engine was still ticking then); the very
# next row for 'safe' is 10:46:15, right after J's dashboard close at 10:46:06.
# --------------------------------------------------------------------------- #
_REAL_TS = [
    "2026-09-04T09:44:03", "2026-09-04T09:45:04", "2026-09-04T09:46:03",
    "2026-09-04T09:47:03", "2026-09-04T09:48:03", "2026-09-04T09:49:03",
    "2026-09-04T09:50:03", "2026-09-04T09:51:03",
    # <-- the real 09:51:03 -> 10:46:15 blackout gap -->
    "2026-09-04T10:46:15", "2026-09-04T10:47:02", "2026-09-04T10:48:02",
    "2026-09-04T10:49:02", "2026-09-04T10:50:03",
]


def _core_row(ts: str, verdict: str = "HOLD") -> dict:
    """Minimal real-shaped row (engine_gaps only reads 'account' + 'ts_et')."""
    return {"ts_et": ts, "account": "safe", "verdict": verdict, "armed": True}


def _write_jsonl(path: Path, rows: list) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _real_fills_fixture() -> list:
    """REAL safe-2 fills for 2026-09-04, copied verbatim from
    automation/state/fills-ledger.jsonl: engine entry 09:46:05, manual exit 10:46:06
    (J's dashboard rescue during the blackout)."""
    return [
        {"activity_id": "20260904094605044::163d6051-00a9-4db7-8c84-2f3278f8f476",
         "arm": "safe-2", "order_id": "a89c9574-77a8-4b99-b347-c2007dde7687",
         "symbol": "SPY260904P00772000", "side": "buy", "qty": 3.0, "price": 1.29,
         "multiplier": 100, "is_crypto": False, "is_option": True,
         "ts_utc": "2026-09-04T13:46:05.044241Z", "ts_et": "2026-09-04T09:46:05.044241",
         "date_et": "2026-09-04", "attribution": "engine"},
        {"activity_id": "20260904104606110::03052a27-f805-4fbe-9766-96f05bfb8208",
         "arm": "safe-2", "order_id": "f5cc9422-9edb-4090-8303-1e92a8511f80",
         "symbol": "SPY260904P00772000", "side": "sell", "qty": 3.0, "price": 2.0,
         "multiplier": 100, "is_crypto": False, "is_option": True,
         "ts_utc": "2026-09-04T14:46:06.110286Z", "ts_et": "2026-09-04T10:46:06.110286",
         "date_et": "2026-09-04", "attribution": "manual"},
    ]


# --------------------------------------------------------------------------- #
# 1. Pure detector against the real fixture
# --------------------------------------------------------------------------- #

def test_find_rth_gaps_finds_the_real_2026_09_04_blackout():
    timestamps = [eg._parse_naive(ts) for ts in _REAL_TS]
    gaps = eg.find_rth_gaps(timestamps, "2026-09-04")
    assert len(gaps) == 1, f"expected exactly one gap, got {gaps}"
    g = gaps[0]
    assert g["start"] == dt.datetime(2026, 9, 4, 9, 51, 3)
    assert g["end"] == dt.datetime(2026, 9, 4, 10, 46, 15)
    assert 54.0 < g["duration_min"] < 56.0, g["duration_min"]


def test_find_gaps_with_position_flag_marks_open_position(tmp_path):
    core_path = tmp_path / "core-decisions.jsonl"
    fills_path = tmp_path / "fills-ledger.jsonl"
    _write_jsonl(core_path, [_core_row(ts) for ts in _REAL_TS])
    _write_jsonl(fills_path, _real_fills_fixture())

    gaps = eg.find_gaps_with_position_flag("safe", "2026-09-04",
                                            core_path=core_path, fills_path=fills_path)
    assert len(gaps) == 1
    assert gaps[0]["open_position"] is True, (
        "the real safe-2 buy fill (09:46:05, qty 3) precedes the gap start (09:51:03) with "
        "no offsetting sell before it -- this MUST read as an open position during the gap")


def test_no_gap_case_is_clean():
    """Evenly-spaced 1-min ticks across a short RTH window -> zero gaps."""
    start = dt.datetime(2026, 9, 3, 9, 30, 0)
    timestamps = [start + dt.timedelta(minutes=i) for i in range(10)]
    gaps = eg.find_rth_gaps(timestamps, "2026-09-03")
    assert gaps == []


# --------------------------------------------------------------------------- #
# 2. engine_health.check_rth_tick_gaps -- RED on the real blackout, GREEN on no-gap
# --------------------------------------------------------------------------- #

def _patch_gap_source(monkeypatch, day: str, core_path: Path, fills_path: Path) -> None:
    """Redirect engine_gaps.find_gaps_with_position_flag (as check_rth_tick_gaps calls
    it, with only account+day positional) to the tmp fixture paths for `day`, and to []
    for any other day (so the 'plus most recent prior trading day' half of the check
    contributes nothing extra in these tests)."""
    real = eg.find_gaps_with_position_flag

    def _fake(account, d, *a, **kw):
        if d != day:
            return []
        return real(account, d, core_path=core_path, fills_path=fills_path)

    monkeypatch.setattr(eg, "find_gaps_with_position_flag", _fake)
    # Deterministic, offline: no calendar/network involvement in _prior_trading_day_str.
    monkeypatch.setattr(eh, "_load_holidays", lambda: set())


def test_check_rth_tick_gaps_is_red_on_the_real_blackout_fixture(tmp_path, monkeypatch):
    core_path = tmp_path / "core-decisions.jsonl"
    fills_path = tmp_path / "fills-ledger.jsonl"
    _write_jsonl(core_path, [_core_row(ts) for ts in _REAL_TS])
    _write_jsonl(fills_path, _real_fills_fixture())
    _patch_gap_source(monkeypatch, "2026-09-04", core_path, fills_path)

    # Evaluate as if it's later the same day (session over), so 'today' is in scope.
    et = dt.datetime(2026, 9, 4, 18, 0, 0)
    result = eh.check_rth_tick_gaps(et)

    assert result["status"] == "RED", result
    assert result["critical"] is True
    assert "OPEN POSITION" in result["detail"]
    assert "55" in result["detail"] or "54." in result["detail"] or "56." in result["detail"]


def test_check_rth_tick_gaps_is_green_with_no_gap(tmp_path, monkeypatch):
    core_path = tmp_path / "core-decisions.jsonl"
    fills_path = tmp_path / "fills-ledger.jsonl"
    start = dt.datetime(2026, 9, 3, 9, 30, 0)
    rows = [_core_row((start + dt.timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S"))
            for i in range(10)]
    _write_jsonl(core_path, rows)
    _write_jsonl(fills_path, [])
    _patch_gap_source(monkeypatch, "2026-09-03", core_path, fills_path)

    et = dt.datetime(2026, 9, 3, 18, 0, 0)
    result = eh.check_rth_tick_gaps(et)

    assert result["status"] == "GREEN", result


def test_check_rth_tick_gaps_fails_open_on_a_corrupt_ledger(tmp_path, monkeypatch):
    """A garbled core-decisions.jsonl must degrade to a benign non-crashing result, never
    raise into build_report()."""
    core_path = tmp_path / "core-decisions.jsonl"
    core_path.write_text("{not valid json\n{also not valid\n", encoding="utf-8")
    fills_path = tmp_path / "fills-ledger.jsonl"
    fills_path.write_text("", encoding="utf-8")

    def _fake(account, d, *a, **kw):
        return eg.find_gaps_with_position_flag(account, d, core_path=core_path,
                                                fills_path=fills_path)
    monkeypatch.setattr(eg, "find_gaps_with_position_flag", _fake)
    monkeypatch.setattr(eh, "_load_holidays", lambda: set())

    et = dt.datetime(2026, 9, 4, 18, 0, 0)
    result = eh.check_rth_tick_gaps(et)  # must not raise
    assert result["status"] in ("GREEN", "YELLOW"), result


def test_rth_tick_gaps_check_is_registered_in_build_report(monkeypatch):
    """The check must actually run inside build_report(), not just exist standalone."""
    # Avoid real IO from every other check by only asserting the name is present in a
    # real (possibly-degraded) build_report() call -- every check fails open by design.
    report = eh.build_report()
    names = [c["name"] for c in report["checks"]]
    assert "rth_tick_gaps" in names


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
