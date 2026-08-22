"""Guard: append-only datasets are verified by FROZEN PREFIX, not whole-file hash.

THE DEFECT (2026-08-21)
----------------------
`_dataset-manifest.json` has described `analysis/pain-ledger/mae-mfe.json` as
"APPEND-ONLY -- tracked by frozen-prefix count" since the integrity system was built on
2026-08-15. `verify()` never implemented that: it compared a whole-file hash for every
dataset. So the file DRIFTED every single trading day its producer appended a row
(303 records at manifest time, 350 by 2026-08-21), and the nightly suite carried a
permanent RED whose actual meaning was "we traded today".

WHY THAT MATTERS MORE THAN ONE RED LINE
The integrity system exists because on 2026-08-15 a replay artifact was silently mutated
(190 -> 191 trades by commit df0348d9, a regime-threshold commit with no business touching
it) and, in that module's own words, "three downstream tests went RED and were nearly
dismissed as stale pins". A guard that fires during normal operation trains everyone to
dismiss it — which is precisely the reflex that nearly waved a real corruption through.

THE FIX
`APPEND_ONLY` declares how many LEADING records are frozen (mae-mfe: ribbon_flipback_ab_v2's
219-row population). For those datasets verify() hashes the prefix and allows the tail to
grow. Editing a frozen row, reordering, or shrinking still DRIFTS.

All three behaviours are RED-proofed below against the real file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import dataset_integrity as di  # noqa: E402

REL = "analysis/pain-ledger/mae-mfe.json"


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point the module at a COPY, so no test can mutate a real research dataset."""
    src = REPO / REL
    if not src.is_file():
        pytest.skip(f"{REL} not present")
    work = tmp_path / "repo"
    (work / Path(REL).parent).mkdir(parents=True, exist_ok=True)
    (work / REL).write_bytes(src.read_bytes())
    monkeypatch.setattr(di, "REPO", work)
    monkeypatch.setattr(di, "MANIFEST", tmp_path / "manifest.json")
    di.record([REL])
    return work / REL


def _rewrite(p: Path, mutate):
    d = json.loads(p.read_text(encoding="utf-8"))
    mutate(d)
    p.write_text(json.dumps(d), encoding="utf-8")


def _status(rel=REL):
    return di.verify([rel])[rel]


# ---------------------------------------------------------------- the contract
def test_append_only_registry_declares_the_frozen_prefix():
    assert REL in di.APPEND_ONLY, "mae-mfe must be declared append-only, or it REDs daily"
    assert di.APPEND_ONLY[REL] == 219, (
        "the frozen prefix is ribbon_flipback_ab_v2's 219-row population; changing this "
        "number changes which rows a published conclusion is protected against"
    )


def test_every_append_only_dataset_is_also_tracked():
    for rel in di.APPEND_ONLY:
        assert rel in di.TRACKED, f"{rel} is append-only but not TRACKED -- it is unverified"


def test_fingerprint_records_a_prefix_hash_for_append_only_files(sandbox):
    fp = di.fingerprint(REL)
    assert fp["frozen_prefix_n"] == 219
    assert fp["frozen_prefix_sha256_16"], "no prefix hash -- the comparison would be vacuous"


def test_a_non_append_only_dataset_gets_no_prefix_fields(sandbox):
    other = "analysis/recommendations/engine-fullhist-replay-2026-07-23.json"
    if not (REPO / other).is_file():
        pytest.skip("replay artifact absent")
    fp = di.fingerprint(other)
    assert "frozen_prefix_sha256_16" not in fp, (
        "a frozen (non-append-only) dataset must stay whole-file hashed"
    )


# ---------------------------------------------------------------- behaviour, RED-proofed
def test_pure_append_is_OK_and_reports_how_much_grew(sandbox):
    """THE bug this closes: this used to read DRIFTED after every trading day."""
    _rewrite(sandbox, lambda d: d["trades"].append({"date": "2026-12-31", "_synthetic": True}))
    r = _status()
    assert r["status"] == "OK", f"a pure append must not drift: {r}"
    assert r["appended_since_record"] == 1


def test_editing_a_row_INSIDE_the_frozen_prefix_drifts(sandbox):
    _rewrite(sandbox, lambda d: d["trades"][5].__setitem__("_tamper", 1))
    r = _status()
    assert r["status"] == "DRIFTED", "a published population was edited and nothing noticed"
    assert "FROZEN PREFIX" in r["reason"]


def test_editing_a_row_OUTSIDE_the_frozen_prefix_is_OK(sandbox):
    """Rows past the prefix are new trades, not tampering with a published result."""
    d = json.loads(sandbox.read_text(encoding="utf-8"))
    if len(d["trades"]) <= 220:
        pytest.skip("file has no rows past the frozen prefix")
    _rewrite(sandbox, lambda x: x["trades"][-1].__setitem__("_late_edit", 1))
    assert _status()["status"] == "OK"


def test_truncation_below_the_prefix_drifts(sandbox):
    _rewrite(sandbox, lambda d: d.__setitem__("trades", d["trades"][:50]))
    r = _status()
    assert r["status"] == "DRIFTED"
    assert "truncated" in r["reason"]


def test_shrinking_while_keeping_the_prefix_still_drifts(sandbox):
    """219 rows survive, but the file lost everything after them -- that is data loss."""
    _rewrite(sandbox, lambda d: d.__setitem__("trades", d["trades"][:219]))
    r = _status()
    assert r["status"] == "DRIFTED", "an append-only dataset that SHRANK must not read OK"
    assert "SHRANK" in r["reason"]


def test_reordering_the_frozen_prefix_drifts(sandbox):
    def swap(d):
        d["trades"][0], d["trades"][1] = d["trades"][1], d["trades"][0]
    _rewrite(sandbox, swap)
    assert _status()["status"] == "DRIFTED", "row order inside a frozen population is part of it"


# ---------------------------------------------------------------- live tree
def test_the_real_tree_verifies_clean_today():
    """The whole point: after this fix the live tree is GREEN, and stays green as the
    producer appends. If this REDs, read the reason -- it is no longer 'we traded'."""
    r = di.verify()
    bad = {k: v for k, v in r.items() if v["status"] not in ("OK", "UNRECORDED")}
    assert not bad, f"dataset integrity: {json.dumps(bad, indent=1)[:800]}"
