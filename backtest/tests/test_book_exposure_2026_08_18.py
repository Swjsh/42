"""Guards for the book-level exposure ceiling (the gap that had no code at all).

CONTEXT: 5 SPY arms, each a separate account with its own isolated kill switch (Rule 5) and
per-trade cap (Rule 6). Those work -- and their independence WAS the gap: all 5 trade one
shared signal at r=0.846, and nothing summed what they could commit at once (~42% of book
theoretically). Calibration is measured, not guessed: replaying real fills, peak concurrent
book notional was $4,596 = 18.7% of a ~$24.5K book, on 2026-08-14 (also the book's
second-worst day). Default cap 25% therefore truncates the tail without having bound a
single historical entry.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("book_exposure", REPO / "setup" / "scripts" / "book_exposure.py")
be = importlib.util.module_from_spec(spec)
spec.loader.exec_module(be)  # type: ignore[union-attr]

EQ = {"safe-2": 5266.38, "bold-2": 5048.40, "safe-3": 5000.0, "risky-1": 5000.0, "risky-3": 4200.0}
BOOK = sum(EQ.values())


def test_notional_is_premium_times_qty_times_100() -> None:
    assert be.position_notional(3, 0.42) == pytest.approx(126.0)
    assert be.position_notional(-3, 0.42) == pytest.approx(126.0), "short qty still consumes premium"
    assert be.position_notional(None, 0.42) == 0.0
    assert be.position_notional(3, "x") == 0.0


def test_empty_book_is_allowed_and_not_degraded() -> None:
    r = be.evaluate({}, EQ, prospective_notional=0.0)
    assert r["allowed"] is True and r["degraded"] is None
    assert r["current_notional"] == 0.0


def test_the_measured_historical_peak_would_NOT_have_been_blocked() -> None:
    """THE CALIBRATION GUARD. The worst real moment must sit under the default cap --
    otherwise this ceiling is not 'truncate the tail', it is a behaviour change."""
    peak = be.OBSERVED_PEAK_USD          # $4,596 across all five arms, 2026-08-14 09:47 ET
    r = be.evaluate({"safe-2": [{"qty": peak / 100.0, "premium": 1.0}]}, EQ)
    assert r["allowed"] is True, (
        f"the observed historical peak ({peak}) breaches the default cap -- either the cap is "
        "mis-set or the book changed; do not silently loosen it, re-derive it"
    )
    assert r["projected_pct"] < be.DEFAULT_MAX_BOOK_EXPOSURE_PCT


def test_the_theoretical_42pct_pile_in_IS_blocked() -> None:
    """The whole point: five correlated arms simultaneously at their per-account caps."""
    notional = BOOK * 0.42
    r = be.evaluate({}, EQ, prospective_notional=notional)
    assert r["allowed"] is False
    assert "BOOK_EXPOSURE_CAP" in r["reason"]
    assert "r=0.846" in r["reason"], "the reason must explain WHY per-account caps don't bound this"


def test_cap_is_evaluated_on_PROJECTED_not_current_exposure() -> None:
    """A candidate entry must be judged including itself, or the cap is always one trade late."""
    open_now = {"safe-2": [{"qty": 10, "premium": 2.0}]}      # $2,000 already open
    r_measure = be.evaluate(open_now, EQ, prospective_notional=0.0)
    assert r_measure["allowed"] is True
    r_add = be.evaluate(open_now, EQ, prospective_notional=BOOK * 0.24)
    assert r_add["allowed"] is False, "prospective notional was ignored -- cap fires one trade late"


def test_boundary_is_inclusive_at_exactly_the_cap() -> None:
    exact = BOOK * be.DEFAULT_MAX_BOOK_EXPOSURE_PCT
    assert be.evaluate({}, EQ, prospective_notional=exact)["allowed"] is True
    assert be.evaluate({}, EQ, prospective_notional=exact * 1.001)["allowed"] is False


def test_sums_across_ALL_arms_not_just_one() -> None:
    """The defect being fixed: per-arm views each looked fine while the book did not."""
    each = BOOK * 0.08                       # 8% each -- every arm individually modest
    positions = {a: [{"qty": each / 100.0, "premium": 1.0}] for a in EQ}   # 5 x 8% = 40%
    r = be.evaluate(positions, EQ)
    assert r["allowed"] is False, "five individually-fine arms summed past the ceiling undetected"
    assert len(r["per_arm_notional"]) == 5


def test_fails_OPEN_and_LOUD_when_equity_is_unavailable() -> None:
    """OP-32 scar: a guard must never halt trading because a state read failed."""
    r = be.evaluate({"safe-2": [{"qty": 100, "premium": 5.0}]}, {}, prospective_notional=1e9)
    assert r["allowed"] is True, "failed CLOSED -- this can lock the operator out of his own system"
    assert r["degraded"] and "failing OPEN" in r["degraded"]
    assert r["projected_pct"] is None


def test_degraded_is_None_on_a_clean_evaluation() -> None:
    """Callers branch on `degraded`; it must not be truthy when the reading is good."""
    assert be.evaluate({}, EQ)["degraded"] is None


def test_malformed_positions_do_not_raise() -> None:
    r = be.evaluate({"safe-2": [{"qty": "x", "premium": None}, {}], "bold-2": None}, EQ)
    assert r["allowed"] is True and isinstance(r["current_notional"], float)


def test_active_spy_arms_excludes_futures_and_retired() -> None:
    arms = be.active_spy_arms()
    assert arms, "registry yielded no active SPY arms"
    ids = {a["arm_id"] for a in arms}
    assert "safe-1" not in ids, "retired arm included"
    for a in arms:
        assert a["account_number"].startswith("PA"), f"non-paper account in roster: {a}"
    assert not any(str(i).startswith("mes") for i in ids), "futures arm included"


def test_active_spy_arms_fails_soft_on_missing_registry(tmp_path: Path) -> None:
    assert be.active_spy_arms(tmp_path / "nope.json") == []
