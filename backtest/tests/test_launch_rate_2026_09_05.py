"""Guard (GOAL-SILENT-RIG-2026-09-05 L3): setup/scripts/launch_rate.py.

Pins the parsing/aggregation contract against a fixture pair of hidden-launcher
logs (never the live automation/state/logs/*.log) and the Known-broken flagging
path against a tmp STATUS.md (never the live one -- see status_known_broken's
own test suite for why).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import launch_rate as lr  # noqa: E402

DATE = "2099-01-02"


def _write_fixture_logs(tmp_path: Path, date: str) -> Path:
    log_dir = tmp_path / "automation" / "state" / "logs"
    log_dir.mkdir(parents=True)

    ps1_lines = [
        f"[{date} 00:00:00] launching: run-kitchen-daemon-keepalive.ps1 args=[]",
        f"[{date} 00:00:00] launching: run-engine-health.ps1 args=[]",
        f"[{date} 00:01:00] launching: run-engine-health.ps1 args=[]",
        f"[{date} 03:00:00]   run-engine-health.ps1 exit=0",  # non-launching line, ignored
        f"[{date} 08:00:00] launching: run-sight-beacon.ps1 args=[]",  # market-open hour
    ]
    (log_dir / f"run-ps1-hidden-{date}.log").write_text("\n".join(ps1_lines) + "\n", encoding="utf-8")

    cmd_lines = [
        f"[{date} 00:00:01] launching: C:\\Python\\pythonw.exe C:\\42\\setup\\scripts\\state_freshness_remediate.py  [pid=1]",
        f"[{date} 02:00:00] launching: C:\\42\\backtest\\.venv\\Scripts\\pythonw.exe C:\\42\\setup\\scripts\\futures_health.py  [pid=2]",
        f"[{date} 02:00:05] launching: C:\\Python\\pythonw.exe C:\\42\\setup\\scripts\\run_cmd_hidden.py --env X -- C:\\Python\\pythonw.exe C:\\42\\setup\\scripts\\auto_commit_candidates.py  [pid=3]",
    ]
    (log_dir / f"run-cmd-hidden-{date}.log").write_text("\n".join(cmd_lines) + "\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------

def test_extract_script_ps1():
    assert lr._extract_script("run-engine-health.ps1 args=[]") == "run-engine-health.ps1"


def test_extract_script_cmd_prefers_real_target_over_wrapper():
    tail = (
        "C:\\Python\\pythonw.exe C:\\42\\setup\\scripts\\run_cmd_hidden.py --env X -- "
        "C:\\Python\\pythonw.exe C:\\42\\setup\\scripts\\auto_commit_candidates.py  [pid=3]"
    )
    assert lr._extract_script(tail) == "auto_commit_candidates.py"


def test_extract_script_cmd_single_target():
    tail = "C:\\42\\backtest\\.venv\\Scripts\\pythonw.exe C:\\42\\setup\\scripts\\futures_health.py  [pid=2]"
    assert lr._extract_script(tail) == "futures_health.py"


# ---------------------------------------------------------------------------
# compute() aggregation
# ---------------------------------------------------------------------------

def test_compute_per_hour_and_top_scripts(tmp_path):
    root = _write_fixture_logs(tmp_path, DATE)
    result = lr.compute(DATE, repo_root=root)

    assert result["date"] == DATE
    assert result["total_launches"] == 7  # 4 ps1 "launching:" + 3 cmd (1 non-launching ps1 line excluded)
    assert result["per_hour"]["00"] == 4  # 3 ps1 (2x00:00 + 1x00:01) + 1 cmd (00:00:01)
    assert result["per_hour"]["02"] == 2
    assert result["per_hour"]["08"] == 1
    assert len(result["per_hour"]) == 24  # all hours present, zero-filled

    top = dict(result["top_scripts"])
    assert top["run-engine-health.ps1"] == 2
    assert top["auto_commit_candidates.py"] == 1


def test_market_closed_hours_over_60_flags_only_off_session_hours(tmp_path):
    root = _write_fixture_logs(tmp_path, DATE)
    log_dir = root / "automation" / "state" / "logs"
    # Pump hour 03 (market-closed, local) over the 60 threshold.
    extra = [f"[{DATE} 03:00:0{i % 10}] launching: run-spam.ps1 args=[]" for i in range(65)]
    with (log_dir / f"run-ps1-hidden-{DATE}.log").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(extra) + "\n")

    result = lr.compute(DATE, repo_root=root)
    assert "03" in result["market_closed_hours_over_60"]
    assert "08" not in result["market_closed_hours_over_60"]  # market-open hour, never flagged


def test_write_output_writes_json(tmp_path):
    root = _write_fixture_logs(tmp_path, DATE)
    result = lr.compute(DATE, repo_root=root)
    out_path = lr.write_output(result, repo_root=root)
    assert out_path.exists()
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["date"] == DATE


def test_missing_logs_return_zero_not_raise(tmp_path):
    result = lr.compute("2099-12-31", repo_root=tmp_path)
    assert result["total_launches"] == 0
    assert all(v == 0 for v in result["per_hour"].values())


# ---------------------------------------------------------------------------
# Known-broken flagging via the shared upsert helper, on a tmp STATUS.md only
# ---------------------------------------------------------------------------

def test_maybe_flag_known_broken_writes_marker_on_breach(tmp_path):
    root = _write_fixture_logs(tmp_path, DATE)
    log_dir = root / "automation" / "state" / "logs"
    extra = [f"[{DATE} 03:00:0{i % 10}] launching: run-spam.ps1 args=[]" for i in range(65)]
    with (log_dir / f"run-ps1-hidden-{DATE}.log").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(extra) + "\n")

    tmp_status = tmp_path / "STATUS.md"
    tmp_status.write_text("## Known broken\n\n", encoding="utf-8")

    result = lr.compute(DATE, repo_root=root)
    changed = lr.maybe_flag_known_broken(result, repo_root=root, status_path=tmp_status)
    assert changed is True
    body = tmp_status.read_text(encoding="utf-8")
    assert "LAUNCH-RATE:" in body


def test_maybe_flag_known_broken_clears_marker_when_clean(tmp_path):
    root = _write_fixture_logs(tmp_path, DATE)  # no breach in the base fixture
    tmp_status = tmp_path / "STATUS.md"
    tmp_status.write_text(
        "## Known broken\n\n- [old] LAUNCH-RATE: stale breach\n", encoding="utf-8"
    )

    result = lr.compute(DATE, repo_root=root)
    assert result["market_closed_hours_over_60"] == []
    lr.maybe_flag_known_broken(result, repo_root=root, status_path=tmp_status)
    body = tmp_status.read_text(encoding="utf-8")
    assert "LAUNCH-RATE:" not in body
