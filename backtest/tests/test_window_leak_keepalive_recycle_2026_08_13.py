"""Guard: the leak-detector keepalive must recycle a long-running detector, not just ping it.

THE INCIDENT (2026-08-13). J: "STOP THESE FUCKING CMD POPUS BEFORE I KILL MYSELF".
window-leak-summary.json read `polls_total: 3180000, leaks_total: 0`; window-leaks.jsonl had
logged nothing since 2026-07-14. The detector process was ALIVE the whole time -- the keepalive
checked exactly that and reported "detector alive (pid=8840)" every 5 minutes for 88 hours.

Restarting it produced 37 detections in 8 minutes, spread across the window (only 2 landed in
the first poll, so this was NOT a startup enumeration artifact). At ~4.6 leaks/min the old
process should have logged tens of thousands. It had stopped detecting while continuing to poll
and to write summaries.

PROCESS LIVENESS IS NOT DETECTION LIVENESS. Same distinction that let `exit=0` mean "nothing
raised" rather than "the work happened" in the fleet exit loop the same day.

The mitigation is deliberately a BOUNDED RECYCLE, not a cleverer wedge detector: the wedge's
mechanism is not understood, and "polls are advancing" cannot separate a wedged detector from a
genuinely quiet screen. Recycling removes the failure's ability to persist for days.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
KA = REPO / "setup" / "scripts" / "window_leak_detector_keepalive.py"


@pytest.fixture(scope="module")
def ka():
    spec = importlib.util.spec_from_file_location("_wlka_probe", KA)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_wlka_probe"] = m
    spec.loader.exec_module(m)
    return m


def test_a_recycle_age_is_defined_and_bounded(ka):
    """Too short thrashes the detector; too long lets a wedge live through a trading day."""
    assert hasattr(ka, "MAX_DETECTOR_AGE_S"), "the recycle threshold was removed"
    assert 3600 <= ka.MAX_DETECTOR_AGE_S <= 24 * 3600, (
        f"MAX_DETECTOR_AGE_S={ka.MAX_DETECTOR_AGE_S}s is outside 1h-24h. The incident ran 88h "
        "undetected; anything beyond a day re-opens that window.")


def test_the_incident_runtime_would_trigger_a_recycle(ka, tmp_path, monkeypatch):
    """THE REGRESSION. 3,180,000 polls x 0.1s = 88 hours -- the exact state that sat wedged."""
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"polls_total": 3180000, "poll_interval_s": 0.1}), encoding="utf-8")
    monkeypatch.setattr(ka, "SUMMARY_FILE", f)
    age = ka._detector_runtime_s()
    assert age is not None and age == pytest.approx(318000.0)
    assert age > ka.MAX_DETECTOR_AGE_S, (
        "the 88-hour wedged detector would NOT be recycled -- the incident can recur unchanged")


def test_a_freshly_started_detector_is_NOT_recycled(ka, tmp_path, monkeypatch):
    """Vary-and-assert: a rule that recycles unconditionally is not a rule, it is a restart loop."""
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"polls_total": 600, "poll_interval_s": 0.1}), encoding="utf-8")
    monkeypatch.setattr(ka, "SUMMARY_FILE", f)
    age = ka._detector_runtime_s()
    assert age == pytest.approx(60.0)
    assert age < ka.MAX_DETECTOR_AGE_S


@pytest.mark.parametrize("body", ["", "{}", "not json", '{"polls_total": "x"}'])
def test_an_unreadable_summary_does_NOT_trigger_a_recycle(ka, tmp_path, monkeypatch, body):
    """FAIL-SAFE DIRECTION. A transient read error must not restart the detector on every fire --
    that would turn a monitoring gap into a restart storm."""
    f = tmp_path / "s.json"
    f.write_text(body, encoding="utf-8")
    monkeypatch.setattr(ka, "SUMMARY_FILE", f)
    assert ka._detector_runtime_s() is None, (
        f"unreadable summary ({body!r}) returned a runtime; None is required so the caller "
        "leaves the detector alone")


def test_missing_summary_file_is_also_safe(ka, tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "SUMMARY_FILE", tmp_path / "does-not-exist.json")
    assert ka._detector_runtime_s() is None


def test_the_kill_helper_uses_no_window(ka):
    """This keepalive exists specifically to keep console windows off J's screen -- a recycle
    that spawns a visible taskkill console would be self-defeating."""
    src = KA.read_text(encoding="utf-8")
    i = src.index("def _kill")
    body = src[i:i + 500]
    assert "_CREATE_NO_WINDOW" in body, "the recycle's taskkill can flash a console window"
    assert "powershell" not in body.lower(), "no PowerShell in the keepalive chain (5/17 foot-gun)"


def test_process_liveness_alone_is_no_longer_the_whole_check(ka):
    """The premise of the fix. If main() goes back to returning on _detector_alive() with no age
    consideration, the 88-hour wedge is possible again."""
    src = "\n".join(l for l in KA.read_text(encoding="utf-8").splitlines()
                    if not l.strip().startswith("#"))
    i = src.index("def main(")
    body = src[i:]
    assert "MAX_DETECTOR_AGE_S" in body, (
        "main() no longer consults the recycle age -- it is back to pure process liveness, "
        "which reported 'alive' for 88 hours while nothing was being detected")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
