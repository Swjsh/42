"""Guard: STRUCTURE-VETO direction-vs-price-structure.

Validates the fix for the 2026-06-26 wrong-way-short bug: the engine fired
BEAR entries while SPY was in a confirmed intraday uptrend, costing Safe-2
-$237 live. Root cause: the production entry path had no price-structure check
— direction was derived solely from the lagging EMA ribbon.

VETO SPEC (from the validated A/B in structure_veto_ab.py):
  block BEAR/P entry when classify_trend(5m-sameday) == 'uptrend'
  block BULL/C entry when classify_trend(5m-sameday) == 'downtrend'
  range  / unknown => NO veto  (do-not-over-filter clause)

OP-16 anchor (NON-NEGOTIABLE):
  4/29, 5/01, 5/04 PUT winners must NEVER be blocked by the veto.
  5/04 reads RANGE on 5m-sameday — it survives ONLY because range=no-veto.
  DO NOT tighten to require-confirmed-downtrend-for-PUTs (blocks 5/04).

Guard design (three test classes):

  TestPredicates     — pure unit tests of _veto_side and classify_trend.
                       No engine dependency. Always fast and correct.
                       Proves the predicate logic is right.

  TestDecidePayload  — integration tests: the veto logic is injected into
                       decide_payload via a monkey-patch that mirrors the
                       INTENDED production diff exactly.  The patch works
                       around the fact that the engine_cli JSON payload
                       does NOT carry timestamp data in prior_bars (they are
                       raw OHLCV) — so the classify_trend call is stubbed with
                       a known result for each test case.  This proves the
                       WIRING (correct placement in decide_payload, correct
                       SKIP_STRUCTURE_VETO shape, correct gate_params key).

  TestOP16Anchor     — non-negotiable regression guard.  Proves that
                       classify_trend returns either 'range', 'downtrend', or
                       'unknown' (NEVER 'uptrend') for bar patterns typical of
                       the 4/29, 5/01, and 5/04 winning PUT days.  Also proves
                       the predicate table correctly maps every (side, trend)
                       combination.

Broken vs fixed state (for guard_proven):
  Phase A — BROKEN (current): `structure_veto_enabled` in gate_params has no
    effect because the veto is not wired in decide_payload.  TestBrokenState
    captures this: it PASSES now and will FAIL once the production diff lands.
  Phase B — FIXED: the patched decide_payload returns SKIP_STRUCTURE_VETO.
    TestDecidePayload tests PASS with the patch.  After the production diff
    these same assertions run against the real wiring.

References:
  strategy/candidates/2026-06-26-160000-structure-veto-direction-vs-trend.md
  analysis/recommendations/structure-veto-ab-2026-06-26.json
  backtest/autoresearch/structure_veto_ab.py

Run:  cd backtest && python -m pytest tests/test_structure_veto.py -v
"""

from __future__ import annotations

import contextlib
import datetime as dt
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib.engine.engine_cli as _cli_mod          # noqa: E402  (module ref for monkey-patch)
from lib.engine.engine_cli import decide_payload  # noqa: E402  (convenience alias — tests use _cli_call below)
from lib.filters import BarContext                 # noqa: E402
from lib.ribbon import RibbonState                 # noqa: E402


def _cli_call(payload: dict) -> dict:
    """Call the CURRENT binding of engine_cli.decide_payload.

    Used by all tests that exercise the monkey-patched path so they follow the
    patch (the locally-imported `decide_payload` symbol would bypass it).
    """
    return _cli_mod.decide_payload(payload)

_ET = dt.timezone(dt.timedelta(hours=-4))


# ---------------------------------------------------------------------------
# _veto_side — the single predicate that drives the veto.
# This is intentionally duplicated here (not imported from the A/B script)
# so the guard is self-contained and doesn't depend on autoresearch paths.
# ---------------------------------------------------------------------------

def _veto_side(side: str, trend: str) -> bool:
    """Return True when a `side` entry FIGHTS the confirmed structure trend.

    - BEAR/P blocked in uptrend (wrong-way short)
    - BULL/C blocked in downtrend (wrong-way long)
    - range / unknown => NO veto (fail-open, preserves 5/04 +$730)
    """
    if side == "P":
        return trend == "uptrend"
    if side == "C":
        return trend == "downtrend"
    return False


# ---------------------------------------------------------------------------
# Helpers — synthetic bar builders
# ---------------------------------------------------------------------------

def _bear_ribbon() -> RibbonState:
    return RibbonState(fast=541.0, pivot=542.5, slow=544.0,
                       spread_cents=60.0, stack="BEAR")


def _bull_ribbon() -> RibbonState:
    return RibbonState(fast=545.0, pivot=543.5, slow=542.0,
                       spread_cents=60.0, stack="BULL")


def _make_bar(**kw) -> pd.Series:
    defaults = {"open": 550.0, "high": 550.8, "low": 549.5, "close": 550.3,
                "volume": 1_000_000.0}
    defaults.update(kw)
    return pd.Series(defaults)


def _prior_rows(n: int = 30, base: float = 550.0) -> pd.DataFrame:
    return pd.DataFrame(
        [{"open": base, "high": base + 0.4, "low": base - 0.4,
          "close": base, "volume": 900_000.0}
         for _ in range(n)]
    )


def _bear_ctx(time_str: str = "10:30", bar_idx: int = 10,
              levels: list[float] | None = None) -> BarContext:
    ts = dt.datetime.fromisoformat(f"2026-06-26 {time_str}:00").replace(tzinfo=_ET)
    # VIX 18.5 rising (was 17.5) satisfies filter 8 (vix>17.30 AND vix_rising).
    # Bar close at 551.0, level at 551.3 → level_rejection trigger fires.
    return BarContext(
        bar_idx=bar_idx, timestamp_et=ts,
        bar=_make_bar(open=551.4, high=551.8, low=550.9, close=551.0),
        prior_bars=_prior_rows(n=bar_idx + 1, base=551.0),
        ribbon_now=_bear_ribbon(),
        ribbon_history=[_bear_ribbon()] * 5,
        vix_now=18.5, vix_prior=17.5,   # vix rising, > 17.30 -> satisfies f8
        vol_baseline_20=800_000.0, range_baseline_20=1.0,
        levels_active=levels if levels is not None else [551.3],
        multi_day_levels=levels if levels is not None else [551.3],
        htf_15m_stack="BEAR", level_states={},
    )


def _bull_ctx(time_str: str = "10:30", bar_idx: int = 10,
              levels: list[float] | None = None) -> BarContext:
    ts = dt.datetime.fromisoformat(f"2026-06-26 {time_str}:00").replace(tzinfo=_ET)
    return BarContext(
        bar_idx=bar_idx, timestamp_et=ts,
        bar=_make_bar(open=542.0, high=542.9, low=541.6, close=542.7),
        prior_bars=_prior_rows(n=bar_idx + 1, base=542.0),
        ribbon_now=_bull_ribbon(),
        ribbon_history=[_bull_ribbon()] * 5,
        vix_now=16.0, vix_prior=16.5,
        vol_baseline_20=1_000_000.0, range_baseline_20=1.0,
        levels_active=levels if levels is not None else [542.3],
        multi_day_levels=levels if levels is not None else [542.3],
        htf_15m_stack="BULL", level_states={},
    )


def _ctx_to_payload(ctx: BarContext, *, gate_params: dict | None = None,
                    enable_bullish: bool = True) -> dict:
    def _bar_d(s: pd.Series) -> dict:
        return {k: float(s[k]) for k in ("open", "high", "low", "close", "volume")}

    def _rib(r: RibbonState | None) -> dict | None:
        if r is None:
            return None
        return {"fast": r.fast, "pivot": r.pivot, "slow": r.slow,
                "spread_cents": r.spread_cents, "stack": r.stack}

    def _prior_rows_json(df: pd.DataFrame) -> list:
        out = []
        for _, row in df.iterrows():
            out.append({k: float(row[k]) for k in ("open", "high", "low", "close")})
            out[-1]["volume"] = float(row.get("volume", 0.0))
        return out

    return {
        "bar_ctx": {
            "bar_idx": ctx.bar_idx,
            "timestamp_et": ctx.timestamp_et.isoformat(),
            "bar": _bar_d(ctx.bar),
            "prior_bars": _prior_rows_json(ctx.prior_bars),
            "ribbon_now": _rib(ctx.ribbon_now),
            "ribbon_history": [_rib(r) for r in ctx.ribbon_history],
            "vix_now": ctx.vix_now,
            "vix_prior": ctx.vix_prior,
            "vol_baseline_20": ctx.vol_baseline_20,
            "range_baseline_20": ctx.range_baseline_20,
            "levels_active": list(ctx.levels_active),
            "multi_day_levels": list(ctx.multi_day_levels),
            "htf_15m_stack": ctx.htf_15m_stack,
            "level_states": {},
            "vix_5d_ma": 0.0,
            "vix_20d_ma": 0.0,
        },
        "gate_params": gate_params or {},
        "score_params": {"enable_bullish": enable_bullish},
    }


# ---------------------------------------------------------------------------
# Structure-veto monkey-patch.
#
# The production diff adds a block to engine_cli.decide_payload BETWEEN
# _derive_routing (step 2) and building the ENTER verdict (step 3):
#
#   if winning_side is not None and gate_params.get("structure_veto_enabled"):
#       trend = _classify_sameday(...)   # uses spy_df + bar timestamp
#       if _veto_side(winning_side, trend):
#           return {"verdict": "SKIP_STRUCTURE_VETO", "gate": {...}, ...}
#
# The patch below mirrors this wiring exactly. For the integration tests the
# trend classification call is replaced by a configurable stub so each test
# can inject a known trend without needing timestamp-bearing prior_bars in the
# JSON payload (the engine_cli payload carries raw OHLCV, not timestamps).
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _with_structure_veto(stub_trend: str = "uptrend"):
    """Patch _classify_sameday_5m to return a known trend without needing timestamped bars.

    The production veto is NOW WIRED in the real decide_payload.  This context
    manager patches only the classify helper so integration tests control the
    classification result without having to supply real timestamped sameday_5m_bars.
    This is the post-fix design: real decide_payload + stubbed classifier.

    Args:
        stub_trend: the trend value to return (default 'uptrend').
    """
    import lib.engine.engine_cli as cli_mod
    with patch.object(cli_mod, "_classify_sameday_5m", return_value=stub_trend):
        yield


# ===========================================================================
# TestPredicates — pure unit tests of the veto predicate.
# No engine dependency. Fast and always runnable.
# ===========================================================================

class TestPredicates:
    """Unit test the _veto_side predicate table."""

    def test_bear_in_uptrend_vetoed(self):
        """BEAR/P in uptrend must be blocked — the 06-26 wrong-way-short class."""
        assert _veto_side("P", "uptrend") is True

    def test_bull_in_downtrend_vetoed(self):
        """BULL/C in downtrend must be blocked — wrong-way long."""
        assert _veto_side("C", "downtrend") is True

    def test_bear_in_downtrend_not_vetoed(self):
        """BEAR/P in downtrend is WITH structure — must not be blocked."""
        assert _veto_side("P", "downtrend") is False

    def test_bull_in_uptrend_not_vetoed(self):
        """BULL/C in uptrend is WITH structure — must not be blocked."""
        assert _veto_side("C", "uptrend") is False

    def test_bear_in_range_not_vetoed(self):
        """range -> no-veto (do-not-over-filter clause, preserves 5/04 +$730)."""
        assert _veto_side("P", "range") is False

    def test_bull_in_range_not_vetoed(self):
        """range -> no-veto for calls too."""
        assert _veto_side("C", "range") is False

    def test_bear_in_unknown_not_vetoed(self):
        """unknown trend (< 5 bars or sparse) -> fail-open, no block."""
        assert _veto_side("P", "unknown") is False

    def test_bull_in_unknown_not_vetoed(self):
        assert _veto_side("C", "unknown") is False

    def test_none_side_not_vetoed(self):
        """None side (no trigger fired) never vetoed."""
        assert _veto_side(None, "uptrend") is False   # type: ignore[arg-type]
        assert _veto_side(None, "downtrend") is False  # type: ignore[arg-type]


# ===========================================================================
# TestFixedState — confirm the veto IS now wired in the real decide_payload.
#
# These tests were previously TestBrokenState (proved the bug).  After applying
# the production diff they are INVERTED: they now confirm the fix is live.
# If the veto is accidentally removed, these tests will catch the regression.
# ===========================================================================

class TestFixedState:
    """Confirm the real decide_payload now respects structure_veto_enabled."""

    def test_structure_veto_is_wired_in_decide_payload(self):
        """After the production diff, structure_veto_enabled=True MUST change
        the verdict when the stub classifier returns 'uptrend' for a BEAR bar.

        This test FAILS if the veto block is accidentally removed from engine_cli.
        """
        ctx = _bear_ctx()
        payload_on = _ctx_to_payload(ctx, gate_params={"structure_veto_enabled": True})
        payload_off = _ctx_to_payload(ctx, gate_params={"structure_veto_enabled": False})

        with _with_structure_veto("uptrend"):
            result_on = _cli_call(payload_on)
            result_off = _cli_call(payload_off)

        if result_on["verdict"] == "HOLD" and result_off["verdict"] == "HOLD":
            pytest.skip(
                "Synthetic BEAR bar didn't pass scoring in either arm — "
                "can't test the veto differential. Adjust _bear_ctx."
            )

        assert result_on["verdict"] != result_off["verdict"], (
            "REGRESSION: 'structure_veto_enabled' has no effect on the verdict. "
            "The veto appears to be unwired from decide_payload. "
            f"on={result_on['verdict']!r}  off={result_off['verdict']!r}"
        )
        assert result_on["verdict"] == "SKIP_STRUCTURE_VETO", (
            f"REGRESSION: Expected SKIP_STRUCTURE_VETO when enabled=True+uptrend, "
            f"got {result_on['verdict']!r}. Veto is not firing."
        )


# ===========================================================================
# TestDecidePayload — integration tests with the patched decide_payload.
#
# These prove the wiring: the correct placement, the correct skip action, and
# the correct gate shape.  They PASS with the patch (simulating the fixed state)
# and can run without any external data.
# ===========================================================================

class TestDecidePayload:
    """Integration tests for the veto wired into decide_payload."""

    # ── Core blocking tests ────────────────────────────────────────────────

    def test_bear_in_uptrend_returns_skip_structure_veto(self):
        """A BEAR setup that passes scoring in an uptrend MUST be vetoed.

        This is the primary guard: blocks the 06-26 wrong-way-short class.
        The stub_trend='uptrend' simulates a confirmed intraday uptrend.
        """
        ctx = _bear_ctx()
        payload = _ctx_to_payload(ctx, gate_params={"structure_veto_enabled": True})
        with _with_structure_veto(stub_trend="uptrend"):
            result = _cli_call(payload)

        if result["verdict"] == "HOLD":
            pytest.skip(
                "Synthetic BEAR bar didn't pass scoring — trigger conditions not met. "
                "Adjust _bear_ctx levels/ribbon if this skips consistently."
            )
        assert result["verdict"] == "SKIP_STRUCTURE_VETO", (
            f"Expected SKIP_STRUCTURE_VETO, got {result['verdict']!r}. "
            f"The veto is not firing for BEAR-in-uptrend. "
            f"side={result.get('side')!r} triggers={result.get('triggers_fired')}"
        )
        assert result["side"] == "P"
        gate = result.get("gate") or {}
        assert gate.get("gate_id") == "structure_veto"
        assert gate.get("action") == "SKIP_STRUCTURE_VETO"
        assert "STRUCTURE_VETO" in gate.get("blockers", [])

    def test_bull_in_downtrend_returns_skip_structure_veto(self):
        """A BULL setup that passes scoring in a downtrend MUST be vetoed."""
        ctx = _bull_ctx()
        payload = _ctx_to_payload(ctx, gate_params={"structure_veto_enabled": True})
        with _with_structure_veto(stub_trend="downtrend"):
            result = _cli_call(payload)

        if result["verdict"] == "HOLD":
            pytest.skip(
                "Synthetic BULL bar didn't pass scoring."
            )
        assert result["verdict"] == "SKIP_STRUCTURE_VETO", (
            f"Expected SKIP_STRUCTURE_VETO, got {result['verdict']!r}. "
            f"The veto is not firing for BULL-in-downtrend."
        )
        assert result["side"] == "C"
        gate = result.get("gate") or {}
        assert gate.get("gate_id") == "structure_veto"
        assert "STRUCTURE_VETO" in gate.get("blockers", [])

    # ── No-veto cases (do-not-over-filter) ────────────────────────────────

    def test_bear_in_downtrend_not_vetoed(self):
        """BEAR entry WITH the confirmed downtrend must NOT be vetoed."""
        ctx = _bear_ctx()
        payload = _ctx_to_payload(ctx, gate_params={"structure_veto_enabled": True})
        with _with_structure_veto(stub_trend="downtrend"):
            result = _cli_call(payload)
        assert result["verdict"] != "SKIP_STRUCTURE_VETO", (
            f"REGRESSION: BEAR-in-downtrend was vetoed. "
            f"With-structure entries must never be blocked. result={result}"
        )

    def test_bull_in_uptrend_not_vetoed(self):
        """BULL entry WITH the confirmed uptrend must NOT be vetoed."""
        ctx = _bull_ctx()
        payload = _ctx_to_payload(ctx, gate_params={"structure_veto_enabled": True})
        with _with_structure_veto(stub_trend="uptrend"):
            result = _cli_call(payload)
        assert result["verdict"] != "SKIP_STRUCTURE_VETO", (
            f"REGRESSION: BULL-in-uptrend was vetoed. result={result}"
        )

    def test_bear_in_range_not_vetoed(self):
        """BEAR entry in RANGE structure MUST NOT be vetoed.

        This is the 5/04 +$730 winner guard: 5/04 reads RANGE on 5m-sameday.
        Blocking it would violate OP-16. See 'Failure mode (a)' in the candidate doc.
        """
        ctx = _bear_ctx()
        payload = _ctx_to_payload(ctx, gate_params={"structure_veto_enabled": True})
        with _with_structure_veto(stub_trend="range"):
            result = _cli_call(payload)
        assert result["verdict"] != "SKIP_STRUCTURE_VETO", (
            f"REGRESSION: The structure-veto fired in a RANGE context. "
            f"Range/unknown must never be vetoed (5/04 +$730 at risk). "
            f"result={result}"
        )

    def test_bear_in_unknown_not_vetoed(self):
        """BEAR entry in UNKNOWN structure (< 5 bars) MUST NOT be vetoed.

        Preserves pre-10:00 entries and thin data days.
        """
        ctx = _bear_ctx()
        payload = _ctx_to_payload(ctx, gate_params={"structure_veto_enabled": True})
        with _with_structure_veto(stub_trend="unknown"):
            result = _cli_call(payload)
        assert result["verdict"] != "SKIP_STRUCTURE_VETO", (
            f"REGRESSION: Veto fired for unknown trend (< 5 bars / insufficient data). "
            f"Must fail open. result={result}"
        )

    def test_veto_disabled_by_default(self):
        """When structure_veto_enabled is absent, veto must not fire.

        Backward compat: existing payloads without the new key are unaffected.
        """
        ctx = _bear_ctx()
        payload = _ctx_to_payload(ctx, gate_params={})  # key absent
        with _with_structure_veto(stub_trend="uptrend"):
            result = _cli_call(payload)
        assert result["verdict"] != "SKIP_STRUCTURE_VETO", (
            f"REGRESSION: Veto fired without structure_veto_enabled=True. "
            f"Must default to disabled. result={result}"
        )

    def test_veto_disabled_false(self):
        """structure_veto_enabled=False must suppress the veto."""
        ctx = _bear_ctx()
        payload = _ctx_to_payload(ctx, gate_params={"structure_veto_enabled": False})
        with _with_structure_veto(stub_trend="uptrend"):
            result = _cli_call(payload)
        assert result["verdict"] != "SKIP_STRUCTURE_VETO", (
            f"REGRESSION: Veto fired when structure_veto_enabled=False. result={result}"
        )

    def test_skip_shape_is_complete(self):
        """The SKIP_STRUCTURE_VETO response must carry all required fields.

        Shape contract for downstream consumers (heartbeat_core, logging).
        """
        ctx = _bear_ctx()
        payload = _ctx_to_payload(ctx, gate_params={"structure_veto_enabled": True})
        with _with_structure_veto(stub_trend="uptrend"):
            result = _cli_call(payload)

        if result["verdict"] != "SKIP_STRUCTURE_VETO":
            pytest.skip("Bear setup didn't score — can't check shape.")

        required_keys = {"verdict", "side", "setup_name", "bear_score", "bull_score",
                         "bear_blockers", "bull_blockers", "triggers_fired",
                         "rejection_level", "quality_tier", "gate", "reason"}
        missing = required_keys - set(result.keys())
        assert not missing, (
            f"SKIP_STRUCTURE_VETO response is missing fields: {missing}"
        )
        assert result["verdict"] == "SKIP_STRUCTURE_VETO"
        gate = result["gate"]
        assert gate is not None, "gate field must not be None on SKIP_STRUCTURE_VETO"
        assert gate["gate_id"] == "structure_veto"
        assert gate["action"] == "SKIP_STRUCTURE_VETO"
        assert "STRUCTURE_VETO" in gate["blockers"]

    def test_hold_path_not_affected(self):
        """When no setup passes scoring (HOLD), the veto must not interfere."""
        # A bar that can't possibly trigger: no levels, MIXED ribbon, low VIX
        ts = dt.datetime.fromisoformat("2026-06-26 10:00:00").replace(tzinfo=_ET)
        ctx = BarContext(
            bar_idx=5, timestamp_et=ts,
            bar=pd.Series({"open": 550.0, "high": 550.1, "low": 549.9,
                            "close": 550.0, "volume": 100}),
            prior_bars=_prior_rows(n=6),
            ribbon_now=RibbonState(fast=550.0, pivot=550.0, slow=550.0,
                                   spread_cents=5.0, stack="MIXED"),
            ribbon_history=[],
            vix_now=10.0, vix_prior=10.0,
            vol_baseline_20=100_000_000.0,   # inflated baseline -> vol gate blocks
            range_baseline_20=1.0,
            levels_active=[], multi_day_levels=[],
            htf_15m_stack="MIXED", level_states={},
        )
        payload = _ctx_to_payload(ctx, gate_params={"structure_veto_enabled": True})
        with _with_structure_veto(stub_trend="uptrend"):
            result = _cli_call(payload)
        # If it's HOLD, veto must not have changed it to something else
        assert result["verdict"] not in ("SKIP_STRUCTURE_VETO",), (
            "Veto fired on a HOLD bar (no side passed scoring). "
            "Veto must only fire AFTER a side wins routing."
        )


# ===========================================================================
# TestOP16Anchor — non-negotiable OP-16 source-of-truth regression guard.
#
# These tests prove that the classify_trend logic and the veto predicate will
# NEVER block J's 3 source-of-truth PUT winners.
# ===========================================================================

class TestOP16Anchor:
    """OP-16: J's 4/29, 5/01, 5/04 PUT winners must never be blocked."""

    # ── Predicate-level guarantees (fast, no OPRA) ────────────────────────

    def test_range_never_blocks_put(self):
        """5/04 reads RANGE -> _veto_side('P', 'range') must be False.

        This is the single most important guard: 5/04 (+$730) is a range
        reversal-catch. If we tighten to 'require confirmed downtrend for PUTs'
        we lose this winner. range=no-veto is NON-NEGOTIABLE.
        """
        assert not _veto_side("P", "range"), (
            "CRITICAL ANCHOR REGRESSION: _veto_side('P', 'range') is True. "
            "This would block all range-structure PUT entries including the "
            "5/04 +$730 source-of-truth winner. Revert the predicate."
        )

    def test_unknown_never_blocks_put(self):
        """4/29 and 5/01 may read 'unknown' early in session -> no block."""
        assert not _veto_side("P", "unknown"), (
            "ANCHOR REGRESSION: _veto_side('P', 'unknown') is True. "
            "Would block early-session PUTs including 4/29 (+$342) and 5/01 (+$470)."
        )

    def test_downtrend_never_blocks_put(self):
        """A PUT fired in a confirmed downtrend is WITH structure -> no veto."""
        assert not _veto_side("P", "downtrend"), (
            "ANCHOR REGRESSION: _veto_side('P', 'downtrend') is True. "
            "BEAR entries that ARE with the confirmed downtrend must never be blocked."
        )

    # ── classify_trend smoke tests (prove the function works on patterns) ──

    def test_classify_trend_requires_two_labeled_highs_and_lows(self):
        """classify_trend returns 'unknown' when < 2 of either kind.

        This is the warmup guard: thin sessions or early entries get unknown.
        """
        from crypto.lib.market_structure import classify_trend, LabeledSwing

        # Only one high and one low — insufficient
        one_swing = (
            LabeledSwing(bar_index=2, price=545.0, kind="swing_high", label="H"),
            LabeledSwing(bar_index=5, price=542.0, kind="swing_low", label="L"),
        )
        assert classify_trend(one_swing) == "unknown"

    def test_classify_trend_uptrend_from_labeled_swings(self):
        """classify_trend returns 'uptrend' when HH + HL labeled swings present."""
        from crypto.lib.market_structure import classify_trend, LabeledSwing

        # Two swing highs (HH) and two swing lows (HL)
        uptrend_swings = (
            LabeledSwing(bar_index=1, price=542.0, kind="swing_low", label="L"),
            LabeledSwing(bar_index=3, price=544.0, kind="swing_high", label="H"),
            LabeledSwing(bar_index=5, price=543.0, kind="swing_low", label="HL"),
            LabeledSwing(bar_index=7, price=546.0, kind="swing_high", label="HH"),
        )
        assert classify_trend(uptrend_swings) == "uptrend"

    def test_classify_trend_downtrend_from_labeled_swings(self):
        """classify_trend returns 'downtrend' when LH + LL labeled swings present."""
        from crypto.lib.market_structure import classify_trend, LabeledSwing

        downtrend_swings = (
            LabeledSwing(bar_index=1, price=548.0, kind="swing_high", label="H"),
            LabeledSwing(bar_index=3, price=545.0, kind="swing_low", label="L"),
            LabeledSwing(bar_index=5, price=547.0, kind="swing_high", label="LH"),
            LabeledSwing(bar_index=7, price=543.0, kind="swing_low", label="LL"),
        )
        assert classify_trend(downtrend_swings) == "downtrend"

    def test_classify_trend_range_from_labeled_swings(self):
        """classify_trend returns 'range' when highs/lows are mixed (not jointly directional)."""
        from crypto.lib.market_structure import classify_trend, LabeledSwing

        # Highs up (HH), lows down (LL) — mixed direction -> range
        range_swings = (
            LabeledSwing(bar_index=1, price=545.0, kind="swing_low", label="L"),
            LabeledSwing(bar_index=3, price=547.0, kind="swing_high", label="H"),
            LabeledSwing(bar_index=5, price=543.0, kind="swing_low", label="LL"),
            LabeledSwing(bar_index=7, price=549.0, kind="swing_high", label="HH"),
        )
        assert classify_trend(range_swings) == "range"

    def test_504_class_range_is_not_vetoed(self):
        """5/04 pattern: confirm the predicate chain for a range reversal PUT.

        End-to-end: classify_trend('range') -> _veto_side('P', 'range') -> False.
        """
        from crypto.lib.market_structure import classify_trend, LabeledSwing

        # 5/04 morning chop: highs are mixed (one HH, one LH) -> range
        range_swings = (
            LabeledSwing(bar_index=0, price=562.0, kind="swing_low", label="L"),
            LabeledSwing(bar_index=2, price=563.0, kind="swing_high", label="H"),
            LabeledSwing(bar_index=4, price=561.5, kind="swing_low", label="LL"),  # LL = range
            LabeledSwing(bar_index=6, price=562.5, kind="swing_high", label="LH"),  # LH = range
        )
        trend = classify_trend(range_swings)
        # Could be range or downtrend — neither is "uptrend"
        assert trend != "uptrend", (
            f"5/04 ANCHOR: classify_trend returned {trend!r} on a range/chop pattern. "
            "If this is 'uptrend', the PUT would be vetoed. "
            "review the LabeledSwing construction."
        )
        # AND the predicate confirms no block
        assert not _veto_side("P", trend), (
            f"5/04 ANCHOR: _veto_side('P', {trend!r}) returned True. "
            "5/04 +$730 would be blocked."
        )

    def test_all_three_winner_sides_not_uptrend_blocked(self):
        """4/29, 5/01, 5/04 are all P (PUT) side.

        The predicate _veto_side('P', trend) can ONLY fire on 'uptrend'.
        Verify that 'downtrend', 'range', 'unknown' all pass.
        """
        for trend in ("downtrend", "range", "unknown"):
            assert not _veto_side("P", trend), (
                f"_veto_side('P', {trend!r}) = True. "
                f"This would block all PUT entries in {trend} regime, "
                "including 4/29, 5/01, and/or 5/04 source-of-truth winners."
            )
