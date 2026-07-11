"""Guards for trade_autopsy.py's TWIN (mechanism) section -- B2c.

Covers: classify_twin_close's mechanism tags, load_twin_closed_events' UTC-day
filtering, detect_twin_hypotheses' rolling-window CODE-only detectors, and THE
DOCTRINE-RAIL BITE TEST: a twin-derived hypothesis must NEVER land in the main
hypothesis-queue.jsonl (both a behavioral test with isolated tmp paths AND a
static AST guard on write_twin_hypotheses' function body).

Mirrors test_trade_autopsy.py's import convention (importlib.util.spec_from_file_location)
and red-proof style (every detector has a fires case and a below-threshold case).
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "trade_autopsy_twin", REPO / "setup" / "scripts" / "trade_autopsy.py")
ta = importlib.util.module_from_spec(_SPEC)
sys.modules["trade_autopsy_twin"] = ta
_SPEC.loader.exec_module(ta)


# ---------- classify_twin_close ----------

def test_classify_twin_close_known_stage_is_clean():
    c = ta.classify_twin_close({"stage": "structure_stop", "reason": "structure_stop @ 63500"})
    assert c["mechanism_ok"] is True
    assert c["tags"] == []


def test_classify_twin_close_unknown_stage_flags():
    c = ta.classify_twin_close({"stage": "totally_new_stage", "reason": "something"})
    assert "unknown_exit_stage" in c["tags"]
    assert c["mechanism_ok"] is False


def test_classify_twin_close_broker_error_flags():
    c = ta.classify_twin_close({"stage": "structure_stop", "reason": "structure_stop @ 63500",
                                "broker": {"_error": "timeout"}})
    assert "broker_call_failed_on_close" in c["tags"]


def test_classify_twin_close_broker_refused_flags():
    c = ta.classify_twin_close({"stage": "tp1", "reason": "tp1 @ +1.5%",
                                "broker": {"_refused": True}})
    assert "broker_call_failed_on_close" in c["tags"]


def test_classify_twin_close_external_flat_flags():
    c = ta.classify_twin_close({"reason": "broker shows flat"})
    assert "external_flat_detected" in c["tags"]
    assert "unlabeled_close" not in c["tags"]      # the more specific tag wins, not both


def test_classify_twin_close_max_hold_reason_is_clean():
    c = ta.classify_twin_close({"reason": "max_hold_flatten", "elapsed_hours": 6.02})
    assert c["mechanism_ok"] is True
    assert c["tags"] == []


def test_classify_twin_close_unlabeled_flags():
    c = ta.classify_twin_close({"reason": "some_new_undocumented_reason"})
    assert "unlabeled_close" in c["tags"]


def test_classify_twin_close_never_references_pnl():
    """Static assertion at the call level: classify_twin_close's return dict must
    never carry a pnl/dollar key -- the classifier is mechanism-only by construction."""
    c = ta.classify_twin_close({"stage": "trail", "reason": "trail stop"})
    assert not any("pnl" in k.lower() or "dollar" in k.lower() for k in c)


# ---------- load_twin_closed_events ----------

def _twin_row(event, ts_utc, **kw):
    return {"event": event, "ts_utc": ts_utc, "twin": True, "symbol": "BTC/USD", **kw}


def test_load_twin_closed_events_filters_by_utc_date_and_event(tmp_path):
    journal = tmp_path / "journal.jsonl"
    rows = [
        _twin_row("PLACED", "2026-07-11T02:00:00+00:00"),
        _twin_row("CLOSED", "2026-07-11T03:00:00+00:00", stage="structure_stop"),
        _twin_row("CLOSED", "2026-07-10T23:00:00+00:00", stage="tp1"),   # wrong UTC day
        _twin_row("MANAGED", "2026-07-11T04:00:00+00:00", stage="tp1"),  # not CLOSED
    ]
    journal.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = ta.load_twin_closed_events("2026-07-11", journal_path=journal)
    assert len(out) == 1
    assert out[0]["stage"] == "structure_stop"


def test_load_twin_closed_events_missing_journal_returns_empty(tmp_path):
    assert ta.load_twin_closed_events("2026-07-11", journal_path=tmp_path / "nope.jsonl") == []


def test_load_twin_closed_events_skips_malformed_lines(tmp_path):
    journal = tmp_path / "journal.jsonl"
    journal.write_text('{not valid json\n' + json.dumps(_twin_row(
        "CLOSED", "2026-07-11T03:00:00+00:00", stage="structure_stop")) + "\n", encoding="utf-8")
    out = ta.load_twin_closed_events("2026-07-11", journal_path=journal)
    assert len(out) == 1


# ---------- detect_twin_hypotheses ----------

def _closed_row(tags, ts="2026-07-11T03:00:00+00:00"):
    return {"ts_utc": ts, "tags": list(tags), "reason": "x", "stage": None}


def test_detect_twin_hypotheses_fires_above_threshold():
    rows = [_closed_row(["unknown_exit_stage"]) for _ in range(3)]
    hyps = ta.detect_twin_hypotheses(rows, "2026-07-11")
    assert any(h["mechanism"] == "unknown_exit_stage" for h in hyps)


def test_detect_twin_hypotheses_below_floor_is_silent():
    rows = [_closed_row(["unknown_exit_stage"]) for _ in range(2)]   # below TWIN_MIN_ANOMALIES=3
    hyps = ta.detect_twin_hypotheses(rows, "2026-07-11")
    assert not any(h["mechanism"] == "unknown_exit_stage" for h in hyps)


def test_detect_twin_hypotheses_clean_window_emits_nothing():
    rows = [_closed_row([]) for _ in range(10)]
    assert ta.detect_twin_hypotheses(rows, "2026-07-11") == []


def test_detect_twin_hypotheses_empty_window_never_crashes():
    assert ta.detect_twin_hypotheses([], "2026-07-11") == []


def test_detect_twin_hypotheses_respects_roll_n_window():
    """Only the last TWIN_ROLL_N rows count -- old anomalies scroll out."""
    old_anomalies = [_closed_row(["unknown_exit_stage"]) for _ in range(5)]
    clean_padding = [_closed_row([]) for _ in range(ta.TWIN_ROLL_N)]
    rows = old_anomalies + clean_padding
    hyps = ta.detect_twin_hypotheses(rows, "2026-07-11")
    assert not any(h["mechanism"] == "unknown_exit_stage" for h in hyps)


def test_detect_twin_hypotheses_carries_evidence_and_code_only_tests():
    """Contract with downstream consumers: every hypothesis carries evidence +
    concrete proposed_tests, and none of the canned copy mentions dollars/P&L/
    parameters (doctrine rail -- CODE fixes only)."""
    rows = [_closed_row(["broker_call_failed_on_close"]) for _ in range(4)]
    hyps = ta.detect_twin_hypotheses(rows, "2026-07-11")
    assert hyps
    for h in hyps:
        assert h["evidence"] and h["proposed_tests"] and h["claim"] and h["id"]
        assert h["id"].startswith("H-TWIN-")
        blob = (h["claim"] + " ".join(h["proposed_tests"])).lower()
        assert "$" not in blob and "p&l" not in blob and "pnl" not in blob
        assert "spy param" not in blob


def test_detect_twin_hypotheses_unknown_tag_gets_generic_code_only_copy():
    """A future mechanism tag with no canned copy must still produce a CODE-fix
    proposal, never crash on a missing dict entry."""
    rows = [_closed_row(["some_brand_new_tag"]) for _ in range(3)]
    hyps = ta.detect_twin_hypotheses(rows, "2026-07-11")
    assert any(h["mechanism"] == "some_brand_new_tag" for h in hyps)


# ---------- render_twin_section_md ----------

def test_render_twin_section_flat_day_message():
    md = ta.render_twin_section_md("2026-07-11", [], [])
    assert "No twin CLOSED events" in md
    assert "## TWIN (mechanism)" in md


def test_render_twin_section_shows_table_and_never_a_dollar_sign():
    rows = [{"ts_utc": "2026-07-11T03:00:00+00:00",
            "classification": {"stage": "structure_stop", "reason": "structure_stop @ 63500",
                               "mechanism_ok": True, "tags": []}}]
    md = ta.render_twin_section_md("2026-07-11", rows, [])
    assert "structure_stop" in md
    assert "1 clean / 0 mechanism anomaly" in md
    assert "$" not in md          # mechanism-only: never a P&L figure in this section


def test_render_twin_section_shows_hypotheses_when_present():
    rows = [{"ts_utc": "t", "classification": {"stage": None, "reason": "weird",
                                               "mechanism_ok": False, "tags": ["unlabeled_close"]}}]
    hyps = [{"id": "H-TWIN-2026-07-11-unlabeled_close", "mechanism": "unlabeled_close",
            "claim": "test claim", "evidence": {"n_hits": 3}}]
    md = ta.render_twin_section_md("2026-07-11", rows, hyps)
    assert "Twin hypotheses emitted" in md
    assert "H-TWIN-2026-07-11-unlabeled_close" in md


# ============================================================================
# THE DOCTRINE-RAIL BITE TEST -- a twin hypothesis must NEVER land in the main queue
# ============================================================================

def test_write_twin_hypotheses_lands_only_in_twin_lane(tmp_path, monkeypatch):
    main_hyp_queue = tmp_path / "hypothesis-queue.jsonl"     # the FORBIDDEN destination
    twin_hyp_queue = tmp_path / "twin-hypotheses.jsonl"
    queue_md = tmp_path / "queue.md"
    queue_md.write_text("# queue\n\n## Active backlog\n", encoding="utf-8")

    # Even if a future edit accidentally referenced the module-level default, it
    # now points at an ISOLATED tmp file -- this monkeypatch makes the bite real.
    monkeypatch.setattr(ta, "HYP_QUEUE", main_hyp_queue)

    hyps = [{"id": "H-TWIN-2026-07-11-unknown_exit_stage", "mechanism": "unknown_exit_stage",
            "claim": "test claim", "evidence": {"n_hits": 3},
            "proposed_tests": ["add a regression guard"]}]
    # queue_md passed EXPLICITLY (the codebase's established injectable-path
    # convention, e.g. load_engine_positions(ledger_path=...)) -- a bare monkeypatch
    # of the module-level default would NOT flow through here (Python binds a
    # default parameter once at def time, not per call).
    ta.write_twin_hypotheses(hyps, "2026-07-11", twin_hyp_queue=twin_hyp_queue, queue_md=queue_md)

    # 1. the twin-only lane received it, correctly tagged.
    assert twin_hyp_queue.exists()
    twin_rows = [json.loads(line) for line in twin_hyp_queue.read_text(encoding="utf-8").splitlines()]
    assert len(twin_rows) == 1
    assert twin_rows[0]["twin"] is True
    assert twin_rows[0]["mechanism"] == "unknown_exit_stage"

    # 2. THE BITE: the main hypothesis queue was never created/written.
    assert not main_hyp_queue.exists()

    # 3. queue.md got a distinctly-tagged, CODE-ONLY-labeled entry.
    queue_text = queue_md.read_text(encoding="utf-8")
    assert "T-TWIN-AUTOPSY-" in queue_text
    assert "[TWIN/CODE-ONLY]" in queue_text


def test_write_twin_hypotheses_empty_list_is_a_true_noop(tmp_path):
    twin_hyp_queue = tmp_path / "twin-hypotheses.jsonl"
    ta.write_twin_hypotheses([], "2026-07-11", twin_hyp_queue=twin_hyp_queue)
    assert not twin_hyp_queue.exists()


def test_static_write_twin_hypotheses_never_references_main_hyp_queue():
    """AST-level guard (mirrors test_crypto_twin_core.py's namespace-isolation
    static guard style): write_twin_hypotheses' function body must not reference
    the HYP_QUEUE name at all -- catches a future "helpful" fallback write to the
    main queue before any behavioral test even has to run."""
    src = (REPO / "setup" / "scripts" / "trade_autopsy.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "write_twin_hypotheses")
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "HYP_QUEUE" not in names, "write_twin_hypotheses must never reference the main HYP_QUEUE"


def test_static_append_twin_queue_md_never_references_main_hyp_queue():
    src = (REPO / "setup" / "scripts" / "trade_autopsy.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "append_twin_queue_md")
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "HYP_QUEUE" not in names


def test_static_detect_twin_hypotheses_never_computes_dollar_fields():
    """AST-level guard: detect_twin_hypotheses' body must never reference actual_pnl
    / stop_cost_vs_best / any of the SPY $-counterfactual vocabulary -- the twin
    detector is mechanism-only by construction, not merely by convention."""
    src = (REPO / "setup" / "scripts" / "trade_autopsy.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "detect_twin_hypotheses")
    src_segment = ast.dump(fn)
    for forbidden in ("actual_pnl", "stop_cost_vs_best", "best_counterfactual"):
        assert forbidden not in src_segment


def test_main_never_writes_twin_rows_into_spy_day_file(tmp_path, monkeypatch):
    """Integration-shaped unit test: TWIN_OUT_DIR must be a SUBDIRECTORY of OUT_DIR
    (never a sibling `twin-*.jsonl` file inside it) -- otherwise load_recent_rows()'s
    non-recursive glob would silently mix twin rows into the SPY rolling window."""
    assert ta.TWIN_OUT_DIR.parent == ta.OUT_DIR
    assert ta.TWIN_OUT_DIR != ta.OUT_DIR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
