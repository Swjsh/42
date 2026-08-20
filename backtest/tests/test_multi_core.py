"""Guards for multi/core.py — the tick loop that will run UNATTENDED.

This module is the one that gets scheduled, so its guards are about what must be true when
nobody is watching:

  1. It cannot place an order. Not "is configured not to" — cannot, structurally.
  2. The funnel narrows, so a scheduled run cannot melt the rate limit on 72 chain reads.
  3. A missing quote is refused, never defaulted — a fabricated mid would pass the gate.
  4. The cascade stays internally consistent, so "why did nothing trade" is answerable.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi import core  # noqa: E402

CORE_SRC = (REPO / "multi" / "core.py").read_text(encoding="utf-8")


# --- 1. structural: no order path ----------------------------------------------------------

def test_tick_module_contains_no_order_placement_call():
    """THE guard. Parsed, not grepped — a docstring mentioning place_bracket must not trip it,
    and an actual call must not slip past because it sits inside a string."""
    tree = ast.parse(CORE_SRC)
    banned = ("place_bracket", "market_sell", "close_all_equity_options",
              "cancel_order", "replace_stop_order")
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name in banned:
                found.append((name, node.lineno))
            for kw in node.keywords or []:
                if kw.arg == "armed":
                    found.append((f"armed= on {name}", node.lineno))
    assert not found, f"the unattended tick loop can place orders: {found}"


def test_broker_calls_are_read_only():
    tree = ast.parse(CORE_SRC)
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and getattr(f.value, "id", "") == "mb":
                called.add(f.attr)
    writes = {c for c in called if not c.startswith(("get_", "equity_", "is_flat", "universe_"))}
    assert not writes, f"tick calls non-read broker functions: {writes}"


# --- 2. the funnel narrows ------------------------------------------------------------------

def _bars(n=80, base=100.0, vol=1_000_000.0):
    idx = pd.date_range("2026-08-01", periods=n, freq="h", tz="America/New_York")
    return pd.DataFrame({
        "open": [base] * n, "high": [base * 1.01] * n,
        "low": [base * 0.99] * n, "close": [base] * n, "volume": [vol] * n,
    }, index=idx)


def test_attention_from_bars_computes_relative_volume():
    df = _bars(80, vol=1_000.0)
    df.iloc[-6:, df.columns.get_loc("volume")] = 10_000.0  # recent surge
    out = core.attention_from_bars({"AAA": df})
    assert "AAA" in out
    assert out["AAA"]["rel_volume"] > 5.0, out["AAA"]


def test_attention_skips_short_frames_without_crashing():
    assert core.attention_from_bars({"AAA": _bars(5)}) == {}
    assert core.attention_from_bars({"AAA": None}) == {}


def test_universe_symbols_dedupes_and_fails_loud_on_empty():
    params = {"universe": {"a": ["SPY", "QQQ"], "b": ["QQQ", "IWM"], "_note": "ignored"}}
    assert core.universe_symbols(params) == ["SPY", "QQQ", "IWM"]
    with pytest.raises(core.TickError, match="universe is empty"):
        core.universe_symbols({"universe": {}})


# --- 3. the liquidity gate refuses rather than defaults -------------------------------------

PARAMS = {"entry": {"liquidity_gate": {"max_spread_pct_of_premium": 8.0,
                                       "min_open_interest": 250, "feed": "indicative"}}}


def test_missing_quote_is_refused_not_defaulted():
    ok, why, facts = core.liquidity_ok(None, PARAMS)
    assert ok is False and "no two-sided quote" in why and facts == {}


def test_one_sided_quote_is_refused():
    ok, why, _ = core.liquidity_ok({"bid": 1.0, "ask": None}, PARAMS)
    assert ok is False


def test_wide_spread_is_refused_and_reports_the_number():
    ok, why, facts = core.liquidity_ok(
        {"bid": 1.00, "ask": 1.50, "open_interest": 5000}, PARAMS)
    assert ok is False
    assert "40.0%" in why or "40" in why
    assert facts["spread_pct"] == pytest.approx(40.0, abs=0.1)


def test_thin_open_interest_is_refused():
    ok, why, _ = core.liquidity_ok(
        {"bid": 1.00, "ask": 1.02, "open_interest": 10}, PARAMS)
    assert ok is False and "OI" in why


def test_a_genuinely_liquid_quote_passes():
    ok, why, facts = core.liquidity_ok(
        {"bid": 2.00, "ask": 2.04, "open_interest": 9000}, PARAMS)
    assert ok is True, why
    assert facts["mid"] == pytest.approx(2.02)
    assert facts["feed"] == "indicative"


# --- 4. the cascade stays honest -------------------------------------------------------------

def test_summary_reports_joint_pass_rate_from_would_place():
    from collections import Counter
    c = Counter({"evaluated": 40, "would_place": 2})
    msg = core.ts_summary(c)
    assert "40" in msg and "2" in msg and "5.0%" in msg


def test_summary_handles_zero_evaluated_without_dividing_by_zero():
    from collections import Counter
    assert "0.0%" in core.ts_summary(Counter())
