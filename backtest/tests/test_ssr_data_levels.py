"""Guards for backtest/futures/ssr/{data_fetch,levels}.py -- SSR battery
Builder 1 (data + levels).

Covers, per the builder contract:
  (1) the frozen session/day/week/4H-block level definitions on a fully
      hand-computed synthetic fixture -- exact assertion of every
      LevelSnapshot field at every bar.
  (2) the CAUSALITY MUTATION TEST: mutating bars strictly after index k never
      changes snapshots[0..k].
  (3) the CSV cache round trip preserves tz-aware America/New_York dtype.
  (4) empty-input raises RuntimeError, on both fetch_bars and build_levels.
Plus (bonus, still contract-scoped): sweepable_highs/sweepable_lows/
all_levels(), a fresh yfinance fetch through MultiIndex-column + duplicate +
out-of-order raw data (normalize/dedup/ascending-sort + provenance line).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yfinance as yf

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from futures.ssr import data_fetch, levels  # noqa: E402

ET = "America/New_York"


def _bar(ts_str: str, o: float, h: float, l: float, c: float, v: float = 100.0) -> dict:
    ts = pd.Timestamp(ts_str).tz_localize(ET)
    return {"timestamp_et": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _bars_df(bar_dicts: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(bar_dicts).reset_index(drop=True)


# ══════════════════════════ (1) hand-computed fixture ═══════════════════════
#
# Definitions under test (SSR-battery/DESIGN.md section 3): trading day
# 18:00 ET (D-1) -> 17:00 ET (D); sessions Asia 18:00-03:00, London
# 03:00-09:30, New York 09:30-17:00; 4H blocks anchored 18:00 ET
# (18/22/02/06/10/14, last block 3h).
#
#   Trading day A: 2026-06-01 18:00 -> 2026-06-02 17:00 ET  (ISO week 23)
#   Trading day B: 2026-06-02 18:00 -> 2026-06-03 17:00 ET  (ISO week 23, same
#                  ISO week as A -- 2026-06-02/03 are Tue/Wed of week 23)
#   Trading day C: 2026-06-07 18:00 -> 2026-06-08 17:00 ET  (ISO week 24 --
#                  2026-06-08 is a Monday, verified via date.isocalendar())
#
# Every expected value below was derived BY HAND by walking these 15 bars in
# chronological order and tracking, independently per period type (day, ISO
# week, 4H block, each of the 3 named sessions), which bars fall in which
# period instance and what that instance's completed high/low become once
# the NEXT bar starts a different instance. See the field-by-field derivation
# in the SSR Builder-1 session notes; the table below is the result, not a
# re-derivation via the code under test.
FIXTURE_BARS = _bars_df([
    _bar("2026-06-01 18:00", 100, 105, 95,  102),   # b1  dayA block0 asia
    _bar("2026-06-01 19:00", 101, 108, 96,  103),   # b2  dayA block0 asia
    _bar("2026-06-01 23:00", 102, 110, 90,  105),   # b3  dayA block1 asia
    _bar("2026-06-02 02:00", 103, 107, 85,  100),   # b4  dayA block2 asia
    _bar("2026-06-02 03:30", 115, 120, 114, 118),   # b5  dayA block2 london
    _bar("2026-06-02 07:00", 118, 125, 112, 120),   # b6  dayA block3 london
    _bar("2026-06-02 11:00", 130, 135, 128, 132),   # b7  dayA block4 ny
    _bar("2026-06-02 15:00", 132, 140, 126, 135),   # b8  dayA block5 ny
    _bar("2026-06-02 18:00", 150, 155, 148, 152),   # b9  dayB block0 asia
    _bar("2026-06-02 20:00", 152, 160, 150, 155),   # b10 dayB block0 asia
    _bar("2026-06-03 04:00", 161, 165, 158, 162),   # b11 dayB block2 london
    _bar("2026-06-03 10:00", 170, 175, 168, 172),   # b12 dayB block4 ny
    _bar("2026-06-03 16:00", 180, 185, 178, 182),   # b13 dayB block5 ny
    _bar("2026-06-07 18:00", 200, 205, 198, 202),   # b14 dayC block0 asia
    _bar("2026-06-08 02:00", 210, 215, 208, 212),   # b15 dayC block2 asia
])

# Columns: prev_day(H,L), prev_week(H,L), prev_4h(H,L), asia(H,L),
#          london(H,L), ny(H,L), day_open, h4_open
EXPECTED_FIELDS = [
    (None, None,  None, None,  None, None,  None, None,  None, None,  None, None,  100, 100),  # b1
    (None, None,  None, None,  None, None,  None, None,  None, None,  None, None,  100, 100),  # b2
    (None, None,  None, None,  108, 95,     None, None,  None, None,  None, None,  100, 102),  # b3
    (None, None,  None, None,  110, 90,     None, None,  None, None,  None, None,  100, 103),  # b4
    (None, None,  None, None,  110, 90,     110, 85,     None, None,  None, None,  100, 103),  # b5
    (None, None,  None, None,  120, 85,     110, 85,     None, None,  None, None,  100, 118),  # b6
    (None, None,  None, None,  125, 112,    110, 85,     125, 112,    None, None,  100, 130),  # b7
    (None, None,  None, None,  135, 128,    110, 85,     125, 112,    None, None,  100, 132),  # b8
    (140, 85,     None, None,  140, 126,    110, 85,     125, 112,    140, 126,    150, 150),  # b9
    (140, 85,     None, None,  140, 126,    110, 85,     125, 112,    140, 126,    150, 150),  # b10
    (140, 85,     None, None,  160, 148,    160, 148,    125, 112,    140, 126,    150, 161),  # b11
    (140, 85,     None, None,  165, 158,    160, 148,    165, 158,    140, 126,    150, 170),  # b12
    (140, 85,     None, None,  175, 168,    160, 148,    165, 158,    140, 126,    150, 180),  # b13
    (185, 148,    185, 85,    185, 178,    160, 148,    165, 158,    185, 168,    200, 200),  # b14
    (185, 148,    185, 85,    205, 198,    160, 148,    165, 158,    185, 168,    200, 210),  # b15
]

FIELD_NAMES = [
    "prev_day_high", "prev_day_low", "prev_week_high", "prev_week_low",
    "prev_4h_high", "prev_4h_low", "asia_high", "asia_low",
    "london_high", "london_low", "ny_high", "ny_low", "day_open", "h4_open",
]


class TestHandComputedFixture:
    def test_iso_week_assumption_holds(self):
        # Ground the fixture's own claim about which calendar dates share an
        # ISO week, so a future stdlib/behavior change can't silently
        # invalidate the hand-derived table above without failing loudly.
        assert dt.date(2026, 6, 2).isocalendar()[1] == 23
        assert dt.date(2026, 6, 3).isocalendar()[1] == 23
        assert dt.date(2026, 6, 8).isocalendar()[1] == 24

    def test_every_field_at_every_bar(self):
        snapshots = levels.build_levels(FIXTURE_BARS)
        assert len(snapshots) == len(FIXTURE_BARS) == 15
        for i, (snap, expected_row) in enumerate(zip(snapshots, EXPECTED_FIELDS)):
            assert snap is not None, f"bar {i}: expected a LevelSnapshot, got None"
            for field, expected_val in zip(FIELD_NAMES, expected_row):
                actual_val = getattr(snap, field)
                exp = None if expected_val is None else float(expected_val)
                assert actual_val == exp, (
                    f"bar {i} field {field}: expected {exp!r}, got {actual_val!r}"
                )

    def test_sweepable_and_all_levels_helpers(self):
        snapshots = levels.build_levels(FIXTURE_BARS)
        snap15 = snapshots[-1]  # fully populated (see EXPECTED_FIELDS row for b15)

        highs = dict(snap15.sweepable_highs())
        assert highs == {
            "PDH": 185.0, "PWH": 185.0, "PREV_4H_HIGH": 205.0,
            "ASIA_HIGH": 160.0, "LONDON_HIGH": 165.0, "NY_HIGH": 185.0,
        }
        lows = dict(snap15.sweepable_lows())
        assert lows == {
            "PDL": 148.0, "PWL": 85.0, "PREV_4H_LOW": 198.0,
            "ASIA_LOW": 148.0, "LONDON_LOW": 158.0, "NY_LOW": 168.0,
        }
        all_lv = dict(snap15.all_levels())
        assert all_lv == {**highs, **lows, "DAY_OPEN": 200.0, "H4_OPEN": 210.0}

        # b1: nothing completed yet -- both sweep lists empty, all_levels has
        # only the two (always-known) opens.
        snap1 = snapshots[0]
        assert snap1.sweepable_highs() == []
        assert snap1.sweepable_lows() == []
        assert snap1.all_levels() == [("DAY_OPEN", 100.0), ("H4_OPEN", 100.0)]


# ══════════════════════════ (2) causality mutation test ═════════════════════

class TestCausalityMutation:
    @pytest.mark.parametrize("k", [0, 3, 7, 10, 13])
    def test_mutating_bars_after_k_never_changes_snapshots_0_to_k(self, k):
        baseline = levels.build_levels(FIXTURE_BARS)

        mutated = FIXTURE_BARS.copy(deep=True)
        after_mask = mutated.index > k
        for col in ("open", "high", "low", "close"):
            mutated.loc[after_mask, col] = mutated.loc[after_mask, col] + 50.0

        rebuilt = levels.build_levels(mutated)

        assert rebuilt[: k + 1] == baseline[: k + 1], (
            f"mutating bars strictly after index {k} changed a snapshot at "
            f"or before index {k} -- look-ahead leak"
        )

    def test_mutation_actually_changes_something_after_k(self):
        # Sanity check that the +50 mutation is load-bearing: a no-op mutator
        # would make the test above vacuously true.
        baseline = levels.build_levels(FIXTURE_BARS)
        mutated = FIXTURE_BARS.copy(deep=True)
        mutated.loc[mutated.index > 7, ["open", "high", "low", "close"]] += 50.0
        rebuilt = levels.build_levels(mutated)
        assert rebuilt[8:] != baseline[8:]


# ══════════════════════════ (3) cache round trip ═════════════════════════════

class TestCacheRoundTrip:
    def test_cache_round_trip_preserves_tz_aware_et(self, monkeypatch, tmp_path):
        monkeypatch.setattr(data_fetch, "DATA_DIR", tmp_path)

        seed_bars = _bars_df([
            _bar("2026-06-01 09:30", 500.0, 501.5, 499.0, 500.8, 1000),
            _bar("2026-06-01 09:45", 500.8, 502.0, 500.2, 501.9, 1100),
            _bar("2026-06-01 10:00", 501.9, 503.0, 501.5, 502.4, 900),
        ])
        cache_path = data_fetch._cache_path("GC=F", "15m")
        tmp_path.mkdir(parents=True, exist_ok=True)
        seed_bars.to_csv(cache_path, index=False)

        loaded = data_fetch.fetch_bars("GC=F", "15m", "60d")  # refresh=False -> cache hit

        assert isinstance(loaded["timestamp_et"].dtype, pd.DatetimeTZDtype)
        assert str(loaded["timestamp_et"].dt.tz) == ET
        assert list(loaded["open"]) == list(seed_bars["open"])
        assert list(loaded["timestamp_et"]) == list(seed_bars["timestamp_et"])
        assert list(loaded.columns) == data_fetch.BAR_COLUMNS

    def test_refresh_true_bypasses_cache(self, monkeypatch, tmp_path):
        monkeypatch.setattr(data_fetch, "DATA_DIR", tmp_path)
        cache_path = data_fetch._cache_path("NQ=F", "15m")
        tmp_path.mkdir(parents=True, exist_ok=True)
        _bars_df([_bar("2026-06-01 09:30", 1.0, 1.0, 1.0, 1.0)]).to_csv(cache_path, index=False)

        fresh_raw = _fake_yfinance_raw([
            ("2026-06-02 09:30", 20000.0, 20010.0, 19995.0, 20005.0, 500),
        ])
        monkeypatch.setattr(yf, "download", lambda *a, **kw: fresh_raw)

        out = data_fetch.fetch_bars("NQ=F", "15m", "60d", refresh=True)
        assert len(out) == 1
        assert float(out["open"].iloc[0]) == 20000.0  # proves it re-fetched, not the stale cache


# ══════════════════════════ (4) empty-input raises ═══════════════════════════

class TestEmptyInputRaises:
    def test_build_levels_raises_on_empty_dataframe(self):
        empty = pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close", "volume"])
        with pytest.raises(RuntimeError):
            levels.build_levels(empty)

    def test_build_levels_raises_on_none(self):
        with pytest.raises(RuntimeError):
            levels.build_levels(None)

    def test_fetch_bars_raises_on_empty_yfinance_response(self, monkeypatch, tmp_path):
        monkeypatch.setattr(data_fetch, "DATA_DIR", tmp_path)
        monkeypatch.setattr(yf, "download", lambda *a, **kw: pd.DataFrame())
        with pytest.raises(RuntimeError):
            data_fetch.fetch_bars("ES=F", "15m", "60d")

    def test_fetch_bars_raises_on_empty_cache_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(data_fetch, "DATA_DIR", tmp_path)
        cache_path = data_fetch._cache_path("ES=F", "15m")
        tmp_path.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=data_fetch.BAR_COLUMNS).to_csv(cache_path, index=False)
        with pytest.raises(RuntimeError):
            data_fetch.fetch_bars("ES=F", "15m", "60d")


# ══════════════════════════ bonus: fresh fetch normalize/provenance ═════════

def _fake_yfinance_raw(rows: list[tuple]) -> pd.DataFrame:
    """MultiIndex-column raw frame shaped like a real yfinance single-symbol
    download (columns = (field, ticker), tz-naive UTC "Datetime" index) --
    exercises the MultiIndex-flatten branch of _normalize_fetch."""
    idx = pd.DatetimeIndex([pd.Timestamp(r[0], tz="UTC") for r in rows], name="Datetime")
    fields = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    cols = pd.MultiIndex.from_product([fields, ["GC=F"]])
    data = {
        ("Open", "GC=F"): [r[1] for r in rows],
        ("High", "GC=F"): [r[2] for r in rows],
        ("Low", "GC=F"): [r[3] for r in rows],
        ("Close", "GC=F"): [r[4] for r in rows],
        ("Adj Close", "GC=F"): [r[4] for r in rows],
        ("Volume", "GC=F"): [r[5] for r in rows],
    }
    return pd.DataFrame(data, index=idx, columns=cols)


class TestFreshFetchNormalization:
    def test_multiindex_dedup_ascending_and_provenance(self, monkeypatch, tmp_path):
        monkeypatch.setattr(data_fetch, "DATA_DIR", tmp_path)

        # Deliberately out of order, with a duplicate timestamp (09:30 twice,
        # different values -- keep='first' in ORIGINAL row order must win).
        raw = _fake_yfinance_raw([
            ("2026-06-01 13:35", 10.0, 10.5, 9.8, 10.2, 100),   # -> 09:35 ET
            ("2026-06-01 13:30", 9.0, 9.5, 8.8, 9.2, 90),       # -> 09:30 ET (kept)
            ("2026-06-01 13:30", 9.9, 9.95, 8.85, 9.25, 95),    # -> 09:30 ET (dup, dropped)
            ("2026-06-01 13:40", 11.0, 11.5, 10.8, 11.2, 110),  # -> 09:40 ET
        ])
        monkeypatch.setattr(yf, "download", lambda *a, **kw: raw)

        out = data_fetch.fetch_bars("GC=F", "15m", "60d")

        assert list(out.columns) == data_fetch.BAR_COLUMNS
        assert len(out) == 3  # 4 raw rows, 1 duplicate timestamp dropped
        assert out["timestamp_et"].is_monotonic_increasing
        assert float(out["open"].iloc[0]) == 9.0  # first-occurrence dedup winner, not 9.9
        assert isinstance(out["timestamp_et"].dtype, pd.DatetimeTZDtype)
        assert str(out["timestamp_et"].dt.tz) == ET

        cache_path = data_fetch._cache_path("GC=F", "15m")
        assert cache_path.exists()

        prov_path = data_fetch._provenance_path()
        assert prov_path.exists()
        lines = prov_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["symbol"] == "GC=F"
        assert record["interval"] == "15m"
        assert record["period"] == "60d"
        assert record["rows"] == 3
        assert record["source"] == "yfinance"
        assert "first_ts" in record and "last_ts" in record and "ts_et" in record

    def test_cache_filename_sanitized(self, monkeypatch, tmp_path):
        monkeypatch.setattr(data_fetch, "DATA_DIR", tmp_path)
        assert data_fetch._cache_path("GC=F", "15m").name == "GC_F_15m.csv"
        assert data_fetch._cache_path("^VIX", "15m").name == "_VIX_15m.csv"
