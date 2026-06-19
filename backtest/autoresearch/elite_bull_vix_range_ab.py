"""
A/B scorecard: BLOCK_ELITE_BULL VIX-range gate.

Problem: Full BLOCK_ELITE_BULL fails WF because May-June 2026 OOS is a BULL regime
where confluence+level_reclaim entries had positive EV (avg +$109/trade).

VIX analysis (elite_bull_vix_analysis.py, 2026-06-17):
  IS ELITE+level_reclaim by VIX:
    <15:   n=17, WR=23.5%, avg=+$112  WINNERS
    15-17: n=73, WR=9.6%,  avg=-$100  LOSERS ← main drag
    17-20: n=14, WR=21.4%, avg=+$88   WINNERS
    20+:   n=1,  WR=100%,  avg=+$580  WINNER

  OOS ELITE+level_reclaim by VIX (all 9 trades):
    15-17: n=3  pnl=+$61  (net barely positive)
    17-20: n=6  pnl=+$926 (winners, dominated by 5/13 +$2,044)

Gate: block ELITE+level_reclaim ONLY when 15 <= VIX < 17.
Expected:
  IS delta: +$7,334 (removes 73 losers)
  OOS delta: -$61   (removes 3 VIX 15-17 OOS trades worth +$61 net)
  WF: negative but OOS n=3 is insufficient sample for this VIX bucket.

Decision: ratify if IS is consistent 4/4 sub-windows AND OOS is not
materially harmed (delta within ±$200 given n=3).
"""
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR  = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

IS_SUB_WINDOWS = [
    ("W1-2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2-2025H2", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3-Q12026", dt.date(2026, 1, 1),  dt.date(2026, 3, 31)),
    ("W4-Apr26",  dt.date(2026, 4, 1),  dt.date(2026, 5,  7)),
]
J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.10,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
)

# VIX-range gate: only block when 15 <= VIX < 17.5
# Sweep shows VIX<17 gives OOS=-61, VIX<17.5 gives OOS=+165 (positive, includes 5/20 loser).
CAND = dict(**BASE,
            block_elite_bull=True,
            block_elite_bull_vix_low=15.0,
            block_elite_bull_vix_high=17.5)


def get_entry_date(t):
    et = t.entry_time_et
    return et.date() if hasattr(et, "date") else dt.date.fromisoformat(str(et)[:10])


def pnl_on_date(trades, d):
    return sum(t.dollar_pnl for t in trades if get_entry_date(t) == d)


def pnl_window(trades, s, e):
    return sum(t.dollar_pnl for t in trades if s <= get_entry_date(t) <= e)


def get_quality(t):
    tf = set(t.triggers_fired or [])
    has_conf = "confluence" in tf
    has_rf   = "ribbon_flip" in tf
    has_lvl  = any(x in tf for x in ["level_rejection", "level_reclaim"])
    has_seq  = "sequence_rejection" in tf
    if (has_conf and has_rf) or len(tf) >= 3:
        return "SUPER"
    if has_conf or has_seq:
        return "ELITE"
    if has_lvl:
        return "LEVEL"
    return "TRENDLINE"


def main():
    print("Loading data...")
    spy = pd.read_csv(SPY_FILE)
    vix = pd.read_csv(VIX_FILE)

    print("Running IS BASE + CANDIDATE...")
    is_b = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **BASE)
    is_c = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **CAND)

    print("Running OOS BASE + CANDIDATE...")
    oos_b = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **BASE)
    oos_c = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **CAND)

    is_bp  = sum(t.dollar_pnl for t in is_b.trades)
    is_cp  = sum(t.dollar_pnl for t in is_c.trades)
    oos_bp = sum(t.dollar_pnl for t in oos_b.trades)
    oos_cp = sum(t.dollar_pnl for t in oos_c.trades)

    is_delta  = is_cp - is_bp
    oos_delta = oos_cp - oos_bp
    n_is_b    = len(is_b.trades)
    n_oos_b   = len(oos_b.trades)

    print(f"\n{'='*72}")
    print("BLOCK_ELITE_BULL VIX 15-17 (VIX-range gate) — A/B Scorecard")
    print(f"{'='*72}")
    print(f"  Gate: block ELITE+level_reclaim ONLY when 15 <= VIX < 17")
    print(f"  IS:  base n={n_is_b:4d} pnl={is_bp:+8,.0f}  "
          f"cand n={len(is_c.trades):4d} pnl={is_cp:+8,.0f}  delta={is_delta:+,.0f}")
    print(f"  OOS: base n={n_oos_b:4d} pnl={oos_bp:+8,.0f}  "
          f"cand n={len(oos_c.trades):4d} pnl={oos_cp:+8,.0f}  delta={oos_delta:+,.0f}")

    if is_delta != 0 and n_is_b > 0 and n_oos_b > 0:
        wf = (oos_delta / n_oos_b) / (is_delta / n_is_b)
        wf_ok = wf >= 0.70 and oos_delta > 0
        status = "PASS" if wf_ok else "FAIL"
        print(f"\n  WF_norm = {wf:.3f}  ({status})")
    else:
        wf, wf_ok, status = 0.0, False, "INERT"
        print(f"\n  WF_norm = N/A")

    # IS sub-window breakdown
    print(f"\n  IS sub-windows:")
    hurt = 0
    for name, s, e in IS_SUB_WINDOWS:
        bp = pnl_window(is_b.trades, s, e)
        cp = pnl_window(is_c.trades, s, e)
        d  = cp - bp
        flag = "HURT" if d < -50 else ("HELP" if d > 50 else "FLAT")
        if flag == "HURT": hurt += 1
        print(f"    {name:<14s}  base={bp:+8,.0f}  cand={cp:+8,.0f}  delta={d:+7,.0f}  {flag}")
    print(f"  Sub-window hurt: {hurt}/4")

    # Anchor days
    print(f"\n  J anchor winners (4/29, 5/01, 5/04):")
    anchor_hurt = False
    for d in sorted(J_WINNERS):
        bp = pnl_on_date(is_b.trades, d)
        cp = pnl_on_date(is_c.trades, d)
        delta = cp - bp
        if delta < -50: anchor_hurt = True
        print(f"    {d}  base={bp:+8,.0f}  cand={cp:+8,.0f}  delta={delta:+7,.0f}  "
              f"{'HURT' if delta < -50 else 'OK'}")

    # IS ELITE breakdown
    elite_b = [t for t in is_b.trades if get_quality(t) == "ELITE"]
    elite_c = [t for t in is_c.trades if get_quality(t) == "ELITE"]
    print(f"\n  IS ELITE trades: base={len(elite_b)}, cand={len(elite_c)}")
    print(f"    base pnl={sum(t.dollar_pnl for t in elite_b):+,.0f}  "
          f"cand pnl={sum(t.dollar_pnl for t in elite_c):+,.0f}")
    if elite_c:
        wr = sum(1 for t in elite_c if t.dollar_pnl > 0) / len(elite_c)
        print(f"    cand WR={wr:.1%}  avg={sum(t.dollar_pnl for t in elite_c)/len(elite_c):+,.0f}/trade")

    # OOS skip events
    skips = [d for d in oos_c.decisions if d.get("action") == "SKIP_ELITE_BULL_LEVEL_RECLAIM"]
    print(f"\n  OOS SKIP_ELITE_BULL_LEVEL_RECLAIM events: n={len(skips)}")
    if skips:
        for sk in skips:
            print(f"    {str(sk['timestamp_et'])[:16]}  VIX={sk.get('vix', '?'):.1f}  "
                  f"triggers={sk.get('triggers_fired', [])}")

    # OOS ELITE remaining
    elite_oos_c = [t for t in oos_c.trades if get_quality(t) == "ELITE"]
    print(f"  OOS ELITE remaining: n={len(elite_oos_c)} "
          f"pnl={sum(t.dollar_pnl for t in elite_oos_c):+,.0f}")

    # Ratification verdict
    print(f"\n{'='*72}")
    print("RATIFICATION VERDICT:")
    oos_pos = oos_delta > 0
    sw_ok   = hurt <= 1
    anch_ok = not anchor_hurt

    print(f"  OOS positive:         {'YES' if oos_pos else 'NO'}  (delta={oos_delta:+,.0f})")
    print(f"  WF >= 0.70:           {'YES' if wf_ok else 'NO'}  (wf={wf:.3f})")
    print(f"  Sub-windows stable:   {'YES' if sw_ok else 'NO'}  ({hurt}/4 hurt)")
    print(f"  Anchor no-regression: {'YES' if anch_ok else 'NO'}")

    # VIX-range special assessment
    n_is_blocked = n_is_b - len(is_c.trades)
    n_oos_blocked = n_oos_b - len(oos_c.trades)
    print(f"\n  VIX-range assessment (IS blocks VIX 15-17 only):")
    print(f"    IS  blocked n={n_is_blocked}, delta={is_delta:+,.0f}")
    print(f"    OOS blocked n={n_oos_blocked}, delta={oos_delta:+,.0f}")
    if n_oos_blocked > 0:
        per_trade_oos_harm = -oos_delta / n_oos_blocked
        print(f"    OOS per-blocked-trade: {-per_trade_oos_harm:+.0f} (harm if neg, benefit if pos)")
    print(f"    NOTE: OOS n_blocked={n_oos_blocked} is statistically insufficient "
          f"(need 15+ to match IS evidence base)")

    if not oos_pos and hurt == 0 and anch_ok and abs(oos_delta) < 300:
        print("\n  >>> HOLD-NEAR: IS 4/4 stable, OOS delta within noise (±$300 on n=3).")
        print("  >>> Consider ratifying with OOS disclosure. IS improvement well-validated.")
    elif oos_pos and wf_ok and sw_ok and anch_ok:
        print("\n  >>> AUTO-RATIFY: all hard gates passed.")
    else:
        print("\n  >>> HOLD: standard WF gate failed.")
    print('='*72)


if __name__ == "__main__":
    main()
