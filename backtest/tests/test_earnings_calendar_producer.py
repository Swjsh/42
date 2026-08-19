"""Guards for setup/scripts/earnings_calendar.py -- the weekly-1 earnings-blackout
producer (WEEKLY-OPTIONS-PROGRAM.md, "trusted earnings calendar" workstream, 2026-08-18).

Everything here is MOCKED -- no live network calls. lookup_yfinance_earnings and
lookup_nasdaq_earnings both accept injectable stand-ins (ticker_factory / fetch) and every
higher-level function (cross_check_symbol, build_symbol_record, run) accepts yf_lookup /
nasdaq_lookup overrides, so the full pipeline is exercisable with plain dict fixtures.

Coverage (per the task brief):
  1. both-sources-agree -> confirmed
  2. sources-disagree -> disputed + UNION-WIDENED window (min start, max end)
  3. single-source path (Nasdaq unreachable or reachable-but-not-found)
  4. AMC vs BMO blackout-window arithmetic -- exact dates, TRADING sessions not calendar
     days (the Fri/Mon weekend-crossing case)
  5. ETF short-circuit -- zero network calls for a KNOWN_ETFS symbol
  6. empty-result -> non-zero exit (empty universe; a totally-failed non-exempt symbol)
  7. no-look-ahead: as_of preserved across runs when the discovered date is unchanged

All tests operate on an isolated tmp_path repo root -- NEVER the real
automation/state/weekly/*.json (those are live files this script also writes on
schedule).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import earnings_calendar as ec  # noqa: E402

NOW = datetime(2026, 8, 18, 21, 0, 0)

PARAMS = {
    "universe": {"active": ["GLD", "QQQ"], "wave_2_pending": ["NVDA"]},
    "entry": {"earnings_blackout_sessions": 3, "earnings_feed_stale_hours_fail_closed": 48},
}


def _seed_repo(tmp_path: Path, params: dict | None = None, holidays: list[str] | None = None,
                existing_output: dict | None = None) -> Path:
    state = tmp_path / "automation" / "state"
    weekly = state / "weekly"
    weekly.mkdir(parents=True)
    (weekly / "params.json").write_text(json.dumps(params or PARAMS), encoding="utf-8")
    (state / "calendar.json").write_text(json.dumps({"holidays": holidays or []}), encoding="utf-8")
    if existing_output is not None:
        (weekly / "earnings-blackout.json").write_text(json.dumps(existing_output), encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------- #
# 4. AMC vs BMO blackout-window arithmetic -- exact dates, trading sessions not
#    calendar days.
# --------------------------------------------------------------------------- #
def test_shift_trading_days_counts_sessions_not_calendar_days():
    # 2026-08-26 is a Wednesday. 3 sessions back crosses the weekend to the PRIOR Friday
    # (5 calendar days, not 3) -- the exact distinction the task brief asks to pin.
    assert ec.shift_trading_days("2026-08-26", -3, set()) == "2026-08-21"
    assert ec.shift_trading_days("2026-08-26", 1, set()) == "2026-08-27"


def test_shift_trading_days_skips_a_holiday_too():
    # Pretend Tue 2026-08-25 is a market holiday -- stepping back 1 session from Wed
    # 2026-08-26 must land on Mon 2026-08-24, not the (non-trading) holiday itself.
    assert ec.shift_trading_days("2026-08-26", -1, {"2026-08-25"}) == "2026-08-24"


def test_classify_timing_boundaries():
    assert ec.classify_timing(6, 0) == "bmo"
    assert ec.classify_timing(9, 29) == "bmo"
    assert ec.classify_timing(16, 0) == "amc"
    assert ec.classify_timing(20, 0) == "amc"
    assert ec.classify_timing(12, 0) == "unknown"  # mid-session -- neither convention


def test_compute_blackout_window_amc_exact_dates():
    # NVDA-shaped case, live-verified 2026-08-18: AMC print 2026-08-26 (Wed), N=3.
    # Anchor = print date itself (must be flat by ITS close) -> window includes the
    # print day AND the day after (overnight gap risk realizes at D+1's open).
    start, end = ec.compute_blackout_window("2026-08-26", "amc", 3, set())
    assert (start, end) == ("2026-08-21", "2026-08-27")


def test_compute_blackout_window_bmo_exact_dates():
    # Same print date, BMO instead: anchor shifts back ONE session (must be flat by the
    # PRIOR close) -> window includes the day BEFORE the print but not the day after.
    start, end = ec.compute_blackout_window("2026-08-26", "bmo", 3, set())
    assert (start, end) == ("2026-08-20", "2026-08-26")


def test_compute_blackout_window_unknown_timing_matches_bmo():
    # Task brief: unknown timing -> treat as BMO (the more conservative default).
    unknown = ec.compute_blackout_window("2026-08-26", "unknown", 3, set())
    bmo = ec.compute_blackout_window("2026-08-26", "bmo", 3, set())
    assert unknown == bmo


def test_amc_and_bmo_windows_differ_for_the_same_print_date():
    amc = ec.compute_blackout_window("2026-08-26", "amc", 3, set())
    bmo = ec.compute_blackout_window("2026-08-26", "bmo", 3, set())
    assert amc != bmo


# --------------------------------------------------------------------------- #
# 1 & 3. cross_check_symbol -- agreement / single-source
# --------------------------------------------------------------------------- #
def test_both_sources_agree_yields_confirmed():
    yf = {"exempt": False, "found": True, "date": "2026-08-26", "timing": "amc", "error": None}
    nd = {"reachable": True, "found": True, "date": "2026-08-26", "timing": "amc", "error": None}
    rec = ec.cross_check_symbol("NVDA", yf, nd, 3, set())
    assert rec["status"] == "ok"
    assert rec["confidence"] == "confirmed"
    assert rec["sources_agreed"] is True
    assert (rec["blackout_start_date"], rec["blackout_end_date"]) == ("2026-08-21", "2026-08-27")


def test_nasdaq_unreachable_yields_single_source():
    yf = {"exempt": False, "found": True, "date": "2026-08-26", "timing": "amc", "error": None}
    nd = {"reachable": False, "found": False, "date": None, "timing": None,
          "error": "Nasdaq earnings-calendar endpoint unreachable on every probed date"}
    rec = ec.cross_check_symbol("NVDA", yf, nd, 3, set())
    assert rec["status"] == "ok"
    assert rec["confidence"] == "single_source"
    assert rec["sources_agreed"] is False
    # window falls back to yfinance-only (same as the confirmed case's window, since
    # only yfinance's (date,timing) is available)
    assert (rec["blackout_start_date"], rec["blackout_end_date"]) == ("2026-08-21", "2026-08-27")


def test_nasdaq_reachable_but_symbol_not_listed_yields_single_source():
    yf = {"exempt": False, "found": True, "date": "2026-08-26", "timing": "amc", "error": None}
    nd = {"reachable": True, "found": False, "date": None, "timing": None,
          "error": "NVDA not listed on Nasdaq's earnings calendar within +/-1 session(s) of 2026-08-26"}
    rec = ec.cross_check_symbol("NVDA", yf, nd, 3, set())
    assert rec["confidence"] == "single_source"


def test_yfinance_total_failure_yields_unavailable_never_fabricated():
    yf = {"exempt": False, "found": False, "date": None, "timing": None, "error": "ConnectionError: boom"}
    nd = {"reachable": True, "found": True, "date": "2026-08-26", "timing": "amc", "error": None}
    rec = ec.cross_check_symbol("NVDA", yf, nd, 3, set())
    assert rec == {"exempt": False, "status": "unavailable", "error": "yfinance: ConnectionError: boom"}


def test_exempt_short_circuits_regardless_of_nasdaq():
    yf = {"exempt": True, "found": False, "date": None, "timing": None, "error": None,
          "reason": "known ETF"}
    nd = {"reachable": True, "found": True, "date": "2026-08-26", "timing": "amc", "error": None}
    rec = ec.cross_check_symbol("GLD", yf, nd, 3, set())
    assert rec == {"exempt": True, "reason": "known ETF"}


# --------------------------------------------------------------------------- #
# 2. sources-disagree -> disputed + UNION-WIDENED window
# --------------------------------------------------------------------------- #
def test_sources_disagree_on_date_yields_disputed_and_union_widened_window():
    """yfinance says 2026-08-26 AMC (window 8/21-8/27); Nasdaq says 2026-08-25 BMO
    (anchor shifts to 8/24, window 8/19-8/25, hand-verified by the module docstring's
    own worked BMO example one session earlier). The union must be the WIDER envelope
    (min start, max end) -- never narrower than either source's own window alone. This
    is the test the RED-proof below deliberately breaks and restores."""
    yf = {"exempt": False, "found": True, "date": "2026-08-26", "timing": "amc", "error": None}
    nd = {"reachable": True, "found": True, "date": "2026-08-25", "timing": "bmo", "error": None}
    rec = ec.cross_check_symbol("NVDA", yf, nd, 3, set())
    assert rec["status"] == "ok"
    assert rec["confidence"] == "disputed"
    assert rec["sources_agreed"] is False
    assert (rec["blackout_start_date"], rec["blackout_end_date"]) == ("2026-08-19", "2026-08-27")
    assert rec["disputed_detail"]["yfinance"] == {"date": "2026-08-26", "timing": "amc"}
    assert rec["disputed_detail"]["nasdaq"] == {"date": "2026-08-25", "timing": "bmo"}


def test_sources_agree_on_date_but_conflict_on_timing_is_also_disputed():
    yf = {"exempt": False, "found": True, "date": "2026-08-26", "timing": "amc", "error": None}
    nd = {"reachable": True, "found": True, "date": "2026-08-26", "timing": "bmo", "error": None}
    rec = ec.cross_check_symbol("NVDA", yf, nd, 3, set())
    assert rec["confidence"] == "disputed"
    # union of amc-window (8/21-8/27) and bmo-window (8/20-8/26) on the SAME date
    assert (rec["blackout_start_date"], rec["blackout_end_date"]) == ("2026-08-20", "2026-08-27")


def test_one_source_unknown_timing_does_not_force_a_dispute():
    """An 'unknown' timing from one source must defer to the other's definite read
    (not manufacture a false conflict) when dates already agree."""
    yf = {"exempt": False, "found": True, "date": "2026-08-26", "timing": "unknown", "error": None}
    nd = {"reachable": True, "found": True, "date": "2026-08-26", "timing": "amc", "error": None}
    rec = ec.cross_check_symbol("NVDA", yf, nd, 3, set())
    assert rec["confidence"] == "confirmed"
    assert rec["timing"] == "amc"


# --------------------------------------------------------------------------- #
# 5. ETF short-circuit -- lookup_yfinance_earnings itself
# --------------------------------------------------------------------------- #
def _exploding_factory(symbol):
    raise AssertionError(f"ticker_factory must NEVER be invoked for a KNOWN_ETFS symbol ({symbol})")


def test_known_etf_never_queries_the_network():
    result = ec.lookup_yfinance_earnings("GLD", today="2026-08-18", ticker_factory=_exploding_factory)
    assert result["exempt"] is True
    assert "GLD" not in result["reason"] or "ETF" in result["reason"]  # sanity: reason is meaningful
    result2 = ec.lookup_yfinance_earnings("QQQ", today="2026-08-18", ticker_factory=_exploding_factory)
    assert result2["exempt"] is True


class _FakeTs:
    def __init__(self, y, m, d, hh, mm):
        self._dt = datetime(y, m, d, hh, mm)

    def strftime(self, fmt):
        return self._dt.strftime(fmt)

    @property
    def hour(self):
        return self._dt.hour

    @property
    def minute(self):
        return self._dt.minute


class _FakeFrame:
    def __init__(self, rows):
        self._rows = rows
        self.empty = len(rows) == 0

    @property
    def index(self):
        return self._rows


class _FakeTicker:
    def __init__(self, earnings_dates=None, calendar=None, raise_exc=None):
        self._ed = earnings_dates
        self._cal = calendar if calendar is not None else {}
        self._raise = raise_exc

    @property
    def earnings_dates(self):
        if self._raise is not None:
            raise self._raise
        return self._ed

    @property
    def calendar(self):
        return self._cal


def test_non_etf_symbol_with_no_data_is_exempted_via_live_confirmation():
    """A symbol NOT on the static KNOWN_ETFS list (any future ETF/no-earnings ticker)
    still gets exempted -- but only because yfinance CONFIRMED emptiness on both
    properties, not because of an error (see the exception test below)."""
    factory = lambda symbol: _FakeTicker(earnings_dates=_FakeFrame([]), calendar={})  # noqa: E731
    result = ec.lookup_yfinance_earnings("XLF", today="2026-08-18", ticker_factory=factory)
    assert result["exempt"] is True
    assert "no company earnings" in result["reason"]


def test_found_picks_soonest_upcoming_row_and_ignores_past_rows():
    rows = [
        _FakeTs(2026, 5, 20, 16, 0),   # past
        _FakeTs(2026, 8, 26, 16, 0),   # soonest upcoming
        _FakeTs(2026, 11, 18, 16, 0),  # further out
    ]
    factory = lambda symbol: _FakeTicker(  # noqa: E731
        earnings_dates=_FakeFrame(rows), calendar={"Earnings Date": [1]})
    result = ec.lookup_yfinance_earnings("NVDA", today="2026-08-18", ticker_factory=factory)
    assert result["found"] is True
    assert result["date"] == "2026-08-26"
    assert result["timing"] == "amc"


def test_rows_present_but_all_in_the_past_is_not_found_and_not_exempt():
    rows = [_FakeTs(2026, 5, 20, 16, 0)]
    factory = lambda symbol: _FakeTicker(  # noqa: E731
        earnings_dates=_FakeFrame(rows), calendar={"Earnings Date": [1]})
    result = ec.lookup_yfinance_earnings("NVDA", today="2026-08-18", ticker_factory=factory)
    assert result["found"] is False
    assert result["exempt"] is False
    assert "none on/after today" in result["error"]


def test_fetch_exception_is_a_real_failure_never_silently_exempted():
    factory = lambda symbol: _FakeTicker(raise_exc=ConnectionError("network down"))  # noqa: E731
    result = ec.lookup_yfinance_earnings("NVDA", today="2026-08-18", ticker_factory=factory)
    assert result["exempt"] is False
    assert result["found"] is False
    assert "network down" in result["error"]


def test_ambiguous_response_is_not_trusted_as_exempt_or_found():
    """earnings_dates empty but calendar non-empty -- yfinance disagreeing with itself.
    Must not be silently defaulted to exempt (would misclassify a real single name)."""
    factory = lambda symbol: _FakeTicker(  # noqa: E731
        earnings_dates=_FakeFrame([]), calendar={"Earnings Date": [1]})
    result = ec.lookup_yfinance_earnings("NVDA", today="2026-08-18", ticker_factory=factory)
    assert result["exempt"] is False
    assert result["found"] is False
    assert "ambiguous" in result["error"]


# --------------------------------------------------------------------------- #
# lookup_nasdaq_earnings -- mocked fetch, no network
# --------------------------------------------------------------------------- #
def test_nasdaq_lookup_finds_symbol_on_the_exact_date():
    def fetch(date_str):
        if date_str == "2026-08-26":
            return [{"symbol": "NVDA", "time": "time-after-hours"}]
        return []
    result = ec.lookup_nasdaq_earnings("NVDA", "2026-08-26", set(), fetch=fetch)
    assert result == {"reachable": True, "found": True, "date": "2026-08-26", "timing": "amc", "error": None}


def test_nasdaq_lookup_finds_symbol_one_session_off_via_probe_window():
    def fetch(date_str):
        if date_str == "2026-08-25":
            return [{"symbol": "NVDA", "time": "time-pre-market"}]
        return []
    result = ec.lookup_nasdaq_earnings("NVDA", "2026-08-26", set(), fetch=fetch)
    assert result["reachable"] is True
    assert result["found"] is True
    assert result["date"] == "2026-08-25"
    assert result["timing"] == "bmo"


def test_nasdaq_lookup_reachable_but_symbol_absent():
    def fetch(date_str):
        return [{"symbol": "OTHERCO", "time": "time-after-hours"}]
    result = ec.lookup_nasdaq_earnings("NVDA", "2026-08-26", set(), fetch=fetch)
    assert result["reachable"] is True
    assert result["found"] is False
    assert "not listed" in result["error"]


def test_nasdaq_lookup_fully_unreachable():
    def fetch(date_str):
        raise TimeoutError("simulated timeout")
    result = ec.lookup_nasdaq_earnings("NVDA", "2026-08-26", set(), fetch=fetch)
    assert result == {"reachable": False, "found": False, "date": None, "timing": None,
                       "error": "Nasdaq earnings-calendar endpoint unreachable on every probed date"}


# --------------------------------------------------------------------------- #
# 7. no-look-ahead: as_of merge
# --------------------------------------------------------------------------- #
def _yf_ok(date="2026-08-26", timing="amc"):
    def _inner(symbol, *, today):
        return {"exempt": False, "found": True, "date": date, "timing": timing, "error": None}
    return _inner


def _nasdaq_none():
    def _inner(symbol, near_date, holidays):
        return {"reachable": False, "found": False, "date": None, "timing": None, "error": "stub: none"}
    return _inner


def test_as_of_preserved_when_discovered_date_is_unchanged():
    existing = {"next_earnings_date": "2026-08-26", "as_of": "2026-08-01T00:00:00"}
    rec = ec.build_symbol_record("NVDA", NOW, PARAMS, set(), existing,
                                  yf_lookup=_yf_ok(), nasdaq_lookup=_nasdaq_none())
    assert rec["as_of"] == "2026-08-01T00:00:00"  # NOT bumped to NOW


def test_as_of_refreshed_when_discovered_date_changes():
    existing = {"next_earnings_date": "2026-05-20", "as_of": "2026-05-01T00:00:00"}
    rec = ec.build_symbol_record("NVDA", NOW, PARAMS, set(), existing,
                                  yf_lookup=_yf_ok(date="2026-08-26"), nasdaq_lookup=_nasdaq_none())
    assert rec["as_of"] == NOW.strftime("%Y-%m-%dT%H:%M:%S")


def test_as_of_stamped_now_on_first_ever_observation():
    rec = ec.build_symbol_record("NVDA", NOW, PARAMS, set(), None,
                                  yf_lookup=_yf_ok(), nasdaq_lookup=_nasdaq_none())
    assert rec["as_of"] == NOW.strftime("%Y-%m-%dT%H:%M:%S")


# --------------------------------------------------------------------------- #
# run() / main() -- end to end with injected lookups, isolated tmp repo
# --------------------------------------------------------------------------- #
def _run_lookups():
    def yf_lookup(symbol, *, today):
        if symbol in ("GLD", "QQQ"):
            return {"exempt": True, "found": False, "date": None, "timing": None, "error": None,
                    "reason": "known ETF (stub)"}
        return {"exempt": False, "found": True, "date": "2026-08-26", "timing": "amc", "error": None}

    def nasdaq_lookup(symbol, near_date, holidays):
        return {"reachable": True, "found": True, "date": near_date, "timing": "amc", "error": None}
    return yf_lookup, nasdaq_lookup


def test_run_writes_full_schema_for_ok_and_exempt_symbols(tmp_path: Path):
    repo = _seed_repo(tmp_path)
    yf_lookup, nasdaq_lookup = _run_lookups()
    result = ec.run(repo, now=NOW, dry_run=False, yf_lookup=yf_lookup, nasdaq_lookup=nasdaq_lookup)

    assert result["generated_at_et"] == NOW.strftime("%Y-%m-%dT%H:%M:%S")
    assert result["producer"] == "setup/scripts/earnings_calendar.py"
    assert "earnings_feed_stale_hours_fail_closed" in result["_fail_closed_contract"]

    gld = result["symbols"]["GLD"]
    assert gld["exempt"] is True and "as_of" in gld

    nvda = result["symbols"]["NVDA"]
    required = {"next_earnings_date", "timing", "confidence", "sources_agreed",
                "blackout_start_date", "blackout_end_date", "as_of"}
    missing = required - nvda.keys()
    assert not missing, f"NVDA record missing required schema fields: {missing}"
    assert nvda["confidence"] == "confirmed"

    written = json.loads((repo / "automation" / "state" / "weekly" / "earnings-blackout.json").read_text(encoding="utf-8"))
    assert written == result


def test_dry_run_never_writes(tmp_path: Path):
    repo = _seed_repo(tmp_path)
    yf_lookup, nasdaq_lookup = _run_lookups()
    ec.run(repo, now=NOW, dry_run=True, yf_lookup=yf_lookup, nasdaq_lookup=nasdaq_lookup)
    assert not (repo / "automation" / "state" / "weekly" / "earnings-blackout.json").exists()


def test_atomic_write_leaves_no_tmp_files(tmp_path: Path):
    repo = _seed_repo(tmp_path)
    yf_lookup, nasdaq_lookup = _run_lookups()
    ec.run(repo, now=NOW, dry_run=False, yf_lookup=yf_lookup, nasdaq_lookup=nasdaq_lookup)
    leftovers = list((repo / "automation" / "state" / "weekly").glob("*.tmp"))
    assert leftovers == []


# ---- 6. empty-result -> non-zero exit ----
def test_empty_universe_raises_refusing_to_write_symbol_less_file(tmp_path: Path):
    empty_params = {"universe": {"active": [], "wave_2_pending": []},
                     "entry": {"earnings_blackout_sessions": 3, "earnings_feed_stale_hours_fail_closed": 48}}
    repo = _seed_repo(tmp_path, params=empty_params)
    with pytest.raises(RuntimeError, match="EMPTY"):
        ec.run(repo, now=NOW, dry_run=False)


def test_main_exits_nonzero_and_prints_fatal_when_run_raises(monkeypatch: pytest.MonkeyPatch, capsys):
    def _boom(*a, **kw):
        raise RuntimeError("simulated empty-universe failure")
    monkeypatch.setattr(ec, "run", _boom)
    rc = ec.main(["--dry-run"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "FATAL earnings_calendar.py" in captured.err


def test_main_exits_nonzero_when_a_nonexempt_symbol_totally_failed(monkeypatch: pytest.MonkeyPatch, capsys):
    canned = {
        "generated_at_et": "2026-08-18T21:00:00",
        "producer": "setup/scripts/earnings_calendar.py",
        "_fail_closed_contract": "...",
        "symbols": {
            "GLD": {"exempt": True, "reason": "known ETF", "as_of": "2026-08-18T21:00:00"},
            "NVDA": {"exempt": False, "status": "unavailable", "error": "yfinance: boom"},
        },
    }
    monkeypatch.setattr(ec, "run", lambda *a, **kw: canned)
    rc = ec.main(["--dry-run"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "NVDA" in captured.err
    assert "FAILED lookup entirely" in captured.err


def test_main_exits_zero_when_everything_ok(monkeypatch: pytest.MonkeyPatch):
    canned = {
        "generated_at_et": "2026-08-18T21:00:00",
        "producer": "setup/scripts/earnings_calendar.py",
        "_fail_closed_contract": "...",
        "symbols": {
            "GLD": {"exempt": True, "reason": "known ETF", "as_of": "2026-08-18T21:00:00"},
            "NVDA": {"exempt": False, "status": "ok", "confidence": "confirmed", "sources_agreed": True,
                     "next_earnings_date": "2026-08-26", "timing": "amc",
                     "blackout_start_date": "2026-08-21", "blackout_end_date": "2026-08-27",
                     "as_of": "2026-08-18T21:00:00"},
        },
    }
    monkeypatch.setattr(ec, "run", lambda *a, **kw: canned)
    rc = ec.main(["--dry-run"])
    assert rc == 0


def test_missing_params_file_raises_clear_error(tmp_path: Path):
    """params.json is required config another workstream owns -- a missing file must
    raise, never silently default to an empty/plausible universe."""
    state = tmp_path / "automation" / "state"
    (state / "weekly").mkdir(parents=True)
    (state / "calendar.json").write_text(json.dumps({"holidays": []}), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        ec.run(tmp_path, now=NOW, dry_run=False)
