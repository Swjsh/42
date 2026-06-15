"""Premarket Low (PML) scan for LIVE_PRICE_FIRST_BAR_TRIGGER.

Background: Stage-2 analysis used PDL/PDH proxy, finding 1 event in 343 days (0.3%).
The 5/15 motivating case used PML (premarket low) — a different level type.

This scan asks: how often does the first RTH bar (09:30-09:35 ET) touch or
break the premarket session low, then RECLAIM it (close above) — creating a
named-level bounce trigger on the very first bar of the session?

Also scans premarket HIGH rejection (first bar breaks PM high then rejects).

Scan method:
  1. Load full 16-month SPY 5m data
  2. For each trading day, compute:
     - premarket_low = min(low) of PM bars (04:00-09:29 ET)
     - premarket_high = max(high) of PM bars (04:00-09:29 ET)
  3. Check first RTH bar (09:30 ET):
     BULL_CASE: first_bar.low <= pml AND first_bar.close > pml (wick below, close above)
     BEAR_CASE: first_bar.high >= pmh AND first_bar.close < pmh (wick above, close below)
  4. For events: trace next 6 bars (30 min) to compute SPY move direction + magnitude
  5. Compare to J anchor days (4/29, 5/01, 5/04, 5/05, 5/06, 5/07)

Output: analysis/backtests/pml-first-bar-scan/results.json
"""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "analysis" / "backtests" / "pml-first-bar-scan"
OUT_JSON = OUT_DIR / "results.json"

# J anchor days for reference
J_ANCHOR_DAYS = {"2026-04-29", "2026-05-01", "2026-05-04",
                 "2026-05-05", "2026-05-06", "2026-05-07", "2026-05-15"}

# Motivation case: 5/15
MOTIVATING_CASE = "2026-05-15"


def _find_spy_csv() -> Path:
    data_dir = ROOT / "backtest" / "data"
    candidates = sorted(data_dir.glob("spy_5m_*.csv"), key=lambda p: p.stat().st_size, reverse=True)
    if not candidates:
        raise FileNotFoundError("No SPY 5m CSV found")
    return candidates[0]


def load_spy(spy_path: Path) -> pd.DataFrame:
    df = pd.read_csv(spy_path)
    df["timestamp_et"] = (
        pd.to_datetime(df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    return df


def _scan_day(date_str: str, df_day: pd.DataFrame, df_all: pd.DataFrame) -> dict | None:
    """Scan a single day for PML/PMH first-bar trigger events.

    df_day: all bars for the date
    df_all: full dataset (for prior context)
    """
    # Premarket bars (04:00-09:29 ET)
    pm_mask = (df_day["timestamp_et"].dt.time >= dt.time(4, 0)) & \
              (df_day["timestamp_et"].dt.time < dt.time(9, 30))
    pm_bars = df_day[pm_mask]

    # RTH bars (09:30+)
    rth_mask = df_day["timestamp_et"].dt.time >= dt.time(9, 30)
    rth_bars = df_day[rth_mask]

    if pm_bars.empty or rth_bars.empty:
        return None

    pml = float(pm_bars["low"].min())
    pmh = float(pm_bars["high"].max())

    # First RTH bar
    first_rth = rth_bars.iloc[0]
    first_low = float(first_rth["low"])
    first_high = float(first_rth["high"])
    first_close = float(first_rth["close"])

    events = []

    # BULL case: first bar wicks to/below PML, closes above (reclaim)
    if first_low <= pml and first_close > pml:
        # Measure subsequent 6-bar (30-min) move
        next_bars = rth_bars.iloc[1:7]  # bars 2-7
        if not next_bars.empty:
            next_close = float(next_bars.iloc[-1]["close"])
            move_30min = next_close - first_close
            events.append({
                "type": "BULL_PML_RECLAIM",
                "pml": round(pml, 2),
                "first_bar_low": round(first_low, 2),
                "first_bar_close": round(first_close, 2),
                "wick_below_pml": round(pml - first_low, 2),
                "close_above_pml": round(first_close - pml, 2),
                "move_30min": round(move_30min, 2),
                "win": move_30min > 0,  # bull = up is win
            })

    # BEAR case: first bar wicks to/above PMH, closes below (rejection)
    if first_high >= pmh and first_close < pmh:
        next_bars = rth_bars.iloc[1:7]
        if not next_bars.empty:
            next_close = float(next_bars.iloc[-1]["close"])
            move_30min = next_close - first_close
            events.append({
                "type": "BEAR_PMH_REJECTION",
                "pmh": round(pmh, 2),
                "first_bar_high": round(first_high, 2),
                "first_bar_close": round(first_close, 2),
                "wick_above_pmh": round(first_high - pmh, 2),
                "close_below_pmh": round(pmh - first_close, 2),
                "move_30min": round(move_30min, 2),
                "win": move_30min < 0,  # bear = down is win
            })

    if not events:
        return None

    return {
        "date": date_str,
        "pml": round(pml, 2),
        "pmh": round(pmh, 2),
        "pm_bars_count": len(pm_bars),
        "j_anchor_day": date_str in J_ANCHOR_DAYS,
        "motivating_case": date_str == MOTIVATING_CASE,
        "events": events,
    }


def main() -> None:
    spy_path = _find_spy_csv()
    print(f"Loading SPY 5m from {spy_path.name} ...")
    spy = load_spy(spy_path)
    print(f"  {len(spy)} bars, {spy['timestamp_et'].iloc[0].date()} to {spy['timestamp_et'].iloc[-1].date()}")

    # Group by date
    spy["date"] = spy["timestamp_et"].dt.date
    all_dates = sorted(spy["date"].unique())
    print(f"  {len(all_dates)} trading days")

    events_by_date = []
    no_pm_data = 0
    bull_events = []
    bear_events = []

    for d in all_dates:
        df_day = spy[spy["date"] == d].copy()
        result = _scan_day(str(d), df_day, spy)
        if result is None:
            if not df_day[df_day["timestamp_et"].dt.time < dt.time(9, 30)].empty:
                pass
            else:
                no_pm_data += 1
            continue
        events_by_date.append(result)
        for ev in result["events"]:
            ev["date"] = result["date"]
            ev["j_anchor_day"] = result.get("j_anchor_day", False)
            ev["motivating_case"] = result.get("motivating_case", False)
            if ev["type"] == "BULL_PML_RECLAIM":
                bull_events.append(ev)
            else:
                bear_events.append(ev)

    print(f"\nDays with events: {len(events_by_date)} / {len(all_dates)} ({len(events_by_date)/len(all_dates)*100:.1f}%)")
    print(f"  No PM data days: {no_pm_data}")
    print(f"  BULL_PML_RECLAIM events: {len(bull_events)}")
    print(f"  BEAR_PMH_REJECTION events: {len(bear_events)}")

    # BULL summary
    if bull_events:
        bull_wins = [e for e in bull_events if e["win"]]
        bull_wr = len(bull_wins) / len(bull_events) * 100
        avg_move = sum(e["move_30min"] for e in bull_events) / len(bull_events)
        print(f"\n=== BULL_PML_RECLAIM (N={len(bull_events)}) ===")
        print(f"  WR: {bull_wr:.1f}% ({len(bull_wins)} wins)")
        print(f"  Avg 30-min move: {avg_move:+.2f}")
        print(f"  J anchor day hits: {sum(1 for e in bull_events if e['j_anchor_day'])}")
        print(f"  5/15 motivating case: {sum(1 for e in bull_events if e['motivating_case'])}")
        if bull_events:
            print("  Sample events:")
            for e in sorted(bull_events, key=lambda x: abs(x["move_30min"]), reverse=True)[:5]:
                anchor = " [J-ANCHOR]" if e["j_anchor_day"] else ""
                motiv = " [5/15-MOTIV]" if e["motivating_case"] else ""
                print(f"    {e['date']}: pml={e['pml']:.2f} wick={e['wick_below_pml']:.2f} move={e['move_30min']:+.2f}{anchor}{motiv}")

    # BEAR summary
    if bear_events:
        bear_wins = [e for e in bear_events if e["win"]]
        bear_wr = len(bear_wins) / len(bear_events) * 100
        avg_move = sum(e["move_30min"] for e in bear_events) / len(bear_events)
        print(f"\n=== BEAR_PMH_REJECTION (N={len(bear_events)}) ===")
        print(f"  WR: {bear_wr:.1f}% ({len(bear_wins)} wins)")
        print(f"  Avg 30-min move: {avg_move:+.2f}")
        print(f"  J anchor day hits: {sum(1 for e in bear_events if e['j_anchor_day'])}")
        print(f"  Sample events:")
        for e in sorted(bear_events, key=lambda x: abs(x["move_30min"]), reverse=True)[:5]:
            anchor = " [J-ANCHOR]" if e["j_anchor_day"] else ""
            print(f"    {e['date']}: pmh={e['pmh']:.2f} wick={e['wick_above_pmh']:.2f} move={e['move_30min']:+.2f}{anchor}")

    # Save
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "generated_at": dt.datetime.now().isoformat(),
        "description": "PML/PMH first-bar trigger scan across 16-month SPY history",
        "spy_file": str(spy_path.name),
        "total_days": len(all_dates),
        "days_with_events": len(events_by_date),
        "days_with_events_pct": round(len(events_by_date) / len(all_dates) * 100, 1),
        "bull_pml_reclaim": {
            "n": len(bull_events),
            "wr_pct": round(len([e for e in bull_events if e["win"]]) / max(len(bull_events), 1) * 100, 1),
            "avg_30min_move": round(sum(e["move_30min"] for e in bull_events) / max(len(bull_events), 1), 2),
            "j_anchor_hits": sum(1 for e in bull_events if e["j_anchor_day"]),
            "motivating_case_hit": any(e["motivating_case"] for e in bull_events),
        },
        "bear_pmh_rejection": {
            "n": len(bear_events),
            "wr_pct": round(len([e for e in bear_events if e["win"]]) / max(len(bear_events), 1) * 100, 1),
            "avg_30min_move": round(sum(e["move_30min"] for e in bear_events) / max(len(bear_events), 1), 2),
            "j_anchor_hits": sum(1 for e in bear_events if e["j_anchor_day"]),
        },
        "events": events_by_date,
    }
    OUT_JSON.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nResults -> {OUT_JSON}")


if __name__ == "__main__":
    main()
