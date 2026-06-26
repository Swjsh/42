"""SAFE quality-based TRENDLINE sizing upgrade (a9d3f1c2-0001).

TRENDLINE tier currently gets qty=3. ELITE gets qty=10.
Quality miner found: bearish_streak>=3 WR=61.1%, vol_ratio_1.0-1.5 WR=69.2%.
These qualify for ELITE sizing if we add bar-quality checks to tier assignment.

APPROACH: Run IS/OOS with current config, identify TRENDLINE trades that pass
quality criteria, re-compute P&L at qty=10 instead of qty=3 (3.33x multiplier).
If IS_delta positive AND re-weighted OOS_delta positive, propose as gate candidate.

This is a post-hoc proof-of-concept — no orchestrator changes needed yet.
The multiplier is (10/3) on the raw P&L (dollar_pnl stores qty-adjusted profit).

Note: dollar_pnl = (exit_premium - entry_premium) * qty * 100 - commissions.
Re-weighting by (10/3) is exact when qty=3 (under risk cap).
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
from lib.filters import _bar_geometry as bar_geom  # noqa
from sniper_matrix import norm_str  # noqa

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_quality_sizing_ab.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES    = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_W  = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

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


def naive(ts):
    return ts.replace(tzinfo=None) if ts.tzinfo else ts


def classify_tier_from_triggers(t) -> str:
    trig = set(getattr(t, "triggers_fired", []) or [])
    has_conf  = "confluence" in trig
    has_seq   = "sequence_rejection" in trig or "sequence_reclaim" in trig
    has_flip  = "ribbon_flip" in trig
    n = len(trig)
    if (has_conf and has_flip) or n >= 3: return "SUPER"
    elif has_conf or has_seq:             return "ELITE"
    elif any(k in trig for k in ("level_rejection", "level_reclaim")): return "LEVEL"
    else:                                 return "TRENDLINE"


def compute_bar_metrics(trade, spy_df):
    entry_dt = naive(trade.entry_time_et)
    date_str = entry_dt.strftime("%Y-%m-%d")
    day = spy_df[spy_df["timestamp_et"].str[:10] == date_str].sort_values("timestamp_et").reset_index(drop=True)
    entry_str = entry_dt.strftime("%Y-%m-%d %H:%M")
    matches = day[day["timestamp_et"].str[:16] == entry_str]
    if matches.empty or matches.index[0] < 5:
        return None

    bar_idx = matches.index[0]
    vol_window = day["volume"].iloc[max(0, bar_idx - 20): bar_idx]
    vol_avg = vol_window.mean() if len(vol_window) >= 5 else None
    vol_ratio = float(day["volume"].iloc[bar_idx]) / vol_avg if vol_avg and vol_avg > 0 else None

    streak = 0
    for i in range(bar_idx, max(bar_idx - 6, -1), -1):
        row = day.iloc[i]
        if float(row["close"]) < float(row["open"]):
            streak += 1
        else:
            break

    return {"streak": streak, "vol_ratio": vol_ratio}


def is_quality(metrics) -> bool:
    if metrics is None:
        return False
    return (metrics["streak"] >= 3) or (metrics["vol_ratio"] is not None and 1.0 <= metrics["vol_ratio"] < 1.5)


def main():
    print("=" * 70)
    print("SAFE QUALITY SIZING A/B (TRENDLINE qty=3 -> 10 for high-quality)")
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

    print("Running IS baseline...")
    r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **SAFE_BASE)
    print("Running OOS baseline...")
    r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **SAFE_BASE)

    UPGRADE_RATIO = 10.0 / 3.0  # qty upgrade: 3 -> 10

    def reweight_trades(trades, window):
        """Re-weight TRENDLINE bear trades that pass quality metrics."""
        base_total = sum(t.dollar_pnl for t in trades)
        upgraded = 0
        extra = 0.0
        for t in trades:
            if getattr(t, "side", "").upper() not in ("P", "PUT", "BEAR"):
                continue
            if classify_tier_from_triggers(t) != "TRENDLINE":
                continue
            m = compute_bar_metrics(t, spy_df)
            if is_quality(m):
                add = t.dollar_pnl * (UPGRADE_RATIO - 1)
                extra += add
                upgraded += 1
        return base_total, round(extra, 1), upgraded

    print("\nComputing IS quality re-weighting...")
    b_is_total, is_extra, is_upgraded = reweight_trades(r_is.trades, "is")
    print(f"  IS base: {b_is_total:+.0f}  upgraded trades: {is_upgraded}  extra P&L: {is_extra:+.0f}")

    print("Computing OOS quality re-weighting...")
    b_oos_total, oos_extra, oos_upgraded = reweight_trades(r_oos.trades, "oos")
    print(f"  OOS base: {b_oos_total:+.0f}  upgraded trades: {oos_upgraded}  extra P&L: {oos_extra:+.0f}")

    is_delta  = round(is_extra, 1)
    oos_delta = round(oos_extra, 1)

    wf = round(oos_delta / is_delta, 3) if is_delta != 0 else None

    sw_hurt = 0
    for _, sw_s, sw_e in SW_SPLITS:
        b_sw = sum(t.dollar_pnl for t in r_is.trades if sw_s <= naive(t.entry_time_et).date() <= sw_e)
        upg_sw = 0.0
        for t in r_is.trades:
            if getattr(t, "side", "").upper() not in ("P", "PUT", "BEAR"): continue
            if classify_tier_from_triggers(t) != "TRENDLINE": continue
            if not (sw_s <= naive(t.entry_time_et).date() <= sw_e): continue
            m = compute_bar_metrics(t, spy_df)
            if is_quality(m):
                upg_sw += t.dollar_pnl * (UPGRADE_RATIO - 1)
        if upg_sw < 0:
            sw_hurt += 1

    b_anch = sum(t.dollar_pnl for t in r_oos.trades if naive(t.entry_time_et).date() in ANCHOR_W)
    anch_extra = sum(t.dollar_pnl * (UPGRADE_RATIO - 1) for t in r_oos.trades
                     if (getattr(t, "side", "").upper() in ("P", "PUT", "BEAR")
                         and classify_tier_from_triggers(t) == "TRENDLINE"
                         and naive(t.entry_time_et).date() in ANCHOR_W
                         and is_quality(compute_bar_metrics(t, spy_df))))
    c_anch = b_anch + anch_extra
    tol = abs(b_anch) * 0.10 if b_anch != 0 else 0
    g5 = c_anch >= b_anch - tol if b_anch != 0 else c_anch >= 0

    g1 = is_delta >= 0
    g2 = oos_delta > 0
    g3 = wf is not None and wf >= 0.70
    g4 = sw_hurt <= 1
    passed = g1 and g2 and g3 and g4 and g5

    wf_str = f"{wf:.3f}" if wf is not None else "N/A"
    print(f"\nIS_delta={is_delta:+.0f}  OOS_delta={oos_delta:+.0f}  WF={wf_str}  SW_hurt={sw_hurt}")
    print(f"Anchor: baseline={b_anch:+.0f}  candidate={c_anch:+.0f}")
    print(f"Gates: G1={g1} G2={g2} G3={g3} G4={g4} G5={g5}")
    print(f"VERDICT: {'RATIFY SIZING UPGRADE' if passed else 'REJECT'}")

    out = {
        "task": "a9d3f1c2-0001-quality-sizing",
        "candidate": "TRENDLINE bear trades with bearish_streak>=3 OR vol_ratio_1.0-1.5 upgraded to qty=10 (from qty=3)",
        "upgrade_ratio": UPGRADE_RATIO,
        "is_base_total": b_is_total, "is_upgraded_trades": is_upgraded, "is_extra": is_extra,
        "oos_base_total": b_oos_total, "oos_upgraded_trades": oos_upgraded, "oos_extra": oos_extra,
        "is_delta": is_delta, "oos_delta": oos_delta, "wf": wf, "sw_hurt": sw_hurt,
        "anchor_baseline": b_anch, "anchor_candidate": c_anch,
        "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": passed},
        "verdict": "RATIFY_SIZING_UPGRADE" if passed else "REJECT",
        "note": ("Post-hoc re-weighting analysis. To implement: orchestrator needs bar-quality check "
                 "in TRENDLINE tier assignment (bearish_streak>=3 OR vol_ratio 1.0-1.5 at entry bar). "
                 "Requires orchestrator code change + re-run with actual qty=10."),
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
