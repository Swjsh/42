"""Guards for the CONDUCTOR-GATE-PRECHECK fix (2026-08-08).

THE FINDING (analysis/recommendations/conductor-cost-correction-measurement-2026-08-08.md,
section "Near-zero-self-report fires"): the conductor's rail-0 budget gate
(setup/scripts/conductor_budget.py --check) used to run INSIDE the spawned Claude session --
automation/prompts/conductor.md's STAGE 0, step 0. setup/scripts/run-conductor.ps1 spawned
the Claude session FIRST (Invoke-ClaudeWithRetry), with no pre-check of its own. So every
gated-out (EXHAUSTED) fire still booted a full Claude session that read CLAUDE.md +
conductor.md + the gamma agent's whole MCP tool surface, evaluated the gate, and exited --
measured ~$1.25 of real token cost each across n=54 such no-op fires, every one of them
self-reporting ~$0 (0 x any correction factor is still 0 -- a purely multiplicative fix, like
the SELF_REPORT_CORRECTION re-measurement in test_conductor_budget.py, structurally cannot
catch this class of waste).

THE FIX: run-conductor.ps1 now runs the IDENTICAL conductor_budget.py --check (via the
backtest venv python) BEFORE Invoke-ClaudeWithRetry, in the same architectural slot as rail
1's market-hours gate (before the cross-fire lock, so an EXHAUSTED fire never even touches
the lock file). Exit code 3 -> records a schema-compatible outcomes row + a log line + exits
0 WITHOUT spawning Claude. Any other outcome (proceed, missing interpreter/script, thrown
exception, timeout) FAILS OPEN and falls through to the unchanged Invoke-ClaudeWithRetry call
-- a broken meter must never silence the autonomous loop (that would be a worse bug than the
one being fixed here).

conductor.md's in-prompt STAGE 0 gate is UNCHANGED in mechanism (kept as a belt-and-braces
second check -- see test_conductor_budget.py's prose-pin tests for its updated wording) and
remains the ONLY gate for Gamma_ConductorWeekend (run-conductor-weekend.ps1, a separate
wrapper, out of this fix's authorized surface).

TEST STRATEGY (why this file does NOT just subprocess the real run-conductor.ps1 end-to-end):
- The real script re-sources _shared.ps1 (which unconditionally resets $Global:ClaudeExe),
  so a caller-side stub/override of Invoke-ClaudeWithRetry or $Global:ClaudeExe would be
  silently stomped -- there is no clean way to intercept "would Claude have been spawned"
  from outside the file.
- The real script's rail-1 market-hours gate depends on the WALL CLOCK (Get-EtNow) -- a test
  that runs the whole file would be non-deterministic across time of day.
- Worst of all: if conductor_budget.py's real, LIVE, on-disk verdict happens to be PROCEED
  when this suite runs, subprocessing the unmodified real script would spawn an ACTUAL
  claude.exe session against the real conductor.md prompt -- a real dollar cost and a real
  autonomous action taken by a test suite. That is never acceptable.
Instead: the real rail-0 pre-check block is extracted VERBATIM from run-conductor.ps1 (via
the ===RAIL0-PRECHECK-BLOCK-START/END=== marker comments the block is wrapped in), with ONLY
the interpreter path / gate-script path / outcome-recorder script path / wait-timeout swapped
for test fixtures via exact, count-asserted string substitution (so this test fails LOUDLY,
not silently, if run-conductor.ps1's shape ever changes underneath it). The substituted block
is pasted into a throwaway harness .ps1 (dot-sources the real _shared.ps1, same as the real
file) that appends one sentinel write + a distinctive exit code AFTER the pasted block, so
"did execution fall through past the gate" is directly observable without ever touching real
production state (conductor-outcomes.jsonl, STATUS.md, or claude.exe).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "setup" / "scripts"
SHARED = SCRIPTS / "_shared.ps1"
RUN_CONDUCTOR = SCRIPTS / "run-conductor.ps1"
RUN_CONDUCTOR_WEEKEND = SCRIPTS / "run-conductor-weekend.ps1"
CONDUCTOR_MD = ROOT / "automation" / "prompts" / "conductor.md"

sys.path.insert(0, str(SCRIPTS))

START_MARKER = "# ===RAIL0-PRECHECK-BLOCK-START==="
END_MARKER = "# ===RAIL0-PRECHECK-BLOCK-END==="

# The exact literal snippets the real block contains -- substituted for fixtures below. Kept
# as raw strings so Windows backslashes in the real file are matched byte-for-byte.
_OLD_PY = r'Join-Path $projectRoot "backtest\.venv\Scripts\python.exe"'
_OLD_SCRIPT = r'Join-Path $projectRoot "setup\scripts\conductor_budget.py"'
_OLD_WAIT = "WaitForExit(30000)"
_OLD_OUTCOME_SCRIPT = r'"setup\scripts\conductor_outcome.py"'

MARKER_ENV_VAR = "PRECHECK_TEST_MARKER"
FELL_THROUGH_EXIT = 42


# --------------------------------------------------------------------------- #
# Structural checks (fast, no subprocess) -- prove the wiring exists at all.
# --------------------------------------------------------------------------- #

def _run_conductor_src(source: Path = RUN_CONDUCTOR) -> str:
    return source.read_text(encoding="utf-8")


def test_precheck_markers_present_exactly_once():
    src = _run_conductor_src()
    assert src.count(START_MARKER) == 1
    assert src.count(END_MARKER) == 1
    assert src.index(START_MARKER) < src.index(END_MARKER)


def test_precheck_block_runs_before_invoke_claude_with_retry():
    """The whole point: the gate must be positioned BEFORE the Claude spawn, not after."""
    src = _run_conductor_src()
    precheck_pos = src.index(START_MARKER)
    invoke_pos = src.index("Invoke-ClaudeWithRetry")
    assert precheck_pos < invoke_pos, (
        "rail-0 pre-check block must appear before the Invoke-ClaudeWithRetry call site")


def test_precheck_block_before_cross_fire_lock():
    """Same architectural slot as rail 1 (market-hours gate): a gate that decides not to
    run should never touch the cross-fire lock file first."""
    src = _run_conductor_src()
    precheck_pos = src.index(START_MARKER)
    lock_pos = src.index("Enter-ConductorFireLock")
    assert precheck_pos < lock_pos


def test_precheck_calls_the_real_conductor_budget_check():
    block = _extract_precheck_block()
    assert "conductor_budget.py" in block
    assert "--check" in block
    assert "backtest\\.venv\\Scripts\\python.exe" in block


def test_precheck_exhausted_branch_exits_without_reaching_claude():
    block = _extract_precheck_block()
    exhausted_idx = block.index("$precheckExitCode -eq 3")
    tail = block[exhausted_idx:]
    # The exhausted branch's own closing brace must contain an `exit 0` before it -- i.e.
    # this branch never falls through to any later code (which is where Invoke-ClaudeWithRetry
    # lives, outside this extracted block entirely).
    close_brace = tail.index("\n}")
    branch_body = tail[:close_brace]
    assert "exit 0" in branch_body
    assert "Invoke-ClaudeWithRetry" not in branch_body


def test_precheck_records_outcome_via_conductor_outcome_py():
    block = _extract_precheck_block()
    assert "conductor_outcome.py" in block
    assert '"record"' in block
    assert "--task-id" in block and "--note" in block


def test_precheck_note_and_task_id_contain_budget_marker():
    """autonomy_report.py's classify_noop_reason() buckets a row as budget_exhausted iff
    "budget" appears (case-insensitive) anywhere in task_id/note -- the precheck's recorded
    row must actually classify correctly, not just LOOK like it does."""
    block = _extract_precheck_block()
    task_id_line = [ln for ln in block.splitlines() if "preTaskId" in ln and "=" in ln][0]
    note_line = [ln for ln in block.splitlines() if "preNote" in ln and "=" in ln][0]
    assert "budget" in task_id_line.lower()
    assert "budget" in note_line.lower()


def test_precheck_wraps_process_start_in_try_catch_for_fail_open():
    block = _extract_precheck_block()
    assert "try {" in block and "} catch {" in block
    assert "failing OPEN" in block


def test_precheck_guards_missing_interpreter_and_script_with_test_path():
    block = _extract_precheck_block()
    assert "Test-Path $budgetPrecheckPy" in block
    assert "Test-Path $budgetPrecheckScript" in block


# --------------------------------------------------------------------------- #
# Executed behavior -- extract the REAL block, swap only interpreter/script/
# outcome-recorder paths + wait timeout for fixtures, and actually run it.
# --------------------------------------------------------------------------- #

def _extract_precheck_block(source: Path = RUN_CONDUCTOR) -> str:
    src = _run_conductor_src(source)
    start = src.index(START_MARKER)
    end = src.index(END_MARKER, start)
    return src[start:end]


def _substituted_block(py_path: Path, script_path: Path, outcome_script_path: Path,
                        wait_ms: int, source: Path = RUN_CONDUCTOR) -> str:
    block = _extract_precheck_block(source)
    for needle in (_OLD_PY, _OLD_SCRIPT, _OLD_WAIT, _OLD_OUTCOME_SCRIPT):
        count = block.count(needle)
        assert count == 1, (
            f"expected exactly one occurrence of {needle!r} in the extracted rail-0 "
            f"pre-check block of {source}, found {count} -- its shape changed, "
            f"update this test's substitution targets to match")
    block = block.replace(_OLD_PY, f'"{py_path}"')
    block = block.replace(_OLD_SCRIPT, f'"{script_path}"')
    block = block.replace(_OLD_WAIT, f"WaitForExit({wait_ms})")
    block = block.replace(_OLD_OUTCOME_SCRIPT, f'"{outcome_script_path}"')
    return block


def _build_harness(tmp_path: Path, py_path: Path, script_path: Path,
                    outcome_script_path: Path, wait_ms: int = 2000,
                    source: Path = RUN_CONDUCTOR, harness_name: str = "harness.ps1") -> Path:
    block = _substituted_block(py_path, script_path, outcome_script_path, wait_ms, source)
    harness = tmp_path / harness_name
    text = (
        '$ErrorActionPreference = "Continue"\n'
        f'$projectRoot = "{ROOT}"\n'
        'Set-Location $projectRoot\n'
        f'. "{SHARED}"\n'
        '$task = "conductor-gate-precheck-test"\n'
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


def _write_gate_fixture(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


REAL_VENV_PY = ROOT / "backtest" / ".venv" / "Scripts" / "python.exe"


def test_real_venv_python_exists():
    """Sanity precondition for every executed test below -- if this fails, the fixtures
    that use the REAL venv interpreter (as opposed to the fixture gate SCRIPT) cannot run
    meaningfully and every other executed test in this file would be testing nothing."""
    assert REAL_VENV_PY.exists(), f"expected backtest venv python at {REAL_VENV_PY}"


def test_precheck_blocks_spawn_when_gate_reports_exhausted(tmp_path):
    gate = _write_gate_fixture(tmp_path, "gate_exhausted.py", "import sys\nsys.exit(3)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, REAL_VENV_PY, gate, recorder)
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)

    assert result.returncode == 0, (
        f"exhausted precheck must exit 0 (blocked), not fall through -- "
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    assert not marker.exists(), (
        "the FELL_THROUGH sentinel must never be written -- this proves the script never "
        "reached the line where Invoke-ClaudeWithRetry would have been called")


def test_precheck_allows_spawn_when_gate_reports_proceed(tmp_path):
    gate = _write_gate_fixture(tmp_path, "gate_proceed.py", "import sys\nsys.exit(0)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, REAL_VENV_PY, gate, recorder)
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)

    assert result.returncode == FELL_THROUGH_EXIT, (
        f"a PROCEED gate must fall through unchanged -- stdout={result.stdout!r} "
        f"stderr={result.stderr!r}")
    # PowerShell 5.1's Out-File -Encoding utf8 writes a BOM -- strip it before comparing.
    assert marker.exists()
    assert marker.read_text(encoding="utf-8-sig").strip() == "FELL_THROUGH"
    # PROCEED must never write an outcome row -- only the EXHAUSTED branch does.
    assert not outcomes_file.exists()


def test_precheck_fails_open_on_timeout(tmp_path):
    """A gate subprocess that never exits must not hang the conductor forever -- it must
    be killed and treated as fail-open (fall through), within the (shortened, for test
    speed) wait window, not the sleeping gate's own duration."""
    gate = _write_gate_fixture(tmp_path, "gate_hangs.py", "import time\ntime.sleep(20)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, REAL_VENV_PY, gate, recorder, wait_ms=1500)
    marker = tmp_path / "marker.txt"

    started = time.time()
    result = _run_harness(harness, marker)
    elapsed = time.time() - started

    assert result.returncode == FELL_THROUGH_EXIT, (
        f"a timed-out precheck must fail OPEN (fall through) -- stdout={result.stdout!r} "
        f"stderr={result.stderr!r}")
    assert marker.exists()
    assert elapsed < 15, (
        f"took {elapsed:.1f}s -- the shortened 1.5s WaitForExit should have fired well "
        f"before the fixture gate's 20s sleep; a full wait means the timeout didn't apply")


def test_precheck_fails_open_when_process_start_throws(tmp_path):
    """A 'python.exe' that exists on disk but is not a valid executable (e.g. a plain text
    file) makes Process.Start throw -- must be caught and fail OPEN, not crash the wrapper."""
    not_an_exe = tmp_path / "not_really_python.exe"
    not_an_exe.write_text("this is not a valid win32 executable", encoding="utf-8")
    gate = _write_gate_fixture(tmp_path, "gate_unused.py", "import sys\nsys.exit(3)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, not_an_exe, gate, recorder)
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)

    assert result.returncode == FELL_THROUGH_EXIT, (
        f"a Process.Start exception must fail OPEN -- stdout={result.stdout!r} "
        f"stderr={result.stderr!r}")
    assert marker.exists()


def test_precheck_fails_open_when_gate_script_missing(tmp_path):
    missing_script = tmp_path / "does_not_exist.py"
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, REAL_VENV_PY, missing_script, recorder)
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)

    assert result.returncode == FELL_THROUGH_EXIT, (
        f"a missing gate script must fail OPEN (Test-Path guard) -- stdout={result.stdout!r} "
        f"stderr={result.stderr!r}")
    assert marker.exists()


def test_precheck_fails_open_when_interpreter_missing(tmp_path):
    missing_py = tmp_path / "no_such_python.exe"
    gate = _write_gate_fixture(tmp_path, "gate_unused2.py", "import sys\nsys.exit(3)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, missing_py, gate, recorder)
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)

    assert result.returncode == FELL_THROUGH_EXIT, (
        f"a missing interpreter must fail OPEN (Test-Path guard) -- stdout={result.stdout!r} "
        f"stderr={result.stderr!r}")
    assert marker.exists()


# --------------------------------------------------------------------------- #
# Requirement 5: the exhausted path's outcome row must be schema-valid AND
# parse cleanly through autonomy_report.py (the actual downstream consumer).
# --------------------------------------------------------------------------- #

def test_exhausted_path_writes_schema_valid_outcome_row(tmp_path):
    gate = _write_gate_fixture(tmp_path, "gate_exhausted.py", "import sys\nsys.exit(3)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, REAL_VENV_PY, gate, recorder)
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    assert outcomes_file.exists(), (
        f"the exhausted branch must write an outcome row -- "
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    lines = [ln for ln in outcomes_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])

    # Same required fields every real row in the production ledger carries (see
    # conductor_outcome.record()'s row dict + the real ledger samples quoted in
    # test_conductor_budget.py / the measurement doc).
    for field in ("fired_at", "task_id", "cost_usd", "items_drained", "items_added",
                  "lessons_shipped", "tests_delta", "regressions", "note", "trading_day",
                  "enters_last_trading_day", "orders_accepted",
                  "extra_exec_orders_accepted", "fills", "distinct_setups_traded"):
        assert field in row, f"missing field {field!r} in precheck outcome row: {row}"

    assert row["cost_usd"] == 0.0, "precheck-blocked fire genuinely cost $0 real -- no LLM ran"
    assert row["items_drained"] == 0
    assert row["lessons_shipped"] == 0
    assert "budget" in row["task_id"].lower()
    assert "budget" in row["note"].lower()


def test_exhausted_outcome_row_parses_via_autonomy_report(tmp_path):
    """The row must not just be valid JSON -- it must classify correctly through the ACTUAL
    downstream consumer, autonomy_report.py, as a no-op / budget_exhausted event with zero
    ship credit (never mistaken for real work)."""
    gate = _write_gate_fixture(tmp_path, "gate_exhausted.py", "import sys\nsys.exit(3)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, REAL_VENV_PY, gate, recorder)
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert outcomes_file.exists()

    import autonomy_report as ar

    rows = ar.load_outcomes(outcomes_file)
    assert len(rows) == 1, f"autonomy_report.load_outcomes() choked on the row: {rows}"
    row = rows[0]

    assert ar.is_ship_event(row) is False, "a precheck-blocked no-op must never read as a ship event"
    assert ar.classify_noop_reason(row) == "budget_exhausted", (
        f"expected budget_exhausted classification, got {ar.classify_noop_reason(row)!r} "
        f"for row {row}")

    et_date = ar._row_et_date(row)
    assert et_date is not None, f"autonomy_report could not derive an ET date from {row}"

    report = ar.compute_report(rows, None, dict(ar._BUDGET_DEFAULTS), et_date)
    assert report["today"]["total_fires"] == 1
    assert report["today"]["ship_fires"] == 0
    assert report["today"]["noop_reasons"]["budget_exhausted"] == 1
    assert "budget-starved" in report["today"]["verdict"]


# --------------------------------------------------------------------------- #
# LANE 1 (2026-08-08): run-conductor-weekend.ps1 port coverage. Same block
# shape, same marker comments, same substitution targets (_OLD_PY/_OLD_SCRIPT/
# _OLD_WAIT/_OLD_OUTCOME_SCRIPT) as the weekday file -- these tests reuse the
# generalized `source=` param on the extraction/harness helpers above rather
# than duplicating them. Executed scenarios only (structural greps for marker
# position/wiring are the SAME shape as the weekday tests above and would be
# redundant here); this section proves the actual behavior: exhausted blocks
# the spawn, under-budget allows it, a precheck error falls through, and the
# recorded outcome row is schema-valid AND classifies correctly.
# --------------------------------------------------------------------------- #

def _weekend_src() -> str:
    return _run_conductor_src(RUN_CONDUCTOR_WEEKEND)


def test_weekend_precheck_markers_present_exactly_once():
    src = _weekend_src()
    assert src.count(START_MARKER) == 1
    assert src.count(END_MARKER) == 1
    assert src.index(START_MARKER) < src.index(END_MARKER)


def test_weekend_precheck_block_runs_before_invoke_claude_with_retry():
    src = _weekend_src()
    precheck_pos = src.index(START_MARKER)
    invoke_pos = src.index("Invoke-ClaudeWithRetry")
    assert precheck_pos < invoke_pos, (
        "weekend rail-0 pre-check block must appear before the Invoke-ClaudeWithRetry call site")


def test_weekend_precheck_block_before_cross_fire_lock():
    """Same architectural slot as the weekend wrapper's own weekday-only gate: a gate that
    decides not to run should never touch the (shared) cross-fire lock file first."""
    src = _weekend_src()
    precheck_pos = src.index(START_MARKER)
    lock_pos = src.index("Enter-ConductorFireLock")
    assert precheck_pos < lock_pos


def test_weekend_precheck_block_after_weekday_only_gate():
    """LANE 1 structural difference vs run-conductor.ps1: this wrapper's own
    'should this fire run at all' gate is Test-WeekDay (weekend-only), not a market-hours
    check -- the precheck must sit AFTER that gate, in the same slot rail-1 occupies in
    the weekday file."""
    src = _weekend_src()
    gate_pos = src.index("if (Test-WeekDay -Et $et) {")
    precheck_pos = src.index(START_MARKER)
    assert gate_pos < precheck_pos


def test_weekend_precheck_note_and_task_id_contain_budget_marker():
    block = _extract_precheck_block(RUN_CONDUCTOR_WEEKEND)
    task_id_line = [ln for ln in block.splitlines() if "preTaskId" in ln and "=" in ln][0]
    note_line = [ln for ln in block.splitlines() if "preNote" in ln and "=" in ln][0]
    assert "budget" in task_id_line.lower()
    assert "budget" in note_line.lower()


def test_weekend_precheck_task_id_tagged_weekend_for_attribution():
    """LANE 1 step 6 needs to distinguish weekend-attributable precheck-blocked rows from
    weekday ones in conductor-outcomes.jsonl -- the recorded task-id must carry a WEEKEND
    tag, not just be a byte-identical copy of the weekday task-id."""
    block = _extract_precheck_block(RUN_CONDUCTOR_WEEKEND)
    task_id_line = [ln for ln in block.splitlines() if "preTaskId" in ln and "=" in ln][0]
    assert "WEEKEND" in task_id_line


def test_weekend_precheck_uses_kill_not_kill_tree_and_wait_before_read():
    """Both bug fixes from the reference block must be present, not reintroduced. The
    block's own explanatory comments legitimately MENTION 'Kill($true)' as the thing NOT
    to do (same doc style as the reference block in run-conductor.ps1) -- so this checks
    for the actual CALL form ('$precheckProc.Kill($true)'), not a bare substring, which
    would false-positive on that prose."""
    block = _extract_precheck_block(RUN_CONDUCTOR_WEEKEND)
    assert "WaitForExit(30000)" in block
    assert "$precheckProc.Kill()" in block
    assert "$precheckProc.Kill($true)" not in block
    # WaitForExit must textually precede both ReadToEnd() calls (proves the ordering fix
    # survived the port, not just that both APIs are mentioned somewhere in the block).
    wait_pos = block.index("WaitForExit(30000)")
    for read_call in ("StandardOutput.ReadToEnd()", "StandardError.ReadToEnd()"):
        assert wait_pos < block.index(read_call)


def test_weekend_precheck_blocks_spawn_when_gate_reports_exhausted(tmp_path):
    gate = _write_gate_fixture(tmp_path, "gate_exhausted.py", "import sys\nsys.exit(3)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, REAL_VENV_PY, gate, recorder,
                              source=RUN_CONDUCTOR_WEEKEND, harness_name="weekend_harness.ps1")
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)

    assert result.returncode == 0, (
        f"exhausted weekend precheck must exit 0 (blocked), not fall through -- "
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    assert not marker.exists(), (
        "the FELL_THROUGH sentinel must never be written -- this proves the weekend script "
        "never reached the line where Invoke-ClaudeWithRetry would have been called")


def test_weekend_precheck_allows_spawn_when_gate_reports_proceed(tmp_path):
    gate = _write_gate_fixture(tmp_path, "gate_proceed.py", "import sys\nsys.exit(0)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, REAL_VENV_PY, gate, recorder,
                              source=RUN_CONDUCTOR_WEEKEND, harness_name="weekend_harness.ps1")
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)

    assert result.returncode == FELL_THROUGH_EXIT, (
        f"a PROCEED gate must fall through unchanged -- stdout={result.stdout!r} "
        f"stderr={result.stderr!r}")
    assert marker.exists()
    assert marker.read_text(encoding="utf-8-sig").strip() == "FELL_THROUGH"
    assert not outcomes_file.exists()


def test_weekend_precheck_fails_open_on_timeout(tmp_path):
    gate = _write_gate_fixture(tmp_path, "gate_hangs.py", "import time\ntime.sleep(20)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, REAL_VENV_PY, gate, recorder, wait_ms=1500,
                              source=RUN_CONDUCTOR_WEEKEND, harness_name="weekend_harness.ps1")
    marker = tmp_path / "marker.txt"

    started = time.time()
    result = _run_harness(harness, marker)
    elapsed = time.time() - started

    assert result.returncode == FELL_THROUGH_EXIT, (
        f"a timed-out weekend precheck must fail OPEN (fall through) -- "
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    assert marker.exists()
    assert elapsed < 15, (
        f"took {elapsed:.1f}s -- the shortened 1.5s WaitForExit should have fired well "
        f"before the fixture gate's 20s sleep")


def test_weekend_precheck_fails_open_when_process_start_throws(tmp_path):
    not_an_exe = tmp_path / "not_really_python.exe"
    not_an_exe.write_text("this is not a valid win32 executable", encoding="utf-8")
    gate = _write_gate_fixture(tmp_path, "gate_unused.py", "import sys\nsys.exit(3)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, not_an_exe, gate, recorder,
                              source=RUN_CONDUCTOR_WEEKEND, harness_name="weekend_harness.ps1")
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)

    assert result.returncode == FELL_THROUGH_EXIT, (
        f"a Process.Start exception must fail OPEN -- stdout={result.stdout!r} "
        f"stderr={result.stderr!r}")
    assert marker.exists()


def test_weekend_exhausted_path_writes_schema_valid_outcome_row(tmp_path):
    gate = _write_gate_fixture(tmp_path, "gate_exhausted.py", "import sys\nsys.exit(3)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, REAL_VENV_PY, gate, recorder,
                              source=RUN_CONDUCTOR_WEEKEND, harness_name="weekend_harness.ps1")
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    assert outcomes_file.exists()
    lines = [ln for ln in outcomes_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])

    for field in ("fired_at", "task_id", "cost_usd", "items_drained", "items_added",
                  "lessons_shipped", "tests_delta", "regressions", "note", "trading_day",
                  "enters_last_trading_day", "orders_accepted",
                  "extra_exec_orders_accepted", "fills", "distinct_setups_traded"):
        assert field in row, f"missing field {field!r} in weekend precheck outcome row: {row}"

    assert row["cost_usd"] == 0.0
    assert row["items_drained"] == 0
    assert row["lessons_shipped"] == 0
    assert "budget" in row["task_id"].lower()
    assert "weekend" in row["task_id"].lower()
    assert "budget" in row["note"].lower()


def test_weekend_exhausted_outcome_row_parses_via_autonomy_report(tmp_path):
    gate = _write_gate_fixture(tmp_path, "gate_exhausted.py", "import sys\nsys.exit(3)\n")
    outcomes_file = tmp_path / "fixture-outcomes.jsonl"
    recorder = _write_outcome_recorder_fixture(tmp_path, outcomes_file)
    harness = _build_harness(tmp_path, REAL_VENV_PY, gate, recorder,
                              source=RUN_CONDUCTOR_WEEKEND, harness_name="weekend_harness.ps1")
    marker = tmp_path / "marker.txt"

    result = _run_harness(harness, marker)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert outcomes_file.exists()

    import autonomy_report as ar

    rows = ar.load_outcomes(outcomes_file)
    assert len(rows) == 1, f"autonomy_report.load_outcomes() choked on the row: {rows}"
    row = rows[0]

    assert ar.is_ship_event(row) is False
    assert ar.classify_noop_reason(row) == "budget_exhausted", (
        f"expected budget_exhausted classification, got {ar.classify_noop_reason(row)!r} "
        f"for row {row}")

    et_date = ar._row_et_date(row)
    assert et_date is not None

    report = ar.compute_report(rows, None, dict(ar._BUDGET_DEFAULTS), et_date)
    assert report["today"]["total_fires"] == 1
    assert report["today"]["ship_fires"] == 0
    assert report["today"]["noop_reasons"]["budget_exhausted"] == 1
