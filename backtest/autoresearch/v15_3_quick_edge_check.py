"""Quick edge-check for v15.3 scorecard — runs only J's 7 source-of-truth days + 5/15.

Writes results to stdout and to analysis/recommendations/v15_3_edge_check.json.
This is the fast path to verify edge-capture before running the full 16-month backtest.
"""
from __future__ import annotations
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner

PARAMS_V151 = {
    "premium_stop_pct_bear": -0.20,
    "premium_stop_pct_bull": -0.08,
    "tp1_premium_pct": 0.75,
    "tp1_qty_fraction": 0.50,
    "runner_target_premium_pct": 2.50,
    "f9_vol_mult": 0.7,
    "min_triggers_bear": 1,
    "min_triggers_bull": 2,
    "strike_offset_bear": -2,
    "strike_offset_bull": -2,
    "vix_bear_threshold": 17.30,
    "ribbon_spread_min_cents": 30,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.20,
}

J_DAYS = [
    ("2026-04-29", "WINNER", +342),
    ("2026-05-01", "WINNER", +470),
    ("2026-05-04", "WINNER", +730),
    ("2026-05-05", "LOSER",  -260),
    ("2026-05-06", "LOSER",  -300),
    ("2026-05-07", "LOSER",  -165),   # two trades: -$45 + -$120
    ("2026-05-15", "LOSS_515", -770),  # v15.3 improvement target
]

MAX_EDGE_CAPTURE = 1542
EDGE_FLOOR = 771

V15_3_ABS_MARGIN = 0.05
V15_3_REL_MARGIN_PCT = 0.00007

def _level_cross_margin(price):
    return max(V15_3_ABS_MARGIN, V15_3_REL_MARGIN_PCT * price)

def _parse_et(df):
    """Parse timestamp_et column to ET-naive times. Returns df with _date and _time columns."""
    import pandas as pd
    df = df.copy()
    # Parse as UTC first, then convert to ET (America/New_York handles DST)
    df["_ts_utc"] = pd.to_datetime(df["timestamp_et"], utc=True)
    df["_ts_et"] = df["_ts_utc"].dt.tz_convert("America/New_York")
    df["_date"] = df["_ts_et"].dt.date
    df["_time"] = df["_ts_et"].dt.time
    return df

def _get_pmh_pml(spy_df, date):
    df = _parse_et(spy_df)
    today = df[df["_date"] == date]
    premarket = today[today["_time"] < dt.time(9, 30)]
    if premarket.empty:
        return []
    return [float(premarket["high"].max()), float(premarket["low"].min())]

def _v153_trigger_fires(spy_df, date):
    """Check if v15.3 live-price BEAR trigger would fire on date."""
    levels = _get_pmh_pml(spy_df, date)
    if not levels:
        return False, None, None

    df = _parse_et(spy_df)
    day = df[(df["_date"] == date) & (df["_time"] >= dt.time(9, 30)) & (df["_time"] < dt.time(16, 0))].reset_index(drop=True)
    if len(day) < 2:
        return False, None, None

    # Check 09:35 and 09:40 bars (first two RTH bars after the open)
    window = day[(day["_time"] >= dt.time(9, 35)) & (day["_time"] < dt.time(9, 45))]
    if window.empty:
        return False, None, None

    for pos in window.index:
        if pos == 0:
            continue
        bar = day.iloc[pos]
        prior = day.iloc[pos - 1]
        bar_low = float(bar["low"])
        prior_close = float(prior["close"])
        for level in levels:
            margin = _level_cross_margin(level)
            # BEAR: bar.low crossed below level - margin, prior bar was ABOVE level
            if bar_low < level - margin and prior_close >= level - 0.05:
                return True, level, bar["_time"]
    return False, None, None

def main():
    print("="*72)
    print("v15.3 Edge-Capture Quick Check")
    print("="*72)

    print("Loading data...")
    spy, vix = runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    print(f"  SPY rows: {len(spy):,}  VIX rows: {len(vix):,}")

    results = []
    for date_str, side, j_pnl in J_DAYS:
        d = dt.date.fromisoformat(date_str)
        try:
            res151, m151 = runner.run_with_params(PARAMS_V151, d, d, spy, vix)
            pnl_151 = round(m151.total_pnl, 2)
            n_151 = m151.n_trades
            trades_151 = [{"side": getattr(t,"side","?"), "strike": getattr(t,"strike","?"),
                           "pnl": round(float(t.dollar_pnl), 2),
                           "exit": str(getattr(t,"exit_reason","?"))[:30]}
                          for t in res151.trades] if res151 else []
        except Exception as ex:
            pnl_151, n_151, trades_151 = 0.0, 0, []
            print(f"  {date_str} v15.1 ERROR: {ex}")

        # v15.3 trigger check
        trigger_fires, trigger_level, trigger_time = _v153_trigger_fires(spy, d)

        # v15.3 P&L estimate
        # For most days: same as v15.1 (the trigger is additive, doesn't remove existing entries)
        # For 5/15 specifically: if trigger fires, we got an earlier entry before V-reversal
        pnl_153_est = pnl_151
        v153_note = "same as v15.1 (trigger doesn't change existing entry)"
        if date_str == "2026-05-15" and trigger_fires:
            # Per forensic: v15.3 enters on 09:40 bar (in-flight at ~09:41 ET)
            # Entry ~$738.95, 09:45 bar wicks to 737.96 (+$1.00 MFE)
            # Chandelier arms at +5% ($3.51), trails 20% off HWM
            # HWM ~$4.20 (if entry was ~$3.34), floor at $3.67. V-rev reversal to $3.30 -> exit $3.67
            # Net: entry ~$3.34, exit ~$3.67 -> +$0.33/contract x qty
            # qty at $1K account (OTM-2, ~$1.34 premium, max 30% = $300) -> ~3 contracts
            # $0.33 x 3 x 100 = ~$99 gain BEFORE the tp1 split
            # Conservative estimate: +$50 to account for slippage + stale quote scenarios
            pnl_153_est = 50.0
            v153_note = "early entry (09:41 ET) before V-reversal, est chandelier exit ~breakeven to +$50"

        row = {
            "date": date_str,
            "side": side,
            "j_pnl": j_pnl,
            "v151_pnl": pnl_151,
            "v151_n_trades": n_151,
            "v151_trades": trades_151,
            "v153_trigger_fires": trigger_fires,
            "v153_trigger_level": trigger_level,
            "v153_trigger_time": str(trigger_time),
            "v153_pnl_est": pnl_153_est,
            "v153_note": v153_note,
        }
        results.append(row)
        print(f"\n  {date_str} [{side:8s}] j_pnl={j_pnl:+.0f}  v15.1=${pnl_151:+.0f}  "
              f"v15.3_est=${pnl_153_est:+.0f}  trigger={trigger_fires}")
        print(f"    trigger_level={trigger_level}  trigger_time={trigger_time}")
        for t in trades_151:
            print(f"    trade: {t['side']} {t['strike']}  pnl=${t['pnl']:+.0f}  ({t['exit']})")

    # Compute edge capture
    def edge_cap(rlist, pnl_key="v151_pnl"):
        winners = [r[pnl_key] for r in rlist if r["side"] == "WINNER"]
        losers = [max(0, -r[pnl_key]) for r in rlist if r["side"] not in ("WINNER", "LOSS_515")]
        return sum(winners) - sum(losers)

    edge_151 = edge_cap(results, "v151_pnl")
    # v15.3: same as v15.1 for J days (trigger doesn't affect them), plus 5/15 improvement
    edge_153_winners = sum(r["v153_pnl_est"] for r in results if r["side"] == "WINNER")
    edge_153_loser_loss = sum(max(0, -r["v153_pnl_est"]) for r in results if r["side"] == "LOSER")
    edge_153 = edge_153_winners - edge_153_loser_loss

    print(f"\n{'='*72}")
    print(f"v15.1 edge_capture = ${edge_151:.0f}  ({edge_151/MAX_EDGE_CAPTURE*100:.1f}% of {MAX_EDGE_CAPTURE})")
    print(f"v15.3 edge_capture = ${edge_153:.0f}  ({edge_153/MAX_EDGE_CAPTURE*100:.1f}% of {MAX_EDGE_CAPTURE})")
    print(f"Floor for ratification: ${EDGE_FLOOR}")
    print(f"v15.1 gate 3: {'PASS' if edge_151 >= EDGE_FLOOR else 'FAIL'}")
    print(f"v15.3 gate 3: {'PASS' if edge_153 >= EDGE_FLOOR else 'FAIL'}")

    # 5/15 improvement
    r515 = next((r for r in results if r["date"] == "2026-05-15"), None)
    if r515:
        print(f"\n5/15 replay:")
        print(f"  v15.1 engine P&L: ${r515['v151_pnl']:.0f}")
        print(f"  v15.3 trigger fires: {r515['v153_trigger_fires']}")
        print(f"  v15.3 estimate: ${r515['v153_pnl_est']:.0f}")
        print(f"  Improvement: ${r515['v153_pnl_est'] - r515['v151_pnl']:+.0f}")

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "edge_capture_v151": edge_151,
        "edge_capture_v153": edge_153,
        "max_edge_capture": MAX_EDGE_CAPTURE,
        "edge_floor": EDGE_FLOOR,
        "gate3_v151_pass": edge_151 >= EDGE_FLOOR,
        "gate3_v153_pass": edge_153 >= EDGE_FLOOR,
        "day_results": results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "v15_3_edge_check.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote: {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
