"""Guards for setup/scripts/after_tax_target.py.

This file produces DOLLAR figures about TAX, which is the most dangerous combination in the
repo for being read as advice. The first test therefore pins the disclaimer, and the rest pin
the arithmetic properties that would make it quietly wrong: that the Section 1256 blend can
never be worse than ordinary treatment, that state tax is applied to the whole gain (assuming
otherwise would flatter the XSP case this study is used to argue for), and that the
gross-needed inversion actually inverts.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "setup" / "scripts" / "after_tax_target.py"

_spec = importlib.util.spec_from_file_location("after_tax_target_g", MODULE)
assert _spec and _spec.loader
att = importlib.util.module_from_spec(_spec)
sys.modules["after_tax_target_g"] = att
_spec.loader.exec_module(att)


def test_disclaimer_is_present_and_loud():
    rep = att.build()
    assert "NOT TAX ADVICE" in rep["_DISCLAIMER"]
    assert "NOT TAX ADVICE" in MODULE.read_text(encoding="utf-8")


def test_section_1256_is_never_worse_than_ordinary():
    """60/40 blends in a lower long-term rate, so it can tie but never lose. If it ever
    reads worse, the blend has been inverted."""
    for b in att.BRACKETS.values():
        assert att.section_1256_rate(b) <= att.ordinary_rate(b)


def test_state_tax_applies_to_the_whole_gain_in_the_1256_blend():
    """Assuming a state mirrors the federal long-term preference would flatter XSP -- the
    very case this study is used to argue. The conservative choice must stay."""
    b = {"federal_ordinary": 0.32, "federal_longterm": 0.15, "state": 0.05}
    expected_fed = 0.60 * 0.15 + 0.40 * 0.32
    assert att.section_1256_rate(b) == pytest.approx(expected_fed + 0.05)


def test_zero_state_still_computes():
    b = {"federal_ordinary": 0.32, "federal_longterm": 0.15, "state": 0.0}
    assert att.section_1256_rate(b) == pytest.approx(0.60 * 0.15 + 0.40 * 0.32)


def test_after_tax_never_exceeds_gross():
    for rate in (0.0, 0.1, 0.37, 0.5):
        out = att.after_tax(200.0, rate)
        assert out["net_per_day"] <= 200.0
        assert out["net_per_day"] == pytest.approx(200.0 * (1 - rate))


def test_gross_needed_inverts_after_tax():
    """Round trip: gross_needed(net, r) taxed at r must return exactly net."""
    for rate in (0.05, 0.27, 0.37):
        g = att.gross_needed(150.0, rate)
        assert g * (1 - rate) == pytest.approx(150.0)
        assert g >= 150.0


def test_gross_needed_at_100pct_rate_is_infinite_not_a_crash():
    assert att.gross_needed(100.0, 1.0) == float("inf")


def test_a_higher_bracket_needs_more_gross():
    lo = att.BRACKETS["illustrative_low"]
    hi = att.BRACKETS["illustrative_high"]
    assert (att.gross_needed(200.0, att.ordinary_rate(hi))
            > att.gross_needed(200.0, att.ordinary_rate(lo)))


def test_the_1256_advantage_is_reported_and_positive_at_the_high_bracket():
    rep = att.build((200.0,))
    hi = [r for r in rep["rows"] if r["bracket"] == "illustrative_high"][0]
    assert hi["section_1256_advantage_per_year"] > 0
    assert hi["section_1256_advantage_per_day"] > 0


def test_report_carries_the_cpa_questions_and_the_assumptions():
    rep = att.build()
    assert len(rep["cpa_questions"]) >= 5
    assert rep["assumptions_that_would_change_everything"]
    joined = " ".join(rep["assumptions_that_would_change_everything"]).lower()
    assert "wash" in joined and "475" in joined


def test_trading_day_constants_are_conventional():
    assert att.TRADING_DAYS_PER_YEAR == 252
    assert att.TRADING_DAYS_PER_MONTH == 20
