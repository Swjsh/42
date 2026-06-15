"""Phase 3 detection module tests — orchestrator-replay (TDD per CLAUDE.md OP 17).

Tests written FIRST. The Phase 3 detection module replays the actual heartbeat
orchestrator (lib.filters.evaluate_bearish_setup + evaluate_bullish_setup) over
today's RTH bars and emits an EngineDecision per bar.

Hand-computed expected decisions for 3 specific bars on 2026-05-14:

  Bar 09:30 ET (idx 0 RTH): time gate v15 = no entries before 10:00 ET.
    → Expected decision: SKIP_TIME_GATE

  Bar 14:30 ET: 14:00-15:00 ET no-trade-window (v14 rule, kept in v15).
    → Expected decision: SKIP_NO_TRADE_WINDOW

  Bar 10:15 ET (after entry gate): may legitimately fire if setup matches.
    → Expected: any of (HOLD, ENTER_BULL, SKIP_QUALITY_LOCK, SKIP_FILTER_*)

Plus structural tests:
  - analyze_detection returns a CategoryScore
  - evidence dict contains "engine_decisions" list
  - all RTH bars produce an entry (~78 bars on a normal day)
  - performance: complete in <30s
"""
from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
# REPO = C:\Users\jackw\Desktop\42

# Importable: backtest is on sys.path
sys.path.insert(0, str(REPO / "backtest"))

from autoresearch.eod_deep.schema import CategoryScore, TradeRecord, Fill  # noqa: E402
from autoresearch.eod_deep.ingest import IngestedData  # noqa: E402
from autoresearch.eod_deep.modules import detection as detection_mod  # noqa: E402


TODAY = "2026-05-14"


def _build_ingested_for_today(date_str: str = TODAY) -> IngestedData:
    """Minimal IngestedData fixture for today — only the fields detection needs.

    Detection module uses:
      - data.date  → resolves which 5m CSV to load today's bars from
      - data.params (optional) → for v15 thresholds; defaults work without it
    """
    return IngestedData(date=date_str, ingested_at_et=dt.datetime.now().isoformat())


def _build_actual_trade_today() -> TradeRecord:
    """Build the actual trade J's engine took today: BULLISH_RECLAIM_RIDE_THE_RIBBON
    SPY 745C, qty=10, entry 09:58 @ $1.67, TP1 partial 10:40, runner exit 11:57.

    Used to verify the engine-decisions trace matches the actual entry/exit timeline.
    """
    return TradeRecord(
        id="trade_1",
        setup_name="BULLISH_RECLAIM_RIDE_THE_RIBBON",
        direction="long",
        underlying="SPY",
        expiry_date="2026-05-14",
        strike=745.0,
        option_type="C",
        fills=[
            Fill(time_et="09:58:35", side="buy",  qty=10, price=1.67, source="engine_heartbeat", reason="entry"),
            Fill(time_et="10:40:13", side="sell", qty=5,  price=2.26, source="engine_heartbeat", reason="tp1"),
            Fill(time_et="11:24:21", side="sell", qty=2,  price=3.72, source="j_manual",          reason="scale_out"),
            Fill(time_et="11:57:00", side="sell", qty=3,  price=3.89, source="engine_heartbeat", reason="runner_target_or_trail"),
        ],
        entry_price=1.67,
        avg_exit_price=3.06,
        qty_entered=10,
        qty_exited=10,
        qty_outstanding=0,
        pnl_dollars_realized=913.0,
        pnl_dollars_unrealized=0.0,
        pnl_pct_on_capital=54.7,
        hold_minutes=119,
        triggers_fired=["level_reclaim", "ribbon_flip"],
        setup_score="10/11",
        doctrine_compliance_score=100.0,
        rule_breaks=[],
        journaled_before_entry=True,
        engine_decisions=[],
    )


# ---------------- Structural tests ----------------

def test_analyze_detection_returns_category_score():
    """Drop-in compatibility: analyze_detection returns a CategoryScore."""
    data = _build_ingested_for_today()
    trades = [_build_actual_trade_today()]
    result = detection_mod.analyze_detection(data, trades)
    assert isinstance(result, CategoryScore), "must return CategoryScore (drop-in compat)"
    assert 0.0 <= result.score <= 100.0
    assert isinstance(result.evidence, dict)
    assert isinstance(result.narrative, str) and len(result.narrative) > 0


def test_phase3_evidence_contains_engine_decisions_list():
    """Phase 3: evidence['engine_decisions'] must be a list with at least 1 entry per RTH bar."""
    data = _build_ingested_for_today()
    trades = [_build_actual_trade_today()]
    result = detection_mod.analyze_detection(data, trades)
    decisions = result.evidence.get("engine_decisions")
    assert decisions is not None, "Phase 3 must surface engine_decisions in evidence"
    assert isinstance(decisions, list)
    assert len(decisions) >= 60, f"expect ~78 RTH bars, got {len(decisions)}"


def test_phase3_each_decision_has_required_fields():
    """Each EngineDecision-shaped dict must have: time_et, decision, reasoning."""
    data = _build_ingested_for_today()
    trades = [_build_actual_trade_today()]
    result = detection_mod.analyze_detection(data, trades)
    decisions = result.evidence.get("engine_decisions", [])
    assert len(decisions) > 0
    sample = decisions[0]
    for required_key in ("time_et", "decision", "reasoning"):
        assert required_key in sample, f"missing required key: {required_key}"


def test_phase3_evidence_has_verdict():
    """Verdict must be one of: PERFECT / OVER_AGGRESSIVE / TOO_PASSIVE / INTRADAY_INCONSISTENT / NO_DATA."""
    data = _build_ingested_for_today()
    trades = [_build_actual_trade_today()]
    result = detection_mod.analyze_detection(data, trades)
    verdict = result.evidence.get("verdict")
    valid = {"PERFECT", "OVER_AGGRESSIVE", "TOO_PASSIVE", "INTRADAY_INCONSISTENT", "NO_DATA"}
    assert verdict in valid, f"verdict {verdict!r} not in {valid}"


def test_phase3_evidence_phase_marker():
    """Evidence must explicitly mark phase as 3 (or '3.x')."""
    data = _build_ingested_for_today()
    trades = [_build_actual_trade_today()]
    result = detection_mod.analyze_detection(data, trades)
    phase = str(result.evidence.get("phase", ""))
    assert phase.startswith("3"), f"expected phase to start with '3', got {phase!r}"


# ---------------- Hand-computed bar tests ----------------

def test_bar_0930_skip_time_gate():
    """Bar 09:30 ET: filter 1 blocks (no_trade_before=10:00). Decision must be a SKIP."""
    data = _build_ingested_for_today()
    trades = [_build_actual_trade_today()]
    result = detection_mod.analyze_detection(data, trades)
    decisions = result.evidence.get("engine_decisions", [])
    bar_0930 = next((d for d in decisions if d["time_et"].startswith("09:30")), None)
    assert bar_0930 is not None, "must have a decision for the 09:30 RTH bar"
    decision = bar_0930["decision"]
    # Pre-10:00 entries are blocked by v15 entry gate. Any SKIP/HOLD is acceptable
    # (HOLD because no setup, SKIP_TIME_GATE because filter 1 blocked).
    assert decision.startswith(("SKIP", "HOLD")), (
        f"09:30 bar should not be ENTER (time gate). got: {decision}"
    )
    # If it's a SKIP, the reasoning should mention time / gate / 09:35 / 10:00 OR
    # filter 1 (the time-gate filter).
    if decision.startswith("SKIP"):
        reason = bar_0930["reasoning"].lower()
        gate_evidence = any(token in reason for token in (
            "time", "gate", "09:35", "10:00", "filter 1", "filter1", "no_trade_before",
            "early", "before", "f1"
        ))
        assert gate_evidence, f"SKIP at 09:30 should mention time-gate. got: {bar_0930['reasoning']!r}"


def test_bar_1430_skip_no_trade_window():
    """Bar 14:30 ET: in 14:00-15:00 no-trade-window. Decision must be a SKIP/HOLD."""
    data = _build_ingested_for_today()
    trades = [_build_actual_trade_today()]
    result = detection_mod.analyze_detection(data, trades)
    decisions = result.evidence.get("engine_decisions", [])
    bar_1430 = next((d for d in decisions if d["time_et"].startswith("14:30")), None)
    assert bar_1430 is not None, "must have a decision for the 14:30 RTH bar"
    decision = bar_1430["decision"]
    assert not decision.startswith("ENTER"), (
        f"14:30 in NTW should NEVER produce ENTER. got: {decision}"
    )


def test_bar_post_entry_position_state():
    """Bars after engine entry (09:58) but before exit (~11:57) should reflect
    in-position context. Engine should NOT show ENTER (engaged) — typically HOLD,
    SKIP_FIRST_ENTRY_LOCK, or HOLD_DEV depending on impl.
    """
    data = _build_ingested_for_today()
    trades = [_build_actual_trade_today()]
    result = detection_mod.analyze_detection(data, trades)
    decisions = result.evidence.get("engine_decisions", [])
    # Look at the 10:15 bar — solidly inside the open trade window
    bar_1015 = next((d for d in decisions if d["time_et"].startswith("10:15")), None)
    assert bar_1015 is not None, "must have a decision for 10:15 bar"
    # Bar is during open trade — engine should not also ENTER again (first_entry_lock).
    # Acceptable: HOLD, SKIP_*, EXIT_*, SCALE_OUT.
    decision = bar_1015["decision"]
    assert not decision.startswith("ENTER"), (
        f"10:15 (mid-trade) should not ENTER again. got: {decision}"
    )


# ---------------- Performance tests ----------------

def test_phase3_performance_under_30s():
    """78 RTH bars must complete in under 30s (per task constraint)."""
    data = _build_ingested_for_today()
    trades = [_build_actual_trade_today()]
    t0 = time.time()
    result = detection_mod.analyze_detection(data, trades)
    elapsed = time.time() - t0
    assert elapsed < 30.0, f"detection.analyze_detection took {elapsed:.2f}s (must be <30s)"
    assert result is not None


# ---------------- Empty/edge cases ----------------

def test_no_trades_still_runs():
    """Empty trades list — engine still replays bars + emits decisions; no error."""
    data = _build_ingested_for_today()
    result = detection_mod.analyze_detection(data, [])
    assert isinstance(result, CategoryScore)
    decisions = result.evidence.get("engine_decisions")
    # With no actual trades, ground-truth comparison degrades but the engine
    # replay should still run. Either non-empty list OR a NO_DATA evidence is OK.
    if decisions is not None:
        assert isinstance(decisions, list)


def test_missing_today_data_returns_no_data_verdict():
    """If today's CSV is missing, gracefully return verdict='NO_DATA'."""
    data = IngestedData(date="1999-01-01", ingested_at_et=dt.datetime.now().isoformat())
    trades: list = []
    result = detection_mod.analyze_detection(data, trades)
    assert isinstance(result, CategoryScore)
    # Either error-flavoured verdict OR an explicit NO_DATA marker
    verdict_or_error = (
        result.evidence.get("verdict") == "NO_DATA"
        or "error" in result.evidence
        or "no_today" in str(result.evidence).lower()
    )
    assert verdict_or_error, f"missing date should signal NO_DATA. got: {result.evidence}"
