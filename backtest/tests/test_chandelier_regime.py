"""Unit tests for the opt-in REGIME-CONDITIONAL / UNDERLYING chandelier in
simulate_trade_real (2026-06-19, vol-scaled exit per Kim-Tse-Wald).

Two opt-in extensions to the v15 premium chandelier, BOTH default OFF:
  * profit_lock_trail_pct_by_vix / profit_lock_trail_underlying_pct_by_vix — a
    {vix_ceiling: trail_pct} map resolved against entry_vix at entry (wider trail
    in high vol, tighter in calm). Falls through to the scalar knob when unset.
  * profit_lock_trail_basis="underlying" — trail the UNDERLYING SPY move instead of
    the option premium (the research's prescription): for a put, exit when SPY
    rallies trail-distance back up off the session low.

Synthetic put contract (monkeypatched into the disk loader) so the logic is
deterministic and disk-free. Mirrors test_timecond_exit.py's harness.

Asserted behaviors:
  1. Default params (no maps, premium basis) == the explicit production premium
     chandelier — byte-for-byte identical fill (the new knobs don't perturb default).
  2. Regime map: low entry-VIX -> tighter trail -> earlier/lower exit; high
     entry-VIX -> wider trail -> rides further. A VIX map produces a strictly
     different exit than a tight scalar when entry_vix selects the wide bucket.
  3. _regime_trail_pct resolves buckets correctly (ascending ceilings, fallthrough).
  4. Underlying basis: a put whose SPY falls then rallies back the trail distance
     exits via the underlying branch (not at 15:50).
  5. Underlying default-off: basis='premium' -> underlying branch never fires.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from lib import simulator_real as sr
from lib.simulator_real import simulate_trade_real, _regime_trail_pct


_DATE = dt.date(2025, 3, 3)  # arbitrary weekday; no real data touched


def _spy_frame(rows_ohlc: list[tuple], start_time=dt.time(9, 30)) -> pd.DataFrame:
    """SPY 5m RTH frame from explicit (open, high, low, close) tuples."""
    rows = []
    t = dt.datetime.combine(_DATE, start_time)
    for (o, h, l, c) in rows_ohlc:
        rows.append({"timestamp_et": pd.Timestamp(t), "open": o, "high": h,
                     "low": l, "close": c, "volume": 1_000_000})
        t += dt.timedelta(minutes=5)
    df = pd.DataFrame(rows)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


def _opt_frame(premiums: list[float], start_time=dt.time(9, 30)) -> pd.DataFrame:
    """Synthetic option frame aligned 1:1 with the SPY timestamps; flat intrabar."""
    rows = []
    t = dt.datetime.combine(_DATE, start_time)
    for p in premiums:
        rows.append({"timestamp_et": pd.Timestamp(t), "open": p, "high": p,
                     "low": p, "close": p, "volume": 5000, "vwap": p, "trade_count": 50})
        t += dt.timedelta(minutes=5)
    df = pd.DataFrame(rows)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


@pytest.fixture
def patch_loader(monkeypatch):
    def _install(opt_df: pd.DataFrame):
        monkeypatch.setattr(sr, "load_contract_bars", lambda symbol: opt_df)
    return _install


def _flat_ribbon(n: int) -> pd.DataFrame:
    return pd.DataFrame({"fast": [600.0] * n, "pivot": [600.0] * n, "slow": [600.0] * n,
                         "stack": ["BEAR"] * n, "spread_cents": [5.0] * n})


def _run(spy_df, ribbon_df, entry_idx, **kwargs):
    """Isolated put trade: rejection_level unreachable, premium-stop disabled so the
    ONLY exits that can fire are the chandelier under test and the 15:50 stop."""
    bar = spy_df.iloc[entry_idx]
    base = dict(
        entry_bar_idx=entry_idx, entry_bar=bar, spy_df=spy_df, ribbon_df=ribbon_df,
        rejection_level=10_000.0, triggers_fired=["t"], side="P", qty=3, setup="UNIT",
        premium_stop_pct=-0.99, strike_offset=0, use_tiered_exits=False,
        entry_slippage=0.0, exit_slippage=0.0,
    )
    base.update(kwargs)
    return simulate_trade_real(**base)


# ── 3. resolver unit (pure) ──────────────────────────────────────────────────
def test_regime_resolver_buckets():
    m = {15: 0.15, 25: 0.30}
    assert _regime_trail_pct(13.0, m, 0.20) == 0.15   # calm -> tight
    assert _regime_trail_pct(20.0, m, 0.20) == 0.30   # elevated -> wide
    assert _regime_trail_pct(40.0, m, 0.20) == 0.20   # above all ceilings -> fallback
    assert _regime_trail_pct(0.0, m, 0.20) == 0.20    # VIX unknown -> fallback
    assert _regime_trail_pct(18.0, None, 0.20) == 0.20  # no map -> fallback
    assert _regime_trail_pct(14.0, {"15": 0.15, "25": 0.30}, 0.20) == 0.15  # str keys ok


# ── 1. default-off equivalence ───────────────────────────────────────────────
def _premium_ramp_then_fade(n: int) -> list[float]:
    """Premium ramps to a peak then fades — exercises the trailing chandelier so a
    default-vs-explicit equivalence is a real (non-vacuous) comparison."""
    out = []
    for i in range(n):
        if i <= 10:
            out.append(1.00 + 0.10 * i)        # 1.00 -> 2.00 by bar 10
        else:
            out.append(max(0.50, 2.00 - 0.08 * (i - 10)))  # fade back down
    return out


def test_default_knobs_match_explicit_premium_chandelier(patch_loader):
    """New regime/underlying knobs at their defaults must NOT change the fill vs the
    explicit production premium chandelier (threshold +5% / offset +10% / trail 20%)."""
    n = 79
    spy = _spy_frame([(600.0, 600.05, 599.95, 600.0)] * n)
    ribbon = _flat_ribbon(n)
    opt = _opt_frame(_premium_ramp_then_fade(n))
    patch_loader(opt)

    chand = dict(profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10,
                 profit_lock_mode="trailing", profit_lock_trail_pct=0.20)
    # A: explicit production chandelier, all NEW knobs left at defaults.
    a = _run(spy, ribbon, entry_idx=2, **chand)
    # B: same, but new knobs explicitly set to their documented defaults (no-op values).
    b = _run(spy, ribbon, entry_idx=2, **chand,
             profit_lock_trail_basis="premium", profit_lock_trail_underlying_pct=0.0,
             profit_lock_trail_pct_by_vix=None, profit_lock_trail_underlying_pct_by_vix=None,
             entry_vix=0.0)
    assert a is not None and b is not None
    assert a.dollar_pnl == b.dollar_pnl
    assert a.runner_exit_time_et == b.runner_exit_time_et
    assert a.exit_reason == b.exit_reason


# ── 2. regime map widens the premium trail ───────────────────────────────────
def _premium_peak_then_fade(n: int) -> list[float]:
    """Sharp ramp to a high peak (bar 8) then a steady fade. With a break-even arm
    (offset 0) the trail %, not the arm floor, governs the runner exit — so the trail
    width difference is unambiguous and deterministic."""
    out = []
    for i in range(n):
        if i <= 8:
            out.append(1.00 + 0.25 * i)                 # 1.00 -> 3.00 by bar 8
        else:
            out.append(max(0.20, 3.00 - 0.15 * (i - 8)))  # fade 0.15/bar
    return out


def test_regime_map_widens_trail_vs_tight_scalar(patch_loader):
    """High entry-VIX selects a WIDE trail bucket -> a winner rides FURTHER through the
    fade (exits later, at a lower locked premium) than under a TIGHT scalar trail.
    Proves the VIX map actually binds and is vol-scaled in the right direction."""
    n = 79
    spy = _spy_frame([(600.0, 600.05, 599.95, 600.0)] * n)
    ribbon = _flat_ribbon(n)
    opt = _opt_frame(_premium_peak_then_fade(n))
    patch_loader(opt)

    # Break-even arm (offset 0) so the TRAIL governs, not the +10% arm floor.
    base = dict(profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.0,
                profit_lock_mode="trailing")
    # Tight scalar 10% trail (locks close to the peak, exits early on the fade).
    tight = _run(spy, ribbon, entry_idx=2, **base, profit_lock_trail_pct=0.10)
    # Regime map: entry_vix=26 -> 35% bucket (much wider); scalar fallback 10%.
    wide = _run(spy, ribbon, entry_idx=2, **base, profit_lock_trail_pct=0.10,
                profit_lock_trail_pct_by_vix={18: 0.10, 30: 0.35}, entry_vix=26.0)
    assert tight is not None and wide is not None
    # Vol-scaled: the wider trail holds the runner LONGER (later exit) and gives back
    # more (lower locked premium) than the tight trail.
    assert wide.runner_exit_time_et > tight.runner_exit_time_et, (
        f"wide trail did not ride longer: tight={tight.runner_exit_time_et} "
        f"wide={wide.runner_exit_time_et}")
    assert wide.runner_exit_premium < tight.runner_exit_premium - 1e-9


def test_regime_map_vix_unknown_uses_scalar(patch_loader):
    """entry_vix<=0 with a map present -> scalar fallback, identical to no-map run."""
    n = 79
    spy = _spy_frame([(600.0, 600.05, 599.95, 600.0)] * n)
    ribbon = _flat_ribbon(n)
    opt = _opt_frame(_premium_ramp_then_fade(n))
    patch_loader(opt)
    base = dict(profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10,
                profit_lock_mode="trailing", profit_lock_trail_pct=0.20)
    no_map = _run(spy, ribbon, entry_idx=2, **base)
    map_unknown_vix = _run(spy, ribbon, entry_idx=2, **base,
                           profit_lock_trail_pct_by_vix={15: 0.10, 30: 0.35}, entry_vix=0.0)
    assert no_map.dollar_pnl == map_unknown_vix.dollar_pnl
    assert no_map.runner_exit_time_et == map_unknown_vix.runner_exit_time_et


# ── 4. underlying-trail fires on SPY retrace ─────────────────────────────────
def test_underlying_trail_exits_on_spy_rally(patch_loader):
    """A put: SPY falls (premium rises, arms the lock), makes a low, then rallies back
    the trail distance -> underlying chandelier exits. Compare to premium basis which
    (with a loose premium trail) would ride further."""
    # SPY: flat at entry, drops to 595 by bar 8 (a 5pt = ~0.83% favorable move on a 600
    # underlying), then rallies. Premium tracks inverse-ish; we just need it ARMED.
    rows = []
    # bars 0..2 flat 600, entry at idx 2 -> entry bar = idx 3
    for _ in range(3):
        rows.append((600.0, 600.10, 599.90, 600.0))
    # bars 3..8 fall to 595 (favorable for a put)
    falls = [599.0, 598.0, 597.0, 596.0, 595.5, 595.0]
    for c in falls:
        rows.append((c + 0.5, c + 0.5, c, c))
    # bars 9..14 rally back up off the 595 low; +3 by bar 12 (0.5% of 600 = 3.0 -> trail)
    rallies = [596.0, 597.0, 598.0, 598.5, 599.0, 599.0]
    for c in rallies:
        rows.append((c - 0.5, c, c - 0.5, c))
    # pad to a full session
    while len(rows) < 79:
        rows.append((599.0, 599.10, 598.90, 599.0))
    spy = _spy_frame(rows)
    ribbon = _flat_ribbon(len(rows))
    # Premium: rises as SPY falls (arm the lock), stays elevated through the rally so the
    # PREMIUM chandelier wouldn't necessarily exit at the same place — isolating the
    # underlying trigger.
    prem = []
    for i in range(len(rows)):
        if i <= 3:
            prem.append(1.00)
        elif i <= 8:
            prem.append(1.00 + 0.15 * (i - 3))   # ramps to ~1.75 at the low
        else:
            prem.append(1.60)                     # stays elevated during rally
    opt = _opt_frame(prem)
    patch_loader(opt)

    # Underlying trail 0.5% of 600 = $3.00 retrace off the low (595 -> 598 triggers).
    u = _run(spy, ribbon, entry_idx=2,
             profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10,
             profit_lock_mode="trailing", profit_lock_trail_basis="underlying",
             profit_lock_trail_underlying_pct=0.005)
    assert u is not None
    # Must exit before the 15:50 stop, via the underlying retrace branch.
    assert u.runner_exit_time_et.time() < dt.time(15, 50), u.runner_exit_time_et
    # The exit bar's SPY high must have reached low + $3 (595 + 3 = 598).
    assert u.runner_exit_time_et.time() <= dt.time(10, 30), \
        f"underlying trail should fire during the rally, got {u.runner_exit_time_et}"


def test_underlying_basis_default_off(patch_loader):
    """basis='premium' (default) -> underlying branch never fires; the same falling-then-
    rallying tape runs to a premium/time exit, NOT the underlying retrace."""
    rows = []
    for _ in range(3):
        rows.append((600.0, 600.10, 599.90, 600.0))
    for c in [599.0, 598.0, 597.0, 596.0, 595.5, 595.0]:
        rows.append((c + 0.5, c + 0.5, c, c))
    for c in [596.0, 597.0, 598.0, 598.5, 599.0, 599.0]:
        rows.append((c - 0.5, c, c - 0.5, c))
    while len(rows) < 79:
        rows.append((599.0, 599.10, 598.90, 599.0))
    spy = _spy_frame(rows)
    ribbon = _flat_ribbon(len(rows))
    prem = []
    for i in range(len(rows)):
        prem.append(1.00 if i <= 3 else (1.00 + 0.15 * (i - 3) if i <= 8 else 1.60))
    opt = _opt_frame(prem)
    patch_loader(opt)
    # Same underlying_pct given, but basis stays premium -> knob inert.
    f = _run(spy, ribbon, entry_idx=2,
             profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10,
             profit_lock_mode="trailing", profit_lock_trail_pct=0.20,
             profit_lock_trail_basis="premium", profit_lock_trail_underlying_pct=0.005)
    assert f is not None
    # With premium basis it must NOT exit at the early underlying-retrace bar (<=10:30);
    # the premium trail / 15:50 governs instead.
    assert f.runner_exit_time_et.time() > dt.time(10, 30), \
        f"premium-basis run exited like the underlying trail at {f.runner_exit_time_et}"
