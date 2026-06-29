"""Guard: the GEX OI-archive continuity checker fails LOUD on a stalled accrual (C7).

The months-long dealer-GEX archive (``journal/gex-archive/``) is the standing-direction
'class' rung's data engine. It only pays off if a snapshot lands every trading day for
months; a silent stall would not surface until the archive is months-deep and useless.
These tests pin ``gex_archive_health.assess_archive_continuity`` against synthetic dates
(no network, no live-archive dependence, no clock) so the verdict logic can never silently
regress. All cases are deterministic and pass on a clean checkout / CI.
"""

from __future__ import annotations

import datetime as dt

import pytest

from backtest.tools import gex_archive_health as gh


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


# ── healthy accrual: latest == owed day, no gaps ──────────────────────────────
def test_green_when_caught_up_weekend_asof():
    # as_of = Mon 2026-06-29 (pre-close, expect_today False); owed = Fri 06-26.
    # Present through Fri 06-26 with no gaps -> GREEN (matches the live state this fire).
    present = [_d(x) for x in (
        "2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26")]
    v = gh.assess_archive_continuity(as_of=_d("2026-06-29"), present_dates=present)
    assert v["status"] == "GREEN", v
    assert v["latest_session"] == "2026-06-26"
    assert v["most_recent_expected"] == "2026-06-26"
    assert v["staleness_trading_days"] == 0
    assert v["interior_gaps"] == []


def test_green_weekday_asof_pre_close_owes_prev_weekday():
    # as_of = Wed 06-24 pre-close (expect_today False) -> owed = Tue 06-23.
    present = [_d("2026-06-22"), _d("2026-06-23")]
    v = gh.assess_archive_continuity(as_of=_d("2026-06-24"), present_dates=present)
    assert v["status"] == "GREEN", v
    assert v["most_recent_expected"] == "2026-06-23"


def test_expect_today_owes_today_after_close():
    # expect_today=True (post 15:55 ET): Wed 06-24 is owed; missing -> stale 1 -> YELLOW.
    present = [_d("2026-06-22"), _d("2026-06-23")]
    v = gh.assess_archive_continuity(
        as_of=_d("2026-06-24"), present_dates=present, expect_today=True)
    assert v["status"] == "YELLOW", v
    assert v["most_recent_expected"] == "2026-06-24"
    assert v["staleness_trading_days"] == 1


# ── staleness ladder ──────────────────────────────────────────────────────────
def test_yellow_when_one_to_two_days_stale():
    # owed = Fri 06-26, latest = Wed 06-24 -> 2 weekdays stale (Thu, Fri) -> YELLOW.
    present = [_d("2026-06-22"), _d("2026-06-23"), _d("2026-06-24")]
    v = gh.assess_archive_continuity(as_of=_d("2026-06-29"), present_dates=present)
    assert v["status"] == "YELLOW", v
    assert v["staleness_trading_days"] == 2


def test_red_when_more_than_max_stale():
    # owed = Fri 06-26, latest = Tue 06-23 -> 3 weekdays stale (> max 2) -> RED.
    present = [_d("2026-06-22"), _d("2026-06-23")]
    v = gh.assess_archive_continuity(as_of=_d("2026-06-29"), present_dates=present)
    assert v["status"] == "RED", v
    assert v["staleness_trading_days"] == 3
    assert "stalled" in v["reason"]


# ── interior gaps (the real silent-death signal) ──────────────────────────────
def test_yellow_on_single_interior_gap():
    # Wed 06-24 missing between present neighbours; caught up to owed Fri 06-26 -> YELLOW.
    present = [_d("2026-06-22"), _d("2026-06-23"),
               _d("2026-06-25"), _d("2026-06-26")]
    v = gh.assess_archive_continuity(as_of=_d("2026-06-29"), present_dates=present)
    assert v["status"] == "YELLOW", v
    assert v["interior_gaps"] == ["2026-06-24"]


def test_red_on_multiple_interior_gaps():
    # Two interior weekdays missing (06-23, 06-25) -> multi-day stall -> RED.
    present = [_d("2026-06-22"), _d("2026-06-24"), _d("2026-06-26")]
    v = gh.assess_archive_continuity(as_of=_d("2026-06-29"), present_dates=present)
    assert v["status"] == "RED", v
    assert v["interior_gaps"] == ["2026-06-23", "2026-06-25"]


# ── empty / missing archive ───────────────────────────────────────────────────
def test_red_when_archive_empty():
    v = gh.assess_archive_continuity(as_of=_d("2026-06-29"), present_dates=[])
    assert v["status"] == "RED", v
    assert v["latest_session"] is None
    assert v["days_accrued"] == 0


def test_missing_dir_is_red_not_raise(tmp_path):
    # A non-existent directory must be reported RED, never raise (fail-open reporter).
    v = gh.assess_archive_continuity(
        archive_dir=tmp_path / "does-not-exist", as_of=_d("2026-06-29"))
    assert v["status"] == "RED", v


# ── filename parsing across both banker schemas ───────────────────────────────
def test_parse_both_schemas_dedup(tmp_path):
    d = tmp_path / "gex-archive"
    d.mkdir()
    (d / "2026-06-25.json").write_text("{}", encoding="utf-8")          # Alpaca schema
    (d / "2026-06-25-cboe.json").write_text("{}", encoding="utf-8")     # CBOE schema (same day)
    (d / "2026-06-26-cboe.json").write_text("{}", encoding="utf-8")
    (d / "not-a-date.json").write_text("{}", encoding="utf-8")          # ignored
    (d / "2026-06-26-cboe.txt").write_text("x", encoding="utf-8")       # ignored (ext)
    dates = gh.parse_archive_dates(d)
    assert dates == [_d("2026-06-25"), _d("2026-06-26")]  # 06-25 counted once


# ── non-vacuous bite: tightening tolerance flips a previously-GREEN case ───────
def test_bite_max_stale_zero_flips_a_lagging_case():
    # owed = Fri 06-26, latest = Thu 06-25 -> 1 stale. Default(2): YELLOW; max_stale=0: RED.
    present = [_d("2026-06-24"), _d("2026-06-25")]
    base = gh.assess_archive_continuity(as_of=_d("2026-06-29"), present_dates=present)
    assert base["status"] == "YELLOW", base
    tight = gh.assess_archive_continuity(
        as_of=_d("2026-06-29"), present_dates=present, max_stale_trading_days=0)
    assert tight["status"] == "RED", tight  # the tolerance actually bites


def test_live_archive_verdict_is_structured_and_safe():
    # The real repo archive must produce a well-formed verdict without raising.
    v = gh.assess_archive_continuity(as_of=_d("2026-06-29"))
    assert v["status"] in ("GREEN", "YELLOW", "RED")
    assert set(v) >= {"status", "reason", "latest_session", "days_accrued",
                      "staleness_trading_days", "interior_gaps"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
