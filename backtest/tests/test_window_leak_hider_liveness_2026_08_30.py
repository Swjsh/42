"""Guard: a dead popup-hider must make the window-leak audit read RED.

THE FAILURE THIS PINS (2026-08-30, J: "first priority is stopping all popups tho i am
seeing cmd or poewrshell popups that must not happen").

Two hiders defend this box against leaked console windows:

  window-leak-detector.py  0.5s EnumWindows poll. Hides LATE -- a leaked window is on
                           screen for up to half a second, which is long enough to see and
                           long enough to pull focus out of a fullscreen game.
  window_leak_hook.py      SetWinEventHook(EVENT_OBJECT_SHOW). Hides within a frame.

The hook died on 2026-08-10 and was still dead on 2026-08-30 -- twenty days. Measured that
session: automation/state/window-leak-hook.pid named pid 9036, which was not running; the
last window-leak-hook-*.log was dated 2026-08-10; and `Get-ScheduledTask Gamma*` had ZERO
actions referencing window_leak_hook, i.e. nothing on the box had ever been responsible for
restarting it. Over the same day the surviving poller logged 29 leaks, every one
`mitigated: true` -- hidden, but only after being seen.

audit_window_leak_compliance.py checks 1-5 all ask "could a popup be spawned?" Not one of
them asked "is anything still awake to hide one?", so the audit was blind to a hider being
dead. Check (6) HIDER_NOT_RUNNING closes that, and this test is its RED-proof: without a
test that drives the check into the failing state, "0 hiders down" is indistinguishable
from a check that cannot fail.

This is the third occurrence of this shape on this subsystem -- the detector itself went
dark ~2 months (2026-05-23 -> 2026-07-14). Per CLAUDE.md OP-25, a re-violated lesson
graduates to a code assertion.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AUDIT_PATH = REPO / "setup" / "scripts" / "audit_window_leak_compliance.py"


def _load_audit():
    spec = importlib.util.spec_from_file_location("_wl_audit", AUDIT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit():
    return _load_audit()


def test_check_exists_and_covers_both_hiders(audit):
    """Both hiders must be enumerated. A check that only watches one of them leaves the
    other free to die unnoticed -- which is exactly what happened to the hook."""
    assert hasattr(audit, "_audit_hiders_running"), "check (6) is missing from the audit"
    labels = {h[0] for h in audit.HIDERS}
    assert "window_leak_hook" in labels, "the event-driven hook is not covered"
    assert "window-leak-detector" in labels, "the polling detector is not covered"


def test_dead_hider_is_flagged_RED(audit, monkeypatch, tmp_path):
    """RED-PROOF. Reproduces the real 2026-08-30 state: the pid file names a pid whose
    command line does NOT contain the hider's marker (dead, or the PID got reused)."""
    # Every pid reads as "not our process" -> both hiders look dead.
    monkeypatch.setattr(audit, "_pid_cmdline", lambda pid: "")
    monkeypatch.setattr(audit, "_registered_task_names",
                        lambda: {"Gamma_WindowLeakHookKeepalive",
                                 "Gamma_WindowLeakDetectorKeepalive"})
    monkeypatch.setattr(audit, "sys", sys)  # keep platform check intact

    if sys.platform != "win32":
        pytest.skip("hider-liveness check is win32-only")

    flags = audit._audit_hiders_running()
    kinds = [f["flag"] for f in flags]
    assert kinds.count("HIDER_NOT_RUNNING") == len(audit.HIDERS), (
        f"a dead hider must be flagged; got {kinds}")
    # The operator has to be able to tell WHICH hider and WHY it matters.
    blob = " ".join(f["detail"] for f in flags)
    assert "window_leak_hook" in blob and "window-leak-detector" in blob


def test_hider_with_no_keepalive_is_flagged(audit, monkeypatch):
    """The hook died because NOTHING restarted it. A live hider with no keepalive task is
    a future outage, so it is a violation now -- not after the next 20-day dark period."""
    if sys.platform != "win32":
        pytest.skip("hider-liveness check is win32-only")
    # Both hiders alive...
    monkeypatch.setattr(audit, "_pid_cmdline",
                        lambda pid: "window_leak_hook window-leak-detector")
    # ...but no keepalive tasks registered at all.
    monkeypatch.setattr(audit, "_registered_task_names", lambda: {"Gamma_Something_Else"})
    flags = audit._audit_hiders_running()
    kinds = [f["flag"] for f in flags]
    assert kinds.count("HIDER_NO_KEEPALIVE") == len(audit.HIDERS), (
        f"a hider with no keepalive must be flagged; got {kinds}")
    assert "HIDER_NOT_RUNNING" not in kinds, "alive hiders must not be reported as down"


def test_unreadable_task_registry_is_unknown_not_violation(audit, monkeypatch):
    """`None` from the registry read means UNKNOWN. Treating it as 'no keepalive exists'
    would fire a false RED every time the query times out -- and an audit that cries wolf
    gets ignored, which is how a real popup storm hides in the noise."""
    if sys.platform != "win32":
        pytest.skip("hider-liveness check is win32-only")
    monkeypatch.setattr(audit, "_pid_cmdline",
                        lambda pid: "window_leak_hook window-leak-detector")
    monkeypatch.setattr(audit, "_registered_task_names", lambda: None)
    flags = audit._audit_hiders_running()
    assert [f["flag"] for f in flags] == [], (
        "an unreadable registry must not manufacture HIDER_NO_KEEPALIVE flags")


def test_keepalive_script_and_installer_exist():
    """The fix has to be on disk, not just in a session transcript (C35)."""
    assert (REPO / "setup" / "scripts" / "window_leak_hook_keepalive.py").exists()
    assert (REPO / "setup" / "scripts" / "install-window-leak-hook-keepalive.ps1").exists()


def test_keepalive_chain_has_no_powershell():
    """The keepalive's own launch chain must not contain a .ps1 link. A PowerShell hop in
    the chain would leak the very console window this subsystem exists to suppress -- the
    documented reason window_leak_detector_keepalive.py replaced its .ps1 predecessor."""
    installer = (REPO / "setup" / "scripts" / "install-window-leak-hook-keepalive.ps1"
                 ).read_text(encoding="utf-8")
    action = [ln for ln in installer.splitlines() if "$wscriptArgs" in ln and "=" in ln]
    assert action, "installer must define the task action"
    line = action[0]

    # The action line references PowerShell variables, so resolve them against their
    # assignments rather than matching literals (the first draft of this test asserted on
    # the raw line and failed on correct code -- verify the harness, not just the target).
    def _assign(var: str) -> str:
        for ln in installer.splitlines():
            stripped = ln.strip()
            if stripped.startswith(f"${var}") and "=" in stripped:
                return stripped.split("=", 1)[1].strip()
        return ""

    assert "$vbs" in line and "$pythonw" in line, f"action must use the hidden chain: {line}"
    assert "run_exe_hidden.vbs" in _assign("vbs"), "$vbs must be the hidden VBS launcher"
    assert "pythonw.exe" in _assign("pythonw"), "$pythonw must be a GUI-subsystem pythonw"

    # No .ps1 anywhere in the chain: wscript -> vbs -> pythonw -> run_cmd_hidden -> pythonw.
    for var in ("vbs", "pythonw", "runCmdHidden", "script"):
        assert not _assign(var).endswith('.ps1"'), (
            f"${var} resolves to a .ps1 -- a PowerShell hop leaks the window this suppresses")


# --- surface 6: installed-plugin hooks -------------------------------------------------
# The 2026-08-09 lesson that shipped check (5) closed with a prediction: "The next
# recurrence will be surface #6 -- likely plugin- or marketplace-supplied hooks." It was
# right. A plugin ships hooks/hooks.json, Claude Code registers those hooks for every
# session, and none of the four settings paths the audit knew about names that file.


def test_plugin_hook_files_are_scanned(audit):
    """The audit must read INSTALLED plugins' hooks.json, not just settings.json."""
    assert hasattr(audit, "_installed_plugin_hook_files"), "surface 6 scanner is missing"
    plugin_sources = [p for p in audit.HOOK_CONFIG_SOURCES
                      if p.name == "hooks.json" and "plugins" in str(p)]
    if not (audit.PLUGINS_MANIFEST).is_file():
        pytest.skip("no plugin manifest on this box")
    assert plugin_sources, (
        "installed plugins declare hooks but HOOK_CONFIG_SOURCES names none of them")


def test_only_installed_plugins_scanned(audit):
    """Marketplace catalogs list plugins that are NOT installed; their hooks never run.
    Flagging them would train the reader to ignore this audit."""
    if not (audit.PLUGINS_MANIFEST).is_file():
        pytest.skip("no plugin manifest on this box")
    for p in audit.HOOK_CONFIG_SOURCES:
        if p.name == "hooks.json":
            assert "marketplaces" not in str(p).replace("\\", "/"), (
                f"marketplace (not-installed) hooks must not be scanned: {p}")


def test_missing_plugin_manifest_is_not_a_crash(audit, monkeypatch, tmp_path):
    """A box with no plugins installed must degrade to 'nothing to scan', not an exception
    -- an auditor that dies on a missing optional file reports nothing at all."""
    monkeypatch.setattr(audit, "PLUGINS_MANIFEST", tmp_path / "does-not-exist.json")
    assert audit._installed_plugin_hook_files() == []


# --- kwargs-helper exemption must not become a false NEGATIVE --------------------------
# Check (2) skips a call whose flags come via `**helper()` when that helper assigns
# creationflags. That exemption is the dangerous kind: a too-loose version would silently
# bless every `**kwargs` spawn on the box, and a popup would ship under a GREEN audit.


def _run_py_check(audit, monkeypatch, tmp_path, source: str):
    f = tmp_path / "sample.py"
    f.write_text(source, encoding="utf-8")
    monkeypatch.setattr(audit, "_iter_audit_py_files", lambda: iter([f]))
    monkeypatch.setattr(audit, "REPO", tmp_path)
    return audit._audit_py_missing_creationflags()


COMPLIANT = '''import subprocess
def _spawn_kwargs():
    kw = {}
    kw["creationflags"] = 0x08000000
    return kw
proc = subprocess.Popen(["x"], **_spawn_kwargs())
'''

NON_COMPLIANT = '''import subprocess
def _spawn_kwargs():
    return {"stdout": None}
proc = subprocess.Popen(["x"], **_spawn_kwargs())
'''


def test_kwargs_helper_that_sets_creationflags_is_exempt(audit, monkeypatch, tmp_path):
    assert _run_py_check(audit, monkeypatch, tmp_path, COMPLIANT) == [], (
        "a helper that DOES set creationflags must not be flagged (false positive)")


def test_kwargs_helper_without_creationflags_is_still_flagged(audit, monkeypatch, tmp_path):
    """RED-PROOF of the exemption. `**helper()` must not be a blanket escape hatch."""
    flags = _run_py_check(audit, monkeypatch, tmp_path, NON_COMPLIANT)
    assert [f["flag"] for f in flags] == ["PY_SUBPROCESS_NO_CREATIONFLAGS"], (
        f"a helper with NO creationflags must still be flagged; got {flags}")


def test_setup_mcp_is_in_scan_roots(audit):
    """The directory whose whole job is spawning children must be audited."""
    roots = {str(r).replace("\\", "/").lower() for r in audit.PY_AUDIT_ROOTS}
    assert any(r.endswith("setup/mcp") for r in roots), (
        "setup/mcp must be in PY_AUDIT_ROOTS -- it spawns every stdio MCP server")


# --- third-party hook severity must not become a blanket escape hatch ------------------
# A bare console launcher in a hook WE own stays a hard RED. Only a hook shipped inside a
# third-party plugin is downgraded to informational, because (a) its command lives in a
# cache dir overwritten on plugin update so no fix is available here, and (b) it was not
# observed to paint: btsc's PostToolUse bash hook fires on every Bash tool call and
# window_leak_hook.py logged ZERO hides outside the :00 scheduled-task burst.


def _hook_flags_for(audit, monkeypatch, tmp_path, path_name: str, command: str):
    import json as _json
    cfg = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
    f = tmp_path / path_name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(_json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(audit, "HOOK_CONFIG_SOURCES", [f])
    flags, scanned = audit._audit_hook_commands()
    assert scanned == 1
    return flags


def test_our_own_bare_hook_is_a_hard_violation(audit, monkeypatch, tmp_path):
    """RED-PROOF: a hook in a settings file we control must stay a real violation."""
    flags = _hook_flags_for(audit, monkeypatch, tmp_path, "settings.json", 'bash "x.sh"')
    assert len(flags) == 1
    assert flags[0]["flag"] == "HOOK_BARE_CONSOLE_LAUNCHER"
    assert flags[0].get("severity") != "info", "our own bare launcher must not be downgraded"


def test_third_party_plugin_hook_is_informational(audit, monkeypatch, tmp_path):
    """A plugin-shipped hook is reported but must not hold the audit permanently RED."""
    flags = _hook_flags_for(
        audit, monkeypatch, tmp_path, "plugins/cache/x/1.0/hooks/hooks.json", 'bash "x.sh"')
    assert len(flags) == 1, "the finding must still be REPORTED, never silently dropped"
    assert flags[0]["flag"] == "HOOK_BARE_CONSOLE_LAUNCHER_THIRDPARTY"
    assert flags[0]["severity"] == "info"


def test_compliant_hook_is_not_flagged(audit, monkeypatch, tmp_path):
    """Sanity: the wrapper chain must still pass, or the check is just noise."""
    flags = _hook_flags_for(
        audit, monkeypatch, tmp_path, "settings.json",
        r'C:\pythonw.exe C:\Users\jackw\.claude\scripts\hidden_hook.py npx thing')
    assert flags == [], f"the approved hidden-wrapper chain must not be flagged: {flags}"
