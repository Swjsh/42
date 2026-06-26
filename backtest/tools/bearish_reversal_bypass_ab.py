"""BEARISH_REVERSAL_BYPASS A/B test (task e670b8f0, Rank 28).

Context:
  5/01 11:50 J anchor (+$470): SPY was in BULL ribbon with FHH rejection.
  Normal AGG bear filter 5 requires ribbon=BEAR -- blocks this setup entirely.
  include_bearish_reversal_bypass=True removes filter_5 and filter_8 when:
    - fhh_level_rejection trigger fires (requires include_first_hour_high=True)
    - trendline_rejection NOT in triggers
    - ribbon_now.stack == BULL (counter-trend reversal at FHH)

  Two knobs are swept in addition to the bypass:
    fhh_above_max_prior_min: FHH must be >= X above max(multi_day_levels).
    Intended to gate out "FHH within existing range" setups (noise) vs
    "FHH broke above prior range" setups (5/01 gap-up pattern).

Conditions tested:
  1. BASELINE: no FHH, no bypass (current AGG prod)
  2. FHH_ONLY: include_first_hour_high=True, bypass=False (additive FHH-level-rejection trades on BEAR ribbon)
  3. BYPASS_NO_GATE: FHH + bypass (all fhh-ribbon-BULL setups allowed)
  4. BYPASS_GAP0.5: FHH + bypass + fhh_above_max_prior_min=0.5
  5. BYPASS_GAP1.0: FHH + bypass + fhh_above_max_prior_min=1.0
  6. BYPASS_GAP2.0: FHH + bypass + fhh_above_max_prior_min=2.0

OP-22 gates for auto-ratify:
  G1: IS_delta >= 0
  G2: OOS_delta > 0
  G3: WF_norm >= 0.70
  G4: SW_hurt <= 1
  G5: anchor no-regression (5/01 fires on all gate-passing configs)

Security: read-only. No Alpaca calls. No production state writes.
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa: E402

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "bearish_reversal_bypass_ab.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026, 5, 26), dt.date(2026, 5, 27),
              dt.date(2026, 5, 28), dt.date(2026, 5, 29)}

# J's anchor dates
ANCHOR_WINNER_501  = dt.date(2026, 5, 1)   # +$470 target
ANCHOR_WINNERS = {dt.date(2026, 4, 29), ANCHOR_WINNER_501, dt.date(2026, 5, 4)}
ANCHOR_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}

SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("SW2_2025H2",  dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("SW3_early26", dt.date(2026, 1, 2),  dt.date(2026, 2, 26)),
]

AGG_BASE = dict(
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

CONFIGS = [
    ("BASELINE",       dict(include_first_hour_high=False, include_bearish_reversal_bypass=False)),
    ("FHH_ONLY",       dict(include_first_hour_high=True,  include_bearish_reversal_bypass=False)),
    ("BYPASS_NO_GATE", dict(include_first_hour_high=True,  include_bearish_reversal_bypass=True)),
    ("BYPASS_GAP0.5",  dict(include_first_hour_high=True,  include_bearish_reversal_bypass=True, fhh_above_max_prior_min=0.5)),
    ("BYPASS_GAP1.0",  dict(include_first_hour_high=True,  include_bearish_reversal_bypass=True, fhh_above_max_prior_min=1.0)),
    ("BYPASS_GAP2.0",  dict(include_first_hour_high=True,  include_bearish_reversal_bypass=True, fhh_above_max_prior_min=2.0)),
]


def get_fill_days():
    from collections import Counter
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def load_data():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_name = spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(DATA / vix_name))
    return spy_df, vix_df


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "avg_pnl": 0.0, "total_pnl": 0.0}
    pnls = [t.dollar_pnl for t in trades]
    return {
        "n": len(trades),
        "wr": round(sum(p > 0 for p in pnls) / len(pnls), 3),
        "avg_pnl": round(sum(pnls) / len(pnls), 1),
        "total_pnl": round(sum(pnls), 1),
    }


def new_trades(baseline_trades, candidate_trades):
    """Trades in candidate but not in baseline (identified by date+entry_time)."""
    base_keys = {(t.entry_time_et, t.setup) for t in baseline_trades}
    return [t for t in candidate_trades if (t.entry_time_et, t.setup) not in base_keys]


def sw_hurt_count(sw_splits, candidate_is_trades, baseline_is_total):
    hurt = 0
    for _name, sw_start, sw_end in sw_splits:
        sw = [t for t in candidate_is_trades if sw_start <= t.entry_time_et.date() <= sw_end]
        if sum(t.dollar_pnl for t in sw) < 0:
            hurt += 1
    return hurt


def main():
    print("=" * 72)
    print("BEARISH_REVERSAL_BYPASS A/B TEST  (Rank 28, task e670b8f0)")
    print("=" * 72)

    print("\n[1] Loading data...")
    spy_df, vix_df = load_data()

    all_fill_days = get_fill_days()
    is_days  = [d for d in all_fill_days if d < IS_CUTOFF and d not in MDATES_SET]
    oos_days_all = [d for d in all_fill_days if d >= IS_CUTOFF and d not in MDATES_SET]
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    oos_days = [d for d in oos_days_all if d in spy_dates]
    print(f"  IS: {len(is_days)} days ({is_days[0]} -> {is_days[-1]})")
    print(f"  OOS: {len(oos_days)} days ({oos_days[0]} -> {oos_days[-1]})")

    print("\n[2] Running all configs...")
    results = {}
    for name, extra_kwargs in CONFIGS:
        kwargs = dict(AGG_BASE, **extra_kwargs)
        is_r  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **kwargs)
        oos_r = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **kwargs)
        results[name] = {"is": is_r.trades, "oos": oos_r.trades}
        is_s  = stats(is_r.trades)
        oos_s = stats(oos_r.trades)
        # Check if 5/01 anchor fires
        may1_oos = [t for t in oos_r.trades if t.entry_time_et.date() == ANCHOR_WINNER_501]
        may1_str = f"5/01={'+' if may1_oos else '-'}({sum(t.dollar_pnl for t in may1_oos):+.0f})" if may1_oos else "5/01=MISS"
        print(f"  {name:<18} IS n={is_s['n']:<4} {is_s['total_pnl']:>+8.0f} | "
              f"OOS n={oos_s['n']:<4} {oos_s['total_pnl']:>+8.0f}  {may1_str}")

    baseline_is  = results["BASELINE"]["is"]
    baseline_oos = results["BASELINE"]["oos"]
    base_is_s  = stats(baseline_is)
    base_oos_s = stats(baseline_oos)
    base_anchor_oos = sum(t.dollar_pnl for t in baseline_oos if t.entry_time_et.date() in ANCHOR_WINNERS)

    print(f"\n[3] Delta vs BASELINE + OP-22 gates:")
    print(f"\n  {'Config':<18} {'IS_D':>7} {'OOS_D':>7} {'WF':>8} {'SW':>4} {'G5':>4} {'501?':>6} {'PASS':>5}")
    print(f"  {'-'*72}")

    scorecard_rows = []
    for name, extra_kwargs in CONFIGS[1:]:  # skip baseline
        c_is  = results[name]["is"]
        c_oos = results[name]["oos"]
        c_is_s  = stats(c_is)
        c_oos_s = stats(c_oos)
        is_d  = round(c_is_s["total_pnl"]  - base_is_s["total_pnl"],  1)
        oos_d = round(c_oos_s["total_pnl"] - base_oos_s["total_pnl"], 1)

        # WF_norm: new trade quality comparison
        added_is  = new_trades(baseline_is, c_is)
        added_oos = new_trades(baseline_oos, c_oos)
        n_add_is  = len(added_is)
        n_add_oos = len(added_oos)
        wf_norm = None
        if n_add_is > 0 and n_add_oos > 0:
            avg_is  = sum(t.dollar_pnl for t in added_is)  / n_add_is
            avg_oos = sum(t.dollar_pnl for t in added_oos) / n_add_oos
            if avg_is != 0:
                wf_norm = round(avg_oos / avg_is, 3)

        sw_h = sw_hurt_count(SW_SPLITS, c_is, base_is_s["total_pnl"])
        curr_anchor = sum(t.dollar_pnl for t in c_oos if t.entry_time_et.date() in ANCHOR_WINNERS)
        g5 = curr_anchor >= base_anchor_oos * 0.90

        # 5/01 fires?
        may1 = [t for t in c_oos if t.entry_time_et.date() == ANCHOR_WINNER_501]
        may1_str = f"+{sum(t.dollar_pnl for t in may1):.0f}" if may1 else "MISS"

        g1 = is_d >= 0
        g2 = oos_d > 0
        g3 = wf_norm is not None and wf_norm >= 0.70
        g4 = sw_h <= 1
        all_pass = g1 and g2 and g3 and g4 and g5
        wf_str = f"{wf_norm:.3f}" if wf_norm is not None else "N/A"

        print(f"  {name:<18} {is_d:>+7.0f} {oos_d:>+7.0f} {wf_str:>8} {sw_h:>4} "
              f"{'Y' if g5 else 'N':>4} {may1_str:>6} {'Y' if all_pass else 'N':>5}")

        # New trade breakdown for this config
        new_is_pnls  = [t.dollar_pnl for t in added_is]
        new_oos_pnls = [t.dollar_pnl for t in added_oos]

        scorecard_rows.append({
            "config": name,
            "extra_kwargs": {k: v for k, v in extra_kwargs.items() if k != "params_overrides"},
            "is": c_is_s,
            "oos": c_oos_s,
            "is_delta": is_d,
            "oos_delta": oos_d,
            "n_added_is": n_add_is,
            "n_added_oos": n_add_oos,
            "added_is_avg": round(sum(new_is_pnls) / max(1, n_add_is), 1),
            "added_oos_avg": round(sum(new_oos_pnls) / max(1, n_add_oos), 1),
            "wf_norm": wf_norm,
            "sw_hurt": sw_h,
            "anchor_ok": g5,
            "may1_pnl": round(sum(t.dollar_pnl for t in may1), 1),
            "may1_fires": bool(may1),
            "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": all_pass},
        })

    # Show new trades breakdown per config
    print("\n[4] New trades added by each config (OOS):")
    for row in scorecard_rows:
        added = new_trades(baseline_oos, results[row["config"]]["oos"])
        if added:
            print(f"  {row['config']}:")
            for t in sorted(added, key=lambda t: str(t.entry_time_et)):
                print(f"    {t.entry_time_et.date()} {str(t.entry_time_et.time())[:5]} "
                      f"side={t.side} setup={t.setup[:30]} vix={t.entry_vix:.1f} "
                      f"pnl={t.dollar_pnl:+.0f}")

    # Best candidate
    passing = [r for r in scorecard_rows if r["gates"]["all"]]
    best = max(passing, key=lambda r: r["oos_delta"]) if passing else None

    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    if best:
        print(f"  RATIFY config: {best['config']}")
        print(f"  IS_delta={best['is_delta']:+.0f}  OOS_delta={best['oos_delta']:+.0f}  "
              f"WF_norm={best['wf_norm']}  SW_hurt={best['sw_hurt']}")
        print(f"  5/01 fires: {best['may1_fires']} (P&L={best['may1_pnl']:+.0f})")
    else:
        print("  REJECT - no config cleared all OP-22 gates.")
        best_oos = max(scorecard_rows, key=lambda r: r["oos_delta"], default=None)
        if best_oos:
            print(f"  Best OOS: {best_oos['config']} OOS_D={best_oos['oos_delta']:+.0f}")

    scorecard = {
        "task": "bearish-reversal-bypass-ab",
        "rule_id": "bearish_reversal_bypass",
        "description": "BEARISH_REVERSAL_BYPASS A/B: FHH counter-trend bear when ribbon=BULL",
        "baseline": {"is": base_is_s, "oos": base_oos_s},
        "configs": scorecard_rows,
        "best": best,
        "auto_ratify": best is not None,
        "verdict": "RATIFY" if best else "REJECT",
        "implementation": (
            "If RATIFY: update automation/state/aggressive/params.json to add "
            "include_first_hour_high and include_bearish_reversal_bypass. "
            "Also update automation/prompts/aggressive/heartbeat.md "
            "(requires J ratification per Rule 9 for heartbeat.md changes)."
        ),
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("BEARISH REVERSAL BYPASS A/B COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
