"""Guard: gamma_home.py regenerates autonomy-report.json on every build.

Root cause (2026-09-04): setup/scripts/autonomy_report.py had NO caller and NO
scheduled task, so automation/state/autonomy-report.json froze at 2026-08-16
while gamma_standup.py kept reading it as if fresh. Fix: gamma_home's page build
(Gamma_Home, every 30 min) calls autonomy_report.main([]) fail-open.

RED-PROOF: with the `_refresh_autonomy_report()` call line removed from
build_payload, test_build_calls_autonomy_report fails on `assert called == [[]]`.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))


def test_refresh_helper_calls_autonomy_report_main(monkeypatch):
    import autonomy_report
    import gamma_home
    called = []
    monkeypatch.setattr(autonomy_report, "main", lambda argv=None: called.append(argv) or 0)
    assert gamma_home._refresh_autonomy_report() is True
    assert called == [[]]


def test_refresh_helper_fails_open(monkeypatch):
    import autonomy_report
    import gamma_home

    def boom(argv=None):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(autonomy_report, "main", boom)
    assert gamma_home._refresh_autonomy_report() is False


def test_page_build_source_invokes_refresh():
    src = (REPO / "setup" / "scripts" / "gamma_home.py").read_text(encoding="utf-8")
    after_def = src.split("def _refresh_autonomy_report", 1)[1]
    assert "    _refresh_autonomy_report()\n" in after_def, "page build no longer refreshes autonomy-report.json"
