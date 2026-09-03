"""Guard for PROSPECTOR-SEMANTIC-DEDUP-GAP (queue.md, filed 2026-08-05 from
CHEF-INBOX-BACKLOG-DRAIN's own findings) -- a RE-VIOLATION of L240
("exact-key dedupe misses re-worded family duplicates"). Per OP-25 a
re-violated lesson must graduate to a code assertion; this file is that
assertion for the THIRD dedupe layer added to prospector.py:
semantic_duplicate_of() / log_semantic_duplicate() / infer_inbox_verdict().

Root cause this layer targets: FAMILY_KEYWORDS (prospector.py's SECOND,
existing dedupe layer) is a hand-curated allowlist that only catches a
duplicate family AFTER someone manually notices and extends it -- it went
unmaintained 2026-07-22..2026-08-22, during which 20+ of 61 un-DONE
chef-inbox items were semantic restatements of already-researched/REJECTED/
KILLED ideas. The new layer needs NO curation: Jaccard overlap on
stopword-stripped TITLE tokens against every existing chef-inbox item's
title (open AND .md.DONE).

Calibration evidence (full sweep run against the REAL 231-item
strategy/candidates/_chef-inbox/ corpus, using idea_family() family
membership as ground truth for "same underlying topic" vs "genuinely
distinct"):

    thr=0.20  recall=0.806 (458/568 within-family pairs)  FPR=0.005 (81/16085)
    thr=0.25  recall=0.680 (386/568 within-family pairs)  FPR=0.001 (22/16085)
    thr=0.30  recall=0.533 (303/568 within-family pairs)  FPR=0.001 (13/16085)

SEMANTIC_OVERLAP_THRESHOLD = 0.25 was chosen: manual inspection of the 22
cross-family pairs it still flags at 0.25 shows most are themselves
defensibly related concepts FAMILY_KEYWORDS itself only separates by
convention (Market Profile/TPO vs Volume Profile; VIX1D vs VIX futures term
structure; NYSE TRIN vs Advance-Decline line) -- not genuine distinct-idea
suppressions. A missed duplicate below threshold just means one more fire
re-notices it manually (today's status quo, unchanged); a wrongly-suppressed
novel idea above threshold would silently lose a real research lead, which
is the worse failure mode for a notify-only organ -- hence erring toward the
higher, stricter threshold.

House convention: import the module under test by file path (matches
test_prospector.py / test_trade_autopsy.py).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "prospector", REPO / "setup" / "scripts" / "prospector.py")
pr = importlib.util.module_from_spec(_SPEC)
sys.modules["prospector"] = pr
_SPEC.loader.exec_module(pr)


def _idea_row(dedupe_key, beat="data_feeds_free", testability="battery-ready", **kw):
    return {"kind": "idea", "id": dedupe_key, "dedupe_key": dedupe_key, "beat": beat,
            "idea": f"idea for {dedupe_key}", "mechanism_1line": "m", "data_source": "d",
            "cost": "$0", "instrument_fit": "both", "testability": testability,
            "status": "proposed", "date": "2026-07-09", **kw}


# Two titles about the SAME novel (not-in-FAMILY_KEYWORDS) concept, reworded
# by a hypothetical second swarm pass -- real Jaccard on these two (verified
# against the production _title_tokens/_title_jaccard helpers) is 0.778,
# comfortably above SEMANTIC_OVERLAP_THRESHOLD.
CANONICAL_TITLE = "Overnight repo rate spikes as a stress indicator for equity risk appetite"
REWORDED_TITLE = "Repo rate spikes overnight signal market stress and risk appetite"
# A genuinely unrelated concept -- zero token overlap with the above.
DISTINCT_TITLE = "Reddit WallStreetBets sentiment via Pushshift API tracking retail flow"


def _write_inbox_item(inbox: Path, fname: str, title: str, *, extra_body: str = "") -> Path:
    inbox.mkdir(parents=True, exist_ok=True)
    text = (
        f"# Chef Inbox — {title}\n\n"
        f"**Routed by:** Gamma_Prospector 2026-07-09\n"
        f"**Priority:** MED\n\n"
        f"## The Finding\n{title}.\n\n"
        f"{extra_body}"
    )
    path = inbox / fname
    path.write_text(text, encoding="utf-8")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# _title_tokens / _title_jaccard -- pure helpers
# ─────────────────────────────────────────────────────────────────────────────


def test_title_jaccard_reworded_vs_distinct():
    a = pr._title_tokens(CANONICAL_TITLE)
    b = pr._title_tokens(REWORDED_TITLE)
    c = pr._title_tokens(DISTINCT_TITLE)
    assert pr._title_jaccard(a, b) >= pr.SEMANTIC_OVERLAP_THRESHOLD
    assert pr._title_jaccard(a, c) == 0.0


def test_title_jaccard_empty_sets_never_matches():
    assert pr._title_jaccard(set(), {"repo"}) == 0.0
    assert pr._title_jaccard({"repo"}, set()) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# extract_inbox_title / infer_inbox_verdict
# ─────────────────────────────────────────────────────────────────────────────


def test_extract_inbox_title_parses_header():
    text = f"# Chef Inbox — {CANONICAL_TITLE}\n\nbody\n"
    assert pr.extract_inbox_title(text, "fallback") == CANONICAL_TITLE


def test_extract_inbox_title_falls_back_when_no_header():
    assert pr.extract_inbox_title("no header here", "fallback-stem") == "fallback-stem"


def test_infer_inbox_verdict_scrapes_known_markers():
    assert pr.infer_inbox_verdict("... REJECTED as stated ...", is_done=True) == "REJECTED"
    assert pr.infer_inbox_verdict("... KILLED, no edge ...", is_done=True) == "KILLED"
    assert pr.infer_inbox_verdict("... NEEDS-MORE-DATA, n too thin ...", is_done=False) == "NEEDS-MORE-DATA"
    assert pr.infer_inbox_verdict("... NO_CANDIDATE_CLEARS_BAR_YET ...", is_done=False) == "NEEDS-MORE-DATA"
    assert pr.infer_inbox_verdict("... CLOSED-REDUNDANT vs Alpaca ...", is_done=True) == "CLOSED-REDUNDANT"
    assert pr.infer_inbox_verdict("... CONSOLIDATED, still open ...", is_done=False) == "CONSOLIDATED-OPEN"


def test_infer_inbox_verdict_falls_back_to_done_or_open():
    assert pr.infer_inbox_verdict("plain text, no marker", is_done=True) == "DONE"
    assert pr.infer_inbox_verdict("plain text, no marker", is_done=False) == "OPEN"


# ─────────────────────────────────────────────────────────────────────────────
# semantic_duplicate_of -- the core detector
# ─────────────────────────────────────────────────────────────────────────────


def test_semantic_duplicate_of_detects_reworded_title(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    canon = _write_inbox_item(inbox, "2026-07-09-prospector-repo-rate-stress.md", CANONICAL_TITLE)
    match = pr.semantic_duplicate_of(REWORDED_TITLE, inbox_dir=inbox)
    assert match is not None
    assert match["path"] == canon
    assert match["score"] >= pr.SEMANTIC_OVERLAP_THRESHOLD


def test_semantic_duplicate_of_returns_none_for_distinct_idea(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    _write_inbox_item(inbox, "2026-07-09-prospector-repo-rate-stress.md", CANONICAL_TITLE)
    match = pr.semantic_duplicate_of(DISTINCT_TITLE, inbox_dir=inbox)
    assert match is None


def test_semantic_duplicate_of_matches_done_files_and_reports_verdict(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    _write_inbox_item(
        inbox, "2026-06-01-prospector-repo-rate-stress.md.DONE", CANONICAL_TITLE,
        extra_body="<!-- DONE 2026-06-05: KILLED -- repo-rate feed is paid-only, no free path found. -->\n",
    )
    match = pr.semantic_duplicate_of(REWORDED_TITLE, inbox_dir=inbox)
    assert match is not None
    assert match["verdict"] == "KILLED"


def test_semantic_duplicate_of_ignores_readme(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    inbox.mkdir()
    (inbox / "README.md").write_text(f"# Chef Inbox — {CANONICAL_TITLE}", encoding="utf-8")
    match = pr.semantic_duplicate_of(REWORDED_TITLE, inbox_dir=inbox)
    assert match is None


def test_semantic_duplicate_of_empty_or_missing_inbox_returns_none(tmp_path):
    assert pr.semantic_duplicate_of(REWORDED_TITLE, inbox_dir=tmp_path / "nonexistent") is None
    empty = tmp_path / "_chef-inbox"
    empty.mkdir()
    assert pr.semantic_duplicate_of(REWORDED_TITLE, inbox_dir=empty) is None


# ─────────────────────────────────────────────────────────────────────────────
# promote_top1 integration: block + log vs write-through
# ─────────────────────────────────────────────────────────────────────────────


def test_promote_top1_blocks_reworded_duplicate_and_logs_canonical_plus_verdict(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    canon = _write_inbox_item(
        inbox, "2026-06-01-prospector-repo-rate-stress.md.DONE", CANONICAL_TITLE,
        extra_body="<!-- DONE 2026-06-05: REJECTED -- paid feed only. -->\n",
    )
    ledger_path = tmp_path / "ideas-ledger.jsonl"
    rows = [_idea_row("data_feeds_free:repo-rate-spike-reworded", idea=REWORDED_TITLE)]

    promoted = pr.promote_top1(rows, {}, date="2026-07-21", inbox_dir=inbox, ledger_path=ledger_path)

    assert promoted is not None
    assert promoted["_chef_inbox_file"] is None                 # no new file written
    assert promoted["_folded_into"] is None                     # NOT the FAMILY_KEYWORDS path
    assert promoted["_semantic_duplicate_of"] == canon.name
    assert promoted["_semantic_duplicate_verdict"] == "REJECTED"
    assert len(list(inbox.iterdir())) == 1                      # still just the 1 pre-existing file

    # logged with the canonical + verdict (the queue item's explicit ask)
    ledger_lines = [json.loads(l) for l in ledger_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    dup_rows = [r for r in ledger_lines if r.get("kind") == "semantic_duplicate"]
    assert len(dup_rows) == 1
    assert dup_rows[0]["dedupe_key"] == "data_feeds_free:repo-rate-spike-reworded"
    assert dup_rows[0]["semantic_duplicate_of"] == canon.name
    assert dup_rows[0]["verdict"] == "REJECTED"
    assert dup_rows[0]["overlap_score"] >= pr.SEMANTIC_OVERLAP_THRESHOLD


def test_promote_top1_writes_new_file_for_genuinely_distinct_idea(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    _write_inbox_item(inbox, "2026-06-01-prospector-repo-rate-stress.md.DONE", CANONICAL_TITLE)
    ledger_path = tmp_path / "ideas-ledger.jsonl"
    rows = [_idea_row("microstructure_internals:wsb-sentiment", idea=DISTINCT_TITLE)]

    promoted = pr.promote_top1(rows, {}, date="2026-07-21", inbox_dir=inbox, ledger_path=ledger_path)

    assert promoted is not None
    assert promoted["_chef_inbox_file"] is not None
    assert promoted.get("_semantic_duplicate_of") is None
    assert (inbox / promoted["_chef_inbox_file"]).exists()
    assert not ledger_path.exists() or not any(
        json.loads(l).get("kind") == "semantic_duplicate"
        for l in ledger_path.read_text(encoding="utf-8").splitlines() if l.strip()
    )


def test_promote_top1_semantic_layer_treats_done_as_canon_same_as_open(tmp_path):
    """.DONE (already-researched, any verdict) items count as canon just like
    an open item -- this is the whole point (a re-worded resurrection of an
    already-KILLED/REJECTED idea must be caught, not just an open dupe)."""
    inbox = tmp_path / "_chef-inbox"
    _write_inbox_item(
        inbox, "2026-06-01-prospector-repo-rate-stress.md.DONE", CANONICAL_TITLE,
        extra_body="<!-- DONE: KILLED, no free feed. -->\n",
    )
    rows = [_idea_row("data_feeds_free:repo-rate-again", idea=REWORDED_TITLE)]
    promoted = pr.promote_top1(rows, {}, date="2026-07-21", inbox_dir=inbox,
                                ledger_path=tmp_path / "ledger.jsonl")
    assert promoted["_chef_inbox_file"] is None
    assert promoted["_semantic_duplicate_verdict"] == "KILLED"


def test_promote_top1_exact_dedupe_key_path_unchanged_even_with_semantic_near_dup_present(tmp_path):
    """The new layer must NEVER be reached when the exact-key /
    already_promoted_from_inbox short-circuit already applies -- pin the
    ORIGINAL exact-key idempotency behavior stays first in line, unaffected
    by the new layer's presence, even when the inbox ALSO happens to hold a
    near-identical title (which would otherwise score above threshold)."""
    inbox = tmp_path / "_chef-inbox"
    _write_inbox_item(inbox, "2026-07-09-prospector-tick-index-nyse-tick.md",
                       "NYSE TICK Index real-time net uptick/downtick")
    rows = [_idea_row("data_feeds_free:tick-index-nyse-tick",
                       idea="NYSE TICK Index real-time net uptick/downtick")]
    # state has NO memory (simulates the 2026-07-21 state-loss incident this
    # exact-key guard was built for) -- already_promoted_from_inbox must still
    # catch it BEFORE semantic_duplicate_of is ever consulted.
    promoted = pr.promote_top1(rows, {}, date="2026-07-21", inbox_dir=inbox,
                                ledger_path=tmp_path / "ledger.jsonl")
    assert promoted is None
    assert len(list(inbox.iterdir())) == 1                      # no new file, no ledger side-effect
    assert not (tmp_path / "ledger.jsonl").exists()


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end dry-run of the real write path: run() with a mocked swarm
# producing one known-duplicate idea and one novel idea across two fires.
# ─────────────────────────────────────────────────────────────────────────────


def test_run_end_to_end_blocks_duplicate_then_writes_novel_on_next_fire(tmp_path):
    inbox = tmp_path / "_chef-inbox"
    canon = _write_inbox_item(
        inbox, "2026-06-01-prospector-repo-rate-stress.md.DONE", CANONICAL_TITLE,
        extra_body="<!-- DONE: NEEDS-MORE-DATA. -->\n",
    )
    ledger_path = tmp_path / "ideas-ledger.jsonl"
    state_path = tmp_path / "state.json"
    last_json_path = tmp_path / "last.json"
    outbox_path = tmp_path / "outbox.jsonl"

    def mocked_scan_duplicate(beat):
        return {"ok": True, "model": "mock/model", "error": None, "ideas_raw": [{
            "idea": REWORDED_TITLE, "mechanism_1line": "m", "data_source": "d",
            "cost": "$0", "instrument_fit": "both", "testability": "battery-ready",
        }]}

    result1 = pr.run(beat="data_feeds_free", dry_run=False, scan_fn=mocked_scan_duplicate,
                      date="2026-08-01", ledger_path=ledger_path, state_path=state_path,
                      last_json_path=last_json_path, inbox_dir=inbox, outbox_path=outbox_path)
    assert result1["promoted"]["_chef_inbox_file"] is None
    assert result1["promoted"]["_semantic_duplicate_of"] == canon.name
    assert len(list(inbox.iterdir())) == 1                      # still just the canonical

    def mocked_scan_novel(beat):
        return {"ok": True, "model": "mock/model", "error": None, "ideas_raw": [{
            "idea": DISTINCT_TITLE, "mechanism_1line": "m", "data_source": "d",
            "cost": "$0", "instrument_fit": "both", "testability": "battery-ready",
        }]}

    result2 = pr.run(beat="microstructure_internals", dry_run=False, scan_fn=mocked_scan_novel,
                      date="2026-08-02", ledger_path=ledger_path, state_path=state_path,
                      last_json_path=last_json_path, inbox_dir=inbox, outbox_path=outbox_path)
    assert result2["promoted"]["_chef_inbox_file"] is not None
    assert (inbox / result2["promoted"]["_chef_inbox_file"]).exists()
    assert len(list(inbox.iterdir())) == 2                      # canonical + the 1 genuinely new file

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["semantic_duplicates_total"] == 1
    assert state["promoted_total"] == 1
    assert state["folded_total"] == 0

    ledger_lines = [json.loads(l) for l in ledger_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    dup_rows = [r for r in ledger_lines if r.get("kind") == "semantic_duplicate"]
    assert len(dup_rows) == 1
    assert dup_rows[0]["semantic_duplicate_of"] == canon.name
    assert dup_rows[0]["verdict"] == "NEEDS-MORE-DATA"
