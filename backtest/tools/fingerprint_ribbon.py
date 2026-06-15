"""Fingerprint the Saty Pivot Ribbon EMA periods from live chart values.

Saty Pivot Ribbon is a TradingView indicator with 5 plot lines:
  Fast EMA, Pivot EMA, Slow EMA, Fast Conviction EMA, Slow Conviction EMA

The exact periods aren't documented uniformly across versions of the indicator.
This script reads the live values captured from the chart (via TradingView MCP)
and finds which EMA periods produce matching values when computed on recent OHLCV.

Output: lib/ribbon_config.json with confirmed periods.

Usage:
    python tools/fingerprint_ribbon.py

The result is a one-time configuration. Re-run only if J changes the indicator settings.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
FIXTURE_BARS = REPO / "fixtures" / "recent_120bars.csv"
FIXTURE_LIVE = REPO / "fixtures" / "live_ribbon_snapshot.json"
OUT_CONFIG = REPO / "lib" / "ribbon_config.json"

TOLERANCE = 0.05  # cents — match if computed EMA is within 5 cents of live value
PERIOD_MIN = 3
PERIOD_MAX = 100


def ema_seeded_with_sma(series: pd.Series, period: int) -> pd.Series:
    """Standard EMA with SMA seed — matches TradingView's ta.ema() behavior.

    For the first `period` bars, returns NaN. At bar `period`, returns SMA of
    bars 1..period. From bar period+1 onward, applies the standard EMA recursion
    EMA_t = alpha * close_t + (1 - alpha) * EMA_{t-1}.
    """
    if len(series) < period:
        return pd.Series([np.nan] * len(series), index=series.index)
    alpha = 2.0 / (period + 1.0)
    out = np.full(len(series), np.nan)
    out[period - 1] = series.iloc[:period].mean()
    for i in range(period, len(series)):
        out[i] = alpha * series.iloc[i] + (1.0 - alpha) * out[i - 1]
    return pd.Series(out, index=series.index)


def fingerprint(closes: pd.Series, live_values: dict[str, float]) -> dict[str, dict]:
    """For each live ribbon line, find the period whose final EMA value matches best."""
    final_emas = {p: ema_seeded_with_sma(closes, p).iloc[-1] for p in range(PERIOD_MIN, PERIOD_MAX + 1)}

    results = {}
    for line_name, target in live_values.items():
        diffs = {p: abs(v - target) for p, v in final_emas.items() if not np.isnan(v)}
        if not diffs:
            results[line_name] = {"period": None, "diff": None, "computed": None, "target": target}
            continue
        best_period = min(diffs, key=diffs.get)
        results[line_name] = {
            "period": int(best_period),
            "diff_cents": float(round(diffs[best_period] * 100, 2)),
            "computed": float(round(final_emas[best_period], 4)),
            "target": float(target),
            "within_tolerance": bool(diffs[best_period] <= TOLERANCE),
        }
    return results


def main() -> int:
    bars = pd.read_csv(FIXTURE_BARS)
    live = json.loads(FIXTURE_LIVE.read_text())

    closes = bars["close"]
    live_values = live["live_ribbon_values"]

    print(f"Fingerprinting against {len(closes)} bars of {live['symbol']} {live['timeframe']}-min")
    print(f"Last close: {closes.iloc[-1]:.2f}")
    print(f"Live ribbon target values:")
    for k, v in live_values.items():
        print(f"  {k}: {v}")
    print()

    matches = fingerprint(closes, live_values)

    print("Best-fit periods:")
    print(f"{'Line':<25} {'Period':>6} {'Computed':>10} {'Target':>10} {'Diff (¢)':>9}  {'OK?':>4}")
    for line, m in matches.items():
        ok = "OK" if m["within_tolerance"] else "FAIL"
        print(
            f"{line:<25} {m['period']:>6} {m['computed']:>10.4f} {m['target']:>10.2f} "
            f"{m['diff_cents']:>9.2f}  {ok:>4}"
        )

    all_ok = all(m["within_tolerance"] for m in matches.values())
    print()
    if all_ok:
        print("All ribbon lines matched within tolerance. Writing ribbon_config.json.")
    else:
        print("WARNING: at least one line did not match within tolerance.")
        print("This means the indicator's algorithm differs from a vanilla close-based EMA")
        print("(possibly Wilder smoothing, hl2 source, or displaced EMA). Investigate before trusting backtest.")

    config = {
        "indicator": "Saty Pivot Ribbon",
        "captured_from_live": live["captured_at"],
        "symbol": live["symbol"],
        "timeframe": live["timeframe"],
        "tolerance_cents": int(TOLERANCE * 100),
        "all_within_tolerance": all_ok,
        "matches": matches,
        "periods": {
            "fast_ema": matches["Fast EMA"]["period"],
            "pivot_ema": matches["Pivot EMA"]["period"],
            "slow_ema": matches["Slow EMA"]["period"],
            "fast_conviction_ema": matches["Fast Conviction EMA"]["period"],
            "slow_conviction_ema": matches["Slow Conviction EMA"]["period"],
        },
        "source": "fingerprinted via fingerprint_ribbon.py against TradingView MCP live values",
        "ema_seed": "sma_then_ema (matches TradingView ta.ema)",
        "price_source": "close",
    }
    OUT_CONFIG.write_text(json.dumps(config, indent=2))
    print(f"Wrote {OUT_CONFIG}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
