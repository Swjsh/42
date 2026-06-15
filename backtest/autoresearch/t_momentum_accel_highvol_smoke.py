"""Smoke tests for detect_momentum_accel_highvol_setup gate logic.

Tests:
  T1: VIX < 20 -> None (LOW_VOL gate rejects — watcher wants HIGH_VOL)
  T2: VIX >= 20, momentum fires, ribbon MISALIGNED -> None (aligned gate)
  T3: VIX >= 20, momentum fires, BULL ribbon -> WatcherSignal (bullish)
  T4: VIX >= 20, momentum fires, BEAR ribbon -> WatcherSignal (bearish)
  T5: no momentum pattern -> None
  T6: cooldown prevents re-fire within 45 min
  T7: ribbon is None -> None (no ribbon data guard)

Run: python backtest/autoresearch/t_momentum_accel_highvol_smoke.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from backtest.lib.filters import BarContext  # noqa: E402
from backtest.lib.ribbon import RibbonState  # noqa: E402
import backtest.lib.watchers.momentum_acceleration_highvol_watcher as _watcher_mod  # noqa: E402
from backtest.lib.watchers.momentum_acceleration_highvol_watcher import (  # noqa: E402
    detect_momentum_accel_highvol_setup,
    VIX_HIGH_VOL_FLOOR,
)

_PASS = 0
_FAIL = 0


def _result(name: str, ok: bool, note: str = "") -> None:
    global _PASS, _FAIL
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {note}" if note else ""))
    if ok:
        _PASS += 1
    else:
        _FAIL += 1


def _make_prior_bars(bars_data: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(bars_data, columns=["open", "high", "low", "close", "volume"])


def _ribbon(stack: str, spread: float = 40.0) -> RibbonState:
    return RibbonState(fast=100.1, pivot=100.0, slow=99.9, stack=stack, spread_cents=spread)


def _base_ctx(
    prior_bars: pd.DataFrame,
    *,
    timestamp_et: dt.datetime,
    vix_now: float = 22.0,
    ribbon_now: RibbonState | None = None,
    levels_active: list[float] | None = None,
) -> BarContext:
    if levels_active is None:
        levels_active = []
    trigger_bar = prior_bars.iloc[-1]
    return BarContext(
        bar_idx=len(prior_bars) - 1,
        timestamp_et=timestamp_et,
        bar=trigger_bar,
        prior_bars=prior_bars,
        ribbon_now=ribbon_now,
        ribbon_history=[],
        vix_now=vix_now,
        vix_prior=vix_now,
        vol_baseline_20=50_000.0,
        range_baseline_20=0.40,
        levels_active=levels_active,
        multi_day_levels=[],
        htf_15m_stack=None,
        level_states={},
    )


# ── Bar designs ───────────────────────────────────────────────────────────────
#
# The momentum_acceleration detector requires:
#   1. len(bars) >= lookback + 2 = 12 (watcher uses _WINDOW_BARS=20 tail)
#   2. latest_range >= 2× prior-10 avg range
#   3. body >= 60% of range (decisive)
#   4. volume >= 2× prior-10 avg volume
#
# Design: 20 bars total — 19 background bars + 1 acceleration bar.
# Background: range=0.20, volume=40,000.
# Accel (bullish): open=100.00, high=100.70, low=99.90, close=100.65, vol=120,000
#   range=0.80 (4× 0.20 avg ✓ ≥ 2×)
#   body=|100.65-100.00|=0.65, fill=0.65/0.80=81% ✓ ≥ 60%
#   vol=120,000 (3× ✓ ≥ 2×)
#   bias=bullish (close > open)
# Accel (bearish): open=100.70, high=100.80, low=100.00, close=100.05, vol=120,000
#   range=0.80 (4× ✓), body=0.65, fill=81% ✓, vol=3× ✓, bias=bearish (close < open)
_BG = (100.00, 100.10, 99.90, 100.05, 40_000)   # background bar (range=0.20, vol=40K)

_BULL_BARS = _make_prior_bars([_BG] * 19 + [
    (100.00, 100.70, 99.90, 100.65, 120_000),   # BULL accel: range=0.80 >> avg=0.20, body=81%
])

_BEAR_BARS = _make_prior_bars([_BG] * 19 + [
    (100.70, 100.80, 100.00, 100.05, 120_000),  # BEAR accel: range=0.80 >> avg=0.20, body=81%
])

# Flat bars — no acceleration (all equal, detector won't fire)
_FLAT_BARS = _make_prior_bars([_BG] * 20)

_RTH_TIME = dt.datetime(2026, 5, 20, 11, 0, 0)


def run_tests() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0

    _watcher_mod._last_signal_time = None

    # First, verify the momentum detector actually fires on our bars (diagnostic)
    try:
        from crypto.lib.chart_patterns import momentum_acceleration, Bar
        def _to_bars(df: pd.DataFrame) -> list[Bar]:
            result = []
            for i, row in df.iterrows():
                result.append(Bar(
                    open_time=dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=5*i),
                    open=float(row["open"]), high=float(row["high"]),
                    low=float(row["low"]), close=float(row["close"]),
                    volume=int(row["volume"]), granularity_seconds=300, source="test"))
            return result
        bull_hit = momentum_acceleration(_to_bars(_BULL_BARS))
        bear_hit = momentum_acceleration(_to_bars(_BEAR_BARS))
        flat_hit = momentum_acceleration(_to_bars(_FLAT_BARS))
        print(f"[DIAG] Bull bars: detector={'FIRES bias='+bull_hit.bias if bull_hit else 'None'}")
        print(f"[DIAG] Bear bars: detector={'FIRES bias='+bear_hit.bias if bear_hit else 'None'}")
        print(f"[DIAG] Flat bars: detector={'FIRES' if flat_hit else 'None (expected)'}")
        if not (bull_hit and bull_hit.bias == "bullish"):
            print("[WARN] Bull bars did not trigger detector — test results may be misleading")
        if not (bear_hit and bear_hit.bias == "bearish"):
            print("[WARN] Bear bars did not trigger detector — test results may be misleading")
    except ImportError:
        print("[DIAG] crypto.lib not available — skipping detector pre-check")

    print("\n=== T1: VIX < 20 -> None (LOW_VOL rejected, watcher needs HIGH_VOL) ===")
    _watcher_mod._last_signal_time = None
    ctx = _base_ctx(_BULL_BARS, timestamp_et=_RTH_TIME, vix_now=15.0,
                    ribbon_now=_ribbon("BULL"))
    result = detect_momentum_accel_highvol_setup(ctx)
    _result("low_vol_rejected", result is None,
            f"vix=15.0 < floor={VIX_HIGH_VOL_FLOOR}, expected None got {type(result).__name__}")

    print("\n=== T2: VIX >= 20, momentum fires, ribbon MISALIGNED -> None ===")
    _watcher_mod._last_signal_time = None
    # Bullish momentum hit but BEAR ribbon — misaligned
    ctx = _base_ctx(_BULL_BARS, timestamp_et=_RTH_TIME, vix_now=22.0,
                    ribbon_now=_ribbon("BEAR"))
    result = detect_momentum_accel_highvol_setup(ctx)
    _result("misaligned_ribbon_rejected", result is None,
            f"bullish hit + BEAR ribbon -> expected None, got {type(result).__name__}")

    print("\n=== T3: VIX >= 20, BULL momentum + BULL ribbon -> WatcherSignal ===")
    _watcher_mod._last_signal_time = None
    ctx = _base_ctx(_BULL_BARS, timestamp_et=_RTH_TIME, vix_now=22.0,
                    ribbon_now=_ribbon("BULL"))
    result = detect_momentum_accel_highvol_setup(ctx)
    if result is not None:
        _result("bull_signal_fires", True,
                f"direction={result.direction}, confidence={result.confidence}")
        _result("direction_is_long", result.direction == "long")
        _result("setup_name_correct",
                result.setup_name == "MOMENTUM_ACCELERATION_HIGHVOL",
                f"got {result.setup_name}")
        _result("stop_below_entry",
                result.stop_price < result.entry_price,
                f"stop={result.stop_price:.2f} entry={result.entry_price:.2f}")
    else:
        _result("bull_signal_fires", False, "watcher returned None — check detector pre-check above")

    print("\n=== T4: VIX >= 20, BEAR momentum + BEAR ribbon -> WatcherSignal ===")
    _watcher_mod._last_signal_time = None
    ctx = _base_ctx(_BEAR_BARS, timestamp_et=_RTH_TIME, vix_now=22.0,
                    ribbon_now=_ribbon("BEAR"))
    result = detect_momentum_accel_highvol_setup(ctx)
    if result is not None:
        _result("bear_signal_fires", True,
                f"direction={result.direction}, confidence={result.confidence}")
        _result("direction_is_short", result.direction == "short")
        _result("stop_above_entry",
                result.stop_price > result.entry_price,
                f"stop={result.stop_price:.2f} entry={result.entry_price:.2f}")
    else:
        _result("bear_signal_fires", False, "watcher returned None — check detector pre-check above")

    print("\n=== T5: no momentum pattern (flat bars) -> None ===")
    _watcher_mod._last_signal_time = None
    ctx = _base_ctx(_FLAT_BARS, timestamp_et=_RTH_TIME, vix_now=22.0,
                    ribbon_now=_ribbon("BULL"))
    result = detect_momentum_accel_highvol_setup(ctx)
    _result("flat_pattern_no_signal", result is None,
            f"no acceleration in flat bars, expected None got {type(result).__name__}")

    print("\n=== T6: cooldown prevents re-fire within 45 min ===")
    _watcher_mod._last_signal_time = None
    ctx1 = _base_ctx(_BULL_BARS, timestamp_et=_RTH_TIME, vix_now=22.0,
                     ribbon_now=_ribbon("BULL"))
    r1 = detect_momentum_accel_highvol_setup(ctx1)
    if r1 is not None:
        ctx2 = _base_ctx(_BULL_BARS, timestamp_et=_RTH_TIME, vix_now=22.0,
                         ribbon_now=_ribbon("BULL"))
        r2 = detect_momentum_accel_highvol_setup(ctx2)
        _result("cooldown_blocks_immediate_re_fire", r2 is None,
                f"same timestamp -> {type(r2).__name__}")
    else:
        _result("cooldown_SKIP", True, "bull pattern didn't fire — cooldown test skipped")

    print("\n=== T7: ribbon is None -> None (no ribbon data guard) ===")
    _watcher_mod._last_signal_time = None
    ctx = _base_ctx(_BULL_BARS, timestamp_et=_RTH_TIME, vix_now=22.0,
                    ribbon_now=None)
    result = detect_momentum_accel_highvol_setup(ctx)
    _result("no_ribbon_returns_none", result is None,
            f"ribbon_now=None -> expected None, got {type(result).__name__}")

    print(f"\n{'='*60}")
    print(f"TOTAL: {_PASS} PASS / {_FAIL} FAIL")
    if _FAIL:
        print("RESULT: FAIL")
    else:
        print("RESULT: PASS")
    return _FAIL


if __name__ == "__main__":
    failures = run_tests()
    sys.exit(failures)
