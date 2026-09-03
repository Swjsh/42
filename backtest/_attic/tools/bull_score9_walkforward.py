"""Bull A5 (bull_score>=9) IS/OOS walk-forward.

Task c88eb9e0: Investigate the A5 signal (bull_score>=9, 2-miss bull) as a
standalone bull strategy candidate. During the gate-relaxation sweep, A5
produced edge_capture=1818, correctly taking CALL positions on J's loser
PUT days (5/05 +204, 5/06 +317, 5/07 +178).

Walk-forward split per task:
  IS  (train): 2025-01-02 to 2025-09-30
  OOS (test):  2025-10-01 to 2026-06-16

Method:
  1. Run backtest with bull-permissive settings (block_elite_bull=False,
     block_conf_lvl_rec_afternoon=False for bull, require_bearish_fill_bar=False).
  2. Filter side=C trades only (bull positions).
  3. Use n_triggers as quality proxy since bull_score is not in TradeFill.
     n_triggers >= 1 = minimal, >= 2 = ELITE quality (correlates with score>=9).
  4. Report N, WR, avg_pnl, total per quality tier.
  5. Check anchor days: 5/05, 5/06, 5/07 (OOS PUT-loser days that A5 turned CALL winners).
  6. Compute WF_norm and edge_capture.
  7. Check OP-22 auto-ratify gates vs bearish-only baseline.

Security: read-only. No Alpaca calls. No production state writes.
"""
from __future__ import annotations
import sys, json, datetime as dt
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa: E402

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "bull_score9_walkforward.json"

# Walk-forward IS/OOS per task (different from standard 287-day IS)
IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2025, 9, 30)
OOS_START = dt.date(2025, 10, 1)
OOS_END   = dt.date(2026, 6, 16)

MDATES_SET = {dt.date(2026, 5, 26), dt.date(2026, 5, 27),
              dt.date(2026, 5, 28), dt.date(2026, 5, 29)}

# J's anchor days (from CLAUDE.md OP-16):
ANCHOR_WINNERS_BEAR = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
ANCHOR_LOSERS_BEAR  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}
# A5 bull "anchor" days — bear-loser days where bull correctly fires:
A5_CHECK_DAYS = {dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 5, 7)}

SW_SPLITS = [
    ("SW1_2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("SW2_2025H2", dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("SW3_OOS_Q4", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("SW4_OOS_26", dt.date(2026, 1, 2),  dt.date(2026, 6, 16)),
]

# Bull-permissive AGG params — enable bull, relax blocking
# A5 = bull_score>=9 = at most 2 misses. Diagnostics show filters 8+9 (VIX gates)
# are the universal blockers. disable_filters=[8,9] implements A5: auto-pass VIX
# filters so all remaining 9 filters must pass (mirrors the gate-relaxation sweep
# that found A5 edge_capture=1818).
# Note: disable_filters applies to BOTH bear and bull evaluations, but
# min_triggers_bear=99 ensures no bear trades fire regardless.
BULL_KWARGS = dict(
    use_real_fills=True,
    strike_offset=2,           # OTM-2 for calls (bullish = long calls)
    premium_stop_pct_bear=-0.07,
    premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    f9_vol_mult=0.7,
    min_triggers_bear=99,      # effectively disable bearish (can't get 99 triggers)
    min_triggers_bull=1,
    no_trade_before=dt.time(10, 0),   # bull gate: start at 10:00 (Filter 1)
    no_trade_window=None,
    block_level_rejection=False,
    block_conf_lvl_rec_afternoon=False,
    block_conf_lvl_rej_midday_afternoon=False,
    midday_trendline_gate=False,
    block_elite_bull=False,           # KEY: allow elite bull entries at all VIX
    require_bearish_fill_bar=False,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.5,
    enable_bullish=True,
    disable_filters=[8, 9],    # A5: auto-pass VIX filters (the 2 "allowed misses")
    params_overrides={"vix_bear_threshold": 99.0},  # disable VIX bear gate
)


def get_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def load_spy_vix():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"), key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_name = spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(DATA / vix_name))
    print(f"  SPY: {spy_path.name}")
    return spy_df, vix_df


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "avg_pnl": 0.0, "total_pnl": 0.0, "sharpe": None}
    n = len(trades)
    pnls = [t.dollar_pnl for t in trades]
    total = round(sum(pnls), 1)
    wins = sum(1 for p in pnls if p > 0)
    avg = round(total / n, 1)
    # Simple Sharpe: mean / std per trade
    import statistics as _s
    std = _s.stdev(pnls) if n > 1 else 0.0
    sharpe = round(avg / std, 3) if std > 0 else None
    return {"n": n, "wr": round(wins / n, 3), "avg_pnl": avg, "total_pnl": total, "sharpe": sharpe}


def print_stats(label, trades):
    s = stats(trades)
    print(f"  {label:<30} n={s['n']:<5} WR={s['wr']:.1%}  avg={s['avg_pnl']:>+7.0f}  "
          f"total={s['total_pnl']:>+8.0f}  sharpe={s['sharpe']}")


def main():
    print("=" * 70)
    print("BULL A5 (bull_score>=9) WALK-FORWARD ANALYSIS")
    print("=" * 70)

    print("\n[1] Loading data...")
    spy_df, vix_df = load_spy_vix()

    all_fill_days = get_fill_days()

    is_days  = [d for d in all_fill_days if IS_START  <= d <= IS_END  and d not in MDATES_SET]
    oos_days = [d for d in all_fill_days if OOS_START <= d <= OOS_END and d not in MDATES_SET]
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    oos_days = [d for d in oos_days if d in spy_dates]

    print(f"\n[2] Date ranges:")
    print(f"    IS:  {len(is_days)} fill days ({is_days[0]} to {is_days[-1]})")
    print(f"    OOS: {len(oos_days)} fill days ({oos_days[0]} to {oos_days[-1]})")

    print("\n[3] Running IS backtest (bull-permissive)...")
    is_result = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **BULL_KWARGS)
    is_all    = is_result.trades
    is_bull   = [t for t in is_all if t.side == "C"]
    is_bear   = [t for t in is_all if t.side == "P"]
    print(f"    -> total={len(is_all)} | bull={len(is_bull)} | bear={len(is_bear)}")

    print("\n[4] Running OOS backtest (bull-permissive)...")
    oos_result = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **BULL_KWARGS)
    oos_all   = oos_result.trades
    oos_bull  = [t for t in oos_all if t.side == "C"]
    oos_bear  = [t for t in oos_all if t.side == "P"]
    print(f"    -> total={len(oos_all)} | bull={len(oos_bull)} | bear={len(oos_bear)}")

    # ── Bull trade quality breakdown by trigger count ─────────────────────
    print("\n[5a] IS — bull by n_triggers (quality proxy):")
    print(f"  {'n_trig':<8} {'n':>4} {'WR':>6} {'avg_pnl':>8} {'total':>8}")
    print(f"  {'-'*40}")
    for ntrig in sorted(set(len(t.triggers_fired) for t in is_bull)):
        grp = [t for t in is_bull if len(t.triggers_fired) == ntrig]
        pnls = [t.dollar_pnl for t in grp]
        wins = sum(1 for p in pnls if p > 0)
        n = len(grp)
        print(f"  {ntrig:<8} {n:>4} {wins/n:>6.1%} {sum(pnls)/n:>+8.0f} {sum(pnls):>+8.0f}")

    print("\n[5b] OOS — bull by n_triggers (quality proxy):")
    print(f"  {'n_trig':<8} {'n':>4} {'WR':>6} {'avg_pnl':>8} {'total':>8}")
    print(f"  {'-'*40}")
    for ntrig in sorted(set(len(t.triggers_fired) for t in oos_bull)):
        grp = [t for t in oos_bull if len(t.triggers_fired) == ntrig]
        pnls = [t.dollar_pnl for t in grp]
        wins = sum(1 for p in pnls if p > 0)
        n = len(grp)
        print(f"  {ntrig:<8} {n:>4} {wins/n:>6.1%} {sum(pnls)/n:>+8.0f} {sum(pnls):>+8.0f}")

    # ── Primary stats: all bull vs >=2 triggers ───────────────────────────
    print("\n[6] Bull performance summary:")
    is_bull_2t  = [t for t in is_bull  if len(t.triggers_fired) >= 2]
    oos_bull_2t = [t for t in oos_bull if len(t.triggers_fired) >= 2]
    print_stats("IS  all bull", is_bull)
    print_stats("IS  bull 2+ triggers", is_bull_2t)
    print_stats("OOS all bull", oos_bull)
    print_stats("OOS bull 2+ triggers", oos_bull_2t)

    # ── Walk-forward calc ─────────────────────────────────────────────────
    is_n   = len(is_bull_2t) if is_bull_2t else len(is_bull)
    is_pnl = sum(t.dollar_pnl for t in (is_bull_2t or is_bull))
    oos_n  = len(oos_bull_2t) if oos_bull_2t else len(oos_bull)
    oos_pnl = sum(t.dollar_pnl for t in (oos_bull_2t or oos_bull))
    # WF_norm: OOS per-trade PnL / IS per-trade PnL
    is_per_trade  = is_pnl  / is_n  if is_n  > 0 else 0
    oos_per_trade = oos_pnl / oos_n if oos_n > 0 else 0
    wf_norm = round(oos_per_trade / is_per_trade, 3) if is_per_trade > 0 else None

    print(f"\n  Walk-forward (2-trigger bull): IS avg={is_per_trade:+.0f}/trade, OOS avg={oos_per_trade:+.0f}/trade")
    print(f"  WF_norm = {wf_norm} (threshold: 0.70)")

    # ── Anchor day check ──────────────────────────────────────────────────
    print(f"\n[7] A5 anchor day check (J's PUT-loser days where bull should fire):")
    all_bull = is_bull + oos_bull
    for d in sorted(A5_CHECK_DAYS):
        day_bull = [t for t in all_bull if t.entry_time_et.date() == d]
        if day_bull:
            pnls = [t.dollar_pnl for t in day_bull]
            wins = sum(1 for p in pnls if p > 0)
            print(f"  {d}: n={len(day_bull)} WR={wins/len(day_bull):.0%} "
                  f"total={sum(pnls):+.0f} avg={sum(pnls)/len(day_bull):+.0f}")
            for t in day_bull:
                entry_dt = t.entry_time_et
                if hasattr(entry_dt, "tzinfo") and entry_dt.tzinfo is not None:
                    entry_dt = entry_dt.replace(tzinfo=None)
                print(f"    -> {entry_dt.strftime('%H:%M')} trig={t.triggers_fired} "
                      f"pnl={t.dollar_pnl:+.0f}")
        else:
            print(f"  {d}: NO bull trade fired")

    # ── Sub-window stability ───────────────────────────────────────────────
    print("\n[8] Sub-window bull performance (all bull):")
    print(f"  {'window':<20} {'n':>4} {'WR':>6} {'avg_pnl':>8} {'total':>8}")
    print(f"  {'-'*50}")
    all_bull = is_bull + oos_bull
    for sw_name, sw_start, sw_end in SW_SPLITS:
        sw_grp = [t for t in all_bull if sw_start <= t.entry_time_et.date() <= sw_end]
        if sw_grp:
            pnls = [t.dollar_pnl for t in sw_grp]
            wins = sum(1 for p in pnls if p > 0)
            n = len(sw_grp)
            print(f"  {sw_name:<20} {n:>4} {wins/n:>6.1%} {sum(pnls)/n:>+8.0f} {sum(pnls):>+8.0f}")
        else:
            print(f"  {sw_name:<20}    0")

    # ── Edge capture ──────────────────────────────────────────────────────
    # Edge capture is measured vs the BEAR-only baseline
    # For bear-only baseline: run with same settings but enable_bullish=False
    print("\n[9] Running bear-only baseline (same period, bull disabled)...")
    bear_kwargs = dict(BULL_KWARGS)
    bear_kwargs["enable_bullish"] = False
    bear_kwargs["min_triggers_bear"] = 1
    bear_kwargs["params_overrides"] = {"vix_bear_threshold": 15.0}
    bear_kwargs["block_level_rejection"] = True
    bear_kwargs["midday_trendline_gate"] = True
    bear_kwargs["block_conf_lvl_rec_afternoon"] = True
    bear_kwargs["block_conf_lvl_rej_midday_afternoon"] = True

    is_bear_result  = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **bear_kwargs)
    oos_bear_result = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **bear_kwargs)
    is_bear_pnl  = sum(t.dollar_pnl for t in is_bear_result.trades)
    oos_bear_pnl = sum(t.dollar_pnl for t in oos_bear_result.trades)
    print(f"  IS bear-only: n={len(is_bear_result.trades)} total={is_bear_pnl:+.0f}")
    print(f"  OOS bear-only: n={len(oos_bear_result.trades)} total={oos_bear_pnl:+.0f}")

    # Edge capture: bull complement on anchor days
    is_bull_pnl  = sum(t.dollar_pnl for t in is_bull)
    oos_bull_pnl = sum(t.dollar_pnl for t in oos_bull)
    edge_capture = oos_bull_pnl  # bull P&L on OOS period

    print(f"\n  IS  bull complement: {is_bull_pnl:+.0f}")
    print(f"  OOS bull complement: {oos_bull_pnl:+.0f}")
    print(f"  Hypothetical combined IS:  {is_bear_pnl + is_bull_pnl:+.0f} (bear {is_bear_pnl:+.0f} + bull {is_bull_pnl:+.0f})")
    print(f"  Hypothetical combined OOS: {oos_bear_pnl + oos_bull_pnl:+.0f} (bear {oos_bear_pnl:+.0f} + bull {oos_bull_pnl:+.0f})")

    # ── Verdict ───────────────────────────────────────────────────────────
    bull_is_stat  = stats(is_bull)
    bull_oos_stat = stats(oos_bull)

    wf_eligible = (wf_norm is not None and wf_norm >= 0.70
                   and bull_oos_stat["wr"] > 0.0 and oos_bull_pnl > 0)
    threshold_wr = bull_is_stat["wr"] >= 0.40
    threshold_n  = bull_is_stat["n"] >= 10

    print(f"\n{'='*70}")
    print("VERDICT SUMMARY")
    print(f"{'='*70}")
    print(f"  IS  bull: n={bull_is_stat['n']} WR={bull_is_stat['wr']:.1%} avg={bull_is_stat['avg_pnl']:+.0f}")
    print(f"  OOS bull: n={bull_oos_stat['n']} WR={bull_oos_stat['wr']:.1%} avg={bull_oos_stat['avg_pnl']:+.0f}")
    print(f"  WF_norm={wf_norm}  WR>=40%: {'YES' if threshold_wr else 'NO'}  n>=10: {'YES' if threshold_n else 'NO'}")
    if wf_eligible and threshold_wr and threshold_n:
        print("  -> RECOMMEND: Activate bull strategy (standalone IS+OOS confirmed)")
    elif oos_bull_pnl > 0 and bull_oos_stat["n"] >= 5:
        print("  -> PROMISING: OOS positive but insufficient sample/WF. Continue monitoring.")
    else:
        print("  -> INSUFFICIENT: Bull signal not ready as standalone strategy.")

    # ── Save ─────────────────────────────────────────────────────────────
    scorecard = {
        "task": "c88eb9e0-bull-a5-walkforward",
        "is_dates": [str(IS_START), str(IS_END)],
        "oos_dates": [str(OOS_START), str(OOS_END)],
        "is_bull": {
            "n": len(is_bull),
            "total_pnl": round(is_bull_pnl, 1),
            "avg_pnl": round(is_bull_pnl / len(is_bull), 1) if is_bull else 0,
            "wr": round(sum(1 for t in is_bull if t.dollar_pnl > 0) / len(is_bull), 3) if is_bull else 0,
        },
        "oos_bull": {
            "n": len(oos_bull),
            "total_pnl": round(oos_bull_pnl, 1),
            "avg_pnl": round(oos_bull_pnl / len(oos_bull), 1) if oos_bull else 0,
            "wr": round(sum(1 for t in oos_bull if t.dollar_pnl > 0) / len(oos_bull), 3) if oos_bull else 0,
        },
        "is_bull_2t": {
            "n": len(is_bull_2t),
            "total_pnl": round(sum(t.dollar_pnl for t in is_bull_2t), 1),
        },
        "oos_bull_2t": {
            "n": len(oos_bull_2t),
            "total_pnl": round(sum(t.dollar_pnl for t in oos_bull_2t), 1),
        },
        "wf_norm": wf_norm,
        "is_bear_baseline_pnl": round(is_bear_pnl, 1),
        "oos_bear_baseline_pnl": round(oos_bear_pnl, 1),
        "anchor_a5_check": {
            str(d): {
                "bull_trades": [
                    {"time": str(t.entry_time_et), "pnl": round(t.dollar_pnl, 2),
                     "triggers": t.triggers_fired}
                    for t in (is_bull + oos_bull) if t.entry_time_et.date() == d
                ]
            } for d in sorted(A5_CHECK_DAYS)
        },
        "recommendation": "RECOMMEND" if (wf_eligible and threshold_wr and threshold_n) else
                          "PROMISING" if (oos_bull_pnl > 0 and bull_oos_stat["n"] >= 5) else
                          "INSUFFICIENT",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("BULL A5 WALK-FORWARD COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
