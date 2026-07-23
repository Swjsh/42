"""Tests for backtest/tools/pattern_anchor_verify.py — the pre-ship + drift contract.

Filed 2026-07-23 (self-audit gap: "the system lacks a reliable pre-ship validation step
that confirms a rule actually fires on the specific anchor bars J identified", surfaced
right after `engulfing_at_swing_shelf` shipped without one and was caught, only by manual
OP-33 diligence AFTER shipping, to not fire on either of its two named live-tape anchors).

THE CONTRACT this guard enforces: any PatternRule.anchors entry declares the CURRENT,
HONEST fire state (`expected_fire`). This guard re-derives the actual state from the live
predicate against the real cached bar and asserts they match — for EVERY declared anchor
in the registry, present and future. A registry entry that silently drifts out of sync
with its own cited exhibits (either direction: stops firing where it should, or starts
firing where it honestly shouldn't yet) goes RED here, forcing a conscious update instead
of nobody noticing.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_pattern_anchor_verify.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backtest"))

from lib.patterns import REGISTRY  # noqa: E402
from tools.pattern_anchor_verify import (  # noqa: E402
    _find_bar_index,
    check_registry_anchors,
    find_freshest_csv,
)

MASTER_CSV_AVAILABLE = True
try:
    find_freshest_csv()
except FileNotFoundError:
    MASTER_CSV_AVAILABLE = False

requires_master_csv = pytest.mark.skipif(
    not MASTER_CSV_AVAILABLE, reason="no spy_5m_*.csv master cache on disk"
)


def test_at_least_one_rule_declares_anchors() -> None:
    """The contract only has teeth if something actually uses it -- engulfing_at_swing_shelf
    is the seed case this module was built for."""
    with_anchors = [r for r in REGISTRY if r.anchors]
    assert with_anchors, "expected at least one PatternRule with anchors declared"
    names = {r.name for r in with_anchors}
    assert "engulfing_at_swing_shelf" in names


def test_anchor_schema_well_formed() -> None:
    """Every declared anchor across the whole registry has the required keys and a
    valid bias -- this is enforced at PatternRule construction time (grammar.py
    __post_init__) but re-verified here as a black-box guard against a future refactor
    quietly loosening that validation."""
    for rule in REGISTRY:
        for anchor in rule.anchors:
            assert {"date", "time_et", "bias", "expected_fire"} <= set(anchor)
            assert anchor["bias"] in ("bullish", "bearish")
            assert isinstance(anchor["expected_fire"], bool)


@requires_master_csv
def test_engulfing_at_swing_shelf_bull_anchor_bar_exists() -> None:
    """The 07-21 11:05 bullish anchor bar must actually be present in the freshest
    cached master CSV -- if this goes missing (cache pruned/rotated), the whole
    verification is silently vacuous, which is worse than a loud skip."""
    results = check_registry_anchors(rule_name="engulfing_at_swing_shelf")
    bull = [r for r in results if r["date"] == "2026-07-21"]
    assert bull, "expected the 2026-07-21 11:05 anchor to be checked"
    assert bull[0]["bar_found"] is True


@requires_master_csv
def test_engulfing_at_swing_shelf_bear_anchor_bar_exists() -> None:
    results = check_registry_anchors(rule_name="engulfing_at_swing_shelf")
    bear = [r for r in results if r["date"] == "2026-07-23"]
    assert bear, "expected the 2026-07-23 10:40 anchor to be checked"
    assert bear[0]["bar_found"] is True


@requires_master_csv
def test_all_registry_anchors_match_their_declared_expected_fire_state() -> None:
    """THE guard. If this goes RED, a registry entry has drifted out of sync with an
    anchor exhibit it cites -- either investigate a shared-primitive regression (a rule
    that used to fire on its own anchor no longer does) or, if a follow-up primitive
    fix now makes a previously-honest expected_fire=False anchor fire correctly, UPDATE
    the registry's anchor entry (flip expected_fire=True + note the fix) rather than
    treating this test as the thing to silence."""
    results = check_registry_anchors()
    mismatches = [r for r in results if not r["matches_expected"]]
    assert not mismatches, (
        "anchor drift detected: " + "; ".join(
            f"{m['rule']} @ {m['date']} {m['time_et']} -- {m['detail']}" for m in mismatches
        )
    )


def test_find_bar_index_returns_none_for_unknown_timestamp() -> None:
    """A typo'd anchor timestamp must fail loud (None -> bar_found=False), never
    silently match the wrong bar."""
    class _FakeOpenTime:
        def __init__(self, d, t):
            self._d, self._t = d, t
        def date(self):
            return self._d
        def time(self):
            return self._t

    class _FakeBar:
        def __init__(self, d, t):
            self.open_time = _FakeOpenTime(d, t)

    import datetime as dt
    bars = (_FakeBar(dt.date(2026, 7, 21), dt.time(11, 5)),)
    assert _find_bar_index(bars, "2026-07-21", "11:05") == 0
    assert _find_bar_index(bars, "2026-07-21", "11:10") is None
    assert _find_bar_index(bars, "1999-01-01", "11:05") is None
