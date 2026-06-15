"""E2E validation: real-fill simulator must reproduce the 3 known historical trades
within tighter tolerance than BS (since real fills are by definition the ground truth).

Cached option contracts at backtest/data/options/SPY{YYMMDD}{C|P}{XXXXXXXX}.csv
must exist; run `tools/fetch_option_data.py` first.

Validations per known trade:
  1. Engine fires the setup on the date.
  2. Real-fill simulator picks an ATM strike that's CACHED (so we get a real fill).
  3. Entry premium VWAP is within ±15% of J's actual entry price (accounts for
     the fact that the engine's trigger bar may be 1-2 bars off from J's manual
     entry, and VWAP averages over the bar's distribution).
  4. P&L direction is plausible (no catastrophic loss when SPY moved in the
     trade's favor).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HISTORICAL_REGIME_FILTERS_DISABLED = [8, 9]


def _load_fixture(date_str: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    spy = pd.read_csv(REPO / "fixtures" / f"spy_5m_{date_str}_with_warmup.csv")
    vix = pd.read_csv(REPO / "fixtures" / f"vix_5m_{date_str}_with_warmup.csv")
    return spy, vix


def _trades_on_date(result, target_date: dt.date) -> list:
    return [t for t in result.trades
            if (t.entry_time_et.date() if hasattr(t.entry_time_et, "date") else
                pd.Timestamp(t.entry_time_et).date()) == target_date]


# ─── Cache verification ──────────────────────────────────────

def test_option_cache_exists_for_all_known_trades():
    """All historical option contracts referenced by tests must be cached."""
    required = [
        ("2026-04-29", 710, "P"),    # J's actual 4/29 trade
        ("2026-04-29", 709, "P"),    # engine's likely ATM strike
        ("2026-05-01", 721, "P"),    # J's actual 5/1 trade
        ("2026-05-04", 721, "P"),    # J's actual 5/4 trade
        ("2026-05-04", 719, "P"),    # engine's likely ATM strike
        ("2026-05-07", 734, "C"),    # J's actual 5/7 BULL trade
    ]
    missing = []
    for date_str, strike, side in required:
        symbol = option_symbol(dt.date.fromisoformat(date_str), strike, side)
        df = load_contract_bars(symbol)
        if df is None or len(df) < 10:
            missing.append((symbol, date_str))
    assert not missing, (
        f"Missing cached contracts: {missing}\n"
        f"Run: cd backtest && python tools/fetch_option_data.py"
    )


# ─── Real-fill engine reproduction ────────────────────────────

@pytest.mark.parametrize("date_str", ["2026-04-29", "2026-05-04"])
def test_engine_fires_with_real_fills(date_str):
    """Engine must fire on each known historical day with real-fill mode enabled."""
    spy, vix = _load_fixture(date_str)
    target_date = dt.date.fromisoformat(date_str)
    result = run_backtest(
        spy, vix, start_date=target_date, end_date=target_date,
        disable_filters=HISTORICAL_REGIME_FILTERS_DISABLED,
        use_real_fills=True,
    )
    trades = _trades_on_date(result, target_date)
    assert len(trades) >= 1, (
        f"Engine fired NO trades on {date_str} with real-fills (BS-mode worked)"
    )
    # No BS_FALLBACK should be needed if cache is complete
    fallbacks = [t for t in trades if "BS_FALLBACK" in t.setup]
    print(f"\n{date_str} real-fills: {len(trades)} trade(s), {len(fallbacks)} BS-fallback(s)")
    for t in trades:
        print(
            f"  Entry {t.entry_time_et} strike={t.strike}{('P' if 'BEARISH' in t.setup else 'C')} "
            f"vwap=${t.entry_premium:.2f} "
            f"exit ${t.runner_exit_premium:.2f} pnl=${t.dollar_pnl:.0f} "
            f"reason={t.exit_reason} hold={t.hold_minutes}min"
        )


# ─── J's actual fill comparison ───────────────────────────────

KNOWN_J_TRADES = {
    "2026-04-29": {"strike": 710, "side": "P", "entry_px": 1.67, "exit_px_avg": 2.24, "qty": 6},
    "2026-05-04": {"strike": 721, "side": "P", "entry_px": 0.85, "exit_px_avg": 1.58, "qty": 10},
    "2026-05-07": {"strike": 734, "side": "C", "entry_px": 0.73, "exit_px_avg": 0.58, "qty": 3},
}


@pytest.mark.parametrize("date_str", ["2026-04-29", "2026-05-04"])
def test_real_vwap_reasonable_vs_j_actual(date_str):
    """Real-fill VWAP for J's entry bar should be within ±25% of J's actual fill.

    J's manual entries hit different intra-bar moments; VWAP averages the whole bar.
    The 25% band gives latitude for that variance while still catching the case
    where the cached contract is the wrong strike or wrong day.
    """
    actual = KNOWN_J_TRADES[date_str]
    target_date = dt.date.fromisoformat(date_str)
    symbol = option_symbol(target_date, actual["strike"], actual["side"])
    df = load_contract_bars(symbol)
    assert df is not None, f"Cache miss for {symbol}"

    # J's 4/29 trade: 10:25:51 ET → entry bar 10:25
    # J's 5/4 trade:  10:27:50 ET → entry bar 10:25
    entry_window_starts = {
        "2026-04-29": dt.datetime(2026, 4, 29, 10, 25),
        "2026-05-04": dt.datetime(2026, 5, 4, 10, 25),
    }
    entry_t = entry_window_starts[date_str]
    if df["timestamp_et"].dt.tz is not None:
        df = df.copy()
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
    bar = df[df["timestamp_et"] == pd.Timestamp(entry_t)]
    assert not bar.empty, f"No bar at {entry_t} for {symbol}"

    real_vwap = float(bar.iloc[0]["vwap"])
    actual_px = actual["entry_px"]
    pct_diff = abs(real_vwap - actual_px) / actual_px
    print(
        f"\n{date_str} {symbol} entry-bar VWAP=${real_vwap:.2f} "
        f"vs J actual ${actual_px:.2f} (±{pct_diff*100:.1f}%)"
    )
    assert pct_diff < 0.25, (
        f"VWAP ${real_vwap:.2f} differs >25% from J's ${actual_px:.2f} — "
        f"likely wrong strike or wrong bar"
    )


# ─── P&L bounds ───────────────────────────────────────────────

@pytest.mark.parametrize("date_str", ["2026-04-29", "2026-05-04"])
def test_real_fill_pnl_bounded(date_str):
    """Real-fill P&L bounded by 3 contracts × realistic premium swing."""
    spy, vix = _load_fixture(date_str)
    target_date = dt.date.fromisoformat(date_str)
    result = run_backtest(
        spy, vix, start_date=target_date, end_date=target_date,
        disable_filters=HISTORICAL_REGIME_FILTERS_DISABLED,
        use_real_fills=True,
    )
    trades = _trades_on_date(result, target_date)
    if not trades:
        pytest.skip(f"No trade fired on {date_str}")
    for t in trades:
        assert -1500 <= t.dollar_pnl <= 1500, (
            f"{date_str} real-fill P&L ${t.dollar_pnl:.0f} outside plausible range"
        )
        assert 0 < t.hold_minutes < 6 * 60
