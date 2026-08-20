"""Guard for multi/lib/scanners.py -- the multi-symbol lane's free Alpaca candidate scanners.

Deterministic, network-free: every test feeds realistic fixture dicts straight into the pure
parse/compute layer, or calls a compute function directly. No HTTP, no .mcp.json read, no live
network anywhere in this file. Two tests are RED-PROOFED per the build instructions (broken on
purpose, run, shown to fail, then restored -- evidence quoted in the session report):

  1. test_relative_volume_exact_math -- the relative-volume math test.
  2. test_run_movers_distinguishes_error_from_empty -- the fail-loud test.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_multi_scanners.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi.lib import scanners as sc  # noqa: E402


# --------------------------------------------------------------------------------------
# movers -- realistic fixture
# --------------------------------------------------------------------------------------

def test_parse_movers_realistic_fixture():
    # Shaped like the verified-live 2026-08-19 response: MRNA +177.0% gainer among the mix.
    raw = {
        "gainers": [
            {"symbol": "MRNA", "percent_change": 177.0, "price": 45.23},
            {"symbol": "SMALLCAP", "percent_change": 3.2, "price": 10.0},  # below threshold
        ],
        "losers": [
            {"symbol": "DROPCO", "percent_change": -12.5, "price": 5.0},
            {"symbol": "FLATCO", "percent_change": -1.1, "price": 20.0},  # below threshold
        ],
    }
    candidates, raw_count = sc.parse_movers(raw, min_abs_pct=8.0)
    assert raw_count == 4
    symbols = [c.symbol for c in candidates]
    assert symbols == ["MRNA", "DROPCO"]  # sorted by |%change| descending
    assert candidates[0].direction == "gainer"
    assert candidates[0].percent_change == 177.0
    assert candidates[1].direction == "loser"
    assert candidates[1].percent_change == -12.5


def test_parse_movers_empty_gainers_and_losers_is_zero_raw_not_error():
    candidates, raw_count = sc.parse_movers({"gainers": [], "losers": []}, min_abs_pct=8.0)
    assert candidates == []
    assert raw_count == 0


# --------------------------------------------------------------------------------------
# most_actives -- realistic fixture, both metrics
# --------------------------------------------------------------------------------------

def test_parse_most_actives_realistic_fixture_volume_metric():
    raw = {"most_actives": [
        {"symbol": "TSLA", "volume": 50000000, "trade_count": 300000},
        {"symbol": "AAPL", "volume": 40000000, "trade_count": 250000},
    ]}
    candidates, raw_count = sc.parse_most_actives(raw, metric="volume")
    assert raw_count == 2
    assert candidates[0].symbol == "TSLA" and candidates[0].rank == 1
    assert candidates[1].symbol == "AAPL" and candidates[1].rank == 2
    assert all(c.metric == "volume" for c in candidates)
    assert candidates[0].volume == 50000000.0


def test_parse_most_actives_trade_count_metric_tagged_separately():
    raw = {"most_actives": [{"symbol": "SPY", "volume": 1e8, "trade_count": 900000}]}
    candidates, _ = sc.parse_most_actives(raw, metric="trades")
    assert candidates[0].metric == "trades"
    assert candidates[0].trade_count == 900000.0


# --------------------------------------------------------------------------------------
# news classification -- keyword hits AND the ambiguous "other" case
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("headline,expected", [
    ("Moderna Announces Positive Phase 3 Trial Results and FDA Submission", "trial_fda"),
    ("Acme Corp to Acquire Widget Inc in $2B Deal", "m_and_a"),
    ("Acme Reports Q2 Results, Beats Estimates on Revenue", "earnings"),
    ("Acme Raises Full-Year Guidance After Strong Demand", "guidance"),
    ("Analysts Upgrade Acme to Buy, Raise Price Target to $50", "analyst"),
])
def test_classify_headline_hits_keywords(headline, expected):
    assert sc.classify_headline(headline) == expected


def test_classify_headline_ambiguous_lands_in_other_not_force_fit():
    # No keyword from any category appears here -- "partnership"/"announces"/"product line"
    # are deliberately NOT in any keyword list. Must land in "other", not be guessed into a
    # nearby-sounding bucket like m_and_a.
    headline = "XYZ Corp Announces New Product Line Partnership With Retailers"
    assert sc.classify_headline(headline) == "other"


def test_parse_news_realistic_fixture_classes_and_tags_symbols():
    now_utc = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)
    raw = {"news": [
        {"id": 1, "headline": "Moderna Announces Positive Phase 3 Trial Results and FDA Submission",
         "created_at": "2026-08-19T10:47:00Z", "source": "Benzinga", "symbols": ["MRNA"],
         "url": "https://example.com/1"},
        {"id": 2, "headline": "Acme Corp to Acquire Widget Inc in $2B Deal",
         "created_at": "2026-08-19T09:00:00Z", "source": "Reuters", "symbols": ["ACME", "WIDG"]},
        {"id": 3, "headline": "XYZ Corp Announces New Product Line Partnership With Retailers",
         "created_at": "2026-08-19T08:00:00Z", "source": "PR Newswire", "symbols": ["XYZ"]},
    ]}
    items, raw_count = sc.parse_news(raw, now_utc, lookback_hours=24)
    assert raw_count == 3
    by_id = {i.id: i for i in items}
    assert by_id[1].category == "trial_fda"
    assert by_id[1].symbols == ("MRNA",)
    assert by_id[2].category == "m_and_a"
    assert by_id[2].symbols == ("ACME", "WIDG")
    assert by_id[3].category == "other"
    assert abs(by_id[1].age_hours - 1.2166666666) < 1e-6


def test_parse_news_drops_items_older_than_lookback():
    now_utc = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)
    raw = {"news": [
        {"id": 1, "headline": "Old news item", "created_at": "2026-08-17T12:00:00Z",
         "source": "Wire", "symbols": ["OLD"]},
        {"id": 2, "headline": "Fresh news item", "created_at": "2026-08-19T11:00:00Z",
         "source": "Wire", "symbols": ["NEW"]},
    ]}
    items, raw_count = sc.parse_news(raw, now_utc, lookback_hours=24)
    assert raw_count == 2  # both counted before the filter
    assert [i.id for i in items] == [2]  # only the fresh one survives


# --------------------------------------------------------------------------------------
# Relative volume / gap math -- RED-PROOFED (see report for break/restore evidence)
# --------------------------------------------------------------------------------------

def test_avg_daily_volume_known_value():
    volumes = [1_000_000.0] * 25  # only the last 20 count
    assert sc.avg_daily_volume(volumes, window=20) == 1_000_000.0


def test_avg_daily_volume_insufficient_history_returns_none():
    assert sc.avg_daily_volume([1_000_000.0] * 5, window=20) is None


def test_relative_volume_exact_math():
    """MRNA-shaped case: ~28x normal volume. Exact, known-by-construction number."""
    assert sc.relative_volume(28_000_000.0, 1_000_000.0) == 28.0
    assert sc.relative_volume(2_500_000.0, 500_000.0) == 5.0


def test_relative_volume_missing_or_zero_average_returns_none_not_fabricated():
    assert sc.relative_volume(1_000_000.0, None) is None
    assert sc.relative_volume(1_000_000.0, 0.0) is None
    assert sc.relative_volume(None, 1_000_000.0) is None


def test_gap_pct_known_value():
    # Prior close 16.30 -> current 45.23: matches the MRNA-shaped +177.0% mover fixture above.
    pct = sc.gap_pct(16.30, 45.23)
    assert abs(pct - 177.48466257668713) < 1e-6


def test_gap_pct_zero_prior_close_returns_none():
    assert sc.gap_pct(0.0, 10.0) is None


# --------------------------------------------------------------------------------------
# Gap candidate build -- realistic fixture (MRNA-shaped: prior close 16.30, run to 45.23,
# volume 28,000,000 vs a flat 1,000,000/day trailing average -> ~177% gap, ~28x rel volume)
# --------------------------------------------------------------------------------------

def _flat_bars(n: int, volume: float, start_date: str = "2026-07-01") -> list[dict]:
    base = datetime.fromisoformat(start_date)
    from datetime import timedelta
    return [{"t": (base + timedelta(days=i)).strftime("%Y-%m-%dT00:00:00Z"),
              "o": 16.0, "h": 16.5, "l": 15.5, "c": 16.3, "v": volume} for i in range(n)]


def test_build_gap_candidate_mrna_shaped_realistic_fixture():
    snapshots_raw = {
        "MRNA": {
            "prevDailyBar": {"c": 16.30},
            "dailyBar": {"c": 45.00, "v": 28_000_000},
            "latestTrade": {"p": 45.23},
        },
    }
    bars_by_symbol = {"MRNA": _flat_bars(25, 1_000_000.0)}
    out = sc.compute_gap_candidates(snapshots_raw, bars_by_symbol, as_of_et="2026-08-19T10:00:00", window=20)
    assert len(out) == 1
    row = out[0]
    assert row.symbol == "MRNA"
    assert row.prior_close == 16.30
    assert row.current_price == 45.23
    assert abs(row.gap_pct - 177.48466257668713) < 1e-6
    assert row.avg_20d_volume == 1_000_000.0
    assert row.relative_volume == 28.0


def test_compute_gap_candidates_skips_symbol_missing_prior_close():
    snapshots_raw = {"NODATA": {"prevDailyBar": {}, "dailyBar": {"c": 10.0, "v": 1000},
                                 "latestTrade": {"p": 10.5}}}
    out = sc.compute_gap_candidates(snapshots_raw, {"NODATA": _flat_bars(25, 1000.0)}, "2026-08-19T10:00:00")
    assert out == []  # never fabricates a prior_close


def test_compute_gap_candidates_insufficient_bar_history_gives_none_relative_volume_not_zero():
    snapshots_raw = {"NEW": {"prevDailyBar": {"c": 10.0}, "dailyBar": {"c": 11.0, "v": 500_000},
                              "latestTrade": {"p": 11.0}}}
    out = sc.compute_gap_candidates(snapshots_raw, {"NEW": _flat_bars(5, 100_000.0)}, "2026-08-19T10:00:00")
    assert len(out) == 1
    assert out[0].avg_20d_volume is None
    assert out[0].relative_volume is None  # None, never a fabricated 0.0 or the raw volume


def test_drop_today_bar_removes_only_todays_date():
    bars = [{"t": "2026-08-18T00:00:00Z", "v": 1}, {"t": "2026-08-19T00:00:00Z", "v": 2}]
    out = sc._drop_today_bar(bars, "2026-08-19")
    assert len(out) == 1
    assert out[0]["t"].startswith("2026-08-18")


def test_select_gap_candidates_or_semantics_and_sort_by_relative_volume():
    big_gap_low_vol = sc.GapCandidate("BIGGAP", 10.0, 16.0, 60.0, 100_000, 200_000, 0.5, "t")
    low_gap_big_vol = sc.GapCandidate("BIGVOL", 10.0, 10.2, 2.0, 5_000_000, 500_000, 10.0, "t")
    neither = sc.GapCandidate("QUIET", 10.0, 10.05, 0.5, 100_000, 500_000, 0.2, "t")
    unknown_vol = sc.GapCandidate("UNKVOL", 10.0, 15.0, 50.0, 100_000, None, None, "t")
    out = sc.select_gap_candidates([big_gap_low_vol, low_gap_big_vol, neither, unknown_vol],
                                    min_gap_pct=10.0, min_rel_volume=3.0)
    symbols = [c.symbol for c in out]
    assert "QUIET" not in symbols  # fails both thresholds
    assert "BIGGAP" in symbols and "BIGVOL" in symbols and "UNKVOL" in symbols  # OR semantics
    # relative_volume descending, unknown (None) sorts last
    assert symbols[0] == "BIGVOL"  # highest known relative_volume
    assert symbols[-1] == "UNKVOL"  # None relative_volume sorts last


# --------------------------------------------------------------------------------------
# Composite merge -- signals stay visible, no opaque score
# --------------------------------------------------------------------------------------

def test_merge_composite_keeps_individual_signals_visible():
    mover = sc.MoverCandidate("AAA", "gainer", 15.0, 100.0)
    active = sc.MostActiveCandidate("AAA", "volume", 1, 5_000_000.0, 20000.0)
    gap = sc.GapCandidate("AAA", 10.0, 11.5, 15.0, 5_000_000, 1_000_000, 5.0, "t")
    news = sc.NewsItem(1, "AAA headline", "2026-08-19T10:00:00Z", "Wire", ("AAA",), "other")
    only_news = sc.NewsItem(2, "BBB headline", "2026-08-19T10:00:00Z", "Wire", ("BBB",), "other")

    rows = sc.merge_composite([mover], [active], [gap], [news, only_news])
    by_symbol = {r["symbol"]: r for r in rows}

    aaa = by_symbol["AAA"]
    assert aaa["movers"]["percent_change"] == 15.0       # each scanner's raw dict is visible
    assert aaa["most_actives"][0]["volume"] == 5_000_000.0
    assert aaa["gap"]["relative_volume"] == 5.0
    assert len(aaa["news"]) == 1
    assert aaa["signal_count"] == 4
    assert "score" not in aaa  # no single opaque blended score field

    bbb = by_symbol["BBB"]
    assert bbb["movers"] is None and bbb["gap"] is None and bbb["most_actives"] == []
    assert bbb["signal_count"] == 1

    # sorted by signal_count descending
    assert rows[0]["symbol"] == "AAA"


def test_merge_composite_empty_inputs_returns_empty_list():
    assert sc.merge_composite([], [], [], []) == []


# --------------------------------------------------------------------------------------
# flatten_universe
# --------------------------------------------------------------------------------------

def test_flatten_universe_dedupes_and_skips_doc_keys():
    block = {
        "_doc": "some prose, not a category",
        "index_etf": ["SPY", "QQQ"],
        "mega_tech": ["AAPL", "SPY"],  # SPY repeated
        "_total_note": "70 names",
    }
    out = sc.flatten_universe(block)
    assert out == ["SPY", "QQQ", "AAPL"]  # first-seen order, deduped, doc keys skipped


# --------------------------------------------------------------------------------------
# Fail-loud: error vs empty -- RED-PROOFED (see report for break/restore evidence)
# --------------------------------------------------------------------------------------

def test_run_movers_distinguishes_error_from_empty(monkeypatch):
    now = sc.et_now()

    def _raise(*a, **kw):
        raise sc.ScannerFetchError("HTTP 500 from /v1beta1/screener/stocks/movers: boom")

    monkeypatch.setattr(sc, "fetch_movers_raw", _raise)
    errored = sc.run_movers("k", "s", min_abs_pct=8.0, now_et=now)
    assert errored.ok is False
    assert errored.error is not None and "boom" in errored.error
    assert errored.candidates == ()

    def _empty(*a, **kw):
        return {"gainers": [{"symbol": "FLAT", "percent_change": 0.1, "price": 1.0}], "losers": []}

    monkeypatch.setattr(sc, "fetch_movers_raw", _empty)
    ran_clean = sc.run_movers("k", "s", min_abs_pct=8.0, now_et=now)
    assert ran_clean.ok is True
    assert ran_clean.error is None
    assert ran_clean.candidates == ()          # nothing cleared the threshold
    assert ran_clean.raw_count == 1            # but the API DID return something

    # The two outcomes must be distinguishable from each other, not just individually sane.
    assert errored.ok != ran_clean.ok


def test_run_gap_empty_universe_is_a_named_error_not_silent_empty():
    now = sc.et_now()
    result = sc.run_gap("k", "s", symbols=[], min_gap_pct=5.0, min_rel_volume=3.0, now_et=now)
    assert result.ok is False
    assert result.error == "empty_symbol_universe"


def test_run_composite_reports_error_when_all_upstream_failed():
    now = sc.et_now().isoformat()
    failed = lambda name: sc.ScannerResult(name, False, tuple(), 0, f"{name} broke", now)
    result = sc.run_composite(failed("movers"), failed("most_actives"), failed("gap"), failed("news"))
    assert result.ok is False
    assert "all upstream scanners failed" in result.error


def test_run_composite_succeeds_when_one_upstream_ok_even_if_empty():
    now = sc.et_now().isoformat()
    ok_empty = sc.ScannerResult("movers", True, tuple(), 5, None, now)
    failed = lambda name: sc.ScannerResult(name, False, tuple(), 0, f"{name} broke", now)
    result = sc.run_composite(ok_empty, failed("most_actives"), failed("gap"), failed("news"))
    assert result.ok is True
    assert result.candidates == ()


def test_scanner_result_to_dict_json_safe_and_shows_counts():
    mover = sc.MoverCandidate("AAA", "gainer", 15.0, 100.0)
    result = sc.ScannerResult("movers", True, (mover,), 3, None, "2026-08-19T10:00:00")
    d = sc.scanner_result_to_dict(result)
    assert d["candidate_count"] == 1
    assert d["raw_count"] == 3
    assert d["candidates"][0]["symbol"] == "AAA"
    import json
    json.dumps(d)  # must not raise -- proves it's actually JSON-serializable
