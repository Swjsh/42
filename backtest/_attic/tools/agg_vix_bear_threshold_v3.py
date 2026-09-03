"""AGG vix_bear_threshold sweep v3.

Fixes v1 (agg_vix_bear_threshold_sweep.py): G5 used zero-tolerance anchor
block check instead of the standard OP-22 10%-tolerance formula.
Fixes v2 (agg_vix_bear_threshold_v2.py): used WRONG AGG params (SAFE-like
no_trade_window, min_triggers_bull=2, strike_offset=+2, vbt=17.3 baseline).

v3 is canonical:
  - Correct AGG_KWARGS (matching agg_tp1_threshold_sweep.py's AGG_BASE)
  - Correct OP-22 G5: curr_anchor >= base_anchor - abs(base_anchor)*0.10
  - Post-hoc VIX filter (1 engine run per period, O(1) sweep)
  - Baseline = 15.0 (AGG production)
  - Thresholds [15.0, 15.5, 16.0, 16.5, 17.0, 17.3, 17.5, 18.0]

Security: read-only (except output). No Alpaca calls.
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
from sniper_matrix import norm_str  # noqa

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "agg_vix_bear_threshold_v3.json"

IS_CUTOFF  = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2",  dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26", dt.date(2026,1,2),  dt.date(2026,2,26)),
]

BASELINE_VBT = 15.0
THRESHOLDS   = [15.0, 15.5, 16.0, 16.5, 17.0, 17.3, 17.5, 18.0]

# Correct AGG params (matches agg_tp1_threshold_sweep.py AGG_BASE — production 2026-06-18)
AGG_KWARGS = dict(
    use_real_fills=True, strike_offset=-2,
    premium_stop_pct_bear=-0.07, premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75, tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0, f9_vol_mult=0.7,
    min_triggers_bear=1, min_triggers_bull=1,
    no_trade_before=dt.time(9, 35), no_trade_window=None,
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True, midday_trendline_gate=True,
    block_elite_bull=True, block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=18.0,
    require_bearish_fill_bar=True, time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.5, enable_bullish=True,
    params_overrides={"vix_bear_threshold": BASELINE_VBT},
)


def get_vix_at_entry(vix_df, entry_dt):
    date_str = str(entry_dt.date() if hasattr(entry_dt, 'date') else entry_dt)
    rows = vix_df[vix_df["timestamp_et"].str.startswith(date_str)]
    morning = rows[rows["timestamp_et"].str[11:16] >= "09:35"]
    if len(morning) == 0:
        return float(rows.iloc[0]["close"]) if len(rows) > 0 else None
    return float(morning.iloc[0]["close"])


def annotate_trades(raw_trades, vix_df):
    out = []
    for t in raw_trades:
        vix_val = getattr(t, 'entry_vix', None)
        if vix_val is None:
            vix_val = get_vix_at_entry(vix_df, t.entry_time_et)
        out.append({
            "date":   t.entry_time_et.date(),
            "entry_dt": t.entry_time_et,
            "side":   t.side,
            "pnl":    round(t.dollar_pnl, 2),
            "vix":    vix_val,
        })
    return out


def filter_trades(trades, thr):
    return [t for t in trades if t["side"] == "C" or (t["vix"] is not None and t["vix"] > thr)]


def stats_from_list(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t["pnl"] for t in trades]
    return {
        "n":    len(pnls),
        "wr":   round(sum(p > 0 for p in pnls) / len(pnls), 3),
        "avg":  round(sum(pnls) / len(pnls), 1),
        "total": round(sum(pnls), 1),
    }


def main():
    print("=" * 70)
    print("AGG VIX BEAR THRESHOLD SWEEP v3 (correct OP-22 G5 formula)")
    print(f"Baseline={BASELINE_VBT}  Thresholds={THRESHOLDS}")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))

    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES_SET]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]

    print(f"IS: {len(is_days)} days ({is_days[0]} to {is_days[-1]})")
    print(f"OOS: {len(oos_days)} days ({oos_days[0]} to {oos_days[-1]})")

    print("\nRunning baseline IS engine (once)...")
    r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **AGG_KWARGS)
    is_trades = annotate_trades(r_is.trades, vix_df)
    print(f"  IS: {len(is_trades)} trades, total={sum(t['pnl'] for t in is_trades):+.0f}")

    print("Running baseline OOS engine (once)...")
    r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **AGG_KWARGS)
    oos_trades = annotate_trades(r_oos.trades, vix_df)
    print(f"  OOS: {len(oos_trades)} trades, total={sum(t['pnl'] for t in oos_trades):+.0f}")

    # VIX breakdown of OOS bears
    bear_oos = [t for t in oos_trades if t["side"] == "P" and t["vix"] is not None]
    print(f"\nOOS bear VIX breakdown (n={len(bear_oos)}):")
    for lo, hi in [(0,15), (15,16), (16,17), (17,17.5), (17.5,18), (18,20), (20,99)]:
        bucket = [t for t in bear_oos if lo <= t["vix"] < hi]
        if bucket:
            s = stats_from_list(bucket)
            print(f"  VIX [{lo:<4.1f}-{hi:<4.1f}): n={s['n']:2} WR={s['wr']:.1%} avg={s['avg']:>+.0f} total={s['total']:>+.0f}")

    # Baseline metrics
    b_is  = stats_from_list(is_trades)
    b_oos = stats_from_list(oos_trades)
    b_pnl_is  = b_is["total"]
    b_pnl_oos = b_oos["total"]

    # Anchor baseline: P&L on anchor-winner days in OOS
    b_anchor = sum(t["pnl"] for t in oos_trades if t["date"] in ANCHOR_WINNERS)
    print(f"\nBaseline IS:  n={b_is['n']} WR={b_is['wr']:.1%} total={b_pnl_is:+.0f}")
    print(f"Baseline OOS: n={b_oos['n']} WR={b_oos['wr']:.1%} total={b_pnl_oos:+.0f}")
    print(f"Baseline anchor (4/29, 5/1, 5/4): {b_anchor:+.0f}")

    # Anchor-winner VIX detail
    print("\nAnchor-winner OOS bear trades:")
    for t in sorted([x for x in oos_trades if x["date"] in ANCHOR_WINNERS], key=lambda x: x["date"]):
        print(f"  {t['date']} side={t['side']} VIX={t['vix']} pnl={t['pnl']:+.0f}")

    anchor_tol = abs(b_anchor) * 0.10

    print(f"\n  {'thr':>5} {'IS_n':>5} {'IS_tot':>9} {'IS_D':>8} "
          f"{'OOS_n':>6} {'OOS_tot':>9} {'OOS_D':>8} {'WF':>8} {'SW':>4} {'G5':>4} {'PASS':>4}")
    print("  " + "-" * 100)

    results = []
    for thr in THRESHOLDS:
        fi = filter_trades(is_trades, thr)
        fo = filter_trades(oos_trades, thr)
        si  = stats_from_list(fi)
        so  = stats_from_list(fo)
        is_d  = round(si["total"] - b_pnl_is,  1)
        oos_d = round(so["total"] - b_pnl_oos, 1)

        if thr == BASELINE_VBT:
            print(f"  {thr:>5.1f} {si['n']:>5} {si['total']:>+9.0f} {'--':>8} "
                  f"{so['n']:>6} {so['total']:>+9.0f} {'--':>8} {'--':>8} {'--':>4} {'--':>4} {'BASE':>4}")
            results.append({"thr": thr, "verdict": "BASELINE"})
            continue

        n_rem_is  = b_is["n"]  - si["n"]
        n_rem_oos = b_oos["n"] - so["n"]

        wf = None
        if n_rem_is > 0 and is_d != 0 and n_rem_oos > 0:
            per_is  = is_d / n_rem_is
            per_oos = oos_d / n_rem_oos if n_rem_oos > 0 else 0
            if per_is != 0:
                wf = round(per_oos / per_is, 3)

        sw_h = 0
        for _name, sw_s, sw_e in SW_SPLITS:
            sw_t = [t for t in is_trades if sw_s <= t["date"] <= sw_e]
            sw_b  = stats_from_list(sw_t)["total"]
            sw_f  = stats_from_list(filter_trades(sw_t, thr))["total"]
            if sw_f < sw_b:
                sw_h += 1

        curr_anchor = sum(t["pnl"] for t in oos_trades if t["date"] in ANCHOR_WINNERS
                          and (t["side"] == "C" or (t["vix"] is not None and t["vix"] > thr)))
        g5 = curr_anchor >= b_anchor - anchor_tol if b_anchor != 0 else curr_anchor >= 0

        g1 = is_d >= 0
        g2 = oos_d > 0
        g3 = wf is not None and wf >= 0.70
        g4 = sw_h <= 1
        passed = g1 and g2 and g3 and g4 and g5
        wf_str = f"{wf:.3f}" if wf is not None else "N/A"

        print(f"  {thr:>5.1f} {si['n']:>5} {si['total']:>+9.0f} {is_d:>+8.0f} "
              f"{so['n']:>6} {so['total']:>+9.0f} {oos_d:>+8.0f} "
              f"{wf_str:>8} {sw_h:>4} {'Y' if g5 else 'N':>4} {'Y' if passed else 'N':>4}")
        print(f"       G1={g1} G2={g2} G3={g3} G4={g4} G5={g5}  "
              f"anchor={curr_anchor:+.0f}/{b_anchor:+.0f}(tol={anchor_tol:.0f})  "
              f"rem_IS={n_rem_is} rem_OOS={n_rem_oos}")

        # Show which anchor bears are blocked at this threshold
        blocked_anchors = [t for t in oos_trades
                           if t["date"] in ANCHOR_WINNERS and t["side"] == "P"
                           and t["vix"] is not None and t["vix"] <= thr]
        if blocked_anchors:
            for ba in blocked_anchors:
                print(f"       BLOCKED anchor: {ba['date']} VIX={ba['vix']:.1f} pnl={ba['pnl']:+.0f}")

        results.append({
            "thr": thr, "is": si, "oos": so,
            "is_delta": is_d, "oos_delta": oos_d,
            "wf_norm": wf, "sw_hurt": sw_h,
            "curr_anchor": curr_anchor, "base_anchor": b_anchor, "anchor_tol": anchor_tol,
            "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": passed},
        })

    passing = [r for r in results if r.get("gates", {}).get("all")]
    best = max(passing, key=lambda r: r["oos_delta"]) if passing else None

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    if best:
        print(f"  RATIFY vix_bear_threshold = {best['thr']:.1f}")
        print(f"  IS_delta={best['is_delta']:+.0f}  OOS_delta={best['oos_delta']:+.0f}  "
              f"WF={best['wf_norm']}  SW_hurt={best['sw_hurt']}")
        print(f"  Update: automation/state/aggressive/params.json")
        print(f"    vix_entry_thresholds.bear_min_exclusive_and_rising -> {best['thr']:.1f}")
    else:
        print("  REJECT - no candidate cleared all OP-22 gates.")
        best_oos = max((r for r in results if r.get("gates") is not None),
                       key=lambda r: r["oos_delta"], default=None)
        if best_oos:
            print(f"  Best OOS: thr={best_oos['thr']} OOS_D={best_oos['oos_delta']:+.0f} "
                  f"gates={best_oos['gates']}")

    out = {
        "task": "agg-vix-bear-threshold-v3",
        "version": "v3-correct-G5",
        "baseline_vbt": BASELINE_VBT,
        "thresholds_tested": THRESHOLDS,
        "base_anchor": b_anchor,
        "anchor_tol": anchor_tol,
        "sweep_results": results,
        "best": best,
        "auto_ratify": best is not None,
        "ratify_value": best["thr"] if best else None,
        "verdict": "RATIFY" if best else "REJECT",
        "note": ("v1 had wrong G5 (zero-tolerance); "
                 "v2 had wrong AGG params (strike_offset=+2, vbt=17.3, SAFE-like params); "
                 "v3 is canonical."),
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("AGG VIX BEAR THRESHOLD V3 COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
