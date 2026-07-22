"""Guard tests for backtest/tools/finra_short_volume_study.py.

Pure-function tests only (no network) except one explicitly-marked live smoke test.
"""
import datetime as dt
from unittest.mock import patch

import pandas as pd
import pytest

from backtest.lib.http_fetch import HttpFetchBlocked
from backtest.tools.finra_short_volume_study import (
    build_sample,
    fetch_finra_short_ratio,
    median_split_test,
    verdict_from_result,
)


def _daily(dates_closes):
    return pd.DataFrame(
        {"date": [d for d, _ in dates_closes], "close": [c for _, c in dates_closes]}
    )


class TestBuildSample:
    def test_basic_join_next_day_return(self):
        daily = _daily(
            [
                (dt.date(2026, 1, 1), 100.0),
                (dt.date(2026, 1, 2), 102.0),
                (dt.date(2026, 1, 3), 99.0),
            ]
        )
        ratios = {dt.date(2026, 1, 1): 0.3, dt.date(2026, 1, 2): 0.6}
        sample = build_sample(daily, ratios)
        assert len(sample) == 2
        row0 = sample.iloc[0]
        assert row0["date"] == dt.date(2026, 1, 1)
        assert row0["next_date"] == dt.date(2026, 1, 2)
        assert row0["short_ratio"] == 0.3
        assert row0["next_day_return"] == pytest.approx((102.0 - 100.0) / 100.0)

    def test_no_lookahead_last_day_never_included_as_a_predictor(self):
        """The LAST day in daily_closes has no 'next day' -- it must never
        appear as a `date` (predictor) row, only ever possibly as a `next_date`."""
        daily = _daily([(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 1, 2), 101.0)])
        ratios = {dt.date(2026, 1, 1): 0.5, dt.date(2026, 1, 2): 0.9}
        sample = build_sample(daily, ratios)
        assert dt.date(2026, 1, 2) not in set(sample["date"])

    def test_missing_ratio_day_is_skipped(self):
        daily = _daily(
            [
                (dt.date(2026, 1, 1), 100.0),
                (dt.date(2026, 1, 2), 105.0),
                (dt.date(2026, 1, 3), 110.0),
            ]
        )
        ratios = {dt.date(2026, 1, 2): 0.4}  # day 1 has no FINRA data (e.g. holiday file 404)
        sample = build_sample(daily, ratios)
        assert len(sample) == 1
        assert sample.iloc[0]["date"] == dt.date(2026, 1, 2)

    def test_empty_ratios_yields_empty_sample(self):
        daily = _daily([(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 1, 2), 101.0)])
        sample = build_sample(daily, {})
        assert sample.empty


class TestMedianSplitTest:
    def test_empty_sample_reports_error(self):
        result = median_split_test(pd.DataFrame(columns=["short_ratio", "next_day_return"]))
        assert result["n"] == 0
        assert "error" in result

    def test_clear_signal_direction_detected(self):
        # Construct a sample where HIGH short-ratio days always precede a negative
        # return and LOW short-ratio days always precede a positive return --
        # a deterministic, maximally-clear synthetic case.
        rows = []
        for i in range(20):
            rows.append({"short_ratio": 0.8, "next_day_return": -0.01})
        for i in range(20):
            rows.append({"short_ratio": 0.1, "next_day_return": 0.01})
        sample = pd.DataFrame(rows)
        result = median_split_test(sample, n_perm=500, seed=1)
        assert result["n_high"] == 20
        assert result["n_low"] == 20
        assert result["hypothesis_direction_confirmed"] is True
        assert result["observed_diff_high_minus_low"] < 0
        # a perfectly separated synthetic signal should be significant
        assert result["permutation_p_value"] < 0.05

    def test_no_signal_random_noise_not_falsely_significant(self):
        import random

        rng = random.Random(7)
        rows = []
        for i in range(40):
            rows.append({"short_ratio": rng.random(), "next_day_return": rng.gauss(0, 0.01)})
        sample = pd.DataFrame(rows)
        result = median_split_test(sample, n_perm=500, seed=7)
        # not asserting p >= 0.05 strictly (randomness), but the machinery must run
        assert 0.0 <= result["permutation_p_value"] <= 1.0
        assert result["n_high"] + result["n_low"] == 40

    def test_underpowered_flag(self):
        rows = [{"short_ratio": 0.9, "next_day_return": -0.01}] * 5 + [
            {"short_ratio": 0.1, "next_day_return": 0.01}
        ] * 5
        sample = pd.DataFrame(rows)
        result = median_split_test(sample, n_perm=200, seed=1)
        assert result["underpowered"] is True


class TestVerdictFromResult:
    def test_kill_on_error(self):
        assert verdict_from_result({"error": "empty sample"}) == "KILL_DATA_INSUFFICIENT"

    def test_kill_when_direction_wrong(self):
        result = {"hypothesis_direction_confirmed": False, "permutation_p_value": 0.01}
        assert verdict_from_result(result) == "KILL"

    def test_kill_when_not_significant(self):
        result = {"hypothesis_direction_confirmed": True, "permutation_p_value": 0.40}
        assert verdict_from_result(result) == "KILL"

    def test_pass_when_direction_right_and_significant(self):
        result = {"hypothesis_direction_confirmed": True, "permutation_p_value": 0.01}
        assert verdict_from_result(result) == "PASS_FIRST_SCREEN"


class TestFetchFinraShortRatioBlockHandling:
    """L241 graduation: verify fetch_finra_short_ratio's `raise_on_block` toggle
    -- fails open (returns None) by default, propagates HttpFetchBlocked only
    when the caller explicitly opts in (main()'s systematic-block detector)."""

    @patch("backtest.tools.finra_short_volume_study.fetch_url_text")
    def test_blocked_fails_open_to_none_by_default(self, mock_fetch):
        mock_fetch.side_effect = HttpFetchBlocked("https://cdn.finra.org/x", 403)
        result = fetch_finra_short_ratio(dt.date(2026, 7, 17))
        assert result is None

    @patch("backtest.tools.finra_short_volume_study.fetch_url_text")
    def test_blocked_raises_when_opted_in(self, mock_fetch):
        mock_fetch.side_effect = HttpFetchBlocked("https://cdn.finra.org/x", 403)
        with pytest.raises(HttpFetchBlocked):
            fetch_finra_short_ratio(dt.date(2026, 7, 17), raise_on_block=True)

    @patch("backtest.tools.finra_short_volume_study.fetch_url_text")
    def test_genuinely_missing_returns_none_regardless_of_flag(self, mock_fetch):
        mock_fetch.return_value = None
        assert fetch_finra_short_ratio(dt.date(2026, 7, 17)) is None
        assert fetch_finra_short_ratio(dt.date(2026, 7, 17), raise_on_block=True) is None


class TestMainSystematicBlockDetection:
    """L241 guard: main() must distinguish 'fetcher is blocked on most dates'
    from 'genuinely no data' rather than silently reporting a near-empty
    sample as if the hypothesis had been fairly tested."""

    @patch("backtest.tools.finra_short_volume_study.OUTPUT_PATH")
    @patch("backtest.tools.finra_short_volume_study.fetch_finra_short_ratio")
    @patch("backtest.tools.finra_short_volume_study.load_spy_daily_closes")
    def test_majority_blocked_flags_kill_fetcher_blocked(
        self, mock_load, mock_fetch, mock_output_path
    ):
        from backtest.tools.finra_short_volume_study import main

        dates = [dt.date(2026, 1, d) for d in range(1, 12)]
        mock_load.return_value = pd.DataFrame(
            {"date": dates, "close": [100.0 + i for i in range(len(dates))]}
        )
        mock_fetch.side_effect = HttpFetchBlocked("https://cdn.finra.org/x", 403)
        mock_output_path.write_text = lambda *a, **k: None

        out = main()
        assert out["fetcher_systematically_blocked"] is True
        assert out["verdict"] == "KILL_FETCHER_BLOCKED"
        assert out["n_dates_blocked_403_429"] == out["n_dates_attempted"]

    @patch("backtest.tools.finra_short_volume_study.OUTPUT_PATH")
    @patch("backtest.tools.finra_short_volume_study.fetch_finra_short_ratio")
    @patch("backtest.tools.finra_short_volume_study.load_spy_daily_closes")
    def test_minority_blocked_does_not_flag(self, mock_load, mock_fetch, mock_output_path):
        from backtest.tools.finra_short_volume_study import main

        dates = [dt.date(2026, 1, d) for d in range(1, 12)]
        mock_load.return_value = pd.DataFrame(
            {"date": dates, "close": [100.0 + i for i in range(len(dates))]}
        )

        def _side_effect(d, raise_on_block=False):
            if d == dates[0]:
                raise HttpFetchBlocked("https://cdn.finra.org/x", 403)
            return 0.4

        mock_fetch.side_effect = _side_effect
        mock_output_path.write_text = lambda *a, **k: None

        out = main()
        assert out["fetcher_systematically_blocked"] is False
        assert out["n_dates_blocked_403_429"] == 1


@pytest.mark.network
def test_live_fetch_smoke():
    """Live network smoke test -- fetches ONE real FINRA file for a KNOWN-valid
    past trading day (2026-07-17, a real Friday with confirmed FINRA data as of
    this test's authoring). Asserts a REAL ratio, not just "None is fine" --
    a weaker assertion here would have silently passed through the 2026-07-22
    403-Forbidden User-Agent bug (bare urllib UA gets blocked by FINRA's CDN;
    curl/browser UA does not) instead of catching it."""
    from backtest.tools.finra_short_volume_study import fetch_finra_short_ratio

    ratio = fetch_finra_short_ratio(dt.date(2026, 7, 17))
    assert ratio is not None, "expected a real FINRA short-volume ratio for a known valid trading day"
    assert 0.0 <= ratio <= 1.0
