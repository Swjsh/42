"""D2 / SWEEP-1 guard -- stop_width_population_grid.get_bars cache-poisoning (2026-08-06).

THE DEFECT: get_bars wrote its per-(symbol,date) cache CSV UNCONDITIONALLY -- including
after a FAILED fetch -- so one transient 403/timeout persisted a header-only file that
returned 0 bars forever after (L241's fetcher-masks-failure family, but WORSE: L241
returned nothing once; this persisted the nothing). Trigger proven live: the hardcoded
`end={date}T20:15:00Z` lands inside Alpaca's last-15-min embargo on same-day fetches ->
guaranteed 403. Two poisoned files were hand-deleted on 2026-08-06.

PINNED HERE:
  1. a failed fetch writes NO cache file (retried next run);
  2. an existing zero-row cache is treated as poisoned -> deleted + refetched;
  3. an empty-but-2xx response is also not persisted;
  4. a successful fetch caches and returns the bars;
  5. same-day fetches cap `end` outside the 15-min embargo (_fetch_end_utc).

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_stop_width_grid_cache_2026_08_06.py
"""
from __future__ import annotations

import csv
import io
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "backtest" / "tools"), str(ROOT / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import stop_width_population_grid as grid  # noqa: E402

CREDS = {"key": "k", "secret": "s"}
SYM, DATE = "SPY260806P00770000", "2026-08-05"
BARS = [{"t": "2026-08-05T14:31:00Z", "o": 1.0, "h": 1.1, "l": 0.9, "c": 1.05, "v": 10}]


class _Resp:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(grid, "CACHE", tmp_path)
    return tmp_path


def test_failed_fetch_writes_no_cache(cache, monkeypatch):
    """THE D2 PIN: a 403 (embargo class) must leave NO cache file behind."""
    def _boom(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 403, "forbidden", {}, io.BytesIO(b""))
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    out = grid.get_bars(SYM, DATE, CREDS)
    assert out == []
    assert list(cache.glob("*.csv")) == [], (
        "a FAILED fetch persisted a cache file -- the D2 poison-forever defect is back")


def test_poisoned_zero_row_cache_self_heals(cache, monkeypatch):
    """A pre-existing header-only cache (the pre-fix failure artifact) is deleted and
    refetched instead of returning 0 bars forever."""
    p = cache / f"{SYM}_{DATE}.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(["t", "o", "h", "l", "c", "v"])  # poisoned: header only
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=30: _Resp({"bars": {SYM: BARS}}))
    out = grid.get_bars(SYM, DATE, CREDS)
    assert len(out) == 1 and out[0]["c"] == 1.05, (
        "poisoned zero-row cache was returned as-is instead of self-healing (D2)")
    assert len(list(csv.DictReader(p.open(encoding='utf-8')))) == 1  # rewritten with data


def test_empty_success_response_not_persisted(cache, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=30: _Resp({"bars": {}}))
    out = grid.get_bars(SYM, DATE, CREDS)
    assert out == []
    assert list(cache.glob("*.csv")) == []


def test_successful_fetch_caches_and_returns(cache, monkeypatch):
    calls = {"n": 0}

    def _ok(req, timeout=30):
        calls["n"] += 1
        return _Resp({"bars": {SYM: BARS}})

    monkeypatch.setattr(urllib.request, "urlopen", _ok)
    out1 = grid.get_bars(SYM, DATE, CREDS)
    out2 = grid.get_bars(SYM, DATE, CREDS)  # second call must be served from disk
    assert out1 == out2 and len(out1) == 1
    assert calls["n"] == 1, "cache miss on second call -- caching broke"


def test_same_day_end_capped_outside_embargo():
    """The 403 trigger itself: a same-day fetch's `end` must sit >=16 min behind UTC now;
    historical dates keep the full 20:15Z window byte-identical."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    end_today = grid._fetch_end_utc(today)
    limit = (datetime.now(timezone.utc) - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert end_today <= limit, f"same-day end {end_today} is inside the 15-min embargo"
    assert grid._fetch_end_utc("2026-07-01") == "2026-07-01T20:15:00Z"
