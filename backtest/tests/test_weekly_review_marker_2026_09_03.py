"""Guard: setup/scripts/weekly_review_marker.py (queue.md WEEKLY-REVIEW-RETRY-DONE-MARKER, LOW).

Gamma_WeeklyReview fires an ~$8 Invoke-Claude LLM review with a 12-min cap. Every other
evening producer got a PT15M/PT30M self-heal retry window on 2026-09-03 (dceb125e) --
WeeklyReview was left out because a retry within that window would double-bill the LLM
call with no way to know a same-week run already completed. This guard covers the
done-marker module the .ps1 wrapper now consults:

  - check(): SKIP (exit 0) when the marker's week_iso matches the current ISO week;
             RUN (exit 1) when the marker is missing, stale (prior week), or corrupt.
  - write(): records the CURRENT ISO week + artifact path; caller invokes this ONLY
             after Invoke-Claude reports success (enforced by run-weekly-review.ps1,
             not by this module) -- so this guard proves write() is never triggered
             as a side effect of check(), which is the mechanism that keeps a failed
             run's marker absent/stale so the retry window can recover it.

All marker files live under tmp_path -- this guard never touches the real
automation/state/weekly-review-done.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import weekly_review_marker as wrm  # noqa: E402


# --------------------------------------------------------------------------------------- #
# iso_week_string -- real ISO-8601 week numbering, not a naive day-of-year divide.
# --------------------------------------------------------------------------------------- #
def test_iso_week_string_known_date():
    # 2026-09-06 is a Sunday; ISO week 36 of 2026 (Mon 2026-08-31 .. Sun 2026-09-06).
    dt = datetime.fromisoformat("2026-09-06T18:00:00-04:00")
    assert wrm.iso_week_string(dt) == "2026-W36"


def test_iso_week_string_next_week_is_different():
    dt_week36 = datetime.fromisoformat("2026-09-06T18:00:00-04:00")
    dt_week37 = datetime.fromisoformat("2026-09-13T18:00:00-04:00")
    assert wrm.iso_week_string(dt_week36) != wrm.iso_week_string(dt_week37)


# --------------------------------------------------------------------------------------- #
# is_current_week_done -- the skip/run decision.
# --------------------------------------------------------------------------------------- #
def test_is_current_week_done_true_when_marker_matches_current_week(tmp_path):
    marker = tmp_path / "weekly-review-done.json"
    now = datetime.fromisoformat("2026-09-06T18:03:11-04:00")
    marker.write_text(json.dumps({
        "week_iso": "2026-W36",
        "generated_et": now.isoformat(),
        "artifact_path": "analysis/weekly/2026-W36.md",
    }), encoding="utf-8")
    assert wrm.is_current_week_done(marker, now) is True


def test_is_current_week_done_false_when_marker_is_a_stale_prior_week(tmp_path):
    marker = tmp_path / "weekly-review-done.json"
    now = datetime.fromisoformat("2026-09-06T18:03:11-04:00")
    marker.write_text(json.dumps({
        "week_iso": "2026-W35",
        "generated_et": "2026-08-30T18:00:00-04:00",
        "artifact_path": "analysis/weekly/2026-W35.md",
    }), encoding="utf-8")
    assert wrm.is_current_week_done(marker, now) is False


def test_is_current_week_done_false_when_marker_missing(tmp_path):
    marker = tmp_path / "does-not-exist.json"
    now = datetime.fromisoformat("2026-09-06T18:03:11-04:00")
    assert wrm.is_current_week_done(marker, now) is False


def test_is_current_week_done_false_when_marker_corrupt(tmp_path):
    marker = tmp_path / "weekly-review-done.json"
    marker.write_text("{not valid json", encoding="utf-8")
    now = datetime.fromisoformat("2026-09-06T18:03:11-04:00")
    assert wrm.is_current_week_done(marker, now) is False


def test_is_current_week_done_false_when_marker_is_not_a_json_object(tmp_path):
    marker = tmp_path / "weekly-review-done.json"
    marker.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    now = datetime.fromisoformat("2026-09-06T18:03:11-04:00")
    assert wrm.is_current_week_done(marker, now) is False


# --------------------------------------------------------------------------------------- #
# write_marker -- the SUCCESS path only.
# --------------------------------------------------------------------------------------- #
def test_write_marker_creates_parent_dirs_and_correct_fields(tmp_path):
    marker = tmp_path / "nested" / "state" / "weekly-review-done.json"
    now = datetime.fromisoformat("2026-09-06T18:03:11-04:00")
    payload = wrm.write_marker(marker, now, "analysis/weekly/2026-W36.md")
    assert marker.exists()
    on_disk = json.loads(marker.read_text(encoding="utf-8"))
    assert on_disk == payload
    assert payload["week_iso"] == "2026-W36"
    assert payload["artifact_path"] == "analysis/weekly/2026-W36.md"
    assert payload["generated_et"] == now.isoformat()


def test_write_marker_overwrites_a_stale_prior_week(tmp_path):
    marker = tmp_path / "weekly-review-done.json"
    old_now = datetime.fromisoformat("2026-08-30T18:00:00-04:00")
    wrm.write_marker(marker, old_now, "analysis/weekly/2026-W35.md")
    new_now = datetime.fromisoformat("2026-09-06T18:03:11-04:00")
    wrm.write_marker(marker, new_now, "analysis/weekly/2026-W36.md")
    on_disk = json.loads(marker.read_text(encoding="utf-8"))
    assert on_disk["week_iso"] == "2026-W36"
    assert wrm.is_current_week_done(marker, new_now) is True
    assert wrm.is_current_week_done(marker, old_now) is False


# --------------------------------------------------------------------------------------- #
# check() never writes -- the mechanism that keeps a FAILED run's marker absent/stale so
# the PT15M/PT30M retry window can recover it (write is only ever called by the .ps1
# wrapper's own success branch, never by check()).
# --------------------------------------------------------------------------------------- #
def test_check_command_never_creates_the_marker_file(tmp_path, capsys):
    marker = tmp_path / "weekly-review-done.json"
    assert not marker.exists()
    rc = wrm.main(["check", "--marker", str(marker), "--now", "2026-09-06T18:03:11-04:00"])
    assert rc == 1  # RUN -- nothing marked done yet
    assert not marker.exists()
    out = capsys.readouterr().out
    assert "RUN 2026-W36" in out


# --------------------------------------------------------------------------------------- #
# CLI: check exits 0 (SKIP) when done, 1 (RUN) when stale/missing.
# --------------------------------------------------------------------------------------- #
def test_cli_check_exits_0_and_prints_skip_when_current_week_done(tmp_path, capsys):
    marker = tmp_path / "weekly-review-done.json"
    marker.write_text(json.dumps({
        "week_iso": "2026-W36",
        "generated_et": "2026-09-06T18:03:11-04:00",
        "artifact_path": "analysis/weekly/2026-W36.md",
    }), encoding="utf-8")
    rc = wrm.main(["check", "--marker", str(marker), "--now", "2026-09-06T20:00:00-04:00"])
    assert rc == 0
    assert "SKIP already-done 2026-W36" in capsys.readouterr().out


def test_cli_check_exits_1_and_prints_run_when_marker_missing(tmp_path, capsys):
    marker = tmp_path / "weekly-review-done.json"
    rc = wrm.main(["check", "--marker", str(marker), "--now", "2026-09-06T20:00:00-04:00"])
    assert rc == 1
    assert "RUN 2026-W36" in capsys.readouterr().out


def test_cli_check_exits_1_when_marker_is_a_different_week(tmp_path, capsys):
    marker = tmp_path / "weekly-review-done.json"
    marker.write_text(json.dumps({
        "week_iso": "2026-W35",
        "generated_et": "2026-08-30T18:00:00-04:00",
        "artifact_path": "analysis/weekly/2026-W35.md",
    }), encoding="utf-8")
    rc = wrm.main(["check", "--marker", str(marker), "--now", "2026-09-06T20:00:00-04:00"])
    assert rc == 1


# --------------------------------------------------------------------------------------- #
# CLI: write records the current week and always exits 0.
# --------------------------------------------------------------------------------------- #
def test_cli_write_records_current_week_and_exits_0(tmp_path, capsys):
    marker = tmp_path / "weekly-review-done.json"
    rc = wrm.main([
        "write", "--marker", str(marker),
        "--now", "2026-09-06T18:03:11-04:00",
        "--artifact", "analysis/weekly/2026-W36.md",
    ])
    assert rc == 0
    on_disk = json.loads(marker.read_text(encoding="utf-8"))
    assert on_disk["week_iso"] == "2026-W36"
    assert on_disk["artifact_path"] == "analysis/weekly/2026-W36.md"
    assert "WROTE 2026-W36" in capsys.readouterr().out


def test_cli_write_then_check_skips(tmp_path, capsys):
    """End-to-end success path: write (simulating a completed LLM run), then check
    on a same-week retry -- must SKIP."""
    marker = tmp_path / "weekly-review-done.json"
    rc_write = wrm.main([
        "write", "--marker", str(marker),
        "--now", "2026-09-06T18:03:11-04:00",
        "--artifact", "analysis/weekly/2026-W36.md",
    ])
    assert rc_write == 0
    capsys.readouterr()  # drain

    rc_check = wrm.main(["check", "--marker", str(marker), "--now", "2026-09-06T18:20:00-04:00"])
    assert rc_check == 0
    assert "SKIP already-done 2026-W36" in capsys.readouterr().out


# --------------------------------------------------------------------------------------- #
# now_et -- naive override is treated as ET, not local/UTC.
# --------------------------------------------------------------------------------------- #
def test_now_et_naive_override_assumed_et():
    dt = wrm.now_et("2026-09-06T18:03:11")
    assert dt.tzinfo is not None
    assert wrm.iso_week_string(dt) == "2026-W36"
