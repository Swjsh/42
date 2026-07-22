"""Guards for the FRED 10Y-2Y Treasury yield-curve gate feasibility probe (chef-inbox
2026-07-10-prospector-fred-daily-treasury-par-yield-curve-10y-).

Pins:
  1. The causal prior-trading-day lookback never leaks a same-day-or-future spread
     reading (C6 no-look-ahead) -- same discipline as the sibling VIX1D/BXM probes.
  2. The `skip` parameter correctly walks PAST the most recent reading for the
     day-over-day slope gate (skip=1 must be strictly older than skip=0).
  3. A malformed trade date degrades gracefully (None), never crashes the whole
     probe (C7).
  4. The spread computation (DGS10 - DGS2) is pinned against a hand-built synthetic
     CSV so a future refactor can't silently invert or rescale it.
  5. The probe runs end-to-end against the real ledger + cached FRED csv and
     returns the expected schema.

Rail-4 CLEAR: read-only guard tests. No params/doctrine/orders/heartbeat/filters touched.
"""
import csv
import os
import sys
import tempfile

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backtest"))

from autoresearch.fred_yield_curve_probe import (  # noqa: E402
    FRED_CSV,
    _load_spread_daily,
    _prior_trading_day_spread,
    run,
)


def test_prior_trading_day_spread_is_causal_not_same_day():
    """The gate must never read a same-day-or-future spread reading (C6 no-look-ahead)."""
    spreads = {
        "2026-05-14": 0.40,
        "2026-05-15": 999.0,  # the trade day itself -- must NOT leak
    }
    result = _prior_trading_day_spread(spreads, "2026-05-15", skip=0)
    assert result == ("2026-05-14", 0.40), "must use the PRIOR day's reading, never same-day"


def test_prior_trading_day_spread_skip_walks_strictly_older():
    """skip=1 (used for the day-over-day slope gate) must return a STRICTLY OLDER
    reading than skip=0, never the same one twice."""
    spreads = {
        "2026-05-12": 0.35,
        "2026-05-13": 0.38,
        "2026-05-14": 0.40,
    }
    most_recent = _prior_trading_day_spread(spreads, "2026-05-15", skip=0)
    one_before = _prior_trading_day_spread(spreads, "2026-05-15", skip=1)
    assert most_recent == ("2026-05-14", 0.40)
    assert one_before == ("2026-05-13", 0.38)
    assert one_before[0] < most_recent[0], "skip=1 must be strictly older than skip=0"


def test_prior_trading_day_spread_handles_malformed_date_without_crashing():
    """A malformed date field must degrade gracefully (None), not raise (C7)."""
    result = _prior_trading_day_spread({}, "not-a-real-date", skip=0)
    assert result is None


def test_load_spread_daily_matches_hand_computed_dgs10_minus_dgs2():
    """Pin the spread math (DGS10 - DGS2) against a hand-built synthetic FRED csv so
    a future refactor can't silently invert the sign or rescale the value."""
    rows = [
        ("2026-06-01", "4.30", "3.80"),
        ("2026-06-02", "4.35", "3.75"),
        ("2026-06-03", "", "3.90"),  # blank DGS10 (holiday) -- must be skipped, not crash
    ]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    ) as f:
        w = csv.writer(f)
        w.writerow(["observation_date", "DGS10", "DGS2", "DGS3MO"])
        for d, d10, d2 in rows:
            w.writerow([d, d10, d2, ""])
        tmp_path = f.name

    try:
        import autoresearch.fred_yield_curve_probe as mod

        orig = mod.FRED_CSV
        mod.FRED_CSV = tmp_path
        try:
            out = mod._load_spread_daily()
        finally:
            mod.FRED_CSV = orig

        assert out == {
            "2026-06-01": round(4.30 - 3.80, 3),
            "2026-06-02": round(4.35 - 3.75, 3),
        }, "blank DGS10 row must be skipped, not crash or coerce to 0"
    finally:
        os.unlink(tmp_path)


@pytest.mark.skipif(not os.path.exists(FRED_CSV), reason="cached FRED csv not present")
def test_probe_runs_end_to_end_without_crashing():
    result = run()
    assert result["probe"] == "fred_yield_curve_gate_feasibility"
    assert result["n_total_trades_loaded"] > 0
    assert result["overall_verdict"] in (
        "FEASIBILITY_CONFIRMED_CANDIDATE_FOUND",
        "NO_CANDIDATE_CLEARS_BAR_YET",
    )
    assert isinstance(result["eval_bar_cleared"], bool)
    assert "method_disclosures" in result and "signal_adaptation" in result["method_disclosures"]
    # both a level gate and a slope gate must have been scored
    assert any(k.startswith("level_gate::") for k in result["candidates"])
    assert any(k.startswith("slope_gate::") for k in result["candidates"])
