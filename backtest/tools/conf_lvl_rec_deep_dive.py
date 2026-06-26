"""conf+lvl_rec deep dive — AGG IS/OOS decomposition.

Task 6d8e358a: Decompose AGG IS conf+lvl_rec trades (n=42 expected,
avg +$173/trade) by:
  (a) entry time bucket [09:35-10:00, 10:00-12:00, 12:00-14:00]
      (14:00+ blocked by block_conf_lvl_rec_afternoon=True)
  (b) VIX bucket [<15, 15-18, 18-22, 22+]
  (c) level "roundness" proxy [round_dollar, half_dollar, chart_level]
      Note: ALL conf+lvl_rec trades have confluence confirmed, meaning
      the reclaim level is in multi_day_levels by construction. The
      round/chart split is the only meaningful distinction here.

Secondary analysis:
  - VIX x time cross-tab to find golden zone
  - IS vs OOS pattern stability comparison
  - Auto-ratify gate candidate if any sub-population dominates

Security: read-only. No Alpaca calls. No production state writes.
"""
from __future__ import annotations
import sys, json, datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa: E402

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "conf_lvl_rec_deep_dive.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026, 5, 26), dt.date(2026, 5, 27),
              dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
ANCHOR_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
ANCHOR_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}

# IS sub-windows for WF stability check
SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("SW2_2025H2",  dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("SW3_early26", dt.date(2026, 1, 2),  dt.date(2026, 2, 26)),
]

AGG_KWARGS = dict(
    use_real_fills=True,
    strike_offset=-2,
    premium_stop_pct_bear=-0.07,
    premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    f9_vol_mult=0.7,
    min_triggers_bear=1,
    min_triggers_bull=1,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    block_level_rejection=True,
    block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True,
    midday_trendline_gate=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    require_bearish_fill_bar=True,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.5,
    enable_bullish=True,
    params_overrides={"vix_bear_threshold": 15.0},
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def load_spy_vix():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"), key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_name = spy_path.name.replace("spy_5m", "vix_5m")
    vix_path = DATA / vix_name
    print(f"  SPY: {spy_path.name}")
    print(f"  VIX: {vix_path.name}")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))
    return spy_df, vix_df


def get_vix_at_935(vix_df, trade_date):
    """VIX at or just after 09:35 ET on trade_date."""
    date_str = str(trade_date)
    rows = vix_df[vix_df["timestamp_et"].str.startswith(date_str)]
    morning = rows[rows["timestamp_et"].str[11:16] >= "09:35"]
    if len(morning) == 0:
        return float(rows.iloc[0]["close"]) if len(rows) > 0 else None
    return float(morning.iloc[0]["close"])


def is_round_dollar(level: float) -> bool:
    frac = abs(level - round(level))
    return frac < 0.15


def is_half_dollar(level: float) -> bool:
    # e.g. 560.50 ± 0.15
    nearest_half = round(level * 2) / 2
    frac = abs(level - nearest_half)
    return frac < 0.15 and not is_round_dollar(level)


def level_type(level: float) -> str:
    if is_round_dollar(level):
        return "round_dollar"
    if is_half_dollar(level):
        return "half_dollar"
    return "chart_level"


def time_bucket(entry_dt: dt.datetime) -> str:
    t = entry_dt.time()
    if t < dt.time(10, 0):
        return "09:35-10:00"
    if t < dt.time(12, 0):
        return "10:00-12:00"
    if t < dt.time(14, 0):
        return "12:00-14:00"
    return "14:00+"  # should be blocked


def vix_bucket(vix: float) -> str:
    if vix < 15:
        return "<15"
    if vix < 18:
        return "15-18"
    if vix < 22:
        return "18-22"
    return "22+"


def annotate_trades(trades, vix_df):
    """Annotate trade list with derived fields; filter to conf+lvl_rec only."""
    out = []
    for t in trades:
        triggers = t.triggers_fired
        is_conf_lvl_rec = "confluence" in triggers and "level_reclaim" in triggers
        if not is_conf_lvl_rec:
            continue
        vix_val = get_vix_at_935(vix_df, t.entry_time_et.date())
        entry_dt = t.entry_time_et
        if hasattr(entry_dt, "tzinfo") and entry_dt.tzinfo is not None:
            entry_dt = entry_dt.replace(tzinfo=None)
        out.append({
            "date": t.entry_time_et.date(),
            "entry_dt": entry_dt,
            "side": t.side,
            "pnl": round(t.dollar_pnl, 2),
            "exit_reason": str(t.exit_reason),
            "hold_min": t.hold_minutes,
            "rejection_level": t.rejection_level,
            "triggers": triggers,
            "vix": vix_val,
            "time_bucket": time_bucket(entry_dt),
            "vix_bucket": vix_bucket(vix_val) if vix_val is not None else "unknown",
            "level_type": level_type(t.rejection_level) if t.rejection_level else "unknown",
        })
    return out


def bucket_stats(trades, key):
    groups = defaultdict(list)
    for t in trades:
        groups[t[key]].append(t["pnl"])
    result = {}
    for bucket_key in sorted(groups):
        pnls = groups[bucket_key]
        n = len(pnls)
        total = round(sum(pnls), 1)
        wins = sum(1 for p in pnls if p > 0)
        result[bucket_key] = {
            "n": n,
            "wr": round(wins / n, 3) if n else 0.0,
            "total_pnl": total,
            "avg_pnl": round(total / n, 1) if n else 0.0,
        }
    return result


def cross_tab(trades, key_a, key_b):
    """Cross-tabulation of two categorical keys."""
    grid = defaultdict(lambda: defaultdict(list))
    for t in trades:
        grid[t[key_a]][t[key_b]].append(t["pnl"])
    result = {}
    for a in sorted(grid):
        row = {}
        for b in sorted(grid[a]):
            pnls = grid[a][b]
            n = len(pnls)
            total = round(sum(pnls), 1)
            wins = sum(1 for p in pnls if p > 0)
            row[b] = {"n": n, "wr": round(wins / n, 3) if n else 0.0,
                      "avg_pnl": round(total / n, 1) if n else 0.0}
        result[a] = row
    return result


def print_bucket(label, stats, pad=18):
    print(f"  {'bucket':<{pad}} {'n':>4} {'WR':>6} {'avg_pnl':>8} {'total':>8}")
    print(f"  {'-'*(pad+32)}")
    for k, s in stats.items():
        print(f"  {k:<{pad}} {s['n']:>4} {s['wr']:>6.1%} {s['avg_pnl']:>+8.0f} {s['total_pnl']:>+8.0f}")


def compute_gates(is_trades_all, is_conf, oos_trades_all, oos_conf, hypothesis_name,
                  filter_fn, sw_splits_data):
    """Check OP-22 auto-ratify gates for a hypothesis that filters conf+lvl_rec.

    filter_fn: callable(trade_dict) -> bool, True = KEEP in filtered set
    Baseline = all conf+lvl_rec trades (no filter).
    Candidate = filter_fn applied.
    """
    is_base = [t["pnl"] for t in is_conf]
    is_filt = [t["pnl"] for t in is_conf if filter_fn(t)]
    oos_base = [t["pnl"] for t in oos_conf]
    oos_filt = [t["pnl"] for t in oos_conf if filter_fn(t)]

    is_delta = round(sum(is_filt) - sum(is_base), 1)
    oos_delta = round(sum(oos_filt) - sum(oos_base), 1)
    n_removed_is  = len(is_base)  - len(is_filt)
    n_removed_oos = len(oos_base) - len(oos_filt)

    wf_norm = None
    if n_removed_is > 0 and is_delta > 0 and n_removed_oos > 0:
        wf_norm = round((oos_delta / n_removed_oos) / (is_delta / n_removed_is), 3)

    # SW hurt
    sw_hurt = 0
    sw_details = []
    for sw_name, sw_start, sw_end in sw_splits_data:
        sw_is = [t for t in is_conf if sw_start <= t["date"] <= sw_end]
        sw_base_pnl = sum(t["pnl"] for t in sw_is)
        sw_filt_pnl = sum(t["pnl"] for t in sw_is if filter_fn(t))
        sw_delta = round(sw_filt_pnl - sw_base_pnl, 1)
        hurt = sw_delta < 0
        if hurt:
            sw_hurt += 1
        sw_details.append({"name": sw_name, "delta": sw_delta, "hurt": hurt})

    # Anchor check
    anchor_blocked = []
    for d in ANCHOR_WINNERS:
        day_trades = [t for t in oos_conf if t["date"] == d]
        for t in day_trades:
            if not filter_fn(t):
                anchor_blocked.append({"date": str(d), "pnl": t["pnl"]})
    anchor_ok = len(anchor_blocked) == 0

    gate_is  = is_delta  > 0
    gate_oos = oos_delta > 0
    gate_wf  = wf_norm is not None and wf_norm >= 0.70
    gate_sw  = sw_hurt <= 1
    all_pass = gate_is and gate_oos and gate_wf and gate_sw and anchor_ok

    verdict = "AUTO-RATIFY" if all_pass else "REJECT"
    return {
        "hypothesis": hypothesis_name,
        "verdict": verdict,
        "is_delta": is_delta,
        "oos_delta": oos_delta,
        "n_removed_is": n_removed_is,
        "n_removed_oos": n_removed_oos,
        "wf_norm": wf_norm,
        "sw_hurt": sw_hurt,
        "sw_details": sw_details,
        "anchor_blocked": anchor_blocked,
        "gates": {
            "is_pos": gate_is, "oos_pos": gate_oos,
            "wf": gate_wf, "sw": gate_sw, "anchor": anchor_ok,
        },
        "is_base": {"n": len(is_base), "total": round(sum(is_base), 1),
                    "avg": round(sum(is_base)/len(is_base), 1) if is_base else 0},
        "is_filt": {"n": len(is_filt), "total": round(sum(is_filt), 1),
                    "avg": round(sum(is_filt)/len(is_filt), 1) if is_filt else 0},
        "oos_base": {"n": len(oos_base), "total": round(sum(oos_base), 1),
                     "avg": round(sum(oos_base)/len(oos_base), 1) if oos_base else 0},
        "oos_filt": {"n": len(oos_filt), "total": round(sum(oos_filt), 1),
                     "avg": round(sum(oos_filt)/len(oos_filt), 1) if oos_filt else 0},
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("CONF+LVL_REC DEEP DIVE (AGG IS/OOS)")
    print("=" * 70)

    all_days = get_fill_days()
    is_days  = [d for d in all_days if d < IS_CUTOFF and d not in MDATES_SET]

    print("\n[1] Loading SPY/VIX data...")
    spy_df, vix_df = load_spy_vix()

    spy_dates   = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    oos_days_all = [d for d in all_days if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]
    oos_days    = oos_days_all[-60:]

    print(f"\n[2] Date ranges:")
    print(f"    IS:  {len(is_days)} fill days ({is_days[0]} to {is_days[-1]})")
    print(f"    OOS: {len(oos_days)} fill days ({oos_days[0]} to {oos_days[-1]})")

    print("\n[3] Running IS backtest...")
    is_result = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **AGG_KWARGS)
    print(f"    -> {len(is_result.trades)} total trades, total={sum(t.dollar_pnl for t in is_result.trades):+.0f}")

    print("[4] Running OOS backtest...")
    oos_result = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **AGG_KWARGS)
    print(f"    -> {len(oos_result.trades)} total trades, total={sum(t.dollar_pnl for t in oos_result.trades):+.0f}")

    print("\n[5] Filtering conf+lvl_rec trades...")
    is_conf  = annotate_trades(is_result.trades, vix_df)
    oos_conf = annotate_trades(oos_result.trades, vix_df)
    print(f"    IS  conf+lvl_rec: n={len(is_conf)}, avg={sum(t['pnl'] for t in is_conf)/len(is_conf):+.0f}/trade, total={sum(t['pnl'] for t in is_conf):+.0f}")
    print(f"    OOS conf+lvl_rec: n={len(oos_conf)}, avg={sum(t['pnl'] for t in oos_conf)/len(oos_conf):+.0f}/trade, total={sum(t['pnl'] for t in oos_conf):+.0f}")

    # ── (a) Time bucket breakdown ─────────────────────────────────────────
    print("\n[6a] IS — by entry time bucket:")
    is_time = bucket_stats(is_conf, "time_bucket")
    print_bucket("time_bucket", is_time)

    print("\n[6a] OOS — by entry time bucket:")
    oos_time = bucket_stats(oos_conf, "time_bucket")
    print_bucket("time_bucket", oos_time)

    # ── (b) VIX bucket breakdown ──────────────────────────────────────────
    print("\n[6b] IS — by VIX bucket at 09:35:")
    is_vix = bucket_stats(is_conf, "vix_bucket")
    print_bucket("vix_bucket", is_vix)

    print("\n[6b] OOS — by VIX bucket at 09:35:")
    oos_vix = bucket_stats(oos_conf, "vix_bucket")
    print_bucket("vix_bucket", oos_vix)

    # ── (c) Level type breakdown ──────────────────────────────────────────
    print("\n[6c] IS — by level type proxy:")
    is_lvl = bucket_stats(is_conf, "level_type")
    print_bucket("level_type", is_lvl)

    print("\n[6c] OOS — by level type proxy:")
    oos_lvl = bucket_stats(oos_conf, "level_type")
    print_bucket("level_type", oos_lvl)

    # ── VIX x Time cross-tab ──────────────────────────────────────────────
    print("\n[6d] IS — VIX x time cross-tab (avg_pnl):")
    is_xtab = cross_tab(is_conf, "vix_bucket", "time_bucket")
    time_buckets_sorted = ["09:35-10:00", "10:00-12:00", "12:00-14:00"]
    print(f"  {'VIX/time':<12}" + "".join(f"  {b:<15}" for b in time_buckets_sorted))
    for vb in ["<15", "15-18", "18-22", "22+"]:
        row_str = f"  {vb:<12}"
        for tb in time_buckets_sorted:
            cell = is_xtab.get(vb, {}).get(tb)
            if cell:
                row_str += f"  n={cell['n']:<2} avg={cell['avg_pnl']:>+5.0f}"
            else:
                row_str += f"  {'—':^15}"
        print(row_str)

    print("\n[6d] OOS — VIX x time cross-tab (avg_pnl):")
    oos_xtab = cross_tab(oos_conf, "vix_bucket", "time_bucket")
    print(f"  {'VIX/time':<12}" + "".join(f"  {b:<15}" for b in time_buckets_sorted))
    for vb in ["<15", "15-18", "18-22", "22+"]:
        row_str = f"  {vb:<12}"
        for tb in time_buckets_sorted:
            cell = oos_xtab.get(vb, {}).get(tb)
            if cell:
                row_str += f"  n={cell['n']:<2} avg={cell['avg_pnl']:>+5.0f}"
            else:
                row_str += f"  {'—':^15}"
        print(row_str)

    # ── Exit reason breakdown ─────────────────────────────────────────────
    print("\n[6e] IS — exit reason breakdown:")
    exit_counts_is = Counter(t["exit_reason"] for t in is_conf)
    for reason, cnt in sorted(exit_counts_is.items(), key=lambda x: -x[1]):
        pnls = [t["pnl"] for t in is_conf if t["exit_reason"] == reason]
        wins = sum(1 for p in pnls if p > 0)
        print(f"  {reason:<40} n={cnt:>3} WR={wins/cnt:>5.1%} avg={sum(pnls)/cnt:>+8.0f}")

    print("\n[6e] OOS — exit reason breakdown:")
    exit_counts_oos = Counter(t["exit_reason"] for t in oos_conf)
    for reason, cnt in sorted(exit_counts_oos.items(), key=lambda x: -x[1]):
        pnls = [t["pnl"] for t in oos_conf if t["exit_reason"] == reason]
        wins = sum(1 for p in pnls if p > 0)
        print(f"  {reason:<40} n={cnt:>3} WR={wins/cnt:>5.1%} avg={sum(pnls)/cnt:>+8.0f}")

    # ── Gate hypotheses ────────────────────────────────────────────────────
    print("\n[7] Testing gate hypotheses (OP-22 gates)...")

    sw_splits_data = list(SW_SPLITS)
    gate_results = []

    # H1: Block midday conf+lvl_rec (12:00-14:00) — already have afternoon block,
    #     test if midday is also losing and should be blocked.
    h1 = compute_gates(
        is_result.trades, is_conf, oos_result.trades, oos_conf,
        "H1_block_midday_conf_lvl_rec (12:00-14:00)",
        lambda t: t["time_bucket"] != "12:00-14:00",
        sw_splits_data,
    )
    gate_results.append(h1)
    print(f"  H1 block_midday_conf_lvl_rec: {h1['verdict']}")
    print(f"     IS_delta={h1['is_delta']:+.0f} OOS_delta={h1['oos_delta']:+.0f} "
          f"WF={str(h1['wf_norm'])} SW_hurt={h1['sw_hurt']}")

    # H2: VIX >= 18 gate on conf+lvl_rec (block low-VIX entries)
    h2 = compute_gates(
        is_result.trades, is_conf, oos_result.trades, oos_conf,
        "H2_vix_18_gate (block conf+lvl_rec when VIX<18)",
        lambda t: t["vix"] is not None and t["vix"] >= 18.0,
        sw_splits_data,
    )
    gate_results.append(h2)
    print(f"  H2 vix_18_gate: {h2['verdict']}")
    print(f"     IS_delta={h2['is_delta']:+.0f} OOS_delta={h2['oos_delta']:+.0f} "
          f"WF={str(h2['wf_norm'])} SW_hurt={h2['sw_hurt']}")

    # H3: VIX >= 15 gate (matches existing bear VIX gate — keep VIX>15 trades only)
    h3 = compute_gates(
        is_result.trades, is_conf, oos_result.trades, oos_conf,
        "H3_vix_15_gate (block conf+lvl_rec when VIX<15)",
        lambda t: t["vix"] is not None and t["vix"] >= 15.0,
        sw_splits_data,
    )
    gate_results.append(h3)
    print(f"  H3 vix_15_gate: {h3['verdict']}")
    print(f"     IS_delta={h3['is_delta']:+.0f} OOS_delta={h3['oos_delta']:+.0f} "
          f"WF={str(h3['wf_norm'])} SW_hurt={h3['sw_hurt']}")

    # H4: Block chart_level type (keep only round_dollar/half_dollar — psychological levels)
    h4 = compute_gates(
        is_result.trades, is_conf, oos_result.trades, oos_conf,
        "H4_block_chart_level (keep round/half-dollar only)",
        lambda t: t["level_type"] in ("round_dollar", "half_dollar"),
        sw_splits_data,
    )
    gate_results.append(h4)
    print(f"  H4 block_chart_level: {h4['verdict']}")
    print(f"     IS_delta={h4['is_delta']:+.0f} OOS_delta={h4['oos_delta']:+.0f} "
          f"WF={str(h4['wf_norm'])} SW_hurt={h4['sw_hurt']}")

    # H5: Restrict to morning session (09:35-10:00) only — pure opening-bell window
    h5 = compute_gates(
        is_result.trades, is_conf, oos_result.trades, oos_conf,
        "H5_morning_only (09:35-10:00 window only)",
        lambda t: t["time_bucket"] == "09:35-10:00",
        sw_splits_data,
    )
    gate_results.append(h5)
    print(f"  H5 morning_only: {h5['verdict']}")
    print(f"     IS_delta={h5['is_delta']:+.0f} OOS_delta={h5['oos_delta']:+.0f} "
          f"WF={str(h5['wf_norm'])} SW_hurt={h5['sw_hurt']}")

    # H6: Composite — morning (09:35-12:00) AND VIX >= 15
    h6 = compute_gates(
        is_result.trades, is_conf, oos_result.trades, oos_conf,
        "H6_morning_vix15 (before 12:00 AND VIX>=15)",
        lambda t: t["time_bucket"] in ("09:35-10:00", "10:00-12:00")
                  and t["vix"] is not None and t["vix"] >= 15.0,
        sw_splits_data,
    )
    gate_results.append(h6)
    print(f"  H6 morning_vix15: {h6['verdict']}")
    print(f"     IS_delta={h6['is_delta']:+.0f} OOS_delta={h6['oos_delta']:+.0f} "
          f"WF={str(h6['wf_norm'])} SW_hurt={h6['sw_hurt']}")

    # ── Auto-ratify summary ────────────────────────────────────────────────
    ratified = [g for g in gate_results if g["verdict"] == "AUTO-RATIFY"]
    print(f"\n{'='*70}")
    print("VERDICT SUMMARY")
    print(f"{'='*70}")
    if ratified:
        best = max(ratified, key=lambda g: g["oos_delta"])
        print(f"  *** AUTO-RATIFY: {best['hypothesis']} ***")
        print(f"  IS_delta={best['is_delta']:+.0f} OOS_delta={best['oos_delta']:+.0f} "
              f"WF_norm={best['wf_norm']} SW_hurt={best['sw_hurt']}")
    else:
        print("  No gate hypothesis cleared all OP-22 gates.")
        print("  Key findings:")
        # Best time bucket in IS
        best_time = max(is_time.items(), key=lambda x: x[1]["avg_pnl"])
        print(f"    Best IS time bucket: {best_time[0]} avg={best_time[1]['avg_pnl']:+.0f}/trade n={best_time[1]['n']}")
        best_vix = max(is_vix.items(), key=lambda x: x[1]["avg_pnl"])
        print(f"    Best IS VIX bucket:  {best_vix[0]} avg={best_vix[1]['avg_pnl']:+.0f}/trade n={best_vix[1]['n']}")

    # ── Save scorecard ────────────────────────────────────────────────────
    scorecard = {
        "task": "6d8e358a-conf-lvl-rec-deep-dive",
        "is_date_range": [str(is_days[0]), str(is_days[-1])],
        "oos_date_range": [str(oos_days[0]), str(oos_days[-1])],
        "is_all_trades": len(is_result.trades),
        "oos_all_trades": len(oos_result.trades),
        "is_conf_lvl_rec": {
            "n": len(is_conf),
            "total_pnl": round(sum(t["pnl"] for t in is_conf), 1),
            "avg_pnl": round(sum(t["pnl"] for t in is_conf) / len(is_conf), 1) if is_conf else 0,
        },
        "oos_conf_lvl_rec": {
            "n": len(oos_conf),
            "total_pnl": round(sum(t["pnl"] for t in oos_conf), 1),
            "avg_pnl": round(sum(t["pnl"] for t in oos_conf) / len(oos_conf), 1) if oos_conf else 0,
        },
        "is_by_time": is_time,
        "oos_by_time": oos_time,
        "is_by_vix": is_vix,
        "oos_by_vix": oos_vix,
        "is_by_level_type": is_lvl,
        "oos_by_level_type": oos_lvl,
        "is_vix_x_time_xtab": is_xtab,
        "oos_vix_x_time_xtab": oos_xtab,
        "gate_hypotheses": gate_results,
        "auto_ratified": [g["hypothesis"] for g in ratified],
        "best_auto_ratify": ratified and max(ratified, key=lambda g: g["oos_delta"])["hypothesis"],
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("DEEP DIVE COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
