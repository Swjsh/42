"""Guards for multi/evaluate.py -- the per-ticker evaluation surface.

This module is what a human will READ before deciding whether a name is worth trading, so its
guards are about the two ways a reporting surface betrays its reader:

  1. It places an order. It must not be able to -- structurally, not by configuration.
  2. It shows a number that isn't real. A fabricated field on a trading surface is worse than a
     blank one, because a blank one gets investigated and a plausible lie does not.
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

from multi import evaluate as ev  # noqa: E402

SRC = (REPO / "multi" / "evaluate.py").read_text(encoding="utf-8")


# --- 1. structurally cannot trade -----------------------------------------------------------

def test_evaluate_contains_no_order_placement_call():
    """Parsed, not grepped: a docstring mentioning place_bracket must not trip it, and a real
    call must not hide inside a string."""
    tree = ast.parse(SRC)
    banned = ("place_bracket", "market_sell", "close_all_equity_options",
              "cancel_order", "replace_stop_order", "place_option_order")
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name in banned:
                found.append((name, node.lineno))
            for kw in node.keywords or []:
                if kw.arg == "armed":
                    found.append((f"armed= on {name}", node.lineno))
    assert not found, f"the evaluation surface can place orders: {found}"


# --- 2. absence is reported, never defaulted ------------------------------------------------

def _bars(n=60, base=100.0):
    idx = pd.date_range("2026-08-20 09:30", periods=n, freq="5min", tz="America/New_York")
    return pd.DataFrame({"open": [base] * n, "high": [base * 1.002] * n,
                         "low": [base * 0.998] * n, "close": [base] * n,
                         "volume": [1_000_000.0] * n}, index=idx)


def test_unavailable_carries_a_reason_and_is_not_silently_falsy():
    u = ev.Unavailable("chain fetch failed")
    assert u["status"] == ev.UNAVAILABLE
    assert "chain fetch" in u["reason"]
    assert u, "an Unavailable must not be falsy -- a falsy sentinel gets skipped by `if value:`"


def test_zone_map_reports_failure_rather_than_returning_empty_levels_silently():
    """No daily bars means no shelves and no pivots. The card must SAY that, because an empty
    level list and a broken level pipeline look identical to a reader otherwise."""
    out = ev.zone_map("TEST", _bars(), daily=[], spot=100.0, atr=0.5,
                      as_of=pd.Timestamp("2026-08-20 11:00").to_pydatetime())
    assert out["status"] == ev.UNAVAILABLE
    assert out.get("reason"), "an UNAVAILABLE zone map with no reason is unactionable"
    assert out["levels"] == []


def test_structure_read_reports_failure_instead_of_inventing_a_trend():
    """A trend label is a directional claim. If the structure engine cannot produce one, the
    card must not print a default like 'neutral' that a reader would act on."""
    out = ev.structure_read(_bars(n=3))
    assert out["status"] in ("OK", ev.UNAVAILABLE)
    if out["status"] == ev.UNAVAILABLE:
        assert out.get("reason")
    else:
        assert out.get("trend") is not None


def test_evaluate_symbol_on_empty_bars_is_excluded_with_a_named_reason():
    card = ev.evaluate_symbol(
        "TEST", params={}, creds=None, bars5=pd.DataFrame(), bars_daily=pd.DataFrame(),
        vix=ev.mctx.VixContext(now=None, prior=None, ma_5d=0.0, ma_20d=0.0,
                               as_of_et=None, degraded=True, reason="test"),
        with_trade=False)
    assert card["verdict"] == "EXCLUDED"
    assert "bars" in card["verdict_reason"].lower()


def test_a_card_always_carries_a_verdict_and_a_reason():
    """Every terminal path must be interpretable. The old lane emitted 178 HOLDs nobody could
    diagnose; that is the failure mode this asserts against."""
    card = ev.evaluate_symbol(
        "TEST", params={}, creds=None, bars5=_bars(), bars_daily=pd.DataFrame(),
        vix=ev.mctx.VixContext(now=None, prior=None, ma_5d=0.0, ma_20d=0.0,
                               as_of_et=None, degraded=True, reason="test"),
        with_trade=False)
    assert card.get("verdict"), "a card without a verdict is an unanswerable question"
    assert card.get("verdict_reason"), "a verdict without a reason is the old opaque HOLD"


def test_renderer_never_omits_the_verdict_line():
    card = {"symbol": "XYZ", "verdict": "WATCH", "verdict_reason": "no trigger", "spot": 10.0}
    out = ev.render_card(card)
    assert "XYZ" in out and "watch" in out and "no trigger" in out


# --- 3. the quote-error vs illiquidity distinction must survive refactors -------------------

def test_quote_error_and_absent_quote_are_distinguishable_in_source():
    """An API failure and an illiquid contract are DIFFERENT facts. Collapsing them cost this
    lane a full trading day (api-error-masqueraded-as-market-condition-2026-08-20). This pins
    that `prospective_trade` calls the CHECKED quote fetcher, which returns the error
    separately, rather than the bare one that cannot distinguish them."""
    assert "fetch_option_quote_checked" in SRC
    tree = ast.parse(SRC)
    bare = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "fetch_option_quote"]
    assert not bare, f"bare fetch_option_quote cannot distinguish API error from illiquidity: {bare}"
