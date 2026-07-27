"""Pins WHY-NOT PROVENANCE: a no-trade tick must explain itself.

THE INCIDENT (2026-07-27): the engine detected J's setup at 09:40 -- level_rejection @744.9 plus
confluence, bear_score 9/10 -- and refused it on ONE structural blocker (filter 5, ribbon not
BEAR-stacked). The decision ledger recorded `triggers: []`, because engine_cli's `triggers_fired`
is the WINNING side's list and `_derive_routing` returns (None, [], None) when neither side passes.

That single ambiguity -- "detected nothing" vs "detected everything and got hard-blocked" -- sent a
six-agent teardown down a false "the detectors are blind" path and cost hours. The blockers and the
raw per-side detections were BOTH already computed; they were just dropped before reaching the log.

These tests pin the disambiguation so it cannot regress.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import datetime as dt  # noqa: E402

import pandas as pd  # noqa: E402

from backtest.lib.engine.engine_cli import _derive_routing  # noqa: E402
from backtest.lib.engine.score import score_bar  # noqa: E402
from backtest.lib.filters import BarContext  # noqa: E402
from backtest.lib.ribbon import RibbonState  # noqa: E402

# The real 2026-07-27 09:40 bar (IEX, the feed the live engine reads) and the real level set.
LEVELS = [735.88, 736.9, 737.75, 738.46, 739.83, 744.13, 744.9, 745.52, 745.72]


def _ctx(stack: str) -> BarContext:
    hist = [{"open": 744.0, "high": 744.5, "low": 743.5, "close": 744.0, "volume": 500_000}] * 40
    hist += [
        {"open": 744.87, "high": 745.17, "low": 743.9425, "close": 744.655, "volume": 1_167_957},
        {"open": 744.66, "high": 745.52, "low": 744.60, "close": 744.945, "volume": 674_447},
        {"open": 744.91, "high": 744.92, "low": 743.45, "close": 743.45, "volume": 563_475},
        {"open": 743.605, "high": 744.03, "low": 743.22, "close": 743.795, "volume": 585_133},
    ]
    df = pd.DataFrame(hist)
    trig = len(df) - 2  # the 09:40 bar under the live n-2 convention
    rs = RibbonState(fast=744.0, pivot=744.2, slow=744.5, stack=stack, spread_cents=105.1)
    return BarContext(
        bar_idx=trig, timestamp_et=dt.datetime(2026, 7, 27, 9, 40), bar=df.iloc[trig],
        prior_bars=df, ribbon_now=rs, ribbon_history=[rs] * 6, vix_now=19.67, vix_prior=19.6,
        vol_baseline_20=500_000, range_baseline_20=1.0,
        levels_active=list(LEVELS), multi_day_levels=list(LEVELS), htf_15m_stack="BEAR",
    )


# --------------------------------------------------------- the incident, pinned
def test_blocked_setup_still_reports_what_it_detected():
    """bear_score 9 + blockers [5] + REAL detections. The row must not look blind."""
    score = score_bar(_ctx("BULL"))
    assert score.bear_score == 9, "expected exactly one blocker"
    assert score.bear_blockers == [5], f"expected filter 5 only, got {score.bear_blockers}"
    assert "level_rejection" in score.bear.triggers_fired
    assert score.bear.rejection_level == 744.9


def test_winning_triggers_are_empty_while_raw_detections_are_not():
    """THE ambiguity that cost hours: routing says [] while the detectors saw two triggers."""
    score = score_bar(_ctx("BULL"))
    side, winning_triggers, _ = _derive_routing(score)
    assert side is None and winning_triggers == [], "nothing passed, so routing is empty"
    assert score.bear.triggers_fired, (
        "raw detections must survive routing -- an empty `triggers` field must never be the "
        "only evidence available about what the engine saw")


def test_one_input_flip_produces_the_trade():
    """Proves filter 5 was the SOLE cause: change the ribbon, nothing else, and it passes."""
    blocked = score_bar(_ctx("BULL"))
    passed = score_bar(_ctx("BEAR"))
    assert blocked.bear.passed is False and passed.bear.passed is True
    assert passed.bear_blockers == []
    assert passed.bear.rejection_level == 744.9
    side, triggers, level = _derive_routing(passed)
    assert side == "P" and "level_rejection" in triggers and level == 744.9


def test_trigger_tick_metric_would_have_called_a_sighted_engine_blind():
    """Guards the metric that lied: counting `triggers` counts PASSES, not detections."""
    score = score_bar(_ctx("BULL"))
    _, winning, _ = _derive_routing(score)
    assert len(winning) == 0
    assert len(score.bear.triggers_fired) >= 1, (
        "a 'trigger-ticks per day' metric built on the winning list reports 0 on a day the "
        "engine detected everything -- exactly the 2026-07-27 false alarm")


# --------------------------------------------------------- the payload contract
def test_decide_payload_exposes_raw_triggers_and_blockers():
    """heartbeat_core copies these into the ledger; they must exist in the engine output."""
    import inspect

    from backtest.lib.engine import engine_cli
    src = inspect.getsource(engine_cli)
    for key in ('"bear_blockers"', '"bull_blockers"', '"bear_triggers_raw"', '"bull_triggers_raw"'):
        assert key in src, f"{key} missing from decide_payload's output contract"


def test_heartbeat_core_logs_the_why_not_fields():
    src = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    for key in ('"bear_blockers"', '"bear_triggers_raw"', '"levels_active"'):
        assert key in src, f"{key} is not written into the decision row"
