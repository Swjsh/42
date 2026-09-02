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
  - flagging requires ALL THREE: stale-status text, age > 14d, AND orphan
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


def test_flag_requires_all_three_conditions(sandbox):
    # Stale status + old age, but REFERENCED -> must NOT flag.
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

    # All three hold -> MUST flag.
    p4 = sandbox["recs"] / "orphan-stale-prereg-2026-08-01.json"
    _write(p4, {"status": "FROZEN -- NOT RUN", "frozen_at_et": "2026-08-01T00:00:00"})

    report = prereg_hygiene.scan()
    flagged_names = {f["file"] for f in report["flagged"]}
    assert flagged_names == {"orphan-stale-prereg-2026-08-01.json"}


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
    monitor would wrongly clear the flag on the next run -- and WITH the exclusion
    (the shipped behaviour) it does not."""
    p = sandbox["recs"] / "orphan-stale-prereg-2026-08-01.json"
    _write(p, {"status": "FROZEN -- NOT RUN", "frozen_at_et": "2026-08-01T00:00:00"})

    # Run once: flags it, writes the filename into STATUS.md.
    assert prereg_hygiene.main() == 0
    status_text = sandbox["status_md"].read_text(encoding="utf-8")
    assert "orphan-stale-prereg-2026-08-01.json" in status_text

    # Guarded behaviour: re-scanning still flags it (STATUS.md mention excluded).
    report_guarded = prereg_hygiene.scan()
    assert any(f["file"] == p.name for f in report_guarded["flagged"]), (
        "guarded scan must still flag the prereg -- its own STATUS.md mention is excluded"
    )

    # RED-PROOF: neuter the exclusion (empty EXCLUDE_PATHS) and confirm the SAME
    # scenario now wrongly clears the flag -- proving the exclusion is load-bearing.
    orig_exclude = prereg_hygiene.EXCLUDE_PATHS
    try:
        prereg_hygiene.EXCLUDE_PATHS = set()
        report_neutered = prereg_hygiene.scan()
        neutered_flagged = {f["file"] for f in report_neutered["flagged"]}
        assert p.name not in neutered_flagged, (
            "removing the STATUS.md exclusion should let its own mention count as a "
            "reference, wrongly clearing the flag (RED-PROOF the guard is load-bearing)"
        )
    finally:
        prereg_hygiene.EXCLUDE_PATHS = orig_exclude
