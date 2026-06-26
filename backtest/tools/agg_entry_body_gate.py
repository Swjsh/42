"""AGG (Gamma-Bold/Risky-2) entry bar body_pct gate A/B.

SAFE body gate ratified 2026-06-18: block BEAR entries where entry bar body_pct < 0.20.
This script tests the same gate on AGG, which already has require_bearish_fill_bar=True.

The two gates are orthogonal:
  - fill_bar: next bar (N+1) must close bearish (next-bar confirmation)
  - body_gate: current entry bar (N+0) must have body_pct >= 0.20 (strong directional candle)

Per C29: "Exit target/stop knobs ratified on one account don't transfer to another without fresh A/B."
AGG has different strike (ITM-2 vs OTM-2), different stop (-7% vs -10%), different TP1 (+75% vs +50%).
Must run fresh A/B even though SAFE passed.

AGG BASELINE (current live config as of 2026-06-18):
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import Counter

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "agg_entry_body_gate.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES    = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_W  = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}
SW_SPLITS = [
    ("SW1_2025H1", dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2", dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26",dt.date(2026,1,2),  dt.date(2026,2,26)),
]

# AGG baseline — all current live gates (as of 2026-06-18 params.json)
AGG_BASE = dict(
    use_real_fills=True, strike_offset=2,     # ITM-2 (positive = ITM)
    premium_stop_pct_bear=-0.07, premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75, tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0, f9_vol_mult=0.7,
    min_triggers_bear=1, min_triggers_bull=1,
    no_trade_before=dt.time(9, 35),           # no midday blackout for AGG
    midday_trendline_gate=True,
    block_level_rejection=True,
    block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=18.0,
    require_bearish_fill_bar=True,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.5, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 15.0, "vix_bull_hard_cap": 30.0},
)


def naive(ts):
    return ts.replace(tzinfo=None) if ts.tzinfo else ts


def stats(ts):
    if not ts:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t.dollar_pnl for t in ts]
    return {"n": len(ts), "wr": round(sum(p > 0 for p in pnls) / len(ts), 3),
            "avg": round(sum(pnls) / len(ts), 1), "total": round(sum(pnls), 1)}


def main():
    print("=" * 70)
    print("AGG ENTRY BAR BODY PCT GATE (block body_pct < 0.20)")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))

    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES and d in spy_dates]
    print(f"IS: {len(is_days)} | OOS: {len(oos_days)}")

    print("Running IS baseline (all AGG gates)...")
    r_ib = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **AGG_BASE)
    print("Running IS candidate (+ body_pct gate)...")
    r_ic = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1],
                        entry_bar_body_pct_min=0.20, **AGG_BASE)
    print("Running OOS baseline...")
    r_ob = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **AGG_BASE)
    print("Running OOS candidate...")
    r_oc = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1],
                        entry_bar_body_pct_min=0.20, **AGG_BASE)

    s_ib, s_ic = stats(r_ib.trades), stats(r_ic.trades)
    s_ob, s_oc = stats(r_ob.trades), stats(r_oc.trades)

    n_rem_is  = s_ib["n"] - s_ic["n"]
    n_rem_oos = s_ob["n"] - s_oc["n"]
    is_d  = round(s_ic["total"] - s_ib["total"], 1)
    oos_d = round(s_oc["total"] - s_ob["total"], 1)

    per_is  = is_d  / n_rem_is  if n_rem_is  > 0 else None
    per_oos = oos_d / n_rem_oos if n_rem_oos > 0 else None
    wf = round(per_oos / per_is, 3) if (per_is is not None and per_oos is not None and per_is != 0) else None

    sw_hurt = 0
    sw_rows = []
    for lbl, sw_s, sw_e in SW_SPLITS:
        b_sw = sum(t.dollar_pnl for t in r_ib.trades if sw_s <= naive(t.entry_time_et).date() <= sw_e)
        c_sw = sum(t.dollar_pnl for t in r_ic.trades if sw_s <= naive(t.entry_time_et).date() <= sw_e)
        hurt = c_sw < b_sw
        if hurt:
            sw_hurt += 1
        sw_rows.append({"label": lbl, "baseline": round(b_sw,1), "candidate": round(c_sw,1),
                        "delta": round(c_sw-b_sw,1), "hurt": hurt})
        print(f"  {lbl}: baseline={b_sw:+.0f} cand={c_sw:+.0f} delta={c_sw-b_sw:+.0f}")

    b_anch = sum(t.dollar_pnl for t in r_ob.trades if naive(t.entry_time_et).date() in ANCHOR_W)
    c_anch = sum(t.dollar_pnl for t in r_oc.trades if naive(t.entry_time_et).date() in ANCHOR_W)
    tol = abs(b_anch) * 0.10 if b_anch != 0 else 0
    g5 = c_anch >= b_anch - tol if b_anch != 0 else c_anch >= 0

    g1 = is_d >= 0
    g2 = oos_d > 0
    g3 = wf is not None and wf >= 0.70
    g4 = sw_hurt <= 1
    passed = g1 and g2 and g3 and g4 and g5

    wf_str = f"{wf:.3f}" if wf is not None else "N/A"
    print(f"\nIS: n={s_ib['n']}->{s_ic['n']} (rem={n_rem_is}) baseline={s_ib['total']:+.0f} cand={s_ic['total']:+.0f} delta={is_d:+.0f}")
    print(f"OOS: n={s_ob['n']}->{s_oc['n']} (rem={n_rem_oos}) baseline={s_ob['total']:+.0f} cand={s_oc['total']:+.0f} delta={oos_d:+.0f}")
    print(f"WF={wf_str}  SW_hurt={sw_hurt}")
    print(f"Anchor baseline={b_anch:+.0f}  candidate={c_anch:+.0f}")
    print(f"Gates: G1={g1} G2={g2} G3={g3} G4={g4} G5={g5}")
    print(f"VERDICT: {'RATIFY BODY GATE FOR AGG' if passed else 'REJECT'}")
    if not passed:
        failed = [f"G{i+1}" for i, g in enumerate([g1, g2, g3, g4, g5]) if not g]
        print(f"Failed: {', '.join(failed)}")

    out = {
        "task": "agg-entry-body-gate",
        "account": "Gamma-Bold (AGG)",
        "is_baseline": s_ib, "is_candidate": s_ic, "is_n_removed": n_rem_is, "is_delta": is_d,
        "oos_baseline": s_ob, "oos_candidate": s_oc, "oos_n_removed": n_rem_oos, "oos_delta": oos_d,
        "wf": wf, "sw_hurt": sw_hurt, "sw_rows": sw_rows,
        "anchor_baseline": b_anch, "anchor_candidate": c_anch,
        "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": passed},
        "verdict": "RATIFY" if passed else "REJECT",
        "auto_ratified": passed,
        "ratification_basis": "OP-22 auto-ratify (all 5 gates pass)" if passed else "N/A",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
