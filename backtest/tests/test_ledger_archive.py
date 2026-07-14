"""Tests for setup/scripts/ledger_archive.py -- the daily local ledger archive
(belt-and-suspenders safety net after the 2026-07-14 `git stash drop` incident
that destroyed ~3 weeks of uncommitted decision-ledger history, recovered by luck).

Coverage:
  * archive_today() copies present sources into <archive_root>/<date>/<flattened-name>
  * missing sources are SKIPPED, never crash
  * re-running archive_today() is idempotent (copy2 overwrite, content stays correct)
  * prune_old_dirs() removes ONLY dirs older than the cutoff, judged by DIRECTORY
    NAME date (not mtime); non-date-named dirs are left alone; boundary is exact
  * main() always exits 0, even when et_clock raises

No live network calls, no git operations -- pure filesystem ops against tmp_path.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import ledger_archive as la  # noqa: E402


# ============================================================================
# section 1: archive_today() -- copy present sources, skip missing ones
# ============================================================================

def test_archive_today_copies_present_sources(tmp_path):
    repo = tmp_path / "repo"
    archive = tmp_path / "archive"
    (repo / "automation" / "state").mkdir(parents=True)
    (repo / "journal").mkdir(parents=True)
    (repo / "automation" / "state" / "core-decisions.jsonl").write_text('{"a": 1}\n', encoding="utf-8")
    (repo / "journal" / "trades.csv").write_text("date,symbol\n2026-07-14,SPY\n", encoding="utf-8")

    sources = ["automation/state/core-decisions.jsonl", "journal/trades.csv"]
    lines = la.archive_today(repo_root=repo, archive_root=archive, sources=sources, today="2026-07-14")

    dest_dir = archive / "2026-07-14"
    assert (dest_dir / "automation__state__core-decisions.jsonl").read_text(encoding="utf-8") == '{"a": 1}\n'
    assert (dest_dir / "journal__trades.csv").read_text(encoding="utf-8") == "date,symbol\n2026-07-14,SPY\n"
    assert all(line.startswith("COPY") for line in lines)
    assert len(lines) == 2


def test_archive_today_skips_missing_sources_without_crashing(tmp_path):
    repo = tmp_path / "repo"
    archive = tmp_path / "archive"
    repo.mkdir()

    sources = ["automation/state/fleet/safe-3/decisions.jsonl", "journal/trades-aggressive.csv"]
    lines = la.archive_today(repo_root=repo, archive_root=archive, sources=sources, today="2026-07-14")

    assert len(lines) == 2
    assert all(line.startswith("SKIP") for line in lines)
    assert all("source not found" in line for line in lines)
    # dest dir is still created (mkdir happens before the per-file loop) but stays empty
    dest_dir = archive / "2026-07-14"
    assert dest_dir.exists()
    assert list(dest_dir.iterdir()) == []


def test_archive_today_mixed_present_and_missing(tmp_path):
    repo = tmp_path / "repo"
    archive = tmp_path / "archive"
    (repo / "journal").mkdir(parents=True)
    (repo / "journal" / "trades.csv").write_text("present\n", encoding="utf-8")

    sources = ["journal/trades.csv", "journal/trades-aggressive.csv"]
    lines = la.archive_today(repo_root=repo, archive_root=archive, sources=sources, today="2026-07-14")

    copy_lines = [l for l in lines if l.startswith("COPY")]
    skip_lines = [l for l in lines if l.startswith("SKIP")]
    assert len(copy_lines) == 1
    assert len(skip_lines) == 1


def test_archive_today_is_idempotent_running_twice(tmp_path):
    repo = tmp_path / "repo"
    archive = tmp_path / "archive"
    (repo / "journal").mkdir(parents=True)
    src = repo / "journal" / "trades.csv"
    src.write_text("v1\n", encoding="utf-8")

    sources = ["journal/trades.csv"]
    la.archive_today(repo_root=repo, archive_root=archive, sources=sources, today="2026-07-14")
    # running twice with unchanged content must be harmless
    la.archive_today(repo_root=repo, archive_root=archive, sources=sources, today="2026-07-14")
    dest = archive / "2026-07-14" / "journal__trades.csv"
    assert dest.read_text(encoding="utf-8") == "v1\n"

    # source updates -> re-running must overwrite with the newest content (never
    # a stale skip -- the spec's "overwrite is fine" contract)
    src.write_text("v2 updated\n", encoding="utf-8")
    la.archive_today(repo_root=repo, archive_root=archive, sources=sources, today="2026-07-14")
    assert dest.read_text(encoding="utf-8") == "v2 updated\n"


def test_flatten_name_replaces_path_separators():
    assert la._flatten_name("automation/state/fleet/safe-3/decisions.jsonl") == \
        "automation__state__fleet__safe-3__decisions.jsonl"
    assert la._flatten_name("journal/trades.csv") == "journal__trades.csv"


# ============================================================================
# section 2: prune_old_dirs() -- delete only dirs older than cutoff, by NAME
# ============================================================================

def test_prune_removes_only_dirs_older_than_cutoff(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    old_dir = archive / "2026-06-01"
    recent_dir = archive / "2026-07-10"
    old_dir.mkdir()
    recent_dir.mkdir()
    (old_dir / "f.txt").write_text("x", encoding="utf-8")
    (recent_dir / "f.txt").write_text("x", encoding="utf-8")

    cutoff = date(2026, 7, 14) - timedelta(days=30)  # 2026-06-14
    lines = la.prune_old_dirs(archive_root=archive, cutoff_date=cutoff)

    assert not old_dir.exists()
    assert recent_dir.exists()
    assert lines == ["PRUNE 2026-06-01"]


def test_prune_boundary_exactly_at_cutoff_is_not_removed(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    cutoff = date(2026, 6, 14)
    exact_dir = archive / "2026-06-14"  # exactly at cutoff -- must survive (< cutoff, not <=)
    exact_dir.mkdir()

    lines = la.prune_old_dirs(archive_root=archive, cutoff_date=cutoff)

    assert exact_dir.exists()
    assert lines == []


def test_prune_one_day_past_cutoff_is_removed(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    cutoff = date(2026, 6, 14)
    just_old_dir = archive / "2026-06-13"
    just_old_dir.mkdir()

    lines = la.prune_old_dirs(archive_root=archive, cutoff_date=cutoff)

    assert not just_old_dir.exists()
    assert lines == ["PRUNE 2026-06-13"]


def test_prune_ignores_non_date_named_dirs_and_files(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    weird_dir = archive / "not-a-date"
    weird_dir.mkdir()
    stray_file = archive / "README.md"
    stray_file.write_text("note", encoding="utf-8")

    cutoff = date(2026, 7, 14)
    lines = la.prune_old_dirs(archive_root=archive, cutoff_date=cutoff)

    assert weird_dir.exists()
    assert stray_file.exists()
    assert lines == []


def test_prune_missing_archive_root_returns_empty(tmp_path):
    archive = tmp_path / "does-not-exist"
    assert la.prune_old_dirs(archive_root=archive, cutoff_date=date(2026, 7, 14)) == []


# ============================================================================
# section 3: main() -- always exits 0, real et_clock wiring, fail-open
# ============================================================================

def test_main_exits_0_with_missing_sources(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    archive = tmp_path / "archive"
    repo.mkdir()

    monkeypatch.setattr(la, "REPO_ROOT", repo)
    monkeypatch.setattr(la, "ARCHIVE_ROOT", archive)
    monkeypatch.setattr(la, "SOURCES", ["automation/state/core-decisions.jsonl"])

    rc = la.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "SKIP" in out
    assert "pruned" in out


def test_main_exits_0_even_when_et_clock_raises(tmp_path, monkeypatch, capsys):
    """Fail-open contract: an unexpected exception anywhere in main() must never
    propagate -- the scheduled task must always exit 0 (OP-25/C7)."""
    monkeypatch.setattr(la, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(la, "ARCHIVE_ROOT", tmp_path / "archive")

    def _boom():
        raise RuntimeError("et_clock unavailable")

    monkeypatch.setattr(la, "et_today_str", _boom)
    rc = la.main()
    assert rc == 0
    assert "ERROR" in capsys.readouterr().out


def test_main_copies_real_style_sources_end_to_end(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    archive = tmp_path / "archive"
    (repo / "automation" / "state" / "fleet" / "safe-3").mkdir(parents=True)
    (repo / "journal").mkdir(parents=True)
    (repo / "automation" / "state" / "fleet" / "safe-3" / "decisions.jsonl").write_text(
        '{"ts": "2026-07-14T10:00:00"}\n', encoding="utf-8"
    )
    (repo / "journal" / "trades.csv").write_text("date,symbol,pnl\n", encoding="utf-8")

    monkeypatch.setattr(la, "REPO_ROOT", repo)
    monkeypatch.setattr(la, "ARCHIVE_ROOT", archive)
    monkeypatch.setattr(la, "SOURCES", [
        "automation/state/fleet/safe-3/decisions.jsonl",
        "journal/trades.csv",
        "journal/trades-aggressive.csv",  # deliberately missing
    ])
    monkeypatch.setattr(la, "et_today_str", lambda: "2026-07-14")
    monkeypatch.setattr(la, "et_now", lambda: __import__("datetime").datetime(2026, 7, 14, 16, 12))

    rc = la.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert (archive / "2026-07-14" / "automation__state__fleet__safe-3__decisions.jsonl").exists()
    assert (archive / "2026-07-14" / "journal__trades.csv").exists()
    assert "COPY" in out
    assert "SKIP" in out
    assert "journal/trades-aggressive.csv" in out
