"""Guards for the BXM (CBOE BuyWrite Index) gate feasibility probe (chef-inbox
2026-07-10-prospector-cboe-buywrite-index-bxm-real-time-levels).

Pins:
  1. The causal prior-trading-day lookback never leaks a same-day-or-future BXM
     realized-vol reading (C6 no-look-ahead) -- the same discipline as
     vix1d_gate_probe.py's equivalent guard.
  2. A malformed trade date degrades gracefully (None reading), never crashes the
     whole probe (C7).
  3. The realized-vol computation is a genuine rolling annualized stdev of daily
     log returns (pinned against a hand-computed synthetic series so a future
     refactor can't silently change the math without a test noticing).
  4. The probe runs end-to-end against the real ledger + cached BXM csv and
     returns the expected schema.

Rail-4 CLEAR: read-only guard tests. No params/doctrine/orders/heartbeat/filters touched.
"""
import math
import os
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backtest"))

from autoresearch.bxm_gate_probe import (  # noqa: E402
    BXM_CSV,
    ROLL_WINDOW,
    _load_bxm_realized_vol,
    _prior_trading_day_reading,
    run,
)


def test_prior_trading_day_reading_is_causal_not_same_day():
    """The gate must never read a same-day-or-future BXM rvol reading (C6 no-look-ahead)."""
    readings = {
        "2026-05-14": 20.0,
        "2026-05-15": 999.0,  # the trade day itself -- must NOT leak
    }
    result = _prior_trading_day_reading(readings, "2026-05-15")
    assert result == 20.0, "must use the PRIOR day's reading, never same-day"


def test_prior_trading_day_reading_handles_malformed_date_without_crashing():
    """A malformed date field must degrade gracefully (None), not raise (C7)."""
    result = _prior_trading_day_reading({}, "not-a-real-date")
    assert result is None


def test_realized_vol_matches_hand_computed_stdev():
    """Pin the rolling-annualized-vol math against a hand-computed synthetic series
    so a future refactor can't silently change the formula without a test failing."""
    import csv
    import tempfile

    # 6 closes -> 5 log returns -> exactly 1 rolling window of size ROLL_WINDOW=5
    closes = [100.0, 101.0, 99.0, 102.0, 98.0, 103.0]
    dates = [f"2026-06-0{i+1}" for i in range(len(closes))]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    ) as f:
        w = csv.writer(f)
        w.writerow(["Date", "Close"])
        for d, c in zip(dates, closes):
            w.writerow([d, c])
        tmp_path = f.name

    try:
        import autoresearch.bxm_gate_probe as mod

        orig = mod.BXM_CSV
        mod.BXM_CSV = tmp_path
        try:
            out = mod._load_bxm_realized_vol()
        finally:
            mod.BXM_CSV = orig

        assert len(out) == 1, f"expected exactly 1 rolling reading, got {len(out)}"
        reading_date, ann_vol = next(iter(out.items()))
        assert reading_date == dates[-1]

        log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        mean = sum(log_rets) / len(log_rets)
        var = sum((x - mean) ** 2 for x in log_rets) / len(log_rets)
        expected = round(math.sqrt(var) * math.sqrt(252) * 100.0, 3)
        assert ann_vol == pytest.approx(expected, abs=1e-6)
    finally:
        os.unlink(tmp_path)


@pytest.mark.skipif(not os.path.exists(BXM_CSV), reason="cached BXM csv not present")
def test_probe_runs_end_to_end_without_crashing():
    result = run()
    assert result["probe"] == "bxm_gate_feasibility"
    assert result["n_total_trades_loaded"] > 0
    assert result["overall_verdict"] in (
        "FEASIBILITY_CONFIRMED_CANDIDATE_FOUND",
        "NO_CANDIDATE_CLEARS_BAR_YET",
    )
    assert isinstance(result["eval_bar_cleared"], bool)
    assert "method_disclosures" in result and "signal_adaptation" in result["method_disclosures"]
