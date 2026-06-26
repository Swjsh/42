"""SAFE entry bar body_pct gate.

Entry quality miner found: body<0.20 has IS total=-$466 (n=16, WR=31.2%).
These are doji/wick-dominant entry bars — price has no directional conviction.
HYPOTHESIS: blocking body<0.20 BEAR entries improves both IS and OOS.

IS_delta expected = +$466 (removing 16 net-negative trades).

BODY_PCT definition: |close - open| / (high - low), i.e., ratio of body to full range.
body_pct < 0.20 means the bar is mostly wicks — a rejection/indecision bar.
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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_entry_body_gate.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES    = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_W  = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}
SW_SPLITS = [
    ("SW1_2025H1", dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2", dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26",dt.date(2026,1,2),  dt.date(2026,2,26)),
]

BODY_THRESHOLD = 0.20  # block entry bars with body_pct < this value

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


def get_entry_body_pct(trade, spy_df) -> float | None:
    """Compute body_pct of the entry bar (bar at entry time)."""
    entry_dt = naive(trade.entry_time_et)
    date_str = entry_dt.strftime("%Y-%m-%d")
    day = spy_df[spy_df["timestamp_et"].str[:10] == date_str].sort_values("timestamp_et").reset_index(drop=True)
    entry_str = entry_dt.strftime("%Y-%m-%d %H:%M")
    matches = day[day["timestamp_et"].str[:16] == entry_str]
    if matches.empty:
        return None
    row = day.iloc[matches.index[0]]
    geom = bar_geom(row)
    return geom.get("body_pct", None)


def main():
    print("=" * 70)
    print(f"SAFE ENTRY BODY PCT GATE (block body_pct < {BODY_THRESHOLD})")
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

    def split_by_body(trades, label):
        bear = [t for t in trades if getattr(t, "side", "").upper() in ("P", "PUT", "BEAR")]
        blocked, kept = [], []
        body_vals = {}
        for t in bear:
            bp = get_entry_body_pct(t, spy_df)
            body_vals[id(t)] = bp
            if bp is not None and bp < BODY_THRESHOLD:
                blocked.append(t)
            else:
                kept.append(t)

        n_b, n_k = len(blocked), len(kept)
        t_b = sum(t.dollar_pnl for t in blocked)
        t_k = sum(t.dollar_pnl for t in kept)
        wr_b = sum(t.dollar_pnl > 0 for t in blocked) / n_b if n_b else 0
        wr_k = sum(t.dollar_pnl > 0 for t in kept) / n_k if n_k else 0
        print(f"\n{label} blocked (body<{BODY_THRESHOLD}): n={n_b} WR={wr_b:.1%} "
              f"total={t_b:+.0f} avg={t_b/n_b:+.0f}" if n_b else f"\n{label}: n_blocked=0")
        print(f"{label} kept (body>={BODY_THRESHOLD}): n={n_k} WR={wr_k:.1%} "
              f"total={t_k:+.0f} avg={t_k/n_k:+.0f}" if n_k else "")

        # Also show full breakdown by body bucket
        buckets = [("body<0.20", 0, 0.20), ("body_0.20-0.40", 0.20, 0.40),
                   ("body_0.40-0.60", 0.40, 0.60), ("body_0.60+", 0.60, 1.01)]
        print(f"\n{label} body breakdown:")
        for bname, lo, hi in buckets:
            bt = [t for t in bear if body_vals.get(id(t)) is not None
                  and lo <= body_vals[id(t)] < hi]
            if bt:
                pnls = [t.dollar_pnl for t in bt]
                print(f"  {bname:20s}: n={len(bt):3d} WR={sum(p>0 for p in pnls)/len(bt):.1%} "
                      f"total={sum(pnls):+.0f} avg={sum(pnls)/len(bt):+.0f}")
        return blocked, kept

    print("\n--- IS ANALYSIS ---")
    is_blocked, _ = split_by_body(r_is.trades, "IS")
    print("\n--- OOS ANALYSIS ---")
    oos_blocked, _ = split_by_body(r_oos.trades, "OOS")

    is_base = sum(t.dollar_pnl for t in r_is.trades)
    oos_base = sum(t.dollar_pnl for t in r_oos.trades)
    is_cand = is_base - sum(t.dollar_pnl for t in is_blocked)
    oos_cand = oos_base - sum(t.dollar_pnl for t in oos_blocked)
    n_is_blocked_int = len(is_blocked)
    n_oos_blocked_int = len(oos_blocked)
    is_delta  = round(is_cand - is_base, 1)
    oos_delta = round(oos_cand - oos_base, 1)

    # Per-trade WF (canonical OP-22 formula matching safe_stop_sweep.py)
    per_is  = is_delta  / n_is_blocked_int  if n_is_blocked_int  > 0 else None
    per_oos = oos_delta / n_oos_blocked_int if n_oos_blocked_int > 0 else None
    wf = round(per_oos / per_is, 3) if (per_is is not None and per_oos is not None and per_is != 0) else None

    sw_hurt = 0
    for _, sw_s, sw_e in SW_SPLITS:
        block_sw = sum(t.dollar_pnl for t in is_blocked if sw_s <= naive(t.entry_time_et).date() <= sw_e)
        if block_sw > 0:  # removing positive-EV trades hurts this window
            sw_hurt += 1

    b_anch = sum(t.dollar_pnl for t in r_oos.trades if naive(t.entry_time_et).date() in ANCHOR_W)
    block_anch = sum(t.dollar_pnl for t in oos_blocked if naive(t.entry_time_et).date() in ANCHOR_W)
    c_anch = b_anch - block_anch
    tol = abs(b_anch) * 0.10 if b_anch != 0 else 0
    g5 = c_anch >= b_anch - tol if b_anch != 0 else c_anch >= 0

    g1 = is_delta >= 0
    g2 = oos_delta > 0
    g3 = wf is not None and wf >= 0.70
    g4 = sw_hurt <= 1
    passed = g1 and g2 and g3 and g4 and g5

    wf_str = f"{wf:.3f}" if wf is not None else "N/A"
    print(f"\nIS baseline={is_base:+.0f}  candidate={is_cand:+.0f}  delta={is_delta:+.0f}  n_blocked={len(is_blocked)}")
    print(f"OOS baseline={oos_base:+.0f}  candidate={oos_cand:+.0f}  delta={oos_delta:+.0f}  n_blocked={len(oos_blocked)}")
    print(f"WF={wf_str}  SW_hurt={sw_hurt}")
    print(f"Anchor baseline={b_anch:+.0f}  candidate={c_anch:+.0f}")
    print(f"Gates: G1={g1} G2={g2} G3={g3} G4={g4} G5={g5}")
    print(f"VERDICT: {'RATIFY' if passed else 'REJECT'}")
    if not passed:
        failed = [f"G{i+1}" for i, g in enumerate([g1, g2, g3, g4, g5]) if not g]
        print(f"Failed: {', '.join(failed)}")

    out = {
        "task": "safe-entry-body-gate",
        "body_threshold": BODY_THRESHOLD,
        "description": f"Block BEAR entries where entry bar body_pct < {BODY_THRESHOLD} (doji/wick-dominant bar)",
        "is_n_blocked": n_is_blocked_int, "is_blocked_total": round(sum(t.dollar_pnl for t in is_blocked), 1),
        "oos_n_blocked": n_oos_blocked_int, "oos_blocked_total": round(sum(t.dollar_pnl for t in oos_blocked), 1),
        "is_delta": is_delta, "oos_delta": oos_delta, "wf": wf, "sw_hurt": sw_hurt,
        "anchor_baseline": b_anch, "anchor_candidate": c_anch,
        "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": passed},
        "verdict": "RATIFY" if passed else "REJECT",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
