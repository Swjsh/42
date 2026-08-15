"""Guard for self_check.check_llm_auth_outage -- the named, J-only-fixable outage.

WHY IT EXISTS (2026-08-15). The entire autonomous conductor was dead for five days and
nothing said so in words anyone would act on. Every LLM-driven task spawns `claude`, which
answered "Not logged in - Please run /login" and returned 1:

  * rail-0's budget precheck said PROCEED on every fire -- it measures SPEND, and a
    logged-out fire spends $0.00, so the gate that exists to stop wasted fires waved
    through 100% of them.
  * Task Scheduler showed LastTaskResult=0 because the outer wscript hop is
    fire-and-forget.
  * The one detector that DID notice, check_run_ps1_hidden_masked_exit, could only say
    `run-conductor-weekend.ps1 (exit=[1], 5x)` -- a generic non-zero exit sitting next to
    unrelated exit=1 noise, advising "check the named .ps1's own log".

Every layer reported success except the work. Measured at build time: 49 failed fires over
8 distinct tasks, 100% of conductor fires from 08-12 on.

The rig did not visibly break because the deterministic backstops held (eod_flatten.py for
the LLM EOD-flatten path, premarket_deterministic_fallback.py for premarket). That is the
actual danger this guard is about: a backstop silently carrying production looks exactly
like a healthy primary, right up until the backstop is what fails.

These tests are pure -- synthetic log files in tmp_path, a frozen clock. No network, no
real logs, no dependence on whether the rig happens to be logged in right now.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "self_check.py"

_spec = importlib.util.spec_from_file_location("self_check", MOD_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

NOW = dt.datetime(2026, 8, 15, 17, 0, 0)


def _log(d: Path, name: str, body: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


FIRE = ("2026-08-15 01:00:04 ET === START tick (timeout=600s effort=high model=sonnet) ===\n"
        "Not logged in · Please run /login\n"
        "2026-08-15 01:00:07 ET === END tick exit=1 ===\n")


def test_reports_the_outage_with_task_and_span(tmp_path):
    _log(tmp_path, "conductor-2026-08-15.log", FIRE)
    out = sc.check_llm_auth_outage(NOW, logs_dir=tmp_path)
    assert len(out) == 1
    msg = out[0]
    assert "LOGGED OUT" in msg
    assert "conductor" in msg
    assert "2026-08-15" in msg


def test_verdict_is_classified_broken_not_merely_degraded(tmp_path):
    """This must NOT read as advisory. A dead autonomous loop is BROKEN -- the repo's own
    _problem_is_broken keys off the substring, and the masked-exit siblings deliberately
    say DEGRADED because they have deterministic backstops. This one has no backstop:
    nothing self-heals an expired login."""
    _log(tmp_path, "conductor-2026-08-15.log", FIRE)
    msg = sc.check_llm_auth_outage(NOW, logs_dir=tmp_path)[0]
    assert "BROKEN" in msg
    assert sc._problem_is_broken(msg) is True


def test_names_j_action_and_forbids_automated_retry(tmp_path):
    """The whole point. `claude /login` is interactive OAuth -- an automated self-heal
    loop retrying into it burns fires forever and never recovers, so the message has to
    say so out loud rather than reading like a self-heal target."""
    _log(tmp_path, "conductor-2026-08-15.log", FIRE)
    msg = sc.check_llm_auth_outage(NOW, logs_dir=tmp_path)[0]
    assert "J ACTION REQUIRED" in msg
    assert "claude /login" in msg
    assert "nothing should retry" in msg


def test_aggregates_the_whole_fleet_not_one_task(tmp_path):
    """The signal the generic exit-code check could not give: ONE cause, whole fleet.
    Seeing 'conductor exit=1' and 'eod-flatten exit=1' as separate incidents is what let
    this run for five days."""
    _log(tmp_path, "conductor-2026-08-15.log", FIRE * 3)
    _log(tmp_path, "eod-flatten-2026-08-14.log", FIRE)
    _log(tmp_path, "premarket-2026-08-13.log", FIRE * 2)
    msg = sc.check_llm_auth_outage(NOW, logs_dir=tmp_path)[0]
    assert "6 LLM fire(s) across 3 task(s)" in msg
    assert "2026-08-13..2026-08-15" in msg
    assert "conductor (3x)" in msg and "premarket (2x)" in msg


def test_counts_fires_not_substring_hits(tmp_path):
    """Both signature strings live on ONE line per fire. Counting substrings would double
    every fire and turn a 3-fire outage into a reported 6."""
    _log(tmp_path, "conductor-2026-08-15.log", FIRE)
    msg = sc.check_llm_auth_outage(NOW, logs_dir=tmp_path)[0]
    assert "1 LLM fire(s)" in msg


def test_silent_when_the_fleet_is_logged_in(tmp_path):
    """A healthy rig must produce NOTHING -- a check that always speaks is noise, and this
    one is loud by design."""
    _log(tmp_path, "conductor-2026-08-15.log",
         "2026-08-15 01:00:04 ET === START tick ===\n"
         "2026-08-15 01:04:22 ET === END tick exit=0 ===\n")
    assert sc.check_llm_auth_outage(NOW, logs_dir=tmp_path) == []


def test_ignores_logs_older_than_the_lookback(tmp_path):
    """A cleared outage must stop being reported, or the alarm never goes green again and
    people learn to ignore it."""
    _log(tmp_path, "conductor-2026-07-14.log", FIRE)
    assert sc.check_llm_auth_outage(NOW, logs_dir=tmp_path, lookback_days=7) == []
    assert sc.check_llm_auth_outage(NOW, logs_dir=tmp_path, lookback_days=60) != []


def test_fails_open_on_a_missing_or_unreadable_log_dir(tmp_path):
    """Rail-2: an observer never raises and never blocks."""
    assert sc.check_llm_auth_outage(NOW, logs_dir=tmp_path / "nope") == []
    _log(tmp_path, "not-dated.log", FIRE)          # no date in the name -> skipped, not fatal
    assert sc.check_llm_auth_outage(NOW, logs_dir=tmp_path) == []


if __name__ == "__main__":  # pragma: no cover
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
