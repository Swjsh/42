"""Guard for the prereg_hygiene aggregator-mention false-positive fix (2026-09-02, conductor
AFTERHOURS).

THE BUG: prereg_hygiene's `by_named_prereg` map treats ANY file that merely mentions a
prereg's filename stem in its raw text as that prereg's "matching result". Confirmed live
2026-09-02: `analysis/deep-research/2026-09-01-audit/findings.json` -- a 633KB multi-topic
audit write-up that names dozens of preregs in prose while adjudicating them -- was matched
as the "result file" for 11 unrelated preregs. Three of those carry an EXPLICIT status of
"deliberately NOT run" / "CANDIDATE ONLY, nothing armed" / "freeze-only by design" in their
own text -- i.e. reporting `has_results_file: True` for them is not just noisy, it is the
exact opposite of true, and if `stale_status_but_has_results` reconciliation ever auto-wrote
a "DONE" status from this signal it would corrupt the prereg's own record of what actually
happened. This is the same self-silencing shape as the 2026-09-01 orphan-proxy bug in this
same file: bare mention treated as evidence.

THE FIX: `_drop_aggregator_mentions` reverse-counts how many DISTINCT preregs each candidate
result filename is mentioned for. A file mentioned by >= AGGREGATOR_MENTION_THRESHOLD
distinct preregs is a report, not a result, and is pruned from every prereg's hit list. A
file legitimately shared by 1-2 preregs (a genuinely combined study) survives untouched.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "setup" / "scripts" / "prereg_hygiene.py"

_spec = importlib.util.spec_from_file_location("prereg_hygiene_agg", MODULE)
assert _spec and _spec.loader
ph = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ph)


def test_aggregator_mentioned_by_many_preregs_is_dropped():
    """Pure-function unit test: a filename mentioned by >= threshold distinct preregs is
    removed from every hit list it appeared in."""
    by_named = {
        "prereg-a.json": ["report.json"],
        "prereg-b.json": ["report.json"],
        "prereg-c.json": ["report.json"],
    }
    out = ph._drop_aggregator_mentions(by_named)
    assert out == {}, f"aggregator 'report.json' (3 mentioners) should be pruned entirely, got {out}"


def test_genuinely_shared_result_below_threshold_survives():
    """Two preregs sharing one real combined study result must NOT be treated as an
    aggregator -- pruning below the threshold would re-break the legitimate shared case."""
    by_named = {
        "prereg-a.json": ["combined-study.json"],
        "prereg-b.json": ["combined-study.json"],
    }
    out = ph._drop_aggregator_mentions(by_named)
    assert out == by_named, "a 2-way genuine share must not be pruned"


def test_mixed_hits_prune_only_the_aggregator_entry():
    """A prereg with BOTH an aggregator mention and a real per-prereg result keeps the
    real one and loses only the aggregator."""
    by_named = {
        "prereg-a.json": ["report.json", "real-result-a.json"],
        "prereg-b.json": ["report.json"],
        "prereg-c.json": ["report.json"],
    }
    out = ph._drop_aggregator_mentions(by_named)
    assert out == {"prereg-a.json": ["real-result-a.json"]}


def test_threshold_boundary_is_inclusive():
    """AGGREGATOR_MENTION_THRESHOLD mentions exactly hits the aggregator branch (>=, not >)."""
    assert ph.AGGREGATOR_MENTION_THRESHOLD == 3
    by_named = {f"prereg-{i}.json": ["report.json"] for i in range(ph.AGGREGATOR_MENTION_THRESHOLD)}
    out = ph._drop_aggregator_mentions(by_named)
    assert out == {}


def test_live_findings_json_no_longer_matched_as_a_result():
    """Regression pin against the real repo artifact that exposed this bug. If this ever
    goes red because findings.json legitimately shrinks below the threshold, that is fine
    (the guard becomes moot); if it goes red because the prune logic broke, that is the
    real failure this test exists to catch."""
    _rid, _reg, by_named = ph._results_index()
    for prereg_name, hits in by_named.items():
        assert "findings.json" not in hits, (
            f"{prereg_name} still matched to the multi-topic audit findings.json as its "
            "'result' -- the aggregator-mention prune did not take effect"
        )


def test_live_explicitly_not_run_preregs_report_no_results_file():
    """The three concrete false positives found live: each carries an explicit
    never-run/candidate-only status in its own text. Confirm the fixed scan agrees with
    what the prereg itself says, not with a stray mention in someone else's report."""
    report = ph.scan()
    never_run_files = {
        "prereg-ladder-x-premium-2026-08-09.json",
        "prereg-chasing-filter-2026-08-14.json",
        "prereg-runner-finite-tgt-candidate-2026-08-06.json",
    }
    by_file = {e["file"]: e for e in report["entries"]}
    for name in never_run_files:
        entry = by_file.get(name)
        if entry is None:
            continue  # file renamed/removed since this guard was written; not this test's concern
        assert entry["result_file"] != "findings.json", (
            f"{name} is matched to findings.json despite its own status text saying it was "
            "never run -- the aggregator prune regressed"
        )
