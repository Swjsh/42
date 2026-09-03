"""Guard for the prereg hygiene monitor (B3-monitors, 2026-09-01).

Pre-registrations are frozen commitments (design + pass/fail criterion written before
any outcome). This monitor surfaces three silent-rot signatures on
analysis/recommendations/*prereg*.json: malformed JSON, staleness (FROZEN/NOT RUN
status sitting for >14 days), and orphaning (nothing in the live pipeline references
the file any more, so its kill/arm criteria can never fire).

Pins:
  - malformed JSON is reported by name + parse error, never silently skipped
  - status extraction prefers `status`, falls back to the first `*verdict*` key
  - age priority: frozen_at_et/frozen_at field > filename date > mtime fallback
  - flagging requires stale-status text AND age > 14d. `orphan` is INFORMATIONAL ONLY
    (ORPHAN-PROXY-IS-SELF-SILENCING FIX, 2026-09-02) -- it no longer gates the flag.
    A prereg mentioned in queue.md/STATUS.md/a work order (i.e. NOT an orphan) must
    still flag once frozen+stale+old, because writing ABOUT a stale prereg used to
    silence its own monitor (observed live: flagged count 6 -> 0 with nothing
    resolved, purely because the adjudication write-up named all six by filename).
  - the STATUS.md append is DEDUPED -- an unchanged flagged-set across runs writes
    nothing new (OP-25 "compound, don't accumulate")
  - SELF-REFERENCE LOOP GUARD: this monitor's own STATUS.md output must be excluded
    from the orphan-reference scan. Without this, flagging a prereg writes its
    filename into STATUS.md (under automation/, a scanned root), and the NEXT run
    then finds that mention and reports it as "referenced" -- permanently
    suppressing the flag after its first firing. This was caught live in this task's
    own dry run (5 flagged -> 1 flagged after a single unguarded cycle) and is the
    RED-PROOF below.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_PH_PATH = _REPO / "setup" / "scripts" / "prereg_hygiene.py"
_spec = importlib.util.spec_from_file_location("prereg_hygiene_under_test", _PH_PATH)
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
    monkeypatch.setattr(prereg_hygiene, "OUT_FILE", recs / "prereg-hygiene.json")
    monkeypatch.setattr(prereg_hygiene, "STATUS_MD", status_md)
    monkeypatch.setattr(prereg_hygiene, "SEARCH_DIRS", ["setup", "backtest", "automation"])
    monkeypatch.setattr(prereg_hygiene, "EXCLUDE_PATHS", {status_md.resolve()})
    # Force the pure-python fallback path deterministically in tests (no rg dependency).
    monkeypatch.setattr(prereg_hygiene, "_referenced_stems", lambda stems: None)
    return {
        "root": tmp_path, "recs": recs, "setup": setup_dir,
        "backtest": backtest_dir, "automation": automation_dir, "status_md": status_md,
    }


def test_malformed_json_reported_not_skipped(sandbox):
    bad = sandbox["recs"] / "broken-prereg-2026-08-01.json"
    bad.write_text('{"a": 1,}', encoding="utf-8")  # trailing comma
    report = prereg_hygiene.scan()
    assert report["n_malformed"] == 1
    assert report["malformed"][0]["file"] == "broken-prereg-2026-08-01.json"
    assert "error" in report["malformed"][0]


def test_status_field_prefers_status_over_verdict():
    data = {"status": "FROZEN", "some_verdict_field": "PASS"}
    assert prereg_hygiene._status_field(data) == "FROZEN"


def test_status_field_falls_back_to_verdict_key():
    data = {"my_verdict_a": "PASS", "another_verdict": "FAIL"}
    # sorted() -> 'another_verdict' < 'my_verdict_a'
    assert prereg_hygiene._status_field(data) == "FAIL"


def test_status_field_none_when_absent():
    assert prereg_hygiene._status_field({"foo": "bar"}) is None


def test_flag_requires_stale_status_and_age_orphan_is_informational_only(sandbox):
    # Stale status + old age, REFERENCED (not orphan) -> MUST still flag (2026-09-02
    # fix: orphan is no longer a flag requirement -- see module docstring).
    p1 = sandbox["recs"] / "referenced-prereg-2026-08-01.json"
    _write(p1, {"status": "FROZEN -- not run", "frozen_at_et": "2026-08-01T00:00:00"})
    (sandbox["setup"] / "consumer.py").write_text(
        "# see referenced-prereg-2026-08-01 for detail\n", encoding="utf-8")

    # Stale status + orphan, but RECENT (age <= 14d) -> must NOT flag.
    p2 = sandbox["recs"] / "recent-prereg-2026-08-30.json"
    _write(p2, {"status": "FROZEN -- not run", "frozen_at_et": "2026-08-30T00:00:00"})

    # Fresh (non-stale) status + old + orphan -> must NOT flag.
    p3 = sandbox["recs"] / "shipped-prereg-2026-08-01.json"
    _write(p3, {"status": "SHIPPED", "frozen_at_et": "2026-08-01T00:00:00"})

    # Stale + old + orphan -> MUST flag (unchanged case).
    p4 = sandbox["recs"] / "orphan-stale-prereg-2026-08-01.json"
    _write(p4, {"status": "FROZEN -- NOT RUN", "frozen_at_et": "2026-08-01T00:00:00"})

    report = prereg_hygiene.scan()
    flagged_names = {f["file"] for f in report["flagged"]}
    assert flagged_names == {
        "referenced-prereg-2026-08-01.json",
        "orphan-stale-prereg-2026-08-01.json",
    }
    by_name = {f["file"]: f for f in report["flagged"]}
    assert by_name["referenced-prereg-2026-08-01.json"]["orphan"] is False
    assert by_name["referenced-prereg-2026-08-01.json"]["reason"] == "FROZEN/NOT RUN + age>14d"
    assert by_name["orphan-stale-prereg-2026-08-01.json"]["orphan"] is True
    assert by_name["orphan-stale-prereg-2026-08-01.json"]["reason"] == \
        "FROZEN/NOT RUN + age>14d + orphan"


def test_prereg_named_in_queue_md_still_flags(sandbox):
    """RED-PROOF the ORPHAN-PROXY-IS-SELF-SILENCING fix: a prereg discussed/adjudicated
    in queue.md (a real file under automation/, a scanned SEARCH_DIRS root -- STATUS.md
    is the only excluded path) is NOT an orphan, but must still flag once it is
    frozen+stale+old. Before the fix this exact shape (mention it, watch the flag clear)
    was the live bug: the flagged count went 6 -> 0 with nothing resolved."""
    p = sandbox["recs"] / "prereg-adjudicated-in-queue-2026-08-01.json"
    _write(p, {"status": "FROZEN -- NOT RUN", "frozen_at_et": "2026-08-01T00:00:00"})
    queue_md = sandbox["automation"] / "queue.md"
    queue_md.write_text(
        "- [ ] SOME-ITEM :: prereg-adjudicated-in-queue-2026-08-01 -- RUN, pending execution\n",
        encoding="utf-8",
    )

    report = prereg_hygiene.scan()
    entry = next(e for e in report["entries"] if e["file"] == p.name)
    assert entry["orphan"] is False, "queue.md mention must clear the orphan bit"
    flagged_names = {f["file"] for f in report["flagged"]}
    assert p.name in flagged_names, (
        "a prereg named in queue.md must still flag -- being adjudicated in prose is "
        "not the same as being resolved (has_results_file), and must not silence the "
        "monitor"
    )


def test_age_source_priority_filename_over_mtime(sandbox):
    p = sandbox["recs"] / "no-frozen-field-prereg-2026-08-01.json"
    _write(p, {"status": "FROZEN"})
    report = prereg_hygiene.scan()
    entry = next(e for e in report["entries"] if e["file"] == p.name)
    assert entry["age_source"] == "filename_date"
    assert entry["age_days"] > 14


def test_status_md_append_deduped_across_unchanged_runs(sandbox):
    p = sandbox["recs"] / "orphan-stale-prereg-2026-08-01.json"
    _write(p, {"status": "FROZEN -- NOT RUN", "frozen_at_et": "2026-08-01T00:00:00"})

    # Exercise main() end-to-end twice; STATUS.md must gain exactly ONE new block.
    before = sandbox["status_md"].read_text(encoding="utf-8")
    assert prereg_hygiene.main() == 0
    after_first = sandbox["status_md"].read_text(encoding="utf-8")
    assert after_first.count("### BROKEN: prereg-hygiene") == 1
    assert prereg_hygiene.main() == 0
    after_second = sandbox["status_md"].read_text(encoding="utf-8")
    assert after_second.count("### BROKEN: prereg-hygiene") == 1, (
        "an UNCHANGED flagged set must not append a second STATUS.md block (dedupe)"
    )
    assert before != after_first


def test_red_proof_self_reference_loop_guard(sandbox):
    """RED-PROOF: this monitor's own STATUS.md output must be excluded from the
    orphan-reference scan. Simulate a run that has already flagged a prereg (its
    filename now sits in STATUS.md), then confirm that WITHOUT the exclusion the
    monitor's own output would wrongly clear the `orphan` bit on the next run -- and
    WITH the exclusion (the shipped behaviour) it does not.

    UPDATED 2026-09-02 (ORPHAN-PROXY-IS-SELF-SILENCING FIX): `orphan` no longer gates
    the flag itself (see test_flag_requires_stale_status_and_age_orphan_is_informational_only
    above), so this guard now checks the INFORMATIONAL `orphan` column rather than the
    flagged set -- the flag survives either way; what the exclusion protects is whether
    `orphan` still means what it says."""
    p = sandbox["recs"] / "orphan-stale-prereg-2026-08-01.json"
    _write(p, {"status": "FROZEN -- NOT RUN", "frozen_at_et": "2026-08-01T00:00:00"})

    # Run once: flags it, writes the filename into STATUS.md.
    assert prereg_hygiene.main() == 0
    status_text = sandbox["status_md"].read_text(encoding="utf-8")
    assert "orphan-stale-prereg-2026-08-01.json" in status_text

    # Guarded behaviour: re-scanning still flags it AND still reports it orphan (its own
    # STATUS.md mention is excluded from the reference scan).
    report_guarded = prereg_hygiene.scan()
    guarded_entry = next(e for e in report_guarded["entries"] if e["file"] == p.name)
    assert guarded_entry["orphan"] is True, (
        "guarded scan must still report orphan=True -- its own STATUS.md mention is excluded"
    )
    assert any(f["file"] == p.name for f in report_guarded["flagged"])

    # RED-PROOF: neuter the exclusion (empty EXCLUDE_PATHS) and confirm the SAME
    # scenario now wrongly clears the `orphan` bit -- proving the exclusion is load-bearing.
    # The flag itself still fires (frozen+age no longer depends on orphan), which is the
    # whole point of the 2026-09-02 fix -- self-mention can no longer silence the flag,
    # only muddy the informational orphan column, and this guard catches exactly that.
    orig_exclude = prereg_hygiene.EXCLUDE_PATHS
    try:
        prereg_hygiene.EXCLUDE_PATHS = set()
        report_neutered = prereg_hygiene.scan()
        neutered_entry = next(e for e in report_neutered["entries"] if e["file"] == p.name)
        assert neutered_entry["orphan"] is False, (
            "removing the STATUS.md exclusion should let its own mention count as a "
            "reference, wrongly clearing the orphan bit (RED-PROOF the guard is load-bearing)"
        )
        neutered_flagged = {f["file"] for f in report_neutered["flagged"]}
        assert p.name in neutered_flagged, (
            "the flag itself must survive regardless -- orphan is informational only"
        )
    finally:
        prereg_hygiene.EXCLUDE_PATHS = orig_exclude
