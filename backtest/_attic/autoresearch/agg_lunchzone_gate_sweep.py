"""
AGG LUNCH-ZONE GATE SWEEP (2026-06-17)

Motivated by exit type audit: AGG IS 12:00-14:00 ET window = WR=0% (6 trades, all premium stops).
Deep-dive shows 12:00-13:00 specifically: IS n=4 WR=0% total=-$875. OOS n=1 (-$232 stop).
OOS 13:00-14:00 has 1 trade (+$1860 winner) so we must keep 13:00+ open.

Tests: block_agg_lunch_zone = no_trade_window(12:00, 13:00) for AGG.

Gates: IS_delta>0 AND OOS_delta>0 AND WF>=0.70 AND SW_hurt<=1 AND anchor_OK
Security: read-only, no Alpaca calls.
"""
from __future__ import annotations
import sys, json, datetime as dt, pathlib

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

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

IS_SUBWINDOWS = [
    ("W1 Jan-Jun 2025", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2 Jul-Dec 2025", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3 Jan-Mar 2026", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4 Apr-May 2026", dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

# AGG production params — post ENFORCED-2/3/5 (correct as of 2026-06-17)
AGG_BASE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,  # baseline: no lunch zone gate
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.07,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    block_conf_lvl_rec_afternoon=True,           # ENFORCED-2
    block_conf_lvl_rej_midday_afternoon=True,    # ENFORCED-3
    require_bearish_fill_bar=True,               # ENFORCED-5
)
AGG_OVR = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0, "strike_offset_itm": 2}

CANDIDATES = [
    ("no_gate (baseline)", None),
    ("12:00-13:00 block", (dt.time(12, 0), dt.time(13, 0))),
    ("12:00-14:00 block", (dt.time(12, 0), dt.time(14, 0))),
]


def _pnl(trades): return sum(t.dollar_pnl for t in trades)


def _by_date(trades):
    out = {}
    for t in trades:
        et = t.entry_time_et
        d = (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()
        out[d] = out.get(d, 0) + t.dollar_pnl
    return out


def _run(spy_df, vix_df, start, end, ntw):
    kw = dict(AGG_BASE_KW)
    kw["no_trade_window"] = ntw
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(AGG_OVR), **kw)


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n" + "="*90)
    print("  AGG LUNCH-ZONE GATE SWEEP")
    print("  Motivation: IS 12:00-14:00 WR=0% (6 stops, -$1,187). 12:00-13:00 sub: IS n=4 -$875, OOS n=1 -$232")
    print("="*90)

    base_is  = _run(spy_df, vix_df, IS_START, IS_END, None)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, None)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_is_n    = len(base_is.trades)
    base_oos_n   = len(base_oos.trades)
    base_by      = _by_date(base_is.trades)
    print(f"\nBaseline: IS n={base_is_n} pnl={base_is_pnl:+,.0f} | OOS n={base_oos_n} pnl={base_oos_pnl:+,.0f}")

    for cname, ntw in CANDIDATES[1:]:
        print(f"\n--- {cname} ---")
        cand_is  = _run(spy_df, vix_df, IS_START, IS_END, ntw)
        cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, ntw)
        is_d     = _pnl(cand_is.trades) - base_is_pnl
        oos_d    = _pnl(cand_oos.trades) - base_oos_pnl
        is_n     = len(cand_is.trades)
        oos_n    = len(cand_oos.trades)

        if is_d <= 0:
            gate = "L155"
            wf_str = "L155"
            wf = float("nan")
        else:
            wf = (oos_d / base_oos_n) / (is_d / base_is_n)
            wf_str = f"{wf:.3f}"

        print(f"  IS:  n={is_n} pnl={_pnl(cand_is.trades):+,.0f} delta={is_d:+,.0f}")
        print(f"  OOS: n={oos_n} pnl={_pnl(cand_oos.trades):+,.0f} delta={oos_d:+,.0f}")
        print(f"  WF={wf_str}  OOS_pos={'YES' if oos_d > 0 else 'NO'}")

        if is_d > 0:
            # Sub-window analysis
            sw_hurts = 0
            for sw_label, s, e in IS_SUBWINDOWS:
                b_sw = _run(spy_df, vix_df, s, e, None)
                c_sw = _run(spy_df, vix_df, s, e, ntw)
                sw_d = _pnl(c_sw.trades) - _pnl(b_sw.trades)
                verdict = "HURT" if sw_d < -500 else ("HELP" if sw_d > 100 else "neutral")
                if verdict == "HURT": sw_hurts += 1
                print(f"    {sw_label}: base={_pnl(b_sw.trades):+,.0f} cand={_pnl(c_sw.trades):+,.0f} d={sw_d:+,.0f} {verdict}")

            # Anchor check
            cand_by = _by_date(cand_is.trades)
            anchor_fails = []
            for d in sorted(J_WINNERS):
                bp = base_by.get(d, 0.0); cp = cand_by.get(d, 0.0)
                if bp > 0 and cp < bp * 0.90:
                    anchor_fails.append(str(d))

            # Gates
            oos_pos = oos_d > 0
            wf_ok   = wf >= 0.70
            sw_ok   = sw_hurts <= 1
            anc_ok  = len(anchor_fails) == 0

            if not oos_pos:  gate = "OOS_NEG"
            elif not wf_ok:  gate = "WF_LOW"
            elif not sw_ok:  gate = "SW_HURT"
            elif not anc_ok: gate = f"ANCHOR_FAIL({','.join(anchor_fails)})"
            else:            gate = "PASS"

            print(f"  SW_hurt={sw_hurts}/4  anchor={'OK' if anc_ok else 'FAIL'}  -> {gate}")

        # Show blocked trades
        base_entries = {t.entry_time_et for t in base_is.trades}
        cand_entries = {t.entry_time_et for t in cand_is.trades}
        blocked = [t for t in base_is.trades if t.entry_time_et not in cand_entries]
        if blocked:
            print(f"  IS blocked trades (n={len(blocked)}):")
            for t in sorted(blocked, key=lambda x: (x.entry_time_et.replace(tzinfo=None) if getattr(x.entry_time_et,'tzinfo',None) else x.entry_time_et)):
                et = t.entry_time_et.replace(tzinfo=None) if getattr(t.entry_time_et,'tzinfo',None) else t.entry_time_et
                triggers = sorted(set(getattr(t,'triggers_fired',[]) or []))
                print(f"    {et.strftime('%H:%M')} {et.date()}  pnl={t.dollar_pnl:+.0f}  triggers={triggers}")

        base_oos_entries = {t.entry_time_et for t in base_oos.trades}
        cand_oos_entries = {t.entry_time_et for t in cand_oos.trades}
        blocked_oos = [t for t in base_oos.trades if t.entry_time_et not in cand_oos_entries]
        if blocked_oos:
            print(f"  OOS blocked trades (n={len(blocked_oos)}):")
            for t in sorted(blocked_oos, key=lambda x: (x.entry_time_et.replace(tzinfo=None) if getattr(x.entry_time_et,'tzinfo',None) else x.entry_time_et)):
                et = t.entry_time_et.replace(tzinfo=None) if getattr(t.entry_time_et,'tzinfo',None) else t.entry_time_et
                triggers = sorted(set(getattr(t,'triggers_fired',[]) or []))
                print(f"    {et.strftime('%H:%M')} {et.date()}  pnl={t.dollar_pnl:+.0f}  triggers={triggers}")

    print("\nSWEEP COMPLETE.")
