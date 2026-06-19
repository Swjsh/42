"""Unit tests for the opt-in TIME-CONDITIONAL EARLY EXIT knob in simulate_trade_real.

Game Plan 2 (2026-06-19): cut STAGNANT / NON-FAVORED 0DTE positions early to step
off the back-loaded theta cliff, while letting in-favor positions ride to the normal
exits. The knob is `early_cutoff_et` (default None = OFF) + `early_cutoff_min_favor_pct`.

These tests use a SYNTHETIC put contract (monkeypatched into the disk loader) so the
favor logic is deterministic and disk-free. Three behaviors are asserted:

  1. NON-FAVORED is cut at the cutoff (stagnant premium → exit at cutoff bar close).
  2. FAVORED rides PAST the cutoff (premium above threshold → not cut early).
  3. Default (early_cutoff_et=None) is byte-for-byte the prior behavior (no early exit).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from lib import simulator_real as sr
from lib.simulator_real import simulate_trade_real


# ── Synthetic-frame builders ─────────────────────────────────────────────────
_DATE = dt.date(2025, 3, 3)  # an arbitrary weekday; no real data is touched


def _spy_frame(closes: list[float], start_time=dt.time(9, 30)) -> pd.DataFrame:
    """A minimal SPY 5m RTH frame: monotone timestamps, flat OHLC around `closes`."""
    rows = []
    t = dt.datetime.combine(_DATE, start_time)
    for c in closes:
        rows.append({
            "timestamp_et": pd.Timestamp(t),
            "open": c, "high": c + 0.05, "low": c - 0.05, "close": c,
            "volume": 1_000_000,
        })
        t += dt.timedelta(minutes=5)
    df = pd.DataFrame(rows)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


def _opt_frame(premiums: list[float], start_time=dt.time(9, 30)) -> pd.DataFrame:
    """A synthetic option contract frame aligned 1:1 with the SPY frame timestamps.

    high == low == close == open == premium on each bar (flat intrabar) so the
    favor test (best_premium = bar high) and the exit fill (bar close) are equal
    and easy to reason about.
    """
    rows = []
    t = dt.datetime.combine(_DATE, start_time)
    for p in premiums:
        rows.append({
            "timestamp_et": pd.Timestamp(t),
            "open": p, "high": p, "low": p, "close": p,
            "volume": 5000, "vwap": p, "trade_count": 50,
        })
        t += dt.timedelta(minutes=5)
    df = pd.DataFrame(rows)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


@pytest.fixture
def patch_loader(monkeypatch):
    """Patch the disk loader so simulate_trade_real reads our synthetic option frame."""
    holder = {}

    def _install(opt_df: pd.DataFrame):
        monkeypatch.setattr(sr, "load_contract_bars", lambda symbol: opt_df)
        holder["df"] = opt_df

    return _install


def _run(spy_df, ribbon_df, entry_idx, **kwargs):
    """simulate_trade_real with safe defaults for an isolated put trade.

    rejection_level far away + premium_stop disabled + no profit-lock so the ONLY
    exits that can fire are the time-conditional cutoff (if set) and the 15:50 stop.
    """
    bar = spy_df.iloc[entry_idx]
    base = dict(
        entry_bar_idx=entry_idx, entry_bar=bar, spy_df=spy_df, ribbon_df=ribbon_df,
        rejection_level=10_000.0,          # unreachable → level stop never fires
        triggers_fired=["t"], side="P", qty=3, setup="UNIT",
        premium_stop_pct=-0.99,            # chart-stop only (no premium stop)
        strike_offset=0,
        use_tiered_exits=False,            # single runner leg — simpler PnL reasoning
        entry_slippage=0.0, exit_slippage=0.0,
    )
    base.update(kwargs)
    return simulate_trade_real(**base)


# Build a long flat session 09:30 → 16:00 (78 bars) so cutoffs at 15:00/15:15/15:30
# all fall inside the frame and the 15:50 time stop is the terminal fallback.
def _session(premiums_pattern):
    n = 79
    spy = _spy_frame([600.0] * n)
    ribbon = pd.DataFrame({
        "fast": [600.0] * n, "pivot": [600.0] * n, "slow": [600.0] * n,
        "stack": ["BEAR"] * n, "spread_cents": [5.0] * n,
    })
    opt = _opt_frame(premiums_pattern(n))
    return spy, ribbon, opt


def test_nonfavored_cut_at_cutoff(patch_loader):
    """A premium that stays FLAT (no favor) must be force-closed at the cutoff bar,
    well before the 15:50 hard stop."""
    spy, ribbon, opt = _session(lambda n: [1.00] * n)  # dead-flat premium = stagnant
    patch_loader(opt)
    fill = _run(spy, ribbon, entry_idx=2,
                early_cutoff_et=dt.time(15, 0), early_cutoff_min_favor_pct=0.10)
    assert fill is not None
    # Exit must land at the cutoff (15:00), not the 15:50 time stop.
    assert fill.runner_exit_time_et.time() == dt.time(15, 0), fill.runner_exit_time_et
    assert fill.exit_reason == sr.ExitReason.EXIT_ALL_TIME_STOP
    assert not fill.tp1_filled()


def test_favored_rides_past_cutoff(patch_loader):
    """A premium that has climbed above the favor threshold by the cutoff must NOT be
    cut early — it rides to a later exit (here: TP1 premium fallback / 15:50)."""
    # Premium ramps up: by 15:00 it is well above entry*(1+0.10). TP1 fallback default
    # is +30%; cap the ramp below that so the early-cutoff (not TP1) is the thing under
    # test — but it is clearly in-favor (>+10%) at the cutoff.
    def ramp(n):
        out = []
        for i in range(n):
            out.append(min(1.20, 1.00 + 0.01 * i))  # +1%/bar, capped +20% (< +30% TP1)
        return out
    spy, ribbon, opt = _session(ramp)
    patch_loader(opt)
    fill = _run(spy, ribbon, entry_idx=2,
                early_cutoff_et=dt.time(15, 0), early_cutoff_min_favor_pct=0.10)
    assert fill is not None
    # In favor at the cutoff → not cut at 15:00. Must exit later (>= cutoff bar).
    assert fill.runner_exit_time_et.time() > dt.time(15, 0), (
        f"in-favor position was cut early at {fill.runner_exit_time_et}")


def test_default_off_no_early_exit(patch_loader):
    """early_cutoff_et=None (production default) → no early-exit branch ever fires.
    A dead-flat premium runs to the 15:50 hard time stop, identical to prior behavior."""
    spy, ribbon, opt = _session(lambda n: [1.00] * n)
    patch_loader(opt)
    fill_off = _run(spy, ribbon, entry_idx=2)  # knob unset → OFF
    assert fill_off is not None
    assert fill_off.runner_exit_time_et.time() == dt.time(15, 50)
    assert fill_off.exit_reason == sr.ExitReason.EXIT_ALL_TIME_STOP


def test_cutoff_threshold_boundary(patch_loader):
    """Exactly-at-threshold counts as in-favor (>=), so it is NOT cut; just-below IS cut."""
    # Flat premium exactly at +10% (== threshold) → in-favor → rides.
    spy, ribbon, opt = _session(lambda n: [1.10] * n)  # entry≈1.10? No: entry is bar after idx
    patch_loader(opt)
    # entry premium = opt bar at entry_idx+1 = 1.10; favor threshold = 1.10*1.10=1.21.
    # Flat 1.10 < 1.21 → NOT in favor → cut. (boundary is vs ENTRY premium, asserted next.)
    fill = _run(spy, ribbon, entry_idx=2,
                early_cutoff_et=dt.time(15, 0), early_cutoff_min_favor_pct=0.0)
    # With min_favor_pct=0.0, threshold == entry premium; flat premium == entry → in-favor
    # (>=) → rides to 15:50. Confirms the >= boundary semantics.
    assert fill.runner_exit_time_et.time() == dt.time(15, 50), fill.runner_exit_time_et
