"""Guard for setup/scripts/sector_heat_scanner.py (WEEKLY-OPTIONS-PROGRAM.md Sec 6).

Deterministic, network-free. Every test either feeds synthetic DailyBars/price arrays
straight into the pure compute layer, or calls a compute function directly -- no HTTP,
no yfinance, no .mcp.json read. Two tests are RED-proofed per the build instructions
(broken on purpose, shown to fail, then restored -- evidence quoted in the session report):

  1. test_leader_ranks_first_by_construction -- the ranking test.
  2. test_build_snapshot_raises_on_empty_result -- the empty-input failure test.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_sector_heat_scanner.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO / "setup" / "scripts"), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import sector_heat_scanner as shs  # noqa: E402


# --------------------------------------------------------------------------------------
# Synthetic data builders (no network)
# --------------------------------------------------------------------------------------

def _dates(n: int) -> tuple[str, ...]:
    base = datetime(2025, 1, 1)
    return tuple((base + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n))


def _bars(ticker: str, closes: list[float], n: int, source: str = "test") -> "shs.DailyBars":
    volumes = tuple(1_000_000.0 for _ in range(n))
    return shs.DailyBars(ticker, _dates(n), tuple(closes), volumes, source, f"ok_{n}bars")


# --------------------------------------------------------------------------------------
# Composite weights
# --------------------------------------------------------------------------------------

def test_composite_weights_sum_to_one():
    assert abs(sum(shs.COMPOSITE_WEIGHTS.values()) - 1.0) < 1e-9


def test_composite_heat_score_missing_component_returns_none():
    # ma_stack_z missing (None) -> whole score must be None, never a partial number.
    assert shs.composite_heat_score(1.0, 0.5, None, 0.2) is None


def test_composite_heat_score_vary_and_assert():
    """Changing ONE component must change the score by exactly that component's weight
    times the delta -- proves each weight is actually wired, not a dead knob (house rule:
    vary-and-assert)."""
    base = shs.composite_heat_score(1.0, 0.5, -0.5, 0.2)
    bumped = shs.composite_heat_score(2.0, 0.5, -0.5, 0.2)  # rs_1m_z: 1.0 -> 2.0
    assert base is not None and bumped is not None
    expected_delta = shs.COMPOSITE_WEIGHTS["rs_1m_z"] * 1.0
    assert abs((bumped - base) - expected_delta) < 1e-9
    assert bumped != base

    # Same check for a second component to prove it isn't just rs_1m_z that's wired.
    bumped2 = shs.composite_heat_score(1.0, 0.5, 0.5, 0.2)  # ma_stack_z: -0.5 -> 0.5
    expected_delta2 = shs.COMPOSITE_WEIGHTS["ma_stack_z"] * 1.0
    assert abs((bumped2 - base) - expected_delta2) < 1e-9


# --------------------------------------------------------------------------------------
# Quadrant boundaries
# --------------------------------------------------------------------------------------

def test_quadrant_label_boundaries():
    assert shs.quadrant_label(0.0, 0.0) == "LEADING"       # >=0, >=0
    assert shs.quadrant_label(0.0, -0.0001) == "WEAKENING"  # >=0, <0
    assert shs.quadrant_label(-0.0001, -0.0001) == "LAGGING"  # <0, <0
    assert shs.quadrant_label(-0.0001, 0.0) == "IMPROVING"   # <0, >=0
    assert shs.quadrant_label(None, 1.0) == "UNKNOWN"
    assert shs.quadrant_label(1.0, None) == "UNKNOWN"


# --------------------------------------------------------------------------------------
# zscore
# --------------------------------------------------------------------------------------

def test_zscore_none_passthrough():
    out = shs.zscore([1.0, None, 3.0, 5.0])
    assert out[1] is None
    assert all(v is not None for i, v in enumerate(out) if i != 1)


def test_zscore_insufficient_valid_values_returns_all_none():
    assert shs.zscore([1.0]) == [None]
    assert shs.zscore([None, None]) == [None, None]


def test_zscore_constant_values_returns_zero_not_nan():
    out = shs.zscore([5.0, 5.0, 5.0])
    assert out == [0.0, 0.0, 0.0]


# --------------------------------------------------------------------------------------
# pct_change_n / ma_stack_score / dollar_volume_change_pct
# --------------------------------------------------------------------------------------

def test_pct_change_n_insufficient_history_returns_none():
    assert shs.pct_change_n([1.0, 2.0, 3.0], 5) is None


def test_pct_change_n_known_value():
    # Explicit known-by-construction case: value 5 periods back = 100, latest = 110.
    vals = [100.0, 100.0, 100.0, 100.0, 100.0, 110.0]
    assert abs(shs.pct_change_n(vals, 5) - 10.0) < 1e-9


def test_ma_stack_score_known_construction():
    # Monotonically rising closes -> close > sma20 > sma50 > sma200 -> full stack score 3.
    closes = [100.0 + i * 0.5 for i in range(220)]
    assert shs.ma_stack_score(closes) == 3
    # Monotonically falling closes -> the reverse stack -> score 0.
    closes_down = [200.0 - i * 0.5 for i in range(220)]
    assert shs.ma_stack_score(closes_down) == 0
    # Too few bars for SMA200 -> None, never a fabricated default.
    assert shs.ma_stack_score([100.0] * 50) is None


def test_dollar_volume_change_pct_known_direction():
    # Flat price, volume doubles in the recent window -> positive dollar-volume change.
    closes = [50.0] * 42
    volumes = [1_000_000.0] * 21 + [2_000_000.0] * 21
    change = shs.dollar_volume_change_pct(closes, volumes, window=21)
    assert change is not None and change > 90.0  # ~100% increase
    assert shs.dollar_volume_change_pct([1.0, 2.0], [1.0, 2.0], window=21) is None


# --------------------------------------------------------------------------------------
# Ranking -- RED-PROOFED (see report for the break/restore evidence)
# --------------------------------------------------------------------------------------

def test_leader_ranks_first_by_construction():
    """Three synthetic tickers vs a synthetic benchmark, built so the correct ranking is
    known in advance: LEAD's relative strength compounds up all 260 sessions, LAG's decays
    down all 260 sessions, NEU tracks the benchmark exactly (constant RS ratio). LEAD must
    rank #1 and be quadrant LEADING; LAG must rank last (#3) among the three."""
    n = 260
    bench_closes = [100.0 + i * 0.05 for i in range(n)]
    lead_closes = [50.0 * (1.004 ** i) for i in range(n)]   # RS climbs the whole series
    lag_closes = [80.0 * (0.997 ** i) for i in range(n)]    # RS falls the whole series
    neu_closes = [0.5 * c for c in bench_closes]            # RS ratio constant

    bench_bars = _bars("SPY", bench_closes, n)
    lead_bars = _bars("LEAD", lead_closes, n)
    lag_bars = _bars("LAG", lag_closes, n)
    neu_bars = _bars("NEU", neu_closes, n)

    raw_rows = [
        shs.compute_ticker_metrics("LEAD", "Leader", lead_bars, bench_bars, "test"),
        shs.compute_ticker_metrics("LAG", "Laggard", lag_bars, bench_bars, "test"),
        shs.compute_ticker_metrics("NEU", "Neutral", neu_bars, bench_bars, "test"),
    ]
    assert all(r["ok"] for r in raw_rows)  # sanity: synthetic data is complete enough

    ranked = shs.rank_universe(raw_rows)
    by_ticker = {r["ticker"]: r for r in ranked}

    assert by_ticker["LEAD"]["rank"] == 1
    assert by_ticker["LAG"]["rank"] == 3
    assert by_ticker["LEAD"]["heat_score"] > by_ticker["NEU"]["heat_score"] > by_ticker["LAG"]["heat_score"]
    assert by_ticker["LEAD"]["quadrant"] == "LEADING"
    assert by_ticker["LAG"]["quadrant"] == "LAGGING"


def test_rank_universe_empty_list_returns_empty():
    assert shs.rank_universe([]) == []


def test_rank_universe_failed_rows_pass_through_unscored():
    raw_rows = [{"ticker": "BAD", "name": "Bad", "ok": False, "reason": "no_bars"}]
    ranked = shs.rank_universe(raw_rows)
    assert len(ranked) == 1
    assert ranked[0]["ticker"] == "BAD"
    assert "heat_score" not in ranked[0]


# --------------------------------------------------------------------------------------
# Empty-input failure -- RED-PROOFED (see report for the break/restore evidence)
# --------------------------------------------------------------------------------------

def test_build_snapshot_raises_on_empty_result():
    """Zero scoreable rows must raise, never silently produce a zero-row 'successful'
    snapshot (LESSONS-LEARNED C7: silent success is failure)."""
    with pytest.raises(shs.SectorHeatEmptyResultError):
        shs.build_snapshot([], {}, as_of="2026-08-18", generated_at_et="2026-08-18T20:00:00")


def test_build_snapshot_raises_when_all_rows_failed():
    raw_rows = [{"ticker": "XLK", "name": "Tech", "ok": False, "reason": "both_sources_failed"}]
    ranked = shs.rank_universe(raw_rows)
    with pytest.raises(shs.SectorHeatEmptyResultError):
        shs.build_snapshot(ranked, {}, as_of="2026-08-18", generated_at_et="2026-08-18T20:00:00")


def test_build_snapshot_succeeds_with_at_least_one_scored_row():
    raw_rows = [{"ticker": "XLK", "name": "Tech", "ok": True, "as_of": "2026-08-18",
                 "data_source": "test", "rs_1m_z": 1.0, "rs_momentum_z": 0.5,
                 "ma_stack_z": 0.2, "dollar_volume_change_z": 0.1, "quadrant": "LEADING",
                 "heat_score": shs.composite_heat_score(1.0, 0.5, 0.2, 0.1), "rank": 1}]
    snap = shs.build_snapshot(raw_rows, {}, as_of="2026-08-18",
                               generated_at_et="2026-08-18T20:00:00")
    assert snap["as_of"] == "2026-08-18"
    assert snap["rows"][0]["ticker"] == "XLK"
    assert abs(sum(snap["composite_weights"].values()) - 1.0) < 1e-9


def test_write_snapshot_refuses_zero_scored_rows(tmp_path):
    bad_snapshot = {"as_of": "2026-08-18", "rows": [{"ticker": "XLK", "ok": False}]}
    with pytest.raises(shs.SectorHeatEmptyResultError):
        shs.write_snapshot(bad_snapshot, out_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []  # never partially wrote a file


def test_write_snapshot_writes_atomically(tmp_path):
    good_snapshot = {"as_of": "2026-08-18", "rows": [{"ticker": "XLK", "heat_score": 1.2}]}
    out_path = shs.write_snapshot(good_snapshot, out_dir=tmp_path)
    assert out_path.exists()
    assert out_path.name == "2026-08-18.json"
    assert not (tmp_path / "2026-08-18.json.tmp").exists()  # tmp file was replaced, not left


# --------------------------------------------------------------------------------------
# main() end-to-end on total fetch failure -- exit code + no file (extra safety net on
# top of the two RED-proofed unit tests above; monkeypatches the fetch layer, no network).
# --------------------------------------------------------------------------------------

def test_main_returns_nonzero_and_writes_no_file_on_total_fetch_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(shs, "OUT_DIR", tmp_path)
    monkeypatch.setattr(shs, "fetch_daily_bars",
                         lambda symbol, lookback_days, now_et=None: (None, "test_forced_failure"))
    rc = shs.main()
    assert rc != 0
    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------------------
# Hardcoded TOP_HOLDINGS sanity (catches data-entry mistakes in the quarterly constant)
# --------------------------------------------------------------------------------------

def test_top_holdings_covers_full_universe_with_sane_weights():
    for ticker in shs.UNIVERSE:
        assert ticker in shs.TOP_HOLDINGS, f"{ticker} missing from TOP_HOLDINGS"
        entry = shs.TOP_HOLDINGS[ticker]
        assert "as_of" in entry and entry["as_of"]
        holdings = entry["holdings"]
        assert len(holdings) >= 3
        for h in holdings:
            assert h["ticker"]
            assert h["name"]
            assert 0.0 < h["weight_pct"] <= 100.0


def test_build_constituent_rows_ranks_by_momentum():
    holdings = [
        {"ticker": "UP", "name": "Up Co", "weight_pct": 10.0},
        {"ticker": "DOWN", "name": "Down Co", "weight_pct": 8.0},
        {"ticker": "MISSING", "name": "No Data Co", "weight_pct": 5.0},
    ]
    n = 40
    up_bars = _bars("UP", [10.0 * (1.01 ** i) for i in range(n)], n)
    down_bars = _bars("DOWN", [10.0 * (0.99 ** i) for i in range(n)], n)
    bars_by_ticker = {
        "UP": (up_bars, "ok"),
        "DOWN": (down_bars, "ok"),
        "MISSING": (None, "both_sources_failed"),
    }
    rows = shs.build_constituent_rows(holdings, bars_by_ticker)
    by_ticker = {r["ticker"]: r for r in rows}
    assert by_ticker["UP"]["rank_in_sector"] == 1
    assert by_ticker["DOWN"]["rank_in_sector"] == 2
    assert by_ticker["MISSING"]["ok"] is False
    assert "rank_in_sector" not in by_ticker["MISSING"]
