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

RECIPE (a), FIRST TRIALED on Gamma_FeeRecalibrate (queue item originally scoped the trial
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

ROLLED OUT (same night, same recipe, each independently live-verified) to
Gamma_RetestZoneShadow and Gamma_StructureClassifierShadow -- both were freshly pointed at
``backtest\\.venv\\Scripts\\pythonw.exe`` earlier that evening (to fix a pandas
ModuleNotFoundError under system pythonw) and so were carrying the exact leaking recipe
this fix targets. Each was re-registered and fired via ``Start-ScheduledTask``: script
output advanced (summary.json ``generated_at_et``), zero new ``window-leaks.jsonl`` rows,
pandas resolved into the venv (216 trades / self-check pass respectively), Export-
ScheduledTask diff showed only the ``Actions`` block changed (triggers untouched). See
``ROLLED_OUT`` below.

WHAT THIS TEST GUARDS
----------------------
Static content of the install scripts named in ``ROLLED_OUT`` -- NOT a live process
launch (that's the diagnostic probe done by hand each time this set grows, not something
to re-run on every pytest invocation). Pins the recipe so a future edit can't silently
regress any of them back to launching ``.venv\\Scripts\\pythonw.exe`` directly, AND
catches an install script picking up the same pattern without having been through that
live verification (and added to ``ROLLED_OUT`` by name). The much larger population of
pre-existing venv-pythonw install scripts (60+, enumerated via grep in the same pass that
authored ``ROLLED_OUT``) was deliberately NOT converted -- per-file structure is
heterogeneous (varying variable names, some multi-hop, several futures/broker-adjacent)
and converting all of them in one sweep would violate the "smallest diffs, one installer
at a time, verify each" discipline. That is follow-up work, with the leak detector as the
oracle, same as this pass.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO / "setup" / "scripts" / "install-fee-recalibrate.ps1"

ROLLED_OUT = {
    "install-fee-recalibrate.ps1",  # setup/scripts/ -- original recipe-(a) proof, 2026-09-03
    "install-retest-zone-shadow.ps1",  # setup/ -- rolled + live-verified 2026-09-03
    "install-structure-classifier-shadow.ps1",  # setup/ -- rolled + live-verified 2026-09-03
    # 2026-09-03 second-pass roll (this session) -- each re-registered, State=Ready,
    # NextRunTime sane, Export-ScheduledTask diff showed only Enabled/StartBoundary/
    # Arguments changed (triggers untouched), fired via Start-ScheduledTask (LastTaskResult
    # =0) or verified via a direct base-pythonw+--env probe, zero new window-leaks.jsonl
    # rows across the whole batch (2619 before and after).
    "install-profit-lock-v2-shadow.ps1",  # setup/ -- doubly-leaking (outer+inner venv
    # pythonw) before this pass; both hops now $sysPythonw. Fired, LastTaskResult=0.
    "install-entry-location-trend-shadow.ps1",  # setup/ -- fired, LastTaskResult=0,
    # entry-location-trend-summary.json mtime advanced.
    "install-trendline-tight-exit-shadow.ps1",  # setup/ -- fired, LastTaskResult=0,
    # trendline-tight-exit-shadow summary mtime advanced.
    "install-state-freshness-remediate.ps1",  # setup/scripts/ -- fired via scheduled task
    # (LastTaskResult=0) AND via a direct probe (verdict=RED n_candidates=0, clean exit,
    # no crash) -- its _default_starter() re-invokes producers with sys.executable + no
    # env= override, so producer children inherit the injected VIRTUAL_ENV/PYTHONPATH and
    # sys.executable now resolves to the non-leaking base pythonw.exe directly.
    "install-key-levels-snapshot.ps1",  # setup/scripts/ -- fired via scheduled task
    # (LastTaskResult=0) AND via a direct probe (SKIP-UNCHANGED, clean exit, no crash).
    "install-context-bundle.ps1",  # setup/scripts/ -- fired, LastTaskResult=0, --once
    # mode, context-bundle summary mtime advanced.
}


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
    """Recipe (a) is scoped to the ROLLED_OUT set above -- each entry was individually
    live-verified (script ran, zero new window-leaks.jsonl rows, pandas resolved) before
    being added here. A sibling install script picking up the same $sysPythonw-as-inner-
    target + --env PYTHONPATH pattern WITHOUT going through that verification (and without
    being added to ROLLED_OUT by the session that did it) is a silent, unverified roll --
    catch it here rather than letting it drift in unnoticed."""
    offenders = []
    for scripts_dir in (REPO / "setup", REPO / "setup" / "scripts"):
        for p in scripts_dir.glob("install-*.ps1"):
            if p.name in ROLLED_OUT:
                continue
            try:
                t = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "--env PYTHONPATH=" in t and "venvSitePkgs" in t:
                offenders.append(p.name)
    assert not offenders, (
        f"recipe (a) appears to have been rolled to install scripts not in ROLLED_OUT: "
        f"{offenders} -- either this is a genuine, verified roll (add the name to "
        f"ROLLED_OUT above, with a comment citing the live verification), or it's an "
        f"accidental/unverified pickup that should be reverted"
    )


def test_rolled_out_scripts_all_exist():
    """Every name in ROLLED_OUT must correspond to a real install script -- a stale entry
    (e.g. after a rename) would silently widen the allowlist without protecting anything."""
    missing = []
    for name in ROLLED_OUT:
        found = list((REPO / "setup").glob(name)) + list((REPO / "setup" / "scripts").glob(name))
        if not found:
            missing.append(name)
    assert not missing, f"ROLLED_OUT names with no matching install script: {missing}"
