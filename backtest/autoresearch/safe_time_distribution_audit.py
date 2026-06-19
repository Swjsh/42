"""
SAFE TIME DISTRIBUTION AUDIT (2026-06-17)

Audit: full breakdown of IS + OOS Safe trades by 30-min time window and trigger class.
Goal: identify structural time-of-day patterns NOT already gated, to guide no_trade_window sweep.

Currently gated:
 - midday_trendline_gate: blocks tl_pure 11:30-14:00
 - block_conf_lvl_rec_afternoon: blocks conf+lvl_rec 14:00+
 - time_stop_minutes_before_close=20: no new entries after 15:40

Structural time effects bypass C22 (regime-independent theta decay + liquidity).
This audit discovers WHERE remaining losses cluster by time.

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys, datetime as dt, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

SAFE_KW = dict(
    use_real_fills=True,
    no_trade_window=(dt.time(11, 30), dt.time(12, 0)),  # ENFORCED-4
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    block_conf_lvl_rec_afternoon=True,
)
SAFE_OVR = {"vix_bull_max": 18.0}

# Time windows: 30-min buckets from open to close
WINDOWS = [
    ("09:35-10:00", dt.time(9, 35),  dt.time(10, 0)),
    ("10:00-10:30", dt.time(10, 0),  dt.time(10, 30)),
    ("10:30-11:00", dt.time(10, 30), dt.time(11, 0)),
    ("11:00-11:30", dt.time(11, 0),  dt.time(11, 30)),
    ("11:30-12:00", dt.time(11, 30), dt.time(12, 0)),   # midday tl_pure blocked
    ("12:00-12:30", dt.time(12, 0),  dt.time(12, 30)),
    ("12:30-13:00", dt.time(12, 30), dt.time(13, 0)),
    ("13:00-13:30", dt.time(13, 0),  dt.time(13, 30)),
    ("13:30-14:00", dt.time(13, 30), dt.time(14, 0)),
    ("14:00-14:30", dt.time(14, 0),  dt.time(14, 30)),  # conf+lvl_rec blocked
    ("14:30-15:00", dt.time(14, 30), dt.time(15, 0)),
    ("15:00-15:30", dt.time(15, 0),  dt.time(15, 30)),
    ("15:30-15:40", dt.time(15, 30), dt.time(15, 40)),  # last before time_stop
]

TRIGGER_CLASSES = ["conf+lvl_rec", "conf+lvl_rej", "tl+ribbon_flip", "tl_pure", "lvl_rec_only", "lvl_rej_only"]


def _classify(t) -> str:
    """Reproduce trigger class label from trade attributes."""
    trigs = set(getattr(t, "winning_triggers", None) or [])
    confluence = getattr(t, "has_confluence", False)
    tl = "trendline_rejection" in trigs
    lvl_rec = "level_reclaim" in trigs
    lvl_rej = "level_rejection" in trigs
    ribbon = "ribbon_flip" in trigs

    if confluence:
        if lvl_rec:
            return "conf+lvl_rec"
        elif lvl_rej:
            return "conf+lvl_rej"
        else:
            return "conf+other"
    elif tl and ribbon:
        return "tl+ribbon_flip"
    elif tl and lvl_rej:
        return "tl+lvl_rej"
    elif tl:
        return "tl_pure"
    elif lvl_rec:
        return "lvl_rec_only"
    elif lvl_rej:
        return "lvl_rej_only"
    else:
        return "other"


def _entry_time(t) -> dt.time:
    et = t.entry_time_et
    naive = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return naive.time()


def _window_label(t_time: dt.time) -> str:
    for label, start, end in WINDOWS:
        if start <= t_time < end:
            return label
    return "15:40+"


def _analyze(trades, label: str):
    print(f"\n{'='*70}")
    print(f"  {label}: n={len(trades)}  total_pnl={sum(t.dollar_pnl for t in trades):+,.0f}")
    print(f"{'='*70}")

    # By time window
    by_window: dict[str, list] = collections.defaultdict(list)
    for t in trades:
        by_window[_window_label(_entry_time(t))].append(t)

    all_windows = [w[0] for w in WINDOWS] + ["15:40+"]
    print(f"\n  {'Window':<18} {'n':>4} {'total':>9} {'avg':>8} {'stop%':>7}  trigger breakdown")
    print(f"  {'-'*75}")
    for wlabel in all_windows:
        ws = by_window.get(wlabel, [])
        if not ws:
            continue
        n = len(ws)
        total = sum(t.dollar_pnl for t in ws)
        avg = total / n
        stops = sum(1 for t in ws if t.dollar_pnl < 0)
        stop_pct = 100 * stops / n

        # Trigger class sub-breakdown for this window
        by_class: dict[str, list] = collections.defaultdict(list)
        for t in ws:
            by_class[_classify(t)].append(t)
        cls_parts = []
        for cls in TRIGGER_CLASSES:
            cs = by_class.get(cls, [])
            if cs:
                cls_pnl = sum(t.dollar_pnl for t in cs)
                cls_parts.append(f"{cls}(n={len(cs)},avg={cls_pnl/len(cs):+.0f})")

        row_star = "BAD" if avg < -50 else ("neg" if avg < 0 else "")
        print(f"  {wlabel:<18} {n:>4} {total:>+9,.0f} {avg:>+8.0f} {stop_pct:>6.1f}%  {' | '.join(cls_parts)} {row_star}")

    # By trigger class
    print(f"\n  {'Class':<22} {'n':>4} {'total':>9} {'avg':>8} {'stop%':>7}  top window")
    print(f"  {'-'*70}")
    by_class_all: dict[str, list] = collections.defaultdict(list)
    for t in trades:
        by_class_all[_classify(t)].append(t)
    for cls in TRIGGER_CLASSES + ["conf+other", "tl+lvl_rej", "other"]:
        cs = by_class_all.get(cls, [])
        if not cs:
            continue
        n = len(cs)
        total = sum(t.dollar_pnl for t in cs)
        avg = total / n
        stops = sum(1 for t in cs if t.dollar_pnl < 0)
        stop_pct = 100 * stops / n
        # Best window for this class
        by_win: dict[str, float] = {}
        for t in cs:
            wl = _window_label(_entry_time(t))
            by_win[wl] = by_win.get(wl, 0) + t.dollar_pnl
        best_win = max(by_win, key=by_win.get) if by_win else "-"
        print(f"  {cls:<22} {n:>4} {total:>+9,.0f} {avg:>+8.0f} {stop_pct:>6.1f}%  best={best_win}")


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\nRunning IS backtest (production Safe params)...")
    r_is = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                        params_overrides=SAFE_OVR, **SAFE_KW)

    print("Running OOS backtest...")
    r_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                         params_overrides=SAFE_OVR, **SAFE_KW)

    _analyze(r_is.trades, "IS (2025-01-02 to 2026-05-07)")
    _analyze(r_oos.trades, "OOS (2026-05-08 to 2026-06-16)")

    print("\n\n=== LOSS CONCENTRATION (IS trades avg < -$30, n >= 3) ===")
    by_window_is: dict[str, list] = collections.defaultdict(list)
    for t in r_is.trades:
        by_window_is[_window_label(_entry_time(t))].append(t)
    for wlabel, ws in sorted(by_window_is.items()):
        avg = sum(t.dollar_pnl for t in ws) / len(ws) if ws else 0
        if avg < -30 and len(ws) >= 3:
            print(f"  [BAD] {wlabel}: n={len(ws)} avg={avg:+.0f}  <<< CANDIDATE FOR no_trade_window")

    print("\n=== GAIN CONCENTRATION (OOS trades avg > +$100, n >= 2) ===")
    by_window_oos: dict[str, list] = collections.defaultdict(list)
    for t in r_oos.trades:
        by_window_oos[_window_label(_entry_time(t))].append(t)
    for wlabel, ws in sorted(by_window_oos.items()):
        avg = sum(t.dollar_pnl for t in ws) / len(ws) if ws else 0
        if avg > 100 and len(ws) >= 2:
            print(f"  [WIN] {wlabel}: n={len(ws)} avg={avg:+.0f}  <<< DO NOT GATE (OOS winner)")

    print("\nDone.")
