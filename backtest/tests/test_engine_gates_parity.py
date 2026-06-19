"""Parity: engine.evaluate_gates == orchestrator inline gate cascade.

Spec: ``docs/SHARED-DECISION-LIBRARY-MIGRATION.md`` §3 "Phase 2 — Extract Gates
A-I into ``engine/gates.py`` + add the executable parity test".

This is the "assert-agree before replace" proof for the GATE layer (mirroring
``test_engine_score_parity.py`` for the scoring layer). Two complementary kinds of
proof:

1. UNIT PARITY (``test_gate_*``) — for each of the 15 gates in
   ``engine.gates.GATE_ORDER``, a hand-built :class:`GateContext` the gate SHOULD
   block and one it must NOT, asserting ``evaluate_gates`` returns the exact SKIP
   action (or ``None``). Data-free, deterministic; directly pins each gate's
   predicate + its SKIP code + the GATE_ORDER first-match precedence.

2. INTEGRATION PARITY (``test_oracle_agrees_on_anchor_day_*``) — re-runs the six
   ported-gate anchor-day BLOCK scenarios from ``test_gate_e2e_2026_06_18.py`` with
   the in-orchestrator assert-agree oracle ON (``GAMMA_ENGINE_GATES_ASSERT=1``).
   The oracle calls ``evaluate_gates`` on the SAME loop locals as the inline
   cascade and raises ``AssertionError`` on ANY per-bar disagreement, so a clean
   pass = the engine fired the SAME first SKIP (or allow) the inline blocks did,
   on every bar of those real days. This is the executable bridge that proves the
   extraction is faithful on production data, not just on hand fixtures.

Run:  cd backtest && python -m pytest tests/test_engine_gates_parity.py -q
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.engine import GATE_ORDER, GateBlock, GateContext, evaluate_gates  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402
from lib.ribbon import RibbonState  # noqa: E402

DATA = BACKTEST / "data"
MASTER_SPY = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
MASTER_VIX = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
_HAS_DATA = MASTER_SPY.exists() and MASTER_VIX.exists()
_needs_data = pytest.mark.skipif(not _HAS_DATA, reason="master SPY/VIX CSV not present")

# 50% risk cap keeps qty unscaled (mirrors test_gate_e2e_2026_06_18.py).
_RISK = {"per_trade_risk_cap_pct": 0.50}


# --------------------------------------------------------------------------- #
# GateContext builders (hand-built, deterministic — no data files needed)
# --------------------------------------------------------------------------- #


def _ctx(
    *,
    side: str = "P",
    triggers=("level_rejection",),
    tier: str = "LEVEL",
    has_level: bool = True,
    vix: float = 18.0,
    hhmm: tuple[int, int] = (11, 0),
    bar: pd.Series | None = None,
    bar_idx: int = 29,
    spread_cents: float = 40.0,
    stack: str = "BEAR",
    spy_df: pd.DataFrame | None = None,
    ribbon_df: pd.DataFrame | None = None,
) -> GateContext:
    """Build a GateContext for one bar. Defaults = a textbook LEVEL bear at 11:00."""
    if bar is None:
        # Decisive red breakdown bar (body_pct high) so the body gate does NOT
        # fire unless a test explicitly supplies a doji.
        bar = pd.Series(
            {"open": 100.45, "high": 100.55, "low": 100.05, "close": 100.10, "volume": 30000}
        )
    return GateContext(
        winning_side=side,
        winning_triggers=list(triggers),
        quality_tier=tier,
        has_level=has_level,
        bar=bar,
        bar_idx=bar_idx,
        bar_time=dt.datetime(2025, 10, 1, hhmm[0], hhmm[1]),
        vix_now=vix,
        ribbon_spread_cents=spread_cents,
        ribbon_stack=stack,
        spy_df=spy_df,
        ribbon_df=ribbon_df,
    )


def _doji_bar() -> pd.Series:
    """A doji: tiny body relative to range (body_pct well under 0.20)."""
    return pd.Series(
        {"open": 100.30, "high": 100.70, "low": 100.05, "close": 100.32, "volume": 30000}
    )


# =========================================================================== #
# 0. GATE_ORDER structural invariants
# =========================================================================== #


def test_gate_order_has_15_unique_gates() -> None:
    """GATE_ORDER declares exactly the 15 lifted gates, each id/action unique."""
    assert len(GATE_ORDER) == 15
    ids = [g[0] for g in GATE_ORDER]
    actions = [g[2] for g in GATE_ORDER]
    assert len(set(ids)) == 15, "duplicate gate_id in GATE_ORDER"
    assert len(set(actions)) == 15, "duplicate SKIP action in GATE_ORDER"


def test_gate_order_matches_documented_sequence() -> None:
    """The sequence is the canonical spec — pin it so a reorder is a loud diff."""
    assert [g[0] for g in GATE_ORDER] == [
        "block_level_rejection",
        "trendline_requires_ribbon_flip",
        "block_elite_bull",
        "block_bull_ribbon_flip",
        "block_bull_1100_1200",
        "block_bull_morning_agg",
        "require_bearish_fill_bar",
        "min_ribbon_momentum_cents",
        "max_ribbon_duration_bars",
        "midday_trendline_gate",
        "block_conf_lvl_rej_midday_afternoon",
        "block_conf_lvl_rec_afternoon",
        "entry_bar_body_pct_min",
        "entry_bar_body_pct_min_bull",
        "vix_bear_hard_cap",
    ]


def test_no_gate_fires_when_all_knobs_off() -> None:
    """Empty params (all gates disarmed) -> always allow (None)."""
    assert evaluate_gates(_ctx(side="P"), {}) is None
    assert evaluate_gates(_ctx(side="C", triggers=("level_reclaim",), tier="LEVEL"), {}) is None


# =========================================================================== #
# 1. UNIT PARITY — each gate: block scenario + allow scenario
# =========================================================================== #


def test_gate_block_level_rejection() -> None:
    p = {"block_level_rejection": True}
    blk = evaluate_gates(_ctx(side="P", triggers=("level_rejection",), tier="LEVEL"), p)
    assert isinstance(blk, GateBlock) and blk.action == "SKIP_LEVEL_REJECTION_GATE"
    assert blk.blockers == ["LEVEL_REJECTION_GATE"]
    # allow: bull level_reclaim LEVEL is NOT blocked (winning_side guard)
    assert evaluate_gates(
        _ctx(side="C", triggers=("level_reclaim",), tier="LEVEL", has_level=True), p
    ) is None
    # allow: gate off
    assert evaluate_gates(_ctx(side="P", tier="LEVEL"), {"block_level_rejection": False}) is None


def test_gate_trendline_requires_ribbon_flip() -> None:
    p = {"trendline_requires_ribbon_flip": True}
    blk = evaluate_gates(
        _ctx(side="P", triggers=("trendline_rejection",), tier="TRENDLINE", has_level=False), p
    )
    assert blk and blk.action == "SKIP_TRENDLINE_NO_RIBBON_FLIP"
    # allow: ribbon_flip present
    assert evaluate_gates(
        _ctx(side="P", triggers=("trendline_rejection", "ribbon_flip"), tier="TRENDLINE",
             has_level=False), p
    ) is None


def test_gate_block_elite_bull() -> None:
    p = {"block_elite_bull": True, "block_elite_bull_vix_low": 0.0, "block_elite_bull_vix_high": 25.0}
    blk = evaluate_gates(
        _ctx(side="C", triggers=("level_reclaim", "confluence"), tier="ELITE", vix=17.0), p
    )
    assert blk and blk.action == "SKIP_ELITE_BULL_LEVEL_RECLAIM"
    # allow: VIX outside band
    assert evaluate_gates(
        _ctx(side="C", triggers=("level_reclaim", "confluence"), tier="ELITE", vix=26.0), p
    ) is None


def test_gate_block_bull_ribbon_flip() -> None:
    p = {"block_bull_ribbon_flip": True}
    blk = evaluate_gates(
        _ctx(side="C", triggers=("level_reclaim", "ribbon_flip"), tier="ELITE"), p
    )
    assert blk and blk.action == "SKIP_BULL_RIBBON_FLIP"
    # allow: no ribbon_flip
    assert evaluate_gates(
        _ctx(side="C", triggers=("level_reclaim",), tier="LEVEL"), p
    ) is None


def test_gate_block_bull_1100_1200() -> None:
    p = {"block_bull_1100_1200": True}
    blk = evaluate_gates(_ctx(side="C", triggers=("level_reclaim",), hhmm=(11, 15)), p)
    assert blk and blk.action == "SKIP_BULL_1100_1200"
    # allow: outside the window (10:30)
    assert evaluate_gates(_ctx(side="C", triggers=("level_reclaim",), hhmm=(10, 30)), p) is None
    # allow: bear side at 11:15 not affected
    assert evaluate_gates(_ctx(side="P", hhmm=(11, 15)), p) is None


def test_gate_block_bull_morning_agg() -> None:
    p = {"block_bull_morning_agg": True}
    # morning window 10:00-11:30
    assert evaluate_gates(_ctx(side="C", triggers=("level_reclaim",), hhmm=(11, 15)), p).action == (
        "SKIP_BULL_MORNING_AGG"
    )
    # afternoon >=14:00
    assert evaluate_gates(_ctx(side="C", triggers=("level_reclaim",), hhmm=(14, 30)), p).action == (
        "SKIP_BULL_MORNING_AGG"
    )
    # allow: midday gap (12:30) is NOT in either window
    assert evaluate_gates(_ctx(side="C", triggers=("level_reclaim",), hhmm=(12, 30)), p) is None


def test_gate_require_bearish_fill_bar() -> None:
    p = {"require_bearish_fill_bar": True}
    # Build a 2-bar spy_df: trigger at idx 0, BULLISH fill bar at idx 1 -> block.
    spy_bull_fill = pd.DataFrame([
        {"open": 100.4, "high": 100.6, "low": 100.0, "close": 100.1, "volume": 1},
        {"open": 100.1, "high": 100.9, "low": 100.0, "close": 100.8, "volume": 1},  # green fill
    ])
    blk = evaluate_gates(_ctx(side="P", bar_idx=0, spy_df=spy_bull_fill), p)
    assert blk and blk.action == "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"
    # allow: bearish (red) fill bar
    spy_bear_fill = pd.DataFrame([
        {"open": 100.4, "high": 100.6, "low": 100.0, "close": 100.1, "volume": 1},
        {"open": 100.8, "high": 100.9, "low": 100.0, "close": 100.1, "volume": 1},  # red fill
    ])
    assert evaluate_gates(_ctx(side="P", bar_idx=0, spy_df=spy_bear_fill), p) is None


def _ribbon_df_widening(spread_now: float, spread_3ago: float, n: int = 40) -> pd.DataFrame:
    """Ribbon frame where spread at idx-3 is spread_3ago and current is spread_now."""
    rows = [{"fast": 100.0, "pivot": 100.3, "slow": 100.6, "spread_cents": spread_3ago,
             "stack": "BEAR"} for _ in range(n)]
    df = pd.DataFrame(rows)
    return df


def test_gate_min_ribbon_momentum_cents() -> None:
    p = {"min_ribbon_momentum_cents": 10.0}
    # spread at idx-3 == 40; current ctx spread 41 -> momentum 1 < 10 -> block.
    rdf = _ribbon_df_widening(spread_now=41.0, spread_3ago=40.0)
    blk = evaluate_gates(_ctx(side="P", bar_idx=29, spread_cents=41.0, ribbon_df=rdf), p)
    assert blk and blk.action == "SKIP_RIBBON_MOMENTUM_GATE"
    # allow: current spread 55 vs 40 three ago -> momentum 15 >= 10
    assert evaluate_gates(_ctx(side="P", bar_idx=29, spread_cents=55.0, ribbon_df=rdf), p) is None


def test_gate_max_ribbon_duration_bars() -> None:
    p = {"max_ribbon_duration_bars": 5}
    # All-BEAR ribbon for 40 bars -> stack age > 5 -> block.
    rdf = pd.DataFrame([{"fast": 100.0, "pivot": 100.3, "slow": 100.6, "spread_cents": 40.0,
                         "stack": "BEAR"} for _ in range(40)])
    blk = evaluate_gates(_ctx(side="P", bar_idx=29, stack="BEAR", ribbon_df=rdf), p)
    assert blk and blk.action == "SKIP_RIBBON_DURATION_GATE"
    # allow: stack just flipped (idx-1 is BULL) -> age 1 <= 5
    rdf2 = rdf.copy()
    rdf2.loc[0:28, "stack"] = "BULL"  # everything before idx 29 is BULL
    assert evaluate_gates(_ctx(side="P", bar_idx=29, stack="BEAR", ribbon_df=rdf2), p) is None


def test_gate_midday_trendline_gate() -> None:
    p = {"midday_trendline_gate": True, "midday_trendline_gate_start_minutes": 690}  # 11:30
    blk = evaluate_gates(
        _ctx(side="P", triggers=("trendline_rejection",), tier="TRENDLINE",
             has_level=False, hhmm=(12, 0)), p
    )
    assert blk and blk.action == "SKIP_MIDDAY_TRENDLINE_GATE"
    # allow: before the window (11:00 < 11:30)
    assert evaluate_gates(
        _ctx(side="P", triggers=("trendline_rejection",), tier="TRENDLINE",
             has_level=False, hhmm=(11, 0)), p
    ) is None
    # allow: 2 triggers (not trendline-only)
    assert evaluate_gates(
        _ctx(side="P", triggers=("trendline_rejection", "level_rejection"), tier="ELITE",
             hhmm=(12, 0)), p
    ) is None


def test_gate_block_conf_lvl_rej_midday_afternoon() -> None:
    p = {"block_conf_lvl_rej_midday_afternoon": True}
    blk = evaluate_gates(
        _ctx(side="P", triggers=("confluence", "level_rejection"), tier="ELITE", hhmm=(12, 0)), p
    )
    assert blk and blk.action == "SKIP_CONF_LVL_REJ_MIDDAY_AFTERNOON"
    # allow: before 11:30
    assert evaluate_gates(
        _ctx(side="P", triggers=("confluence", "level_rejection"), tier="ELITE", hhmm=(11, 0)), p
    ) is None


def test_gate_block_conf_lvl_rec_afternoon() -> None:
    p = {"block_conf_lvl_rec_afternoon": True}
    blk = evaluate_gates(
        _ctx(side="C", triggers=("confluence", "level_reclaim"), tier="ELITE", hhmm=(14, 30)), p
    )
    assert blk and blk.action == "SKIP_CONF_LVL_REC_AFTERNOON"
    # allow: before 14:00
    assert evaluate_gates(
        _ctx(side="C", triggers=("confluence", "level_reclaim"), tier="ELITE", hhmm=(13, 0)), p
    ) is None


def test_gate_entry_bar_body_pct_min_bear() -> None:
    p = {"entry_bar_body_pct_min": 0.20}
    blk = evaluate_gates(_ctx(side="P", bar=_doji_bar()), p)
    assert blk and blk.action == "SKIP_DOJI_ENTRY_BAR"
    # allow: decisive body bar (default _ctx bar has body_pct >= 0.20)
    assert evaluate_gates(_ctx(side="P"), p) is None
    # allow: bull side not affected by the bear body gate
    assert evaluate_gates(_ctx(side="C", triggers=("level_reclaim",), bar=_doji_bar()), p) is None


def test_gate_entry_bar_body_pct_min_bull() -> None:
    p = {"entry_bar_body_pct_min_bull": 0.20}
    blk = evaluate_gates(
        _ctx(side="C", triggers=("level_reclaim",), bar=_doji_bar()), p
    )
    assert blk and blk.action == "SKIP_DOJI_ENTRY_BAR_BULL"
    # allow: bear side not affected by the bull body gate
    assert evaluate_gates(_ctx(side="P", bar=_doji_bar()), p) is None


def test_gate_vix_bear_hard_cap() -> None:
    p = {"vix_bear_hard_cap": 23.0}
    blk = evaluate_gates(_ctx(side="P", vix=26.0), p)
    assert blk and blk.action == "SKIP_VIX_BEAR_HIGH"
    # allow: VIX below cap
    assert evaluate_gates(_ctx(side="P", vix=18.0), p) is None
    # allow: bull side not affected
    assert evaluate_gates(_ctx(side="C", triggers=("level_reclaim",), vix=26.0), p) is None


# =========================================================================== #
# 2. FIRST-MATCH PRECEDENCE — when two gates would fire, GATE_ORDER wins
# =========================================================================== #


def test_first_match_precedence_level_rejection_before_vix() -> None:
    """A LEVEL bear level_rejection at VIX>=cap arms BOTH gate 1 (level_rejection)
    and gate 15 (vix_bear_hard_cap). GATE_ORDER -> gate 1 fires first."""
    p = {"block_level_rejection": True, "vix_bear_hard_cap": 23.0}
    blk = evaluate_gates(_ctx(side="P", triggers=("level_rejection",), tier="LEVEL", vix=26.0), p)
    assert blk and blk.action == "SKIP_LEVEL_REJECTION_GATE", (
        "GATE_ORDER precedence broken: level_rejection (gate 1) must beat "
        "vix_bear_hard_cap (gate 15)"
    )


# =========================================================================== #
# 3. INTEGRATION PARITY — the in-orchestrator assert-agree oracle on real days
# =========================================================================== #
#
# Each anchor day + gate below is the BLOCK scenario from
# test_gate_e2e_2026_06_18.py. We run the real backtest with the engine-gates
# oracle ON (default). The oracle calls evaluate_gates on the SAME loop locals as
# the inline cascade every bar and raises AssertionError on ANY disagreement, so a
# clean run that ALSO produces the expected SKIP action proves byte-faithful gate
# parity on production data. We force the oracle on explicitly (defensive against a
# hostile env) and assert the expected SKIP appears.

_ANCHORS = [
    (dt.date(2025, 10, 30), {"block_level_rejection": True}, "SKIP_LEVEL_REJECTION_GATE"),
    (dt.date(2025, 11, 21), {"vix_bear_hard_cap": 23.0}, "SKIP_VIX_BEAR_HIGH"),
    (dt.date(2025, 6, 6), {"entry_bar_body_pct_min": 0.20}, "SKIP_DOJI_ENTRY_BAR"),
    (dt.date(2025, 6, 5), {"block_bull_1100_1200": True}, "SKIP_BULL_1100_1200"),
    (dt.date(2025, 6, 5), {"block_bull_morning_agg": True}, "SKIP_BULL_MORNING_AGG"),
    (
        dt.date(2025, 6, 9),
        {"block_elite_bull": True, "block_elite_bull_vix_low": 0.0, "block_elite_bull_vix_high": 25.0},
        "SKIP_ELITE_BULL_LEVEL_RECLAIM",
    ),
]


@_needs_data
@pytest.mark.parametrize("day,overrides,expected_action", _ANCHORS)
def test_oracle_agrees_on_anchor_day(day, overrides, expected_action) -> None:
    """Run the anchor-day block scenario with the assert-agree oracle ON; the run
    must not raise (engine agreed on every bar) AND the expected SKIP must appear."""
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    prev = os.environ.get("GAMMA_ENGINE_GATES_ASSERT")
    os.environ["GAMMA_ENGINE_GATES_ASSERT"] = "1"  # force oracle ON
    try:
        result = run_backtest(
            spy, vix, start_date=day, end_date=day, use_real_fills=False,
            params_overrides={**_RISK, **overrides},
        )
    finally:
        if prev is None:
            os.environ.pop("GAMMA_ENGINE_GATES_ASSERT", None)
        else:
            os.environ["GAMMA_ENGINE_GATES_ASSERT"] = prev
    actions = [d.get("action") for d in result.decisions if d.get("action")]
    assert expected_action in actions, (
        f"{day}: expected {expected_action} not produced — anchor scenario invalid "
        f"or gate inert (got actions: {sorted(set(actions))})"
    )
