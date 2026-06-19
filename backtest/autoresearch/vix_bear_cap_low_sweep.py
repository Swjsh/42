"""
VIX_HARD_CAP_BEAR low-range sweep (20-30).

Composition analysis revealed:
  IS VIX 22-25: n=8, WR=12%, pnl=-$346
  IS VIX 25-30: n=8, WR=25%, pnl=-$427
  IS VIX 30+:   n=4, WR=75%, pnl=+$764  <- WINNER bucket, do NOT gate
  OOS VIX>22:   n=0  (no OOS trades in this range)

Prior vix_hard_cap_bear sweep only went down to 30, so cap=22 and cap=25
were never tested. This sweep tests cap [20, 21, 22, 23, 24, 25, 27, 30].

Key question: are VIX 22-30 IS losses concentrated in W4_Apr26 (C22)
or spread across multiple sub-windows? If spread -> gate may generalize.

Note: vix_hard_cap_bear=999 (off) is the production baseline.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_S = dt.date(2025, 1, 2)
IS_E = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 16)

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

WINDOWS = [
    ("W1_2025H1", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
    ("W2_2025H2", dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
    ("W3_Q12026", dt.date(2026, 1, 2), dt.date(2026, 3, 31)),
    ("W4_Apr26",  dt.date(2026, 4, 1), dt.date(2026, 5, 7)),
]

CAPS = [20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 27.0, 30.0]


def run_with_cap(spy_df, vix_df, start, end, cap):
    kw = dict(BASE_KWARGS)
    po = dict(kw.get("params_overrides", {}))
    po["vix_hard_cap_bear"] = cap
    kw["params_overrides"] = po
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end, **kw)


def main():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    print("\nRunning baseline (cap=999=off)...")
    is_base = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **BASE_KWARGS)
    oos_base = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE_KWARGS)
    is_base_pnl = sum(t.dollar_pnl for t in is_base.trades)
    oos_base_pnl = sum(t.dollar_pnl for t in oos_base.trades)
    n_is = len(is_base.trades)
    n_oos = len(oos_base.trades)
    print(f"BASE: IS n={n_is} pnl={is_base_pnl:+.0f} | OOS n={n_oos} pnl={oos_base_pnl:+.0f}")

    print(f"\n{'='*70}")
    print(f"VIX_HARD_CAP_BEAR SWEEP (low range 20-30)")
    print(f"{'='*70}")
    print(f"  {'cap':>5} {'IS_n':>5} {'IS_rm':>6} {'IS_dlt':>7} {'OOS_dlt':>8} {'WF':>7} {'verdict'}")
    print(f"  {'-'*5} {'-'*5} {'-'*6} {'-'*7} {'-'*8} {'-'*7} {'-'*15}")

    best_candidates = []

    for cap in CAPS:
        is_r = run_with_cap(spy, vix, IS_S, IS_E, cap)
        oos_r = run_with_cap(spy, vix, OOS_S, OOS_E, cap)
        is_pnl = sum(t.dollar_pnl for t in is_r.trades)
        oos_pnl = sum(t.dollar_pnl for t in oos_r.trades)
        is_delta = is_pnl - is_base_pnl
        oos_delta = oos_pnl - oos_base_pnl
        n_is_rm = n_is - len(is_r.trades)
        n_oos_rm = n_oos - len(oos_r.trades)

        wf = None
        wf_str = "N/A"
        if n_is_rm > 0 and n_oos_rm > 0 and is_delta != 0:
            wf = (oos_delta / n_oos) / (is_delta / n_is)
            wf_str = f"{wf:.3f}"
        elif n_is_rm > 0 and n_oos_rm == 0:
            wf_str = "INERT"

        if is_delta > 0 and oos_delta >= 0:
            verdict = "CANDIDATE"
        elif is_delta > 0 and oos_delta < 0:
            verdict = "C22-RISK"
        else:
            verdict = "REJECT"

        print(f"  {cap:>5.0f} {len(is_r.trades):>5} {n_is_rm:>6} {is_delta:>+7.0f} {oos_delta:>+8.0f} {wf_str:>7} {verdict}")

        if is_delta > 0:
            best_candidates.append((cap, is_delta, oos_delta, n_is_rm, n_oos_rm, wf))

    if not best_candidates:
        print(f"\nNo IS-positive candidates found. Production cap=999 confirmed optimal.")
        return

    print(f"\nIS-positive candidates:")
    for cap, is_d, oos_d, n_rm_is, n_rm_oos, wf in best_candidates:
        print(f"  cap={cap:.0f}: IS+{is_d:.0f} OOS{oos_d:+.0f} n_rm_is={n_rm_is} n_rm_oos={n_rm_oos}")

    # Run full sub-window for best IS candidate
    best_cap, best_is, best_oos, _, _, _ = max(best_candidates, key=lambda x: x[1])
    print(f"\n{'='*70}")
    print(f"SUB-WINDOW STABILITY: cap={best_cap:.0f} (best IS improvement)")
    print(f"{'='*70}")

    hurt = 0
    w4_delta = None
    for name, ws, we in WINDOWS:
        sw_base = run_backtest(spy, vix, start_date=ws, end_date=we, **BASE_KWARGS)
        sw_cand = run_with_cap(spy, vix, ws, we, best_cap)
        sw_delta = sum(t.dollar_pnl for t in sw_cand.trades) - sum(t.dollar_pnl for t in sw_base.trades)
        sw_rm = len(sw_base.trades) - len(sw_cand.trades)
        verdict = "HELP" if sw_delta > 0 else "FLAT" if sw_delta == 0 else "HURT"
        if verdict == "HURT":
            hurt += 1
        if name == "W4_Apr26":
            w4_delta = sw_delta
        print(f"  {name}: n_removed={sw_rm} delta={sw_delta:+.0f} -> {verdict}")

    # C22 check: what fraction of IS improvement came from W4?
    c22_pct = (w4_delta / best_is * 100) if best_is != 0 and w4_delta else 0
    c22_risk = "HIGH" if c22_pct > 80 else "MEDIUM" if c22_pct > 50 else "LOW"
    print(f"\n  SW hurt: {hurt}/4 (gate: <=1)")
    print(f"  C22 check: W4_Apr26 contribution = {c22_pct:.0f}% of IS improvement [{c22_risk} C22 RISK]")

    # Run rolling OOS (2 windows of ~3 weeks each)
    oos_wins = [
        ("OOS_W1_May8-22",  dt.date(2026, 5, 8), dt.date(2026, 5, 22)),
        ("OOS_W2_May23-Jun16", dt.date(2026, 5, 23), dt.date(2026, 6, 16)),
    ]
    print(f"\n  Rolling OOS:")
    oos_pass = 0
    for name, ws, we in oos_wins:
        w_base = run_backtest(spy, vix, start_date=ws, end_date=we, **BASE_KWARGS)
        w_cand = run_with_cap(spy, vix, ws, we, best_cap)
        w_delta = sum(t.dollar_pnl for t in w_cand.trades) - sum(t.dollar_pnl for t in w_base.trades)
        w_rm = len(w_base.trades) - len(w_cand.trades)
        verdict = "PASS" if w_delta >= 0 else "FAIL"
        if w_delta >= 0:
            oos_pass += 1
        print(f"  {name}: n_removed={w_rm} delta={w_delta:+.0f} -> {verdict}")

    oos_roll_pct = oos_pass / len(oos_wins) * 100
    print(f"  Rolling OOS: {oos_pass}/{len(oos_wins)} ({oos_roll_pct:.0f}%, gate: >=60%)")

    # Anchor check (J's key anchor days: 4/29, 5/01, 5/04, 5/05, 5/06)
    anchor_dates = [
        dt.date(2026, 4, 29),
        dt.date(2026, 5, 1),
        dt.date(2026, 5, 4),
        dt.date(2026, 5, 5),
        dt.date(2026, 5, 6),
    ]
    print(f"\n  Anchor check (cap={best_cap:.0f}):")
    all_ok = True
    for d in anchor_dates:
        b = run_backtest(spy, vix, start_date=d, end_date=d, **BASE_KWARGS)
        c = run_with_cap(spy, vix, d, d, best_cap)
        b_pnl = sum(t.dollar_pnl for t in b.trades)
        c_pnl = sum(t.dollar_pnl for t in c.trades)
        delta = c_pnl - b_pnl
        d_str = d.strftime("%m/%d")
        ok = delta >= -100
        if not ok:
            all_ok = False
        flag = "OK" if ok else "REGRESSION"
        print(f"  {d_str}: base={b_pnl:+.0f} cand={c_pnl:+.0f} delta={delta:+.0f} [{flag}]")

    print(f"\n{'='*70}")
    print(f"FINAL VERDICT (cap={best_cap:.0f}):")
    oos_pos = best_oos >= 0
    sw_ok = hurt <= 1
    anchor_ok = all_ok
    auto_ratify = oos_pos and sw_ok and anchor_ok and c22_risk != "HIGH"
    print(f"  IS delta: {best_is:+.0f}")
    print(f"  OOS delta: {best_oos:+.0f}")
    print(f"  SW: {hurt}/4 HURT ({'PASS' if sw_ok else 'FAIL'})")
    print(f"  C22 risk: {c22_risk} ({c22_pct:.0f}%)")
    print(f"  Anchor: {'OK' if anchor_ok else 'REGRESSION'}")
    print(f"  -> {'CANDIDATE (auto-ratify eligible)' if auto_ratify else 'REJECT or INCONCLUSIVE'}")
    print(f"\nVIX bear cap sweep complete.")


if __name__ == "__main__":
    main()
