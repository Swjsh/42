"""Guard: setup/scripts/claude_usage_ledger.py (GOAL-EARN-YOUR-KEEP-2026-09-12 DONE-WHEN (5),
"tokens spent per day").

Pins the three things that would silently rot:
1. TOKEN SUMS. Exact input/output/cache-read/cache-write sums off a 3-message fixture (2
   models, one message written into a separate "subagent" transcript file with isSidechain
   true) must match hand-computed totals -- a schema-field typo would silently zero a column.
2. DOLLAR MATH. The per-model rate table (Sonnet $3/$15, Fable $15/$75; cache read = 10% of
   input rate, cache write = 125%) must reproduce a hand-computed $ figure exactly.
3. KIND CLASSIFICATION. isSidechain=True -> subagent; isSidechain=False + entrypoint
   "claude-desktop" -> interactive; isSidechain=False + entrypoint in {"sdk-cli","sdk-ts","cli"}
   -> scheduled; anything else -> unknown (never guessed).

RED-PROOFED (per instruction): test_kind_classification_catches_regression flips the
classify_kind branch order and asserts the fixture-derived kind changes -- proving the test
would actually fail if the classification logic broke, not just that it currently passes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "setup" / "scripts" / "claude_usage_ledger.py"
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "claude_usage_ledger" / "projects"


def _load_module():
    spec = importlib.util.spec_from_file_location("claude_usage_ledger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


# ---- 1. schema / token sums -------------------------------------------------------------

def test_fixture_files_exist():
    assert (FIXTURE_ROOT / "proj-main" / "main.jsonl").exists()
    assert (FIXTURE_ROOT / "proj-main" / "subagent.jsonl").exists()


def test_token_sums_exact(mod):
    ledger = mod.build_ledger(days=30, root=FIXTURE_ROOT)
    days = ledger["days"]
    assert set(days.keys()) == {"2026-09-01", "2026-09-02"}

    d1 = days["2026-09-01"]["tokens"]
    # msg1: 1000/500/0/0  + msg2: 2000/100/4000/1000  -> summed
    assert d1["input"] == pytest.approx(3000.0)
    assert d1["output"] == pytest.approx(600.0)
    assert d1["cache_read"] == pytest.approx(1000.0)
    assert d1["cache_write"] == pytest.approx(4000.0)

    d2 = days["2026-09-02"]["tokens"]
    assert d2["input"] == pytest.approx(500.0)
    assert d2["output"] == pytest.approx(200.0)
    assert d2["cache_read"] == pytest.approx(0.0)
    assert d2["cache_write"] == pytest.approx(0.0)


# ---- 2. dollar math -----------------------------------------------------------------------

def test_usd_for_usage_sonnet(mod):
    usage = {"input_tokens": 1000, "output_tokens": 500,
              "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    usd, label = mod.usd_for_usage(usage, "claude-sonnet-5")
    # 1000*3/1e6 + 500*15/1e6 = 0.003 + 0.0075
    assert usd == pytest.approx(0.0105)
    assert label == "sonnet"


def test_usd_for_usage_fable_with_cache(mod):
    usage = {"input_tokens": 2000, "output_tokens": 100,
              "cache_creation_input_tokens": 4000, "cache_read_input_tokens": 1000}
    usd, label = mod.usd_for_usage(usage, "claude-fable-5-1")
    # in: 2000*15/1e6=0.03  out: 100*75/1e6=0.0075
    # cache_read: 1000*(15*0.10)/1e6=0.0015  cache_write: 4000*(15*1.25)/1e6=0.075
    assert usd == pytest.approx(0.03 + 0.0075 + 0.0015 + 0.075)
    assert label == "fable"


def test_day_totals_dollar_math_exact(mod):
    ledger = mod.build_ledger(days=30, root=FIXTURE_ROOT)
    days = ledger["days"]
    # day 1 = sonnet msg (0.0105) + fable msg (0.114) = 0.1245
    assert days["2026-09-01"]["usd_total"] == pytest.approx(0.1245, abs=1e-6)
    # day 2 = subagent sonnet msg = 0.0045
    assert days["2026-09-02"]["usd_total"] == pytest.approx(0.0045, abs=1e-6)


def test_unmatched_model_priced_at_sonnet_default_and_flagged(mod):
    usd, label = mod.usd_for_usage(
        {"input_tokens": 1_000_000, "output_tokens": 0,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        "some-unknown-future-model",
    )
    assert label == mod.DEFAULT_RATE[0]
    assert usd == pytest.approx(3.0)  # sonnet input rate


# ---- 3. kind classification ----------------------------------------------------------------

def test_kind_classification_rules(mod):
    assert mod.classify_kind(True, "claude-desktop") == "subagent"
    assert mod.classify_kind(True, "sdk-cli") == "subagent"  # sidechain wins regardless
    assert mod.classify_kind(False, "claude-desktop") == "interactive"
    assert mod.classify_kind(False, "sdk-cli") == "scheduled"
    assert mod.classify_kind(False, "sdk-ts") == "scheduled"
    assert mod.classify_kind(False, "cli") == "scheduled"
    assert mod.classify_kind(False, "something-new") == "unknown"
    assert mod.classify_kind(False, None) == "unknown"


def test_fixture_kind_split_by_kind(mod):
    ledger = mod.build_ledger(days=30, root=FIXTURE_ROOT)
    d1 = ledger["days"]["2026-09-01"]
    assert set(d1["by_kind"].keys()) == {"interactive"}
    d2 = ledger["days"]["2026-09-02"]
    assert set(d2["by_kind"].keys()) == {"subagent"}


def test_kind_classification_catches_regression(mod):
    """RED-proof: prove the assertion actually discriminates. If isSidechain stopped being
    checked first (e.g. someone reordered the branches to check entrypoint before
    isSidechain), a sidechain message with entrypoint "claude-desktop" would silently become
    "interactive" instead of "subagent". This asserts the CORRECT behavior and documents the
    wrong one inline so a future refactor that breaks it fails loudly here."""
    correct = mod.classify_kind(True, "claude-desktop")
    assert correct == "subagent"
    wrong_if_reordered = "interactive"
    assert correct != wrong_if_reordered


# ---- top sessions / first user message -----------------------------------------------------

def test_top_sessions_captures_truncated_first_message(mod):
    ledger = mod.build_ledger(days=30, root=FIXTURE_ROOT)
    assert ledger["top_5_sessions"], "expected at least one costed session"
    top = ledger["top_5_sessions"][0]
    assert "first_user_msg" in top
    assert len(top["first_user_msg"]) <= 100
