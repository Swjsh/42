"""
Aggressive OOS Feature Analysis: What separates winners from losers?

Post-Rank35 Aggressive baseline: OOS n=28 pnl=+$3,272
Window: 2026-05-08 to 2026-06-16

Mirrors oos_feature_analysis.py (Safe account) but for the Bold account.
Aggressive differences: VIX bear_threshold=15.0, runner=5x, risk_cap=50%,
midday_trendline_gate=OFF, block_elite_bull ON (15-17.5), block_level_rejection ON.

OOS regime note: 2026-05-08 onward = VIX declining recovery after tariff shock peak.
C22: any IS-trained gate will hit this — work purely on OOS trades.
"""
import datetime as dt
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

IS_START = dt.date(2025, 1, 2)
IS_END   = dt.date(2026, 5, 7)

# Post-Rank35 Aggressive baseline
AGG_BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bear_threshold": 15.0},
)


def sort_key(et):
    if et is None:
        return dt.datetime.min
    if hasattr(et, "tzinfo") and et.tzinfo is not None:
        return et.replace(tzinfo=None)
    return et


def classify_triggers(triggers_fired: list) -> str:
    has_tl  = any("trendline" in str(t) for t in triggers_fired)
    has_lvl = any("level" in str(t) for t in triggers_fired)
    has_rec = any("level_reclaim" in str(t) for t in triggers_fired)
    has_rej = any("level_rejection" in str(t) for t in triggers_fired)
    if has_tl and has_lvl:
        return "conf_tl_lvl"
    if has_tl:
        return "trendline_only"
    if has_rec:
        return "level_reclaim"
    if has_rej:
        return "level_rejection"
    return "other"


def bucket_vix(vix):
    if vix is None:
        return "VIX_unknown"
    if vix < 15.0:
        return "VIX<15"
    if vix < 17.0:
        return "VIX 15-17"
    if vix < 20.0:
        return "VIX 17-20"
    if vix < 25.0:
        return "VIX 20-25"
    return "VIX 25+"


def bucket_time(t):
    if t is None:
        return "unknown"
    if t < dt.time(11, 0):
        return "09:35-11:00"
    if t < dt.time(13, 0):
        return "11:00-13:00"
    return "13:00-15:40"


def get_entry_time(trade):
    et = getattr(trade, "entry_time_et", None)
    if et is None:
        return None
    if hasattr(et, "time"):
        try:
            return et.time()
        except Exception:
            pass
    return None


def print_group(trades, label, extra=""):
    if not trades:
        return
    pnl   = sum(t.dollar_pnl for t in trades)
    wins  = sum(1 for t in trades if t.dollar_pnl > 0)
    wr    = wins / len(trades) * 100
    avg   = pnl / len(trades)
    print(f"  {label}: n={len(trades)} W={wins} L={len(trades)-wins} "
          f"WR={wr:.0f}% pnl={pnl:+,.0f} avg={avg:+.0f}{extra}")


def run():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    print("\nRunning Aggressive baseline (IS + OOS)...")
    is_r  = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **AGG_BASE_KWARGS)
    oos_r = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **AGG_BASE_KWARGS)
    is_trades  = is_r.trades
    oos_trades = sorted(oos_r.trades, key=lambda t: sort_key(getattr(t, "entry_time_et", None)))

    is_pnl  = sum(t.dollar_pnl for t in is_trades)
    oos_pnl = sum(t.dollar_pnl for t in oos_trades)
    print(f"\nAGGRESSIVE BASELINE: IS n={len(is_trades)} pnl={is_pnl:+,.0f} | "
          f"OOS n={len(oos_trades)} pnl={oos_pnl:+,.0f}")

    winners = [t for t in oos_trades if t.dollar_pnl > 0]
    losers  = [t for t in oos_trades if t.dollar_pnl <= 0]
    print(f"\nOOS W={len(winners)} L={len(losers)}\n")

    # ── Per-trade table ─────────────────────────────────────────────────────
    print("=== OOS TRADE TABLE ===")
    print(f"{'Date':<12} {'Side':<5} {'Trigger':<20} {'VIX':>6} {'Entry_T':<10} "
          f"{'$PnL':>8} {'Exit':<30} {'Hold':>5}")
    print("-" * 110)
    for t in oos_trades:
        date_str  = str(sort_key(getattr(t, "entry_time_et", None)))[:10]
        side      = getattr(t, "side", "?")
        triggers  = getattr(t, "triggers_fired", [])
        trig_str  = classify_triggers(triggers)
        raw_trig  = "+".join(str(x) for x in triggers)[:25]
        vix_val   = getattr(t, "entry_vix", None)
        entry_t   = get_entry_time(t)
        pnl       = t.dollar_pnl
        exit_r    = getattr(t, "exit_reason", "?")[:28]
        hold_m    = getattr(t, "hold_minutes", "?")
        vix_str   = f"{vix_val:.1f}" if vix_val else "N/A"
        t_str     = entry_t.strftime("%H:%M") if entry_t else "?"
        print(f"{date_str:<12} {side:<5} {trig_str:<20} {vix_str:>6} {t_str:<10} "
              f"{pnl:>8.0f} {exit_r:<30} {hold_m!s:>5}")
    print()

    # ── Direction ───────────────────────────────────────────────────────────
    print("=== DIRECTION ===")
    bears = [t for t in oos_trades if t.side == "P"]
    bulls = [t for t in oos_trades if t.side == "C"]
    print_group(bears, "BEAR (PUT)")
    print_group(bulls, "BULL (CALL)")

    # ── Trigger category ────────────────────────────────────────────────────
    print("\n=== TRIGGER CATEGORY ===")
    trig_map: dict = defaultdict(list)
    for t in oos_trades:
        trig_map[classify_triggers(getattr(t, "triggers_fired", []))].append(t)
    for cat, tlist in sorted(trig_map.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
        print_group(tlist, cat)

    # ── Winner vs loser trigger breakdown ───────────────────────────────────
    print("\n=== TRIGGER: WINNERS ===")
    wt_map: dict = defaultdict(list)
    for t in winners:
        wt_map[classify_triggers(getattr(t, "triggers_fired", []))].append(t)
    for cat, tlist in sorted(wt_map.items(), key=lambda x: -len(x[1])):
        print_group(tlist, cat)

    print("\n=== TRIGGER: LOSERS ===")
    lt_map: dict = defaultdict(list)
    for t in losers:
        lt_map[classify_triggers(getattr(t, "triggers_fired", []))].append(t)
    for cat, tlist in sorted(lt_map.items(), key=lambda x: -len(x[1])):
        print_group(tlist, cat)

    # ── VIX bucket ──────────────────────────────────────────────────────────
    print("\n=== VIX BUCKET ===")
    vix_map: dict = defaultdict(list)
    for t in oos_trades:
        vix_map[bucket_vix(getattr(t, "entry_vix", None))].append(t)
    for bkt in ["VIX<15", "VIX 15-17", "VIX 17-20", "VIX 20-25", "VIX 25+", "VIX_unknown"]:
        if bkt in vix_map:
            print_group(vix_map[bkt], bkt)

    # ── VIX bucket: winners vs losers ───────────────────────────────────────
    print("\n=== VIX BUCKET: WINNERS ===")
    wv_map: dict = defaultdict(list)
    for t in winners:
        wv_map[bucket_vix(getattr(t, "entry_vix", None))].append(t)
    for bkt in ["VIX<15", "VIX 15-17", "VIX 17-20", "VIX 20-25", "VIX 25+", "VIX_unknown"]:
        if bkt in wv_map:
            print_group(wv_map[bkt], bkt)

    print("\n=== VIX BUCKET: LOSERS ===")
    lv_map: dict = defaultdict(list)
    for t in losers:
        lv_map[bucket_vix(getattr(t, "entry_vix", None))].append(t)
    for bkt in ["VIX<15", "VIX 15-17", "VIX 17-20", "VIX 20-25", "VIX 25+", "VIX_unknown"]:
        if bkt in lv_map:
            print_group(lv_map[bkt], bkt)

    # ── Time bucket ─────────────────────────────────────────────────────────
    print("\n=== TIME OF DAY ===")
    time_map: dict = defaultdict(list)
    for t in oos_trades:
        time_map[bucket_time(get_entry_time(t))].append(t)
    for bkt in ["09:35-11:00", "11:00-13:00", "13:00-15:40", "unknown"]:
        if bkt in time_map:
            print_group(time_map[bkt], bkt)

    # ── Exit reason ─────────────────────────────────────────────────────────
    print("\n=== EXIT REASON ===")
    exit_map: dict = defaultdict(list)
    for t in oos_trades:
        exit_map[str(getattr(t, "exit_reason", "?"))].append(t)
    for reason, tlist in sorted(exit_map.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
        print_group(tlist, reason[:35])

    print("\n=== EXIT REASON: WINNERS ===")
    we_map: dict = defaultdict(list)
    for t in winners:
        we_map[str(getattr(t, "exit_reason", "?"))].append(t)
    for reason, tlist in sorted(we_map.items(), key=lambda x: -len(x[1])):
        print_group(tlist, reason[:35])

    print("\n=== EXIT REASON: LOSERS ===")
    le_map: dict = defaultdict(list)
    for t in losers:
        le_map[str(getattr(t, "exit_reason", "?"))].append(t)
    for reason, tlist in sorted(le_map.items(), key=lambda x: -len(x[1])):
        print_group(tlist, reason[:35])

    # ── Hold time distribution ───────────────────────────────────────────────
    print("\n=== HOLD TIME (MINUTES) ===")
    w_holds = sorted([getattr(t, "hold_minutes", 0) or 0 for t in winners])
    l_holds = sorted([getattr(t, "hold_minutes", 0) or 0 for t in losers])
    if w_holds:
        print(f"  Winners avg={sum(w_holds)/len(w_holds):.0f}m median={w_holds[len(w_holds)//2]}m "
              f"range={w_holds[0]}-{w_holds[-1]}m")
    if l_holds:
        print(f"  Losers  avg={sum(l_holds)/len(l_holds):.0f}m median={l_holds[len(l_holds)//2]}m "
              f"range={l_holds[0]}-{l_holds[-1]}m")

    # ── Level_reclaim vs level_rejection detailed ────────────────────────────
    print("\n=== LEVEL_RECLAIM vs LEVEL_REJECTION (OOS) ===")
    lr_rec = [t for t in oos_trades if any("level_reclaim" in str(x) for x in getattr(t, "triggers_fired", []))]
    lr_rej = [t for t in oos_trades if any("level_rejection" in str(x) for x in getattr(t, "triggers_fired", []))]
    print_group(lr_rec, "level_reclaim (any)")
    print_group(lr_rej, "level_rejection (any)")

    if lr_rec:
        rec_wins = [t for t in lr_rec if t.dollar_pnl > 0]
        rec_loss = [t for t in lr_rec if t.dollar_pnl <= 0]
        avg_w = sum(t.dollar_pnl for t in rec_wins) / max(1, len(rec_wins))
        avg_l = sum(t.dollar_pnl for t in rec_loss) / max(1, len(rec_loss))
        exp   = (len(rec_wins)/len(lr_rec)) * avg_w + (len(rec_loss)/len(lr_rec)) * avg_l
        print(f"    level_reclaim avg_winner={avg_w:+.0f}, avg_loser={avg_l:+.0f}, expectancy={exp:+.0f}/trade")
    if lr_rej:
        rej_wins = [t for t in lr_rej if t.dollar_pnl > 0]
        rej_loss = [t for t in lr_rej if t.dollar_pnl <= 0]
        avg_w = sum(t.dollar_pnl for t in rej_wins) / max(1, len(rej_wins))
        avg_l = sum(t.dollar_pnl for t in rej_loss) / max(1, len(rej_loss))
        exp   = (len(rej_wins)/len(lr_rej)) * avg_w + (len(rej_loss)/len(lr_rej)) * avg_l
        print(f"    level_rejection avg_winner={avg_w:+.0f}, avg_loser={avg_l:+.0f}, expectancy={exp:+.0f}/trade")

    # ── IS vs OOS per-trigger per-trade comparison ───────────────────────────
    print("\n=== IS TRIGGER COMPOSITION (for cross-reference) ===")
    is_trig_map: dict = defaultdict(list)
    for t in is_trades:
        is_trig_map[classify_triggers(getattr(t, "triggers_fired", []))].append(t)
    for cat, tlist in sorted(is_trig_map.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
        print_group(tlist, f"IS {cat}")

    # ── Premium bucket at entry ───────────────────────────────────────────────
    print("\n=== ENTRY PREMIUM BUCKET (OOS) ===")
    def bucket_prem(p):
        if p is None:
            return "?"
        if p < 1.0:
            return "<$1.00"
        if p < 2.0:
            return "$1-2"
        if p < 4.0:
            return "$2-4"
        if p < 7.0:
            return "$4-7"
        return "$7+"

    prem_map: dict = defaultdict(list)
    for t in oos_trades:
        prem_map[bucket_prem(getattr(t, "entry_premium", None))].append(t)
    for bkt in ["<$1.00", "$1-2", "$2-4", "$4-7", "$7+", "?"]:
        if bkt in prem_map:
            print_group(prem_map[bkt], f"entry_prem {bkt}")

    print("\n=== AGGRESSIVE OOS FEATURE ANALYSIS COMPLETE ===")
    print(f"OOS: n={len(oos_trades)} W={len(winners)} L={len(losers)} "
          f"WR={len(winners)/max(1,len(oos_trades))*100:.0f}% pnl={oos_pnl:+,.0f}")
    print(f"IS:  n={len(is_trades)} pnl={is_pnl:+,.0f}")


if __name__ == "__main__":
    run()
