"""Guards for dataset_integrity.py -- the check that would have caught the 190 -> 191 mutation.

THE INCIDENT IT EXISTS FOR: `engine-fullhist-replay-2026-07-23.json` published +$5,064.75 / 190
trades and silently became +$4,808.75 / 191 when `df0348d9` (a regime-threshold commit) added
one losing row. Nothing announced it. Three downstream tests went RED and were nearly written
off as stale pins, and ENTRY-LOCATION-GATE published the wrong population size off the mutated
file.

These tests use the REAL historical mutation as their fixture -- the 190-row blob is pulled from
git and fingerprinted -- so they prove the check catches the thing that actually happened, not a
synthetic edit chosen to be easy to catch.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOD = REPO / "setup" / "scripts" / "dataset_integrity.py"
_spec = importlib.util.spec_from_file_location("dataset_integrity", MOD)
di = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(di)

REPLAY = "analysis/recommendations/engine-fullhist-replay-2026-07-23.json"


def test_manifest_exists_and_covers_the_mutated_dataset():
    man = di.load_manifest().get("datasets", {})
    assert REPLAY in man, (
        "the 18-month replay population is not fingerprinted -- it is the exact file that was "
        "mutated out-of-band, and every downstream study keys on it")
    assert man[REPLAY].get("sha256_16"), "no hash recorded"


def test_current_tree_verifies_clean():
    res = di.verify()
    bad = {k: v["status"] for k, v in res.items() if v["status"] not in ("OK", "UNRECORDED")}
    assert not bad, f"tracked datasets drifted without the manifest being updated: {bad}"


def test_reformatting_alone_is_NOT_reported_as_drift(tmp_path, monkeypatch):
    """Canonicalised hashing: whitespace/key-order churn must not cry wolf, or the check gets
    muted the first time someone pretty-prints a file -- and a muted check is no check."""
    p = REPO / REPLAY
    obj = json.loads(p.read_text(encoding="utf-8"))
    orig = p.read_bytes()
    before = di.fingerprint(REPLAY)["sha256_16"]
    try:
        p.write_text(json.dumps(obj, indent=4, sort_keys=True), encoding="utf-8")
        after = di.fingerprint(REPLAY)["sha256_16"]
    finally:
        p.write_bytes(orig)
    assert before == after, "reformatting changed the hash -- the check will be ignored"


def test_the_REAL_190_row_version_is_detected_as_drift():
    """The historical mutation, replayed. Not a synthetic edit -- the actual pre-df0348d9 blob."""
    blob = subprocess.run(
        ["git", "show", f"6b7c07ac:{REPLAY}"], cwd=str(REPO),
        capture_output=True, encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    if not blob.strip():
        pytest.skip("historical blob unavailable in this checkout")
    old = json.loads(blob)
    assert len(old["trades"]) == 190, "fixture drifted: that commit should hold 190 trades"

    p = REPO / REPLAY
    orig = p.read_bytes()
    try:
        p.write_text(blob, encoding="utf-8")
        res = di.verify([REPLAY])[REPLAY]
    finally:
        p.write_bytes(orig)
    assert res["status"] == "DRIFTED", (
        "swapping in the pre-mutation 190-row population was NOT flagged -- this check would "
        "not have caught the incident it was built for")
    assert res["n_records_delta"] == -1, f"row delta not reported: {res}"


def test_assert_intact_raises_so_a_runner_fails_at_the_POINT_OF_USE():
    """A study that reads a mutated population publishes a wrong number under a frozen prereg's
    authority. Failing three tests later is not good enough -- it must fail before computing."""
    p = REPO / REPLAY
    orig = p.read_bytes()
    obj = json.loads(orig.decode("utf-8"))
    try:
        obj["trades"] = obj["trades"][:-1]          # drop one row = the incident, inverted
        p.write_text(json.dumps(obj), encoding="utf-8")
        with pytest.raises(RuntimeError, match="DATASET INTEGRITY"):
            di.assert_intact(REPLAY)
    finally:
        p.write_bytes(orig)


def test_assert_intact_is_silent_when_the_dataset_is_untouched():
    """Vacuity check: the guard above must not pass merely because assert_intact always raises."""
    di.assert_intact(REPLAY)


def test_missing_file_is_reported_not_silently_ok(tmp_path, monkeypatch):
    monkeypatch.setitem(di.TRACKED, "analysis/recommendations/__no_such_dataset__.json", "probe")
    monkeypatch.setattr(di, "load_manifest", lambda: {
        "datasets": {"analysis/recommendations/__no_such_dataset__.json": {"sha256_16": "deadbeefdeadbeef"}}})
    res = di.verify(["analysis/recommendations/__no_such_dataset__.json"])
    assert res["analysis/recommendations/__no_such_dataset__.json"]["status"] == "MISSING"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
