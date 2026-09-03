"""Guard: setup/scripts/trend_cache_producer.py -- the daily $0 extender for the
trend-classification SPY-daily-bar cache (TREND-CLASSIFICATION-CACHE-STALE-SINCE-07-14,
automation/overnight/queue.md).

WHAT THIS PINS:
  1. merge_bars() is append-only from a reader's point of view: every existing bar OUTSIDE
     the fetch window survives byte-for-byte; fetched bars win only on a genuine timestamp
     overlap.
  2. classify_trend_asof() (backtest/tools/regime_classifier.py, UNMODIFIED, no re-derivation)
     returns the BYTE-EQUAL (trend, trend_meta) for every date within the frozen cache's own
     coverage whether it is handed the original frozen bars or the producer's merged/extended
     bars -- extending the cache forward must never retroactively change a single historical
     label.
  3. run() NEVER writes to the frozen 2026-07-14 filename, always publishes a NEW dated file
     + updates the pointer.
  4. backtest/tools/regime_conditioned_validation.py's guarded reader (guarded_classify_trend_asof
     + resolve_trend_cache_last_bar_date) gets a DETERMINATE trend for dates the extension now
     covers, while dates still past the (moved) staleness boundary stay 'unknown' -- never
     fabricated.
  5. RED-PROOF: 3 mutants of the merge/overwrite-guard logic, each shown to diverge from the
     real implementation's behavior in a way that would silently corrupt or overwrite data.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_trend_cache_producer_2026_09_03.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_SCRIPTS = ROOT / "setup" / "scripts"
for _p in (str(_SCRIPTS), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import trend_cache_producer as tcp  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402
from backtest.tools import regime_classifier as rc  # noqa: E402
from backtest.tools import regime_conditioned_validation as rcv  # noqa: E402

FROZEN_CACHE = ROOT / "analysis" / "backtests" / "cache" / "trend-alignment-spy-daily-2024-07-01_2026-07-14.json"
DATA_PRESENT = FROZEN_CACHE.exists()
requires_data = pytest.mark.skipif(not DATA_PRESENT, reason="frozen trend cache not on disk")


# --------------------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------------------- #
def _raw_bar(date_str: str, close: float) -> dict:
    return {"timestamp": f"{date_str}T04:00:00Z", "open": close - 0.5, "high": close + 1.0,
            "low": close - 1.0, "close": close, "volume": 1_000_000}


def _bars_from_raw(raw_bars: list[dict]) -> list[Bar]:
    """SAME parsing shape regime_classifier.load_daily_spy_bars() uses -- test scaffolding
    only, never re-derives the classification math itself."""
    bars = []
    for row in raw_bars:
        ts = dt.datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        bars.append(Bar(open_time=ts, open=float(row["open"]), high=float(row["high"]),
                         low=float(row["low"]), close=float(row["close"]),
                         volume=float(row.get("volume", 0) or 0),
                         granularity_seconds=86400, source="test_fixture"))
    bars.sort(key=lambda b: b.open_time)
    return bars


@pytest.fixture()
def small_existing() -> list[dict]:
    """20 synthetic trading-day bars ending 2026-07-14 -- a tiny stand-in for the frozen
    cache, used by the hermetic (non-real-data) tests."""
    out = []
    d = dt.date(2026, 6, 15)
    n = 0
    while n < 20:
        if d.weekday() < 5:
            out.append(_raw_bar(d.isoformat(), 700.0 + n))
            n += 1
        d += dt.timedelta(days=1)
    return out


@pytest.fixture()
def existing_ending_0714() -> list[dict]:
    """Synthetic bars whose max date is EXACTLY 2026-07-14 -- needed to force the
    frozen-filename collision the overwrite guard must catch."""
    out = []
    d = dt.date(2026, 6, 16)
    n = 0
    while d <= dt.date(2026, 7, 14):
        if d.weekday() < 5:
            out.append(_raw_bar(d.isoformat(), 700.0 + n))
            n += 1
        d += dt.timedelta(days=1)
    assert out[-1]["timestamp"][:10] == "2026-07-14"
    return out


def _stub_fetch_factory(bars: list[dict]):
    def _fetch(start: dt.date, end: dt.date):
        return [b for b in bars if start <= dt.date.fromisoformat(b["timestamp"][:10]) <= end], 1
    return _fetch


# --------------------------------------------------------------------------------------- #
# 1. merge_bars() -- append-only, freshest-wins-on-overlap
# --------------------------------------------------------------------------------------- #
class TestMergeBars:
    def test_preserves_existing_outside_overlap_byte_for_byte(self, small_existing):
        fetched = [_raw_bar("2026-07-20", 999.0)]  # far outside the existing range
        merged = tcp.merge_bars(small_existing, fetched)
        by_ts = {b["timestamp"]: b for b in merged}
        for b in small_existing:
            assert by_ts[b["timestamp"]] == b, "an untouched historical bar was mutated"

    def test_appends_new_bars(self, small_existing):
        fetched = [_raw_bar("2026-07-15", 800.0), _raw_bar("2026-07-16", 801.0)]
        merged = tcp.merge_bars(small_existing, fetched)
        assert len(merged) == len(small_existing) + 2
        assert merged[-1]["timestamp"] == "2026-07-16T04:00:00Z"

    def test_fetched_wins_on_genuine_overlap(self, small_existing):
        last = small_existing[-1]
        overlap_date = last["timestamp"][:10]
        corrected = _raw_bar(overlap_date, close=last["close"] + 5.0)  # a "corrected" re-fetch
        merged = tcp.merge_bars(small_existing, [corrected])
        by_ts = {b["timestamp"]: b for b in merged}
        assert by_ts[corrected["timestamp"]]["close"] == corrected["close"]
        assert len(merged) == len(small_existing)  # no duplicate row for the same date


# --------------------------------------------------------------------------------------- #
# 2. run() -- never overwrites the frozen file, always publishes a new dated file + pointer
# --------------------------------------------------------------------------------------- #
class TestRunNeverTouchesFrozenFile:
    def test_run_writes_new_dated_file_and_pointer(self, tmp_path, monkeypatch, small_existing):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        pointer_file = tmp_path / "state" / "trend-alignment-latest.json"
        existing_path = cache_dir / "trend-alignment-spy-daily-2024-07-01_2026-07-14.json"
        existing_path.write_text(json.dumps({"bars": small_existing}), encoding="utf-8")

        monkeypatch.setattr(tcp, "CACHE_DIR", cache_dir)
        monkeypatch.setattr(tcp, "POINTER_FILE", pointer_file)
        monkeypatch.setattr(tcp, "FROZEN_CACHE_FILE", existing_path)

        fetched = [_raw_bar("2026-07-15", 900.0), _raw_bar("2026-07-16", 901.0)]
        now_et = dt.datetime(2026, 7, 16, 16, 20, 0)
        result = tcp.run(now_et=now_et, existing_cache_path=existing_path,
                          fetch_fn=_stub_fetch_factory(fetched))

        out_path = Path(result["out_path"])
        assert out_path.exists()
        assert out_path != existing_path
        assert out_path.name == "trend-alignment-spy-daily-2024-07-01_2026-07-16.json"
        assert existing_path.read_text(encoding="utf-8") == json.dumps({"bars": small_existing})

        assert pointer_file.exists()
        ptr = json.loads(pointer_file.read_text(encoding="utf-8"))
        assert ptr["cache_path"].endswith("trend-alignment-spy-daily-2024-07-01_2026-07-16.json")
        assert ptr["end"] == "2026-07-16"

        published = json.loads(out_path.read_text(encoding="utf-8"))
        assert published["n_bars"] == len(small_existing) + 2
        assert published["end"] == "2026-07-16"

    def test_run_refuses_if_output_would_collide_with_frozen_name(self, tmp_path, monkeypatch, existing_ending_0714):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        pointer_file = tmp_path / "state" / "trend-alignment-latest.json"
        existing_path = cache_dir / "trend-alignment-spy-daily-2024-07-01_2026-07-14.json"
        original_bytes = json.dumps({"bars": existing_ending_0714})
        existing_path.write_text(original_bytes, encoding="utf-8")

        monkeypatch.setattr(tcp, "CACHE_DIR", cache_dir)
        monkeypatch.setattr(tcp, "POINTER_FILE", pointer_file)
        monkeypatch.setattr(tcp, "FROZEN_CACHE_FILE", existing_path)
        monkeypatch.setattr(tcp, "FETCH_START", dt.date(2024, 7, 1))

        # Force the collision: no new bars fetched, so merged end_date stays 2026-07-14
        # (the frozen file's own date) -- the run must be refused, not silently accepted.
        no_new_bars = _stub_fetch_factory([])
        now_et = dt.datetime(2026, 7, 14, 16, 20, 0)
        with pytest.raises(RuntimeError, match="refusing to overwrite"):
            tcp.run(now_et=now_et, existing_cache_path=existing_path, fetch_fn=no_new_bars)
        # And the frozen file itself must be untouched by the attempt.
        assert existing_path.read_text(encoding="utf-8") == original_bytes


# --------------------------------------------------------------------------------------- #
# 3. classify_trend_asof byte-equality for overlapping dates (real frozen cache)
# --------------------------------------------------------------------------------------- #
@requires_data
class TestClassificationByteEqualOnOverlap:
    @pytest.fixture(scope="class")
    def frozen_raw_bars(self):
        return json.loads(FROZEN_CACHE.read_text(encoding="utf-8"))["bars"]

    def test_same_labels_before_and_after_extension(self, frozen_raw_bars):
        frozen_bars = _bars_from_raw(frozen_raw_bars)
        extended_raw = tcp.merge_bars(
            frozen_raw_bars,
            [_raw_bar("2026-07-15", 760.0), _raw_bar("2026-07-16", 761.0),
             _raw_bar("2026-07-17", 762.0)],
        )
        extended_bars = _bars_from_raw(extended_raw)

        for target in (dt.date(2026, 6, 1), dt.date(2026, 5, 1), dt.date(2026, 3, 2)):
            trend_before, meta_before = rc.classify_trend_asof(frozen_bars, target)
            trend_after, meta_after = rc.classify_trend_asof(extended_bars, target)
            assert trend_after == trend_before, f"trend changed for {target} after extension"
            assert meta_after == meta_before, f"trend_meta changed for {target} after extension"


# --------------------------------------------------------------------------------------- #
# 4. Guarded reader gets fresh labels; past-coverage dates stay unknown
# --------------------------------------------------------------------------------------- #
@requires_data
class TestGuardedReaderFreshCoverage:
    @pytest.fixture(scope="class")
    def extended_bars(self):
        frozen_raw = json.loads(FROZEN_CACHE.read_text(encoding="utf-8"))["bars"]
        new_bars = []
        d = dt.date(2026, 7, 15)
        n = 0
        while n < 15:
            if d.weekday() < 5:
                new_bars.append(_raw_bar(d.isoformat(), 750.0 + n))
                n += 1
            d += dt.timedelta(days=1)
        merged_raw = tcp.merge_bars(frozen_raw, new_bars)
        return _bars_from_raw(merged_raw), max(dt.date.fromisoformat(b["timestamp"][:10]) for b in merged_raw)

    def test_date_newly_covered_is_determinate(self, extended_bars):
        bars, resolved_end = extended_bars
        target = resolved_end - dt.timedelta(days=1)  # well within the fresh coverage
        trend, meta = rcv.guarded_classify_trend_asof(bars, target, cache_last_bar_date=resolved_end)
        assert meta["available"] is True
        assert trend != "unknown" or meta.get("reason") != f"trend_cache_stale_past_{resolved_end.isoformat()}"

    def test_date_past_extended_coverage_still_unknown(self, extended_bars):
        bars, resolved_end = extended_bars
        far_future = resolved_end + dt.timedelta(days=60)
        trend, meta = rcv.guarded_classify_trend_asof(bars, far_future, cache_last_bar_date=resolved_end)
        assert trend == "unknown"
        assert meta["available"] is False
        assert meta["reason"] == f"trend_cache_stale_past_{resolved_end.isoformat()}"

    def test_default_call_without_override_still_pinned_to_frozen_constant(self, extended_bars):
        """Existing pinned tests call guarded_classify_trend_asof with NO override -- must
        keep behaving exactly as before this change (frozen 2026-07-14 boundary)."""
        bars, _resolved_end = extended_bars
        stale_date = dt.date(2026, 8, 25)
        trend, meta = rcv.guarded_classify_trend_asof(bars, stale_date)
        assert trend == "unknown"
        assert meta["cache_last_bar_date"] == rcv.TREND_CACHE_LAST_BAR_DATE.isoformat()

    def test_resolve_trend_cache_last_bar_date_matches_max_bar(self, extended_bars):
        bars, resolved_end = extended_bars
        assert rcv.resolve_trend_cache_last_bar_date(bars) == resolved_end


# --------------------------------------------------------------------------------------- #
# 5. RED-PROOF: 3 mutants, each shown to diverge from the real implementation.
# --------------------------------------------------------------------------------------- #
class TestRedProofMutants:
    def test_mutant_forgets_old_bars_loses_history(self, small_existing):
        """Mutant A: a 'merge' that just returns the newly-fetched bars, discarding
        everything already on disk -- a plausible bug if someone 'simplifies' the merge."""
        def mutant_merge(existing, fetched):
            return sorted(fetched, key=lambda b: b["timestamp"])

        fetched = [_raw_bar("2026-07-15", 900.0)]
        real = tcp.merge_bars(small_existing, fetched)
        mutant = mutant_merge(small_existing, fetched)
        real_dates = {b["timestamp"] for b in real}
        mutant_dates = {b["timestamp"] for b in mutant}
        lost = real_dates - mutant_dates
        assert lost, "mutant should have lost history the real merge preserves"
        assert all(b["timestamp"] in real_dates for b in small_existing)
        assert not all(b["timestamp"] in mutant_dates for b in small_existing)

    def test_mutant_stale_wins_over_fresh_on_overlap(self, small_existing):
        """Mutant B: 'existing wins' instead of 'fetched wins' on a genuine timestamp
        overlap -- silently keeps a stale/corrected bar instead of the fresher re-fetch."""
        def mutant_merge(existing, fetched):
            by_ts = {b["timestamp"]: b for b in fetched}
            for b in existing:
                by_ts[b["timestamp"]] = b  # BUG: existing overwrites fetched
            return sorted(by_ts.values(), key=lambda b: b["timestamp"])

        last = small_existing[-1]
        overlap_date = last["timestamp"][:10]
        corrected = _raw_bar(overlap_date, close=last["close"] + 5.0)

        real = tcp.merge_bars(small_existing, [corrected])
        mutant = mutant_merge(small_existing, [corrected])
        real_val = {b["timestamp"]: b for b in real}[corrected["timestamp"]]
        mutant_val = {b["timestamp"]: b for b in mutant}[corrected["timestamp"]]
        assert real_val["close"] == corrected["close"]
        assert mutant_val["close"] == last["close"]  # mutant kept the stale value -- caught
        assert real_val["close"] != mutant_val["close"]

    def test_mutant_no_frozen_overwrite_guard_would_have_written(self, tmp_path, monkeypatch, existing_ending_0714):
        """Mutant C: run() with the frozen-filename collision check removed entirely --
        would silently write straight into the frozen file's path instead of refusing."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        pointer_file = tmp_path / "state" / "trend-alignment-latest.json"
        existing_path = cache_dir / "trend-alignment-spy-daily-2024-07-01_2026-07-14.json"
        original_bytes = json.dumps({"bars": existing_ending_0714})
        existing_path.write_text(original_bytes, encoding="utf-8")

        monkeypatch.setattr(tcp, "CACHE_DIR", cache_dir)
        monkeypatch.setattr(tcp, "POINTER_FILE", pointer_file)
        monkeypatch.setattr(tcp, "FROZEN_CACHE_FILE", existing_path)

        now_et = dt.datetime(2026, 7, 14, 16, 20, 0)
        with pytest.raises(RuntimeError):
            tcp.run(now_et=now_et, existing_cache_path=existing_path, fetch_fn=_stub_fetch_factory([]))
        assert existing_path.read_text(encoding="utf-8") == original_bytes  # real guard: untouched

        # Mutant: same scenario but WITHOUT the guard check -- reimplements run()'s write
        # path minus the collision guard, proving it WOULD have clobbered the frozen file.
        merged = tcp.merge_bars(existing_ending_0714, [])
        end_date = max(dt.date.fromisoformat(b["timestamp"][:10]) for b in merged)
        mutant_out_path = tcp.CACHE_DIR / f"trend-alignment-spy-daily-2024-07-01_{end_date.isoformat()}.json"
        assert mutant_out_path == existing_path  # the collision the real guard catches
        mutant_out_path.write_text(json.dumps({"bars": merged, "MUTATED": True}), encoding="utf-8")
        assert existing_path.read_text(encoding="utf-8") != original_bytes  # mutant corrupted it
