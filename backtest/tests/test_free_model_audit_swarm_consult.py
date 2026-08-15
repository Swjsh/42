"""Guards for free_model_audit_swarm_consult.py -- the "swarm_consult" AUDIT_SUBJECTS adapter
(AUDIT-HARNESS-B3).

REAL_CONSULT_2026_06_28 below is copied VERBATIM from the actual
analysis/swarm-consult/2026-06-28-224358-decide-how-confident-should-we-be-that-the-gamma-0dte-
spy.json file on disk (confirmed via direct Read before this adapter was built, per the task's
own instruction not to trust the description alone) -- real production swarm_consult output,
not invented. collect_items parsing tests run against a copy of this real file.
Grading-dispatch tests use small synthetic consults + monkeypatched _blind_reanswer/
_agreement_judgment (mirrors free_model_audit_heartbeat_veto's own test pattern of
monkeypatching `_llm_judgment` rather than spawning a real `claude` subprocess in tests).
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

# DO NOT _load() this one (fixed 2026-08-15). free_model_audit imports it ITSELF while
# building AUDIT_SUBJECTS (free_model_audit.py:237), and the adapter's `grade` closes over
# THAT module instance. Re-executing the file here produced a SECOND, distinct module object,
# so every `monkeypatch.setattr(sca, "_blind_reanswer", ...)` below patched a copy the adapter
# never calls -- and `grade` then ran the REAL `_blind_reanswer`, i.e. a test that believed it
# was mocked was firing a live `claude` subprocess. It "failed" only because that call fails on
# this box; with a working subprocess it would have passed while silently spending money.
# Binding to the sys.modules entry keeps one instance, which is what the adapter uses.
sca = sys.modules["free_model_audit_swarm_consult"]


# ---------- REAL fixture (verbatim from disk, 2026-06-28-224358 consult) ----------

REAL_CONSULT_2026_06_28 = {
    "ts_et": "2026-06-28T22:43:58",
    "mode": "decide",
    "question": "How confident should we be that the Gamma 0DTE SPY options engine will have a "
               "profitable week starting Monday 2026-06-29? Assess: (1) engine mechanical "
               "readiness -- will heartbeat fire, detect, size, and manage orders correctly? "
               "(2) edge confidence -- is BEARISH_REJECTION_RIDE_THE_RIBBON a real armable "
               "edge given recent BEAR losses + BULL historical bias? (3) profitable week "
               "probability. Be brutally adversarial. Surface single-point failures.",
    "context": "ENGINE: GREEN, 103/104 gym validators pass. SPY=732.14 BEAR ribbon (below "
              "50SMA 733.35). Both accounts FLAT. 62 tasks registered. ONLY armed strategy: "
              "BEARISH_REJECTION_RIDE_THE_RIBBON (paper). RECENT BEAR trades: 06-26 -237, -15 "
              "(2 losses). Best wins: 06-15 +474+78 BULL, 05-14 +1500 BULL. J anchor trade "
              "history: 5:1 BULL:BEAR win ratio.",
    "slug": "how-confident-should-we-be-that-the-gamma-0dte-spy",
    "total_cost_usd": 0.0,
    "total_elapsed_s": 18.78,
    "synthesis": {
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "ok": True,
        "content": "Keep BEARISH_REJECTION_RIDE_THE_RIBBON in paper-only mode for the week of "
                  "2026-06-29. Do not enable live trading until the strategy demonstrates a "
                  "restored edge and the OPRA cache is verified fresh. The mechanical engine "
                  "is ready, but sole reliance on a historically weak BEAR edge, combined with "
                  "recent losses and a stale data feed, creates a single-point failure.",
        "input_tokens": 1487, "output_tokens": 868, "cost_usd": 0.0, "elapsed_s": 8.586,
        "error": None,
    },
}


def _write_consult(consult_dir: Path, fname: str, payload: dict) -> Path:
    consult_dir.mkdir(parents=True, exist_ok=True)
    p = consult_dir / fname
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ---------- collect_items: parsing on the REAL consult ----------

def test_collect_items_reads_real_consult(tmp_path):
    _write_consult(tmp_path, "2026-06-28-224358-decide-x.json", REAL_CONSULT_2026_06_28)
    items = sca.collect_items(None, date(2026, 6, 28), consult_dir=tmp_path)
    assert len(items) == 1
    it = items[0]
    assert it.subject == "swarm_consult"
    assert it.item_id == "consult:2026-06-28-224358-decide-x"
    assert it.account == "swarm_consult"
    assert it.timestamp_et == "2026-06-28T22:43:58"
    assert it.context["mode"] == "decide"
    assert it.context["question"] == REAL_CONSULT_2026_06_28["question"]
    assert it.free_model_output == REAL_CONSULT_2026_06_28["synthesis"]
    assert it.free_model_output["ok"] is True


def test_collect_items_date_window_filters(tmp_path):
    early = {**REAL_CONSULT_2026_06_28, "ts_et": "2026-06-20T10:00:00"}
    _write_consult(tmp_path, "2026-06-20-early.json", early)
    _write_consult(tmp_path, "2026-06-28-224358-decide-x.json", REAL_CONSULT_2026_06_28)

    only_28 = sca.collect_items(date(2026, 6, 21), date(2026, 6, 28), consult_dir=tmp_path)
    assert len(only_28) == 1
    assert only_28[0].timestamp_et == "2026-06-28T22:43:58"

    both = sca.collect_items(date(2026, 6, 20), date(2026, 6, 28), consult_dir=tmp_path)
    assert len(both) == 2

    only_20 = sca.collect_items(None, date(2026, 6, 20), consult_dir=tmp_path)
    assert len(only_20) == 1


def test_collect_items_skips_malformed_json(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")
    _write_consult(tmp_path, "2026-06-28-224358-decide-x.json", REAL_CONSULT_2026_06_28)
    items = sca.collect_items(None, date(2026, 6, 28), consult_dir=tmp_path)
    assert len(items) == 1


def test_collect_items_missing_dir_returns_empty(tmp_path):
    assert sca.collect_items(None, date(2026, 6, 28), consult_dir=tmp_path / "nope") == []


def test_collect_items_caps_at_max_sample_most_recent_first(tmp_path):
    """Cost bound: J -- 'cap the per-run sample (<=5 consults) to bound cost'. A window with
    MORE than MAX_SAMPLE_PER_RUN candidates must yield only the most recent N, regardless of
    how large the backlog is."""
    for day in range(1, 9):  # 8 candidates, all in-window
        payload = {**REAL_CONSULT_2026_06_28, "ts_et": f"2026-06-{day:02d}T10:00:00"}
        _write_consult(tmp_path, f"2026-06-{day:02d}-decide-x.json", payload)
    items = sca.collect_items(date(2026, 6, 1), date(2026, 6, 8), consult_dir=tmp_path)
    assert len(items) == sca.MAX_SAMPLE_PER_RUN == 5
    ts_values = sorted(it.timestamp_et for it in items)
    # the 5 MOST RECENT of the 8 (days 4-8), not the first 5 encountered alphabetically
    assert ts_values == [f"2026-06-{d:02d}T10:00:00" for d in range(4, 9)]


# ---------- grade_item dispatch ----------

def _mk_item(question="Q?", context_blob="ctx", swarm_content="swarm answer", swarm_ok=True):
    return fma.AuditItem(
        subject="swarm_consult", item_id="consult:x", timestamp_et="2026-06-28T22:43:58",
        account="swarm_consult",
        context={"mode": "decide", "question": question, "context_blob": context_blob,
                "slug": "x"},
        free_model_output={"model": "nvidia/nemotron-3-super-120b-a12b:free", "ok": swarm_ok,
                           "content": swarm_content})


def test_grade_correct_when_blind_reanswer_agrees(monkeypatch):
    it = _mk_item()
    monkeypatch.setattr(sca, "_blind_reanswer", lambda q, c, **kw: "independent answer")
    monkeypatch.setattr(sca, "_agreement_judgment",
                        lambda q, b, s, **kw: {"agree": True, "reason": "same conclusion"})
    result = sca.grade_item(it, {"allow_llm_fallback": True})
    assert result["grading_method"] == "llm_judgment"
    assert result["decision"] == "decide"
    assert result["correct"] is True
    assert "agreement=True" in result["evidence_summary"]
    assert result["detail"]["blind_answer"] == "independent answer"


def test_grade_wrong_when_blind_reanswer_disagrees(monkeypatch):
    it = _mk_item()
    monkeypatch.setattr(sca, "_blind_reanswer", lambda q, c, **kw: "a different conclusion")
    monkeypatch.setattr(sca, "_agreement_judgment",
                        lambda q, b, s, **kw: {"agree": False, "reason": "opposite recommendation"})
    result = sca.grade_item(it, {"allow_llm_fallback": True})
    assert result["grading_method"] == "llm_judgment"
    assert result["correct"] is False


def test_grade_ungraded_when_no_synthesis_content():
    it = _mk_item(swarm_content=None)
    result = sca.grade_item(it, {})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert result["correct"] is None
    assert "no successful synthesis" in result["evidence_summary"]


def test_grade_ungraded_when_synthesis_not_ok():
    it = _mk_item(swarm_ok=False)
    result = sca.grade_item(it, {})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert result["correct"] is None


def test_grade_ungraded_when_question_missing():
    it = _mk_item(question="")
    result = sca.grade_item(it, {})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert "question to re-ask" in result["evidence_summary"]


def test_grade_ungraded_when_llm_fallback_disabled():
    """This subject has NO non-LLM grading path -- blind re-judgment IS the method, so
    --no-llm-fallback must ungrade every item, not silently skip the check."""
    it = _mk_item()
    result = sca.grade_item(it, {"allow_llm_fallback": False})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert result["correct"] is None
    assert "fallback disabled" in result["evidence_summary"]


def test_grade_ungraded_when_blind_reanswer_call_fails(monkeypatch):
    it = _mk_item()
    monkeypatch.setattr(sca, "_blind_reanswer", lambda q, c, **kw: None)
    result = sca.grade_item(it, {"allow_llm_fallback": True})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert "blind re-answer" in result["evidence_summary"]


def test_grade_ungraded_when_agreement_judgment_fails(monkeypatch):
    it = _mk_item()
    monkeypatch.setattr(sca, "_blind_reanswer", lambda q, c, **kw: "independent answer")
    monkeypatch.setattr(sca, "_agreement_judgment", lambda q, b, s, **kw: None)
    result = sca.grade_item(it, {"allow_llm_fallback": True})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert "agreement-judgment" in result["evidence_summary"]


def test_grade_never_calls_sonnet_when_synthesis_missing(monkeypatch):
    """A cost-safety guard: an ungraded-before-any-LLM-call item must never trigger a Sonnet
    subprocess at all."""
    it = _mk_item(swarm_content=None)
    called = {"n": 0}

    def _spy(*a, **kw):
        called["n"] += 1
        return "x"
    monkeypatch.setattr(sca, "_blind_reanswer", _spy)
    sca.grade_item(it, {"allow_llm_fallback": True})
    assert called["n"] == 0


# ---------- _agreement_judgment JSON parsing (mocked subprocess) ----------

def test_agreement_judgment_parses_json(monkeypatch):
    monkeypatch.setattr(sca, "_call_sonnet",
                        lambda prompt, **kw: '{"agree": true, "reason": "converges"}')
    result = sca._agreement_judgment("Q?", "blind", "swarm")
    assert result == {"agree": True, "reason": "converges"}


def test_agreement_judgment_none_when_call_fails(monkeypatch):
    monkeypatch.setattr(sca, "_call_sonnet", lambda prompt, **kw: None)
    assert sca._agreement_judgment("Q?", "blind", "swarm") is None


def test_agreement_judgment_none_when_unparseable(monkeypatch):
    monkeypatch.setattr(sca, "_call_sonnet", lambda prompt, **kw: "not json at all")
    assert sca._agreement_judgment("Q?", "blind", "swarm") is None


def test_blind_reanswer_truncates_long_context(monkeypatch):
    captured = {}

    def _spy(prompt, **kw):
        captured["prompt"] = prompt
        return "answer"
    monkeypatch.setattr(sca, "_call_sonnet", _spy)
    long_ctx = "x" * (sca.CONTEXT_TRUNCATE_CHARS + 500)
    sca._blind_reanswer("Q?", long_ctx)
    assert "[truncated for audit]" in captured["prompt"]
    assert len(captured["prompt"]) < len(long_ctx) + 1000


# ---------- registry integration (via the real free_model_audit.py) ----------

def test_wired_in_real_registry_and_end_to_end_against_the_real_consult(tmp_path, monkeypatch):
    assert "swarm_consult" in fma.AUDIT_SUBJECTS
    adapter = fma.AUDIT_SUBJECTS["swarm_consult"]
    assert adapter.wired is True

    consult_dir = tmp_path / "swarm-consult"
    _write_consult(consult_dir, "2026-06-28-224358-decide-x.json", REAL_CONSULT_2026_06_28)
    items = list(adapter.collect(None, date(2026, 6, 28), consult_dir=consult_dir))
    assert len(items) == 1

    monkeypatch.setattr(sca, "_blind_reanswer", lambda q, c, **kw: "independent answer")
    monkeypatch.setattr(sca, "_agreement_judgment",
                        lambda q, b, s, **kw: {"agree": True, "reason": "same direction"})
    result = adapter.grade(items[0], {"allow_llm_fallback": True})
    assert result["grading_method"] in fma.GRADING_METHODS
    assert result["grading_method"] == "llm_judgment"
    assert result["correct"] is True
