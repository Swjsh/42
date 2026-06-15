"""Smoke tests for detect_db_morning_low_vol_setup gate logic.

Tests:
  T1: VIX >= 20 -> None (VIX gate rejects HIGH_VOL)
  T2: time outside morning window (afternoon) -> None
  T3: time before morning start (pre-9:35) -> None
  T4: pure base pattern (conf=0.45) in morning window + all gates pass -> WatcherSignal
  T5: named level near pattern -> None (NOT_NEAR_NAMED gate rejects)
  T6: cooldown prevents re-fire within 30 min
  T7: textbook pattern (conf=0.75) in morning window -> WatcherSignal (NO conf ceiling)

Key difference vs db_base_quiet: morning watcher accepts ALL confidence levels
(no ceiling). The discriminator is the MORNING window (09:35-11:30) + LOW_VOL (VIX<20).

Run: python backtest/autoresearch/t_db_morning_low_vol_smoke.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from backtest.lib.filters import BarContext  # noqa: E402
import backtest.lib.watchers.double_bottom_morning_low_vol_watcher as _watcher_mod  # noqa: E402
from backtest.lib.watchers.double_bottom_morning_low_vol_watcher import (  # noqa: E402
    detect_db_morning_low_vol_setup,
    ENTRY_TIME_START,
    ENTRY_TIME_END,
    VIX_LOW_VOL_CEILING,
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


def _base_ctx(
    prior_bars: pd.DataFrame,
    *,
    timestamp_et: dt.datetime,
    vix_now: float = 15.0,
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
        ribbon_now=None,
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


# Pure base double-bottom bars (conf=0.45) — identical to t_db_base_quiet_smoke.py.
# 11 rows: 4 neutral background + 7 pattern bars. len(bars) >= 10 gate satisfied.
# All v2 factors False → conf = 0.45 (base only, no enhancements).
_BASE_BARS = _make_prior_bars([
    (100.60, 100.70, 100.50, 100.60, 50_000),   # idx 0: background (padding)
    (100.60, 100.65, 100.55, 100.62, 50_000),   # idx 1: background (padding)
    (100.62, 100.68, 100.58, 100.64, 50_000),   # idx 2: background (padding)
    (100.64, 100.70, 100.60, 100.65, 50_000),   # idx 3: background (padding)
    (100.50, 100.60, 100.40, 100.50, 50_000),   # idx 4: background
    (100.50, 100.50, 100.00, 100.10, 50_000),   # idx 5: FIRST LOCAL LOW (100.00)
    (100.10, 100.40, 100.20, 100.35, 50_000),   # idx 6: rising (high=100.40)
    (100.35, 100.45, 100.30, 100.40, 50_000),   # idx 7: NECKLINE BAR (high=100.45)
    (100.40, 100.42, 100.12, 100.20, 50_000),   # idx 8: SECOND LOCAL LOW (100.12)
    (100.20, 100.42, 100.20, 100.40, 50_000),   # idx 9: rising
    (100.40, 100.48, 100.40, 100.46, 50_000),   # idx 10: BREAKOUT (close=100.46 > neckline=100.45)
])

# Textbook T1 bars (conf=0.75) from v22_chart_patterns.py T1, padded to 11 rows
# so the watcher's `len(bars) < 10` gate passes (same padding fix as _BASE_BARS).
# The morning watcher has NO confidence ceiling — this should FIRE (unlike db_base_quiet).
_T1_BARS = _make_prior_bars([
    (100.5, 100.6, 100.4, 100.5, 50_000),    # idx 0: background (padding)
    (100.5, 100.6, 100.4, 100.5, 50_000),    # idx 1: background (padding)
    (100.5, 100.6, 100.4, 100.5, 50_000),    # idx 2: background (padding)
    (100.5, 100.6, 100.4, 100.5, 50_000),    # idx 3: background (padding)
    (100.5, 100.6, 100.4, 100.5, 50_000),    # idx 4: background (padding)
    (100.5, 100.8, 100.2, 100.4, 50_000),    # idx 5: pre-pattern context
    (100.4, 100.6, 100.0, 100.1, 50_000),    # idx 6: FIRST LOCAL LOW (100.0)
    (100.1, 102.0, 100.1, 101.8, 50_000),    # idx 7: neckline area (high=102.0)
    (101.8, 102.0, 101.5, 101.7, 50_000),    # idx 8: intermediate
    (101.7, 101.9, 100.05, 100.2, 50_000),   # idx 9: SECOND LOCAL LOW (100.05)
    (100.2, 102.3, 100.2, 102.2, 50_000),    # idx 10: BREAKOUT (close=102.2 >> neckline=102.0)
])

_MORNING_TIME  = dt.datetime(2026, 5, 20, 10, 0, 0)   # 10:00 ET — in morning window
_AFTERNOON_TIME = dt.datetime(2026, 5, 20, 14, 0, 0)  # 14:00 ET — outside morning window
_PRE_RTH_TIME  = dt.datetime(2026, 5, 20, 9, 20, 0)   # 09:20 ET — before RTH start
_LATE_MORNING  = dt.datetime(2026, 5, 20, 11, 25, 0)  # 11:25 ET — still in morning window


def run_tests() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0

    _watcher_mod._last_signal_time = None

    print("\n=== T1: VIX >= 20 -> None ===")
    ctx = _base_ctx(_BASE_BARS, timestamp_et=_MORNING_TIME, vix_now=VIX_LOW_VOL_CEILING + 5.0)
    result = detect_db_morning_low_vol_setup(ctx)
    _result("VIX_gate_rejects_HIGH_VOL", result is None,
            f"vix={VIX_LOW_VOL_CEILING + 5.0}, expected None got {type(result).__name__}")

    print("\n=== T2: afternoon time (14:00) -> None ===")
    _watcher_mod._last_signal_time = None
    ctx = _base_ctx(_BASE_BARS, timestamp_et=_AFTERNOON_TIME)
    result = detect_db_morning_low_vol_setup(ctx)
    _result("afternoon_rejected", result is None,
            f"time=14:00 > ENTRY_TIME_END={ENTRY_TIME_END}, expected None")

    print("\n=== T3: pre-RTH time (09:20) -> None ===")
    _watcher_mod._last_signal_time = None
    ctx = _base_ctx(_BASE_BARS, timestamp_et=_PRE_RTH_TIME)
    result = detect_db_morning_low_vol_setup(ctx)
    _result("pre_rth_rejected", result is None,
            f"time=09:20 < ENTRY_TIME_START={ENTRY_TIME_START}, expected None")

    print("\n=== T4: pure base pattern (conf=0.45) in morning + all gates pass -> WatcherSignal ===")
    _watcher_mod._last_signal_time = None
    ctx = _base_ctx(_BASE_BARS, timestamp_et=_MORNING_TIME)
    result = detect_db_morning_low_vol_setup(ctx)
    if result is not None:
        conf_score = result.metadata.get("confidence_score", -1)
        _result("base_pattern_fires_in_morning", True,
                f"direction={result.direction}, conf_score={conf_score:.2f}")
        _result("direction_is_long", result.direction == "long")
        _result("setup_name_correct",
                result.setup_name == "DOUBLE_BOTTOM_MORNING_LOW_VOL",
                f"got {result.setup_name}")
    else:
        try:
            from crypto.lib.chart_patterns import double_bottom_detector, Bar
            base_raw = [
                Bar(open_time=dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=5*i),
                    open=float(_BASE_BARS.iloc[i]["open"]), high=float(_BASE_BARS.iloc[i]["high"]),
                    low=float(_BASE_BARS.iloc[i]["low"]), close=float(_BASE_BARS.iloc[i]["close"]),
                    volume=float(_BASE_BARS.iloc[i]["volume"]), granularity_seconds=300, source="test")
                for i in range(len(_BASE_BARS))
            ]
            base_hit = double_bottom_detector(base_raw)
            diag = f"detector_hit={base_hit is not None}"
            if base_hit:
                diag += f" conf={base_hit.confidence:.3f}"
        except ImportError:
            diag = "crypto.lib not available"
        _result("base_pattern_fires_in_morning", False, f"watcher returned None -- {diag}")

    print("\n=== T5: named level near pattern -> None ===")
    _watcher_mod._last_signal_time = None
    ctx = _base_ctx(_BASE_BARS, timestamp_et=_MORNING_TIME, levels_active=[100.45])
    result = detect_db_morning_low_vol_setup(ctx)
    _result("NOT_NEAR_NAMED_gate", result is None,
            f"level=100.45 at neckline -> expected None, got {type(result).__name__}")

    print("\n=== T6: cooldown prevents re-fire within 30 min ===")
    _watcher_mod._last_signal_time = None
    ctx1 = _base_ctx(_BASE_BARS, timestamp_et=_MORNING_TIME)
    r1 = detect_db_morning_low_vol_setup(ctx1)
    if r1 is not None:
        ctx2 = _base_ctx(_BASE_BARS, timestamp_et=_MORNING_TIME)
        r2 = detect_db_morning_low_vol_setup(ctx2)
        _result("cooldown_blocks_immediate_re_fire", r2 is None,
                f"same timestamp -> {type(r2).__name__}")
    else:
        _result("cooldown_SKIP", True, "base pattern didn't fire — cooldown test skipped")

    print("\n=== T7: textbook pattern (conf=0.75) in morning window -> WatcherSignal (NO ceiling) ===")
    _watcher_mod._last_signal_time = None
    ctx = _base_ctx(_T1_BARS, timestamp_et=_MORNING_TIME)
    result_t1 = detect_db_morning_low_vol_setup(ctx)
    # Morning watcher accepts ALL confidence including 0.75 (no conf ceiling like db_base_quiet)
    if result_t1 is not None:
        conf_score_t1 = result_t1.metadata.get("confidence_score", -1)
        _result("textbook_fires_in_morning_NO_CEILING", True,
                f"conf_score={conf_score_t1:.2f} >= 0.60 and watcher still fired (correct — no ceiling)")
    else:
        try:
            from crypto.lib.chart_patterns import double_bottom_detector, Bar
            t1_raw = [
                Bar(open_time=dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=5*i),
                    open=float(_T1_BARS.iloc[i]["open"]), high=float(_T1_BARS.iloc[i]["high"]),
                    low=float(_T1_BARS.iloc[i]["low"]), close=float(_T1_BARS.iloc[i]["close"]),
                    volume=float(_T1_BARS.iloc[i]["volume"]), granularity_seconds=300, source="test")
                for i in range(len(_T1_BARS))
            ]
            t1_hit = double_bottom_detector(t1_raw)
            diag = f"detector_hit={t1_hit is not None}"
            if t1_hit:
                diag += f" conf={t1_hit.confidence:.3f}"
        except ImportError:
            diag = "crypto.lib not available"
        _result("textbook_fires_in_morning_NO_CEILING", False,
                f"watcher returned None for conf>=0.60 pattern -- {diag}")

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
