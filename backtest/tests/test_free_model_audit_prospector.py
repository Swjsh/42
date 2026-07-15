"""Guards for free_model_audit_prospector.py -- the "prospector" AUDIT_SUBJECTS adapter
(AUDIT-HARNESS-B3).

REAL_IDEA_ROW / REAL_CHEF_INBOX_MD below are copied VERBATIM from the actual
analysis/prospector/ideas-ledger.jsonl row and strategy/candidates/_chef-inbox/
2026-07-09-prospector-gex_flip_from_banked_cboe.md file on disk (confirmed via direct Read
before this adapter was built, per the task's own instruction not to trust the description
alone) -- this is real production output from prospector.py's first live promotion, not
invented. collect_items parsing tests run against copies of these real files in tmp_path.
Grading-dispatch tests use small synthetic ledger/recommendations fixtures so no test ever
depends on the live ideas-ledger.jsonl / analysis/recommendations/ tree's mutable state.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relpath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fma = _load("free_model_audit", "setup/scripts/free_model_audit.py")
pa = _load("free_model_audit_prospector", "setup/scripts/free_model_audit_prospector.py")


# ---------- REAL fixtures (verbatim from disk, 2026-07-09 gex_flip_from_banked_cboe promotion) ----------

REAL_IDEA_ROW = {
    "id": "gex_flip_from_banked_cboe",
    "beat": "options_structure_metrics",
    "idea": "Tag every 0DTE session by which side of the CBOE zero-gamma-flip SPY closed on, "
            "using the archive Gamma_CboeOiBank already banks.",
    "mechanism_1line": "Dealer hedging flips from move-dampening (positive gamma) to "
                       "move-amplifying (negative gamma) at the zero-gamma strike -- a regime "
                       "tag no current filter reads.",
    "data_source": "journal/gex-archive/*-cboe.json (Gamma_CboeOiBank, free CBOE CDN, 14 "
                   "sessions banked as of 2026-07-09) + gex_regime.py (already built).",
    "cost": "$0", "instrument_fit": "0dte", "testability": "battery-ready",
    "dedupe_key": "gex_flip_from_banked_cboe",
    "source": "fable-2026-07-09",
    "note": "14 sessions ALREADY BANKED by Gamma_CboeOiBank -- nothing consumes it yet -- "
           "cheapest first study (zero new data fetch).",
    "kind": "idea", "status": "proposed", "date": "2026-07-09",
    "ts_et": "2026-07-09T19:47:08.696054",
}

REAL_CHEF_INBOX_MD = """# Chef Inbox — Tag every 0DTE session by which side of the CBOE zero-gamma-flip SPY c

**Routed by:** Gamma_Prospector 2026-07-09
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** fable-2026-07-09

## The Finding
Prospector beat `options_structure_metrics` surfaced: Tag every 0DTE session by which side of \
the CBOE zero-gamma-flip SPY closed on, using the archive Gamma_CboeOiBank already banks.

## Research Question for Chef
SPY's proximity to the CBOE-derived zero-gamma flip point predicts a continuation-vs-reversion \
regime for 0DTE entries.

## Backtest Request
Data: journal/gex-archive/*-cboe.json
Null hypothesis: trade outcome is INDEPENDENT of the zero-gamma flip side.
Pass bar: OOS positive AND WF >= 0.70 AND sub-window stable AND anchor no-regression.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: gex_flip_from_banked_cboe) · \
markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
"""


def _write_ledger(ledger_path: Path, rows: list[dict]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _write_inbox(inbox_dir: Path, fname: str, text: str) -> Path:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    p = inbox_dir / fname
    p.write_text(text, encoding="utf-8")
    return p


# ---------- collect_items: parsing on REAL fixtures ----------

def test_collect_items_reads_real_promotion(tmp_path):
    inbox = tmp_path / "inbox"
    ledger = tmp_path / "ideas-ledger.jsonl"
    _write_inbox(inbox, "2026-07-09-prospector-gex_flip_from_banked_cboe.md", REAL_CHEF_INBOX_MD)
    _write_ledger(ledger, [REAL_IDEA_ROW])

    items = pa.collect_items(None, date(2026, 7, 9), inbox_dir=inbox, ledger_path=ledger)
    assert len(items) == 1
    it = items[0]
    assert it.subject == "prospector"
    assert it.item_id == "promoted:gex_flip_from_banked_cboe:2026-07-09"
    assert it.account == "prospector"
    assert it.context["dedupe_key"] == "gex_flip_from_banked_cboe"
    assert it.context["beat"] == "options_structure_metrics"
    assert it.context["testability"] == "battery-ready"
    assert it.free_model_output["source"] == "fable-2026-07-09"
    assert it.free_model_output["promoted"] is True


def test_collect_items_date_window_filters(tmp_path):
    inbox = tmp_path / "inbox"
    ledger = tmp_path / "ideas-ledger.jsonl"
    _write_inbox(inbox, "2026-07-09-prospector-gex_flip_from_banked_cboe.md", REAL_CHEF_INBOX_MD)
    _write_inbox(inbox, "2026-07-12-prospector-gex_flip_from_banked_cboe.md",
                REAL_CHEF_INBOX_MD.replace("2026-07-09", "2026-07-12"))
    _write_ledger(ledger, [REAL_IDEA_ROW])

    only_09 = pa.collect_items(None, date(2026, 7, 9), inbox_dir=inbox, ledger_path=ledger)
    assert len(only_09) == 1
    assert only_09[0].context["promoted_date"] == "2026-07-09"

    both = pa.collect_items(date(2026, 7, 9), date(2026, 7, 12), inbox_dir=inbox, ledger_path=ledger)
    assert len(both) == 2

    only_12 = pa.collect_items(date(2026, 7, 10), date(2026, 7, 12), inbox_dir=inbox, ledger_path=ledger)
    assert len(only_12) == 1
    assert only_12[0].context["promoted_date"] == "2026-07-12"


def test_collect_items_skips_non_prospector_files(tmp_path):
    inbox = tmp_path / "inbox"
    ledger = tmp_path / "ideas-ledger.jsonl"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "2026-07-09-hand-authored-idea.md").write_text("# not from prospector",
                                                             encoding="utf-8")
    _write_inbox(inbox, "2026-07-09-prospector-gex_flip_from_banked_cboe.md", REAL_CHEF_INBOX_MD)
    _write_ledger(ledger, [REAL_IDEA_ROW])
    items = pa.collect_items(None, date(2026, 7, 9), inbox_dir=inbox, ledger_path=ledger)
    assert len(items) == 1


def test_collect_items_skips_file_with_no_parseable_dedupe_key(tmp_path):
    inbox = tmp_path / "inbox"
    ledger = tmp_path / "ideas-ledger.jsonl"
    _write_inbox(inbox, "2026-07-09-prospector-broken.md", "# Chef Inbox\n\nno dedupe_key line\n")
    _write_ledger(ledger, [])
    items = pa.collect_items(None, date(2026, 7, 9), inbox_dir=inbox, ledger_path=ledger)
    assert items == []


def test_collect_items_missing_dir_returns_empty(tmp_path):
    assert pa.collect_items(None, date(2026, 7, 9), inbox_dir=tmp_path / "nope",
                            ledger_path=tmp_path / "nope.jsonl") == []


def test_collect_items_missing_ledger_row_still_yields_item_with_empty_context(tmp_path):
    """A promotion whose original idea row somehow isn't in the ledger (e.g. ledger was
    pruned) must still surface as a gradeable item -- grading falls through to 'pending', it
    is never dropped silently."""
    inbox = tmp_path / "inbox"
    ledger = tmp_path / "ideas-ledger.jsonl"
    _write_inbox(inbox, "2026-07-09-prospector-gex_flip_from_banked_cboe.md", REAL_CHEF_INBOX_MD)
    _write_ledger(ledger, [])  # no matching idea row
    items = pa.collect_items(None, date(2026, 7, 9), inbox_dir=inbox, ledger_path=ledger)
    assert len(items) == 1
    assert items[0].context["beat"] is None


# ---------- _kill_reason_for / _recommendation_verdict_for (pure record-linkage) ----------

def test_kill_reason_found():
    rows = [REAL_IDEA_ROW, {"kind": "kill", "dedupe_key": "gex_flip_from_banked_cboe",
                            "reason": "no discriminating power, real-fills A/B", "ts_et": "x"}]
    assert pa._kill_reason_for("gex_flip_from_banked_cboe", rows) == (
        "no discriminating power, real-fills A/B")


def test_kill_reason_none_when_not_killed():
    assert pa._kill_reason_for("gex_flip_from_banked_cboe", [REAL_IDEA_ROW]) is None


def test_recommendation_verdict_none_when_dedupe_key_not_found(tmp_path):
    recs = tmp_path / "recs"
    recs.mkdir()
    (recs / "unrelated.json").write_text('{"rule_id": "something_else", "verdict": "KILL"}',
                                         encoding="utf-8")
    assert pa._recommendation_verdict_for("gex_flip_from_banked_cboe", recs_dir=recs) is None


def test_recommendation_verdict_killed(tmp_path):
    recs = tmp_path / "recs"
    recs.mkdir()
    (recs / "gex-flip-scorecard.json").write_text(
        json.dumps({"rule_id": "gex_flip_from_banked_cboe", "verdict": "KILL",
                   "reason": "no edge"}), encoding="utf-8")
    rec = pa._recommendation_verdict_for("gex_flip_from_banked_cboe", recs_dir=recs)
    assert rec["disposition"] == "KILLED"
    assert rec["file"].endswith("gex-flip-scorecard.json")


def test_recommendation_verdict_cleared(tmp_path):
    recs = tmp_path / "recs"
    recs.mkdir()
    (recs / "gex-flip-scorecard.json").write_text(
        json.dumps({"rule_id": "gex_flip_from_banked_cboe", "verdict": "SHIP",
                   "oos_positive": True}), encoding="utf-8")
    rec = pa._recommendation_verdict_for("gex_flip_from_banked_cboe", recs_dir=recs)
    assert rec["disposition"] == "CLEARED"


def test_recommendation_verdict_ambiguous_when_both_words_present(tmp_path):
    recs = tmp_path / "recs"
    recs.mkdir()
    (recs / "gex-flip-history.md") .write_text(
        "gex_flip_from_banked_cboe: first attempt KILLED for look-ahead; re-tested and "
        "SHIPPED after the fix.",
        encoding="utf-8")
    rec = pa._recommendation_verdict_for("gex_flip_from_banked_cboe", recs_dir=recs)
    assert rec["disposition"] == "AMBIGUOUS"
    assert rec["n_hits"] == 1


def test_recommendation_verdict_missing_dir_returns_none(tmp_path):
    assert pa._recommendation_verdict_for("x", recs_dir=tmp_path / "nope") is None


# ---------- grade_item dispatch ----------

def _mk_item(dedupe_key="gex_flip_from_banked_cboe", promoted_date="2026-07-09"):
    return fma.AuditItem(
        subject="prospector", item_id=f"promoted:{dedupe_key}:{promoted_date}",
        timestamp_et=f"{promoted_date}T00:00:00", account="prospector",
        context={"dedupe_key": dedupe_key, "promoted_date": promoted_date,
                "chef_inbox_file": "x", "beat": "options_structure_metrics",
                "idea": REAL_IDEA_ROW["idea"], "testability": "battery-ready"},
        free_model_output={"idea": REAL_IDEA_ROW["idea"], "testability": "battery-ready",
                           "source": "fable-2026-07-09", "promoted": True})


def test_grade_wrong_when_killed_in_ledger(monkeypatch, tmp_path):
    it = _mk_item()
    ledger = tmp_path / "ideas-ledger.jsonl"
    _write_ledger(ledger, [REAL_IDEA_ROW, {"kind": "kill", "dedupe_key": it.context["dedupe_key"],
                                           "reason": "killed on real-fills A/B", "ts_et": "x"}])
    monkeypatch.setattr(pa, "LEDGER_FILE", ledger)
    result = pa.grade_item(it, {})
    assert result["grading_method"] == "deterministic_cross_check"
    assert result["decision"] == "promoted"
    assert result["correct"] is False
    assert "KILLED" in result["evidence_summary"]


def test_grade_correct_when_recommendation_shows_cleared(monkeypatch, tmp_path):
    it = _mk_item()
    ledger = tmp_path / "ideas-ledger.jsonl"
    _write_ledger(ledger, [REAL_IDEA_ROW])
    monkeypatch.setattr(pa, "LEDGER_FILE", ledger)
    monkeypatch.setattr(pa, "_recommendation_verdict_for",
                        lambda dk, **kw: {"disposition": "CLEARED", "file": "x.json",
                                          "evidence": "SHIP"})
    result = pa.grade_item(it, {})
    assert result["grading_method"] == "deterministic_cross_check"
    assert result["correct"] is True


def test_grade_wrong_when_recommendation_shows_killed(monkeypatch, tmp_path):
    it = _mk_item()
    ledger = tmp_path / "ideas-ledger.jsonl"
    _write_ledger(ledger, [REAL_IDEA_ROW])
    monkeypatch.setattr(pa, "LEDGER_FILE", ledger)
    monkeypatch.setattr(pa, "_recommendation_verdict_for",
                        lambda dk, **kw: {"disposition": "KILLED", "file": "x.json",
                                          "evidence": "KILL"})
    result = pa.grade_item(it, {})
    assert result["correct"] is False


def test_grade_ungraded_when_nothing_found_yet(monkeypatch, tmp_path):
    """The expected, honest state for every currently-promoted idea as of this adapter's
    authorship -- see module docstring."""
    it = _mk_item()
    ledger = tmp_path / "ideas-ledger.jsonl"
    _write_ledger(ledger, [REAL_IDEA_ROW])
    monkeypatch.setattr(pa, "LEDGER_FILE", ledger)
    monkeypatch.setattr(pa, "_recommendation_verdict_for", lambda dk, **kw: None)
    result = pa.grade_item(it, {})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert result["correct"] is None
    assert "still pending" in result["evidence_summary"]


def test_grade_ungraded_when_ambiguous(monkeypatch, tmp_path):
    it = _mk_item()
    ledger = tmp_path / "ideas-ledger.jsonl"
    _write_ledger(ledger, [REAL_IDEA_ROW])
    monkeypatch.setattr(pa, "LEDGER_FILE", ledger)
    monkeypatch.setattr(pa, "_recommendation_verdict_for",
                        lambda dk, **kw: {"disposition": "AMBIGUOUS", "file": "x.md", "n_hits": 2})
    result = pa.grade_item(it, {})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert result["correct"] is None
    assert "not guessed" in result["evidence_summary"]


def test_grade_ungraded_when_dedupe_key_missing():
    it = fma.AuditItem(subject="prospector", item_id="promoted::2026-07-09",
                       timestamp_et="2026-07-09T00:00:00", account="prospector",
                       context={}, free_model_output={})
    result = pa.grade_item(it, {})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert result["correct"] is None


# ---------- registry integration (via the real free_model_audit.py) ----------

def test_wired_in_real_registry(tmp_path, monkeypatch):
    assert "prospector" in fma.AUDIT_SUBJECTS
    adapter = fma.AUDIT_SUBJECTS["prospector"]
    assert adapter.wired is True

    inbox = tmp_path / "inbox"
    ledger = tmp_path / "ideas-ledger.jsonl"
    _write_inbox(inbox, "2026-07-09-prospector-gex_flip_from_banked_cboe.md", REAL_CHEF_INBOX_MD)
    _write_ledger(ledger, [REAL_IDEA_ROW])
    items = list(adapter.collect(None, date(2026, 7, 9), inbox_dir=inbox, ledger_path=ledger))
    assert len(items) == 1

    monkeypatch.setattr(pa, "LEDGER_FILE", ledger)
    monkeypatch.setattr(pa, "_recommendation_verdict_for", lambda dk, **kw: None)
    result = adapter.grade(items[0], {"allow_llm_fallback": True})
    assert result["grading_method"] in fma.GRADING_METHODS
    assert result["grading_method"] == "ungraded_insufficient_data"
