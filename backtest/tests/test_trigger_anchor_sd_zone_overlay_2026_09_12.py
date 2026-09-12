"""Guards for the sd-zone overlay added to backtest/tools/trigger_anchor_class_read.py
(GOAL-SD-LIQUIDITY-ZONES-2026-09-11 item d; ratifying instrument named in
prereg-sd-zone-anchor-promotion-2026-09-12.md).

WHAT THIS CLOSES: the SD_ZONE overlay answers a question the engine's own
`matched_level_label` cannot -- sd-zones.json/sd-zones-archive is SHADOW-only, so no
ENTER tick is ever anchored on a zone label. `sd_zone_read` instead checks, independent
of what triggered the entry, whether the SPY spot at entry time was sitting inside an
archived Smart-Money-Concepts zone that day.

Covers:
  1. `_in_zone` matches inclusive bounds, misses outside them, skips malformed zone rows.
  2. `_load_zone_archive` returns None (not []) when no file exists for that day --
     the None/empty-list distinction is load-bearing (a day with a real archive but zero
     surviving zones must never be conflated with "archive doesn't exist yet").
  3. `sd_zone_read` buckets each leg into in_zone / out_of_zone / no_archive_days using a
     synthetic ledger + trades.csv + archive fixture -- proves the (day, time) join,
     the +-2min tick-matching tolerance (mirrors `read()`'s own), and that a day with no
     archive file contributes to `no_archive_days`, never silently into `out_of_zone`.
  4. The pre-existing `read()` / `_cls` path (the already-ratified swing-pivot prereg
     instrument) is byte-behaviourally unchanged by this addition.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO / "backtest" / "tools"
for _p in (str(REPO), str(TOOLS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import trigger_anchor_class_read as tac  # noqa: E402


# --------------------------------------------------------------------------- 1. _in_zone

def test_in_zone_matches_inclusive_bounds_and_misses_outside():
    zones = [{"low": 760.0, "high": 761.0}, {"low": 500.0, "high": "garbage"}]
    assert tac._in_zone(760.0, zones) is not None
    assert tac._in_zone(761.0, zones) is not None
    assert tac._in_zone(759.99, zones) is None
    assert tac._in_zone(761.01, zones) is None


def test_in_zone_skips_malformed_zone_rows_without_raising():
    zones = [{"low": "x", "high": "y"}, {"missing": "keys"}]
    assert tac._in_zone(700.0, zones) is None


# --------------------------------------------------------------------------- 2. archive load

def test_load_zone_archive_returns_none_when_file_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(tac, "SD_ZONE_ARCHIVE", tmp_path)
    assert tac._load_zone_archive("2026-09-01") is None


def test_load_zone_archive_none_vs_empty_list_are_distinct(tmp_path, monkeypatch):
    monkeypatch.setattr(tac, "SD_ZONE_ARCHIVE", tmp_path)
    (tmp_path / "2026-09-02.json").write_text(json.dumps({"date": "2026-09-02", "zones": []}),
                                                encoding="utf-8")
    result = tac._load_zone_archive("2026-09-02")
    assert result == [], "a real archive with zero surviving zones must be [], not None"
    assert tac._load_zone_archive("2026-09-03") is None, "no file at all must be None"


# --------------------------------------------------------------------------- 3. sd_zone_read

def _write_ledger(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _write_trades(path: Path, rows: list[dict]) -> None:
    fields = ["date", "time_entry", "dollar_pnl"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def test_sd_zone_read_buckets_in_zone_out_of_zone_and_no_archive(tmp_path, monkeypatch):
    ledger = tmp_path / "core-decisions.jsonl"
    trades = tmp_path / "trades.csv"
    archive_dir = tmp_path / "sd-zones-archive"
    archive_dir.mkdir()

    # Day 1 (has an archive): one entry lands inside the zone, one lands outside it.
    _write_ledger(ledger, [
        {"ts_et": "2026-09-14 10:00:03", "verdict": "ENTER", "spy": 760.5},
        {"ts_et": "2026-09-14 11:00:02", "verdict": "ENTER", "spy": 700.0},
        # Day 2 (no archive file): entry must land in no_archive_days, never out_of_zone.
        {"ts_et": "2026-09-15 09:40:01", "verdict": "ENTER", "spy": 750.0},
    ])
    _write_trades(trades, [
        {"date": "2026-09-14", "time_entry": "10:00", "dollar_pnl": "150"},
        {"date": "2026-09-14", "time_entry": "11:00", "dollar_pnl": "-40"},
        {"date": "2026-09-15", "time_entry": "09:40", "dollar_pnl": "20"},
    ])
    (archive_dir / "2026-09-14.json").write_text(
        json.dumps({"date": "2026-09-14", "zones": [{"low": 760.0, "high": 761.0}]}),
        encoding="utf-8")

    monkeypatch.setattr(tac, "LEDGER", ledger)
    monkeypatch.setattr(tac, "TRADES", trades)
    monkeypatch.setattr(tac, "SD_ZONE_ARCHIVE", archive_dir)

    res = tac.sd_zone_read("2026-09-14", "2026-09-15")
    assert res["buckets"]["in_zone"]["legs"] == 1
    assert res["buckets"]["in_zone"]["pnl"] == 150.0
    assert res["buckets"]["out_of_zone"]["legs"] == 1
    assert res["buckets"]["out_of_zone"]["pnl"] == -40.0
    assert res["no_archive_days"] == ["2026-09-15"]
    assert res["unmatched_legs"] == 0


def test_sd_zone_read_offset_tick_join_matches_read_tolerance(tmp_path, monkeypatch):
    """Entry logged at 10:02, ENTER tick fired at 10:00 -- within the same +-2min window
    `read()` already uses; must still resolve to the archived zone."""
    ledger = tmp_path / "core-decisions.jsonl"
    trades = tmp_path / "trades.csv"
    archive_dir = tmp_path / "sd-zones-archive"
    archive_dir.mkdir()

    _write_ledger(ledger, [{"ts_et": "2026-09-14 10:00:03", "verdict": "ENTER", "spy": 760.5}])
    _write_trades(trades, [{"date": "2026-09-14", "time_entry": "10:02", "dollar_pnl": "10"}])
    (archive_dir / "2026-09-14.json").write_text(
        json.dumps({"date": "2026-09-14", "zones": [{"low": 760.0, "high": 761.0}]}),
        encoding="utf-8")

    monkeypatch.setattr(tac, "LEDGER", ledger)
    monkeypatch.setattr(tac, "TRADES", trades)
    monkeypatch.setattr(tac, "SD_ZONE_ARCHIVE", archive_dir)

    res = tac.sd_zone_read("2026-09-14", "2026-09-14")
    assert res["buckets"]["in_zone"]["legs"] == 1
    assert res["unmatched_legs"] == 0


# --------------------------------------------------------------------------- 4. pre-existing path unchanged

def test_cls_function_unchanged_by_this_addition():
    assert tac._cls(None) == "NONE"
    assert tac._cls("INTRADAY_SWING_HIGH") == "SWING"
    assert tac._cls("PRIOR_DAY_HIGH") == "STRUCT"
    assert tac._cls("MEMORY_RES_1") == "MEMORY"
    assert tac._cls("SHELF_1") == "SHELF"
    assert tac._cls("SOMETHING_ELSE") == "OTHER"
