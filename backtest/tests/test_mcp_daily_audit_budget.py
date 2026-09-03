"""Guard: run-mcp-daily-audit.ps1's invocation shape.

RETIRED-AND-REPOINTED 2026-09-03: this guard originally pinned `-MaxBudgetUsd`/
`-TimeoutSec` on an `Invoke-Claude` LLM fire against
`automation/prompts/mcp-weekly-audit.md` (full incident: `MaxBudgetUsd` was
mis-sized at birth at 0.30/240s, producing a 45% combined failure rate across 42
dated fires 2026-06-21..2026-08-07 -- 10 budget-exceeded, 6 timeout -- fixed to
0.60/300 on 2026-08-08, see git history for that fix's own commit). That whole
premise is now moot: `run-mcp-daily-audit.ps1` no longer spawns an LLM at all.
The free-model prompt wrote TWO false BLOCKERs into STATUS.md in one night
(2026-09-03, 00:03 ET RED + 07:48 ET YELLOW, both contradicted by a direct REST
`/v2/account` call using the same `.mcp.json` keys returning 200/ACTIVE
throughout), so the fire was converted to a deterministic, $0 Python probe
(`setup/scripts/mcp_daily_audit.py`, guard: `test_mcp_daily_audit_2026_09_03.py`)
invoked via `Invoke-PythonHidden`. A `-MaxBudgetUsd`/model/effort knob no longer
applies -- there is no LLM spend to bound. This file is REPOINTED, not deleted,
to the new invariant: the script must invoke the deterministic Python probe (not
`Invoke-Claude`) and must not silently regress back to an LLM fire.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "setup" / "scripts" / "run-mcp-daily-audit.ps1"
PY_PROBE = ROOT / "setup" / "scripts" / "mcp_daily_audit.py"


def _read_script_text() -> str:
    assert SCRIPT.exists(), f"run-mcp-daily-audit.ps1 missing at {SCRIPT}"
    return SCRIPT.read_text(encoding="utf-8")


def test_mcp_daily_audit_calls_the_deterministic_python_probe():
    text = _read_script_text()
    assert "mcp_daily_audit.py" in text, (
        "run-mcp-daily-audit.ps1 no longer references mcp_daily_audit.py -- the deterministic "
        "$0 probe this task was repointed to on 2026-09-03. See module docstring."
    )
    assert PY_PROBE.exists(), "mcp_daily_audit.py itself is missing -- the script it invokes"


def test_mcp_daily_audit_no_longer_invokes_an_llm_fire():
    text = _read_script_text()
    # Match the actual PowerShell CALL shape ("$var = Invoke-Claude"), not the word
    # appearing inside this script's own historical-context docstring/comment prose.
    call_pattern = re.compile(r"(?m)^\s*\$\w+\s*=\s*Invoke-Claude\b")
    assert not call_pattern.search(text), (
        "run-mcp-daily-audit.ps1 has regressed back to an Invoke-Claude LLM fire -- this task "
        "was converted to a deterministic $0 probe on 2026-09-03 after the free-model prompt "
        "wrote two false BLOCKERs (401/404) into STATUS.md while direct REST with the same "
        "keys returned 200/ACTIVE the whole time. See module docstring / "
        "automation/prompts/mcp-weekly-audit.md's own retirement header."
    )
    prompt_ref_pattern = re.compile(r"PromptFile.*mcp-weekly-audit\.md")
    assert not prompt_ref_pattern.search(text), (
        "run-mcp-daily-audit.ps1 still wires the retired LLM prompt file as a -PromptFile"
    )


def test_mcp_daily_audit_uses_invoke_python_hidden_not_a_bare_spawn():
    text = _read_script_text()
    assert "Invoke-PythonHidden" in text, (
        "must invoke the python probe via the sanctioned hidden-window helper (OP-27 L41) -- "
        "a bare `python script.py` in a scheduled-task PS1 leaks a conhost window"
    )


if __name__ == "__main__":
    sys.exit(0)
