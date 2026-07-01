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
    sys.modules["run_minimax"] = stub
    path = os.path.join(ROOT, "setup", "scripts", "eod_fallback.py")
    spec = importlib.util.spec_from_file_location("eod_fallback_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    the fleet acceptance -- the exact numbers the old path reported as zero."""
    q = ef._quant_section(DAY)
    assert ef.QUANT_BEGIN in q and ef.QUANT_END in q
    assert "| **TOTAL** | 1278 | 28 | 16 | 16 | 4 | 4 | 4 |" in q
    assert "PLACEMENT BROKEN[core:safe]" in q
    assert "expires soon" in q  # verbatim broker rejection


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
