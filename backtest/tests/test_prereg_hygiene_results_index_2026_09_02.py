"""Guards for prereg_hygiene's WIDENED result cross-reference (2026-09-02).

WHY THE WIDENING HAPPENED. The index scanned only the top level of
analysis/recommendations/, so it could not see a result artifact living in a sibling
analysis/ subtree -- and that is where many of them live. The visible symptom: 40 preregs
carried a FROZEN/never-run status while 31 of them already had a real result artifact on
disk (analysis/multi-lane/intraday-null-stageA.json carries verdict FAIL_stop_the_lane for
prereg-multi-intraday-null; analysis/whole-engine-null/ ran the same night and returned
PASS while its prereg still read "NOT RUN"). The backlog looked like 52 items and was 7.

WHY THIS NEEDS GUARDING. Widening a "has it already been answered?" search is exactly how a
monitor gets silenced: if preregs can satisfy each other, a cluster of cross-referencing
preregs clears itself and the monitor goes quiet on a real backlog. That is the same
self-silencing shape as the orphan-proxy bug found in this very file on 2026-09-01, where
FILING the adjudication named all six stale preregs and drove the flagged count 6 -> 0 with
nothing resolved. So the central test here is that a prereg is never a result.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "setup" / "scripts" / "prereg_hygiene.py"

_spec = importlib.util.spec_from_file_location("prereg_hygiene_g", MODULE)
assert _spec and _spec.loader
ph = importlib.util.module_from_spec(_spec)
sys.modules["prereg_hygiene_g"] = ph
_spec.loader.exec_module(ph)


def test_index_returns_three_maps():
    """The third map (by_named_prereg) is the whole point of the widening."""
    out = ph._results_index()
    assert isinstance(out, tuple) and len(out) == 3
    by_rule_id, by_registration, by_named = out
    assert isinstance(by_named, dict)


def test_a_prereg_is_never_counted_as_a_result_for_another_prereg():
    """THE self-silencing guard. Preregs routinely cite each other; if that satisfied the
    'already answered' test, a cluster of them would clear itself."""
    _rid, _reg, by_named = ph._results_index()
    prereg_names = {f.name for f in ph.RECS_DIR.glob("*prereg*.json")}
    for target, hits in by_named.items():
        for hit in hits:
            assert hit not in prereg_names, (
                f"{hit} is a pre-registration but was indexed as a RESULT for {target} -- "
                "preregs must never satisfy each other's 'has it been answered' test"
            )


def test_no_prereg_is_its_own_result():
    _rid, _reg, by_named = ph._results_index()
    for target, hits in by_named.items():
        assert target not in hits, f"{target} indexed as its own result"


def test_matcher_prefers_explicit_conventions_over_the_name_scan():
    """rule_id / registration are deliberate self-labels; the filename scan is a fallback.
    If the fallback outranked them, a stray mention would beat a real declaration."""
    p = Path("prereg-example-2026-01-01.json")
    got = ph._matching_result_file(
        p, {"rule_id": "RID"},
        by_rule_id={"RID": ["real-result.json"]},
        by_registration={},
        by_named_prereg={p.name: ["some-other-mention.json"]},
    )
    assert got == "real-result.json"


def test_matcher_uses_the_name_scan_when_nothing_else_matches():
    p = Path("prereg-example-2026-01-01.json")
    got = ph._matching_result_file(
        p, {}, by_rule_id={}, by_registration={},
        by_named_prereg={p.name: ["analysis-artifact.json"]},
    )
    assert got == "analysis-artifact.json"


def test_matcher_returns_none_when_genuinely_unanswered():
    """The backlog must still be reportable -- a widened search that can never return None
    would report every prereg as answered."""
    got = ph._matching_result_file(
        Path("prereg-unanswered.json"), {},
        by_rule_id={}, by_registration={}, by_named_prereg={})
    assert got is None


def test_oversized_files_are_skipped():
    """A data ledger is a tape, not a verdict. Without the cap this becomes a multi-minute
    walk over 531MB and the daily monitor starts timing out."""
    assert ph.MAX_RESULT_BYTES <= 5_000_000
    oversized = [f for f in ph.ANALYSIS_DIR.rglob("*.json")
                 if f.stat().st_size > ph.MAX_RESULT_BYTES]
    _rid, _reg, by_named = ph._results_index()
    indexed = {n for hits in by_named.values() for n in hits}
    for f in oversized:
        assert f.name not in indexed, f"oversized {f.name} should not be indexed"


def test_the_real_known_pairs_are_found():
    """Anchors the widening against cases verified by hand on 2026-09-02. If a later change
    re-narrows the scan, these fail rather than quietly restoring the phantom backlog."""
    _rid, _reg, by_named = ph._results_index()
    expected = {
        "prereg-multi-intraday-null-2026-08-20.json": "intraday-null-stageA.json",
        "prereg-whole-engine-null-2026-09-01.json": None,  # any artifact under whole-engine-null/
    }
    hits = by_named.get("prereg-multi-intraday-null-2026-08-20.json", [])
    assert expected["prereg-multi-intraday-null-2026-08-20.json"] in hits, (
        "the multi-lane Stage A result (verdict FAIL_stop_the_lane) is no longer being "
        "matched to its own prereg -- the cross-reference has re-narrowed"
    )


def test_scan_still_reports_a_nonzero_backlog():
    """The point of widening is a TRUE count, not a zero. If everything now looks answered,
    the matcher has become too permissive and the monitor is useless."""
    report = ph.scan()
    entries = report["entries"]
    unresolved = [e for e in entries
                  if not e.get("has_results_file")
                  and any(w in str(e.get("status", "")).upper()
                          for w in ("FROZEN", "NOT RUN", "NOT_RUN", "PENDING"))]
    assert unresolved, (
        "every frozen prereg now reports a matching result -- that is not plausible and "
        "means the name-scan is matching on something too loose"
    )
    assert len(unresolved) < 25, (
        f"{len(unresolved)} unresolved -- the widening appears not to have taken effect"
    )
