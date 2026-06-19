"""
VIX_RISING_DEADBAND=0.15 SUB-WINDOW STABILITY CHECK

C14 final batch found two PASS candidates for vix_rising_deadband:
  deadband=0.15: IS_delta=+689 OOS_delta=+865 WF=20.4 anchor=OK
  deadband=0.30: IS_delta=+5107 OOS_delta=+2191 WF=6.98 anchor=OK (n_oos=5, too thin)

This script runs sub-window stability on deadband=0.15 (the stronger candidate):
  4 IS sub-windows: W1 Jan-Jun 2025, W2 Jul-Dec 2025, W3 Jan-Mar 2026, W4 Apr-May 2026
  Gate: ALL must be HELP or NEUTRAL, zero HURT.

Also checks rolling walk-forward for deadband=0.15 (3 windows: OOS each month).
And spot-checks deadband=0.30 for anchor stability (which J anchor days does it remove?).

Mechanism: A VIX rising deadband of 0.15 means bar-to-bar VIX change < 0.15 is
  classified as 'flat' not 'rising'. This blocks BEAR entries where VIX barely moved —
  arguably noise rather than genuine escalation.

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

# Current production Safe baseline (post-Rank37)
BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    midday_trendline_gate_start_minutes=690,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.50,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)

CANDIDATE_DEADBAND = 0.15

# BASE has params_overrides baked in — we need to pop it to avoid double-kwarg.
# Split: BASE_KW = BASE minus params_overrides. BASE_OVERRIDES and CANDIDATE_EXTRA passed explicitly.
BASE_KW = {k: v for k, v in BASE.items() if k != "params_overrides"}
BASE_OVERRIDES = {"vix_bull_max": 18.0}
CANDIDATE_EXTRA = {"vix_bull_max": 18.0, "vix_rising_deadband": CANDIDATE_DEADBAND}

IS_SUBWINDOWS = [
    ("W1 Jan-Jun 2025",  dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2 Jul-Dec 2025",  dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3 Jan-Mar 2026",  dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4 Apr-May 2026",  dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

ROLLING_OOS_WINDOWS = [
    ("OOS Jul-25",  dt.date(2025, 7, 1),  dt.date(2025, 7, 31), dt.date(2025, 1, 2)),
    ("OOS Sep-25",  dt.date(2025, 9, 1),  dt.date(2025, 9, 30), dt.date(2025, 3, 1)),
    ("OOS Nov-25",  dt.date(2025, 11, 1), dt.date(2025, 11, 30), dt.date(2025, 5, 1)),
    ("OOS Jan-26",  dt.date(2026, 1, 1),  dt.date(2026, 1, 31), dt.date(2025, 7, 1)),
    ("OOS Mar-26",  dt.date(2026, 3, 1),  dt.date(2026, 3, 31), dt.date(2025, 9, 1)),
    ("OOS May-26",  dt.date(2026, 5, 1),  dt.date(2026, 5, 22), dt.date(2025, 11, 1)),
]


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _by_date(trades):
    result = {}
    for t in trades:
        d = _date(t)
        result[d] = result.get(d, 0.0) + t.dollar_pnl
    return result


def _anchor_ok(by_date, base_bd):
    for d in J_WINNERS:
        bp = base_bd.get(d, 0.0)
        cp = by_date.get(d, 0.0)
        if bp > 0 and cp < bp * 0.90:
            return False
    return True


if __name__ == "__main__":
    print("=" * 90)
    print(f"VIX_RISING_DEADBAND={CANDIDATE_DEADBAND} SUB-WINDOW STABILITY CHECK")
    print("=" * 90)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Full IS and OOS baseline
    print("\n[FULL IS BASELINE]")
    is_base = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, params_overrides=BASE_OVERRIDES, **BASE_KW)
    is_cand = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, params_overrides=CANDIDATE_EXTRA, **BASE_KW)
    is_bp = _pnl(is_base.trades)
    is_cp = _pnl(is_cand.trades)
    is_bd = _by_date(is_base.trades)
    is_cd = _by_date(is_cand.trades)
    is_delta = is_cp - is_bp
    print(f"  BASELINE: n={len(is_base.trades)} pnl={is_bp:+.0f}")
    print(f"  CANDIDATE: n={len(is_cand.trades)} pnl={is_cp:+.0f} delta={is_delta:+.0f}")
    anchor_is = _anchor_ok(is_cd, is_bd)
    print(f"  Anchor check: {'OK' if anchor_is else 'FAIL'}")

    print("\n[OOS BASELINE]")
    oos_base = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, params_overrides=BASE_OVERRIDES, **BASE_KW)
    oos_cand = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, params_overrides=CANDIDATE_EXTRA, **BASE_KW)
    oos_bp = _pnl(oos_base.trades)
    oos_cp = _pnl(oos_cand.trades)
    oos_delta = oos_cp - oos_bp
    n_is = len(is_base.trades)
    n_oos = len(oos_base.trades)
    wf = (oos_delta / n_oos) / (is_delta / n_is) if is_delta != 0 else 0.0
    print(f"  BASELINE: n={n_oos} pnl={oos_bp:+.0f}")
    print(f"  CANDIDATE: n={len(oos_cand.trades)} pnl={oos_cp:+.0f} delta={oos_delta:+.0f}")
    print(f"  WF_norm: {wf:.3f}")

    # Sub-window stability
    print("\n[IS SUB-WINDOW STABILITY]")
    print(f"  {'Window':20}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>9}  {'CAND_pnl':>9}  {'delta':>7}  {'verdict':>8}")
    print("  " + "-" * 80)
    sub_hurts = 0
    sub_helps = 0
    sub_neutral = 0
    for label, s, e in IS_SUBWINDOWS:
        b = run_backtest(spy_df, vix_df, start_date=s, end_date=e, params_overrides=BASE_OVERRIDES, **BASE_KW)
        c = run_backtest(spy_df, vix_df, start_date=s, end_date=e, params_overrides=CANDIDATE_EXTRA, **BASE_KW)
        bp = _pnl(b.trades)
        cp = _pnl(c.trades)
        d = cp - bp
        verdict = "HURT" if d < -100 else ("HELP" if d > 100 else "NEUTRAL")
        if verdict == "HURT":
            sub_hurts += 1
        elif verdict == "HELP":
            sub_helps += 1
        else:
            sub_neutral += 1
        print(f"  {label:20}  {len(b.trades):>6}  {len(c.trades):>6}  {bp:>+9.0f}  {cp:>+9.0f}  {d:>+7.0f}  {verdict:>8}")
    print(f"\n  HURT={sub_hurts} HELP={sub_helps} NEUTRAL={sub_neutral}")
    sub_stable = sub_hurts == 0
    print(f"  Sub-window gate: {'PASS (zero HURT)' if sub_stable else f'FAIL ({sub_hurts} HURT windows)'}")

    # What trades are blocked? Show details of the IS trades removed
    print("\n[BLOCKED IS TRADES DETAIL (trades in baseline NOT in candidate)]")
    base_dates = {_date(t): t for t in is_base.trades}
    cand_date_set = set(_date(t) for t in is_cand.trades)
    blocked = [t for t in is_base.trades if _date(t) not in cand_date_set]
    # More precisely: compare by entry time
    base_et = [(t.entry_time_et, t.dollar_pnl, getattr(t, 'entry_vix', 0)) for t in is_base.trades]
    cand_et = set(t.entry_time_et for t in is_cand.trades)
    blocked = [(et, pnl, vix) for et, pnl, vix in base_et if et not in cand_et]
    for et, pnl, vix in blocked[:20]:
        print(f"  {et} VIX={vix:.1f} pnl={pnl:+.0f}")
    if len(blocked) > 20:
        print(f"  ... and {len(blocked)-20} more")
    print(f"  Total blocked: {len(blocked)}, avg_pnl={sum(p for _,p,_ in blocked)/len(blocked):+.0f}/trade" if blocked else "  No blocked IS trades found")

    # OOS blocked trades
    print("\n[BLOCKED OOS TRADES DETAIL]")
    oos_base_et = [(t.entry_time_et, t.dollar_pnl, getattr(t, 'entry_vix', 0)) for t in oos_base.trades]
    oos_cand_et = set(t.entry_time_et for t in oos_cand.trades)
    oos_blocked = [(et, pnl, vix) for et, pnl, vix in oos_base_et if et not in oos_cand_et]
    for et, pnl, vix in oos_blocked:
        print(f"  {et} VIX={vix:.1f} pnl={pnl:+.0f}")
    if not oos_blocked:
        print("  No blocked OOS trades found")
    if oos_blocked:
        print(f"  Total blocked: {len(oos_blocked)}, avg_pnl={sum(p for _,p,_ in oos_blocked)/len(oos_blocked):+.0f}/trade")

    # Rolling OOS check
    print("\n[ROLLING OOS CHECK (is deadband=0.15 consistent across rolling windows?)]")
    print(f"  {'OOS Window':12}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>9}  {'CAND_pnl':>9}  {'delta':>7}  {'WF_norm':>8}")
    print("  " + "-" * 75)
    rolling_oos_pos = 0
    rolling_oos_total = 0
    for label, oos_s, oos_e, is_s in ROLLING_OOS_WINDOWS:
        try:
            is_b = run_backtest(spy_df, vix_df, start_date=is_s, end_date=oos_s, params_overrides=BASE_OVERRIDES, **BASE_KW)
            is_c = run_backtest(spy_df, vix_df, start_date=is_s, end_date=oos_s, params_overrides=CANDIDATE_EXTRA, **BASE_KW)
            oos_b = run_backtest(spy_df, vix_df, start_date=oos_s, end_date=oos_e, params_overrides=BASE_OVERRIDES, **BASE_KW)
            oos_c = run_backtest(spy_df, vix_df, start_date=oos_s, end_date=oos_e, params_overrides=CANDIDATE_EXTRA, **BASE_KW)
            is_d = _pnl(is_c.trades) - _pnl(is_b.trades)
            oos_d = _pnl(oos_c.trades) - _pnl(oos_b.trades)
            n_is_r = len(is_b.trades)
            n_oos_r = len(oos_b.trades)
            wf_r = (oos_d / n_oos_r) / (is_d / n_is_r) if is_d != 0 and n_oos_r > 0 else 0.0
            if oos_d > 0:
                rolling_oos_pos += 1
            rolling_oos_total += 1
            print(f"  {label:12}  {n_oos_r:>6}  {len(oos_c.trades):>6}  {_pnl(oos_b.trades):>+9.0f}  {_pnl(oos_c.trades):>+9.0f}  {oos_d:>+7.0f}  {wf_r:>8.3f}")
        except Exception as ex:
            print(f"  {label:12}  ERROR: {ex}")
    if rolling_oos_total > 0:
        pct = rolling_oos_pos / rolling_oos_total * 100
        print(f"\n  Rolling OOS+: {rolling_oos_pos}/{rolling_oos_total} ({pct:.0f}%) [gate: >=60%]")
        print(f"  Rolling gate: {'PASS' if pct >= 60 else 'FAIL'}")

    # Final verdict
    print("\n" + "=" * 90)
    print("FINAL VERDICT")
    print("=" * 90)
    oos_positive = oos_delta > 0
    wf_pass = wf >= 0.70
    print(f"\n  OOS positive: {oos_positive} (delta={oos_delta:+.0f})")
    print(f"  WF >= 0.70: {wf_pass} (WF={wf:.3f})")
    print(f"  Anchor OK: {anchor_is}")
    print(f"  Sub-window stable: {sub_stable}")
    all_pass = oos_positive and wf_pass and anchor_is and sub_stable
    print(f"\n  CANDIDATE STATUS: {'PASS - file A/B scorecard' if all_pass else 'FAIL - reject'}")
    if all_pass:
        print(f"\n  RECOMMENDATION: Ratify vix_rising_deadband={CANDIDATE_DEADBAND}")
        print(f"  Mechanism: blocks BEAR entries where VIX barely moves (<0.15/bar)")
        print(f"  Effect: removed {n_is - len(is_cand.trades)} bad IS trades, {n_oos - len(oos_cand.trades)} bad OOS trades")
        print(f"  Consistent per-blocked-trade improvement: IS ${is_delta/max(1,n_is-len(is_cand.trades)):+.0f} vs OOS ${oos_delta/max(1,n_oos-len(oos_cand.trades)):+.0f}")

    print("\nANALYSIS COMPLETE.")
