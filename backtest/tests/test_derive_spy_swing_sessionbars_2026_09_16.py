"""Guards for `derive_spy_swing_sessionbars.py` — the DATA step of GOAL-GAMMA-STATION item (14)
"SPY swing lane by evidence" (order fixed: data -> prereg -> null -> shadow fork; never live).

Locks the load-bearing claims:
  1. OCC symbol parsing recovers root/expiry/side/strike exactly (a wrong expiry silently
     mislabels `is_expiry_day`, which every downstream exit-gate decision depends on).
  2. Daily aggregation is OHLCV-correct: open=first intraday bar, high=max, low=min,
     close=last intraday bar, volume=sum — a swapped open/close would invent a price path.
  3. `is_expiry_day` fires on exactly the session matching the parsed expiry, never off-by-one.
  4. The written CSV round-trips through `multiday_walk.load_contract_bars` unchanged — this
     is the actual consumer; a schema drift here would silently produce empty/wrong walks.
  5. A zero-row source file fails LOUD (DeriveError), never a silently-empty output.

Uses SYNTHETIC intraday CSVs in tmp_path — independent of whether the real options_3dte/4dte
cache exists on this box, so the suite is deterministic and portable.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_derive_spy_swing_sessionbars_2026_09_16.py -q
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

import pytest

_BT = Path(__file__).resolve().parents[1]
_REPO = _BT.parent
for p in (str(_BT), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from tools import derive_spy_swing_sessionbars as D  # noqa: E402

sys.path.insert(0, str(_BT / "lib"))
import multiday_walk as mw  # noqa: E402


def _write_intraday(path: Path, rows: list[tuple[str, float, float, float, float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp_et", "open", "high", "low", "close", "volume", "vwap", "trade_count"])
        for ts, o, h, l, c, v in rows:
            w.writerow([ts, o, h, l, c, v, (o + c) / 2, 1])


def test_parse_occ_recovers_root_expiry_side_strike():
    root, expiry, side, strike = D.parse_occ("SPY250107P00584000")
    assert root == "SPY"
    assert expiry == dt.date(2025, 1, 7)
    assert side == "P"
    assert strike == 584.0


def test_parse_occ_rejects_unparseable_stem():
    with pytest.raises(D.DeriveError):
        D.parse_occ("not_an_occ_symbol")


def test_aggregate_sessions_ohlcv_and_expiry_flag():
    rows = [
        ("2025-01-06T10:00:00-04:00", 1.0, 1.5, 0.8, 1.2, 100),
        ("2025-01-06T10:05:00-04:00", 1.2, 1.3, 1.1, 1.25, 50),
        ("2025-01-07T10:00:00-04:00", 0.5, 0.6, 0.1, 0.2, 500),
    ]
    loaded = []
    for ts, o, h, l, c, v in rows:
        loaded.append({
            "timestamp_et": ts, "_ts": dt.datetime.fromisoformat(ts),
            "open": o, "high": h, "low": l, "close": c, "volume": v,
            "vwap": (o + c) / 2, "trade_count": 1,
        })
    sessions = D.aggregate_sessions(loaded, expiry=dt.date(2025, 1, 7))
    assert len(sessions) == 2
    day1, day2 = sessions
    # Day 1: open=first bar's open, close=last bar's close, high/low across both bars
    assert day1["open"] == 1.0
    assert day1["close"] == 1.25
    assert day1["high"] == 1.5
    assert day1["low"] == 0.8
    assert day1["volume"] == 150.0
    assert day1["is_expiry_day"] == 0
    # Day 2 is the parsed expiry -> flagged
    assert day2["is_expiry_day"] == 1


def test_zero_row_source_fails_loud(tmp_path):
    path = tmp_path / "SPY250107P00584000.csv"
    _write_intraday(path, [])
    with pytest.raises(D.DeriveError):
        D.load_intraday(path)


def test_round_trips_through_multiday_walk_loader(tmp_path, monkeypatch):
    """The actual consumer: write via this tool, read via multiday_walk.load_contract_bars."""
    src = tmp_path / "src" / "SPY250107P00584000.csv"
    _write_intraday(src, [
        ("2025-01-06T10:00:00-04:00", 2.0, 2.5, 1.8, 2.2, 100),
        ("2025-01-07T10:00:00-04:00", 0.10, 0.20, 0.01, 0.02, 900),
    ])
    out_root = tmp_path / "out"
    monkeypatch.setattr(D, "OUT_ROOT", out_root)

    rows = D.load_intraday(src)
    root, expiry, side, strike = D.parse_occ(src.stem)
    sessions = D.aggregate_sessions(rows, expiry)
    D.write_session_csv(src.stem, root, expiry, strike, side, sessions)

    written = out_root / "SPY250107P00584000.csv"
    assert written.exists()

    bars = mw.load_contract_bars("SPY250107P00584000", out_root.name, data_root=out_root.parent)
    assert len(bars) == 2
    assert bars[0].date_et == dt.date(2025, 1, 6)
    assert bars[0].open == 2.0
    assert bars[1].is_expiry_day is True
    assert bars[1].close == 0.02
