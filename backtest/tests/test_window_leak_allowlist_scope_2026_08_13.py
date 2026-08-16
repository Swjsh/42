"""Guard: a console host must never inherit an app's title allowlist (2026-08-13).

THE INCIDENT. J: "STOP THESE FUCKING CMD POPUS BEFORE I KILL MYSELF" (2026-08-13 ~10:40 ET),
while automation/state/window-leak-summary.json read:

    {"polls_total": 3180000, "leaks_total": 0, ...}

and automation/state/window-leaks.jsonl had recorded nothing since 2026-07-14 -- 422 leaks
logged historically, then silence, through a morning of visible console flashes.

ROOT CAUSE. `_is_allowed` matched the title-substring allowlist against EVERY suspect image.
The allowlist carries "Claude Code" so J's own terminal is not reported. A console host spawned
BY a Claude Code session INHERITS that console title, so a transient `powershell.exe` window
carried the title "Claude Code", matched, and was skipped entirely -- never logged, never
counted, never hidden.

The detector was not broken. It was exempting precisely the windows being complained about.
Third instance in one day of a green signal covering a live failure (the others: exit=0 while
an arm went unmanaged, and min_contracts still valid-looking at 2.75x stale equity).

THE FIX. A title match is honoured only for the app's OWN window image (TITLE_ALLOWLIST_IMAGES).
Console hosts are never exempted by an inherited title.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DET = REPO / "setup" / "scripts" / "window-leak-detector.py"

ALLOW = {"image_names": [], "pids": [],
         "title_substrings": ["Claude Code", "Claude in Chrome", "Apex Legends", "Steam", "Discord"]}


@pytest.fixture(scope="module")
def det():
    spec = importlib.util.spec_from_file_location("_wld_probe", DET)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_wld_probe"] = m
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------------ the incident


@pytest.mark.parametrize("image", ["powershell.exe", "cmd.exe", "conhost.exe", "OpenConsole.exe", "pwsh.exe"])
def test_a_console_host_is_NOT_exempted_by_an_inherited_title(det, image):
    """THE REGRESSION. This is the exact shape of the 2026-08-13 morning popups: a console
    spawned from a Claude Code session, carrying the parent's title."""
    assert det._is_allowed(image, "Claude Code - 42", 4242, ALLOW) is False, (
        f"{image} with an inherited 'Claude Code' title is still allowlisted -- the detector "
        "remains blind to exactly the windows J reported")


@pytest.mark.parametrize("title", ["Claude Code", "Steam", "Apex Legends", "Discord", "Claude in Chrome"])
def test_no_allowlisted_title_can_exempt_a_console_host(det, title):
    """Every entry in the shipped allowlist, not just the one that bit us."""
    assert det._is_allowed("powershell.exe", title, 1, ALLOW) is False


def test_the_apps_OWN_window_is_still_exempted(det):
    """The allowlist must keep doing its actual job -- J's real terminal is not a leak."""
    assert det._is_allowed("WindowsTerminal.exe", "Claude Code - 42", 1, ALLOW) is True
    assert det._is_allowed("WindowsTerminal.exe", "Steam", 1, ALLOW) is True


def test_an_unrelated_console_title_was_never_exempt_and_still_is_not(det):
    """Vary-and-assert: the fix must not have made everything unconditionally allowed."""
    assert det._is_allowed("powershell.exe", "Windows PowerShell", 1, ALLOW) is False


# ------------------------------------------------------------------ the other two doors


def test_explicit_image_and_pid_allowlists_still_work(det):
    """Those are DELIBERATE, operator-set exemptions and must be untouched by this scope fix."""
    assert det._is_allowed("powershell.exe", "anything", 1, dict(ALLOW, image_names=["powershell.exe"])) is True
    assert det._is_allowed("powershell.exe", "anything", 99, dict(ALLOW, pids=[99])) is True


def test_the_scope_set_is_narrow(det):
    """If TITLE_ALLOWLIST_IMAGES grows to include a console host, the bug is back."""
    assert "WindowsTerminal.exe" in det.TITLE_ALLOWLIST_IMAGES
    for banned in ("powershell.exe", "cmd.exe", "conhost.exe", "OpenConsole.exe", "pwsh.exe",
                   "python.exe", "pythonw.exe", "wscript.exe", "cscript.exe"):
        assert banned not in det.TITLE_ALLOWLIST_IMAGES, (
            f"{banned} was added to TITLE_ALLOWLIST_IMAGES -- a console host can once again be "
            "exempted by an inherited title, which is the 2026-08-13 blindness restored")


def test_console_hosts_are_still_scrutinised_at_all(det):
    """The premise. If powershell.exe leaves SUSPECT_IMAGES, none of the above matters."""
    for img in ("powershell.exe", "cmd.exe", "conhost.exe", "OpenConsole.exe"):
        assert img in det.SUSPECT_IMAGES, f"{img} is no longer scrutinised as a leak candidate"


def test_the_shipped_allowlist_still_contains_the_trigger_entry(det):
    """Provenance: if 'Claude Code' is ever removed from the allowlist the incident cannot
    recur by this route, and this guard should be re-derived rather than trusted."""
    p = REPO / "automation" / "state" / "window-leak-allowlist.json"
    if not p.exists():
        pytest.skip("allowlist absent")
    subs = json.loads(p.read_text(encoding="utf-8")).get("title_substrings", [])
    assert "Claude Code" in subs, (
        "'Claude Code' left the allowlist -- this guard's scenario no longer reflects the "
        "shipped config; re-derive it rather than assuming the fix is still load-bearing")


# ---------------------------------------------------------------------------
# 2026-08-15: the OPPOSITE failure -- the detector hid J's OWN terminal.
# ---------------------------------------------------------------------------
#
# The 08-13 fix above tightened the allowlist so a console host could not hide behind an
# inherited title. Two days later the detector ate J's interactive PowerShell window twice
# ("my powershell window is being auto closed"). Both records in window-leaks.jsonl:
#
#   image_name: WindowsTerminal.exe   title: "Windows PowerShell"   mitigated: true
#   ancestry:   WindowsTerminal.exe -> svchost.exe -> services.exe -> wininit.exe
#
# THE ANCESTRY GATE IS NOT BUGGY -- ITS PREMISE IS. `_is_service_rooted` assumes a terminal J
# opened himself descends from explorer.exe. Modern Windows Terminal launches by DCOM
# activation, so a Start-menu terminal is spawned by svchost with NO explorer.exe in the
# chain -- byte-identical to the service-rooted leak signature. Ancestry cannot separate them,
# so the title allowlist (already honoured for WindowsTerminal.exe by the 08-13 scope fix) is
# the only discriminator available.
#
# THE SPACE IS LOAD-BEARING. Automation-spawned shells are titled with a FULL PATH --
# "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" -- where "WindowsPowerShell" has
# no space. J's interactive window is the friendly name "Windows PowerShell". So the substring
# exempts his window and still hides the automation one.

_REAL_VENV_LEAK = r"C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe"
_REAL_PS_PATH_LEAK = r"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
_REAL_GIT_LEAK = r"C:\Program Files\Git\cmd\git.exe"


def _shipped_allowlist(det):
    import json
    return {**det.DEFAULT_ALLOWLIST,
            **json.loads(det.ALLOW_FILE.read_text(encoding="utf-8"))}


def test_js_own_interactive_terminal_is_exempt(det):
    """RED-PROOF, from the exact record that hid J's window on 2026-08-15."""
    allow = _shipped_allowlist(det)
    assert det._is_allowed("WindowsTerminal.exe", "Windows PowerShell", 5804, allow) is True


@pytest.mark.parametrize("title", [_REAL_VENV_LEAK, _REAL_PS_PATH_LEAK, _REAL_GIT_LEAK,
                                    "Terminal", "Windows Script Host"])
def test_real_automation_leaks_are_STILL_hidden(det, title):
    """The exemption must not buy J's window back at the cost of the popups he asked to
    have killed. Every title here is copied from real window-leaks.jsonl rows."""
    allow = _shipped_allowlist(det)
    assert det._is_allowed("WindowsTerminal.exe", title, 999, allow) is False


def test_the_path_titled_powershell_leak_is_not_caught_by_the_space(det):
    """The whole exemption rests on 'Windows PowerShell' (with a space) not being a substring
    of '...\\WindowsPowerShell\\v1.0\\...' (without one). If someone 'tidies' the allowlist
    entry to 'WindowsPowerShell', every automation shell silently becomes exempt."""
    allow = _shipped_allowlist(det)
    assert "Windows PowerShell" in allow["title_substrings"], (
        "the interactive-terminal exemption was removed -- J's own window will be hidden again")
    assert "WindowsPowerShell" not in allow["title_substrings"], (
        "space-less 'WindowsPowerShell' would exempt every automation-spawned shell too")
    assert det._is_allowed("WindowsTerminal.exe", _REAL_PS_PATH_LEAK, 999, allow) is False


def test_a_console_host_titled_windows_powershell_is_still_not_exempt(det):
    """The 08-13 scope fix must survive this addition: only WindowsTerminal.exe's OWN window
    may be exempted by title, never a console host that inherited it."""
    allow = _shipped_allowlist(det)
    for image in ("powershell.exe", "cmd.exe", "conhost.exe", "OpenConsole.exe"):
        assert det._is_allowed(image, "Windows PowerShell", 999, allow) is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
