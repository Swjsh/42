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


# ═══════════════ SSR-v1 ADDENDUM: h4_anchor='2000' grid (hand-derived) ══════
#
# Anchor grid [20,0,4,8,12,16] ET, per-trading-day block SEQUENCE (see
# levels.py module docstring's ADDENDUM section for why block identity must
# be a per-day sequence number, not a raw wall-clock floor-div -- a raw
# floor-div would collide day D's [18:00,20:00) bars with day D's own
# [16:00,17:00) bars 21+ hours apart, since both land in the SAME wall-clock
# 16:00-20:00 slot but on either side of the 17:00 trading-day roll):
#   block_seq 0        [18:00,20:00)  -- short LEADING block (2h)
#   block_seq 1..5     20-00/00-04/04-08/08-12/12-16 -- five full 4H blocks
#   block_seq 6        [16:00,17:00)  -- short TRAILING block (1h) --
#                       "last block 16:00-17:00 short then 17-18 halt" per
#                       the addendum's own wording.
# Two trading days, to also prove PREV_4H_HIGH/LOW carries the LAST
# COMPLETED block across the day boundary (day2's leading block references
# day1's trailing block6) -- exactly the same carry-over v0 already relies
# on for its own block5 -> next-day-block0 transition.
#
# One bar per hour, open==high==close (a single round number) so each
# block's high/open is read off by eye; low is a distinct hand-picked value
# per bar so min(low) isn't trivially "== high" (proves the low column is
# genuinely tracked, not accidentally always equal to high).
H4_ANCHOR_2000_ROWS = [
    # (timestamp, open=high=close, low)
    ("2026-06-01 18:00", 10, 0),    # 0  block_seq0 (leading) bar1
    ("2026-06-01 19:00", 12, -2),   # 1  block_seq0 bar2 -- block0 completes: H=12, L=-2
    ("2026-06-01 20:00", 20, 5),    # 2  block_seq1 (20-00) begins
    ("2026-06-01 21:00", 22, 3),    # 3
    ("2026-06-01 22:00", 18, 8),    # 4
    ("2026-06-01 23:00", 25, 2),    # 5  block1 completes: H=25, L=2
    ("2026-06-02 00:00", 30, 10),   # 6  block_seq2 (00-04) begins
    ("2026-06-02 01:00", 28, 12),   # 7
    ("2026-06-02 02:00", 35, 9),    # 8
    ("2026-06-02 03:00", 32, 15),   # 9  block2 completes: H=35, L=9
    ("2026-06-02 04:00", 40, 20),   # 10 block_seq3 (04-08) begins
    ("2026-06-02 05:00", 42, 18),   # 11
    ("2026-06-02 06:00", 38, 22),   # 12
    ("2026-06-02 07:00", 45, 19),   # 13 block3 completes: H=45, L=18
    ("2026-06-02 08:00", 50, 30),   # 14 block_seq4 (08-12) begins
    ("2026-06-02 09:00", 52, 28),   # 15
    ("2026-06-02 10:00", 48, 32),   # 16
    ("2026-06-02 11:00", 55, 29),   # 17 block4 completes: H=55, L=28
    ("2026-06-02 12:00", 60, 40),   # 18 block_seq5 (12-16) begins
    ("2026-06-02 13:00", 62, 38),   # 19
    ("2026-06-02 14:00", 58, 42),   # 20
    ("2026-06-02 15:00", 65, 39),   # 21 block5 completes: H=65, L=38
    ("2026-06-02 16:00", 70, 50),   # 22 block_seq6 (TRAILING, ONLY this bar -- day rolls 17:00): H=70, L=50
    ("2026-06-02 18:00", 80, 60),   # 23 trading day 2 -- block_seq0 again (leading [18:00,20:00))
    ("2026-06-02 19:00", 82, 58),   # 24 block0(day2) completes: H=82, L=58
    ("2026-06-02 20:00", 90, 65),   # 25 block_seq1(day2) begins
]

# (prev_4h_high, prev_4h_low, h4_open) per row -- derived by eye from the
# tiny (1-, 2-, or 4-element) high/low lists per block above; cross-checked
# against build_levels(h4_anchor='2000') while writing this fixture (same
# discipline TestHandComputedFixture's own header describes).
H4_ANCHOR_2000_EXPECTED = [
    (None, None, 10),  (None, None, 10),                                 # 0,1  block0 in progress
    (12, -2, 20), (12, -2, 20), (12, -2, 20), (12, -2, 20),               # 2-5  block1 in progress
    (25, 2, 30), (25, 2, 30), (25, 2, 30), (25, 2, 30),                   # 6-9  block2 in progress
    (35, 9, 40), (35, 9, 40), (35, 9, 40), (35, 9, 40),                   # 10-13 block3 in progress
    (45, 18, 50), (45, 18, 50), (45, 18, 50), (45, 18, 50),               # 14-17 block4 in progress
    (55, 28, 60), (55, 28, 60), (55, 28, 60), (55, 28, 60),               # 18-21 block5 in progress
    (65, 38, 70),                                                        # 22   block6 (trailing) in progress
    (70, 50, 80), (70, 50, 80),                                          # 23,24 block0(day2) in progress
    (82, 58, 90),                                                        # 25   block1(day2) begins
]


class TestH4Anchor2000Grid:
    def test_block_seq_boundaries_hand_derived(self):
        """Lock in the block-SEQUENCE definition itself (not just the
        downstream PREV_4H values below) at the exact wall-clock boundaries
        named in the addendum, using first_boundary_offset_min=120 (20:00 is
        120 minutes after the 18:00 day start) -- the same arithmetic
        `build_levels(h4_anchor='2000')` uses internally."""
        ET_ = ET
        day = pd.Timestamp("2026-06-01", tz=ET_)
        cases = [
            ("2026-06-01 18:00", 0), ("2026-06-01 19:59", 0),   # leading block
            ("2026-06-01 20:00", 1), ("2026-06-01 23:59", 1),   # block1
            ("2026-06-02 00:00", 2), ("2026-06-02 03:59", 2),   # block2
            ("2026-06-02 04:00", 3), ("2026-06-02 07:59", 3),   # block3
            ("2026-06-02 08:00", 4), ("2026-06-02 11:59", 4),   # block4
            ("2026-06-02 12:00", 5), ("2026-06-02 15:59", 5),   # block5
            ("2026-06-02 16:00", 6), ("2026-06-02 16:59", 6),   # trailing block
        ]
        for ts_str, expected_seq in cases:
            ts = pd.Timestamp(ts_str, tz=ET_)
            assert levels._h4_block_seq(ts, 120) == expected_seq, (
                f"{ts_str}: expected block_seq {expected_seq}"
            )
        del day  # unused, kept for readability of the case list's intent

    def test_h4_anchor_2000_default_offset_reduces_to_v0(self):
        """first_boundary_offset_min=0 (h4_anchor='1800') must reduce to
        EXACTLY `block_index`'s own m // BLOCK_MINUTES -- the invariant that
        makes h4_anchor='1800' byte-identical to pre-addendum behavior."""
        for ts_str in ("2026-06-01 18:00", "2026-06-02 13:37", "2026-06-02 16:59"):
            ts = pd.Timestamp(ts_str, tz=ET)
            assert levels._h4_block_seq(ts, 0) == levels.block_index(ts)

    def test_prev_4h_and_h4_open_hand_derived(self):
        bars = _bars_df([
            _bar(ts, o, o, l, o) for ts, o, l in H4_ANCHOR_2000_ROWS
        ])
        snaps = levels.build_levels(bars, h4_anchor="2000")
        assert len(snaps) == len(H4_ANCHOR_2000_ROWS) == 26

        for i, (snap, (exp_h, exp_l, exp_open)) in enumerate(zip(snaps, H4_ANCHOR_2000_EXPECTED)):
            assert snap.prev_4h_high == (None if exp_h is None else float(exp_h)), f"row {i} prev_4h_high"
            assert snap.prev_4h_low == (None if exp_l is None else float(exp_l)), f"row {i} prev_4h_low"
            assert snap.h4_open == float(exp_open), f"row {i} h4_open"

    def test_v0_default_unaffected_by_the_new_anchor_code_path(self):
        """Same bars, h4_anchor left at its v0 default -- PREV_4H/H4_OPEN
        must come out completely differently (anchored 18:00, not 20:00),
        proving the anchor grid actually branches rather than being a dead
        parameter."""
        bars = _bars_df([
            _bar(ts, o, o, l, o) for ts, o, l in H4_ANCHOR_2000_ROWS
        ])
        default_snaps = levels.build_levels(bars)
        anchor2000_snaps = levels.build_levels(bars, h4_anchor="2000")
        assert [s.prev_4h_high for s in default_snaps] != [s.prev_4h_high for s in anchor2000_snaps]

    def test_unsupported_anchor_raises(self):
        bars = _bars_df([_bar("2026-06-01 18:00", 1, 1, 1, 1)])
        with pytest.raises(ValueError):
            levels.build_levels(bars, h4_anchor="1900")


# ═══════════════ SSR-v1 ADDENDUM: include_running=True (hand-derived) ═══════
#
# Global bar index k (0-based across the WHOLE fixture, spanning both
# trading days): high[k] = k, low[k] = -k -- strictly monotonic, so any
# running window's max is always its LAST element and its min is always its
# last element too (min(low) over ANY suffix window ending at k-1, since
# low keeps getting MORE negative as k grows, is achieved at k-1 itself,
# regardless of the window's start) -- collapsing every "running max/min
# over [window_start, k-1]" to the trivial closed form (k-1, -(k-1)) once
# that window's own >= 8-bars gate is satisfied. This makes hand-derivation
# of the expected table below arithmetic, not a re-derivation via the code
# under test (same discipline as TestHandComputedFixture's own header) --
# the INTERESTING part this fixture proves is the GATING (None until >=8
# bars; a session-scoped RUN_* field going back to None the instant that
# session ends, even while RUN_DAY_* keeps updating; both resetting to None
# at the next trading day's start and re-gating independently with fresh
# values) -- not the arithmetic.
#
# Day 1 (2026-06-01 18:00 -> 2026-06-02 17:00): 10 Asia bars (30min apart,
# k=0..9), 10 London bars (k=10..19), 10 NY bars (k=20..29).
# Day 2: 10 more Asia bars, offset +200 (k'=0..9, high=200+k', low=-200-k')
# so day2's values are trivially distinguishable from day1's leftovers.
def _run_fixture_rows() -> list[tuple[pd.Timestamp, float, float]]:
    rows: list[tuple[pd.Timestamp, float, float]] = []

    def _block(start_ts: pd.Timestamp, ks: range, offset: int = 0):
        t = start_ts
        for k in ks:
            rows.append((t, float(offset + k), float(-offset - k)))
            t += pd.Timedelta(minutes=30)

    _block(pd.Timestamp("2026-06-01 18:00", tz=ET), range(0, 10))            # Asia   k=0..9
    _block(pd.Timestamp("2026-06-02 03:00", tz=ET), range(10, 20))           # London k=10..19
    _block(pd.Timestamp("2026-06-02 09:30", tz=ET), range(20, 30))           # NY     k=20..29
    _block(pd.Timestamp("2026-06-02 18:00", tz=ET), range(0, 10), offset=200)  # Day2 Asia, offset +200
    return rows


# Per-row expected (run_day_high, run_day_low, run_asia_high, run_asia_low,
# run_london_high, run_london_low, run_ny_high, run_ny_low) -- None until
# each field's own >=8-bar gate; session fields additionally None whenever
# the CURRENT bar's own session differs from that field's name.
_N = (None, None, None, None, None, None, None, None)
RUN_FIXTURE_EXPECTED = [
    # day1 Asia (rows 0-9): rows 0-7 ungated (day_bar_count < 8); rows 8-9
    # gated -- day and asia coincide (asia IS the day's first session), so
    # both read (k-1, -(k-1)) identically.
    _N, _N, _N, _N, _N, _N, _N, _N,                       # 0-7
    (7, -7, 7, -7, None, None, None, None),               # 8  day+asia gate met (day_bar_count==8)
    (8, -8, 8, -8, None, None, None, None),                # 9
    # day1 London (rows 10-19, k=10..19): day CONTINUES updating every bar
    # (already gated); asia goes back to None THIS SAME BAR the session
    # changes (session != asia) even though day doesn't reset; london starts
    # its own fresh ungated count (session_bar_count 0..7 -> None) until its
    # own gate at row18.
    (9, -9, None, None, None, None, None, None),           # 10 (session flips to london here)
    (10, -10, None, None, None, None, None, None),         # 11
    (11, -11, None, None, None, None, None, None),         # 12
    (12, -12, None, None, None, None, None, None),         # 13
    (13, -13, None, None, None, None, None, None),         # 14
    (14, -14, None, None, None, None, None, None),         # 15
    (15, -15, None, None, None, None, None, None),         # 16
    (16, -16, None, None, None, None, None, None),         # 17
    (17, -17, None, None, 17, -17, None, None),             # 18  london gate met (session_bar_count==8)
    (18, -18, None, None, 18, -18, None, None),             # 19
    # day1 NY (rows 20-29, k=20..29): london -> None, ny fresh ungated until
    # its own gate at row28.
    (19, -19, None, None, None, None, None, None),         # 20 (session flips to ny here)
    (20, -20, None, None, None, None, None, None),         # 21
    (21, -21, None, None, None, None, None, None),         # 22
    (22, -22, None, None, None, None, None, None),         # 23
    (23, -23, None, None, None, None, None, None),         # 24
    (24, -24, None, None, None, None, None, None),         # 25
    (25, -25, None, None, None, None, None, None),         # 26
    (26, -26, None, None, None, None, None, None),         # 27
    (27, -27, None, None, None, None, 27, -27),             # 28  ny gate met (session_bar_count==8)
    (28, -28, None, None, None, None, 28, -28),             # 29
    # day2 begins (rows 30-39, k'=0..9, offset +200): EVERYTHING resets to
    # None -- day rolled over, so run_day AND run_ny (the session active at
    # day1's close) both re-require their own fresh 8-bar gate. Rows 30-37
    # ungated; rows 38-39 gated with the OFFSET +200 values, proving day2's
    # running extremes are computed from day2's own bars only (no leftover
    # from day1's k=0..29 range, which would show up as un-offset ~20-29
    # values instead of the +200-offset ~207-208 seen here).
    _N, _N, _N, _N, _N, _N, _N, _N,                        # 30-37
    (207, -207, 207, -207, None, None, None, None),         # 38  day+asia gate met, day2 offset values
    (208, -208, 208, -208, None, None, None, None),         # 39
]

RUN_FIELD_NAMES = (
    "run_day_high", "run_day_low", "run_asia_high", "run_asia_low",
    "run_london_high", "run_london_low", "run_ny_high", "run_ny_low",
)


def _run_fixture_bars() -> pd.DataFrame:
    # NOTE: _run_fixture_rows() already produces tz-aware timestamps (built
    # via pd.Timestamp(..., tz=ET) directly, since they're generated
    # programmatically at 30-minute steps rather than hand-listed strings)
    # -- so this bypasses the module's `_bar` helper (which expects a naive
    # string and tz_localizes it) and builds rows directly instead.
    return _bars_df([
        {"timestamp_et": ts, "open": h + 0.5, "high": h, "low": l,
         "close": (h + l) / 2, "volume": 100.0}
        for ts, h, l in _run_fixture_rows()
    ])


class TestRunningExtremeFixture:
    def test_every_run_field_at_every_bar_across_session_transitions(self):
        bars = _run_fixture_bars()
        assert len(bars) == 40
        snapshots = levels.build_levels(bars, include_running=True)
        assert len(snapshots) == 40

        for i, (snap, expected_row) in enumerate(zip(snapshots, RUN_FIXTURE_EXPECTED)):
            for field, expected_val in zip(RUN_FIELD_NAMES, expected_row):
                actual_val = getattr(snap, field)
                exp = None if expected_val is None else float(expected_val)
                assert actual_val == exp, f"bar {i} field {field}: expected {exp!r}, got {actual_val!r}"

    def test_include_running_false_never_populates_run_fields(self):
        """The include_running=False default (v0 behavior) must leave every
        RUN_* field None throughout, even on a fixture explicitly built to
        satisfy every gate -- backward compat is opt-in, not automatic."""
        bars = _run_fixture_bars()
        snapshots = levels.build_levels(bars)  # include_running defaults False
        for i, snap in enumerate(snapshots):
            for field in RUN_FIELD_NAMES:
                assert getattr(snap, field) is None, f"bar {i} field {field} should stay None"

    def test_run_names_only_in_sweepable_helpers_when_non_none(self):
        bars = _run_fixture_bars()
        snapshots = levels.build_levels(bars, include_running=True)

        # bar 0: nothing gated yet -- no RUN_* names anywhere.
        highs0 = dict(snapshots[0].sweepable_highs())
        assert not any(name.startswith("RUN_") for name in highs0)

        # bar 8: RUN_DAY_HIGH + RUN_ASIA_HIGH present (gated), no london/ny.
        highs8 = dict(snapshots[8].sweepable_highs())
        lows8 = dict(snapshots[8].sweepable_lows())
        assert highs8["RUN_DAY_HIGH"] == 7.0 and lows8["RUN_DAY_LOW"] == -7.0
        assert highs8["RUN_ASIA_HIGH"] == 7.0 and lows8["RUN_ASIA_LOW"] == -7.0
        assert "RUN_LONDON_HIGH" not in highs8 and "RUN_NY_HIGH" not in highs8

        # bar 18: RUN_LONDON present, RUN_ASIA has dropped out entirely.
        highs18 = dict(snapshots[18].sweepable_highs())
        assert "RUN_ASIA_HIGH" not in highs18
        assert highs18["RUN_LONDON_HIGH"] == 17.0
        assert highs18["RUN_DAY_HIGH"] == 17.0

        all18 = dict(snapshots[18].all_levels())
        assert all18["RUN_LONDON_HIGH"] == 17.0  # all_levels() folds RUN_* in too


# ═══════ SSR-v1 ADDENDUM: causality mutation test specific to RUN_* fields ══

class TestRunningExtremeCausalityMutation:
    """Same invariant as TestCausalityMutation above (mutating bars strictly
    after index k never changes snapshots[0..k]), run specifically against
    the include_running=True fixture and specifically at the RUN_* fields --
    including right at their >=8-bar gate boundaries and session-transition
    edges, where a running-extreme implementation is most likely to
    accidentally peek at bar i's own high/low instead of stopping at i-1."""

    @pytest.mark.parametrize("k", [0, 6, 7, 8, 9, 17, 18, 19, 27, 28, 37, 38])
    def test_mutating_bars_after_k_never_changes_run_fields_0_to_k(self, k):
        bars = _run_fixture_bars()
        baseline = levels.build_levels(bars, include_running=True)

        mutated = bars.copy(deep=True)
        after_mask = mutated.index > k
        for col in ("open", "high", "low", "close"):
            mutated.loc[after_mask, col] = mutated.loc[after_mask, col] + 1000.0
        rebuilt = levels.build_levels(mutated, include_running=True)

        for i in range(k + 1):
            for field in RUN_FIELD_NAMES:
                b, r = getattr(baseline[i], field), getattr(rebuilt[i], field)
                assert b == r, (
                    f"mutating bars strictly after index {k} changed {field} at bar {i} "
                    f"(baseline={b!r}, rebuilt={r!r}) -- look-ahead leak in a RUN_* field"
                )

    def test_mutation_actually_changes_a_run_field_after_k(self):
        # Sanity check the +1000 mutation is load-bearing for RUN_* fields
        # specifically (not just a vacuous pass because nothing downstream
        # of k=8 ever differs). Row 9 itself must stay UNCHANGED (its own
        # run_day_high reads bars[0..8], none of which are mutated by
        # `index > 8`) -- it's row 10 (reads bars[0..9], and bar 9 IS
        # mutated) where the mutation must first become visible.
        bars = _run_fixture_bars()
        baseline = levels.build_levels(bars, include_running=True)
        mutated = bars.copy(deep=True)
        mutated.loc[mutated.index > 8, ["open", "high", "low", "close"]] += 1000.0
        rebuilt = levels.build_levels(mutated, include_running=True)
        assert baseline[9].run_day_high == rebuilt[9].run_day_high, (
            "bar 9's run_day_high must NOT see bar 9's own (mutated) high -- C6 same-bar leak"
        )
        assert baseline[10].run_day_high != rebuilt[10].run_day_high, (
            "the +1000 mutation on bar 9 must be visible in bar 10's run_day_high, or this "
            "regression guard is vacuous"
        )

