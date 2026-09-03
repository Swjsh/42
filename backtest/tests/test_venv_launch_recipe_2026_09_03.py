"""Guard: setup/scripts/install-fee-recalibrate.ps1 uses the proven "base pythonw +
venv-via-env" launch recipe (queue.md VENV-PYTHONW-REDIRECTS-TO-CONSOLE-PYTHON, MED,
status:recipe-proven 2026-09-03).

BACKGROUND
----------
PANDAS-CONSOLE-LEAK-ROOT-CAUSE (root-caused 2026-09-03) found that
``backtest\\.venv\\Scripts\\pythonw.exe`` is CPython's ``venvwlauncher`` redirector, but
``backtest\\.venv\\pyvenv.cfg`` records only ``executable=...\\python.exe`` (no
GUI-variant path) -- so EVERY venv pythonw launch re-execs the base install's CONSOLE
python.exe internally, which spawns a console-host window (conhost.exe /
WindowsTerminal.exe -Embedding) per fire. Live proof this session (WMI Win32_Process
inspection, ``creationflags=CREATE_NO_WINDOW`` passed on the OUTER launch exactly as
``run_cmd_hidden.py`` does today): the venv pythonw path still produced a
python.exe + conhost.exe descendant pair -- CREATE_NO_WINDOW does not survive the
internal re-exec. The base install's own pythonw.exe launched identically (same flag,
same script) produced zero console-relevant descendants.

RECIPE (a), TRIALED on Gamma_FeeRecalibrate ONLY (queue item explicitly scopes the trial
to one non-trading task): launch the BASE install's pythonw.exe directly and activate the
venv via environment (``VIRTUAL_ENV`` + ``PYTHONPATH=<venv>\\Lib\\site-packages``,
injected through ``run_cmd_hidden.py``'s existing ``--env`` flag) instead of via the
venv's own launcher stub. Verified live 2026-09-03 via both a manual probe AND
``Start-ScheduledTask`` on the re-registered task: zero new rows in
``window-leaks.jsonl`` (the live detector's own independent oracle), ``pandas.__file__``
resolves into ``backtest\\.venv\\Lib\\site-packages`` (the base install has no pandas
installed at all -- ``ModuleNotFoundError`` confirmed, ruling out ambiguous resolution),
rc=0 both as a bare probe and as the real scheduled-task fire (``LastTaskResult=0``), and
``automation/state/fee-calibration.json``'s mtime + ``as_of`` advanced with a correct
roster and no fetch errors.

WHAT THIS TEST GUARDS
----------------------
Static content of ``setup/scripts/install-fee-recalibrate.ps1`` -- NOT a live process
launch (that's the diagnostic probe done by hand this session, not something to
re-run on every pytest invocation). Pins the recipe so a future edit can't silently
regress it back to launching ``.venv\\Scripts\\pythonw.exe`` directly. This is the ONLY
install script this pin applies to -- the queue item explicitly says NOT to roll this
recipe to other install scripts in the same pass; a repo-wide roll is separate future
work with the leak detector as the oracle.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO / "setup" / "scripts" / "install-fee-recalibrate.ps1"


def _text() -> str:
    assert INSTALL_SCRIPT.exists(), f"missing: {INSTALL_SCRIPT}"
    return INSTALL_SCRIPT.read_text(encoding="utf-8")


def test_install_script_exists():
    assert INSTALL_SCRIPT.exists()


def test_wscript_action_launches_base_pythonw_not_venv_pythonw_as_inner_target():
    """The inner (post `--`) target -- the actual script interpreter -- must be
    $sysPythonw (base install), never $pywVenv (backtest\\.venv\\Scripts\\pythonw.exe).
    This is the one line that matters: it's what determines which pythonw.exe process
    tree the OS actually spawns."""
    text = _text()
    assert '-- `"$sysPythonw`" `"$script`""' in text, (
        "expected the wscriptArgs inner target (after the '--' separator) to be "
        "$sysPythonw (base install pythonw.exe), not $pywVenv -- the recipe (a) fix "
        "for VENV-PYTHONW-REDIRECTS-TO-CONSOLE-PYTHON. Full text:\n" + text
    )
    # Belt-and-suspenders: the venv pythonw variable must not appear as the inner
    # target of the actual $wscriptArgs assignment line.
    wscript_line = next(
        (ln for ln in text.splitlines() if ln.strip().startswith("$wscriptArgs")), None
    )
    assert wscript_line is not None, "could not find the $wscriptArgs assignment line"
    assert "$pywVenv" not in wscript_line, (
        f"$wscriptArgs still references $pywVenv directly -- regression back to the "
        f"leaking venv-launcher recipe: {wscript_line!r}"
    )


def test_venv_is_activated_via_env_not_via_launcher_stub():
    """VIRTUAL_ENV and PYTHONPATH must be injected via run_cmd_hidden.py's --env flag
    so the base pythonw.exe process resolves imports (pandas/numpy/etc.) into the
    venv's site-packages despite not being the venv's own launcher stub."""
    text = _text()
    assert "--env VIRTUAL_ENV=" in text, "VIRTUAL_ENV must be injected via --env"
    assert "--env PYTHONPATH=" in text, "PYTHONPATH must be injected via --env"
    assert "venvSitePkgs" in text and "Lib\\site-packages" in text, (
        "PYTHONPATH must point at the venv's Lib\\site-packages directory"
    )


def test_venv_site_packages_variable_defined_and_checked_for_existence():
    """$venvSitePkgs must be defined and included in the pre-flight existence check
    (the `foreach ($p in @(...))` guard) -- a silent typo in this path would make
    every future fire import-fail against the base install's site-packages instead."""
    text = _text()
    assert '$venvSitePkgs' in text
    # The existence-check foreach loop must include $venvSitePkgs in its array.
    foreach_line = next(
        (ln for ln in text.splitlines() if ln.strip().startswith("foreach ($p in @(")),
        None,
    )
    assert foreach_line is not None, "could not find the pre-flight existence-check loop"
    assert "$venvSitePkgs" in foreach_line, (
        f"pre-flight existence check does not verify $venvSitePkgs exists: {foreach_line!r}"
    )


def test_path_env_var_is_not_injected():
    """Documented, deliberate scope limit: PATH is NOT overridden by this recipe.
    fee_recalibrate.py's only go_live_gate usage is module-level constants -- it never
    calls go_live_gate._run_pytest or spawns BACKTEST_PY, so there is no PATH-relative
    interpreter lookup in this script's path. If a future edit starts injecting --env
    PATH=..., that's a scope change that should be a conscious, re-verified decision,
    not something this recipe silently grew."""
    text = _text()
    assert "--env PATH=" not in text, (
        "install-fee-recalibrate.ps1 now injects PATH via --env -- this is a scope "
        "change beyond the recipe (a) trial verified 2026-09-03; re-verify the "
        "PATH-relative-lookup assumption in fee_recalibrate.py's call chain before "
        "shipping this, then update this test's docstring/assertion accordingly."
    )


def test_not_rolled_to_other_install_scripts():
    """The queue item explicitly scopes this trial to Gamma_FeeRecalibrate only --
    a sibling install script picking up the same $sysPythonw-as-inner-target pattern
    independently (not via a shared helper) would mean the roll happened without the
    explicit after-hours pass + leak-detector-oracle step the item calls for."""
    scripts_dir = REPO / "setup" / "scripts"
    siblings = [
        p for p in scripts_dir.glob("install-*.ps1")
        if p.name not in ("install-fee-recalibrate.ps1",)
    ]
    offenders = []
    for p in siblings:
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "--env PYTHONPATH=" in t and "venvSitePkgs" in t:
            offenders.append(p.name)
    assert not offenders, (
        f"recipe (a) appears to have been rolled to other install scripts already: "
        f"{offenders} -- queue item VENV-PYTHONW-REDIRECTS-TO-CONSOLE-PYTHON scoped "
        f"the trial to Gamma_FeeRecalibrate only for this pass"
    )
