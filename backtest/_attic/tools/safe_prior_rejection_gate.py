"""SAFE prior_rejection blocking gate.

Entry quality miner found: prior_rejection=True (bar before entry is a rejection/small-body)
has WR=23.5% vs WR=48.2% for False. n=17 IS bear trades with prior_rejection=True.

HYPOTHESIS: These 17 trades are net-negative or near-zero P&L (WR=23.5% with 0DTE losses
tends to drag). Blocking them would improve total P&L.

METHOD: Post-hoc gate test — run IS/OOS baseline, identify prior_rejection=True BEAR trades,
remove them from total, compute IS_delta and OOS_delta, run OP-22 gates.

PRIOR_REJECTION definition: the bar immediately before entry (N-1) has body_pct < 0.30
AND that body_pct is less than half the range. In other words, the N-1 bar is a doji or
wick-dominant bar (price rejected at the level without follow-through).
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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_prior_rejection_gate.json"

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


def get_prior_rejection(trade, spy_df) -> bool:
    """Return True if the bar immediately before entry was a rejection bar.

    Rejection = bar where body_pct < 0.30 (doji or wick-dominant — price tested
    a level and was rejected without directional follow-through).
    """
    entry_dt = naive(trade.entry_time_et)
    date_str = entry_dt.strftime("%Y-%m-%d")
    day = spy_df[spy_df["timestamp_et"].str[:10] == date_str].sort_values("timestamp_et").reset_index(drop=True)
    entry_str = entry_dt.strftime("%Y-%m-%d %H:%M")
    matches = day[day["timestamp_et"].str[:16] == entry_str]
    if matches.empty or matches.index[0] < 2:
        return False

    bar_idx = matches.index[0]
    prior_row = day.iloc[bar_idx - 1]
    geom = bar_geom(prior_row)
    body_pct = geom.get("body_pct", 0)
    return body_pct < 0.30


def main():
    print("=" * 70)
    print("SAFE PRIOR REJECTION BLOCKING GATE (WR=23.5% anti-signal)")
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

    def analyze_prior_rejection(trades, label):
        """Split trades by prior_rejection, compute P&L for blocked subset."""
        bear_trades = [t for t in trades if getattr(t, "side", "").upper() in ("P", "PUT", "BEAR")]
        blocked_pnl = []
        kept_pnl = []
        for t in bear_trades:
            pr = get_prior_rejection(t, spy_df)
            if pr:
                blocked_pnl.append(t.dollar_pnl)
            else:
                kept_pnl.append(t.dollar_pnl)

        n_blocked = len(blocked_pnl)
        total_blocked = sum(blocked_pnl)
        wr_blocked = sum(p > 0 for p in blocked_pnl) / n_blocked if n_blocked else 0
        wr_kept = sum(p > 0 for p in kept_pnl) / len(kept_pnl) if kept_pnl else 0

        print(f"\n{label} prior_rejection=True: n={n_blocked} WR={wr_blocked:.1%} "
              f"total={total_blocked:+.0f} avg={total_blocked/n_blocked:+.0f}" if n_blocked else f"\n{label}: n_blocked=0")
        print(f"{label} prior_rejection=False (kept): n={len(kept_pnl)} WR={wr_kept:.1%} "
              f"total={sum(kept_pnl):+.0f} avg={sum(kept_pnl)/len(kept_pnl):+.0f}" if kept_pnl else f"{label}: n_kept=0")
        return blocked_pnl, kept_pnl, n_blocked

    print("\n--- IS ANALYSIS ---")
    b_is_blocked, b_is_kept, n_is_blocked = analyze_prior_rejection(r_is.trades, "IS")
    print("\n--- OOS ANALYSIS ---")
    b_oos_blocked, b_oos_kept, n_oos_blocked = analyze_prior_rejection(r_oos.trades, "OOS")

    # IS/OOS delta: if we block prior_rejection trades, total improves by -sum(blocked_pnl)
    # (i.e., we stop taking those negative-EV trades)
    is_baseline = sum(t.dollar_pnl for t in r_is.trades)
    oos_baseline = sum(t.dollar_pnl for t in r_oos.trades)
    is_candidate = is_baseline - sum(b_is_blocked)
    oos_candidate = oos_baseline - sum(b_oos_blocked)
    is_delta  = round(is_candidate - is_baseline, 1)
    oos_delta = round(oos_candidate - oos_baseline, 1)

    wf = round(oos_delta / is_delta, 3) if is_delta != 0 else None

    sw_hurt = 0
    for _, sw_s, sw_e in SW_SPLITS:
        b_sw = sum(t.dollar_pnl for t in r_is.trades if sw_s <= naive(t.entry_time_et).date() <= sw_e)
        block_sw = sum(t.dollar_pnl for t in r_is.trades
                       if (getattr(t, "side", "").upper() in ("P", "PUT", "BEAR")
                           and sw_s <= naive(t.entry_time_et).date() <= sw_e
                           and get_prior_rejection(t, spy_df)))
        c_sw = b_sw - block_sw
        if c_sw < b_sw:
            sw_hurt += 1

    b_anch = sum(t.dollar_pnl for t in r_oos.trades if naive(t.entry_time_et).date() in ANCHOR_W)
    block_anch = sum(t.dollar_pnl for t in r_oos.trades
                     if (getattr(t, "side", "").upper() in ("P", "PUT", "BEAR")
                         and naive(t.entry_time_et).date() in ANCHOR_W
                         and get_prior_rejection(t, spy_df)))
    c_anch = b_anch - block_anch
    tol = abs(b_anch) * 0.10 if b_anch != 0 else 0
    g5 = c_anch >= b_anch - tol if b_anch != 0 else c_anch >= 0

    g1 = is_delta >= 0
    g2 = oos_delta > 0
    g3 = wf is not None and wf >= 0.70
    g4 = sw_hurt <= 1
    passed = g1 and g2 and g3 and g4 and g5

    wf_str = f"{wf:.3f}" if wf is not None else "N/A"
    print(f"\nIS baseline={is_baseline:+.0f}  candidate={is_candidate:+.0f}  delta={is_delta:+.0f}  n_blocked={n_is_blocked}")
    print(f"OOS baseline={oos_baseline:+.0f}  candidate={oos_candidate:+.0f}  delta={oos_delta:+.0f}  n_blocked={n_oos_blocked}")
    print(f"WF={wf_str}  SW_hurt={sw_hurt}")
    print(f"Anchor baseline={b_anch:+.0f}  candidate={c_anch:+.0f}")
    print(f"Gates: G1={g1} G2={g2} G3={g3} G4={g4} G5={g5}")
    print(f"VERDICT: {'RATIFY' if passed else 'REJECT'}")

    out = {
        "task": "safe-prior-rejection-gate",
        "description": "Block BEAR entries where prior bar (N-1) is a rejection/doji (body_pct < 0.30)",
        "is_baseline": is_baseline, "is_candidate": is_candidate,
        "is_n_blocked": n_is_blocked,
        "is_blocked_pnl": round(sum(b_is_blocked), 1),
        "is_blocked_wr": round(sum(p > 0 for p in b_is_blocked) / n_is_blocked, 3) if n_is_blocked else None,
        "oos_baseline": oos_baseline, "oos_candidate": oos_candidate,
        "oos_n_blocked": n_oos_blocked,
        "oos_blocked_pnl": round(sum(b_oos_blocked), 1),
        "oos_blocked_wr": round(sum(p > 0 for p in b_oos_blocked) / n_oos_blocked, 3) if n_oos_blocked else None,
        "is_delta": is_delta, "oos_delta": oos_delta, "wf": wf, "sw_hurt": sw_hurt,
        "anchor_baseline": b_anch, "anchor_candidate": c_anch,
        "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": passed},
        "verdict": "RATIFY" if passed else "REJECT",
        "note": ("Gate requires orchestrator parameter: block_prior_rejection_bar=True. "
                 "Revert: set False. Implementation: in BEAR trigger logic, after all gates pass "
                 "and before entry, check bar N-1 body_pct — if < 0.30, skip entry."),
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
