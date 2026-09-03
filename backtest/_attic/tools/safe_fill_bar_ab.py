"""SAFE require_bearish_fill_bar A/B test.

Observation: fill bar direction is discriminatory for BEARISH_REJECTION trades.
WR=41% when fill bar is bearish, WR=3% when fill bar is bullish.
AGG already has require_bearish_fill_bar=True (since Rank35).
SAFE does NOT currently have this gate.

A/B: BASELINE (no fill bar gate) vs CANDIDATE (require_bearish_fill_bar=True).

OP-22 gates: G1=IS_delta>=0, G2=OOS_delta>0, G3=WF_norm>=0.70,
             G4=SW_hurt<=1, G5=anchor_no_regression (10% tolerance).

Security: read-only (except output). No Alpaca calls.
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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_fill_bar_ab.json"

IS_CUTOFF  = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}
ANCHOR_LOSERS  = {dt.date(2026,5,5), dt.date(2026,5,6), dt.date(2026,5,7)}

SW_SPLITS = [
    ("SW1_2025H1", dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2", dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26",dt.date(2026,1,2),  dt.date(2026,2,26)),
]

SAFE_BASE = dict(
    use_real_fills=True, strike_offset=-2,
    premium_stop_pct_bear=-0.10, premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5, f9_vol_mult=0.7,
    min_triggers_bear=1, min_triggers_bull=2,
    no_trade_before=dt.time(9, 35), no_trade_window=(dt.time(11, 30), dt.time(12, 0)),
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    midday_trendline_gate=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.3, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 17.3, "vix_bull_hard_cap": 18.0},
)


def stats(ts):
    if not ts:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t.dollar_pnl for t in ts]
    return {
        "n": len(ts),
        "wr": round(sum(p > 0 for p in pnls) / len(ts), 3),
        "avg": round(sum(pnls) / len(ts), 1),
        "total": round(sum(pnls), 1),
    }


def main():
    print("=" * 70)
    print("SAFE REQUIRE_BEARISH_FILL_BAR A/B")
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

    print(f"IS: {len(is_days)} days | OOS: {len(oos_days)} days")

    # BASELINE (no fill bar gate)
    print("\nRunning BASELINE IS...")
    b_is_r = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1],
                          require_bearish_fill_bar=False, **SAFE_BASE)
    print("Running BASELINE OOS...")
    b_oos_r = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1],
                           require_bearish_fill_bar=False, **SAFE_BASE)

    # CANDIDATE (require_bearish_fill_bar=True)
    print("Running CANDIDATE IS...")
    c_is_r = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1],
                          require_bearish_fill_bar=True, **SAFE_BASE)
    print("Running CANDIDATE OOS...")
    c_oos_r = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1],
                           require_bearish_fill_bar=True, **SAFE_BASE)

    b_is  = stats(b_is_r.trades)
    b_oos = stats(b_oos_r.trades)
    c_is  = stats(c_is_r.trades)
    c_oos = stats(c_oos_r.trades)

    is_delta  = round(c_is["total"]  - b_is["total"], 1)
    oos_delta = round(c_oos["total"] - b_oos["total"], 1)
    n_removed_is  = b_is["n"]  - c_is["n"]
    n_removed_oos = b_oos["n"] - c_oos["n"]

    # WF: per-trade delta normalised
    wf = None
    if n_removed_is > 0 and is_delta != 0 and n_removed_oos > 0:
        per_is  = is_delta  / n_removed_is
        per_oos = oos_delta / n_removed_oos if n_removed_oos > 0 else 0
        if per_is != 0:
            wf = round(per_oos / per_is, 3)

    # Sub-window hurt
    sw_hurt = 0
    for _name, sw_s, sw_e in SW_SPLITS:
        bts = [t for t in b_is_r.trades if sw_s <= t.entry_time_et.date() <= sw_e]
        cts = [t for t in c_is_r.trades if sw_s <= t.entry_time_et.date() <= sw_e]
        b_sw = sum(t.dollar_pnl for t in bts)
        c_sw = sum(t.dollar_pnl for t in cts)
        if c_sw < b_sw:
            sw_hurt += 1

    # Anchor check
    b_anchor = sum(t.dollar_pnl for t in b_oos_r.trades if t.entry_time_et.date() in ANCHOR_WINNERS)
    c_anchor = sum(t.dollar_pnl for t in c_oos_r.trades if t.entry_time_et.date() in ANCHOR_WINNERS)
    anchor_tol = abs(b_anchor) * 0.10 if b_anchor != 0 else 0
    g5 = c_anchor >= b_anchor - anchor_tol if b_anchor != 0 else c_anchor >= 0

    # Anchor-winner day detail
    print("\nAnchor-winner OOS trades baseline:")
    for t in sorted([x for x in b_oos_r.trades if x.entry_time_et.date() in ANCHOR_WINNERS],
                    key=lambda x: x.entry_time_et):
        ts = x = t
        td = ts.entry_time_et
        if hasattr(td, 'tzinfo') and td.tzinfo: td = td.replace(tzinfo=None)
        print(f"  {td.date()} {td.strftime('%H:%M')} {ts.side} pnl={ts.dollar_pnl:+.0f}")
    print("Anchor-winner OOS trades candidate:")
    for t in sorted([x for x in c_oos_r.trades if x.entry_time_et.date() in ANCHOR_WINNERS],
                    key=lambda x: x.entry_time_et):
        ts = x = t
        td = ts.entry_time_et
        if hasattr(td, 'tzinfo') and td.tzinfo: td = td.replace(tzinfo=None)
        print(f"  {td.date()} {td.strftime('%H:%M')} {ts.side} pnl={ts.dollar_pnl:+.0f}")

    g1 = is_delta >= 0
    g2 = oos_delta > 0
    g3 = wf is not None and wf >= 0.70
    g4 = sw_hurt <= 1
    passed = g1 and g2 and g3 and g4 and g5

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"BASELINE:  IS n={b_is['n']:3} WR={b_is['wr']:.1%} total={b_is['total']:+.0f}"
          f"  OOS n={b_oos['n']:3} WR={b_oos['wr']:.1%} total={b_oos['total']:+.0f}")
    print(f"CANDIDATE: IS n={c_is['n']:3} WR={c_is['wr']:.1%} total={c_is['total']:+.0f}"
          f"  OOS n={c_oos['n']:3} WR={c_oos['wr']:.1%} total={c_oos['total']:+.0f}")
    print(f"IS_delta={is_delta:+.0f}  OOS_delta={oos_delta:+.0f}  WF={wf}  SW_hurt={sw_hurt}")
    print(f"Anchor: baseline={b_anchor:+.0f}  candidate={c_anchor:+.0f}  tol={anchor_tol:.0f}")
    print(f"Gates: G1={g1} G2={g2} G3={g3} G4={g4} G5={g5}")
    print(f"VERDICT: {'RATIFY' if passed else 'REJECT'}")
    print(f"  Removed from IS: {n_removed_is} trades  OOS: {n_removed_oos} trades")
    wf_str = f"{wf:.3f}" if wf is not None else "N/A"
    print(f"  WF={wf_str} (need 0.70+)")

    out = {
        "task": "c7d2e831-lbfs-fill-bar",
        "candidate": "require_bearish_fill_bar=True on SAFE account",
        "baseline": {"is": b_is, "oos": b_oos, "anchor": b_anchor},
        "candidate_stats": {"is": c_is, "oos": c_oos, "anchor": c_anchor},
        "is_delta": is_delta, "oos_delta": oos_delta,
        "wf_norm": wf, "sw_hurt": sw_hurt,
        "removed_is": n_removed_is, "removed_oos": n_removed_oos,
        "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": passed},
        "verdict": "RATIFY" if passed else "REJECT",
        "auto_ratify": passed,
        "ratify_action": "Set require_bearish_fill_bar=True in automation/state/params.json" if passed else None,
        "note": "C29 caveat: both SAFE and AGG use strike_offset=-2 (ITM-2 per orchestrator). G3=WF>=0.70 is the key gate.",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
