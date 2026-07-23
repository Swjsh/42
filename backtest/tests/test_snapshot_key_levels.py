"""Tests for setup/scripts/snapshot_key_levels.py -- dated point-in-time snapshots
of the live level feed (automation/state/key-levels.json + key-levels-memory.json),
built 2026-07-23 after the full-engine replay proved the live level feed is never
historically snapshotted (trade-level fidelity of every historical engine replay
is compromised as a result). Forward-only fix: this script takes the snapshots.

Coverage:
  * snapshot_one() writes a dated file when no prior snapshot exists for the day
  * snapshot_one() SKIPS the write (SKIP-UNCHANGED) when content matches the day's
    latest same-kind snapshot -- the churn-avoidance contract
  * snapshot_one() writes a FRESH file when content differs from the latest snapshot
  * snapshot_one() fails open (SKIP, never raises) when the source file is missing
  * _latest_snapshot() picks the highest-HHMM file and never crosses main/memory kinds
  * main() always exits 0, including when et_clock raises (fail-open, OP-25/C7)
  * main() end-to-end: writes both main + memory snapshots from real-shaped sources

No live network calls, no broker/MCP calls -- pure filesystem ops against tmp_path.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import snapshot_key_levels as sk  # noqa: E402


# ============================================================================
# section 1: snapshot_one() -- write / skip-unchanged / skip-missing / fresh
# ============================================================================

def test_snapshot_one_writes_dated_file_when_none_exists(tmp_path):
    source = tmp_path / "key-levels.json"
    source.write_text('{"schema_version": 3}\n', encoding="utf-8")
    day_dir = tmp_path / "history" / "2026-07-23"

    line = sk.snapshot_one(source=source, day_dir=day_dir, hhmm="0835", pattern=sk._MAIN_PATTERN, suffix="")

    dest = day_dir / "0835.json"
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == '{"schema_version": 3}\n'
    assert line.startswith("WROTE")


def test_snapshot_one_skips_when_unchanged_vs_latest(tmp_path):
    source = tmp_path / "key-levels.json"
    source.write_text('{"a": 1}\n', encoding="utf-8")
    day_dir = tmp_path / "history" / "2026-07-23"

    # first fire writes 08:35
    sk.snapshot_one(source=source, day_dir=day_dir, hhmm="0835", pattern=sk._MAIN_PATTERN, suffix="")
    # second fire, same content, later time -- must SKIP, not write a duplicate
    line = sk.snapshot_one(source=source, day_dir=day_dir, hhmm="0930", pattern=sk._MAIN_PATTERN, suffix="")

    assert line.startswith("SKIP-UNCHANGED")
    assert not (day_dir / "0930.json").exists()
    assert (day_dir / "0835.json").exists()
    assert len(list(day_dir.iterdir())) == 1  # no churn


def test_snapshot_one_writes_fresh_file_when_content_changed(tmp_path):
    source = tmp_path / "key-levels.json"
    source.write_text('{"a": 1}\n', encoding="utf-8")
    day_dir = tmp_path / "history" / "2026-07-23"

    sk.snapshot_one(source=source, day_dir=day_dir, hhmm="0835", pattern=sk._MAIN_PATTERN, suffix="")
    source.write_text('{"a": 2}\n', encoding="utf-8")  # levels moved intraday
    line = sk.snapshot_one(source=source, day_dir=day_dir, hhmm="1200", pattern=sk._MAIN_PATTERN, suffix="")

    dest = day_dir / "1200.json"
    assert line.startswith("WROTE")
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == '{"a": 2}\n'
    assert (day_dir / "0835.json").read_text(encoding="utf-8") == '{"a": 1}\n'  # prior snapshot untouched


def test_snapshot_one_fails_open_on_missing_source(tmp_path):
    source = tmp_path / "does-not-exist.json"
    day_dir = tmp_path / "history" / "2026-07-23"

    line = sk.snapshot_one(source=source, day_dir=day_dir, hhmm="0835", pattern=sk._MAIN_PATTERN, suffix="")

    assert line.startswith("SKIP")
    assert "source not found" in line
    assert not day_dir.exists()  # never created for a missing source


def test_snapshot_one_memory_suffix_writes_distinct_filename(tmp_path):
    source = tmp_path / "key-levels-memory.json"
    source.write_text('{"levels": []}\n', encoding="utf-8")
    day_dir = tmp_path / "history" / "2026-07-23"

    line = sk.snapshot_one(
        source=source, day_dir=day_dir, hhmm="0835", pattern=sk._MEMORY_PATTERN, suffix="-memory"
    )

    assert (day_dir / "0835-memory.json").exists()
    assert line.startswith("WROTE")


# ============================================================================
# section 2: _latest_snapshot() -- highest HHMM, never crosses kinds
# ============================================================================

def test_latest_snapshot_picks_highest_hhmm(tmp_path):
    day_dir = tmp_path / "2026-07-23"
    day_dir.mkdir(parents=True)
    for hhmm in ("0835", "0930", "1200", "1550"):
        (day_dir / f"{hhmm}.json").write_text("x", encoding="utf-8")

    latest = sk._latest_snapshot(day_dir, sk._MAIN_PATTERN)
    assert latest.name == "1550.json"


def test_latest_snapshot_main_pattern_ignores_memory_files(tmp_path):
    day_dir = tmp_path / "2026-07-23"
    day_dir.mkdir(parents=True)
    (day_dir / "0835.json").write_text("main", encoding="utf-8")
    (day_dir / "1550-memory.json").write_text("memory", encoding="utf-8")  # higher HHMM, wrong kind

    latest = sk._latest_snapshot(day_dir, sk._MAIN_PATTERN)
    assert latest.name == "0835.json"  # the -memory file must never match the main pattern


def test_latest_snapshot_missing_dir_returns_none(tmp_path):
    assert sk._latest_snapshot(tmp_path / "nope", sk._MAIN_PATTERN) is None


# ============================================================================
# section 3: main() -- always exits 0, real et_clock wiring, fail-open
# ============================================================================

def test_main_exits_0_with_missing_sources(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sk, "SOURCE_MAIN", tmp_path / "no-main.json")
    monkeypatch.setattr(sk, "SOURCE_MEMORY", tmp_path / "no-memory.json")
    monkeypatch.setattr(sk, "HISTORY_ROOT", tmp_path / "history")
    monkeypatch.setattr(sk, "et_today_str", lambda: "2026-07-23")
    monkeypatch.setattr(sk, "et_now", lambda: __import__("datetime").datetime(2026, 7, 23, 8, 35))

    rc = sk.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert out.count("SKIP") == 2
    assert "source not found" in out


def test_main_exits_0_even_when_et_clock_raises(tmp_path, monkeypatch, capsys):
    """Fail-open contract: an unexpected exception anywhere in main() must never
    propagate -- the scheduled task must always exit 0 (OP-25/C7)."""
    monkeypatch.setattr(sk, "HISTORY_ROOT", tmp_path / "history")

    def _boom():
        raise RuntimeError("et_clock unavailable")

    monkeypatch.setattr(sk, "et_today_str", _boom)
    rc = sk.main()
    assert rc == 0
    assert "ERROR" in capsys.readouterr().out


def test_main_writes_both_sources_end_to_end(tmp_path, monkeypatch, capsys):
    main_src = tmp_path / "key-levels.json"
    memory_src = tmp_path / "key-levels-memory.json"
    main_src.write_text('{"schema_version": 3, "levels": []}\n', encoding="utf-8")
    memory_src.write_text('{"levels": []}\n', encoding="utf-8")
    history_root = tmp_path / "history"

    monkeypatch.setattr(sk, "SOURCE_MAIN", main_src)
    monkeypatch.setattr(sk, "SOURCE_MEMORY", memory_src)
    monkeypatch.setattr(sk, "HISTORY_ROOT", history_root)
    monkeypatch.setattr(sk, "et_today_str", lambda: "2026-07-23")
    monkeypatch.setattr(sk, "et_now", lambda: __import__("datetime").datetime(2026, 7, 23, 8, 35))

    rc = sk.main()
    out = capsys.readouterr().out

    assert rc == 0
    day_dir = history_root / "2026-07-23"
    assert (day_dir / "0835.json").read_text(encoding="utf-8") == '{"schema_version": 3, "levels": []}\n'
    assert (day_dir / "0835-memory.json").read_text(encoding="utf-8") == '{"levels": []}\n'
    assert out.count("WROTE") == 2

    # a second fire the same "minute" with unchanged content must skip both, not duplicate
    rc2 = sk.main()
    out2 = capsys.readouterr().out
    assert rc2 == 0
    assert out2.count("SKIP-UNCHANGED") == 2
    assert len(list(day_dir.iterdir())) == 2  # still exactly the two original files
