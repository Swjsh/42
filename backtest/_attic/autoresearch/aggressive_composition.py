"""
Aggressive account composition breakdown: post-TIGHTER_STOP_2 baseline.
IS n=? pnl=? | OOS n=? pnl=?  (re-run needed with corrected -0.07 stop)

Correct production params (2026-06-17, synced with aggressive/params.json):
  - premium_stop_pct_bear=-0.07 (TIGHTER_STOP_2: -0.10->-0.07, WF=0.725, ratified 2026-06-17)
  - block_level_rejection=True (Rank 34, ratified 2026-06-17)
  - block_elite_bull=True, vix_low=15.0, vix_high=17.5 (Rank 35)
  - vix_bear_threshold=15.0 (Aggressive-specific, vs 17.3 Safe)
  - runner_target_premium_pct=5.0 (Aggressive runner is 5x)
  - per_trade_risk_cap_pct=0.50 (Aggressive 50% risk cap)

Produces breakdown by:
- Trigger type (confluence+level_rejection / trendline_only / etc.)
- VIX bucket (intraday VIX at entry)
- Direction (BEAR/BULL)
- Time bucket
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START = dt.date(2025, 1, 2)
IS_END   = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

# Aggressive account base kwargs (post-Rank35 production params, 2026-06-17)
AGG_BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,        # OFF for Aggressive
    premium_stop_pct_bear=-0.07,        # TIGHTER_STOP_2: -0.10->-0.07, ratified 2026-06-17
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,      # Aggressive 5x runner
    time_stop_minutes_before_close=20,  # L110: exit at 15:40
    per_trade_risk_cap_pct=0.50,        # 50% aggressive risk cap
    block_level_rejection=True,         # Rank 34
    block_elite_bull=True,              # Rank 35: ELITE bull block in VIX 15-17.5
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    tp1_premium_pct=0.75,                                                  # C14 fix: must match production (default is 0.30)
    params_overrides={"vix_bear_threshold": 15.0, "vix_bull_max": 30.0},  # Aggressive: bear@VIX>15, bull@VIX<30
)


def bucket_vix(vix):
    if vix is None:
        return "unknown"
    if vix < 17.0:
        return "VIX<17"
    if vix < 20.0:
        return "VIX 17-20"
    if vix < 25.0:
        return "VIX 20-25"
    if vix < 30.0:
        return "VIX 25-30"
    return "VIX 30+"


def bucket_time(t):
    if t is None:
        return "unknown"
    if t < dt.time(11, 0):
        return "09:35-11:00"
    if t < dt.time(13, 0):
        return "11:00-13:00"
    return "13:00-15:40"



def summarize_trades(trades, label):
    if not trades:
        print(f"  {label}: n=0")
        return
    pnl = sum(t.dollar_pnl for t in trades)
    wins = sum(1 for t in trades if t.dollar_pnl > 0)
    wr = wins / len(trades) * 100
    avg = pnl / len(trades)
    print(f"  {label}: n={len(trades)} WR={wr:.0f}% pnl={pnl:+,.0f} avg={avg:+.0f}")


def get_trigger_label(triggers_fired: list) -> str:
    if not triggers_fired:
        return "unknown"
    tset = set(t.split("_")[0] if "_" in t else t for t in triggers_fired)
    tstr = "+".join(sorted(triggers_fired))
    if "confluence" in tstr and "level_rejection" in tstr:
        return "conf+lvl_rej"
    if "confluence" in tstr and "level_reclaim" in tstr:
        return "conf+lvl_rec"
    if "confluence" in tstr:
        return "conf+trendline"
    if "level_rejection" in tstr and "trendline" not in tstr:
        return "lvl_rej_only"
    if "level_reclaim" in tstr and "trendline" not in tstr:
        return "lvl_rec_only"
    if "trendline" in tstr:
        return "trendline_only"
    return tstr[:30]


def run():
    import pandas as pd
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    print("\nRunning Aggressive baseline (IS + OOS)...")
    is_r = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **AGG_BASE_KWARGS)
    oos_r = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **AGG_BASE_KWARGS)

    is_trades = is_r.trades
    oos_trades = oos_r.trades
    is_pnl = sum(t.dollar_pnl for t in is_trades)
    oos_pnl = sum(t.dollar_pnl for t in oos_trades)
    print(f"AGGRESSIVE BASE: IS n={len(is_trades)} pnl={is_pnl:+,.0f} | OOS n={len(oos_trades)} pnl={oos_pnl:+,.0f}")

    # --- Direction breakdown ---
    print("\n=== DIRECTION BREAKDOWN ===")
    for direction, label in [("P", "BEAR (PUT)"), ("C", "BULL (CALL)")]:
        is_d = [t for t in is_trades if t.side == direction]
        oos_d = [t for t in oos_trades if t.side == direction]
        summarize_trades(is_d, f"  IS {label}")
        summarize_trades(oos_d, f" OOS {label}")

    # --- Trigger breakdown ---
    print("\n=== TRIGGER BREAKDOWN (IS) ===")
    trigger_groups: dict = {}
    for t in is_trades:
        trig = get_trigger_label(getattr(t, "triggers_fired", []))
        trigger_groups.setdefault(trig, []).append(t)
    for trig, tlist in sorted(trigger_groups.items(), key=lambda x: sum(t.dollar_pnl for t in x[1])):
        summarize_trades(tlist, trig)

    print("\n=== TRIGGER BREAKDOWN (OOS) ===")
    trigger_groups_oos: dict = {}
    for t in oos_trades:
        trig = get_trigger_label(getattr(t, "triggers_fired", []))
        trigger_groups_oos.setdefault(trig, []).append(t)
    for trig, tlist in sorted(trigger_groups_oos.items(), key=lambda x: sum(t.dollar_pnl for t in x[1])):
        summarize_trades(tlist, trig)

    # --- VIX bucket breakdown ---
    print("\n=== VIX BUCKET BREAKDOWN (IS) ===")
    vix_groups: dict = {}
    for t in is_trades:
        bkt = bucket_vix(getattr(t, "entry_vix", None))
        vix_groups.setdefault(bkt, []).append(t)
    for bkt in ["VIX<17", "VIX 17-20", "VIX 20-25", "VIX 25-30", "VIX 30+", "unknown"]:
        if bkt in vix_groups:
            summarize_trades(vix_groups[bkt], bkt)

    print("\n=== VIX BUCKET BREAKDOWN (OOS) ===")
    vix_groups_oos: dict = {}
    for t in oos_trades:
        bkt = bucket_vix(getattr(t, "entry_vix", None))
        vix_groups_oos.setdefault(bkt, []).append(t)
    for bkt in ["VIX<17", "VIX 17-20", "VIX 20-25", "VIX 25-30", "VIX 30+", "unknown"]:
        if bkt in vix_groups_oos:
            summarize_trades(vix_groups_oos[bkt], bkt)

    # --- Time bucket breakdown ---
    print("\n=== TIME BUCKET BREAKDOWN (IS) ===")
    time_groups: dict = {}
    for t in is_trades:
        entry_ts = getattr(t, "entry_time_et", None)
        if entry_ts:
            try:
                entry_t = entry_ts.time() if hasattr(entry_ts, "time") else None
            except Exception:
                entry_t = None
        else:
            entry_t = None
        bkt = bucket_time(entry_t)
        time_groups.setdefault(bkt, []).append(t)
    for bkt in ["09:35-11:00", "11:00-13:00", "13:00-15:40", "unknown"]:
        if bkt in time_groups:
            summarize_trades(time_groups[bkt], bkt)

    # --- Sub-window IS breakdown ---
    print("\n=== IS SUB-WINDOWS ===")
    sub_windows = [
        ("W1_2025H1", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
        ("W2_2025H2", dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
        ("W3_Q12026", dt.date(2026, 1, 1), dt.date(2026, 3, 31)),
        ("W4_Apr26",  dt.date(2026, 4, 1), dt.date(2026, 5, 7)),
    ]
    for name, ws, we in sub_windows:
        sw_r = run_backtest(spy, vix, start_date=ws, end_date=we, **AGG_BASE_KWARGS)
        sw_pnl = sum(t.dollar_pnl for t in sw_r.trades)
        sw_wr = sum(1 for t in sw_r.trades if t.dollar_pnl > 0) / max(1, len(sw_r.trades)) * 100
        print(f"  {name}: n={len(sw_r.trades)} WR={sw_wr:.0f}% pnl={sw_pnl:+,.0f}")

    print("\nAggressive composition complete.")


if __name__ == "__main__":
    run()
