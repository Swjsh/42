"""Guard for GOAL-SILENT-RIG-2026-09-05 R4b: presence_gate.py must be wired into both
conductor launchers' rail-0 gate, right after the existing budget precheck and before the
cross-fire lock, so a conductor fire (full Claude session + MCP children + subagent
fan-out) never spawns while J is at the keyboard or in a fullscreen app.

Same test strategy as test_conductor_gate_precheck.py (the rail-0 budget precheck's own
guard, which this wiring sits directly after): the real ===PRESENCE-GATE-BLOCK-START/END===
block is extracted VERBATIM from each run-conductor*.ps1 via its marker comments, with ONLY
the interpreter/script/outcome-recorder paths substituted for fixtures (exact,
count-asserted string substitution -- fails loudly, not silently, if the real file's shape
changes), pasted into a throwaway harness that dot-sources the real _shared.ps1, and
actually executed via powershell.exe. Never touches production state (conductor-outcomes.
jsonl, quiet-presence.json, or claude.exe) and never runs the real presence_gate.py against
the live machine's actual idle/fullscreen state -- the fixture gate script controls the
verdict directly.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "setup" / "scripts"
SHARED = SCRIPTS / "_shared.ps1"
RUN_CONDUCTOR = SCRIPTS / "run-conductor.ps1"
RUN_CONDUCTOR_WEEKEND = SCRIPTS / "run-conductor-weekend.ps1"

sys.path.insert(0, str(SCRIPTS))

START_MARKER = "# ===PRESENCE-GATE-BLOCK-START==="
END_MARKER = "# ===PRESENCE-GATE-BLOCK-END==="
RAIL0_END_MARKER = "# ===RAIL0-PRECHECK-BLOCK-END==="

_OLD_PY = r'Join-Path $projectRoot "backtest\.venv\Scripts\python.exe"'
_OLD_SCRIPT = r'Join-Path $projectRoot "setup\scripts\presence_gate.py"'
_OLD_OUTCOME_SCRIPT = r'"setup\scripts\conductor_outcome.py"'

MARKER_ENV_VAR = "PRESENCE_GATE_TEST_MARKER"
FELL_THROUGH_EXIT = 42


def _src(source: Path) -> str:
    return source.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Structural checks (fast, no subprocess) -- both wrappers, prove the wiring exists.
# --------------------------------------------------------------------------- #

def _assert_structural(source: Path, task_label: str) -> None:
    src = _src(source)
    assert src.count(START_MARKER) == 1, f"{source}: expected exactly one START marker"
    assert src.count(END_MARKER) == 1, f"{source}: expected exactly one END marker"
    start = src.index(START_MARKER)
    end = src.index(END_MARKER)
    assert start < end

    # Must sit right after the rail-0 budget precheck block, before the Claude spawn and
    # before the cross-fire lock (same architectural slot as the budget precheck itself).
    rail0_end = src.index(RAIL0_END_MARKER)
    assert rail0_end < start, "presence gate must run AFTER the rail-0 budget precheck"
    lock_pos = src.index("Enter-ConductorFireLock")
    invoke_pos = src.index("Invoke-ClaudeWithRetry")
    assert start < lock_pos < invoke_pos, (
        "presence gate must run before the cross-fire lock and before the Claude spawn")

    block = src[start:end]
    assert "presence_gate.py" in block
    assert "--conductor-check" in block
    assert "PRESENCE-SKIP" in block
    assert f'conductor: PRESENCE SKIP -- J at the box' in block
    assert "conductor_outcome.py" in block
    assert '"record"' in block
    assert "try {" in block and "} catch {" in block
    assert "failing OPEN" in block
    assert "Test-Path $presenceGatePy" in block
    assert "Test-Path $presenceGateScript" in block

    # exhausted/present branch never falls through to Invoke-ClaudeWithRetry
    present_idx = block.index("$presenceExitCode -eq 3")
    tail = block[present_idx:]
    close_brace = tail.index("\n}")
    branch_body = tail[:close_brace]
    assert "exit 0" in branch_body
    assert "Invoke-ClaudeWithRetry" not in branch_body


def test_run_conductor_structural_wiring():
    _assert_structural(RUN_CONDUCTOR, "conductor")


def test_run_conductor_weekend_structural_wiring():
    _assert_structural(RUN_CONDUCTOR_WEEKEND, "conductor-weekend")


# --------------------------------------------------------------------------- #
# Executed behavior -- extract the REAL block from each wrapper, swap interpreter/
# script/outcome-recorder paths for fixtures, and actually run it via powershell.exe.
# --------------------------------------------------------------------------- #

def _extract_block(source: Path) -> str:
    src = _src(source)
    start = src.index(START_MARKER)
    end = src.index(END_MARKER, start)
    return src[start:end]


def _substituted_block(source: Path, py_path: Path, script_path: Path,
                        outcome_script_path: Path) -> str:
    block = _extract_block(source)
    for needle in (_OLD_PY, _OLD_SCRIPT, _OLD_OUTCOME_SCRIPT):
        count = block.count(needle)
        assert count == 1, (
            f"expected exactly one occurrence of {needle!r} in the extracted presence-gate "
            f"block of {source}, found {count} -- its shape changed, update this test")
    block = block.replace(_OLD_PY, f'"{py_path}"')
    block = block.replace(_OLD_SCRIPT, f'"{script_path}"')
    block = block.replace(_OLD_OUTCOME_SCRIPT, f'"{outcome_script_path}"')
    return block


def _build_harness(tmp_path: Path, source: Path, py_path: Path, script_path: Path,
                    outcome_script_path: Path, harness_name: str) -> Path:
    block = _substituted_block(source, py_path, script_path, outcome_script_path)
    harness = tmp_path / harness_name
    text = (
        '$ErrorActionPreference = "Continue"\n'
        f'$projectRoot = "{ROOT}"\n'
        'Set-Location $projectRoot\n'
        f'. "{SHARED}"\n'
        '$task = "presence-gate-wiring-test"\n'
        + block + "\n"
        f'"FELL_THROUGH" | Out-File -FilePath $env:{MARKER_ENV_VAR} -Encoding utf8\n'
        f'exit {FELL_THROUGH_EXIT}\n'
    )
    harness.write_text(text, encoding="utf-8")
    return harness


def _run_harness(harness_path: Path, marker_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env[MARKER_ENV_VAR] = str(marker_path)
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(harness_path)],
        capture_output=True, text=True, timeout=60, env=env,
    )


_OUTCOME_RECORDER_FIXTURE = '''\
import sys
from pathlib import Path
sys.path.insert(0, r"{scripts_dir}")
import conductor_outcome as co

args = co._build_parser().parse_args(sys.argv[1:])
row = co.record(
    task_id=args.task_id,
    cost_usd=args.cost,
    items_drained=args.drained,
    items_added=args.added,
    lessons_shipped=args.lessons,
    tests_delta=args.tests_delta,
    regressions=args.regressions,
    note=args.note,
    fired_at=args.fired_at,
    outcomes_file=Path(r"{outcomes_file}"),
)
print(row)
'''


def _write_outcome_recorder_fixture(tmp_path: Path, outcomes_file: Path) -> Path:
    p = tmp_path / "fixture_conductor_outcome_recorder.py"
    p.write_text(
        _OUTCOME_RECORDER_FIXTURE.format(scripts_dir=str(SCRIPTS), outcomes_file=str(outcomes_file)),
        encoding="utf-8",
    )
    return p


_FIXTURE_GATE_PRESENT = 'import sys; print("PRESENT: fake fullscreen app"); sys.exit(3)\n'
_FIXTURE_GATE_CLEAR = 'import sys; print("CLEAR"); sys.exit(0)\n'

REAL_VENV_PY = ROOT / "backtest" / ".venv" / "Scripts" / "python.exe"


def _run_wiring_case(tmp_path: Path, source: Path, gate_body: str, harness_name: str):
    gate_fixture = tmp_path / "fixture_presence_gate.py"
    gate_fixture.write_text(gate_body, encoding="utf-8")

    outcomes_file = tmp_path / "conductor-outcomes.jsonl"
    outcome_fixture = _write_outcome_recorder_fixture(tmp_path, outcomes_file)

    harness = _build_harness(
        tmp_path, source,
        py_path=REAL_VENV_PY if REAL_VENV_PY.exists() else Path(sys.executable),
        script_path=gate_fixture,
        outcome_script_path=outcome_fixture,
        harness_name=harness_name,
    )
    marker_path = tmp_path / "marker.txt"
    result = _run_harness(harness, marker_path)
    return result, marker_path, outcomes_file


def test_real_venv_python_exists():
    """Sanity precondition -- if this fails, the executed tests below aren't testing the
    real interpreter path and every other executed test in this file is testing nothing."""
    assert REAL_VENV_PY.exists(), f"expected venv python at {REAL_VENV_PY}"


def test_run_conductor_blocks_spawn_when_gate_reports_present(tmp_path):
    result, marker_path, outcomes_file = _run_wiring_case(
        tmp_path, RUN_CONDUCTOR, _FIXTURE_GATE_PRESENT, "harness_present.ps1")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert not marker_path.exists(), "PRESENT verdict must exit before falling through to Invoke-ClaudeWithRetry"
    assert outcomes_file.exists(), "a PRESENCE-SKIP outcome row must be recorded"
    row_text = outcomes_file.read_text(encoding="utf-8")
    assert "PRESENCE-SKIP" in row_text


def test_run_conductor_allows_fallthrough_when_gate_reports_clear(tmp_path):
    result, marker_path, outcomes_file = _run_wiring_case(
        tmp_path, RUN_CONDUCTOR, _FIXTURE_GATE_CLEAR, "harness_clear.ps1")
    assert result.returncode == FELL_THROUGH_EXIT, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert marker_path.exists(), "CLEAR verdict must fall through past the presence gate"
    assert not outcomes_file.exists(), "no PRESENCE-SKIP row should be written on a CLEAR verdict"


def test_run_conductor_weekend_blocks_spawn_when_gate_reports_present(tmp_path):
    result, marker_path, outcomes_file = _run_wiring_case(
        tmp_path, RUN_CONDUCTOR_WEEKEND, _FIXTURE_GATE_PRESENT, "harness_weekend_present.ps1")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert not marker_path.exists()
    assert outcomes_file.exists()
    assert "PRESENCE-SKIP-WEEKEND" in outcomes_file.read_text(encoding="utf-8")


def test_run_conductor_weekend_allows_fallthrough_when_gate_reports_clear(tmp_path):
    result, marker_path, outcomes_file = _run_wiring_case(
        tmp_path, RUN_CONDUCTOR_WEEKEND, _FIXTURE_GATE_CLEAR, "harness_weekend_clear.ps1")
    assert result.returncode == FELL_THROUGH_EXIT, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert marker_path.exists()
    assert not outcomes_file.exists()


def test_presence_gate_missing_script_fails_open(tmp_path):
    """If presence_gate.py itself is missing (Test-Path guard), the block must fail open --
    fall through to Invoke-ClaudeWithRetry, never silently block the conductor forever."""
    missing_script = tmp_path / "does-not-exist.py"
    outcomes_file = tmp_path / "conductor-outcomes.jsonl"
    outcome_fixture = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(
        tmp_path, RUN_CONDUCTOR,
        py_path=REAL_VENV_PY if REAL_VENV_PY.exists() else Path(sys.executable),
        script_path=missing_script,
        outcome_script_path=outcome_fixture,
        harness_name="harness_missing.ps1",
    )
    marker_path = tmp_path / "marker.txt"
    result = _run_harness(harness, marker_path)
    assert result.returncode == FELL_THROUGH_EXIT, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert marker_path.exists(), "a missing presence_gate.py must fail OPEN, not block the fire"
    assert not outcomes_file.exists()
