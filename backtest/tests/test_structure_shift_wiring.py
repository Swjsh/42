"""Guards STRUCTURE-SHIFT-CONFIRMATION-AT-LEVELS wiring — FLAG-GATED, DEFAULT OFF.

Pre-reg:  analysis/recommendations/prereg-structure-shift-confirmation-2026-07-28.json
Doctrine: markdown/doctrine/J-MARKET-PHILOSOPHY.md (Gap 1 — lagging EMA confirmation vs
          immediate price-structure confirmation).
Predicate: backtest/lib/structure_shift.py (canonical, single source of truth).
Wiring:
  - backtest/lib/filters.py — filter 5 OR-alternative (bear), HTF-demerit waiver (bull).
  - backtest/lib/engine/engine_cli.py — gate_params["structure_shift_confirmation_enabled"]
    is the single flip point; threads structure_shift_confirmation=True into BOTH
    bear_kwargs and bull_kwargs before score_bar runs.
  - setup/scripts/heartbeat_core.py — GATE_KEYS pass-through only (params.json untouched;
    arming is a separate ratification decision per the pre-reg's arming_plan).

INERTNESS is the #1 deliverable here (market is OPEN while this ships): every test in the
INERTNESS class must be byte-identical whether the flag is omitted entirely or explicitly
passed False. RED-PROOFED 2026-07-28: `structure_shift_confirmation`'s default was
temporarily forced to True on both `evaluate_bearish_setup` and `evaluate_bullish_setup`
signatures, this file's INERTNESS class was re-run, and every test in it FAILED (see the
session report for the captured failure output) — then the defaults were reverted and this
class re-confirmed green. `git diff` on filters.py's signatures is clean at rest (this is a
one-time verification performed during authoring, not a permanent part of this suite —
mutating source inside a pytest run is not something we want live in CI).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backtest" / "tests"))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from backtest.lib.engine.engine_cli import decide_payload  # noqa: E402
from backtest.lib.filters import (  # noqa: E402
    BarContext,
    evaluate_bearish_setup,
    evaluate_bullish_setup,
)
from backtest.lib.ribbon import RibbonState  # noqa: E402
from backtest.lib.structure_shift import (  # noqa: E402
    detect_structure_shift_bear,
    detect_structure_shift_bull,
)

from test_why_not_provenance import LEVELS as INCIDENT_0727_LEVELS  # noqa: E402
from test_why_not_provenance import _ctx as _incident_0727_ctx  # noqa: E402


# --------------------------------------------------------------------------- fixtures
# A deliberate SPREAD: the real 2026-07-27 incident (both ribbon variants), plus two
# synthetic contexts with no level anywhere near price (so no shift is even possible) --
# inertness must hold on setups the flag can't touch as well as ones it could.

def _flat_bull_ctx() -> BarContext:
    """Clean BULL-passing fixture, levels far from price -- no shift possible."""
    hist = [{"open": 700.0, "high": 700.4, "low": 699.6, "close": 700.2, "volume": 600_000}] * 25
    df = pd.DataFrame(hist)
    idx = len(df) - 1
    rs = RibbonState(fast=700.0, pivot=699.8, slow=699.5, stack="BULL", spread_cents=50.0)
    return BarContext(
        bar_idx=idx, timestamp_et=dt.datetime(2026, 6, 10, 10, 30),
        bar=df.iloc[idx], prior_bars=df, ribbon_now=rs, ribbon_history=[rs] * 6,
        vix_now=15.0, vix_prior=15.2, vol_baseline_20=550_000, range_baseline_20=0.8,
        levels_active=[650.0, 750.0], multi_day_levels=[650.0, 750.0], htf_15m_stack="BULL",
    )


def _no_signal_ctx() -> BarContext:
    """HOLD day -- flat tape, ribbon MIXED, no level nearby."""
    hist = [{"open": 710.0, "high": 710.3, "low": 709.7, "close": 710.1, "volume": 400_000}] * 30
    df = pd.DataFrame(hist)
    idx = len(df) - 1
    rs = RibbonState(fast=710.0, pivot=710.1, slow=709.9, stack="MIXED", spread_cents=5.0)
    return BarContext(
        bar_idx=idx, timestamp_et=dt.datetime(2026, 6, 11, 11, 0),
        bar=df.iloc[idx], prior_bars=df, ribbon_now=rs, ribbon_history=[rs] * 6,
        vix_now=16.0, vix_prior=16.0, vol_baseline_20=400_000, range_baseline_20=0.6,
        levels_active=[680.0, 740.0], multi_day_levels=[680.0, 740.0], htf_15m_stack=None,
    )


# 2026-07-28 11:05 bull shape: reclaim @739.34, HTF BEAR. Level/price values pulled from
# the live decision ledger (automation/state/core-decisions.jsonl, ts_et 2026-07-28T10:56-
# 11:00, bull_reclaim_level_raw=739.34, htf_15m="BEAR"). Structure-shift sequence
# (R at idx40, confirm at idx42) is synthetic/constructed for a clean, deterministic test.
BULL_0728_LEVELS = [736.9, 737.75, 738.46, 739.34, 740.5, 741.6]


def _bull_0728_ctx() -> BarContext:
    hist = [{"open": 737.0, "high": 737.3, "low": 736.7, "close": 737.0, "volume": 500_000}] * 40
    hist += [
        {"open": 739.10, "high": 739.50, "low": 739.00, "close": 739.45, "volume": 600_000},  # idx40: R (reclaim @739.34)
        {"open": 739.30, "high": 739.60, "low": 739.10, "close": 739.20, "volume": 500_000},  # idx41: filler, not a reclaim
        {"open": 739.50, "high": 739.80, "low": 739.40, "close": 739.70, "volume": 700_000},  # idx42: confirm (higher low, higher high)
    ]
    df = pd.DataFrame(hist)
    idx = len(df) - 1
    rs = RibbonState(fast=737.0, pivot=736.8, slow=736.5, stack="BULL", spread_cents=50.0)
    return BarContext(
        bar_idx=idx, timestamp_et=dt.datetime(2026, 7, 28, 11, 5),
        bar=df.iloc[idx], prior_bars=df, ribbon_now=rs, ribbon_history=[rs] * 6,
        vix_now=18.0, vix_prior=18.1, vol_baseline_20=500_000, range_baseline_20=0.6,
        levels_active=list(BULL_0728_LEVELS), multi_day_levels=list(BULL_0728_LEVELS),
        htf_15m_stack="BEAR",
    )


INERTNESS_FIXTURES = {
    "incident_0727_ribbon_bull": lambda: _incident_0727_ctx("BULL"),
    "incident_0727_ribbon_bear": lambda: _incident_0727_ctx("BEAR"),
    "flat_bull": _flat_bull_ctx,
    "no_signal": _no_signal_ctx,
    "bull_0728_shape": _bull_0728_ctx,
}


def _payload_for(ctx: BarContext, gate_params: Optional[dict] = None) -> dict:
    """Builds a decide_payload-compatible JSON dict from a BarContext -- mirrors
    heartbeat_core._build_payload's bar_ctx shape (engine_cli.build_bar_context's
    input contract) closely enough for these synthetic fixtures."""

    def _bars(df: pd.DataFrame) -> list:
        return [
            {"open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]),
             "close": float(r["close"]), "volume": float(r["volume"])}
            for _, r in df.iterrows()
        ]

    def _rs(rs: Optional[RibbonState]) -> Optional[dict]:
        if rs is None:
            return None
        return {"fast": rs.fast, "pivot": rs.pivot, "slow": rs.slow,
                "spread_cents": rs.spread_cents, "stack": rs.stack}

    bar_ctx = {
        "bar_idx": ctx.bar_idx,
        "timestamp_et": ctx.timestamp_et.isoformat(),
        "bar": {"open": float(ctx.bar["open"]), "high": float(ctx.bar["high"]),
                "low": float(ctx.bar["low"]), "close": float(ctx.bar["close"]),
                "volume": float(ctx.bar["volume"])},
        "prior_bars": _bars(ctx.prior_bars),
        "ribbon_now": _rs(ctx.ribbon_now),
        "ribbon_history": [_rs(rs) for rs in ctx.ribbon_history],
        "vix_now": ctx.vix_now, "vix_prior": ctx.vix_prior,
        "vol_baseline_20": ctx.vol_baseline_20, "range_baseline_20": ctx.range_baseline_20,
        "levels_active": list(ctx.levels_active), "multi_day_levels": list(ctx.multi_day_levels),
        "htf_15m_stack": ctx.htf_15m_stack,
        "fhh_level": ctx.fhh_level, "vix_5d_ma": ctx.vix_5d_ma, "vix_20d_ma": ctx.vix_20d_ma,
    }
    return {"bar_ctx": bar_ctx, "gate_params": gate_params or {}, "score_params": {}}


# --------------------------------------------------------------------------- (a) INERTNESS


class TestInertness:
    """Flag absent == flag explicitly False, on every fixture, at both layers
    (evaluate_bearish_setup / evaluate_bullish_setup and decide_payload)."""

    @pytest.mark.parametrize("name", list(INERTNESS_FIXTURES))
    def test_bear_setup_result_flag_absent_equals_explicit_false(self, name):
        ctx = INERTNESS_FIXTURES[name]()
        absent = evaluate_bearish_setup(ctx)
        explicit = evaluate_bearish_setup(ctx, structure_shift_confirmation=False)
        assert absent == explicit, f"{name}: flag-absent result diverged from flag=False"

    @pytest.mark.parametrize("name", list(INERTNESS_FIXTURES))
    def test_bull_setup_result_flag_absent_equals_explicit_false(self, name):
        ctx = INERTNESS_FIXTURES[name]()
        absent = evaluate_bullish_setup(ctx)
        explicit = evaluate_bullish_setup(ctx, structure_shift_confirmation=False)
        assert absent == explicit, f"{name}: flag-absent result diverged from flag=False"

    @pytest.mark.parametrize("name", list(INERTNESS_FIXTURES))
    def test_decide_payload_flag_absent_equals_gate_params_explicit_false(self, name):
        ctx = INERTNESS_FIXTURES[name]()
        payload_absent = _payload_for(ctx, gate_params={})
        payload_explicit = _payload_for(
            ctx, gate_params={"structure_shift_confirmation_enabled": False},
        )
        v_absent = decide_payload(payload_absent)
        v_explicit = decide_payload(payload_explicit)
        assert v_absent == v_explicit, f"{name}: decide_payload diverged absent vs explicit-False"

    def test_pinned_0727_incident_values_unaffected_by_new_module(self):
        """Concrete golden values (same ones test_why_not_provenance.py already pins) --
        a permanent regression net: if a future edit ever makes the flag-off path drift,
        this fails on exact numbers, not just object equality against itself."""
        ctx = _incident_0727_ctx("BULL")
        result = evaluate_bearish_setup(ctx)
        assert result.bear_score == 9
        assert result.blockers == [5]
        assert result.passed is False
        assert "level_rejection" in result.triggers_fired
        assert result.rejection_level == 744.9

    def test_engine_cli_decide_payload_output_unaffected_key_absent(self):
        ctx = _incident_0727_ctx("BULL")
        verdict = decide_payload(_payload_for(ctx))
        assert verdict["verdict"] == "HOLD"
        assert verdict["bear_score"] == 9
        assert verdict["bear_blockers"] == [5]
        assert "level_rejection" in verdict["bear_triggers_raw"]


# --------------------------------------------------------- (b) BEAR shift path, flag ON


class TestBearShiftPathArmed:
    def test_detect_structure_shift_bear_finds_the_0727_sequence(self):
        ctx = _incident_0727_ctx("BULL")
        shift = detect_structure_shift_bear(ctx.prior_bars, ctx.bar_idx, ctx.levels_active, k=3)
        assert shift == {"rejection_bar_idx": 40, "level": 744.9, "confirmed_at_idx": 42}

    def test_incident_0727_passes_via_shift_path_while_ribbon_stays_bull(self):
        """G5 (pre-reg): the live incident anchor must be CAPTURED by the new confirmation.
        Ribbon is BULL throughout (never mutated) -- the ribbon check alone would still
        block; the OR-alternative is what flips `passed`."""
        ctx = _incident_0727_ctx("BULL")
        assert ctx.ribbon_now.stack == "BULL"

        off = evaluate_bearish_setup(ctx)
        assert off.passed is False
        assert off.blockers == [5]

        on = evaluate_bearish_setup(ctx, structure_shift_confirmation=True)
        assert on.passed is True
        assert on.blockers == []
        assert on.bear_score == 10
        assert ctx.ribbon_now.stack == "BULL"  # unchanged -- confirms the OR, not a swap

    def test_disabling_filter_5_bypasses_shift_computation_untouched(self):
        """disable_filters=[5] must still short-circuit filter 5 entirely, flag or no
        flag -- the new branch lives INSIDE `if 5 not in disable`."""
        ctx = _incident_0727_ctx("BULL")
        r1 = evaluate_bearish_setup(ctx, disable_filters=[5])
        r2 = evaluate_bearish_setup(ctx, disable_filters=[5], structure_shift_confirmation=True)
        assert r1 == r2
        assert 5 not in r1.blockers


# --------------------------------------------------------- (c) BULL mirror, flag ON


class TestBullShiftPathArmed:
    def test_detect_structure_shift_bull_finds_the_0728_sequence(self):
        ctx = _bull_0728_ctx()
        shift = detect_structure_shift_bull(ctx.prior_bars, ctx.bar_idx, ctx.levels_active, k=3)
        assert shift == {"rejection_bar_idx": 40, "level": 739.34, "confirmed_at_idx": 42}

    def test_htf_bear_demerit_waived_by_shift_confirmation(self):
        """G-mirror of the bear anchor: HTF stays BEAR throughout (never mutated); the
        soft -1 score demerit for htf disagreement is what the OR-alternative waives (bull
        has no HARD htf blocker to begin with -- see filters.py's own filter-11 docstring).
        """
        ctx = _bull_0728_ctx()
        assert ctx.htf_15m_stack == "BEAR"

        off = evaluate_bullish_setup(ctx)
        on = evaluate_bullish_setup(ctx, structure_shift_confirmation=True)

        assert on.bull_score == off.bull_score + 1, (
            f"expected the htf demerit to be waived (+1): off={off.bull_score} on={on.bull_score}"
        )
        assert ctx.htf_15m_stack == "BEAR"  # unchanged -- confirms the OR, not a swap
        # Nothing else about the two results should move -- only the demerit toggles.
        assert on.blockers == off.blockers
        assert on.triggers_fired == off.triggers_fired
        assert on.passed == off.passed

    def test_htf_agrees_shift_confirmation_is_a_no_op(self):
        """When HTF already agrees (not BEAR), the demerit was never applied -- flag on
        or off must be identical (the `if htf_disagrees` guard short-circuits either way)."""
        ctx = _bull_0728_ctx()
        ctx_agree = dataclasses.replace(ctx, htf_15m_stack="BULL")
        off = evaluate_bullish_setup(ctx_agree)
        on = evaluate_bullish_setup(ctx_agree, structure_shift_confirmation=True)
        assert off == on


# --------------------------------------------------------- (d) PARITY vs the replay tool


# Shared fixture table: hand-buildable bar sequences + expected StructureShift descriptors,
# usable by both a direct predicate test here AND (when it exists) the replay tool's own
# predicate, so the two never silently drift (Sim-accuracy-gate discipline, CLAUDE.md OP-16).
PARITY_FIXTURE_TABLE = [
    {
        "name": "bear_0727_incident",
        "side": "bear",
        "bars": None,  # filled in below from the incident ctx (kept as one source of truth)
        "bar_idx": 42,
        "levels": list(INCIDENT_0727_LEVELS),
        "k": 3,
        "expected": {"rejection_bar_idx": 40, "level": 744.9, "confirmed_at_idx": 42},
    },
    {
        "name": "bear_no_rejection_in_window",
        "side": "bear",
        "bars": [
            {"open": 700.0, "high": 700.2, "low": 699.8, "close": 700.0, "volume": 500_000},
            {"open": 700.0, "high": 700.2, "low": 699.8, "close": 700.0, "volume": 500_000},
            {"open": 700.0, "high": 700.2, "low": 699.8, "close": 700.0, "volume": 500_000},
            {"open": 700.0, "high": 700.2, "low": 699.8, "close": 700.0, "volume": 500_000},
        ],
        "bar_idx": 3,
        "levels": [750.0],
        "k": 3,
        "expected": None,
    },
    {
        "name": "bull_0728_shape",
        "side": "bull",
        "bars": None,  # filled in below from the bull-0728 ctx
        "bar_idx": 42,
        "levels": list(BULL_0728_LEVELS),
        "k": 3,
        "expected": {"rejection_bar_idx": 40, "level": 739.34, "confirmed_at_idx": 42},
    },
    {
        "name": "bull_no_reclaim_in_window",
        "side": "bull",
        "bars": [
            {"open": 700.0, "high": 700.2, "low": 699.8, "close": 700.0, "volume": 500_000},
            {"open": 700.0, "high": 700.2, "low": 699.8, "close": 700.0, "volume": 500_000},
            {"open": 700.0, "high": 700.2, "low": 699.8, "close": 700.0, "volume": 500_000},
            {"open": 700.0, "high": 700.2, "low": 699.8, "close": 700.0, "volume": 500_000},
        ],
        "bar_idx": 3,
        "levels": [650.0],
        "k": 3,
        "expected": None,
    },
]
# Backfill the two incident-derived tables from the same ctx builders used above, instead of
# hand-transcribing bar values twice (single source of truth per fixture).
_bear_incident_ctx = _incident_0727_ctx("BULL")
PARITY_FIXTURE_TABLE[0]["bars"] = [
    {"open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]),
     "close": float(r["close"]), "volume": float(r["volume"])}
    for _, r in _bear_incident_ctx.prior_bars.iterrows()
]
_bull_shape_ctx = _bull_0728_ctx()
PARITY_FIXTURE_TABLE[2]["bars"] = [
    {"open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]),
     "close": float(r["close"]), "volume": float(r["volume"])}
    for _, r in _bull_shape_ctx.prior_bars.iterrows()
]


def _replay_tool_predicate():
    """Returns (detect_bear, detect_bull) from backtest/tools/structure_shift_replay.py if
    that module exists yet (a sibling agent may be building it against the same frozen
    pre-reg concurrently); None if it doesn't exist yet."""
    try:
        from backtest.tools import structure_shift_replay as replay_mod  # type: ignore
    except ImportError:
        return None
    detect_bear = getattr(replay_mod, "detect_structure_shift_bear", None)
    detect_bull = getattr(replay_mod, "detect_structure_shift_bull", None)
    if detect_bear is None or detect_bull is None:
        return None
    return detect_bear, detect_bull


class TestParityVsCanonicalPredicate:
    """Sanity: the canonical predicate agrees with itself across the fixture table (this
    always runs). The cross-module parity assertion below only runs once
    backtest/tools/structure_shift_replay.py exists and exposes its own predicate."""

    @pytest.mark.parametrize("case", PARITY_FIXTURE_TABLE, ids=lambda c: c["name"])
    def test_canonical_predicate_matches_expected(self, case):
        df = pd.DataFrame(case["bars"])
        fn = detect_structure_shift_bear if case["side"] == "bear" else detect_structure_shift_bull
        got = fn(df, case["bar_idx"], case["levels"], k=case["k"])
        assert got == case["expected"], f"{case['name']}: predicate mismatch"

    @pytest.mark.skipif(
        _replay_tool_predicate() is None,
        reason=(
            "backtest/tools/structure_shift_replay.py does not exist yet (or doesn't "
            "expose detect_structure_shift_bear/bull) -- parity fixture table is ready "
            "above; this test activates automatically once the replay tool lands."
        ),
    )
    @pytest.mark.parametrize("case", PARITY_FIXTURE_TABLE, ids=lambda c: c["name"])
    def test_replay_tool_predicate_matches_canonical(self, case):
        replay_bear, replay_bull = _replay_tool_predicate()
        df = pd.DataFrame(case["bars"])
        replay_fn = replay_bear if case["side"] == "bear" else replay_bull
        canonical_fn = detect_structure_shift_bear if case["side"] == "bear" else detect_structure_shift_bull
        canonical = canonical_fn(df, case["bar_idx"], case["levels"], k=case["k"])
        replayed = replay_fn(df, case["bar_idx"], case["levels"], k=case["k"])
        assert replayed == canonical, f"{case['name']}: replay tool predicate diverged from canonical"
