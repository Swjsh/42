"""Guards for the VIX1D gate feasibility probe (chef-inbox 2026-07-09-prospector-vix1d_gate).

Two things this pins:
  1. `journal/trades.csv` -- J's real-fills ledger, C1's "only WR authority" -- must never
     contain a stray line-number-prefix contamination (a literal "<digits>\\t" glued onto a
     data row, e.g. from an accidental `cat -n` paste). Found LIVE on row 13 (2026-07-22
     conductor fire) corrupting a real 2026-05-18 Gamma-Bold trade's date field enough to
     break csv-module row-count assumptions in any downstream probe. Fixed once; this guard
     makes a re-occurrence fail LOUD instead of silently poisoning a probe's date parsing.
  2. The probe itself runs end-to-end on the real ledger without crashing and returns the
     expected schema -- so a future trades.csv edit (new column, new stray row) that would
     silently break the probe's positional-index assumptions is caught by CI, not by a
     3rd conductor fire discovering `ValueError: Invalid isoformat string` live again.

Rail-4 CLEAR: read-only guard tests. No params/doctrine/orders/heartbeat/filters touched.
"""
import csv
import os
import re
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backtest"))

from autoresearch.vix1d_gate_probe import (  # noqa: E402
    TRADES_CSV,
    VIX_CSV,
    _load_real_trades,
    _prior_trading_day_vix,
    run,
)

_LINE_NUM_PREFIX = re.compile(r"^\d+\t")


def test_trades_csv_has_no_line_number_prefix_contamination():
    """Guards the exact L-class foot-gun found live: a stray '<n>\\t' glued onto a data
    row's first field (from a cat-n-style paste) breaks positional CSV parsing downstream."""
    with open(TRADES_CSV, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        next(r)  # header
        for i, row in enumerate(r, start=2):
            assert row and not _LINE_NUM_PREFIX.match(row[0]), (
                f"trades.csv row {i} field[0]={row[0]!r} looks line-number-prefixed "
                "(cat-n contamination) -- this breaks date parsing for any real-fills probe"
            )


def test_trades_csv_all_dates_parseable():
    """Every loaded row must have a genuinely ISO-parseable date -- a stricter, faster-
    failing companion to the prefix-contamination check above (catches ANY malformed
    date, not just the one contamination pattern already seen)."""
    import datetime as dt

    rows = _load_real_trades()
    assert len(rows) > 0
    bad = [r["date"] for r in rows if _bad_date(r["date"])]
    assert not bad, f"unparseable dates in trades.csv: {bad}"


def _bad_date(s: str) -> bool:
    import datetime as dt

    try:
        dt.date.fromisoformat(s)
        return False
    except ValueError:
        return True


def test_prior_trading_day_vix_is_causal_not_same_day():
    """The gate must never read a same-day-or-future VIX reading (C6 no-look-ahead)."""
    vix_by_date = {
        "2026-05-14": {"vix1d": 20.0, "vix30": 18.0},
        "2026-05-15": {"vix1d": 99.0, "vix30": 99.0},  # the trade day itself -- must NOT leak
    }
    result = _prior_trading_day_vix(vix_by_date, "2026-05-15")
    assert result["vix1d"] == 20.0, "must use the PRIOR day's close, never same-day"


def test_prior_trading_day_vix_handles_malformed_date_without_crashing():
    """A malformed date field must degrade gracefully (None reading), not raise -- so one
    corrupted row can never crash the whole probe fire again (C7)."""
    result = _prior_trading_day_vix({}, "not-a-real-date")
    assert result == {"vix1d": None, "vix30": None}


@pytest.mark.skipif(not os.path.exists(VIX_CSV), reason="cached VIX1D/VIX30 csv not present")
def test_probe_runs_end_to_end_without_crashing():
    result = run()
    assert result["probe"] == "vix1d_gate_feasibility"
    assert result["n_total_trades_loaded"] > 0
    assert result["overall_verdict"] in (
        "FEASIBILITY_CONFIRMED_CANDIDATE_FOUND",
        "NO_CANDIDATE_CLEARS_BAR_YET",
    )
    assert "candidates" in result and len(result["candidates"]) >= 3
    assert isinstance(result["eval_bar_cleared"], bool)
