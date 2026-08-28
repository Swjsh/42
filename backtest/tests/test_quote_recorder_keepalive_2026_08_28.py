"""Guard: quote_recorder.py must actually stay alive, not just get verified once.

THE GAP (2026-08-28 conductor fire). quote_recorder.py (Task B1's independent
exit-quote NBBO side-channel) was built and verified the same day but never given
an always-on scheduled task -- self_check.py's own docstring for
check_quote_recorder_alive said arming one was "J's call" and left it there. It was
started manually once (~17:18 ET) and the moment that process exits,
check_quote_recorder_alive has no way to distinguish "never armed" from "armed and
died" (a status file that exists but goes stale reads RED forever, per its own
SILENT-UNTIL-DEPLOYED docstring) -- confirmed live: self-check-last.json read
verdict=BROKEN with "QUOTE-RECORDER RED: status file 21m stale ... has stopped"
minutes before this fix.

Mirrors the pattern already proven for every other always-on daemon in this repo
(window_leak_detector_keepalive.py / crypto_grinder_keepalive.py): a pid-liveness
probe cross-checked against the live process table, relaunch via system pythonw +
CREATE_NO_WINDOW|DETACHED_PROCESS if dead. No PowerShell in the fire chain
(OP-27 L41); no live-order/secret/CLAUDE.md surface touched (READ-ONLY recorder).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
KA = REPO / "setup" / "scripts" / "quote_recorder_keepalive.py"
INSTALLER = REPO / "setup" / "scripts" / "install-quote-recorder-keepalive.ps1"


@pytest.fixture(scope="module")
def ka():
    spec = importlib.util.spec_from_file_location("_qrka_probe", KA)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_qrka_probe"] = m
    spec.loader.exec_module(m)
    return m


def test_keepalive_script_exists():
    assert KA.exists(), "quote_recorder_keepalive.py is missing -- the recorder can never self-heal"


def test_installer_exists():
    assert INSTALLER.exists(), "install-quote-recorder-keepalive.ps1 is missing"


def test_never_deployed_is_treated_as_dead_not_crashed(ka, tmp_path, monkeypatch):
    """No status file at all (fresh checkout, or before the recorder's first-ever cycle)
    must read as 'not alive' so the keepalive launches it -- never assumes silence means OK."""
    monkeypatch.setattr(ka, "STATUS_FILE", tmp_path / "does-not-exist.json")
    alive, pid = ka._recorder_alive()
    assert alive is False and pid is None


def test_corrupt_status_file_is_treated_as_dead(ka, tmp_path, monkeypatch):
    f = tmp_path / "quote-recorder-status.json"
    f.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(ka, "STATUS_FILE", f)
    alive, pid = ka._recorder_alive()
    assert alive is False


def test_a_stale_pid_pointing_at_an_unrelated_process_is_NOT_alive(ka, tmp_path, monkeypatch):
    """THE CORE REGRESSION THIS GUARDS. If the keepalive trusted the pid number alone
    (never cross-checking the live process table), Windows recycling that pid into an
    unrelated process (a very common occurrence over hours/days) would falsely read
    'alive' forever and the recorder would never be relaunched -- reproducing exactly the
    QUOTE-RECORDER RED state this fix exists to close."""
    f = tmp_path / "quote-recorder-status.json"
    # os.getpid() is guaranteed alive right now and guaranteed NOT to be quote_recorder.py
    # (this test process), so this is a real live-but-wrong-process probe, not a fake pid.
    import os
    f.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    monkeypatch.setattr(ka, "STATUS_FILE", f)
    alive, pid = ka._recorder_alive()
    assert alive is False, (
        "keepalive read a pid belonging to an unrelated live process as 'alive' -- it must "
        "cross-check CommandLine against 'quote_recorder', not trust the pid number alone")


def test_a_genuinely_dead_pid_is_NOT_alive(ka, tmp_path, monkeypatch):
    """A pid that matches no live process at all (the common crash case) must relaunch."""
    f = tmp_path / "quote-recorder-status.json"
    # PID 999999 does not exist on any real Windows box.
    f.write_text(json.dumps({"pid": 999999}), encoding="utf-8")
    monkeypatch.setattr(ka, "STATUS_FILE", f)
    alive, pid = ka._recorder_alive()
    assert alive is False


def test_launch_uses_no_window_and_bounded_duration(ka):
    """The whole point of a keepalive is to be invisible (OP-27 L41) and self-recycling
    (2026-08-13 wedge lesson: unbounded runtime is a liability even for a light poller)."""
    src = KA.read_text(encoding="utf-8")
    i = src.index("def main(")
    body = src[i:i + 1500]
    assert "_CREATE_NO_WINDOW" in body
    assert "_DETACHED_PROCESS" in body
    assert "powershell" not in body.lower(), "no PowerShell in the launch chain (5/17 foot-gun)"
    assert "--duration-sec" in body, "recorder launched with no bound -- reopens the unbounded-runtime risk"
    assert hasattr(ka, "MAX_RUNTIME_S")
    assert 3600 <= ka.MAX_RUNTIME_S <= 7 * 24 * 3600, (
        f"MAX_RUNTIME_S={ka.MAX_RUNTIME_S}s is outside a sane 1h-7d recycle window")


def test_fail_open_wrapper_never_raises(ka):
    """This keepalive must never be the reason a scheduled fire shows non-zero (OP-33e)."""
    src = KA.read_text(encoding="utf-8")
    assert "_main_safe" in src
    assert "except Exception" in src


def test_installer_references_the_correct_files_and_chain():
    """Wiring check: the installer must point at THIS keepalive script and use the
    wscript -> run_exe_hidden.vbs -> run_cmd_hidden.py chain (no bare powershell.exe
    action, matching the 2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration)."""
    src = INSTALLER.read_text(encoding="utf-8")
    assert "quote_recorder_keepalive.py" in src
    assert "run_exe_hidden.vbs" in src
    assert "run_cmd_hidden.py" in src
    assert "wscript.exe" in src
    assert "Gamma_QuoteRecorderKeepalive" in src


def test_installer_supports_uninstall_for_a_clean_revert():
    src = INSTALLER.read_text(encoding="utf-8")
    assert "-Uninstall" in src
    assert "Unregister-ScheduledTask" in src


def test_installer_cadence_is_every_5_min_24_7():
    """Not RTH-gated at the scheduler level -- a crash overnight must be caught before the
    next session opens, not discovered cold at 08:55 (the recorder itself already
    self-gates its own polling to 08:55-16:05 ET; this is the keepalive's OWN cadence)."""
    src = INSTALLER.read_text(encoding="utf-8")
    assert "-RepetitionInterval (New-TimeSpan -Minutes 5)" in src


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
