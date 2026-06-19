"""END-TO-END entry-gate validation (2026-06-18).

Goal: PROVE each entry gate produces the correct ENTER/SKIP decision, with
special focus on the 6 gates ported into the live heartbeats. The live
heartbeats are LLM prompts (not unit-testable); their gate logic MIRRORS
backtest/lib/orchestrator.py + filters.py, so we validate via that engine.

Structure
---------
1. SIX NEWLY-PORTED GATES — for each gate, a block-scenario (gate SHOULD fire)
   and an allow-scenario (gate must NOT fire); the decision must flip.
       - vix_bear_hard_cap      (=23.0)  : bear PUT, VIX>=23 -> SKIP_VIX_BEAR_HIGH
       - block_level_rejection  (=true)  : LEVEL bear level_rejection -> SKIP_LEVEL_REJECTION_GATE
       - entry_bar_body_pct_min (=0.20)  : bear doji entry bar -> SKIP_DOJI_ENTRY_BAR
       - block_bull_1100_1200   (=true)  : bull 11:00-12:00 ET -> SKIP_BULL_1100_1200
       - block_elite_bull       (vix band): ELITE bull level_reclaim -> SKIP_ELITE_BULL_LEVEL_RECLAIM
       - block_bull_morning_agg (agg)    : bull 10:00-11:30 / >=14:00 -> SKIP_BULL_MORNING_AGG
2. CASCADE F1-F11 — hand-built BarContext: a clean textbook bear ENTERs, and
   breaking any required filter flips it to SKIP (deterministic, data-free).
3. PARAMS<->FILTERS PARITY — the 17.30 VIX threshold is the live boundary, and
   the params.json gate values match the constants/kwargs the engine consumes.
4. REPRODUCIBILITY — identical scenario twice -> identical output; repro run_id stable.
5. CRITICAL REGRESSION GUARDS — two gates (vix_bear_hard_cap, entry_bar_body_pct_min)
   were DEAD via the params_overrides plumbing path (silently dropped). FIXED
   2026-06-18: both are now translated AND assigned from params_overrides. These
   tests assert the FIXED state (gate fires via params_overrides) so the bug
   cannot silently regress, and confirm the DIRECT-kwarg path still works too.

Run:  cd backtest && python -m pytest tests/test_gate_e2e_2026_06_18.py -v
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.orchestrator import run_backtest  # noqa: E402
from lib.ribbon import RibbonState  # noqa: E402
from lib.filters import (  # noqa: E402
    BarContext,
    evaluate_bearish_setup,
    VIX_BEAR_THRESHOLD,
    RIBBON_SPREAD_MIN_CENTS,
)

DATA = BACKTEST / "data"
MASTER_SPY = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
MASTER_VIX = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
PARAMS = REPO / "automation" / "state" / "params.json"
AGG_PARAMS = REPO / "automation" / "state" / "aggressive" / "params.json"
_HAS_DATA = MASTER_SPY.exists() and MASTER_VIX.exists()
_needs_data = pytest.mark.skipif(not _HAS_DATA, reason="master SPY/VIX CSV not present")

# 50% risk cap keeps qty unscaled so a single textbook trade fires cleanly.
_RISK = {"per_trade_risk_cap_pct": 0.50}


# --------------------------------------------------------------------------- #
# data helpers (mirror test_graduated_guards.py conventions)
# --------------------------------------------------------------------------- #

_SPY_CACHE: list = []
_VIX_CACHE: list = []


def _spy() -> pd.DataFrame:
    if not _SPY_CACHE:
        _SPY_CACHE.append(pd.read_csv(MASTER_SPY))
    return _SPY_CACHE[0]


def _vix() -> pd.DataFrame:
    if not _VIX_CACHE:
        _VIX_CACHE.append(pd.read_csv(MASTER_VIX))
    return _VIX_CACHE[0]


def _run_day(day: dt.date, **kw):
    return run_backtest(
        _spy(), _vix(), start_date=day, end_date=day, use_real_fills=False, **kw
    )


def _actions(result) -> list:
    return [d.get("action") for d in result.decisions if d.get("action")]


def _sig(trades) -> list:
    return sorted((str(t.entry_time_et), t.side, round(t.dollar_pnl, 2)) for t in trades)


# =========================================================================== #
# 1. SIX NEWLY-PORTED GATES — block vs allow, decision must flip
# =========================================================================== #
#
# Anchor days were located by scanning the master dataset (2025-06..2026-05)
# for a natural entry that exercises each gate's exact target action.
# Each gate is exercised via the plumbing path that actually delivers the value
# to the engine: direct-kwarg for the two gates whose params_overrides path is
# broken (see section 5), params_overrides for the four that work that way.


@_needs_data
def test_gate_vix_bear_hard_cap_blocks_and_allows() -> None:
    """vix_bear_hard_cap=23.0: a bear PUT entering at VIX>=23 must be blocked.

    Anchor: 2025-11-21 11:00 ET bear level_rejection, entry VIX=26.58 (>=23).
    Delivered via DIRECT kwarg here; the params_overrides path is verified
    separately in test_CRITICAL_vix_bear_hard_cap_works_via_params_overrides."""
    day = dt.date(2025, 11, 21)

    allow = _run_day(day, vix_bear_hard_cap=None, **_RISK)
    block = _run_day(day, vix_bear_hard_cap=23.0, **_RISK)

    allow_bears = [t for t in allow.trades if t.side == "P"]
    assert allow_bears, "anchor day did not produce the expected bear entry (allow scenario)"
    assert any((t.entry_vix or 0) >= 23.0 for t in allow_bears), (
        "anchor bear did not enter at VIX>=23; gate scenario invalid"
    )
    # BLOCK: gate fires -> that bear no longer fills, SKIP action present.
    assert "SKIP_VIX_BEAR_HIGH" in _actions(block), (
        "vix_bear_hard_cap=23 did NOT block the VIX>=23 bear (gate inert)"
    )
    assert len([t for t in block.trades if t.side == "P"]) < len(allow_bears), (
        "vix_bear_hard_cap=23 did not reduce bear fills"
    )


@_needs_data
def test_gate_block_level_rejection_blocks_and_allows() -> None:
    """block_level_rejection=true: a LEVEL-tier bear level_rejection must be blocked.

    Anchor: 2025-10-30 15:00 ET, single trigger=['level_rejection'] (LEVEL tier).
    Works via params_overrides (path is wired)."""
    day = dt.date(2025, 10, 30)

    allow = _run_day(day, params_overrides={**_RISK, "block_level_rejection": False})
    block = _run_day(day, params_overrides={**_RISK, "block_level_rejection": True})

    allow_bears = [t for t in allow.trades if t.side == "P"]
    assert allow_bears, "anchor day did not produce a bear level_rejection entry"
    assert "SKIP_LEVEL_REJECTION_GATE" in _actions(block), (
        "block_level_rejection=true did NOT block the LEVEL bear (gate inert)"
    )
    assert _sig(block.trades) != _sig(allow.trades), "gate did not change the day's trades"


@_needs_data
def test_gate_entry_bar_body_pct_min_blocks_and_allows() -> None:
    """entry_bar_body_pct_min=0.20: a bear whose entry bar is a doji (body<0.20)
    must be blocked.

    Anchor: 2025-06-06 12:00 ET bear, entry-bar body_pct=0.043 (deep doji).
    Delivered via DIRECT kwarg here; the params_overrides path is verified
    separately in test_CRITICAL_entry_bar_body_pct_min_works_via_params_overrides."""
    day = dt.date(2025, 6, 6)

    allow = _run_day(day, entry_bar_body_pct_min=0.0, **_RISK)
    block = _run_day(day, entry_bar_body_pct_min=0.20, **_RISK)

    allow_bears = [t for t in allow.trades if t.side == "P"]
    assert allow_bears, "anchor day did not produce the doji bear entry (allow scenario)"
    assert "SKIP_DOJI_ENTRY_BAR" in _actions(block), (
        "entry_bar_body_pct_min=0.20 did NOT block the doji bear (gate inert)"
    )
    assert len([t for t in block.trades if t.side == "P"]) < len(allow_bears), (
        "entry_bar_body_pct_min did not reduce bear fills"
    )


@_needs_data
def test_gate_block_bull_1100_1200_blocks_and_allows() -> None:
    """block_bull_1100_1200=true: a BULL entry in 11:00-12:00 ET must be blocked.

    Anchor: 2025-06-05 11:15 ET bull (level_reclaim+ribbon_flip+confluence)."""
    day = dt.date(2025, 6, 5)

    allow = _run_day(day, params_overrides={**_RISK, "block_bull_1100_1200": False})
    block = _run_day(day, params_overrides={**_RISK, "block_bull_1100_1200": True})

    allow_bulls = [t for t in allow.trades if t.side == "C"]
    assert allow_bulls, "anchor day did not produce an 11:00-12:00 bull entry"
    assert any(dt.time(11, 0) <= pd.Timestamp(t.entry_time_et).time() < dt.time(12, 0)
               for t in allow_bulls), "no bull entry in the 11:00-12:00 window"
    assert "SKIP_BULL_1100_1200" in _actions(block), (
        "block_bull_1100_1200=true did NOT block the 11:15 bull (gate inert)"
    )


@_needs_data
def test_gate_block_elite_bull_blocks_and_allows() -> None:
    """block_elite_bull (VIX band): an ELITE bull (level_reclaim+confluence) inside
    the VIX band must be blocked; outside the band it must NOT be blocked.

    Anchor: 2025-06-09 12:50 ET bull level_reclaim+confluence at VIX~17.0 (in [0,25))."""
    day = dt.date(2025, 6, 9)
    base_po = {**_RISK, "block_elite_bull": True, "block_elite_bull_vix_low": 0.0}

    allow = _run_day(day, params_overrides={**_RISK, "block_elite_bull": False})
    block = _run_day(day, params_overrides={**base_po, "block_elite_bull_vix_high": 25.0})
    # Allow-via-band: same gate ON but VIX band moved ABOVE the entry VIX -> inert.
    band_off = _run_day(day, params_overrides={**base_po,
                                               "block_elite_bull_vix_low": 30.0,
                                               "block_elite_bull_vix_high": 40.0})

    allow_bulls = [t for t in allow.trades if t.side == "C"]
    assert allow_bulls, "anchor day did not produce an ELITE bull entry"
    assert "SKIP_ELITE_BULL_LEVEL_RECLAIM" in _actions(block), (
        "block_elite_bull in-band did NOT block the ELITE bull (gate inert)"
    )
    # All blocked decisions must carry a VIX inside the configured band.
    blocked = [d for d in block.decisions if d.get("action") == "SKIP_ELITE_BULL_LEVEL_RECLAIM"]
    assert all(0.0 <= d["vix"] < 25.0 for d in blocked), (
        "block_elite_bull fired on a VIX outside the [0,25) band — band logic broken"
    )
    assert "SKIP_ELITE_BULL_LEVEL_RECLAIM" not in _actions(band_off), (
        "block_elite_bull fired even though the VIX band was moved above the entry VIX "
        "(band lower-bound not respected)"
    )


@_needs_data
def test_gate_block_bull_morning_agg_blocks_and_allows() -> None:
    """block_bull_morning_agg (aggressive): a BULL in 10:00-11:30 or >=14:00 ET
    must be blocked.

    Anchor: 2025-06-05 11:15 ET bull (in the 10:00-11:30 morning window)."""
    day = dt.date(2025, 6, 5)

    allow = _run_day(day, params_overrides={**_RISK, "block_bull_morning_agg": False})
    block = _run_day(day, params_overrides={**_RISK, "block_bull_morning_agg": True})

    allow_bulls = [t for t in allow.trades if t.side == "C"]
    assert allow_bulls, "anchor day did not produce a morning bull entry"
    assert "SKIP_BULL_MORNING_AGG" in _actions(block), (
        "block_bull_morning_agg=true did NOT block the 11:15 morning bull (gate inert)"
    )
    # Every block must be inside the configured time windows.
    blocked = [d for d in block.decisions if d.get("action") == "SKIP_BULL_MORNING_AGG"]
    for d in blocked:
        t = pd.Timestamp(d["timestamp_et"]).time()
        assert (dt.time(10, 0) <= t < dt.time(11, 30)) or t >= dt.time(14, 0), (
            f"block_bull_morning_agg fired outside its windows at {t}"
        )


# =========================================================================== #
# 2. CASCADE F1-F11 — hand-built BarContext (deterministic, data-free)
# =========================================================================== #


def _bear_ribbon(spread: float = 40.0) -> RibbonState:
    # Fast < Pivot < Slow  => BEAR stack
    return RibbonState(fast=100.0, pivot=100.3, slow=100.6, spread_cents=spread, stack="BEAR")


def _bull_ribbon(spread: float = 40.0) -> RibbonState:
    return RibbonState(fast=100.6, pivot=100.3, slow=100.0, spread_cents=spread, stack="BULL")


_LEVEL = 100.50


def _clean_bear_ctx(**override) -> BarContext:
    """A textbook BEAR_REJECTION bar: stacked BEAR ribbon (spread 40c), VIX>17.30
    rising, red high-volume breakdown bar that rejects an overhead level which is
    also a multi-day level (confluence). All of F1-F11 pass."""
    prior_rows = [
        {"open": 100.0, "high": 100.2, "low": 99.8, "close": 100.0, "volume": 10000}
        for _ in range(30)
    ]
    # trigger bar (idx 29): red, high>level, close<level, decisive body, vol 3x baseline
    trigger = pd.Series(
        {"open": 100.45, "high": 100.70, "low": 100.05, "close": 100.10, "volume": 30000}
    )
    prior = pd.DataFrame(prior_rows)
    prior.iloc[-1] = trigger
    base = dict(
        bar_idx=29,
        timestamp_et=dt.datetime(2025, 10, 1, 11, 0),
        bar=trigger,
        prior_bars=prior,
        ribbon_now=_bear_ribbon(40),
        ribbon_history=[_bear_ribbon(40)] * 5,
        vix_now=18.0,
        vix_prior=17.6,  # rising, > deadband, value > 17.30
        vol_baseline_20=10000.0,
        range_baseline_20=0.4,
        levels_active=[_LEVEL],
        multi_day_levels=[_LEVEL],
        htf_15m_stack="BEAR",
        level_states={},
    )
    base.update(override)
    return BarContext(**base)


def _eval(ctx: BarContext):
    return evaluate_bearish_setup(ctx, min_triggers=1, no_trade_before=dt.time(9, 35))


def test_cascade_clean_textbook_bear_enters() -> None:
    """F1-F11 all green on a clean textbook bear -> passed=True, score=10."""
    res = _eval(_clean_bear_ctx())
    assert res.passed is True, f"clean bear should ENTER, blockers={res.blockers}"
    assert res.bear_score == 10, f"clean bear should score 10, got {res.bear_score}"
    assert "level_rejection" in res.triggers_fired


def test_cascade_skip_filter5_ribbon_not_bear() -> None:
    """F5: ribbon not BEAR-stacked -> blocker 5, SKIP."""
    res = _eval(_clean_bear_ctx(ribbon_now=_bull_ribbon(40), ribbon_history=[_bull_ribbon(40)] * 5))
    assert res.passed is False
    assert 5 in res.blockers


def test_cascade_skip_filter6_spread_too_tight() -> None:
    """F6: ribbon spread < 30c -> blocker 6, SKIP."""
    res = _eval(_clean_bear_ctx(ribbon_now=_bear_ribbon(15), ribbon_history=[_bear_ribbon(15)] * 5))
    assert res.passed is False
    assert 6 in res.blockers


def test_cascade_skip_filter8_vix_falling() -> None:
    """F8: VIX falling (not rising) -> blocker 8, SKIP."""
    res = _eval(_clean_bear_ctx(vix_now=18.0, vix_prior=18.6))
    assert res.passed is False
    assert 8 in res.blockers


def test_cascade_skip_filter9_volume_not_elevated() -> None:
    """F9: red bar but volume below threshold -> blocker 9, SKIP.

    Raise the 20-bar baseline so the trigger bar's 30k volume falls under
    f9_vol_mult (0.7) * baseline. trendline_only relaxation can't fire here
    (level_rejection is present), so F9 stays a hard blocker."""
    res = _eval(_clean_bear_ctx(vol_baseline_20=100000.0))
    assert res.passed is False
    assert 9 in res.blockers


def test_cascade_skip_filter10_no_level_tied_trigger() -> None:
    """F10: no level-tied trigger (price nowhere near any level) -> blocker 10, SKIP."""
    # Move the level far away so neither level_rejection nor confluence fires.
    res = _eval(_clean_bear_ctx(levels_active=[200.0], multi_day_levels=[200.0]))
    assert res.passed is False
    assert 10 in res.blockers


def test_cascade_skip_filter1_before_0935() -> None:
    """F1: bar before 09:35 ET -> blocker 1, SKIP."""
    res = _eval(_clean_bear_ctx(timestamp_et=dt.datetime(2025, 10, 1, 9, 30)))
    assert res.passed is False
    assert 1 in res.blockers


# =========================================================================== #
# 3. PARAMS <-> FILTERS PARITY
# =========================================================================== #


def test_parity_vix_threshold_constant_matches_params() -> None:
    """The engine's VIX_BEAR_THRESHOLD constant must equal params.json's
    vix_entry_thresholds.bear_min_exclusive_and_rising (17.30)."""
    params = json.loads(PARAMS.read_text(encoding="utf-8-sig"))
    live = params["vix_entry_thresholds"]["bear_min_exclusive_and_rising"]
    assert VIX_BEAR_THRESHOLD == live, (
        f"PARITY BREAK: filters.VIX_BEAR_THRESHOLD={VIX_BEAR_THRESHOLD} != "
        f"params.json bear_min_exclusive_and_rising={live}"
    )


def test_parity_vix_threshold_is_the_live_boundary() -> None:
    """RUN a scenario proving 17.30 is the live boundary: VIX==17.30 BLOCKS
    (filter requires strictly > 17.30); VIX==17.31 PASSES. Everything else equal."""
    at_boundary = _eval(_clean_bear_ctx(vix_now=17.30, vix_prior=16.9))
    just_above = _eval(_clean_bear_ctx(vix_now=17.31, vix_prior=16.9))
    assert at_boundary.passed is False and 8 in at_boundary.blockers, (
        "VIX==17.30 should be blocked by filter 8 (threshold is exclusive '>')"
    )
    assert just_above.passed is True, (
        "VIX==17.31 should pass filter 8 — 17.30 is not the live boundary as configured"
    )


def test_parity_spread_constant_matches_params() -> None:
    """RIBBON_SPREAD_MIN_CENTS must equal params.json ribbon_min_spread_cents (30)."""
    params = json.loads(PARAMS.read_text(encoding="utf-8-sig"))
    live = params["ribbon_min_spread_cents"]
    assert RIBBON_SPREAD_MIN_CENTS == live, (
        f"PARITY BREAK: filters.RIBBON_SPREAD_MIN_CENTS={RIBBON_SPREAD_MIN_CENTS} != "
        f"params.json ribbon_min_spread_cents={live}"
    )


def test_parity_gate_values_present_in_params() -> None:
    """The 6 ported gates must carry their ratified values in the SAFE/AGG params."""
    p = json.loads(PARAMS.read_text(encoding="utf-8-sig"))
    a = json.loads(AGG_PARAMS.read_text(encoding="utf-8-sig"))
    assert p["vix_bear_hard_cap"] == 23.0
    assert p["block_level_rejection"] is True
    assert p["entry_bar_body_pct_min"] == 0.20
    assert p["block_bull_1100_1200"] is True
    assert p["block_elite_bull"] is True
    assert a["block_bull_morning_agg"] is True


# =========================================================================== #
# 4. REPRODUCIBILITY
# =========================================================================== #


@_needs_data
def test_repro_same_scenario_twice_identical() -> None:
    """The same backtest scenario run twice produces byte-identical trade
    signatures and identical decision actions (no hidden nondeterminism)."""
    day = dt.date(2025, 11, 21)
    kw = dict(vix_bear_hard_cap=23.0, **_RISK)
    r1 = _run_day(day, **kw)
    r2 = _run_day(day, **kw)
    assert _sig(r1.trades) == _sig(r2.trades), "trade signatures differ across identical runs"
    assert _actions(r1) == _actions(r2), "decision actions differ across identical runs"


def test_repro_run_id_stable() -> None:
    """repro.compute_run_id is deterministic for fixed inputs (same code+data+params
    hash -> same run_id within a day)."""
    from lib.repro import compute_run_id

    if not _HAS_DATA or not PARAMS.exists():
        pytest.skip("inputs for repro not present")
    a = compute_run_id(MASTER_SPY, MASTER_VIX, PARAMS)
    b = compute_run_id(MASTER_SPY, MASTER_VIX, PARAMS)
    assert a.run_id == b.run_id, "run_id not stable across identical inputs"
    assert a.data_hash == b.data_hash and a.params_hash == b.params_hash


# =========================================================================== #
# 5. CRITICAL REGRESSION GUARDS — params_overrides plumbing FIXED for 2 gates
# =========================================================================== #
#
# FINDING (2026-06-18): vix_bear_hard_cap and entry_bar_body_pct_min behaved
# correctly when passed as DIRECT kwargs, but were SILENTLY DROPPED when supplied
# via params_overrides={...} — the L38/L72/C14 "translated-but-unapplied" bug class.
#   * vix_bear_hard_cap: _params_to_kwargs DID translate it (orchestrator.py:405),
#     but the override-application block had NO line assigning ovrk["vix_bear_hard_cap"]
#     back onto the local kwarg, so it never reached the gate at orchestrator.py:~1424.
#   * entry_bar_body_pct_min: was NOT mapped in _params_to_kwargs at all.
# Neither gate was in runner.run_with_params' direct_passthrough allowlist either,
# so walk-forward validation also could not see them through params.
#
# FIX (2026-06-18): orchestrator.py now translates entry_bar_body_pct_min in
# _params_to_kwargs AND assigns BOTH gates from ovrk in the override-application
# block; runner.py adds all six gates to direct_passthrough. These guards now
# assert the FIXED state — supplying each gate via params_overrides fires it —
# so the bug cannot silently regress. The DIRECT-kwarg path is verified still-works.


@_needs_data
def test_CRITICAL_vix_bear_hard_cap_works_via_params_overrides() -> None:
    """CRITICAL (FIXED 2026-06-18): vix_bear_hard_cap supplied via params_overrides
    now FIRES the gate (was a dead knob — silently dropped by the plumbing).

    On 2025-11-21 the VIX=26.58 bear must be blocked whether the cap is supplied
    via params_overrides OR via DIRECT kwarg. If the params_overrides path ever
    regresses (gate stops firing through params), this guard fails."""
    day = dt.date(2025, 11, 21)
    base = _run_day(day, **_RISK)
    via_override = _run_day(day, params_overrides={**_RISK, "vix_bear_hard_cap": 23.0})
    via_kwarg = _run_day(day, vix_bear_hard_cap=23.0, **_RISK)

    # FIXED: params_overrides path now changes output vs baseline (gate active).
    assert _sig(via_override.trades) != _sig(base.trades), (
        "REGRESSION: vix_bear_hard_cap via params_overrides is INERT again "
        "(output identical to baseline) — the params-path plumbing broke. "
        "Check _params_to_kwargs translation + the override-application assignment."
    )
    assert "SKIP_VIX_BEAR_HIGH" in _actions(via_override), (
        "REGRESSION: vix_bear_hard_cap via params_overrides did NOT fire the gate — "
        "the translated-but-unapplied dead-knob bug has returned."
    )
    # Direct-kwarg path must also still block the VIX>=23 bear.
    assert "SKIP_VIX_BEAR_HIGH" in _actions(via_kwarg), (
        "REGRESSION: vix_bear_hard_cap via DIRECT kwarg no longer blocks — "
        "the gate's direct plumbing path broke."
    )


@_needs_data
def test_CRITICAL_entry_bar_body_pct_min_works_via_params_overrides() -> None:
    """CRITICAL (FIXED 2026-06-18): entry_bar_body_pct_min supplied via
    params_overrides now FIRES the gate (was a dead knob — never mapped in
    _params_to_kwargs).

    On 2025-06-06 the body_pct=0.043 doji bear must be blocked whether supplied
    via params_overrides OR via DIRECT kwarg (SKIP_DOJI_ENTRY_BAR)."""
    day = dt.date(2025, 6, 6)
    base = _run_day(day, **_RISK)
    via_override = _run_day(day, params_overrides={**_RISK, "entry_bar_body_pct_min": 0.20})
    via_kwarg = _run_day(day, entry_bar_body_pct_min=0.20, **_RISK)

    # FIXED: params_overrides path now changes output vs baseline (gate active).
    assert _sig(via_override.trades) != _sig(base.trades), (
        "REGRESSION: entry_bar_body_pct_min via params_overrides is INERT again "
        "(output identical to baseline) — the params-path plumbing broke. "
        "Check _params_to_kwargs translation + the override-application assignment."
    )
    assert "SKIP_DOJI_ENTRY_BAR" in _actions(via_override), (
        "REGRESSION: entry_bar_body_pct_min via params_overrides did NOT fire the "
        "gate — the translated-but-unapplied dead-knob bug has returned."
    )
    # Direct-kwarg path must also still block the doji bear.
    assert "SKIP_DOJI_ENTRY_BAR" in _actions(via_kwarg), (
        "REGRESSION: entry_bar_body_pct_min via DIRECT kwarg no longer blocks — "
        "the gate's direct plumbing path broke."
    )


@_needs_data
def test_CRITICAL_four_gates_DO_work_via_params_overrides() -> None:
    """Contrast control: the other four ported gates DO take effect via
    params_overrides (proving the bug is specific to the two gates above, not a
    blanket params_overrides failure)."""
    checks = [
        (dt.date(2025, 10, 30), "block_level_rejection", True, "SKIP_LEVEL_REJECTION_GATE"),
        (dt.date(2025, 6, 5), "block_bull_1100_1200", True, "SKIP_BULL_1100_1200"),
        (dt.date(2025, 6, 9), "block_elite_bull", True, "SKIP_ELITE_BULL_LEVEL_RECLAIM"),
        (dt.date(2025, 6, 5), "block_bull_morning_agg", True, "SKIP_BULL_MORNING_AGG"),
    ]
    for day, key, val, action in checks:
        po = {**_RISK, key: val}
        if key == "block_elite_bull":
            po.update(block_elite_bull_vix_low=0.0, block_elite_bull_vix_high=25.0)
        r = _run_day(day, params_overrides=po)
        assert action in _actions(r), (
            f"{key} via params_overrides did NOT fire {action} on {day} "
            "(this gate's params_overrides path is also broken)"
        )
