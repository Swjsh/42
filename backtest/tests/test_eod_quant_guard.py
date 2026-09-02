"""Graduated guards for the honest-EOD-digest fix (eod_fallback.py, 2026-07-01).

THE DISEASE THESE RED ON: the free-tier EOD producer inlined the legacy (empty)
decisions.jsonl + loop-state.json (ticks_today=0), so the model wrote
"ENTER signals: 0" on a day with 10 real ENTER_BEAR and 4 fleet fills, and its
journal-append logic deleted everything after '## EOD Reflection' on re-runs.

Guards:
  1. the eod-summary/analyst/manager prompts carry the DETERMINISTIC QUANT block
     (code-computed numbers) and no longer inline the legacy decisions.jsonl
  2. _write_eod_summary preserves trailing sections (### Engine Misses Today)
  3. quant injection is idempotent (one QUANT block after N runs)
  4. COOK 'none' variants are not routed as R&D tasks
"""
import importlib.util
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _load_eod_fallback():
    """Load eod_fallback with run_minimax stubbed (no key/network at import)."""
    stub = types.ModuleType("run_minimax")
    stub.call_minimax = lambda *a, **k: {"ok": False, "error": "stubbed", "cost_usd": 0.0,
                                         "model": "stub"}
    # RESTORE sys.modules AFTERWARDS (2026-09-02). This stub used to be left installed for
    # the rest of the session, and since it is planted at IMPORT time it leaked into every
    # test file collected after this one -- alphabetically that includes
    # test_graduated_guards.py, whose test_free_model_cost_estimate_is_zero does
    # importlib.import_module("run_minimax") and got THIS stub instead of the real module.
    # That test consequently failed in every FULL suite run while passing alone and passing
    # with its own whole file (129 passed) -- the classic "flaky" signature that is really
    # cross-file global-state pollution.
    #
    # Restoring is safe because eod_fallback.py does `from run_minimax import call_minimax`
    # at MODULE level (line 51), so it binds the stub's function into its own namespace
    # during exec_module and never consults sys.modules again.
    prior = sys.modules.get("run_minimax")
    sys.modules["run_minimax"] = stub
    try:
        path = os.path.join(ROOT, "setup", "scripts", "eod_fallback.py")
        spec = importlib.util.spec_from_file_location("eod_fallback_under_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if prior is not None:
            sys.modules["run_minimax"] = prior
        else:
            sys.modules.pop("run_minimax", None)


ef = _load_eod_fallback()
DAY = "2026-07-01"


# ---------------------------------------------------------------------------
# 1. prompts carry deterministic numbers, not the legacy empty ledger
# ---------------------------------------------------------------------------

def test_eod_summary_prompt_carries_quant_not_legacy_ledger():
    prompt, _ = ef._prompt_eod_summary(DAY)
    assert "DETERMINISTIC QUANT" in prompt
    assert "NUMBERS RULE" in prompt
    # the legacy inputs that produced the 2026-07-01 fabrication must be gone
    assert "decisions.jsonl (today only" not in prompt
    assert "loop-state.json" not in prompt


def test_analyst_prompt_carries_quant_not_legacy_ledger():
    prompt, _ = ef._prompt_analyst(DAY)
    assert "DETERMINISTIC QUANT" in prompt
    assert "NUMBERS RULE" in prompt
    assert "decisions.jsonl (today only" not in prompt
    assert "loop-state.json" not in prompt


def test_manager_prompt_carries_quant_not_legacy_ledger():
    prompt, _ = ef._prompt_manager(DAY)
    assert "DETERMINISTIC QUANT" in prompt
    assert "decisions.jsonl (today" not in prompt
    assert "loop-state.json" not in prompt


def test_quant_section_carries_real_ledger_truth():
    """Against the REAL repo ledgers: 2026-07-01 must show the 10 core ENTERs and
    the fleet acceptance -- the exact numbers the old path reported as zero.

    NOTE (2026-07-08, pre-existing drift found + fixed while rewiring T2): this
    assertion had gone stale vs. two UNRELATED prior fixes -- the `rule-blocked`
    funnel column (added after this test was written) and the PLACEMENT BROKEN ->
    PLACEMENT PRE-FIX ARTIFACT reclassification for retired-ladder-only rejection
    days -- so it was failing before any T2 edit touched this file. Values below
    are the current, real, code-computed output (verified by running _quant_section
    directly against the real ledgers)."""
    q = ef._quant_section(DAY)
    assert ef.QUANT_BEGIN in q and ef.QUANT_END in q
    assert "| **TOTAL** | 1278 | 28 | 16 | 0 | 16 | 4 | 4 | 4 |" in q
    assert "PLACEMENT PRE-FIX ARTIFACT[core:safe]" in q
    assert "expires soon" in q  # verbatim broker rejection
    # T2 rewire (HANDOFF-2026-07-09): P&L must now be broker-truth (T1), not the CSV fallback.
    assert "P&L (source: pnl-statement.json (T1, broker-truth))" in q


# ---------------------------------------------------------------------------
# 2 + 3. journal write preserves trailing sections; quant is idempotent
# ---------------------------------------------------------------------------

def _journal_with_trailing(tmp_path):
    j = tmp_path / "journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / f"{DAY}.md").write_text(
        "# Journal\n\n## Premarket\nkeep-premarket\n\n"
        "## EOD Reflection\nOLD fabricated reflection\n\n---\n\n"
        "### Engine Misses Today\nkeep-engine-misses\n", encoding="utf-8")
    return j / f"{DAY}.md"


def test_write_eod_summary_preserves_trailing_sections(tmp_path, monkeypatch):
    target = _journal_with_trailing(tmp_path)
    monkeypatch.setattr(ef, "REPO", tmp_path)
    out = ef._write_eod_summary("## EOD Reflection\nNEW honest reflection\n", DAY,
                                model="test", cost_usd=0.0, omitted=[], primary=True)
    text = out.read_text(encoding="utf-8")
    assert "keep-premarket" in text
    assert "keep-engine-misses" in text, \
        "the old split() logic deleted sections after the reflection -- regression"
    assert "NEW honest reflection" in text
    assert "OLD fabricated reflection" not in text
    assert ef.QUANT_BEGIN in text


def test_write_eod_summary_quant_idempotent(tmp_path, monkeypatch):
    _journal_with_trailing(tmp_path)
    monkeypatch.setattr(ef, "REPO", tmp_path)
    for _ in range(2):
        out = ef._write_eod_summary("## EOD Reflection\nrun\n", DAY,
                                    model="test", cost_usd=0.0, omitted=[], primary=True)
    text = out.read_text(encoding="utf-8")
    assert text.count(ef.QUANT_BEGIN) == 1, "re-runs must not stack quant blocks"
    assert text.count("## EOD Reflection") == 1
    assert "keep-engine-misses" in text


def test_write_eod_summary_appends_when_no_marker(tmp_path, monkeypatch):
    j = tmp_path / "journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / f"{DAY}.md").write_text("# Journal\n\n## Premarket\nkeep\n", encoding="utf-8")
    monkeypatch.setattr(ef, "REPO", tmp_path)
    out = ef._write_eod_summary("## EOD Reflection\nfresh\n", DAY,
                                model="test", cost_usd=0.0, omitted=[], primary=True)
    text = out.read_text(encoding="utf-8")
    assert "keep" in text and "fresh" in text and ef.QUANT_BEGIN in text


# ---------------------------------------------------------------------------
# 4. COOK routing: 'none' variants never become R&D tasks
# ---------------------------------------------------------------------------

def test_cook_none_variants_not_routed():
    tasks, _ = ef._extract_cook_tasks("prose\nCOOK: none\n")
    assert tasks == []
    tasks, _ = ef._extract_cook_tasks("prose\nCOOK: none (if no further tasks).\n")
    assert tasks == []
    tasks, _ = ef._extract_cook_tasks("prose\nCOOK: Backtest the thing with the harness.\n")
    assert tasks == ["Backtest the thing with the harness."]
