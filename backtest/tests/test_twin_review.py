"""Guard: setup/scripts/twin_review.py -- the nightly FREE-LLM review of the CRYPTO
TWIN's day.

Locks in: context gathering reads the day's decisions/incidents/coverage/soak/
sentinel state (via twin_sentinel's own paths, monkeypatchable since they're plain
module attributes read at call time); the free-lane structured-JSON call path
degrades cleanly to the deterministic NO-LLM stats-only report+sidecar -- labeled,
never silently skipped -- when the swarm client fails, returns nothing, or returns
JSON that doesn't validate (bad enum/out-of-range confidence/empty summary); BOTH
the human .md and the machine .json sidecar land at the exact spec'd paths from the
SAME single call; apply_last_review_note_to_sentinel does a READ-MODIFY-WRITE that
preserves every other key already in twin-sentinel.json; and -- the durable guard
for this build's $0 HARD COST RULE -- this file never references the PAID
kitchen_daemon.MODEL_LADDER / run_minimax.call_minimax fallback (see twin_review.py's
own module docstring for why that ladder was deliberately excluded despite
kitchen_seeder.py using it).
"""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import twin_sentinel as tsm  # noqa: E402
import twin_review as trev  # noqa: E402

UTC = timezone.utc


def _write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _isolate_twin_sentinel_paths(monkeypatch, tmp_path):
    """gather_day_context() reads ts.DECISIONS_PATH etc as plain module-attribute
    lookups at call time -- monkeypatching twin_sentinel's constants redirects
    twin_review's reads too, since `import twin_sentinel as ts` inside twin_review.py
    and `import twin_sentinel as tsm` here are the SAME cached module object."""
    monkeypatch.setattr(tsm, "DECISIONS_PATH", tmp_path / "decisions.jsonl")
    monkeypatch.setattr(tsm, "INCIDENTS_PATH", tmp_path / "incidents.jsonl")
    monkeypatch.setattr(tsm, "COVERAGE_PATH", tmp_path / "path-coverage.json")
    monkeypatch.setattr(tsm, "SOAK_LOG_PATH", tmp_path / "soak-log.jsonl")
    monkeypatch.setattr(tsm, "SENTINEL_PATH", tmp_path / "twin-sentinel.json")


def _fake_swarm_json_module(monkeypatch, *, ok: bool, parsed=None, error: str = "boom",
                            lane: str = "openrouter::nvidia/nemotron-3-super-120b-a12b:free"):
    fake = types.ModuleType("swarm_client")
    calls = {}

    def _call_role_json(role, prompt, schema, **kwargs):
        calls["role"] = role
        calls["prompt"] = prompt
        calls["schema"] = schema
        calls["kwargs"] = kwargs
        env = ({"ok": True, "lane": lane, "model": lane.split("::")[-1]} if ok
               else {"ok": False, "error": error, "lane": lane})
        return env, (parsed if ok else None)

    fake.call_role_json = _call_role_json
    monkeypatch.setitem(sys.modules, "swarm_client", fake)
    return calls


_VALID_PARSED = {
    "assessment": "HEALTHY",
    "confidence": 0.9,
    "flags_raised": [],
    "summary": "Nothing unusual. All HOLD, zero errors.",
}


# ============================================================================
# gather_day_context
# ============================================================================
def test_gather_day_context_filters_to_today_utc(tmp_path, monkeypatch):
    _isolate_twin_sentinel_paths(monkeypatch, tmp_path)
    _write_jsonl(tmp_path / "decisions.jsonl", [
        {"ts_utc": "2026-07-10T23:00:00+00:00", "session_date_utc": "2026-07-10", "action": "HOLD"},
        {"ts_utc": "2026-07-11T00:05:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
        {"ts_utc": "2026-07-11T00:10:00+00:00", "session_date_utc": "2026-07-11", "action": "TICK_ERROR",
         "reason": "simulated timeout"},
    ])
    ctx = trev.gather_day_context(datetime(2026, 7, 11, 1, 0, tzinfo=UTC))
    assert ctx["n_ticks_today"] == 2
    assert ctx["n_tick_errors"] == 1
    assert ctx["action_distribution"]["HOLD"] == 1
    assert ctx["action_distribution"]["TICK_ERROR"] == 1
    assert len(ctx["tick_error_sample"]) == 1


def test_gather_day_context_fail_open_on_all_missing_files(tmp_path, monkeypatch):
    _isolate_twin_sentinel_paths(monkeypatch, tmp_path)
    ctx = trev.gather_day_context(datetime(2026, 7, 11, 1, 0, tzinfo=UTC))
    assert ctx["n_ticks_today"] == 0
    assert ctx["incidents_today_n"] == 0
    assert ctx["coverage"] is None
    assert ctx["sentinel_snapshot"] is None


def test_gather_day_context_reads_incidents_and_coverage(tmp_path, monkeypatch):
    _isolate_twin_sentinel_paths(monkeypatch, tmp_path)
    _write_jsonl(tmp_path / "incidents.jsonl", [{"ts_utc": "2026-07-11T00:10:00+00:00"}])
    _write_json(tmp_path / "path-coverage.json",
               {"date_utc": "2026-07-11", "total_branches": 10, "green_branches": 4})
    ctx = trev.gather_day_context(datetime(2026, 7, 11, 1, 0, tzinfo=UTC))
    assert ctx["incidents_today_n"] == 1
    assert ctx["coverage"] == {"total": 10, "green": 4, "incidents": None, "date_utc": "2026-07-11"}


# ============================================================================
# _build_review_prompt -- sanity (content survives into the prompt)
# ============================================================================
def test_build_review_prompt_includes_key_stats():
    ctx = {
        "today_utc": "2026-07-11", "n_ticks_today": 42,
        "action_distribution": {"HOLD": 40, "TICK_ERROR": 2},
        "n_tick_errors": 2, "tick_error_sample": [{"ts_utc": "t", "reason": "timeout"}],
        "incidents_today_n": 1, "incidents_undated": 0,
        "incidents_sample": [{"ts_utc": "2026-07-11T00:00:00+00:00", "kind": "x"}],
        "coverage": {"total": 10, "green": 5, "date_utc": "2026-07-11"},
        "soak_rows_sample": [], "sentinel_snapshot": {"verdict": "GREEN", "reasons": []},
        "decisions_sample": [{"ts_utc": "t", "action": "HOLD", "verdict": "HOLD", "reason": "x"}],
    }
    prompt = trev._build_review_prompt(ctx)
    assert "42" in prompt
    assert "TICK_ERROR" in prompt
    assert "timeout" in prompt
    assert "5/10" in prompt or "5" in prompt  # coverage numbers present


# ============================================================================
# _call_free_model_json -- free lane only, never raises
# ============================================================================
def test_call_free_model_json_success_returns_ok_and_parsed(monkeypatch):
    calls = _fake_swarm_json_module(monkeypatch, ok=True, parsed=dict(_VALID_PARSED))
    env, parsed = trev._call_free_model_json("some prompt")
    assert env["ok"] is True
    assert parsed["assessment"] == "HEALTHY"
    assert calls["role"] == "critic"
    assert calls["schema"] == trev.REVIEW_JSON_SCHEMA
    assert calls["kwargs"]["system"] == trev.REVIEW_SYSTEM_PROMPT


def test_call_free_model_json_failure_returns_none_parsed(monkeypatch):
    _fake_swarm_json_module(monkeypatch, ok=False, error="all lanes 429")
    env, parsed = trev._call_free_model_json("some prompt")
    assert env["ok"] is False
    assert parsed is None


def test_call_free_model_json_import_error_is_caught(monkeypatch):
    monkeypatch.setitem(sys.modules, "swarm_client", None)  # forces ImportError
    env, parsed = trev._call_free_model_json("some prompt")
    assert env["ok"] is False
    assert parsed is None


def test_call_free_model_json_never_raises_on_client_exception(monkeypatch):
    fake = types.ModuleType("swarm_client")

    def _boom(role, prompt, schema, **kwargs):
        raise RuntimeError("simulated network crash")

    fake.call_role_json = _boom
    monkeypatch.setitem(sys.modules, "swarm_client", fake)
    env, parsed = trev._call_free_model_json("some prompt")
    assert env["ok"] is False
    assert "RuntimeError" in env["error"]


# ============================================================================
# _validate_parsed -- the stricter enum/range check beyond schema type-checking
# ============================================================================
def test_validate_parsed_accepts_well_formed():
    assert trev._validate_parsed(dict(_VALID_PARSED)) is True


def test_validate_parsed_rejects_bad_assessment_enum():
    bad = dict(_VALID_PARSED, assessment="FINE")
    assert trev._validate_parsed(bad) is False


def test_validate_parsed_rejects_confidence_out_of_range():
    bad = dict(_VALID_PARSED, confidence=1.5)
    assert trev._validate_parsed(bad) is False


def test_validate_parsed_rejects_confidence_as_bool():
    """isinstance(True, int) is True in Python -- must be explicitly excluded."""
    bad = dict(_VALID_PARSED, confidence=True)
    assert trev._validate_parsed(bad) is False


def test_validate_parsed_rejects_empty_summary():
    bad = dict(_VALID_PARSED, summary="   ")
    assert trev._validate_parsed(bad) is False


def test_validate_parsed_rejects_non_dict():
    assert trev._validate_parsed(None) is False
    assert trev._validate_parsed("not a dict") is False


# ============================================================================
# run_review -- LLM mode + NO-LLM fallback, writes BOTH .md and .json sidecar
# ============================================================================
def test_run_review_llm_mode_writes_report_and_sidecar(tmp_path, monkeypatch):
    _isolate_twin_sentinel_paths(monkeypatch, tmp_path)
    _fake_swarm_json_module(monkeypatch, ok=True, parsed=dict(_VALID_PARSED))
    now = datetime(2026, 7, 11, 23, 45, tzinfo=UTC)

    result = trev.run_review(now_utc=now, now_et=now, reviews_dir=tmp_path / "reviews")
    assert result["ok"] is True
    assert result["mode"] == "LLM"
    assert result["assessment"] == "HEALTHY"
    assert result["confidence"] == 0.9

    report_path = Path(result["report_path"])
    assert report_path.exists()
    md_text = report_path.read_text(encoding="utf-8")
    assert "MODE: LLM" in md_text
    assert "ASSESSMENT: HEALTHY" in md_text
    assert "Nothing unusual" in md_text
    assert report_path.name == "2026-07-11.md"

    sidecar_path = Path(result["sidecar_path"])
    assert sidecar_path.exists()
    assert sidecar_path.name == "2026-07-11.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["date"] == "2026-07-11"
    assert sidecar["model_used"]
    assert sidecar["assessment"] == "HEALTHY"
    assert sidecar["confidence"] == 0.9
    assert sidecar["flags_raised"] == []
    assert "Nothing unusual" in sidecar["summary"]


def test_run_review_no_llm_fallback_never_skips(tmp_path, monkeypatch):
    _isolate_twin_sentinel_paths(monkeypatch, tmp_path)
    _fake_swarm_json_module(monkeypatch, ok=False, error="all free lanes exhausted")
    now = datetime(2026, 7, 11, 23, 45, tzinfo=UTC)

    result = trev.run_review(now_utc=now, now_et=now, reviews_dir=tmp_path / "reviews")
    assert result["ok"] is True
    assert result["mode"] == "NO-LLM"
    assert result["model"] is None
    assert result["assessment"] in ("HEALTHY", "DEGRADED", "CONCERNING")
    assert result["confidence"] == trev.NO_LLM_CONFIDENCE

    md_text = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "MODE: NO-LLM" in md_text
    assert "all free lanes exhausted" in md_text

    sidecar = json.loads(Path(result["sidecar_path"]).read_text(encoding="utf-8"))
    assert sidecar["model_used"] is None
    assert sidecar["assessment"] == result["assessment"]


def test_run_review_invalid_llm_json_falls_back_to_no_llm(tmp_path, monkeypatch):
    """The call itself succeeds (ok=True) but the parsed content fails validation
    (bad enum) -- must degrade to NO-LLM, not silently trust a malformed judgment."""
    _isolate_twin_sentinel_paths(monkeypatch, tmp_path)
    _fake_swarm_json_module(monkeypatch, ok=True, parsed=dict(_VALID_PARSED, assessment="MAYBE"))
    now = datetime(2026, 7, 11, 23, 45, tzinfo=UTC)

    result = trev.run_review(now_utc=now, now_et=now, reviews_dir=tmp_path / "reviews")
    assert result["mode"] == "NO-LLM"


def test_run_review_concerning_classification_on_incident_spike(tmp_path, monkeypatch):
    _isolate_twin_sentinel_paths(monkeypatch, tmp_path)
    _fake_swarm_json_module(monkeypatch, ok=False)
    _write_jsonl(tmp_path / "incidents.jsonl", [
        {"ts_utc": "2026-07-11T00:10:00+00:00"},
        {"ts_utc": "2026-07-11T00:20:00+00:00"},
        {"ts_utc": "2026-07-11T00:30:00+00:00"},
    ])
    now = datetime(2026, 7, 11, 23, 45, tzinfo=UTC)
    result = trev.run_review(now_utc=now, now_et=now, reviews_dir=tmp_path / "reviews")
    assert result["mode"] == "NO-LLM"
    assert result["assessment"] == "CONCERNING"
    assert any("incidents=3" in f for f in result["flags_raised"])


def test_run_review_healthy_classification_when_clean(tmp_path, monkeypatch):
    _isolate_twin_sentinel_paths(monkeypatch, tmp_path)
    _fake_swarm_json_module(monkeypatch, ok=False)
    now = datetime(2026, 7, 11, 23, 45, tzinfo=UTC)
    result = trev.run_review(now_utc=now, now_et=now, reviews_dir=tmp_path / "reviews")
    assert result["assessment"] == "HEALTHY"


def test_run_review_summary_line_is_nonempty_in_both_modes(tmp_path, monkeypatch):
    _isolate_twin_sentinel_paths(monkeypatch, tmp_path)
    now = datetime(2026, 7, 11, 23, 45, tzinfo=UTC)

    _fake_swarm_json_module(monkeypatch, ok=True, parsed=dict(_VALID_PARSED, summary="line one\nline two"))
    r_llm = trev.run_review(now_utc=now, now_et=now, reviews_dir=tmp_path / "reviews-llm")
    assert r_llm["summary_line"] == "line one"

    _fake_swarm_json_module(monkeypatch, ok=False)
    r_nollm = trev.run_review(now_utc=now, now_et=now, reviews_dir=tmp_path / "reviews-nollm")
    assert r_nollm["summary_line"].startswith("NO-LLM stats-only:")


def test_run_review_never_raises_even_if_swarm_import_itself_explodes(tmp_path, monkeypatch):
    _isolate_twin_sentinel_paths(monkeypatch, tmp_path)
    monkeypatch.setitem(sys.modules, "swarm_client", None)
    now = datetime(2026, 7, 11, 23, 45, tzinfo=UTC)
    result = trev.run_review(now_utc=now, now_et=now, reviews_dir=tmp_path / "reviews")
    assert result["mode"] == "NO-LLM"
    assert Path(result["report_path"]).exists()
    assert Path(result["sidecar_path"]).exists()


# ============================================================================
# apply_last_review_note_to_sentinel -- read-modify-write, preserves other keys
# ============================================================================
def test_apply_last_review_note_preserves_other_keys(tmp_path):
    sp = tmp_path / "twin-sentinel.json"
    _write_json(sp, {"verdict": "GREEN", "reasons": [], "facts": {"account_status": "LIVE"}})
    trev.apply_last_review_note_to_sentinel(
        {"date_utc": "2026-07-11", "mode": "LLM", "summary": "ok"}, sentinel_path=sp
    )
    on_disk = json.loads(sp.read_text(encoding="utf-8"))
    assert on_disk["verdict"] == "GREEN"
    assert on_disk["facts"]["account_status"] == "LIVE"
    assert on_disk["last_review_note"]["date_utc"] == "2026-07-11"


def test_apply_last_review_note_creates_file_if_missing(tmp_path):
    sp = tmp_path / "twin-sentinel.json"
    assert not sp.exists()
    trev.apply_last_review_note_to_sentinel({"date_utc": "2026-07-11"}, sentinel_path=sp)
    assert sp.exists()
    assert json.loads(sp.read_text(encoding="utf-8"))["last_review_note"]["date_utc"] == "2026-07-11"


# ============================================================================
# main() -- CLI orchestration
# ============================================================================
def test_main_writes_sentinel_note_by_default(tmp_path, monkeypatch):
    _isolate_twin_sentinel_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(trev, "run_review", lambda: {
        "ok": True, "mode": "LLM", "summary_line": "fine", "assessment": "HEALTHY",
        "confidence": 0.9, "report_path": str(tmp_path / "x.md"), "sidecar_path": str(tmp_path / "x.json"),
    })
    sp = tmp_path / "twin-sentinel.json"
    monkeypatch.setattr(tsm, "SENTINEL_PATH", sp)

    rc = trev.main([])
    assert rc == 0
    assert sp.exists()
    on_disk = json.loads(sp.read_text(encoding="utf-8"))
    assert on_disk["last_review_note"]["mode"] == "LLM"
    assert on_disk["last_review_note"]["assessment"] == "HEALTHY"


def test_main_no_sentinel_write_flag_skips_write(tmp_path, monkeypatch):
    monkeypatch.setattr(trev, "run_review", lambda: {
        "ok": True, "mode": "LLM", "summary_line": "fine", "assessment": "HEALTHY",
        "confidence": 0.9, "report_path": str(tmp_path / "x.md"), "sidecar_path": str(tmp_path / "x.json"),
    })
    sp = tmp_path / "twin-sentinel.json"
    monkeypatch.setattr(tsm, "SENTINEL_PATH", sp)

    rc = trev.main(["--no-sentinel-write"])
    assert rc == 0
    assert not sp.exists()


# ============================================================================
# $0 HARD COST RULE guard -- durable, encodes the deliberate deviation from
# kitchen_seeder.py's paid MODEL_LADDER fallback (see module docstring)
# ============================================================================
def test_twin_review_never_references_the_paid_model_ladder():
    """The precise guarantee: neither kitchen_daemon (home of MODEL_LADDER) nor
    run_minimax (home of call_minimax) is ever imported, and call_minimax is never
    invoked -- so MODEL_LADDER can never be reached from this file (it isn't defined
    here). Deliberately does NOT ban the bare word "MODEL_LADDER" from the whole file
    -- the module docstring and section comments legitimately NAME it while
    explaining why it's excluded (see twin_review.py's own docstring); banning the
    substring everywhere would falsely flag that honest disclosure."""
    src = (REPO / "setup" / "scripts" / "twin_review.py").read_text(encoding="utf-8")
    assert "import kitchen_daemon" not in src
    assert "from kitchen_daemon" not in src
    assert "import run_minimax" not in src
    assert "from run_minimax" not in src
    assert "call_minimax(" not in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
