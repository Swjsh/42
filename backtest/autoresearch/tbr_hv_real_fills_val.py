"""TBR_HIGH_VOL real-fills validation.

Runs SHOTGUN_SCALPER detector restricted to TRENDLINE_BREAK_RETEST tier
with vol_ratio >= 1.5× on the OOS window (2025-10-01 to 2026-05-24),
using actual OPRA option fills instead of SPY-price simulation.

This provides the "real-fills validation" gate required for TBR_HIGH_VOL
promotion (gate 3 in strategy/candidates/2026-05-24-tbr-high-vol-discovery.md).

Pass criteria (per discovery doc):
  - N_fills >= 10
  - WR >= 55%

CLI::

    python -m autoresearch.tbr_hv_real_fills_val
    python -m autoresearch.tbr_hv_real_fills_val --start 2025-10-01 --end 2026-05-24
    python -m autoresearch.tbr_hv_real_fills_val --start 2025-01-01 --full   # full IS+OOS
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch.shotgun_scalper_grinder import (
    ShotgunCombo,
    _build_auto_levels,
    _import_detector,
    _simulate_trade_real,
)
from autoresearch.runner import load_data


# Default combo — single-exit, ATM, tight premium stop, 12-min time-stop.
# Matches the TBR-high-vol WF analysis defaults.
DEFAULT_COMBO = ShotgunCombo(
    vol_ratio_threshold=1.5,   # only TBR-high-vol signals
    strike_offset=0,           # ATM
    tp_premium_pct=0.75,       # +75% premium target
    stop_premium_pct=-0.15,    # −15% premium stop
    time_stop_min=12,
    chandelier_arm_pct=0.25,
    qty=3,
    tp1_qty_fraction=1.0,
)

OOS_START = dt.date(2025, 10, 1)
OOS_END   = dt.date(2026, 5, 22)  # Data boundary: SPY CSV available through 2026-05-22


def _run_tbr_hv_real_fills(
    start: dt.date,
    end: dt.date,
    combo: ShotgunCombo = DEFAULT_COMBO,
    verbose: bool = True,
) -> list[dict]:
    """Run TBR-high-vol real-fills across [start, end].

    Returns a list of trade result dicts (one per matched trade).
    """
    import pandas as pd

    detect = _import_detector()

    if verbose:
        print(f"Loading SPY bars {start} to {end}...")
    spy_full, _vix = load_data(start, end)

    # Normalise timestamp: ensure datetimelike, then strip tz so dt accessor works
    import pandas as pd
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"], utc=False)
    try:
        if spy_full["timestamp_et"].dt.tz is not None:
            spy_full["timestamp_et"] = spy_full["timestamp_et"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    except Exception:
        pass

    no_trade_before = dt.time(combo.no_trade_before_hour, combo.no_trade_before_min)
    no_trade_after  = dt.time(combo.no_trade_after_hour, combo.no_trade_after_min)

    trading_dates = sorted(spy_full["timestamp_et"].dt.date.unique())
    trading_dates = [d for d in trading_dates if start <= d <= end]

    if verbose:
        print(f"  {len(trading_dates)} trading days to scan.")

    opra_cache: dict = {}
    trades: list[dict] = []

    for date_et in trading_dates:
        day_bars = spy_full[
            (spy_full["timestamp_et"].dt.date == date_et)
            & (spy_full["timestamp_et"].dt.time >= no_trade_before)
            & (spy_full["timestamp_et"].dt.time < no_trade_after)
        ].reset_index(drop=True)
        if day_bars.empty:
            continue

        first_ts = day_bars["timestamp_et"].iloc[0]
        pre_bars = spy_full[spy_full["timestamp_et"] < first_ts].tail(60).reset_index(drop=True)
        combined = pd.concat([pre_bars, day_bars], ignore_index=True)
        day_offset = len(pre_bars)

        levels = _build_auto_levels(spy_full, date_et, pre_bars)
        ribbon_stub = {"fast": float("nan"), "pivot": float("nan"), "slow": float("nan"),
                       "spread_cents": 0.0, "stack": "NEUTRAL"}

        last_exit_idx = -1

        for i in range(len(day_bars)):
            bar_idx = day_offset + i
            if bar_idx <= last_exit_idx:
                continue
            try:
                signal = detect(
                    today_bars=day_bars,
                    today_bar_idx=i,
                    levels=levels,
                    ribbon=ribbon_stub,
                    vix=17.0,
                    htf_15m_stack=None,
                )
            except Exception:
                continue
            if signal is None:
                continue

            # TBR-ONLY filter: skip non-TBR tiers (LRL, OPEN_REJECTION)
            if signal.get("name") != "TRENDLINE_BREAK_RETEST":
                continue

            # Vol-ratio gate
            vr = signal.get("vol_ratio", 0.0) or 0.0
            if vr < combo.vol_ratio_threshold:
                continue

            # Schema normalisation for _simulate_trade_real
            signal["direction"] = "short" if signal.get("direction") in ("bearish", "short", "put") else "long"
            signal["bar_timestamp_et"] = day_bars.iloc[i]["timestamp_et"]
            signal["entry_price"] = float(day_bars.iloc[i]["close"])

            trade = _simulate_trade_real(signal, bar_idx, combined, combo, opra_cache)
            if trade is None:
                continue

            trades.append({
                "date": str(date_et),
                "entry_time": str(trade.entry_time_et),
                "exit_time": str(trade.exit_time_et),
                "direction": trade.direction,
                "strike": trade.strike,
                "entry_premium": round(float(trade.entry_premium), 4),
                "exit_premium": round(float(trade.exit_premium), 4),
                "pnl": round(float(trade.dollar_pnl), 2),
                "exit_reason": trade.exit_reason,
                "vol_ratio": round(float(vr), 3),
            })

            # Block re-entry until exit
            exit_time = trade.exit_time_et
            for j in range(bar_idx, len(combined)):
                if combined.iloc[j]["timestamp_et"] >= exit_time:
                    last_exit_idx = j
                    break

    return trades


def _report(trades: list[dict], label: str) -> dict:
    """Print summary stats and return summary dict."""
    if not trades:
        print(f"\n{label}: 0 trades — no fills.")
        return {"n": 0}

    pnls = [t["pnl"] for t in trades]
    winners = [p for p in pnls if p > 0]
    losers  = [p for p in pnls if p <= 0]
    total = sum(pnls)
    wr = len(winners) / len(pnls)
    exp = total / len(pnls)
    outcomes = Counter(t["exit_reason"] for t in trades)

    # Pass/fail gate
    passes = len(trades) >= 10 and wr >= 0.55

    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"  N={len(trades)}  WR={wr:.1%}  exp=${exp:+.2f}  total=${total:+.2f}")
    print(f"  avg_win=${sum(winners)/max(1,len(winners)):+.2f}  avg_loss=${sum(losers)/max(1,len(losers)):+.2f}")
    print(f"  exits: {dict(outcomes)}")
    gate_label = "PASS" if passes else "FAIL"
    print(f"  Gate (N>=10, WR>=55%): {gate_label}")
    print()

    # Per-quarter breakdown
    qpnl: dict = defaultdict(float)
    qn: dict = defaultdict(int)
    for t in trades:
        d = dt.date.fromisoformat(t["date"])
        q = f"{d.year}-Q{(d.month-1)//3+1}"
        qpnl[q] += t["pnl"]
        qn[q] += 1
    for q in sorted(qpnl):
        print(f"  {q}: n={qn[q]}  P&L=${qpnl[q]:+.2f}  exp=${qpnl[q]/qn[q]:+.2f}")

    return {
        "n": len(trades),
        "wr": round(wr, 4),
        "exp": round(exp, 2),
        "total_pnl": round(total, 2),
        "passes": passes,
        "exits": dict(outcomes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="TBR high-vol real-fills validation")
    parser.add_argument("--start",         default=str(OOS_START))
    parser.add_argument("--end",           default=str(OOS_END))
    parser.add_argument("--full",          action="store_true", help="Run IS+OOS (2025-01-01 to data boundary)")
    parser.add_argument("--out",           default=None,  help="Write JSON summary to this path")
    parser.add_argument("--strike-offset", type=int,   default=0,    help="Strike offset vs ATM (0=ATM, -1=ITM-1, -2=ITM-2)")
    parser.add_argument("--stop",          type=float, default=-0.15, help="Premium stop pct (e.g. -0.35 for -35%%)")
    args = parser.parse_args()

    start = dt.date(2025, 1, 1) if args.full else dt.date.fromisoformat(args.start)
    end   = OOS_END if args.full else dt.date.fromisoformat(args.end)

    from dataclasses import replace
    combo = replace(DEFAULT_COMBO, strike_offset=args.strike_offset, stop_premium_pct=args.stop)

    offset_label = "ATM" if args.strike_offset == 0 else f"ITM-{abs(args.strike_offset)}"
    label = f"TBR_HIGH_VOL real-fills  {start} to {end}  ({offset_label} stop={args.stop:.0%})"

    trades = _run_tbr_hv_real_fills(start, end, combo=combo)
    summary = _report(trades, label)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump({"summary": summary, "trades": trades}, f, indent=2, default=str)
        print(f"\nOutput written to {out_path}")

    return 0 if summary.get("passes", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
