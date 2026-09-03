"""Guard for prereg_hygiene's RESULT_EXISTS_STATUS_STALE flag class (2026-09-03,
queue item PREREG-RESULT-EXISTS-STATUS-STALE).

THE GAP THIS CLOSES: four real preregs (favorable-extreme-entry, morning-gate,
regime-conditioned-validation, block-elite-bull-ssb) sat at FROZEN_PENDING_RUN for
48-55 days although their runner had already written a results file weeks earlier --
nothing ever wrote the verdict back to the prereg's own `status` field. The existing
`stale_status_but_has_results` key (2026-09-02 fix) already computed this SHAPE but
only for the narrow STALE_STATUS_RE vocabulary (FROZEN/NOT RUN/NOT SHIPPED). This
flag class widens the vocabulary to the full set of pending/frozen status strings
actually observed across the 128 real prereg files (PRE-REGISTERED, PARKED,
CANDIDATE ONLY, NOT IMPLEMENTED, NOT BUILT, ...), is AGE-INDEPENDENT (unlike the
`flagged` list, which requires age>14d), and enriches each hit with the matched
result file's own mtime + verdict/status field so a reader never has to open the
result file by hand.

Pins:
  - a pending-status prereg with a matching result file is reported in
    `result_exists_status_stale`, with `result_mtime_utc` and `result_verdict`
    populated from the result file itself
  - a TERMINAL status (RUN_COMPLETE*, KILLED, RETIRED_UNRUNNABLE_AS_FROZEN, etc.)
    with a matching result file is NEVER reported here, even though the result
    exists -- the status field already carries (or explicitly closes out) its own
    verdict, there is nothing stale about it
  - a pending-status prereg with NO matching result file is NEVER reported here --
    it is genuinely awaiting a run, not stale bookkeeping
  - the flag fires regardless of age (unlike `flagged`) -- a result written
    yesterday against a status that still says FROZEN_PENDING_RUN is exactly as
    stale as one from 55 days ago
  - a status containing the substring FROZEN that ALSO carries an explicit
    terminal token (e.g. "RETIRED_UNRUNNABLE_AS_FROZEN") must NOT flag --
    TERMINAL_STATUS_RE wins over PENDING_STATUS_RE on conflict
  - the report JSON carries `n_result_exists_status_stale` / `result_exists_status_stale`
    as an ADDITIVE schema change (existing keys `flagged` / `stale_status_but_has_results`
    are untouched)
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_PH_PATH = _REPO / "setup" / "scripts" / "prereg_hygiene.py"
_spec = importlib.util.spec_from_file_location("prereg_hygiene_result_stale_under_test", _PH_PATH)
prereg_hygiene = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prereg_hygiene)


def _write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    recs = tmp_path / "analysis" / "recommendations"
    recs.mkdir(parents=True)
    setup_dir = tmp_path / "setup"
    setup_dir.mkdir()
    backtest_dir = tmp_path / "backtest"
    backtest_dir.mkdir()
    automation_dir = tmp_path / "automation" / "overnight"
    automation_dir.mkdir(parents=True)
    status_md = automation_dir / "STATUS.md"
    status_md.write_text("# status\n", encoding="utf-8")

    monkeypatch.setattr(prereg_hygiene, "REPO", tmp_path)
    monkeypatch.setattr(prereg_hygiene, "RECS_DIR", recs)
    monkeypatch.setattr(prereg_hygiene, "ANALYSIS_DIR", tmp_path / "analysis")
    monkeypatch.setattr(prereg_hygiene, "OUT_FILE", recs / "prereg-hygiene.json")
    monkeypatch.setattr(prereg_hygiene, "STATUS_MD", status_md)
    monkeypatch.setattr(prereg_hygiene, "SEARCH_DIRS", ["setup", "backtest", "automation"])
    monkeypatch.setattr(prereg_hygiene, "EXCLUDE_PATHS", {status_md.resolve()})
    monkeypatch.setattr(prereg_hygiene, "_referenced_stems", lambda stems: None)
    return {"recs": recs, "status_md": status_md}


def test_pending_status_with_result_flags_and_is_enriched(sandbox):
    """The core shape: PRE-REGISTERED (not in the narrow STALE_STATUS_RE vocabulary)
    + a matching result file -> must appear in result_exists_status_stale, with the
    result file's own mtime and verdict populated."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-favorable-extreme-entry-2026-07-17.json"
    _write(prereg, {"status": "PRE-REGISTERED", "frozen_at_et": "2026-07-17T00:00:00"})
    _write(recs / "favorable-extreme-entry-2026-07-17.json", {
        "prereg_path": "analysis/recommendations/prereg-favorable-extreme-entry-2026-07-17.json",
        "verdict": "KILL -- no edge",
    })
    report = prereg_hygiene.scan()
    hits = {r["file"]: r for r in report["result_exists_status_stale"]}
    assert prereg.name in hits, "PRE-REGISTERED + matching result must flag"
    row = hits[prereg.name]
    assert row["result_file"] == "favorable-extreme-entry-2026-07-17.json"
    assert row["result_verdict"] == "KILL -- no edge"
    assert row["result_mtime_utc"] is not None
    assert report["n_result_exists_status_stale"] == 1


def test_terminal_status_with_result_does_not_flag(sandbox):
    """A prereg whose status is already terminal (RUN_COMPLETE variant) must NOT be
    reported even though a result file matches -- its status already carries the
    verdict, there is nothing stale to reconcile."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-widget-done-2026-07-17.json"
    _write(prereg, {
        "status": "RUN_COMPLETE -- KEEP", "frozen_at_et": "2026-07-17T00:00:00",
        "rule_id": "WIDGET-DONE-2026-07-17",
    })
    _write(recs / "widget-done-2026-07-17-results.json", {
        "rule_id": "WIDGET-DONE-2026-07-17", "verdict": "KEEP",
    })
    report = prereg_hygiene.scan()
    hits = {r["file"] for r in report["result_exists_status_stale"]}
    assert prereg.name not in hits


def test_pending_status_without_result_does_not_flag(sandbox):
    """Genuinely awaiting a run (pending status, no result file anywhere) must not
    be reported -- that is the OTHER, age-gated flag class's job (`flagged`), not
    this one."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-still-waiting-2026-08-20.json"
    _write(prereg, {"status": "FROZEN_PENDING_RUN", "frozen_at_et": "2026-08-20T00:00:00"})
    report = prereg_hygiene.scan()
    hits = {r["file"] for r in report["result_exists_status_stale"]}
    assert prereg.name not in hits


def test_terminal_substring_frozen_excluded(sandbox):
    """RED-PROOF: TERMINAL_STATUS_RE must win over PENDING_STATUS_RE on conflict.
    A status containing the substring FROZEN but ALSO an explicit terminal token
    (the real RETIRED_UNRUNNABLE_AS_FROZEN shape) must not flag even with a
    matching result file."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-level-memory-wire-2026-07-15.json"
    _write(prereg, {
        "status": "RETIRED_UNRUNNABLE_AS_FROZEN -- not a verdict on the hypothesis",
        "frozen_at_et": "2026-07-15T00:00:00",
    })
    _write(recs / "level-memory-wire.json", {
        "note": "retired study for prereg-level-memory-wire-2026-07-15",
        "verdict": "N/A",
    })
    report = prereg_hygiene.scan()
    hits = {r["file"] for r in report["result_exists_status_stale"]}
    assert prereg.name not in hits, "RETIRED terminal token must beat the FROZEN substring"


def test_flag_is_age_independent(sandbox):
    """RED-PROOF the age-independence claim: a prereg frozen TODAY (age ~0d, well
    under the 14d AGE_DAYS_THRESHOLD used by the OTHER flag class) with a pending
    status and a matching result file must still flag here."""
    recs = sandbox["recs"]
    today = prereg_hygiene._et_ts()[:10]
    prereg = recs / f"prereg-fresh-{today}.json"
    _write(prereg, {"status": "PARKED -- BLOCKED ON J SIGN-OFF", "frozen_at_et": f"{today}T00:00:00"})
    _write(recs / f"fresh-{today}-results.json", {"status": "SHIP"})
    report = prereg_hygiene.scan()
    hits = {r["file"]: r for r in report["result_exists_status_stale"]}
    assert prereg.name in hits
    assert hits[prereg.name]["age_days"] < prereg_hygiene.AGE_DAYS_THRESHOLD
    # And it must NOT also appear in the age-gated `flagged` list's reasoning path
    # being the only thing keeping it out of `flagged` -- flagged requires age>14d,
    # so a same-day prereg must never land there regardless of status text.
    assert all(f["file"] != prereg.name for f in report["flagged"])


def test_pending_vocabulary_covers_pre_registered_and_parked(sandbox):
    """RED-PROOF the vocabulary widening itself: PRE-REGISTERED and PARKED are NOT
    matched by the narrow STALE_STATUS_RE (used by the original age-gated `flagged`
    list) but MUST be matched by the new PENDING_STATUS_RE used here."""
    assert prereg_hygiene.STALE_STATUS_RE.search("PRE-REGISTERED") is None
    assert prereg_hygiene.PENDING_STATUS_RE.search("PRE-REGISTERED") is not None
    assert prereg_hygiene.STALE_STATUS_RE.search("PARKED -- blocked") is None
    assert prereg_hygiene.PENDING_STATUS_RE.search("PARKED -- blocked") is not None


def test_additive_schema_does_not_remove_existing_keys(sandbox):
    """The new keys must be ADDITIVE -- existing consumers reading `flagged`,
    `stale_status_but_has_results`, `entries[].has_results_file` must see them
    completely unchanged in shape."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-untouched-2026-08-01.json"
    _write(prereg, {"status": "FROZEN -- NOT RUN", "frozen_at_et": "2026-08-01T00:00:00"})
    report = prereg_hygiene.scan()
    for key in ("n_total", "n_parsed", "n_malformed", "malformed", "n_flagged", "flagged",
                "n_has_results_file", "stale_status_but_has_results", "entries"):
        assert key in report, f"pre-existing key {key} must still be present"
    assert "n_result_exists_status_stale" in report
    assert "result_exists_status_stale" in report


def test_status_md_block_includes_result_exists_section(sandbox):
    """main()'s STATUS.md append must surface the new class by name, not just the
    JSON file -- a nightly reader skimming STATUS.md must be able to see it without
    opening prereg-hygiene.json."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-morning-gate-2026-07-11.json"
    _write(prereg, {"status": "PRE-REGISTERED", "frozen_at_et": "2026-07-11T00:00:00"})
    _write(recs / "morning-gate-result.json", {
        "registration": "analysis/recommendations/prereg-morning-gate-2026-07-11.json",
        "verdict": "SUPERSEDED",
    })
    report = prereg_hygiene.scan()
    wrote = prereg_hygiene._append_status_block(report)
    assert wrote is True
    text = sandbox["status_md"].read_text(encoding="utf-8")
    assert "RESULT_EXISTS_STATUS_STALE" in text
    assert prereg.name in text
