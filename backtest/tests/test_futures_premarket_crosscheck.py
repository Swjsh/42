"""Guards for backtest/futures/futures_premarket_crosscheck.py -- the read-only premarket
vs internal level cross-check (queue.md FUTURES-LANE-WIRING-2 (c) / FUTURES-PREMARKET-
LEVELS-CONSUMER, DECIDED "cross-check only").

Covers: no-op when the premarket file/instrument is missing (never fabricates), idempotent
per session (one row/day even across many calls), the row shape and matched/unmatched math,
and that nothing here raises on a corrupt or absent input.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import futures.futures_premarket_crosscheck as fpc  # noqa: E402


def _bars(prices: list[float], start: str = "2026-09-02T09:30:00-04:00") -> pd.DataFrame:
    ts = pd.date_range(start=start, periods=len(prices), freq="5min")
    rows = []
    for t, p in zip(ts, prices):
        rows.append({"timestamp_et": t, "open": p, "high": p + 0.5, "low": p - 0.5,
                    "close": p, "volume": 100})
    return pd.DataFrame(rows)


def _write_key_levels(path: Path, symbol: str, levels: list[dict], *, status: str = "OK",
                      for_session: str = "2026-09-03") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": 1,
        "for_session": for_session,
        "instruments": {
            symbol: {"instrument": symbol, "status": status, "for_session": for_session,
                     "levels": levels},
        },
    }
    path.write_text(json.dumps(doc), encoding="utf-8")


NOW_ET = dt.datetime(2026, 9, 3, 10, 0, 0)  # naive, matches the lane's own now_et convention


class TestNoOpWhenPremarketMissing:
    def test_missing_file_returns_none_and_writes_nothing(self, tmp_path):
        klp = tmp_path / "key-levels.json"
        outp = tmp_path / "crosscheck.jsonl"
        result = fpc.crosscheck_and_log("MES", _bars([100.0]), NOW_ET,
                                        key_levels_path=klp, out_path=outp)
        assert result is None
        assert not outp.exists()

    def test_instrument_not_in_file_returns_none(self, tmp_path):
        klp = tmp_path / "key-levels.json"
        outp = tmp_path / "crosscheck.jsonl"
        _write_key_levels(klp, "MNQ", [{"price": 100.0, "label": "PDH"}])
        result = fpc.crosscheck_and_log("MES", _bars([100.0]), NOW_ET,
                                        key_levels_path=klp, out_path=outp)
        assert result is None

    def test_data_missing_status_returns_none(self, tmp_path):
        klp = tmp_path / "key-levels.json"
        outp = tmp_path / "crosscheck.jsonl"
        _write_key_levels(klp, "MES", [], status="DATA_MISSING")
        result = fpc.crosscheck_and_log("MES", _bars([100.0]), NOW_ET,
                                        key_levels_path=klp, out_path=outp)
        assert result is None

    def test_corrupt_key_levels_file_never_raises(self, tmp_path):
        klp = tmp_path / "key-levels.json"
        outp = tmp_path / "crosscheck.jsonl"
        klp.write_text("{not json", encoding="utf-8")
        result = fpc.crosscheck_and_log("MES", _bars([100.0]), NOW_ET,
                                        key_levels_path=klp, out_path=outp)
        assert result is None


class TestRowShapeAndMath:
    def test_matched_within_threshold_and_unmatched_named(self, tmp_path):
        klp = tmp_path / "key-levels.json"
        outp = tmp_path / "crosscheck.jsonl"
        # internal levels derived from these bars will include 100.0-ish highs/lows;
        # premarket carries one level close to the data (matches) and one far away (no match).
        _write_key_levels(klp, "MES", [
            {"price": 100.0, "label": "PDH_close"},
            {"price": 500.0, "label": "PDL_far"},
        ])
        bars = _bars([99.0, 100.0, 101.0, 100.5, 99.5] * 5)
        row = fpc.crosscheck_and_log("MES", bars, NOW_ET, key_levels_path=klp, out_path=outp)
        assert row is not None
        assert row["date"] == "2026-09-03"
        assert row["instrument"] == "MES"
        assert row["n_premarket"] == 2
        assert row["n_internal"] >= 1
        assert row["matched_within_2pts"] == 1
        assert row["max_gap_pts"] is not None
        assert len(row["unmatched_premarket"]) == 1
        assert row["unmatched_premarket"][0]["label"] == "PDL_far"
        assert row["unmatched_premarket"][0]["nearest_internal_gap_pts"] > 2.0

    def test_row_is_appended_to_jsonl(self, tmp_path):
        klp = tmp_path / "key-levels.json"
        outp = tmp_path / "crosscheck.jsonl"
        _write_key_levels(klp, "MES", [{"price": 100.0, "label": "PDH"}])
        fpc.crosscheck_and_log("MES", _bars([100.0] * 5), NOW_ET, key_levels_path=klp,
                               out_path=outp)
        lines = outp.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert set(row.keys()) >= {"date", "n_internal", "n_premarket",
                                   "matched_within_2pts", "max_gap_pts",
                                   "unmatched_premarket"}

    def test_no_internal_levels_leaves_every_premarket_level_unmatched(self, tmp_path):
        klp = tmp_path / "key-levels.json"
        outp = tmp_path / "crosscheck.jsonl"
        _write_key_levels(klp, "MES", [{"price": 100.0, "label": "PDH"}])
        row = fpc.crosscheck_and_log("MES", pd.DataFrame(), NOW_ET, key_levels_path=klp,
                                     out_path=outp)
        assert row["n_internal"] == 0
        assert row["matched_within_2pts"] == 0
        assert row["unmatched_premarket"][0]["nearest_internal_gap_pts"] is None
        assert row["max_gap_pts"] is None


class TestIdempotentPerSession:
    def test_second_call_same_session_is_a_noop(self, tmp_path):
        klp = tmp_path / "key-levels.json"
        outp = tmp_path / "crosscheck.jsonl"
        _write_key_levels(klp, "MES", [{"price": 100.0, "label": "PDH"}])
        bars = _bars([100.0] * 5)
        first = fpc.crosscheck_and_log("MES", bars, NOW_ET, key_levels_path=klp, out_path=outp)
        second = fpc.crosscheck_and_log("MES", bars, NOW_ET + dt.timedelta(minutes=5),
                                        key_levels_path=klp, out_path=outp)
        assert first is not None
        assert second is None
        lines = outp.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_already_logged_today_reads_existing_rows(self, tmp_path):
        outp = tmp_path / "crosscheck.jsonl"
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps({"date": "2026-09-03"}) + "\n", encoding="utf-8")
        assert fpc.already_logged_today("2026-09-03", path=outp) is True
        assert fpc.already_logged_today("2026-09-04", path=outp) is False

    def test_already_logged_today_false_when_file_absent(self, tmp_path):
        assert fpc.already_logged_today("2026-09-03", path=tmp_path / "nope.jsonl") is False


class TestNeverRaises:
    def test_crosscheck_and_log_never_raises_on_garbage_bars(self, tmp_path):
        klp = tmp_path / "key-levels.json"
        outp = tmp_path / "crosscheck.jsonl"
        _write_key_levels(klp, "MES", [{"price": 100.0, "label": "PDH"}])
        # bars missing the expected column entirely
        bad_bars = pd.DataFrame({"nonsense": [1, 2, 3]})
        result = fpc.crosscheck_and_log("MES", bad_bars, NOW_ET, key_levels_path=klp,
                                        out_path=outp)
        assert result is None
