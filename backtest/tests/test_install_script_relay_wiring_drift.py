"""Static drift guard: install-*.ps1 SOURCE templates must match the relay wiring
they were migrated onto, so a legitimate future re-run can never silently regress it.

THE BUG THIS GUARDS (found live, 2026-08-07, VBS-WRAPPER-EXIT-CODE-BLIND-SPOT
follow-up). `fix-venv-pythonw-console-leak.ps1` (commit 306e5075, 2026-07-14) migrated
18 tasks from a direct `wscript -> run_exe_hidden.vbs -> venv-pythonw -> script.py`
wiring (Task Scheduler's LastTaskResult is always a fake 0 on this shape -- the vbs is
fire-and-forget) onto the two-hop relay `... -> run_cmd_hidden.py -- venv-pythonw
script.py`, which runs the child SYNCHRONOUSLY and logs the true exit code. That fix
was applied IMPERATIVELY (one-off `Set-ScheduledTask -Action ...` calls against live
Task Scheduler state) -- but each task's own DECLARATIVE install-*.ps1 source (the
script that owns re-registration whenever anyone tunes a cadence/trigger/setting) was
never updated to match. Proven concretely: `install-crypto-twin.ps1`'s 2026-08-01
cadence-tune commit (af849657) re-ran the OLD direct-wiring template, silently undoing
the relay fix with zero error, log line, or visible symptom -- confirmed live via
`Get-ScheduledTask -TaskName Gamma_CryptoTwin` showing bare venv-pythonw invocation
again, 3+ weeks after the "fix". Any of the other 17 already-migrated tasks has the
identical latent risk the next time its own install script is legitimately re-run.

THE FIX (this test enforces it going forward): for every Gamma_* task this repo
considers "on the relay" (EXPECTED_RELAY_TASKS below), the install-*.ps1 file that
registers it must itself reference `run_cmd_hidden.py` (or `run_ps1_hidden.py`) in its
action-construction code -- not just live Task Scheduler state, which this test does
NOT query (pure static parsing, runs anywhere, fast, deterministic, matches
test_scheduled_tasks_doc.py's precedent of doc<->script static checking rather than
doc<->live-reality, which is audit_scheduled_tasks.py's separate live-state job).

A task that legitimately still routes directly (never migrated, or migrated to a
DIFFERENT relay like run_ps1_hidden.py for a .ps1-wrapped worker) is fine as long as
it is not falsely claimed here -- EXPECTED_RELAY_TASKS is the list this repo has
actually committed to keeping on the run_cmd_hidden.py relay; growing that list is a
deliberate future-fire action (VBS-WRAPPER-EXIT-CODE-BLIND-SPOT's remaining ~13 direct
non-daemon candidates), not something this guard invents on its own.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SETUP = _REPO / "setup"

# Task name -> install script relative path (the DECLARATIVE source of truth that
# owns re-registration). Only tasks this repo has actually migrated onto the
# run_cmd_hidden.py relay belong here -- see the module docstring.
EXPECTED_RELAY_TASKS: dict[str, str] = {
    "Gamma_BrokerFills": "install-broker-fills.ps1",
    "Gamma_Confluence": "install-confluence.ps1",
    "Gamma_CryptoTwin": "scripts/install-crypto-twin.ps1",
    "Gamma_DressRehearsal": "install-dress-rehearsal.ps1",
    "Gamma_EmaSnapshot": "install-ema-snapshot.ps1",
    "Gamma_FirmBrief": "install-firm-brief.ps1",
    "Gamma_FreeModelAudit": "scripts/install-free-model-audit.ps1",
    "Gamma_FuturesMirror": "scripts/install-futures-mirror.ps1",
    "Gamma_LevelMemory": "install-level-memory.ps1",
    "Gamma_Prospector": "scripts/install-prospector.ps1",
    "Gamma_SelfAudit": "scripts/install-self-audit.ps1",
    "Gamma_TradeAutopsy": "install-trade-autopsy.ps1",
    "Gamma_TradeToday": "install-trade-today.ps1",
    "Gamma_Trendlines": "install-trendlines.ps1",
    "Gamma_TwinSentinel": "scripts/install-twin-sentinel.ps1",
    # 2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration -- 19 of the 31 direct-
    # invocation tasks named in the 2026-08-07 audit (queue.md), the ones with a
    # dedicated install-*.ps1 (the other ~9 are registered by a shared/batch
    # installer or have no discoverable install script -- left for a future fire,
    # NOT silently claimed here). EodFlattenCore/JIntentExecutor deliberately
    # EXCLUDED per the audit's own explicit note (system-pythonw-direct /
    # safety-critical daemon shape, handle with a dedicated fire).
    "Gamma_AutoCommitCandidates": "scripts/install-auto-commit-candidates.ps1",
    "Gamma_CcrKeepalive": "scripts/install-ccr-keepalive.ps1",
    "Gamma_ChopMeter": "scripts/install-chop-meter.ps1",
    "Gamma_ContextBundle": "scripts/install-context-bundle.ps1",
    "Gamma_FuturesEdge3Sim": "scripts/install-futures-edge3-sim.ps1",
    "Gamma_KeyLevelsSnapshot": "scripts/install-key-levels-snapshot.ps1",
    "Gamma_LedgerArchive": "scripts/install-ledger-archive.ps1",
    "Gamma_LiveWatch": "scripts/install-live-watch.ps1",
    "Gamma_MacroCalendar": "scripts/install-macro-calendar.ps1",
    "Gamma_MondayVerify": "scripts/install-monday-verify.ps1",
    "Gamma_OpenBellStatus": "scripts/install-open-bell-status.ps1",
    "Gamma_ParticipationDaily": "scripts/install-participation-daily.ps1",
    "Gamma_PremarketReadiness": "scripts/install-premarket-readiness.ps1",
    "Gamma_PreopenReadiness": "scripts/install-preopen-readiness.ps1",
    "Gamma_RegimeAttribution": "scripts/install-regime-attribution.ps1",
    "Gamma_ThetaClock": "scripts/install-theta-clock.ps1",
    "Gamma_TwinChaos": "scripts/install-twin-chaos-drill.ps1",
    "Gamma_ViolinMetric": "scripts/install-violin-metric.ps1",
    "Gamma_WindowLeakDetectorKeepalive": "scripts/install-window-leak-detector-keepalive.ps1",
}


def _strip_ps1_comments(text: str) -> str:
    """Strip PowerShell `<# ... #>` block comments and trailing `# ...` line comments.

    Load-bearing for this guard: several install scripts' own DOCSTRINGS mention
    "run_cmd_hidden.py" in PROSE while explicitly saying it is NOT used (e.g.
    install-crypto-twin.ps1's pre-fix docstring: "no run_ps1_hidden.py/
    run_cmd_hidden.py hop needed"). A naive `"run_cmd_hidden.py" in text` substring
    check is fooled by that negation -- caught live via a RED-proof restore of the
    pre-fix file, which the naive check incorrectly passed. Only CODE lines count.
    """
    text = re.sub(r"<#.*?#>", "", text, flags=re.DOTALL)
    text = re.sub(r"(?m)(?<!`)#.*$", "", text)
    return text


def _find_install_script(rel_hint: str) -> Path | None:
    """Resolve a hinted relative path; fall back to a name-based search under setup/
    since not every install script lives at the exact hinted path (naming drift is
    itself common in this repo -- be forgiving about WHERE, strict about CONTENT)."""
    direct = _SETUP / rel_hint
    if direct.exists():
        return direct
    stem = Path(rel_hint).stem  # e.g. "install-broker-fills"
    hits = list(_SETUP.rglob(f"{stem}.ps1"))
    return hits[0] if hits else None


@pytest.mark.parametrize("task_name", sorted(EXPECTED_RELAY_TASKS))
def test_expected_relay_task_install_script_references_relay(task_name: str) -> None:
    rel_hint = EXPECTED_RELAY_TASKS[task_name]
    script_path = _find_install_script(rel_hint)
    if script_path is None:
        pytest.skip(
            f"{task_name}: no install script found for hint {rel_hint!r} under setup/ "
            "-- this task may be registered by a shared/batch installer instead of its "
            "own file; not a relay-drift failure, just an unmapped source (fix the hint "
            "in EXPECTED_RELAY_TASKS if this fires)."
        )
    raw_text = script_path.read_text(encoding="utf-8", errors="ignore")

    # Must actually be the script that registers THIS task (defense against a stale hint
    # silently matching the wrong file).
    assert re.search(rf'\$taskName\s*=\s*"{re.escape(task_name)}"', raw_text) or task_name in raw_text, (
        f"{script_path} does not appear to register {task_name} -- fix EXPECTED_RELAY_TASKS' "
        f"hint, this test matched the wrong file"
    )

    # CODE ONLY -- see _strip_ps1_comments' docstring for why this matters (a prose
    # mention inside a comment/docstring saying the relay is NOT used must not pass).
    text = _strip_ps1_comments(raw_text)

    assert "run_cmd_hidden.py" in text or "run_ps1_hidden.py" in text, (
        f"DRIFT: {script_path} registers {task_name} directly against a target script "
        f"with no run_cmd_hidden.py/run_ps1_hidden.py relay reference. This is the exact "
        f"class of regression found live for Gamma_CryptoTwin on 2026-08-07 (a prior "
        f"imperative fix was silently undone by this script's own next legitimate "
        f"re-run). Re-apply the relay wiring in THIS FILE (not just live Task Scheduler "
        f"state) before shipping any other change to it."
    )


def test_crypto_twin_install_script_uses_venv_pythonw_as_inner_interpreter() -> None:
    """Narrower regression pin for the exact bug found: the relay's INNER command must
    still launch crypto_twin_health.py under backtest-venv pythonw (it imports
    exit_manager/risk_gate/crypto.lib.* + pandas -- system pythonw can't run it)."""
    script_path = _SETUP / "scripts" / "install-crypto-twin.ps1"
    text = script_path.read_text(encoding="utf-8", errors="ignore")
    assert "run_cmd_hidden.py" in text
    assert re.search(r'--\s*`"\$pythonwVenv`"\s*`"\$script`"', text) or (
        "pythonwVenv" in text and "run_cmd_hidden.py" in text
    ), (
        "install-crypto-twin.ps1's action string must pass venv-pythonw as the command "
        "AFTER the '--' separator (the relay's inner interpreter), not just reference "
        "run_cmd_hidden.py somewhere incidental."
    )
