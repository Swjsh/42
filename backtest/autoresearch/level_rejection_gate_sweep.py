"""
Sweep: block LEVEL trades where trigger contains 'level_rejection'.
Hypothesis: level_reclaim fires IN TREND (price reclaims broken level);
            level_rejection fires COUNTER-TREND (fade the touch).
            Counter-trend fades in BEARISH_REVERSAL context lose badly.

Gate logic (post-hoc simulation — no engine param needed):
  Remove trades where classify_tier == LEVEL AND any(tr.startswith('level_rejection')
  for tr in triggers_fired)
"""
import sys
import datetime as dt
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR  = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

IS_SUB_WINDOWS = [
    ("W1", dt.date(2025,  1,  2), dt.date(2025,  6, 30)),
    ("W2", dt.date(2025,  7,  1), dt.date(2025, 12, 31)),
    ("W3", dt.date(2026,  1,  1), dt.date(2026,  3, 31)),
    ("W4", dt.date(2026,  4,  1), dt.date(2026,  5,  7)),
]

OOS_ROLLING = [
    ("OOS_W1", dt.date(2026, 5,  8), dt.date(2026, 5, 14)),
    ("OOS_W2", dt.date(2026, 5, 15), dt.date(2026, 5, 22)),
]

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)


def classify_tier(triggers):
    full = [x.lower() for x in triggers]
    has_confluence = any("confluence" in x for x in full)
    has_ribbon_flip = any("ribbon_flip" in x for x in full)
    has_sequence = any("sequence_rejection" in x for x in full)
    has_level = any(x in ("level_rejection", "level_reclaim") for x in full)
    n = len(triggers)
    if n >= 3 and has_confluence and has_ribbon_flip:
        return "SUPER"
    elif n >= 2 and (has_confluence or has_sequence):
        return "ELITE"
    elif has_level:
        return "LEVEL"
    elif any("trendline_rejection" in x for x in full):
        return "TRENDLINE"
    else:
        return "BASE"


def has_level_rejection(t):
    """True if ANY trigger starts with 'level_rejection'."""
    return any(tr.startswith("level_rejection") for tr in t.triggers_fired)


def is_level_rejection_trade(t):
    """Trade is LEVEL tier AND has level_rejection trigger."""
    return classify_tier(t.triggers_fired) == "LEVEL" and has_level_rejection(t)


def get_entry_date(t):
    et = t.entry_time_et
    if hasattr(et, 'date'):
        return et.date()
    return dt.date.fromisoformat(str(et)[:10])


def pnl_by_date_window(trades, start, end):
    in_window = [t for t in trades if start <= get_entry_date(t) <= end]
    return sum(t.dollar_pnl for t in in_window), len(in_window)


def main():
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("Running backtests...")
    is_r  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)

    all_is  = is_r.trades
    all_oos = oos_r.trades

    # ── Gate: remove LEVEL level_rejection trades ───────────────────────────────
    is_removed  = [t for t in all_is  if is_level_rejection_trade(t)]
    oos_removed = [t for t in all_oos if is_level_rejection_trade(t)]

    is_cand  = [t for t in all_is  if not is_level_rejection_trade(t)]
    oos_cand = [t for t in all_oos if not is_level_rejection_trade(t)]

    is_base_pnl  = sum(t.dollar_pnl for t in all_is)
    oos_base_pnl = sum(t.dollar_pnl for t in all_oos)
    is_cand_pnl  = sum(t.dollar_pnl for t in is_cand)
    oos_cand_pnl = sum(t.dollar_pnl for t in oos_cand)

    n_is_base  = len(all_is)
    n_oos_base = len(all_oos)
    n_is_cand  = len(is_cand)
    n_oos_cand = len(oos_cand)

    is_delta  = is_cand_pnl  - is_base_pnl
    oos_delta = oos_cand_pnl - oos_base_pnl

    print(f"\n{'='*72}")
    print("GATE: block LEVEL trades with level_rejection trigger")
    print(f"{'='*72}")
    print(f"  IS:  base n={n_is_base:4d} pnl={is_base_pnl:+,.0f}  "
          f"cand n={n_is_cand:4d} pnl={is_cand_pnl:+,.0f}  delta={is_delta:+,.0f}")
    print(f"  OOS: base n={n_oos_base:4d} pnl={oos_base_pnl:+,.0f}  "
          f"cand n={n_oos_cand:4d} pnl={oos_cand_pnl:+,.0f}  delta={oos_delta:+,.0f}")

    if is_delta != 0 and n_is_base > 0 and n_oos_base > 0:
        wf = (oos_delta / n_oos_base) / (is_delta / n_is_base)
        print(f"  WF_norm = {wf:.3f}  ({'PASS' if wf >= 0.70 and oos_delta > 0 else 'FAIL'})")
    else:
        print(f"  WF_norm = N/A (IS_delta={is_delta})")

    # ── Removed trades detail ───────────────────────────────────────────────────
    print(f"\n  IS removed ({len(is_removed)} trades, total={sum(t.dollar_pnl for t in is_removed):+,.0f}):")
    by_trigger = defaultdict(list)
    for t in is_removed:
        key = "|".join(sorted(t.triggers_fired))
        by_trigger[key].append(t.dollar_pnl)
    for k, pnls in sorted(by_trigger.items()):
        wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
        print(f"    {k:50s}  n={len(pnls):3d}  WR={wr:4.1f}%  avg={sum(pnls)/len(pnls):+.0f}")

    print(f"\n  OOS removed ({len(oos_removed)} trades, total={sum(t.dollar_pnl for t in oos_removed):+,.0f}):")
    for t in oos_removed:
        d = get_entry_date(t)
        print(f"    {d}  VIX={t.entry_vix:.2f}  pnl={t.dollar_pnl:+.0f}  trigs={t.triggers_fired}")

    # ── Anchor check ─────────────────────────────────────────────────────────────
    print(f"\n  J anchor check:")
    anchor_ok = True
    for j_day in sorted(J_WINNERS):
        base_day_pnl = sum(t.dollar_pnl for t in all_is if get_entry_date(t) == j_day)
        cand_day_pnl = sum(t.dollar_pnl for t in is_cand if get_entry_date(t) == j_day)
        delta = cand_day_pnl - base_day_pnl
        removed_today = [t for t in is_removed if get_entry_date(t) == j_day]
        status = "OK" if delta >= 0 else "HURT"
        if delta < 0:
            anchor_ok = False
        print(f"    {j_day}  base={base_day_pnl:+,.0f}  cand={cand_day_pnl:+,.0f}  "
              f"delta={delta:+,.0f}  removed={len(removed_today)}  {status}")

    # ── IS Sub-window stability ───────────────────────────────────────────────────
    print(f"\n  IS Sub-window stability (HURT = delta < -200):")
    n_hurt = 0
    for name, sw_start, sw_end in IS_SUB_WINDOWS:
        base_pnl, base_n = pnl_by_date_window(all_is, sw_start, sw_end)
        cand_pnl, cand_n = pnl_by_date_window(is_cand, sw_start, sw_end)
        delta = cand_pnl - base_pnl
        status = "HURT" if delta < -200 else "OK"
        if status == "HURT":
            n_hurt += 1
        print(f"    {name}  base_n={base_n:3d} base={base_pnl:+,.0f}  "
              f"cand_n={cand_n:3d} cand={cand_pnl:+,.0f}  delta={delta:+,.0f}  {status}")

    # ── OOS Rolling windows ─────────────────────────────────────────────────────
    print(f"\n  OOS Rolling windows (need >=60% positive):")
    n_pass = 0
    for name, w_start, w_end in OOS_ROLLING:
        base_pnl, _ = pnl_by_date_window(all_oos, w_start, w_end)
        cand_pnl, _ = pnl_by_date_window(oos_cand, w_start, w_end)
        delta = cand_pnl - base_pnl
        status = "PASS" if delta > 0 else "FAIL"
        if status == "PASS":
            n_pass += 1
        print(f"    {name}  base={base_pnl:+,.0f}  cand={cand_pnl:+,.0f}  delta={delta:+,.0f}  {status}")

    oos_rolling_ok = n_pass >= max(1, len(OOS_ROLLING) * 0.6)

    # ── Final verdict ────────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print("FINAL VERDICT")
    print(f"{'='*72}")
    oos_ok = oos_delta > 0
    wf_ok = (oos_delta / n_oos_base) / (is_delta / n_is_base) >= 0.70 if is_delta > 0 else False

    print(f"  OOS positive:        {oos_ok}  ({oos_delta:+,.0f})")
    print(f"  WF >= 0.70:          {wf_ok}")
    print(f"  anchor_no_regression:{anchor_ok}")
    print(f"  sub_window_stable:   {n_hurt == 0}  ({n_hurt} HURT windows)")
    print(f"  OOS_rolling_gate:    {oos_rolling_ok}  ({n_pass}/{len(OOS_ROLLING)} pass)")

    all_pass = oos_ok and wf_ok and anchor_ok and n_hurt == 0 and oos_rolling_ok
    print(f"\n  CANDIDATE STATUS: {'RATIFY' if all_pass else 'FAIL'}")

    if not all_pass:
        fails = []
        if not oos_ok: fails.append("OOS_negative")
        if not wf_ok: fails.append(f"WF_low({(oos_delta/n_oos_base)/(is_delta/n_is_base):.3f})" if is_delta > 0 else "WF_N/A")
        if not anchor_ok: fails.append("anchor_regression")
        if n_hurt > 0: fails.append(f"{n_hurt}_IS_sub_windows_HURT")
        if not oos_rolling_ok: fails.append(f"OOS_rolling_{n_pass}/{len(OOS_ROLLING)}")
        print(f"  Failed gates: {', '.join(fails)}")

    print("\n[ANALYSIS COMPLETE]")


if __name__ == "__main__":
    main()
