"""Guard tests for setup/scripts/state_freshness_audit.py -- the silent-producer-death
detector built 2026-07-30 after the blind-engine incident (Gamma_LevelRefresh DISABLED ->
key-levels.json frozen at the 2026-07-29 session -> heartbeat_core._read_levels correctly
returned ([],[]) -> the engine silently switched to trendline-only entries, its worst
cohort, and produced 11 ENTER_BEAR verdicts at the low of the day).

The audit's job is to make that visible BEFORE it costs a day, and to keep being visible
after the close -- the two existing instruments both went quiet:
  * engine_health.check_level_feed short-circuits to GREEN when market_open is False,
    so at 18:46 ET it reported GREEN on a 1,199-minute-stale file.
  * audit_scheduled_tasks.py's SILENT_TASK loop opens with
    ``if state == "Disabled": continue`` -- a documented-ACTIVE-but-DISABLED task is
    silent by construction.

Coverage (each is a RED-proofed contract -- see the docstring on each test for the exact
defect it re-detects):
  * a stale file REDs and the reason NAMES the file + its writer + its task
  * a fresh file is GREEN
  * criticality drives escalation (medium staleness is YELLOW, not RED)
  * the date axis is NOT market-hours suppressed -- it REDs after the close
  * the date axis is quiet BEFORE the producer's ready time (no 07:00 false RED)
  * the age axis is quiet while the producer's duty window is CLOSED
  * an unreadable manifest fails OPEN with UNKNOWN and never raises
  * a malformed manifest fails OPEN with UNKNOWN and never raises
  * a malformed/unreadable STATE FILE is UNKNOWN, never a RED mistaken for evidence
  * engine_health.check_state_freshness is NON-CRITICAL and fails open to YELLOW

Pure filesystem + a frozen clock. No network, no broker, no LLM.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import state_freshness_audit as sfa  # noqa: E402

# Thursday 2026-07-30 18:46 ET -- the exact wall-clock at which every existing
# instrument reported GREEN on the outage.
AFTER_CLOSE = datetime(2026, 7, 30, 18, 46, 0)
MIDDAY = datetime(2026, 7, 30, 12, 0, 0)
PREMARKET = datetime(2026, 7, 30, 7, 0, 0)

NO_HOLIDAYS: set = set()


def _entry(**kw) -> dict:
    base = {
        "path": "key-levels.json",
        "writer": "refresh_levels_intraday.py",
        "task": "Gamma_LevelRefresh",
        "criticality": "critical",
        "max_age_min": 20,
        "date_field": "for_session",
        "date_expected_after_et": "09:35",
        "window_et": None,
        "weekdays_only": True,
    }
    base.update(kw)
    return base


def _write(tmp: Path, name: str, payload: dict) -> None:
    (tmp / name).write_text(json.dumps(payload), encoding="utf-8")


# ============================================================================
# The core contract: stale -> RED naming the file; fresh -> GREEN
# ============================================================================

def test_stale_file_reds_and_names_the_file(tmp_path):
    """RED-PROOF TARGET: the 2026-07-30 outage itself. key-levels.json stamped with the
    PRIOR session while today is a session day. Must RED, and the reason must name the
    file, its writer and its scheduled task -- a RED that does not say WHICH producer
    died is a RED J has to investigate by hand."""
    _write(tmp_path, "key-levels.json", {"for_session": "2026-07-29"})
    r = sfa.evaluate_entry(_entry(), AFTER_CLOSE, NO_HOLIDAYS, repo=tmp_path)
    assert r["status"] == "RED"
    joined = " ".join(r["reasons"])
    assert "key-levels.json" in joined
    assert "2026-07-29" in joined and "2026-07-30" in joined
    assert "refresh_levels_intraday.py" in joined
    assert "Gamma_LevelRefresh" in joined


def test_fresh_file_is_green(tmp_path):
    """The inverse: a file stamped with TODAY's session on a session day is GREEN.
    Without this the detector could 'pass' by REDing unconditionally."""
    _write(tmp_path, "key-levels.json", {"for_session": "2026-07-30"})
    r = sfa.evaluate_entry(_entry(), AFTER_CLOSE, NO_HOLIDAYS, repo=tmp_path)
    assert r["status"] == "GREEN", r["reasons"]
    assert r["reasons"] == []


def test_criticality_drives_escalation(tmp_path):
    """A medium-criticality shadow file (trendlines-live.json) going stale must NOT RED
    the same way a critical one does -- otherwise the beacon cries wolf and J stops
    reading it, which is how the 06-22 three-day-unalerted incident happened."""
    _write(tmp_path, "key-levels.json", {"for_session": "2026-07-29"})
    r = sfa.evaluate_entry(_entry(criticality="medium"), AFTER_CLOSE, NO_HOLIDAYS,
                           repo=tmp_path)
    assert r["status"] == "YELLOW"


# ============================================================================
# The axis that the existing instruments lacked
# ============================================================================

def test_date_axis_is_not_market_hours_suppressed(tmp_path):
    """RED-PROOF TARGET: engine_health.check_level_feed's
    ``if not market_open: return GREEN`` short-circuit. At 18:46 ET (market CLOSED) a
    file stamped with the prior session must still RED. If this ever goes GREEN the
    audit has re-acquired the exact blindness it was built to remove."""
    _write(tmp_path, "key-levels.json", {"for_session": "2026-07-29"})
    r = sfa.evaluate_entry(_entry(), AFTER_CLOSE, NO_HOLIDAYS, repo=tmp_path)
    assert r["status"] == "RED"
    assert "STALE BY SESSION" in " ".join(r["reasons"])


def test_date_axis_quiet_before_producer_ready_time(tmp_path):
    """No false RED at 07:00 ET: before ``date_expected_after_et`` the producer has not
    yet run for today, so the PRIOR session's stamp is the correct expectation."""
    _write(tmp_path, "key-levels.json", {"for_session": "2026-07-29"})
    r = sfa.evaluate_entry(_entry(), PREMARKET, NO_HOLIDAYS, repo=tmp_path)
    assert r["status"] == "GREEN", r["reasons"]
    assert r["expected_session"] == "2026-07-29"


def test_expected_session_walks_back_over_weekend_and_holidays():
    """Monday premarket must expect FRIDAY's stamp, not Sunday's -- a naive
    ``today - 1 day`` would emit a weekend-wide false RED every Monday morning."""
    monday_premarket = datetime(2026, 8, 3, 7, 0, 0)  # Mon
    assert sfa.expected_session_date(monday_premarket, "09:35", NO_HOLIDAYS) == "2026-07-31"
    # With Friday 07-31 a holiday, walk back to Thursday 07-30.
    assert sfa.expected_session_date(monday_premarket, "09:35", {"2026-07-31"}) == "2026-07-30"


def test_age_axis_quiet_while_producer_window_closed(tmp_path):
    """A 5-min RTH producer is legitimately silent overnight. The AGE axis must respect
    ``window_et``; only the date axis asserts through the close."""
    _write(tmp_path, "ctx.json", {"computed_at_et": "2026-07-30T15:55:00"})
    e = _entry(path="ctx.json", date_field="computed_at_et", criticality="medium",
               max_age_min=25, window_et=["09:30", "16:05"], task="Gamma_ContextBundle")
    r = sfa.evaluate_entry(e, AFTER_CLOSE, NO_HOLIDAYS, repo=tmp_path)
    assert r["status"] == "GREEN", r["reasons"]
    assert r["window_open"] is False


def test_age_axis_reds_inside_the_window(tmp_path):
    """...and it must actually fire while the window IS open, or the suppression above
    would silently disable the whole age axis."""
    _write(tmp_path, "ctx.json", {"computed_at_et": "2026-07-30T09:35:00"})
    e = _entry(path="ctx.json", date_field="computed_at_et", criticality="critical",
               max_age_min=25, window_et=["09:30", "16:05"], task="Gamma_ContextBundle")
    r = sfa.evaluate_entry(e, MIDDAY, NO_HOLIDAYS, repo=tmp_path)
    assert r["status"] == "RED"
    assert "STALE BY AGE" in " ".join(r["reasons"])


# ============================================================================
# FAIL-OPEN contract (this is a MONITOR: it must never take the caller down)
# ============================================================================

def test_unreadable_manifest_fails_open_unknown(tmp_path):
    """HOUSE RULE: monitoring fails OPEN. A missing manifest yields UNKNOWN with an
    empty entry list -- never an exception, and never a GREEN that would read as
    'everything is fresh' when nothing was actually checked."""
    rep = sfa.audit(manifest_path=tmp_path / "does-not-exist.json", repo=tmp_path,
                    now_et=AFTER_CLOSE)
    assert rep["verdict"] == "UNKNOWN"
    assert rep["entries"] == []
    assert "unreadable" in (rep["reason"] or "")


def test_load_manifest_returns_error_never_raises(tmp_path):
    """BOTH layers of the fail-open must hold independently. ``audit()`` has a catch-all
    that would mask a raising ``load_manifest``, so pin the inner layer directly --
    otherwise a future refactor that drops the catch-all silently re-arms the crash."""
    missing, err = sfa.load_manifest(tmp_path / "nope.json")
    assert missing == [] and "unreadable" in err
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    entries, err2 = sfa.load_manifest(bad)
    assert entries == [] and "malformed" in err2


def test_malformed_manifest_fails_open_unknown(tmp_path):
    """Same contract for a manifest that exists but is not valid JSON."""
    bad = tmp_path / "manifest.json"
    bad.write_text("{not json at all", encoding="utf-8")
    rep = sfa.audit(manifest_path=bad, repo=tmp_path, now_et=AFTER_CLOSE)
    assert rep["verdict"] == "UNKNOWN"
    assert rep["entries"] == []


def test_manifest_without_entries_list_fails_open_unknown(tmp_path):
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({"_doc": "no entries key"}), encoding="utf-8")
    rep = sfa.audit(manifest_path=m, repo=tmp_path, now_et=AFTER_CLOSE)
    assert rep["verdict"] == "UNKNOWN"


def test_malformed_state_file_is_unknown_not_red(tmp_path):
    """An unparseable STATE file is monitor-side ambiguity, not proof of a dead producer.
    Reporting it RED would put a fake root cause in front of J."""
    (tmp_path / "key-levels.json").write_text("{broken", encoding="utf-8")
    r = sfa.evaluate_entry(_entry(), AFTER_CLOSE, NO_HOLIDAYS, repo=tmp_path)
    assert r["status"] == "UNKNOWN"
    assert "malformed json" in " ".join(r["reasons"])


def test_missing_state_file_reds_for_critical(tmp_path):
    """A file the decision path READS that is not on disk at all is unambiguous."""
    r = sfa.evaluate_entry(_entry(), AFTER_CLOSE, NO_HOLIDAYS, repo=tmp_path)
    assert r["status"] == "RED"
    assert "MISSING" in " ".join(r["reasons"])


def test_audit_never_raises_on_a_hostile_manifest(tmp_path):
    """Belt-and-braces: entries of the wrong shape are dropped or absorbed, never raised."""
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({"entries": [
        "not-a-dict", {"no_path_key": 1},
        {"path": "x.json", "criticality": "nonsense-tier", "date_field": 12345},
    ]}), encoding="utf-8")
    rep = sfa.audit(manifest_path=m, repo=tmp_path, now_et=AFTER_CLOSE)
    assert rep["verdict"] in ("GREEN", "YELLOW", "RED", "UNKNOWN")


# ============================================================================
# The SHIPPED manifest must stay honest
# ============================================================================

def test_shipped_manifest_is_wellformed_and_covers_key_levels():
    """The manifest is the registry of what the live path reads. If it stops parsing,
    or key-levels.json falls out of it, the audit silently narrows -- the exact
    'monitor degrades quietly' failure this whole workstream exists to kill."""
    entries, err = sfa.load_manifest(sfa.DEFAULT_MANIFEST)
    assert err is None, err
    assert len(entries) >= 15
    paths = {e["path"] for e in entries}
    assert "automation/state/key-levels.json" in paths
    for e in entries:
        assert e.get("criticality") in ("critical", "high", "medium", "low", "info"), e["path"]
        assert e.get("writer"), e["path"]
        assert e.get("task"), e["path"]
        # Every entry must carry at least ONE freshness contract, or it is decoration.
        assert e.get("date_field") or e.get("max_age_min") is not None, e["path"]


def test_shipped_manifest_cites_no_phantom_writers():
    """L249: a manifest that cites a writer script which does not exist is worse than no
    manifest -- it sends whoever reads a RED to a file that was never built. This test
    caught a real one on the first run (``setup/scripts/ema_snapshot.py``; the actual
    writer is ``automation/scripts/compute_ema_snapshot.py``)."""
    import re  # noqa: PLC0415

    entries, err = sfa.load_manifest(sfa.DEFAULT_MANIFEST)
    assert err is None, err
    phantoms = []
    for e in entries:
        for tok in re.findall(r"[A-Za-z0-9_./\\-]+\.(?:py|md)", e.get("writer") or ""):
            if not (REPO / tok).exists():
                phantoms.append(f"{e['path']} -> {tok}")
    assert not phantoms, f"manifest cites non-existent writers: {phantoms}"


# ============================================================================
# engine_health wiring
# ============================================================================

def test_engine_health_check_is_non_critical_and_named():
    """The check must be NON-CRITICAL (monitoring never trade-halts) and keep a stable
    name -- engine_health's alerter is idempotent on the SET of red check names, so a
    renamed check re-pings J for an outage he was already told about."""
    import engine_health as eh  # noqa: PLC0415
    r = eh.check_state_freshness(AFTER_CLOSE)
    assert r["name"] == "state_freshness"
    assert r["critical"] is False
    assert r["status"] in ("GREEN", "YELLOW", "RED")


def test_engine_health_check_fails_open_when_audit_unknown(monkeypatch):
    """RED-PROOF TARGET: an audit that CANNOT RUN must never look like an audit that
    PASSED. UNKNOWN maps to YELLOW, never GREEN."""
    import engine_health as eh  # noqa: PLC0415
    monkeypatch.setattr(sfa, "audit",
                        lambda *a, **k: {"verdict": "UNKNOWN", "reason": "manifest unreadable",
                                         "entries": []})
    r = eh.check_state_freshness(AFTER_CLOSE)
    assert r["status"] == "YELLOW"
    assert r["critical"] is False


def test_engine_health_check_never_raises(monkeypatch):
    """If the audit module explodes outright, the beacon must still produce a check."""
    import engine_health as eh  # noqa: PLC0415

    def _boom(*a, **k):
        raise RuntimeError("simulated audit explosion")

    monkeypatch.setattr(sfa, "audit", _boom)
    r = eh.check_state_freshness(AFTER_CLOSE)
    assert r["status"] == "YELLOW"
    assert r["critical"] is False


def test_et_minus_local_offset_is_a_property_of_the_date_not_of_now():
    """RED-PROOF for the 2026-08-15 flaky-guard defect.

    The AGE axis converted a LOCAL mtime to ET with
    `round((now_et - datetime.now()).total_seconds()/3600)`. That is only an offset when
    `now_et` IS now; under this file's own fixed PREMARKET clock it evaluated to -389, and
    because it rounds to whole HOURS the sub-hour remainder leaked into age_min as a phantom
    age (measured: 18.5-20.9 minutes, drifting minute-by-minute). Against key-levels.json's
    20m budget that made `test_date_axis_quiet_before_producer_ready_time` pass or fail purely
    on what time of the hour the suite ran -- it passed in isolation and failed in-batch 20
    minutes earlier. The flakiness was a real impurity in the PRODUCER, not test noise.

    A timezone offset is a property of a DATE, so it must stay bounded for any clock.
    """
    for clock in (PREMARKET, AFTER_CLOSE, datetime(2020, 1, 2, 3, 4),
                  datetime(2026, 12, 25, 9, 0)):
        off = sfa._et_minus_local_hours(clock)
        assert -12 <= off <= 12, f"{clock} -> {off}h is a clock difference, not an offset"


def test_age_axis_reports_no_phantom_age_under_a_frozen_clock(tmp_path):
    """The end-to-end shape of the same defect. The fixture file is written NOW and evaluated
    under a FIXED PAST clock, so its honest age relative to that clock is strongly NEGATIVE
    (the file did not exist yet). The broken offset masked that with a small POSITIVE number
    -- the rounding remainder, measured at +18.5 to +20.9m -- which is exactly what crossed
    key-levels.json's 20m budget and made this file flaky. Sign is the discriminator: a small
    positive age here means the offset arithmetic is manufacturing it again."""
    _write(tmp_path, "key-levels.json", {"for_session": "2026-07-29"})
    r = sfa.evaluate_entry(_entry(), PREMARKET, NO_HOLIDAYS, repo=tmp_path)
    assert r["status"] == "GREEN", r["reasons"]
    assert r["age_min"] < 0, (
        f"age_min={r['age_min']}m is positive for a file written AFTER the frozen clock -- "
        "the ET-minus-local offset is being derived from the wall clock again")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
