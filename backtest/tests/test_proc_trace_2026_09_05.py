"""Guard for GOAL-SILENT-RIG-2026-09-05 R4a: setup/scripts/proc_trace.py.

proc_trace.py's real subscription lives entirely in a hidden PowerShell child
(proc_trace_watcher.ps1's Register-CimIndicationEvent) -- this file's own Python surface is
deliberately just: parse one JSON line from that child, decide whether today's rotated
output file is under its 20MB cap, append a row, and loop. Every one of those is a pure
function driven here with fixture text; no real powershell.exe/CIM subscription is ever
spawned by this test file.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import proc_trace as pt  # noqa: E402


@pytest.fixture(autouse=True)
def _redirect_runner_log_to_tmp(tmp_path, monkeypatch):
    """R4c-lesson applied here too: run_watcher_loop's own error path calls _runner_log,
    which by default writes to the REAL automation/state/logs/proc-trace-runner-<date>.log.
    Tests must never write to real files under automation/state (the exact bug this same
    GOAL-SILENT-RIG session already found and fixed in
    test_window_leak_hook_attribution_2026_09_05.py) -- redirect both log/pid paths here."""
    monkeypatch.setattr(pt, "RUNNER_LOG_FILE", tmp_path / "proc-trace-runner-test.log")
    monkeypatch.setattr(pt, "PID_FILE", tmp_path / "proc-trace-test.pid")


_VALID_ROW = {
    "ts_local": 1_757_000_000_000,
    "pid": 4242,
    "ppid": 1,
    "name": "wscript.exe",
    "cmdline": r"wscript.exe //nologo run_exe_hidden.vbs",
    "parent_name": "explorer.exe",
    "parent_cmdline": r"C:\Windows\explorer.exe",
    "session_id": 1,
}


# ---------------------------------------------------------------------------
# _parse_trace_line
# ---------------------------------------------------------------------------

def test_parse_valid_line_roundtrips_all_fields():
    line = json.dumps(_VALID_ROW)
    row = pt._parse_trace_line(line)
    assert row is not None
    for k in pt.REQUIRED_FIELDS:
        assert k in row


def test_parse_blank_line_is_none():
    assert pt._parse_trace_line("") is None
    assert pt._parse_trace_line("   \n") is None


def test_parse_malformed_json_is_none_not_raise():
    assert pt._parse_trace_line("{not json") is None


def test_parse_non_object_json_is_none():
    assert pt._parse_trace_line("[1, 2, 3]") is None
    assert pt._parse_trace_line('"just a string"') is None


def test_parse_missing_required_field_is_none():
    bad = dict(_VALID_ROW)
    del bad["ppid"]
    assert pt._parse_trace_line(json.dumps(bad)) is None


def test_parse_null_parent_fields_become_none():
    row = dict(_VALID_ROW)
    row["parent_name"] = None
    row["parent_cmdline"] = None
    parsed = pt._parse_trace_line(json.dumps(row))
    assert parsed is not None
    assert parsed["parent_name"] is None
    assert parsed["parent_cmdline"] is None


def test_parse_non_numeric_pid_is_none():
    bad = dict(_VALID_ROW)
    bad["pid"] = "not-a-number"
    assert pt._parse_trace_line(json.dumps(bad)) is None


# ---------------------------------------------------------------------------
# _log_path_for_date / _within_cap / write_trace_row
# ---------------------------------------------------------------------------

def test_log_path_for_date_is_daily_rotated(tmp_path):
    p1 = pt._log_path_for_date(dt.date(2026, 9, 5), log_dir=tmp_path)
    p2 = pt._log_path_for_date(dt.date(2026, 9, 6), log_dir=tmp_path)
    assert p1 != p2
    assert p1.name == "proc-trace-2026-09-05.jsonl"


def test_within_cap_true_for_missing_file(tmp_path):
    assert pt._within_cap(tmp_path / "nope.jsonl", cap_bytes=100) is True


def test_within_cap_false_once_file_at_cap(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_bytes(b"x" * 200)
    assert pt._within_cap(p, cap_bytes=100) is False
    assert pt._within_cap(p, cap_bytes=1000) is True


def test_write_trace_row_appends_one_json_line(tmp_path):
    row = pt._parse_trace_line(json.dumps(_VALID_ROW))
    path = pt.write_trace_row(row, log_dir=tmp_path, today=dt.date(2026, 9, 5))
    assert path is not None
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["pid"] == 4242


def test_write_trace_row_bite_stops_once_capped(tmp_path):
    """NON-VACUOUS BITE: with a tiny cap, the SECOND write must be dropped (return None)
    while the first still lands -- proves the cap is actually enforced, not just present."""
    row = pt._parse_trace_line(json.dumps(_VALID_ROW))
    cap = len(json.dumps(row, separators=(",", ":"))) + 1  # room for exactly one row + \n
    first = pt.write_trace_row(row, log_dir=tmp_path, cap_bytes=cap, today=dt.date(2026, 9, 5))
    second = pt.write_trace_row(row, log_dir=tmp_path, cap_bytes=cap, today=dt.date(2026, 9, 5))
    assert first is not None
    assert second is None, "a write past the cap must be silently dropped, not grow the file"
    lines = first.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_write_trace_row_rotates_across_days(tmp_path):
    row = pt._parse_trace_line(json.dumps(_VALID_ROW))
    p1 = pt.write_trace_row(row, log_dir=tmp_path, today=dt.date(2026, 9, 5))
    p2 = pt.write_trace_row(row, log_dir=tmp_path, today=dt.date(2026, 9, 6))
    assert p1 != p2
    assert p1.exists() and p2.exists()


# ---------------------------------------------------------------------------
# run_watcher_loop -- fixture lines, no real subprocess
# ---------------------------------------------------------------------------

def test_bite_run_watcher_loop_writes_only_valid_lines(tmp_path):
    """NON-VACUOUS BITE: a mix of one valid line, one blank line, and one malformed line
    must write exactly one row and not raise."""
    lines = [json.dumps(_VALID_ROW), "", "{not json"]
    written = []

    def _fake_write(row):
        written.append(row)
        return tmp_path / "fake.jsonl"

    count = pt.run_watcher_loop(lines, write_fn=_fake_write)
    assert count == 1
    assert len(written) == 1
    assert written[0]["pid"] == 4242


def test_run_watcher_loop_returns_zero_for_all_invalid_lines():
    count = pt.run_watcher_loop(["", "not json", "{}"], write_fn=lambda row: Path("x"))
    assert count == 0


def test_run_watcher_loop_survives_write_fn_exception():
    """A write failure for one line must never stop the loop from processing the next."""
    lines = [json.dumps(_VALID_ROW), json.dumps(_VALID_ROW)]
    calls = []

    def _raising_write(row):
        calls.append(row)
        if len(calls) == 1:
            raise RuntimeError("disk full")
        return Path("ok")

    count = pt.run_watcher_loop(lines, write_fn=_raising_write)
    assert len(calls) == 2, "second line must still be attempted after the first raised"
    assert count == 1


def test_run_watcher_loop_respects_stop_check():
    lines = [json.dumps(_VALID_ROW)] * 10
    seen = []

    def _write(row):
        seen.append(row)
        return Path("ok")

    count = pt.run_watcher_loop(lines, write_fn=_write, stop_check=lambda: len(seen) >= 3)
    assert count == 3, "loop must stop as soon as stop_check() returns True"
