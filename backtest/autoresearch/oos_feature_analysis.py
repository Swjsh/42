"""
OOS Feature Analysis: What separates the 10 winners from the 11 losers?

Post-Rank35 Safe baseline: OOS n=21 pnl=+$3,728
Window: 2026-05-08 to 2026-06-16

Extracts all per-trade features and computes winner vs loser distributions
to find discriminating features NOT tainted by the C22 IS regime flip.

C22 background: IS period = VIX-escalating (tariff shock era).
OOS period = VIX-declining recovery. Any IS-trained gate hits C22.
This analysis works PURELY on OOS trades to find stable discriminators.
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

# Post-Rank35 Safe baseline
BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)


def classify_triggers(triggers_fired: list) -> str:
    """Classify trigger combination into a named category."""
    ts = set(str(t).split("_")[0] for t in triggers_fired)
    raw = set(triggers_fired)
    has_tl = any("trendline" in str(t) for t in triggers_fired)
    has_lvl = any("level" in str(t) for t in triggers_fired)
    has_conf = has_tl and has_lvl
    if has_conf:
        return "conf_tl_lvl"
    if has_tl:
        return "trendline_only"
    if has_lvl:
        return "level_only"
    return "other"


def entry_session(entry_time: dt.datetime) -> str:
    if entry_time is None:
        return "unknown"
    h = entry_time.hour
    m = entry_time.minute
    t = h * 60 + m
    if t < 10 * 60:
        return "morning"        # 09:35-09:59
    if t < 11 * 60:
        return "mid_morning"    # 10:00-10:59
    if t < 13 * 60:
        return "midday"         # 11:00-12:59
    if t < 14 * 60:
        return "afternoon"      # 13:00-13:59
    return "late"               # 14:00+


def vix_bucket(vix: float) -> str:
    if vix < 17.0:
        return "VIX_lt17"
    if vix < 20.0:
        return "VIX_17_20"
    if vix < 25.0:
        return "VIX_20_25"
    if vix < 30.0:
        return "VIX_25_30"
    return "VIX_30plus"


def premium_bucket(prem: float) -> str:
    if prem < 0.50:
        return "under_50c"
    if prem < 1.00:
        return "50c_1d"
    if prem < 2.00:
        return "1d_2d"
    if prem < 3.00:
        return "2d_3d"
    return "3d_plus"


def mfe_mae_ratio(t) -> float:
    mae = abs(getattr(t, "max_adverse_premium", 0) or 0)
    mfe = getattr(t, "max_favorable_premium", 0) or 0
    if mae < 0.001:
        return 10.0  # never went adverse
    return mfe / mae


def compute_stats(values: list) -> dict:
    if not values:
        return {"n": 0, "mean": 0, "median": 0, "p25": 0, "p75": 0}
    import statistics
    s = sorted(values)
    n = len(s)
    return {
        "n": n,
        "mean": statistics.mean(s),
        "median": statistics.median(s),
        "p25": s[n // 4],
        "p75": s[min(3 * n // 4, n - 1)],
    }


def pct_in_group(items: list, group_set: set) -> float:
    if not items:
        return 0.0
    return 100.0 * sum(1 for x in items if x in group_set) / len(items)


def print_feature_split(feature_name: str, winners: list, losers: list, n_thresh: int = 2):
    """Print categorical feature distribution for winners vs losers."""
    all_cats = sorted(set(winners) | set(losers))
    if not all_cats:
        return
    n_w = max(1, len(winners))
    n_l = max(1, len(losers))
    header = f"  {feature_name:<30} {'Winners':>12} {'Losers':>12}"
    print(header)
    for cat in all_cats:
        w_cnt = winners.count(cat)
        l_cnt = losers.count(cat)
        w_pct = 100.0 * w_cnt / n_w
        l_pct = 100.0 * l_cnt / n_l
        edge = w_pct - l_pct
        flag = " <<<<" if abs(edge) >= 20 else ""
        print(f"    {cat:<28} {w_cnt:>3} ({w_pct:>4.0f}%)   {l_cnt:>3} ({l_pct:>4.0f}%){flag}")


def run():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    print(f"\nRunning OOS backtest ({OOS_START} to {OOS_END})...")
    result = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **BASE_KWARGS)
    trades = result.trades
    total_pnl = sum(t.dollar_pnl for t in trades)
    print(f"OOS: n={len(trades)} total_pnl={total_pnl:+,.0f}")

    winners = [t for t in trades if t.dollar_pnl > 0]
    losers  = [t for t in trades if t.dollar_pnl <= 0]
    print(f"Winners: {len(winners)} | Losers: {len(losers)}")
    print(f"Winner avg P&L: {sum(t.dollar_pnl for t in winners) / max(1,len(winners)):+.0f}")
    print(f"Loser avg P&L:  {sum(t.dollar_pnl for t in losers)  / max(1,len(losers)):+.0f}")

    print("\n" + "=" * 70)
    print("ALL OOS TRADES (sorted by entry time)")
    print("=" * 70)
    print(f"{'Date':>12} {'Time':>6} {'VIX':>6} {'Prem':>5} {'Trigger':>18} {'Exit':>26} {'pnl':>8} {'MFE/MAE':>7}")
    print("-" * 95)
    def sort_key(t):
        et = t.entry_time_et
        if hasattr(et, 'tzinfo') and et.tzinfo is not None:
            return et.replace(tzinfo=None)
        return et

    for t in sorted(trades, key=sort_key):
        entry_dt = t.entry_time_et
        date_str = entry_dt.strftime("%Y-%m-%d")
        time_str = entry_dt.strftime("%H:%M")
        trig = classify_triggers(getattr(t, "triggers_fired", []))
        exit_r = str(getattr(t, "exit_reason", "?") or "?")
        # Shorten exit reason
        exit_r = exit_r.replace("ExitReason.", "").replace("TP1_THEN_RUNNER_", "TP1>")
        exit_r = exit_r.replace("EXIT_ALL_", "STOP_")
        pnl = t.dollar_pnl
        ratio = mfe_mae_ratio(t)
        prem = getattr(t, "entry_premium", 0) or 0
        vix_v = getattr(t, "entry_vix", 0) or 0
        marker = " W" if pnl > 0 else " L"
        print(f"  {date_str} {time_str:>6} {vix_v:>5.1f} {prem:>5.2f} {trig:>18} {exit_r:>26} {pnl:>+8.0f} {ratio:>6.1f}x{marker}")

    print("\n" + "=" * 70)
    print("FEATURE COMPARISON: WINNERS vs LOSERS")
    print("=" * 70)

    # === TRIGGER TYPE ===
    w_trig = [classify_triggers(getattr(t, "triggers_fired", [])) for t in winners]
    l_trig = [classify_triggers(getattr(t, "triggers_fired", [])) for t in losers]
    print("\n[1] TRIGGER TYPE")
    print_feature_split("trigger", w_trig, l_trig)

    # === VIX BUCKET ===
    w_vix = [vix_bucket(getattr(t, "entry_vix", 0) or 0) for t in winners]
    l_vix = [vix_bucket(getattr(t, "entry_vix", 0) or 0) for t in losers]
    print("\n[2] VIX AT ENTRY")
    print_feature_split("vix_bucket", w_vix, l_vix)
    w_vix_vals = [getattr(t, "entry_vix", 0) or 0 for t in winners]
    l_vix_vals = [getattr(t, "entry_vix", 0) or 0 for t in losers]
    ws = compute_stats(w_vix_vals)
    ls = compute_stats(l_vix_vals)
    print(f"  Winners: mean={ws['mean']:.1f} median={ws['median']:.1f} p25={ws['p25']:.1f} p75={ws['p75']:.1f}")
    print(f"  Losers:  mean={ls['mean']:.1f} median={ls['median']:.1f} p25={ls['p25']:.1f} p75={ls['p75']:.1f}")

    # === SESSION / TIME OF DAY ===
    w_sess = [entry_session(t.entry_time_et) for t in winners]
    l_sess = [entry_session(t.entry_time_et) for t in losers]
    print("\n[3] TIME OF DAY")
    print_feature_split("session", w_sess, l_sess)
    w_tods = [(t.entry_time_et.hour * 60 + t.entry_time_et.minute) for t in winners]
    l_tods = [(t.entry_time_et.hour * 60 + t.entry_time_et.minute) for t in losers]
    ws = compute_stats(w_tods)
    ls = compute_stats(l_tods)
    print(f"  Winners: mean={ws['mean']//60:.0f}:{ws['mean']%60:02.0f} median={ws['median']//60:.0f}:{ws['median']%60:02.0f}")
    print(f"  Losers:  mean={ls['mean']//60:.0f}:{ls['mean']%60:02.0f} median={ls['median']//60:.0f}:{ls['median']%60:02.0f}")

    # === ENTRY PREMIUM ===
    w_prem = [premium_bucket(getattr(t, "entry_premium", 0) or 0) for t in winners]
    l_prem = [premium_bucket(getattr(t, "entry_premium", 0) or 0) for t in losers]
    print("\n[4] ENTRY PREMIUM")
    print_feature_split("premium", w_prem, l_prem)
    w_prem_vals = [getattr(t, "entry_premium", 0) or 0 for t in winners]
    l_prem_vals = [getattr(t, "entry_premium", 0) or 0 for t in losers]
    ws = compute_stats(w_prem_vals)
    ls = compute_stats(l_prem_vals)
    print(f"  Winners: mean={ws['mean']:.2f} median={ws['median']:.2f}")
    print(f"  Losers:  mean={ls['mean']:.2f} median={ls['median']:.2f}")

    # === MFE/MAE RATIO ===
    w_ratio = [mfe_mae_ratio(t) for t in winners]
    l_ratio = [mfe_mae_ratio(t) for t in losers]
    ws = compute_stats(w_ratio)
    ls = compute_stats(l_ratio)
    print("\n[5] MFE/MAE RATIO (higher = better — max favorable vs max adverse)")
    print(f"  Winners: mean={ws['mean']:.2f}x median={ws['median']:.2f}x p25={ws['p25']:.2f}x p75={ws['p75']:.2f}x")
    print(f"  Losers:  mean={ls['mean']:.2f}x median={ls['median']:.2f}x p25={ls['p25']:.2f}x p75={ls['p75']:.2f}x")

    # === EXIT REASON ===
    w_exit = [str(getattr(t, "exit_reason", "?") or "?") for t in winners]
    l_exit = [str(getattr(t, "exit_reason", "?") or "?") for t in losers]
    print("\n[6] EXIT REASON")
    print_feature_split("exit_reason", w_exit, l_exit)

    # === HOLD TIME ===
    w_hold = [getattr(t, "hold_minutes", 0) or 0 for t in winners]
    l_hold = [getattr(t, "hold_minutes", 0) or 0 for t in losers]
    ws = compute_stats(w_hold)
    ls = compute_stats(l_hold)
    print("\n[7] HOLD MINUTES")
    print(f"  Winners: mean={ws['mean']:.0f}m median={ws['median']:.0f}m")
    print(f"  Losers:  mean={ls['mean']:.0f}m median={ls['median']:.0f}m")

    # === ENTRY DELTA ===
    w_delta = [getattr(t, "entry_delta", 0) or 0 for t in winners]
    l_delta = [getattr(t, "entry_delta", 0) or 0 for t in losers]
    ws = compute_stats(w_delta)
    ls = compute_stats(l_delta)
    print("\n[8] ENTRY DELTA (abs)")
    print(f"  Winners: mean={ws['mean']:.2f} median={ws['median']:.2f}")
    print(f"  Losers:  mean={ls['mean']:.2f} median={ls['median']:.2f}")

    # === SIDE ===
    w_side = [getattr(t, "side", "?") for t in winners]
    l_side = [getattr(t, "side", "?") for t in losers]
    print("\n[9] SIDE (P=Bear/Put, C=Bull/Call)")
    print_feature_split("side", w_side, l_side)

    # === TRIGGER RAW STRINGS ===
    print("\n[10] RAW TRIGGER STRINGS (top values)")
    all_trig_w = defaultdict(int)
    all_trig_l = defaultdict(int)
    for t in winners:
        for tr in getattr(t, "triggers_fired", []):
            all_trig_w[str(tr).split("_")[0] + "_" + "_".join(str(tr).split("_")[1:3])] += 1
    for t in losers:
        for tr in getattr(t, "triggers_fired", []):
            all_trig_l[str(tr).split("_")[0] + "_" + "_".join(str(tr).split("_")[1:3])] += 1
    all_keys = sorted(set(all_trig_w) | set(all_trig_l))
    for k in all_keys:
        wc = all_trig_w.get(k, 0)
        lc = all_trig_l.get(k, 0)
        wp = 100.0 * wc / max(1, len(winners))
        lp = 100.0 * lc / max(1, len(losers))
        edge = wp - lp
        flag = " <<<<" if abs(edge) >= 15 else ""
        print(f"    {k:<28} W={wc}({wp:.0f}%)  L={lc}({lp:.0f}%){flag}")

    # === WEEKLY BUCKETING ===
    print("\n[11] WEEK BUCKETS (which weeks had good OOS?)")
    def week_of(t):
        et = t.entry_time_et
        if hasattr(et, 'tzinfo') and et.tzinfo is not None:
            et = et.replace(tzinfo=None)
        d = et.date()
        # Week start (Monday)
        return (d - dt.timedelta(days=d.weekday())).strftime("%Y-%m-%d")
    w_weeks = [week_of(t) for t in winners]
    l_weeks = [week_of(t) for t in losers]
    all_weeks = sorted(set(w_weeks) | set(l_weeks))
    for wk in all_weeks:
        wc = w_weeks.count(wk)
        lc = l_weeks.count(wk)
        wk_pnl = sum(t.dollar_pnl for t in trades if week_of(t) == wk)
        print(f"    {wk}  W={wc} L={lc} pnl={wk_pnl:+.0f}")

    # === SUMMARY TABLE: trade-by-trade with all features ===
    print("\n" + "=" * 70)
    print("DETAILED FEATURE TABLE (per trade)")
    print("=" * 70)
    print(f"{'Date':>12} {'Time':>6} {'VIX':>5} {'Prem':>5} {'Delta':>6} {'Trig':>18} {'Hold':>5} {'MFE':>5} {'MAE':>5} {'pnl':>8}")
    print("-" * 90)
    for t in sorted(trades, key=lambda x: x.dollar_pnl, reverse=True):  # noqa
        entry_dt = t.entry_time_et
        pnl = t.dollar_pnl
        vix_v = getattr(t, "entry_vix", 0) or 0
        prem = getattr(t, "entry_premium", 0) or 0
        delta = abs(getattr(t, "entry_delta", 0) or 0)
        trig = classify_triggers(getattr(t, "triggers_fired", []))
        hold = getattr(t, "hold_minutes", 0) or 0
        mfe = getattr(t, "max_favorable_premium", 0) or 0
        mae = abs(getattr(t, "max_adverse_premium", 0) or 0)
        marker = "W" if pnl > 0 else "L"
        print(f"  {entry_dt.strftime('%Y-%m-%d')} {entry_dt.strftime('%H:%M'):>6} {vix_v:>5.1f} {prem:>5.2f} {delta:>6.2f} {trig:>18} {hold:>5.0f}m {mfe:>5.2f} {mae:>5.2f} {pnl:>+8.0f} {marker}")

    # === FULL TRIGGER LISTS per trade ===
    print("\n" + "=" * 70)
    print("FULL TRIGGERS_FIRED PER TRADE (sorted by P&L)")
    print("=" * 70)
    for t in sorted(trades, key=lambda x: x.dollar_pnl, reverse=True):  # noqa
        entry_dt = t.entry_time_et
        if hasattr(entry_dt, 'tzinfo') and entry_dt.tzinfo is not None:
            entry_dt = entry_dt.replace(tzinfo=None)
        pnl = t.dollar_pnl
        tfs = getattr(t, "triggers_fired", []) or []
        marker = "W" if pnl > 0 else "L"
        print(f"  {entry_dt.strftime('%Y-%m-%d %H:%M')} pnl={pnl:>+8.0f} {marker}  triggers={list(tfs)}")

    # === LEVEL RECLAIM vs REJECTION isolation ===
    print("\n" + "=" * 70)
    print("LEVEL_RECLAIM vs LEVEL_REJECTION isolation")
    print("=" * 70)
    reclaim_w, reclaim_l, rejection_w, rejection_l = [], [], [], []
    for t in trades:
        tfs = [str(x) for x in (getattr(t, "triggers_fired", []) or [])]
        has_reclaim = any("level_reclaim" in x for x in tfs)
        has_rejection = any("level_rejection" in x for x in tfs)
        is_win = t.dollar_pnl > 0
        if has_reclaim and not has_rejection:
            if is_win:
                reclaim_w.append(t)
            else:
                reclaim_l.append(t)
        elif has_rejection and not has_reclaim:
            if is_win:
                rejection_w.append(t)
            else:
                rejection_l.append(t)
    print(f"  level_reclaim ONLY: W={len(reclaim_w)} L={len(reclaim_l)}")
    if reclaim_w:
        print(f"    Winner P&Ls: {[round(t.dollar_pnl) for t in reclaim_w]}")
    if reclaim_l:
        print(f"    Loser P&Ls:  {[round(t.dollar_pnl) for t in reclaim_l]}")
    print(f"  level_rejection ONLY: W={len(rejection_w)} L={len(rejection_l)}")
    if rejection_w:
        print(f"    Winner P&Ls: {[round(t.dollar_pnl) for t in rejection_w]}")
    if rejection_l:
        print(f"    Loser P&Ls:  {[round(t.dollar_pnl) for t in rejection_l]}")

    reclaim_only_loser_pnl = sum(t.dollar_pnl for t in reclaim_l)
    reclaim_only_winner_pnl = sum(t.dollar_pnl for t in reclaim_w)
    print(f"\n  If block_level_reclaim (sole trigger): OOS delta={reclaim_only_loser_pnl - reclaim_only_winner_pnl:+,.0f}")
    print(f"   (removes {len(reclaim_l)} losers totaling {reclaim_only_loser_pnl:+,.0f} AND {len(reclaim_w)} winners totaling {reclaim_only_winner_pnl:+,.0f})")

    print(f"\nOOS feature analysis complete. n={len(trades)} (W={len(winners)}, L={len(losers)})")


if __name__ == "__main__":
    run()
