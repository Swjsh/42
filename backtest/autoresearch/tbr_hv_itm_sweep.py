"""TBR_HIGH_VOL ITM-options rescue sweep.

ATM version (strike_offset=0) real-fills FAIL: OOS WR=44.9%, exp=-$6.44.
Root cause: delta≈0.5 + theta decay + -15% premium stop misfires (48% of exits).

This sweep tests whether ITM options (higher delta) can preserve the SPY-space
edge (WF WR=70%) in real option premium space.

Strike offsets tested:
  0  = ATM (delta≈0.50) — baseline, already FAIL
 -1  = ITM-1 (delta≈0.65, ~$1 ITM)
 -2  = ITM-2 (delta≈0.75, ~$2 ITM)

Premium stop widths tested (each strike):
  -0.15  = tight (current baseline)
  -0.25  = moderate
  -0.35  = wide

Pass gate (same as baseline): N >= 10 AND WR >= 55%.
Window: OOS only (2025-10-01 to 2026-05-22) to avoid IS look-ahead.

CLI::

    python -m autoresearch.tbr_hv_itm_sweep
    python -m autoresearch.tbr_hv_itm_sweep --out analysis/recommendations/tbr_hv_itm_sweep.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from dataclasses import replace
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

import pandas as pd

OOS_START = dt.date(2025, 10, 1)
OOS_END   = dt.date(2026, 5, 22)

# Strike offsets to test: 0=ATM, negative=ITM (calls: lower strike = more delta)
STRIKE_OFFSETS = [0, -1, -2]
# Premium stop widths to test
STOP_PREMIUMS  = [-0.15, -0.25, -0.35]

BASE_COMBO = ShotgunCombo(
    vol_ratio_threshold=1.5,
    strike_offset=0,
    tp_premium_pct=0.75,
    stop_premium_pct=-0.15,
    time_stop_min=12,
    chandelier_arm_pct=0.25,
    qty=3,
    tp1_qty_fraction=1.0,
)


def _run_one(
    spy_full: pd.DataFrame,
    combo: ShotgunCombo,
    start: dt.date,
    end: dt.date,
    detect,
    verbose: bool = False,
) -> list[dict]:
    """Run TBR-high-vol real-fills for a single combo config."""
    no_trade_before = dt.time(combo.no_trade_before_hour, combo.no_trade_before_min)
    no_trade_after  = dt.time(combo.no_trade_after_hour, combo.no_trade_after_min)

    trading_dates = sorted(spy_full["timestamp_et"].dt.date.unique())
    trading_dates = [d for d in trading_dates if start <= d <= end]

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
        ribbon_stub = {
            "fast": float("nan"), "pivot": float("nan"), "slow": float("nan"),
            "spread_cents": 0.0, "stack": "NEUTRAL",
        }
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

            if signal.get("name") != "TRENDLINE_BREAK_RETEST":
                continue
            vr = signal.get("vol_ratio", 0.0) or 0.0
            if vr < combo.vol_ratio_threshold:
                continue

            signal["direction"] = "short" if signal.get("direction") in ("bearish", "short", "put") else "long"
            signal["bar_timestamp_et"] = day_bars.iloc[i]["timestamp_et"]
            signal["entry_price"] = float(day_bars.iloc[i]["close"])

            trade = _simulate_trade_real(signal, bar_idx, combined, combo, opra_cache)
            if trade is None:
                continue

            trades.append({
                "date": str(date_et),
                "entry_time": str(trade.entry_time_et),
                "direction": trade.direction,
                "strike": trade.strike,
                "entry_premium": round(float(trade.entry_premium), 4),
                "exit_premium": round(float(trade.exit_premium), 4),
                "pnl": round(float(trade.dollar_pnl), 2),
                "exit_reason": trade.exit_reason,
                "vol_ratio": round(float(vr), 3),
            })

            exit_time = trade.exit_time_et
            for j in range(bar_idx, len(combined)):
                if combined.iloc[j]["timestamp_et"] >= exit_time:
                    last_exit_idx = j
                    break

    return trades


def _summarise(trades: list[dict], label: str) -> dict:
    if not trades:
        return {"label": label, "n": 0, "wr": 0.0, "exp": 0.0, "total_pnl": 0.0,
                "passes": False, "exits": {}}
    pnls    = [t["pnl"] for t in trades]
    winners = [p for p in pnls if p > 0]
    losers  = [p for p in pnls if p <= 0]
    total   = sum(pnls)
    wr      = len(winners) / len(pnls)
    exp     = total / len(pnls)
    passes  = len(trades) >= 10 and wr >= 0.55
    outcomes = Counter(t["exit_reason"] for t in trades)

    gate = "PASS" if passes else "FAIL"
    print(f"  {label:<32}  N={len(trades):>4}  WR={wr:.1%}  exp=${exp:+7.2f}  "
          f"total=${total:+8.2f}  [{gate}]")

    return {
        "label": label,
        "n": len(trades),
        "wr": round(wr, 4),
        "exp": round(exp, 2),
        "total_pnl": round(total, 2),
        "avg_win":  round(sum(winners)/max(1, len(winners)), 2),
        "avg_loss": round(sum(losers) /max(1, len(losers)),  2),
        "passes": passes,
        "exits": dict(outcomes),
        "pct_stop": round(outcomes.get("STOP", 0) / max(1, len(trades)) * 100, 1),
        "pct_target": round(outcomes.get("TARGET_LEVEL", 0) / max(1, len(trades)) * 100, 1),
    }


def run_sweep(
    start: dt.date = OOS_START,
    end:   dt.date = OOS_END,
    out_path: Path | None = None,
) -> list[dict]:
    print(f"Loading SPY bars {start} to {end}...")
    spy_full, _ = load_data(start, end)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"], utc=False)
    try:
        if spy_full["timestamp_et"].dt.tz is not None:
            spy_full["timestamp_et"] = (
                spy_full["timestamp_et"]
                .dt.tz_convert("America/New_York")
                .dt.tz_localize(None)
            )
    except Exception:
        pass

    detect = _import_detector()
    print(f"  Detector loaded. Running {len(STRIKE_OFFSETS) * len(STOP_PREMIUMS)} combos...\n")

    print(f"  {'Combo':>32}  {'N':>5}  {'WR':>6}  {'Exp/obs':>9}  {'Total P&L':>10}  Gate")
    print("  " + "-" * 80)

    results: list[dict] = []
    passers: list[dict] = []

    for offset in STRIKE_OFFSETS:
        for stop in STOP_PREMIUMS:
            combo = replace(BASE_COMBO, strike_offset=offset, stop_premium_pct=stop)
            offset_label = "ATM" if offset == 0 else f"ITM-{abs(offset)}"
            label = f"offset={offset}({offset_label}) stop={stop:.0%}"
            trades = _run_one(spy_full, combo, start, end, detect)
            row = _summarise(trades, label)
            row["strike_offset"] = offset
            row["stop_premium_pct"] = stop
            results.append(row)
            if row["passes"]:
                passers.append(row)

    print()
    if passers:
        best = max(passers, key=lambda r: r["exp"])
        print(f"RESCUE FOUND: {len(passers)} combo(s) pass gate.")
        print(f"Best by exp/obs: {best['label']}  WR={best['wr']:.1%}  exp=${best['exp']:+.2f}")
    else:
        best_any = max(results, key=lambda r: r["wr"])
        print(f"NO RESCUE FOUND. Best WR: {best_any['label']} WR={best_any['wr']:.1%} (gate=55%)")

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(
                {"run_date": dt.date.today().isoformat(), "start": str(start), "end": str(end),
                 "results": results, "passers": passers},
                f, indent=2, default=str,
            )
        print(f"\nResults written to {out_path}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="TBR high-vol ITM-options rescue sweep")
    parser.add_argument("--start", default=str(OOS_START))
    parser.add_argument("--end",   default=str(OOS_END))
    parser.add_argument("--out",   default=None, help="Write JSON to this path")
    args = parser.parse_args()

    results = run_sweep(
        start=dt.date.fromisoformat(args.start),
        end=dt.date.fromisoformat(args.end),
        out_path=Path(args.out) if args.out else None,
    )

    passers = [r for r in results if r["passes"]]
    return 0 if passers else 1


if __name__ == "__main__":
    raise SystemExit(main())
