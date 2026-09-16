"""Guards for the brain-provenance ledger + visible-stamp fix (2026-09-15).

THE DEFECT (already root-caused by the task that produced this fix -- not re-litigated
here): automation/state/brain-mode.json routes four launchers (run-conductor.ps1,
run-conductor-weekend.ps1, run-analyst-eod.ps1, run-treasurer-weekly.ps1) through
setup/scripts/_brain.ps1#Resolve-BrainModel to either a local Ollama model (mode=local) or
the normal Claude path (anything else). That routing is intentional and untouched by this
fix. The defect was PROVENANCE: the human-readable artifacts those fires write (STATUS.md
lines, EOD digests, treasury audits) never recorded which brain produced them -- a
qwen-authored analysis was indistinguishable from a Claude-authored one, violating the
OP-32 free-model trust gate (every free-model touchpoint must be identifiable and
Claude-gradable).

THE FIX, under test here:
  1. Resolve-BrainModel now routes every return (including its own fail-open catch) through
     Complete-BrainResolution, which appends one JSONL row to
     automation/state/brain-provenance.jsonl via Write-BrainProvenanceRow and sets
     $env:GAMMA_BRAIN_STAMP to a short human string ("<model> (local)" / "<model>
     (anthropic)").
  2. Write-BrainProvenanceRow is fail-open by construction: every mutating step is inside
     one try/catch that swallows any exception, so a ledger write failure (disk full, locked
     file, bad path) can never propagate into Resolve-BrainModel and change the model name
     the caller gets back or block the fire.
  3. The ledger self-prunes to a 90-day retention window (OP-22) once it exceeds 200 rows.

TEST STRATEGY: this suite runs the REAL, unmodified _shared.ps1 + _brain.ps1 via
powershell.exe, exactly as the existing PowerShell-facing tests in this directory do (see
test_conductor_gate_precheck.py's docstring for the rationale -- subprocessing the real file
is the only way to prove the actual runtime behavior rather than a description of it). Unlike
that file, this one does NOT need to extract a marker-delimited block: Resolve-BrainModel is
a complete, callable function, so the harness just dot-sources the two real files, points
$Global:WorkDir at an isolated tmp_path fixture tree (so the test never reads or writes the
REAL automation/state/brain-mode.json or brain-provenance.jsonl -- both of which are live
production state that can change under a running test, as this session's own transcript
demonstrated when brain-mode.json flipped from "local" to "claude" mid-session), and prints a
small JSON result the Python side asserts against.

Network calls (Invoke-RestMethod to the local Ollama daemon, Test-NetConnection for the
no-think proxy) are stubbed with PowerShell functions of the same name defined in the harness
AFTER dot-sourcing -- functions outrank cmdlets in PowerShell's command resolution, so every
call site inside the real Resolve-BrainModel/Start-NoThinkProxy transparently hits the stub.
This means the "local mode succeeds" test never touches a real Ollama installation and is
deterministic regardless of what is actually running on the box.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "setup" / "scripts"
SHARED = SCRIPTS / "_shared.ps1"
BRAIN = SCRIPTS / "_brain.ps1"

TIMEOUT_SEC = 60


def _fixture_tree(tmp_path: Path, brain_mode_text: str | None, station_mode: str = "work") -> Path:
    """Builds an isolated automation/state/ tree so the test never touches the real one."""
    work_dir = tmp_path / "workdir"
    state_dir = work_dir / "automation" / "state"
    station_dir = state_dir / "station"
    state_dir.mkdir(parents=True, exist_ok=True)
    station_dir.mkdir(parents=True, exist_ok=True)
    if brain_mode_text is not None:
        (state_dir / "brain-mode.json").write_text(brain_mode_text, encoding="utf-8")
    (station_dir / "mode.json").write_text(json.dumps({"mode": station_mode}), encoding="utf-8")
    return work_dir


_LOCAL_MODE_JSON = json.dumps({
    "mode": "local",
    "map": {"sonnet": "gamma-planner-fast", "opus": "gamma-planner-fast", "haiku": "qwen3:14b"},
    "proxy_port": 11435,
    "ollama_port": 11434,
})

_CLAUDE_MODE_JSON = json.dumps({
    "mode": "claude",
    "map": {"sonnet": "gamma-planner-fast", "opus": "gamma-planner-fast", "haiku": "qwen3:14b"},
    "proxy_port": 11435,
    "ollama_port": 11434,
})

_MALFORMED_JSON = "{ this is not valid json,,, ["

# Stubs for the two network calls Resolve-BrainModel's local path makes. Defined as
# PowerShell functions AFTER dot-sourcing the real files -- functions take precedence over
# cmdlets of the same name in PowerShell's command resolution, so every call site inside the
# real Resolve-BrainModel / Start-NoThinkProxy transparently hits these instead of the network.
_NETWORK_STUBS = r'''
function Invoke-RestMethod {
    param($Uri, $TimeoutSec)
    if ($Uri -match "/api/version") { return @{ version = "0.0.0-test" } }
    if ($Uri -match "/api/tags") {
        return @{ models = @(@{ name = "gamma-planner-fast" }, @{ name = "qwen3:14b" }) }
    }
    throw "TEST STUB: unexpected Invoke-RestMethod call to $Uri"
}
function Test-NetConnection {
    param($ComputerName, $Port, $InformationLevel, $WarningAction)
    return $true
}
'''


def _build_harness(tmp_path: Path, work_dir: Path, tier: str, task_name: str,
                    extra_preamble: str = "", extra_postamble: str = "") -> Path:
    harness = tmp_path / "harness.ps1"
    text = (
        '$ErrorActionPreference = "Continue"\n'
        f'. "{SHARED}"\n'
        f'. "{BRAIN}"\n'
        # Override WorkDir AFTER sourcing _shared.ps1 (which hardcodes it to the real repo) --
        # _brain.ps1 reads $Global:WorkDir at CALL time inside each function, not at
        # dot-source time, so this redirection is picked up by every Get-BrainMode /
        # Get-StationMode / Write-BrainProvenanceRow call below.
        f'$Global:WorkDir = "{work_dir}"\n'
        + extra_preamble
        + f'$result = Resolve-BrainModel -Tier "{tier}" -TaskName "{task_name}"\n'
        + '$ledgerPath = Join-Path $Global:WorkDir "automation\\state\\brain-provenance.jsonl"\n'
        'if (Test-Path $ledgerPath) {\n'
        '    $ledgerLines = @(Get-Content -Path $ledgerPath | ForEach-Object { [string]$_ })\n'
        '    $ledgerLastLine = [string]$ledgerLines[-1]\n'
        '    $ledgerLineCount = $ledgerLines.Count\n'
        '} else {\n'
        '    $ledgerLastLine = $null\n'
        '    $ledgerLineCount = 0\n'
        '}\n'
        + extra_postamble
        + '$out = @{\n'
        '    returnedModel   = $result\n'
        '    stamp           = $env:GAMMA_BRAIN_STAMP\n'
        '    ledgerLastLine  = $ledgerLastLine\n'
        '    ledgerLineCount = $ledgerLineCount\n'
        '    completedOk     = $true\n'
        '}\n'
        '$out | ConvertTo-Json -Compress\n'
        'exit 0\n'
    )
    harness.write_text(text, encoding="utf-8")
    return harness


def _run_harness(harness_path: Path) -> dict:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(harness_path)],
        capture_output=True, text=True, timeout=TIMEOUT_SEC,
    )
    assert result.returncode == 0, (
        f"harness must complete without throwing -- stdout={result.stdout!r} "
        f"stderr={result.stderr!r}")
    # Last non-blank line is the ConvertTo-Json -Compress output; earlier lines (if any) would
    # be stray Write-Host/log noise from a real function we failed to stub.
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert lines, f"harness produced no output -- stderr={result.stderr!r}"
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"harness stdout was not valid JSON: {result.stdout!r} stderr={result.stderr!r}"
        ) from exc


# --------------------------------------------------------------------------- #
# 1. claude mode stamps the Claude tier
# --------------------------------------------------------------------------- #

def test_claude_mode_stamps_claude_tier_and_ledger_row(tmp_path):
    work_dir = _fixture_tree(tmp_path, _CLAUDE_MODE_JSON)
    harness = _build_harness(tmp_path, work_dir, tier="sonnet", task_name="brain-provenance-test-claude")
    out = _run_harness(harness)

    assert out["returnedModel"] == "sonnet", "mode=claude must return the tier name unchanged"
    assert "(anthropic)" in out["stamp"], f"stamp must label the Claude path: {out['stamp']!r}"
    assert out["ledgerLineCount"] == 1, "exactly one provenance row must be appended per call"

    row = json.loads(out["ledgerLastLine"])
    assert row["task_name"] == "brain-provenance-test-claude"
    assert row["requested_tier"] == "sonnet"
    assert row["resolved_model"] == "sonnet"
    assert row["mode"] == "claude"
    assert row["local_path_taken"] is False
    assert "ts_et" in row and row["ts_et"]


# --------------------------------------------------------------------------- #
# 2. local mode stamps the local model
# --------------------------------------------------------------------------- #

def test_local_mode_stamps_local_model_and_ledger_row(tmp_path):
    work_dir = _fixture_tree(tmp_path, _LOCAL_MODE_JSON, station_mode="work")
    harness = _build_harness(
        tmp_path, work_dir, tier="sonnet", task_name="brain-provenance-test-local",
        extra_preamble=_NETWORK_STUBS,
    )
    out = _run_harness(harness)

    assert out["returnedModel"] == "gamma-planner-fast", (
        f"mode=local with a healthy stubbed Ollama must resolve to the mapped local model, "
        f"got {out['returnedModel']!r}")
    assert "(local)" in out["stamp"], f"stamp must label the local path: {out['stamp']!r}"
    assert out["ledgerLineCount"] == 1

    row = json.loads(out["ledgerLastLine"])
    assert row["task_name"] == "brain-provenance-test-local"
    assert row["requested_tier"] == "sonnet"
    assert row["resolved_model"] == "gamma-planner-fast"
    assert row["mode"] == "local"
    assert row["local_path_taken"] is True
    assert row["reason"] == "local_ok"


# --------------------------------------------------------------------------- #
# 3. unreadable / missing brain-mode.json fails open to the Claude path,
#    stamped as such
# --------------------------------------------------------------------------- #

def test_malformed_brain_mode_json_fails_open_to_claude_with_labeled_stamp(tmp_path):
    work_dir = _fixture_tree(tmp_path, _MALFORMED_JSON)
    harness = _build_harness(tmp_path, work_dir, tier="sonnet", task_name="brain-provenance-test-malformed")
    out = _run_harness(harness)

    assert out["returnedModel"] == "sonnet", "malformed brain-mode.json must fail open to the tier name"
    assert "(anthropic)" in out["stamp"]

    row = json.loads(out["ledgerLastLine"])
    assert row["mode"] == "claude", "Get-BrainMode's internal catch defaults to mode=claude on a parse failure"
    assert row["local_path_taken"] is False
    assert row["reason"] == "mode!=local"


def test_missing_brain_mode_json_fails_open_to_claude_with_labeled_stamp(tmp_path):
    work_dir = _fixture_tree(tmp_path, brain_mode_text=None)  # file never written
    harness = _build_harness(tmp_path, work_dir, tier="opus", task_name="brain-provenance-test-missing")
    out = _run_harness(harness)

    assert out["returnedModel"] == "opus"
    assert "(anthropic)" in out["stamp"]
    row = json.loads(out["ledgerLastLine"])
    assert row["mode"] == "claude"
    assert row["local_path_taken"] is False


# --------------------------------------------------------------------------- #
# 4. ledger write failure never breaks the fire -- Resolve-BrainModel still
#    returns a usable model and the harness completes normally
# --------------------------------------------------------------------------- #

def test_ledger_write_failure_does_not_break_the_fire(tmp_path):
    work_dir = _fixture_tree(tmp_path, _CLAUDE_MODE_JSON)
    # Shadow Add-Content (the only mutating call Write-BrainProvenanceRow makes) with a
    # function that always throws -- proves the ledger writer's internal try/catch actually
    # swallows a real failure rather than merely looking like it does by inspection.
    broken_add_content = 'function Add-Content { throw "TEST_FORCED_LEDGER_FAILURE" }\n'
    harness = _build_harness(
        tmp_path, work_dir, tier="sonnet", task_name="brain-provenance-test-ledger-fail",
        extra_preamble=broken_add_content,
    )
    out = _run_harness(harness)

    assert out["completedOk"] is True, "the harness (and by extension the fire) must complete, not crash"
    assert out["returnedModel"] == "sonnet", (
        "Resolve-BrainModel must still return the correct model even when its own "
        "provenance logging fails")
    assert out["ledgerLineCount"] == 0, "a forced Add-Content failure must leave no ledger row behind"
    assert out["ledgerLastLine"] is None


# --------------------------------------------------------------------------- #
# 5. retention cap -- structural check that Write-BrainProvenanceRow prunes
# --------------------------------------------------------------------------- #

def test_ledger_retention_cap_prunes_rows_older_than_90_days(tmp_path):
    work_dir = _fixture_tree(tmp_path, _CLAUDE_MODE_JSON)
    ledger_path = work_dir / "automation" / "state" / "brain-provenance.jsonl"

    # Seed 250 rows: 5 "old" (200 days back, must be pruned) + 245 "recent" (must survive),
    # so the seeded file is already over the 200-line prune-trigger threshold before the
    # harness's own call appends row #251 and Write-BrainProvenanceRow's prune step runs.
    old_row = json.dumps({
        "ts_et": "2025-01-01 00:00:00 ET", "task_name": "seed-old", "requested_tier": "sonnet",
        "resolved_model": "sonnet", "mode": "claude", "station_mode": "work",
        "local_path_taken": False, "reason": "seed",
    })
    recent_row = json.dumps({
        "ts_et": "2026-09-14 00:00:00 ET", "task_name": "seed-recent", "requested_tier": "sonnet",
        "resolved_model": "sonnet", "mode": "claude", "station_mode": "work",
        "local_path_taken": False, "reason": "seed",
    })
    lines = [old_row] * 5 + [recent_row] * 245
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    harness = _build_harness(tmp_path, work_dir, tier="sonnet", task_name="brain-provenance-test-retention")
    out = _run_harness(harness)

    assert out["returnedModel"] == "sonnet"
    # 5 old rows pruned, 245 recent + 1 new row survive.
    assert out["ledgerLineCount"] == 246, (
        f"expected 245 recent seed rows + 1 new row = 246 after pruning 5 old rows, "
        f"got {out['ledgerLineCount']}")
    # utf-8-sig: Write-BrainProvenanceRow's prune path rewrites via PowerShell 5.1's
    # Set-Content -Encoding UTF8, which (unlike Add-Content in this .NET/PS version) prepends
    # a BOM -- read it off rather than let it corrupt the first row's first field.
    remaining_task_names = {
        json.loads(ln)["task_name"]
        for ln in (work_dir / "automation" / "state" / "brain-provenance.jsonl").read_text(encoding="utf-8-sig").splitlines()
        if ln.strip()
    }
    assert "seed-old" not in remaining_task_names, "rows older than the 90-day OP-22 retention window must be pruned"
    assert "seed-recent" in remaining_task_names
