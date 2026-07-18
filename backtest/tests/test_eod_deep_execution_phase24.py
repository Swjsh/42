"""Execution module Phase 2.4 tests (EOD-PHASE-2.4 slice — real fill-timing +
partial-fill implementation, replacing the Phase-1 shallow stub).

Covers:
  - no trades -> neutral stub score, no crash
  - fast, clean fill (lag <=60s, no partial, no slippage data) -> high score
  - slow fill (lag >300s) -> timing sub-score penalized
  - partial fill spread >60s -> partial sub-score penalized
  - missing engine_decisions (e.g. J-manual entry, decisions.jsonl gap) ->
    degrades gracefully to a neutral-low timing score, never crashes
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))

from autoresearch.eod_deep.schema import CategoryScore, TradeRecord, Fill, EngineDecision  # noqa: E402
from autoresearch.eod_deep.modules import execution as execution_mod  # noqa: E402


def _base_trade(**overrides) -> TradeRecord:
    defaults = dict(
        id="trade_1",
        setup_name="BULLISH_RECLAIM_RIDE_THE_RIBBON",
        direction="long",
        underlying="SPY",
        expiry_date="2026-05-14",
        strike=745.0,
        option_type="C",
        fills=[],
        entry_price=1.67,
        avg_exit_price=3.06,
        qty_entered=10,
        qty_exited=10,
        qty_outstanding=0,
        pnl_dollars_realized=1499.60,
        pnl_dollars_unrealized=0.0,
        pnl_pct_on_capital=89.8,
        hold_minutes=119,
        triggers_fired=[],
        setup_score="10/11",
        doctrine_compliance_score=100.0,
        rule_breaks=[],
        journaled_before_entry=True,
        engine_decisions=[],
    )
    defaults.update(overrides)
    return TradeRecord(**defaults)


def test_no_trades_returns_neutral_stub():
    result = execution_mod.analyze_execution(data=None, trades=[])
    assert isinstance(result, CategoryScore)
    assert result.score == 50.0
    assert result.evidence["trade_count"] == 0


def test_fast_clean_fill_scores_high():
    trade = _base_trade(
        engine_decisions=[
            EngineDecision(time_et="09:58:00", tick_or_fire_id=1, decision="ENTER_BULL", reasoning="reclaim"),
        ],
        fills=[
            Fill(time_et="09:58:35", side="buy", qty=10, price=1.67, source="engine_heartbeat", reason="entry"),
        ],
    )
    result = execution_mod.analyze_execution(data=None, trades=[trade])
    per_trade = result.evidence["per_trade"][0]
    assert per_trade["fill_lag_secs"] == 35
    assert per_trade["is_partial_fill"] is False
    assert per_trade["timing_pts"] == 40.0
    assert per_trade["partial_pts"] == 30.0
    # No slippage data on the fill -> neutral slippage sub-score
    assert per_trade["slippage_pts"] == 22.0
    assert result.score >= 85.0


def test_slow_fill_penalizes_timing_subscore():
    trade = _base_trade(
        engine_decisions=[
            EngineDecision(time_et="09:58:00", tick_or_fire_id=1, decision="ENTER_BULL", reasoning="reclaim"),
        ],
        fills=[
            Fill(time_et="10:05:00", side="buy", qty=10, price=1.67, source="engine_heartbeat", reason="entry"),
        ],
    )
    result = execution_mod.analyze_execution(data=None, trades=[trade])
    per_trade = result.evidence["per_trade"][0]
    assert per_trade["fill_lag_secs"] == 420  # 7 minutes
    assert per_trade["timing_pts"] == 10.0


def test_spread_out_partial_fill_penalizes_partial_subscore():
    trade = _base_trade(
        engine_decisions=[
            EngineDecision(time_et="09:58:00", tick_or_fire_id=1, decision="ENTER_BULL", reasoning="reclaim"),
        ],
        fills=[
            Fill(time_et="09:58:35", side="buy", qty=5, price=1.67, source="engine_heartbeat", reason="entry"),
            Fill(time_et="10:02:10", side="buy", qty=5, price=1.71, source="engine_heartbeat", reason="entry"),
        ],
    )
    result = execution_mod.analyze_execution(data=None, trades=[trade])
    per_trade = result.evidence["per_trade"][0]
    assert per_trade["is_partial_fill"] is True
    assert per_trade["partial_clip_count"] == 2
    assert per_trade["partial_spread_secs"] == 215  # 10:02:10 - 09:58:35
    assert per_trade["partial_pts"] == 12.0  # spread > 60s


def test_missing_engine_decisions_degrades_gracefully_not_crash():
    """A J-manual entry or a decisions.jsonl gap must never crash the category —
    it should fall back to a neutral-low timing score."""
    trade = _base_trade(
        engine_decisions=[],  # nothing to match a trigger against
        fills=[
            Fill(time_et="09:58:35", side="buy", qty=10, price=1.67, source="j_manual", reason="entry"),
        ],
    )
    result = execution_mod.analyze_execution(data=None, trades=[trade])
    per_trade = result.evidence["per_trade"][0]
    assert per_trade["fill_lag_secs"] is None
    assert per_trade["timing_pts"] == 25.0
    assert isinstance(result.score, float)


def test_tight_partial_fill_within_60s_scores_between_full_and_spread_out():
    trade = _base_trade(
        engine_decisions=[
            EngineDecision(time_et="09:58:00", tick_or_fire_id=1, decision="ENTER_BULL", reasoning="reclaim"),
        ],
        fills=[
            Fill(time_et="09:58:35", side="buy", qty=5, price=1.67, source="engine_heartbeat", reason="entry"),
            Fill(time_et="09:59:00", side="buy", qty=5, price=1.68, source="engine_heartbeat", reason="entry"),
        ],
    )
    result = execution_mod.analyze_execution(data=None, trades=[trade])
    per_trade = result.evidence["per_trade"][0]
    assert per_trade["is_partial_fill"] is True
    assert per_trade["partial_spread_secs"] == 25
    assert per_trade["partial_pts"] == 22.0
