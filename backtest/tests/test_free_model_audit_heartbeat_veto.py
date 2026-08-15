"""Guards for free_model_audit_heartbeat_veto.py -- the heartbeat_veto AUDIT_SUBJECTS adapter.

Fixtures REAL_ROW_0 / REAL_ROW_1 below are VERBATIM rows copied from the real
automation/state/core-decisions.jsonl (confirmed via `grep '"VETOED_BY_MODELS"'`, 15 real
rows found 2026-07-11) -- ts_et, account, scores, lane names, votes, and reasons are the
actual production log, not invented. Parsing tests run against these. Grading-dispatch tests
use small synthetic rows (clearly non-production) with INJECTED fetch/replay functions so no
test ever makes a network call or depends on live Alpaca creds / a `claude` CLI being present.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relpath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fma = _load("free_model_audit", "setup/scripts/free_model_audit.py")
# DO NOT _load() this one (fixed 2026-08-15) -- free_model_audit imports it ITSELF when
# building AUDIT_SUBJECTS, so re-executing the file makes a second module object and any
# monkeypatch here lands on a copy the adapter never calls. This file's tests happen to call
# `hv.grade_item` DIRECTLY rather than through `adapter.grade`, so they were not yet wrong --
# but they sit one added adapter test away from the exact silent-real-LLM-call defect that
# hit the swarm_consult and twin_review guards. Bound to sys.modules so all four siblings
# share one instance and the trap cannot re-open.
hv = sys.modules["free_model_audit_heartbeat_veto"]


# ---------- REAL fixture rows (verbatim from core-decisions.jsonl, 2026-07-11 grep) ----------

REAL_ROW_0 = {
    "ts_et": "2026-07-08T10:04:04", "account": "safe", "armed": True, "spy": 744.09,
    "ribbon": "BEAR", "spread_cents": 178.21365557122135, "vix": 17.08, "htf_15m": "BEAR",
    "verdict": "HOLD", "side": None, "setup": None, "bear_score": 6, "bull_score": 9,
    "triggers": [], "reason": "no setup passed scoring (neither bear nor bull)", "exit_pass": [],
    "extra_signals": [
        {"setup_name": "vwap_continuation", "fired": True, "direction": "long",
         "entry_price": 744.09, "stop_price": 742.74, "confidence": "medium",
         "triggers": ["VWAP_TREND_ESTABLISHED", "VWAP_CONTINUATION_PULLBACK"]},
        {"setup_name": "gap_and_go", "fired": False, "skip_reason": "SKIP_NO_SIGNAL"},
        {"setup_name": "vwap_reclaim_failed_break", "fired": True, "direction": "long",
         "entry_price": 744.09, "stop_price": 743.26, "confidence": "medium",
         "triggers": ["VWAP_TREND_ESTABLISHED", "VWAP_COUNTER_TREND_BREAK_FAILED",
                     "VWAP_WITH_TREND_RECLAIM"]},
    ],
    "action": "HOLD",
    "extra_exec": [
        {"setup": "vwap_continuation", "action": "RISK_DENY_PDT",
         "exec": {"status": "RISK_DENY_PDT",
                 "reason": "safe: 7 day-trades in 5d at equity $1,513 < $25,000 — PDT rule blocks a 4th day-trade",
                 "symbol": "SPY260708C00744000", "qty": 3, "premium": 1.88}},
        {"setup": "vwap_reclaim_failed_break", "action": "VETOED_BY_MODELS",
         "free_eval": {"evaluated": True,
                      "votes": [{"lane": "groq::llama-3.1-8b-instant", "go": False, "reason": "VIX spike"},
                               {"lane": "openrouter::nvidia/nemotron-3-super-120b-a12b:free",
                                "go": False, "reason": ""}],
                      "veto": True}},
    ],
}

REAL_ROW_1 = {
    "ts_et": "2026-07-09T09:51:03", "account": "safe", "armed": True, "spy": 748.11,
    "ribbon": "BULL", "spread_cents": 125.23483097947974, "vix": 16.69, "htf_15m": "MIXED",
    "verdict": "HOLD", "side": None, "setup": None, "bear_score": 8, "bull_score": 10,
    "triggers": [], "reason": "no setup passed scoring (neither bear nor bull)", "exit_pass": [],
    "extra_signals": [
        {"setup_name": "vwap_continuation", "fired": True, "direction": "long",
         "entry_price": 748.11, "stop_price": 745.715, "confidence": "medium",
         "triggers": ["VWAP_TREND_ESTABLISHED", "VWAP_CONTINUATION_BREAKOUT"]},
        {"setup_name": "vix_regime_dayside", "fired": True, "direction": "long",
         "entry_price": 748.11, "stop_price": 745.715, "confidence": "medium",
         "triggers": ["VWAP_DAY_TREND_ESTABLISHED", "VIX_REGIME_FAVORABLE_LOW_NOT_RISING"]},
    ],
    "action": "HOLD",
    "extra_exec": [
        {"setup": "vwap_continuation", "action": "VETOED_BY_MODELS",
         "free_eval": {"evaluated": True,
                      "votes": [{"lane": "ollama::qwen3:14b", "go": False,
                                "reason": "Conflicting HTF15m=MIXED with ENTER_BULL signal"},
                               {"lane": "openrouter::nvidia/nemotron-3-super-120b-a12b:free",
                                "go": False, "reason": "Wide spread (125c) and mixed HTF"}],
                      "veto": True}},
        {"setup": "vix_regime_dayside", "action": "RISK_DENY_PDT",
         "exec": {"status": "RISK_DENY_PDT",
                 "reason": "safe: 7 day-trades in 5d at equity $1,513 < $25,000 — PDT rule blocks a 4th day-trade",
                 "symbol": "SPY260709C00748000", "qty": 3, "premium": 1.92}},
    ],
}


def _write_jsonl(path, rows):
    import json
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---------- collect_items: parsing on REAL rows ----------

def test_collect_items_extracts_real_veto_and_skips_risk_deny(tmp_path):
    p = tmp_path / "core-decisions.jsonl"
    _write_jsonl(p, [REAL_ROW_0])
    items = hv.collect_items(None, date(2026, 7, 8), path=p)
    # exactly ONE item: the VETOED_BY_MODELS extra-setup row. The RISK_DENY_PDT sibling has
    # no free_eval at all and must NOT be collected as an evaluated item.
    assert len(items) == 1
    it = items[0]
    assert it.item_id == "extra:safe:2026-07-08T10:04:04:vwap_reclaim_failed_break"
    assert it.free_model_output["veto"] is True
    assert it.context["side"] == "C"  # direction="long" -> ENTER_BULL -> side C
    assert it.context["setup_name"] == "vwap_reclaim_failed_break"
    assert it.context["spy"] == 744.09
    assert it.context["equity_hint"] == 1513.0  # scraped from the sibling RISK_DENY reason text


def test_collect_items_real_qwen3_nemotron_lanes(tmp_path):
    p = tmp_path / "core-decisions.jsonl"
    _write_jsonl(p, [REAL_ROW_1])
    items = hv.collect_items(None, date(2026, 7, 9), path=p)
    assert len(items) == 1
    votes = items[0].free_model_output["votes"]
    lanes = {v["lane"] for v in votes}
    assert lanes == {"ollama::qwen3:14b", "openrouter::nvidia/nemotron-3-super-120b-a12b:free"}
    assert all(v["go"] is False for v in votes)


def test_collect_items_date_window_filters(tmp_path):
    p = tmp_path / "core-decisions.jsonl"
    _write_jsonl(p, [REAL_ROW_0, REAL_ROW_1])  # 07-08 and 07-09
    only_08 = hv.collect_items(None, date(2026, 7, 8), path=p)
    assert len(only_08) == 1 and only_08[0].timestamp_et.startswith("2026-07-08")
    both = hv.collect_items(date(2026, 7, 8), date(2026, 7, 9), path=p)
    assert len(both) == 2
    since_09 = hv.collect_items(date(2026, 7, 9), date(2026, 7, 9), path=p)
    assert len(since_09) == 1 and since_09[0].timestamp_et.startswith("2026-07-09")


def test_collect_items_missing_file_returns_empty(tmp_path):
    assert hv.collect_items(None, date(2026, 7, 11), path=tmp_path / "nope.jsonl") == []


# ---------- pure helpers ----------

def test_et_naive_to_utc_iso_is_dst_aware_edt():
    # 2026-07-08 is well inside EDT (-4h): 10:04:04 ET -> 14:04:04Z
    assert hv._et_naive_to_utc_iso("2026-07-08T10:04:04") == "2026-07-08T14:04:04Z"


def test_et_naive_to_utc_iso_est_in_winter():
    # 2026-01-15 is EST (-5h): 10:00:00 ET -> 15:00:00Z
    assert hv._et_naive_to_utc_iso("2026-01-15T10:00:00") == "2026-01-15T15:00:00Z"


def test_occ_symbol_matches_known_real_example():
    # SPY260708C00744000 is a REAL symbol seen in REAL_ROW_0's sibling exec block
    sym = hv._occ_symbol("C", 744, datetime(2026, 7, 8))
    assert sym == "SPY260708C00744000"


def test_scan_equity_hint_real_phrasing():
    blob = ('{"reason": "safe: 7 day-trades in 5d at equity $1,513 < $25,000 '
           '\\u2014 PDT rule blocks a 4th day-trade"}')
    assert hv._scan_equity_hint(blob) == 1513.0


def test_scan_equity_hint_absent_returns_none():
    assert hv._scan_equity_hint('{"reason": "no mention of that word here"}') is None


def test_sysmsg_matches_heartbeat_core_source():
    """Drift guard: the Sonnet fallback must judge against the SAME rubric text the free
    models were given. If heartbeat_core.py's sysmsg ever changes, this must be updated too
    -- catch silent divergence instead of grading against a stale rubric forever."""
    src = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    fragment = "Your ONLY job: is this a SANE entry given the tape"
    assert fragment in src, "heartbeat_core.py's sysmsg wording changed -- update _SYSMSG in free_model_audit_heartbeat_veto.py to match"
    assert fragment in hv._SYSMSG


# ---------- grade_item dispatch (synthetic rows, INJECTED replay/fetch -- no network) ----------

def _mk_item(item_id="synthetic:1", side="P", spy=744.0, veto=True, votes=None, exec_block=None):
    votes = votes if votes is not None else [
        {"lane": "ollama::qwen3:14b", "go": not veto},
        {"lane": "openrouter::nvidia/nemotron-3-super-120b-a12b:free", "go": not veto},
    ]
    return fma.AuditItem(
        subject="heartbeat_veto", item_id=item_id, timestamp_et="2026-07-08T10:04:04",
        account="safe",
        context={"is_extra": True, "side": side, "setup_name": "vwap_continuation", "spy": spy,
                "ribbon": "BEAR", "spread_cents": 100.0, "vix": 17.0, "htf_15m": "BEAR",
                "verdict_str": "ENTER_BEAR" if side == "P" else "ENTER_BULL", "triggers": [],
                "bear_score": None, "bull_score": None, "ts_et": "2026-07-08T10:04:04",
                "date_et": "2026-07-08", "account": "safe", "equity_hint": 1500.0,
                "exec": exec_block},
        free_model_output={"evaluated": True, "veto": veto, "votes": votes})


def test_grade_veto_correct_when_replay_shows_a_loser(monkeypatch):
    it = _mk_item(veto=True)
    fake_bars = [{"t": "2026-07-08T14:04:00Z", "o": 1.00, "h": 1.05, "l": 0.40, "c": 0.45}]
    monkeypatch.setattr(hv, "_counterfactual_replay",
                        lambda item, **kw: {"pnl": -50.0, "source": "replay", "symbol": "SPY260708P00742000",
                                            "strike": 742, "equity_used": 1500.0,
                                            "equity_method": "reason_text_scan",
                                            "entry_price_proxy": 1.0, "shape": "v15_3_safe_ratified",
                                            "n_bars": len(fake_bars)})
    result = hv.grade_item(it, {"allow_llm_fallback": True})
    assert result["grading_method"] == "counterfactual"
    assert result["decision"] == "veto"
    assert result["correct"] is True   # blocked a loser -> TRUE veto


def test_grade_veto_wrong_false_veto_when_replay_shows_a_winner(monkeypatch):
    it = _mk_item(veto=True)
    monkeypatch.setattr(hv, "_counterfactual_replay",
                        lambda item, **kw: {"pnl": 120.0, "source": "replay", "symbol": "x",
                                            "strike": 742, "equity_used": 1500.0,
                                            "equity_method": "reason_text_scan",
                                            "entry_price_proxy": 1.0, "shape": "v15_3_safe_ratified",
                                            "n_bars": 5})
    result = hv.grade_item(it, {"allow_llm_fallback": True})
    assert result["correct"] is False  # blocked a winner -> FALSE veto (the costly class)


def test_grade_go_correct_via_real_fill(monkeypatch):
    it = _mk_item(item_id="synthetic:go1", veto=False, exec_block={"symbol": "SPY260708P00742000"})
    monkeypatch.setattr(hv, "_grade_via_real_fill",
                        lambda item: {"pnl": 88.0, "source": "real_fill", "symbol": "SPY260708P00742000"})
    result = hv.grade_item(it, {"allow_llm_fallback": True})
    assert result["grading_method"] == "counterfactual"
    assert result["decision"] == "go"
    assert result["correct"] is True
    assert result["detail"]["source"] == "real_fill"


def test_grade_go_wrong_via_real_fill_loss(monkeypatch):
    it = _mk_item(item_id="synthetic:go2", veto=False, exec_block={"symbol": "SPY260708P00742000"})
    monkeypatch.setattr(hv, "_grade_via_real_fill",
                        lambda item: {"pnl": -200.0, "source": "real_fill", "symbol": "x"})
    result = hv.grade_item(it, {"allow_llm_fallback": True})
    assert result["correct"] is False


def test_grade_falls_back_to_llm_when_replay_infeasible(monkeypatch):
    it = _mk_item(veto=True)
    monkeypatch.setattr(hv, "_counterfactual_replay", lambda item, **kw: None)
    monkeypatch.setattr(hv, "_llm_judgment",
                        lambda item, **kw: {"sonnet_go": False, "sonnet_reason": "VIX spike, chop"})
    result = hv.grade_item(it, {"allow_llm_fallback": True})
    assert result["grading_method"] == "llm_judgment"
    assert result["correct"] is True  # Sonnet independently agrees NO-GO -> veto correct


def test_grade_never_fabricates_when_all_methods_fail(monkeypatch):
    it = _mk_item(veto=True)
    monkeypatch.setattr(hv, "_counterfactual_replay", lambda item, **kw: None)
    monkeypatch.setattr(hv, "_llm_judgment", lambda item, **kw: None)
    result = hv.grade_item(it, {"allow_llm_fallback": True})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert result["correct"] is None


def test_grade_respects_no_llm_fallback_flag(monkeypatch):
    it = _mk_item(veto=True)
    monkeypatch.setattr(hv, "_counterfactual_replay", lambda item, **kw: None)
    called = {"n": 0}

    def _spy_llm(item, **kw):
        called["n"] += 1
        return {"sonnet_go": False, "sonnet_reason": "x"}
    monkeypatch.setattr(hv, "_llm_judgment", _spy_llm)
    result = hv.grade_item(it, {"allow_llm_fallback": False})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert called["n"] == 0  # must never call the LLM when the flag says not to


def test_grade_not_evaluated_is_ungraded():
    it = fma.AuditItem(subject="heartbeat_veto", item_id="x", timestamp_et="t", account="safe",
                       context={}, free_model_output={"evaluated": False, "votes": [], "veto": False})
    result = hv.grade_item(it, {})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert result["correct"] is None


# ---------- veto_reason_class classifier (VETO-HTF-CONFLICT-REGRADE, 2026-07-16) ----------
# All quoted strings below are VERBATIM real free-model vote reasons, grepped out of
# automation/state/core-decisions.jsonl (160 veto-vote reasons, 2026-07-01..07-16) -- not
# invented. See setup/scripts/free_model_audit_heartbeat_veto.py::classify_veto_reason_class
# for the keyword sets and priority rationale.

REAL_HTF_CONFLICT_REASONS = [
    "conflicting HTF15m=MIXED",
    "conflicting HTF15m BEAR",
    "Conflicting HTF15m=MIXED with ENTER_BULL signal; bull=None/11 indicates no confirmed "
    "bull signal; side=None contradicts ENTER_BULL action; wide spread=125.23 ma",
    "Conflicting HTF and ribbon signals: HTF15m=BULL and ribbon=BULL suggest bullish bias, "
    "but entry is bearish (ENTER_BEAR). This creates a direct contradiction in ",
    "conflicting HTF (HTF15m=BULL vs entry=BEAR)",
]

REAL_SPREAD_DATA_DOUBT_REASONS = [
    "Excessive option spread (107 points) indicates illiquid market; avoid entry.",
    "Excessive option spread (45c) indicates poor liquidity, making the entry unsound.",
    "Excessive bid-ask spread (45.38c) indicates poor liquidity for a 0DTE entry.",
    "spread=145.4 is unrealistic for SPY (typical spreads are 1-10 points), likely a data "
    "entry error",
    "spread value of 75.14 is implausibly large for SPY options (typical spreads are "
    "~$0.10-$0.50), indicating a likely data entry error",
]

REAL_OTHER_REASONS = [
    "VIX spike",
    "Conflicting setup parameters: rules_engine_says=ENTER_BULL but side=None. VWAP-based "
    "triggers imply directional bias but lack explicit side assignment. Setup=vw",
    "Conflicting trigger 'ribbon_flip' when ribbon is already BULL. A ribbon flip implies a "
    "change from prior state, but current ribbon is BULL with no indication of",
    "no clear issues with the entry",
    "default",
]

# A real BLENDED reason (both HTF and spread cited in one sentence, 2026-07-08T13:33:12 bold)
# -- must resolve to htf_conflict per the documented priority (this is the common case: 71/76
# real veto items in the full ledger cite HTF, and most of those also mention spread/ribbon).
REAL_BLENDED_HTF_AND_SPREAD_REASON = (
    "conflicting HTF15m bearish and excessively wide spread 52.28c indicates poor liquidity "
    "and counter-trend risk"
)


def test_classify_real_htf_conflict_reasons():
    for r in REAL_HTF_CONFLICT_REASONS:
        assert hv.classify_veto_reason_class(r) == "htf_conflict", r


def test_classify_real_spread_data_doubt_reasons():
    for r in REAL_SPREAD_DATA_DOUBT_REASONS:
        assert hv.classify_veto_reason_class(r) == "spread_data_doubt", r


def test_classify_real_other_reasons():
    for r in REAL_OTHER_REASONS:
        assert hv.classify_veto_reason_class(r) == "other", r


def test_classify_blended_reason_prioritizes_htf():
    assert hv.classify_veto_reason_class(REAL_BLENDED_HTF_AND_SPREAD_REASON) == "htf_conflict"


def test_classify_empty_or_missing_reason_is_other():
    assert hv.classify_veto_reason_class("") == "other"
    assert hv.classify_veto_reason_class(None) == "other"  # type: ignore[arg-type]


def test_item_veto_reason_class_aggregates_across_lanes():
    """One lane cites HTF, the other doesn't -- the item still tags htf_conflict (ANY lane
    citing it is enough, matching the real REAL_ROW_1 fixture shape below)."""
    fmo = {"votes": [
        {"lane": "ollama::qwen3:14b", "go": False,
         "reason": "Conflicting HTF15m=MIXED with ENTER_BULL signal"},
        {"lane": "openrouter::nvidia/nemotron-3-super-120b-a12b:free", "go": False,
         "reason": "no clear issues besides timing"},
    ]}
    assert hv._item_veto_reason_class(fmo) == "htf_conflict"


def test_item_veto_reason_class_real_row1_fixture():
    """REAL_ROW_1's extra-setup veto (both lanes cite HTF/spread) tags htf_conflict."""
    fmo = REAL_ROW_1["extra_exec"][0]["free_eval"]
    assert hv._item_veto_reason_class(fmo) == "htf_conflict"


def test_item_veto_reason_class_no_reasons_is_other():
    assert hv._item_veto_reason_class({"votes": [{"lane": "x", "go": False}]}) == "other"


def test_grade_item_tags_veto_reason_class_on_veto(monkeypatch):
    it = _mk_item(veto=True, votes=[
        {"lane": "ollama::qwen3:14b", "go": False, "reason": "conflicting HTF15m=MIXED"},
        {"lane": "openrouter::...", "go": False, "reason": "HTF15m mixed indicates conflict"},
    ])
    monkeypatch.setattr(hv, "_counterfactual_replay",
                        lambda item, **kw: {"pnl": -50.0, "source": "replay", "symbol": "x",
                                            "strike": 742, "equity_used": 1500.0,
                                            "equity_method": "reason_text_scan",
                                            "entry_price_proxy": 1.0, "shape": "v15_3_safe_ratified",
                                            "n_bars": 1})
    result = hv.grade_item(it, {"allow_llm_fallback": True})
    assert result["veto_reason_class"] == "htf_conflict"


def test_grade_item_does_not_tag_veto_reason_class_on_go(monkeypatch):
    it = _mk_item(item_id="synthetic:go3", veto=False, exec_block={"symbol": "SPY260708P00742000"})
    monkeypatch.setattr(hv, "_grade_via_real_fill",
                        lambda item: {"pnl": 10.0, "source": "real_fill", "symbol": "x"})
    result = hv.grade_item(it, {"allow_llm_fallback": True})
    assert "veto_reason_class" not in result


# ---------- veto_reason_class_breakdown / scorecard section (pure, injected ledger data) ----------

def _write_core_decisions(tmp_path, rows):
    p = tmp_path / "core-decisions.jsonl"
    _write_jsonl(p, rows)
    return p


def test_veto_reason_class_breakdown_joins_history_to_ledger(tmp_path):
    ledger = _write_core_decisions(tmp_path, [REAL_ROW_0, REAL_ROW_1])
    history_items = [
        # REAL_ROW_0's veto reasons are "VIX spike" / "" (empty) -- neither htf nor spread -> other
        {"item_id": "extra:safe:2026-07-08T10:04:04:vwap_reclaim_failed_break",
         "decision": "veto", "correct": True},
        # REAL_ROW_1's veto reasons cite HTF15m/higher time frame in both lanes -> htf_conflict
        {"item_id": "extra:safe:2026-07-09T09:51:03:vwap_continuation",
         "decision": "veto", "correct": False},
        {"item_id": "core:safe:2026-07-08T10:04:04", "decision": "go", "correct": True},  # not a veto -- skipped
    ]
    bd = hv.veto_reason_class_breakdown(history_items, date(2026, 7, 9), path=ledger)
    assert bd["htf_conflict"]["n_tagged"] == 1
    assert bd["htf_conflict"]["false"] == 1
    assert bd["other"]["n_tagged"] == 1
    assert bd["other"]["true"] == 1
    assert bd["spread_data_doubt"]["n_tagged"] == 0
    assert bd["_n_unmatched"] == 0


def test_veto_reason_class_breakdown_never_guesses_unmatched_items(tmp_path):
    ledger = _write_core_decisions(tmp_path, [])  # empty ledger -- nothing to join against
    history_items = [{"item_id": "extra:safe:2026-07-08T10:04:04:vwap_reclaim_failed_break",
                      "decision": "veto", "correct": True}]
    bd = hv.veto_reason_class_breakdown(history_items, date(2026, 7, 9), path=ledger)
    assert bd["_n_unmatched"] == 1
    assert sum(bd[rc]["n_tagged"] for rc in ("htf_conflict", "spread_data_doubt", "other")) == 0


def test_veto_reason_class_scorecard_section_cites_the_study(tmp_path):
    ledger = _write_core_decisions(tmp_path, [REAL_ROW_1])
    history_items = [{"item_id": "extra:safe:2026-07-09T09:51:03:vwap_continuation",
                      "decision": "veto", "correct": False}]
    md = hv.veto_reason_class_scorecard_section(history_items, date(2026, 7, 9), path=ledger)
    assert "vwapcont-htf-precheck-2026-07-16" in md
    assert "htf_conflict" in md and "spread_data_doubt" in md
    assert "INSUFFICIENT EVIDENCE" in md  # n=1 < 5 floor


def test_veto_reason_class_scorecard_section_reports_insufficient_contrast(tmp_path):
    """htf_conflict n>=5 graded, but the OTHER-classes comparison has too little evidence --
    must say INSUFFICIENT CONTRAST, never a false 'ship it' verdict."""
    rows, history_items = [], []
    for i in range(6):
        ts = f"2026-07-{10+i:02d}T09:51:03"
        row = {
            "ts_et": ts, "account": "safe", "spy": 744.0, "ribbon": "BEAR", "spread_cents": 10.0,
            "vix": 15.0, "htf_15m": "MIXED", "verdict": "HOLD", "side": None, "setup": None,
            "bear_score": 5, "bull_score": 5, "triggers": [], "action": "HOLD",
            "extra_signals": [{"setup_name": "vwap_continuation", "direction": "long"}],
            "extra_exec": [{"setup": "vwap_continuation", "action": "VETOED_BY_MODELS",
                            "free_eval": {"evaluated": True,
                                         "votes": [{"lane": "a", "go": False,
                                                   "reason": "conflicting HTF15m=MIXED"}],
                                         "veto": True}}],
        }
        rows.append(row)
        history_items.append({"item_id": f"extra:safe:{ts}:vwap_continuation",
                              "decision": "veto", "correct": (i % 2 == 0)})
    ledger = _write_core_decisions(tmp_path, rows)
    md = hv.veto_reason_class_scorecard_section(history_items, date(2026, 7, 16), path=ledger)
    assert "INSUFFICIENT CONTRAST" in md


def test_n_lanes_answered_asymmetry_stat():
    single_lane = _mk_item(veto=True, votes=[{"lane": "ollama::qwen3:14b", "go": False}])
    both_lanes = _mk_item(veto=True, votes=[{"lane": "a", "go": False}, {"lane": "b", "go": False}])
    assert hv.grade_item.__call__  # sanity the function is callable (dispatch below uses it)
    import types
    fake_grade_ctx = {"allow_llm_fallback": False}
    r1 = hv.grade_item(single_lane, fake_grade_ctx)
    r2 = hv.grade_item(both_lanes, fake_grade_ctx)
    assert r1["n_lanes_answered"] == 1
    assert r2["n_lanes_answered"] == 2
