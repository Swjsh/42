"""Guard test for G2-TRENDLINE-BYPASS-INVERTS-PRIORITY (filed 2026-07-27, resolved 2026-08-01).

Pins the `trendline_bypass_scope` flag added to `evaluate_bearish_setup`
(backtest/lib/filters.py, TRENDLINE-CHOP-ZONE relaxation, ~line 1603):

  - "trendline_only" (DEFAULT): byte-identical to pre-flag behavior -- the filters-5/8/9
    relaxation fires ONLY when trendline_rejection is the SOLE level-tied trigger. A
    level_rejection setup (co-occurring with trendline) gets NO relief.
  - "all_level_tied" (ARM_EXTEND): the SAME relaxation extends to ANY level-tied trigger.
  - "none" (ARM_REMOVE): the trendline-only bypass is deleted outright.

RED-proofed: reverting the filters.py edit (deleting the `trendline_bypass_scope` branch,
i.e. restoring the old unconditional `trendline_only_setup = (...)` assignment) makes
test_all_level_tied_extends_relief_to_level_rejection and test_none_removes_bypass_even_for_
trendline_only FAIL (both would silently fall back to "trendline_only" semantics because the
default kwarg is absent) while test_default_scope_is_byte_identical still passes -- proving
these two tests actually exercise the new branch, not just the untouched default path.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib import filters as filters_mod  # noqa: E402
from lib.filters import BarContext, evaluate_bearish_setup  # noqa: E402
from lib.ribbon import RibbonState  # noqa: E402


def _mixed_ribbon_ctx() -> BarContext:
    """MIXED ribbon (blocks filter 5) + low/falling VIX (blocks filter 8) -- the exact chop
    conditions the 2026-05-09 relaxation was built to admit a trendline-only trade through."""
    hist = [{"open": 700.0, "high": 700.3, "low": 699.7, "close": 700.0, "volume": 900_000}] * 30
    df = pd.DataFrame(hist)
    idx = len(df) - 1
    rs = RibbonState(fast=700.05, pivot=700.10, slow=700.00, stack="MIXED", spread_cents=50.0)
    return BarContext(
        bar_idx=idx, timestamp_et=dt.datetime(2026, 8, 1, 11, 0),
        bar=df.iloc[idx], prior_bars=df, ribbon_now=rs, ribbon_history=[rs] * 6,
        vix_now=14.0, vix_prior=14.5,  # below VIX_BEAR_THRESHOLD (17.30) -> filter 8 blocks
        vol_baseline_20=900_000, range_baseline_20=0.6,
        levels_active=[705.0], multi_day_levels=[705.0], htf_15m_stack="BEAR",
    )


@pytest.fixture(autouse=True)
def _force_triggers(monkeypatch):
    """Deterministic trigger control: patch every trigger-detector called inside
    evaluate_bearish_setup so tests only vary WHICH triggers are present, never geometry.
    Filters 6/7/9 forced to auto-pass so only 5/8 (the ones the relaxation touches) plus
    the flag's own routing decide the blocker list."""
    monkeypatch.setattr(filters_mod, "volume_divergence_failed", lambda *a, **k: False)  # filter 7 pass
    monkeypatch.setattr(filters_mod, "breakdown_bar_bearish", lambda *a, **k: True)       # filter 9 pass
    monkeypatch.setattr(filters_mod, "detect_confluence", lambda *a, **k: None)
    monkeypatch.setattr(filters_mod, "detect_sequence_rejection", lambda *a, **k: False)
    monkeypatch.setattr(filters_mod, "detect_wick_rejection_bearish", lambda *a, **k: None)
    monkeypatch.setattr(filters_mod, "detect_candlestick_pattern_bearish", lambda *a, **k: None)
    yield


def _run(ctx, *, level_fires: bool, trendline_fires: bool, scope: str = "trendline_only",
          monkeypatch=None):
    monkeypatch.setattr(
        filters_mod, "detect_level_rejection",
        (lambda bar, levels: 705.0) if level_fires else (lambda bar, levels: None),
    )
    monkeypatch.setattr(
        filters_mod, "detect_trendline_rejection_bearish",
        (lambda *a, **k: 699.5) if trendline_fires else (lambda *a, **k: None),
    )
    return evaluate_bearish_setup(ctx, min_triggers=1, trendline_bypass_scope=scope)


class TestG2TrendlineBypassScope:
    def test_default_scope_is_byte_identical_trendline_only_gets_relief(self, monkeypatch):
        """Pre-existing behavior, unchanged: trendline-only -> filters 5/8 relaxed."""
        ctx = _mixed_ribbon_ctx()
        r = _run(ctx, level_fires=False, trendline_fires=True, scope="trendline_only",
                 monkeypatch=monkeypatch)
        assert 5 not in r.blockers, f"trendline-only must relax filter 5, got {r.blockers}"
        assert 8 not in r.blockers, f"trendline-only must relax filter 8, got {r.blockers}"

    def test_default_scope_level_rejection_gets_no_relief(self, monkeypatch):
        """THE G2 finding: under the default scope, a level_rejection co-occurring with
        trendline_rejection gets NO relief (stronger evidence, stricter standard)."""
        ctx = _mixed_ribbon_ctx()
        r = _run(ctx, level_fires=True, trendline_fires=True, scope="trendline_only",
                 monkeypatch=monkeypatch)
        assert 5 in r.blockers, f"level_rejection co-fire must NOT relax filter 5 (default scope), got {r.blockers}"
        assert 8 in r.blockers, f"level_rejection co-fire must NOT relax filter 8 (default scope), got {r.blockers}"

    def test_all_level_tied_extends_relief_to_level_rejection(self, monkeypatch):
        """ARM_EXTEND: with scope='all_level_tied', a level_rejection (even co-firing with
        trendline) now ALSO gets the filters-5/8 relief -- the inverted priority is fixed."""
        ctx = _mixed_ribbon_ctx()
        r = _run(ctx, level_fires=True, trendline_fires=True, scope="all_level_tied",
                 monkeypatch=monkeypatch)
        assert 5 not in r.blockers, f"all_level_tied must relax filter 5 for level_rejection, got {r.blockers}"
        assert 8 not in r.blockers, f"all_level_tied must relax filter 8 for level_rejection, got {r.blockers}"

    def test_all_level_tied_still_relieves_trendline_only(self, monkeypatch):
        """ARM_EXTEND never makes trendline-only WORSE off -- superset of relief, not a swap."""
        ctx = _mixed_ribbon_ctx()
        r = _run(ctx, level_fires=False, trendline_fires=True, scope="all_level_tied",
                 monkeypatch=monkeypatch)
        assert 5 not in r.blockers
        assert 8 not in r.blockers

    def test_none_removes_bypass_even_for_trendline_only(self, monkeypatch):
        """ARM_REMOVE: scope='none' deletes the relaxation outright -- even a pure
        trendline-only setup now faces the full filter set, same as pre-2026-05-09."""
        ctx = _mixed_ribbon_ctx()
        r = _run(ctx, level_fires=False, trendline_fires=True, scope="none",
                 monkeypatch=monkeypatch)
        assert 5 in r.blockers, f"scope='none' must NOT relax filter 5, got {r.blockers}"
        assert 8 in r.blockers, f"scope='none' must NOT relax filter 8, got {r.blockers}"

    def test_unknown_scope_string_falls_back_to_default_fail_closed(self, monkeypatch):
        """Fail-closed: an unrecognized scope string behaves like 'trendline_only' (the
        narrowest/safest relief), never like 'all_level_tied' (the widest)."""
        ctx = _mixed_ribbon_ctx()
        r = _run(ctx, level_fires=True, trendline_fires=True, scope="typo_garbage",
                 monkeypatch=monkeypatch)
        assert 5 in r.blockers, f"unrecognized scope must fail closed (narrowest relief), got {r.blockers}"
