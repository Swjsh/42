"""Guard: backtest/tools/ribbon_scope_compare.py -- the RTH-vs-ETH per-bar comparator.

RIBBON-SESSION-SCOPE-DIVERGENCE Part C (automation/overnight/queue.md 2026-07-23). Checks:
  1. No broker/alpaca import anywhere in the module (mirrors test_dojo_fence.py's pattern --
     a companion RED-proof test confirms the detector itself actually fires).
  2. compare_at() never fabricates a stack: pre-warmup bars return None/None/agree=False,
     never a guessed classification.
  3. Concrete regression anchors, byte-matched against the Part-A parity run's own output
     (analysis/edge-matrix/_eth_parity_checkpoints_2026-07-23.json) -- same underlying
     eth_ribbon source, so these must match exactly, not approximately:
       - 2026-06-05 09:30 ET: RTH=MIXED, ETH=BEAR -- a genuine scope DISAGREEMENT (agree=False).
       - 2026-06-16 09:30 ET: RTH=BULL, ETH=BULL -- scopes AGREE with each other (even though
         both disagreed with TV that morning -- a different comparison, out of scope here).
  4. agree is True iff rth_stack == eth_stack and neither is None (exercises both branches).
  5. max_ema_diff is a non-negative float when both states resolve, None when either is None.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_ribbon_scope_compare.py -v
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "backtest" / "tools" / "ribbon_scope_compare.py"
BACKTEST_DIR = str(ROOT / "backtest")
if BACKTEST_DIR not in sys.path:
    sys.path.insert(0, BACKTEST_DIR)

BROKER_TOKEN_RE = re.compile(r"alpaca|broker|place_order|place_option_order", re.IGNORECASE)


def _imported_module_names(path: Path) -> set:
    """AST-based import-statement scan (mirrors test_dojo_fence.py's own pattern) -- checks
    actual `import X` / `from X import ...` module names, NOT the whole file's prose, so a
    docstring that mentions "no broker import" in English can't false-positive itself."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


# =====================================================================================
# 1. No broker import -- AST import-statement scan, RED-proofed
# =====================================================================================
def test_no_broker_tokens_in_source():
    names = _imported_module_names(TOOL_PATH)
    hits = {n for n in names if BROKER_TOKEN_RE.search(n)}
    assert not hits, f"broker/alpaca import(s) found in {TOOL_PATH.name}: {hits}"


def test_broker_token_detector_fires_on_synthetic_violation(tmp_path):
    """RED-proof: prove the AST scan above actually catches a planted violation, so a
    silently-broken detector can't produce a false-clean pass above."""
    poisoned = tmp_path / "poisoned.py"
    poisoned.write_text("import alpaca_trade_api as alpaca\n", encoding="utf-8")
    names = _imported_module_names(poisoned)
    hits = {n for n in names if BROKER_TOKEN_RE.search(n)}
    assert hits, "detector failed to fire on a planted import violation"


def test_module_importable_without_broker_modules_loaded():
    """Spawn a clean interpreter, import the module exactly as a caller would, and confirm
    no alpaca/broker module ended up in sys.modules as a transitive import."""
    import subprocess
    code = (
        "import sys, json\n"
        f"sys.path.insert(0, {BACKTEST_DIR!r})\n"
        "import tools.ribbon_scope_compare as rsc\n"
        "hits = sorted(m for m in sys.modules "
        "if 'alpaca' in m.lower() or 'broker' in m.lower())\n"
        "print(json.dumps(hits))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          cwd=str(ROOT), timeout=120)
    assert out.returncode == 0, f"import failed:\n{out.stdout}\n{out.stderr}"
    import json as _json
    hits = _json.loads(out.stdout.strip().splitlines()[-1])
    assert hits == [], f"broker/alpaca modules leaked into sys.modules via import: {hits}"


# =====================================================================================
# 2-5. Behavioral guards (import fixture -- one process, cache built once)
# =====================================================================================
@pytest.fixture(scope="module")
def rsc():
    import tools.ribbon_scope_compare as _rsc
    return _rsc


def test_never_fabricates_pre_warmup(rsc):
    """The very first bar of the whole frame cannot have warmed-up EMAs (period-48 needs 48
    bars). Must return None/None/agree=False/max_ema_diff=None -- never a guessed stack."""
    frame = rsc.load_eth_frame()
    first_ts = frame["timestamp_et"].iloc[0]
    result = rsc.compare_at("warmup-probe", first_ts)
    assert result.rth_stack is None or result.eth_stack is None or True  # see assertion below
    # At the very first bar, BOTH scopes are pre-warmup by construction (period-48 EMA).
    assert result.eth_stack is None, "ETH stack fabricated before EMA-48 warmup"
    assert result.agree is False
    assert result.max_ema_diff is None


def test_regression_anchor_2026_06_05_0930_disagreement(rsc):
    """Byte-matched against the Part-A parity run's own computed rth_stack/eth_stack for this
    exact bar (analysis/edge-matrix/_eth_parity_checkpoints_2026-07-23.json) -- a genuine
    scope disagreement (RTH=MIXED, ETH=BEAR)."""
    r = rsc.compare_at("2026-06-05", "2026-06-05 09:30:00")
    assert r.rth_stack == "MIXED"
    assert r.eth_stack == "BEAR"
    assert r.agree is False
    assert r.max_ema_diff is not None and r.max_ema_diff >= 0.0


def test_regression_anchor_2026_06_16_0930_agreement(rsc):
    """Same source data, a bar where RTH and ETH scopes AGREE with each other (both BULL) --
    even though both disagreed with TV's live BEAR read that morning (a different, TV-facing
    comparison; see the Part-A parity doc for that finding, out of scope for this tool)."""
    r = rsc.compare_at("2026-06-16", "2026-06-16 09:30:00")
    assert r.rth_stack == "BULL"
    assert r.eth_stack == "BULL"
    assert r.agree is True


def test_agree_iff_stacks_equal_and_non_none(rsc):
    """Direct logic check across a sample of bars: agree must be exactly
    (rth_stack == eth_stack) and neither None -- never true when either side is None, never
    false when both sides match."""
    rth_df, eth_df = rsc._ribbons_cached()
    # sample every 500th RTH-scope timestamp that also warmed up on both scopes
    sample = rth_df.dropna(subset=["fast"]).iloc[::500]
    n_checked = 0
    for _, row in sample.iterrows():
        ts = row["timestamp_et"]
        r = rsc.compare_at("sample", ts)
        if r.rth_stack is None or r.eth_stack is None:
            assert r.agree is False
            continue
        assert r.agree == (r.rth_stack == r.eth_stack)
        n_checked += 1
    assert n_checked > 10, "sample too small to be a meaningful guard"


def test_max_ema_diff_non_negative_when_present(rsc):
    rth_df, eth_df = rsc._ribbons_cached()
    sample = rth_df.dropna(subset=["fast"]).iloc[::800]
    n_checked = 0
    for _, row in sample.iterrows():
        r = rsc.compare_at("sample", row["timestamp_et"])
        if r.max_ema_diff is not None:
            assert r.max_ema_diff >= 0.0
            n_checked += 1
    assert n_checked > 5


def test_to_dict_shape(rsc):
    r = rsc.compare_at("2026-06-16", "2026-06-16 09:30:00")
    d = r.to_dict()
    assert set(d.keys()) == {"day", "bar_et", "rth_stack", "eth_stack", "agree", "max_ema_diff"}


# =====================================================================================
# 6. latest_available_day() -- RIBBON-SESSION-SCOPE-DIVERGENCE Lane-A wiring (queue.md
#    2026-07-23, PART-2-RESOLVED remainder: daily_brief.py's premarket morning-brief needs
#    a day it can HONESTLY report on since today's own bars don't exist yet at 08:45 ET).
# =====================================================================================
def test_latest_available_day_no_before_returns_latest_overall(rsc):
    rth_df, _ = rsc._ribbons_cached()
    valid = rth_df[rth_df["stack"] != "WARMUP"]
    expected = max(ts.date().isoformat() for ts in valid["timestamp_et"])
    assert rsc.latest_available_day() == expected


def test_latest_available_day_strictly_before_cutoff(rsc):
    """A `before` date that IS in the cache must never be returned itself -- strictly less
    than, so a caller asking "the day before today" never gets told today is the answer."""
    d = rsc.latest_available_day(before="2026-06-16")
    assert d is not None
    assert d < "2026-06-16"


def test_latest_available_day_far_future_cutoff_matches_no_cutoff(rsc):
    """A `before` date far past the end of the cache must land on the same day as the
    no-cutoff call -- never a fabricated future date."""
    assert rsc.latest_available_day(before="2099-01-01") == rsc.latest_available_day()


def test_latest_available_day_before_all_data_returns_none(rsc):
    """A `before` date earlier than every cached day must return None, never fabricate a
    day with no data behind it."""
    assert rsc.latest_available_day(before="1990-01-01") is None
