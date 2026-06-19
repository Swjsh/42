"""
Trendline VIX gate A/B scorecard.

Hypothesis: trendline-only setups (sole trigger = trendline_rejection) are profitable
when VIX is low-moderate (15-17) and lose money when VIX > 20-22. Blocking them above
a VIX threshold should improve OOS performance.

Corrected baseline: block_level_rejection=True + block_elite_bull (VIX15-17.5) +
  premium_stop_pct_bear=-0.10 + vix_bull_max=18.0 + time_stop_minutes_before_close=20
  + tp1_qty_fraction=0.667 + no_trade_before=09:35 + midday_trendline_gate=True

VIX gate logic in backtest: a new params_overrides key 'block_trendline_high_vix'
(bool) + 'trendline_high_vix_threshold' (float). These must be wired in orchestrator.
First check if they exist; if not, we simulate by analyzing decisions output.

Actually: take a simpler approach. Analyze trade P&L by trendline-only flag and VIX
bucket first, then test threshold sweep once we know the distribution.
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_S = dt.date(2025, 1, 2)
IS_E = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 16)

# Corrected baseline — all gates deployed through Rank 35
BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)


def vix_bucket(v):
    if v < 15:
        return "<15"
    elif v < 17:
        return "15-17"
    elif v < 18:
        return "17-18"
    elif v < 20:
        return "18-20"
    elif v < 22:
        return "20-22"
    elif v < 25:
        return "22-25"
    else:
        return "25+"


def analyze_trendline_breakdown(spy, vix, start, end, label):
    """Run baseline and break down trendline-only trades by VIX bucket."""
    result = run_backtest(spy, vix, start_date=start, end_date=end, **BASE_KWARGS)
    print(f"\n=== {label} BASELINE ===")
    print(f"  n_trades={len(result.trades)} pnl={sum(t.dollar_pnl for t in result.trades):+.0f}")

    tl_trades = []
    other_trades = []
    for t in result.trades:
        # Trendline-only: sole trigger is trendline_rejection (no level, no confluence)
        triggers = getattr(t, "triggers_fired", None) or []
        is_tl_only = (
            len(triggers) == 1 and
            any("trendline_rejection" in str(tr) for tr in triggers)
        )
        if is_tl_only:
            tl_trades.append(t)
        else:
            other_trades.append(t)

    print(f"\n  TRENDLINE-ONLY  n={len(tl_trades)} pnl={sum(t.dollar_pnl for t in tl_trades):+.0f}")
    print(f"  OTHER           n={len(other_trades)} pnl={sum(t.dollar_pnl for t in other_trades):+.0f}")

    # VIX breakdown for trendline-only trades
    if tl_trades:
        print(f"\n  TRENDLINE-ONLY by VIX bucket:")
        buckets = {}
        for t in tl_trades:
            # Get VIX at entry
            vix_val = getattr(t, "entry_vix", None)
            if vix_val is None:
                vix_val = 0.0
            bucket = vix_bucket(float(vix_val))
            if bucket not in buckets:
                buckets[bucket] = []
            buckets[bucket].append(t)
        for bkt in sorted(buckets.keys()):
            ts = buckets[bkt]
            pnl = sum(x.dollar_pnl for x in ts)
            wins = sum(1 for x in ts if x.dollar_pnl > 0)
            wr = wins / len(ts) if ts else 0
            print(f"    VIX {bkt:6s}: n={len(ts):3d} WR={wr:.0%} pnl={pnl:+.0f} avg={pnl/len(ts):+.0f}")

    # Also use decisions for trendline quality signal
    tl_decisions = [d for d in result.decisions if
                    d.get("action", "").startswith("ENTER") and
                    "trendline" in str(d.get("reason", "")).lower() and
                    "level" not in str(d.get("reason", "")).lower()]
    print(f"\n  TRENDLINE-ONLY decisions approx n={len(tl_decisions)}")

    return result


def run_vix_threshold_sweep(spy, vix):
    """Test blocking trendline-only trades when VIX > threshold."""
    print("\n\n=== TRENDLINE VIX GATE THRESHOLD SWEEP (IS) ===")

    base = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **BASE_KWARGS)
    base_pnl = sum(t.dollar_pnl for t in base.trades)
    print(f"BASE: n={len(base.trades)} pnl={base_pnl:+.0f}")

    thresholds = [17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0]
    results = {}

    for thresh in thresholds:
        # Block trendline-only setups when VIX >= thresh
        # We do this by filtering decisions post-hoc (no engine param needed)
        # Actually we need to check if the orchestrator supports this via params_overrides
        # For now, manually subtract trendline-only trades above VIX threshold
        subtracted_pnl = 0
        subtracted_n = 0
        for t in base.trades:
            vix_val = getattr(t, "entry_vix", 0.0) or 0.0
            triggers = getattr(t, "triggers_fired", None) or []
            is_tl_only = (
                len(triggers) == 1 and
                any("trendline_rejection" in str(tr) for tr in triggers)
            )
            if is_tl_only and float(vix_val) >= thresh:
                subtracted_pnl += t.dollar_pnl
                subtracted_n += 1

        cand_pnl = base_pnl - subtracted_pnl
        delta = cand_pnl - base_pnl
        print(f"  VIX<={thresh:.0f}: blocked n={subtracted_n} subtracted={subtracted_pnl:+.0f} IS_delta={delta:+.0f}")
        results[thresh] = {
            "n_blocked": subtracted_n,
            "subtracted_pnl": subtracted_pnl,
            "is_delta": delta,
        }

    return results


def run_full_ab(spy, vix, threshold):
    """Full A/B including OOS and sub-windows for a given VIX threshold."""
    print(f"\n\n=== FULL A/B: block trendline-only when VIX >= {threshold} ===")

    def cand_pnl_for(result, thresh):
        """Compute candidate P&L by removing blocked trades."""
        blocked_pnl = 0
        n_blocked = 0
        for t in result.trades:
            vix_val = float(getattr(t, "entry_vix", 0.0) or 0.0)
            triggers = getattr(t, "triggers_fired", None) or []
            is_tl_only = (
                len(triggers) == 1 and
                any("trendline_rejection" in str(tr) for tr in triggers)
            )
            if is_tl_only and vix_val >= thresh:
                blocked_pnl += t.dollar_pnl
                n_blocked += 1
        return blocked_pnl, n_blocked

    # IS
    is_base = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **BASE_KWARGS)
    is_base_pnl = sum(t.dollar_pnl for t in is_base.trades)
    is_blocked_pnl, is_n_blocked = cand_pnl_for(is_base, threshold)
    is_cand_pnl = is_base_pnl - is_blocked_pnl
    is_delta = is_cand_pnl - is_base_pnl

    # OOS
    oos_base = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE_KWARGS)
    oos_base_pnl = sum(t.dollar_pnl for t in oos_base.trades)
    oos_blocked_pnl, oos_n_blocked = cand_pnl_for(oos_base, threshold)
    oos_cand_pnl = oos_base_pnl - oos_blocked_pnl
    oos_delta = oos_cand_pnl - oos_base_pnl

    print(f"  IS:  base n={len(is_base.trades)} pnl={is_base_pnl:+.0f} | blocked n={is_n_blocked} pnl={is_blocked_pnl:+.0f} | cand pnl={is_cand_pnl:+.0f} | IS_delta={is_delta:+.0f}")
    print(f"  OOS: base n={len(oos_base.trades)} pnl={oos_base_pnl:+.0f} | blocked n={oos_n_blocked} pnl={oos_blocked_pnl:+.0f} | cand pnl={oos_cand_pnl:+.0f} | OOS_delta={oos_delta:+.0f}")

    # WF
    n_is_base = len(is_base.trades)
    n_oos_base = len(oos_base.trades)
    if is_n_blocked > 0 and oos_n_blocked > 0:
        is_per_trade = is_delta / is_n_blocked
        oos_per_trade = oos_delta / oos_n_blocked
        wf_norm = (oos_per_trade / oos_base_pnl * n_oos_base) / (is_per_trade / is_base_pnl * n_is_base) if is_per_trade != 0 else 0
        wf_simple = (oos_delta / n_oos_base) / (is_delta / n_is_base) if is_delta != 0 else 0
        print(f"  WF_simple={wf_simple:.3f} (n_is_base={n_is_base}, n_oos_base={n_oos_base})")
        print(f"  IS per-blocked-trade={is_per_trade:+.0f}  OOS per-blocked-trade={oos_per_trade:+.0f}")
    else:
        print(f"  WARNING: n_is_blocked={is_n_blocked}, n_oos_blocked={oos_n_blocked} — insufficient data")

    # Sub-windows
    windows = [
        ("W1_2025H1", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
        ("W2_2025H2", dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
        ("W3_Q12026", dt.date(2026, 1, 2), dt.date(2026, 3, 31)),
        ("W4_Apr26",  dt.date(2026, 4, 1), dt.date(2026, 5, 7)),
    ]
    print(f"\n  IS sub-windows:")
    hurt = 0
    for name, ws, we in windows:
        wr = run_backtest(spy, vix, start_date=ws, end_date=we, **BASE_KWARGS)
        wr_pnl = sum(t.dollar_pnl for t in wr.trades)
        wr_blocked_pnl, wr_n_blocked = cand_pnl_for(wr, threshold)
        wr_delta = -wr_blocked_pnl
        verdict = "HELP" if wr_delta > 0 else "FLAT" if wr_delta == 0 else "HURT"
        if verdict == "HURT":
            hurt += 1
        print(f"    {name}: n_blocked={wr_n_blocked} delta={wr_delta:+.0f} -> {verdict}")
    print(f"  SW hurt: {hurt}/4 (gate: <=1)")

    return {
        "threshold": threshold,
        "is_n_base": n_is_base, "is_base_pnl": is_base_pnl,
        "is_n_blocked": is_n_blocked, "is_delta": is_delta,
        "oos_n_base": n_oos_base, "oos_base_pnl": oos_base_pnl,
        "oos_n_blocked": oos_n_blocked, "oos_delta": oos_delta,
        "sw_hurt": hurt,
    }


def main():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    # Step 1: VIX breakdown analysis
    analyze_trendline_breakdown(spy, vix, IS_S, IS_E, "IS")
    analyze_trendline_breakdown(spy, vix, OOS_S, OOS_E, "OOS")

    # Step 2: Threshold sweep (IS quick scan)
    sweep = run_vix_threshold_sweep(spy, vix)

    # Step 3: Full A/B for best candidate threshold
    print("\n\nSweep summary:")
    for thresh, r in sorted(sweep.items()):
        status = "POS" if r["is_delta"] > 0 else "NEG"
        print(f"  VIX>={thresh:.0f}: IS_delta={r['is_delta']:+.0f} n_blocked={r['n_blocked']} [{status}]")

    # Find best IS positive threshold
    best = max(sweep.items(), key=lambda x: x[1]["is_delta"])
    best_thresh = best[0]
    best_is_delta = best[1]["is_delta"]
    print(f"\nBest IS candidate: VIX>={best_thresh:.0f} (IS_delta={best_is_delta:+.0f})")

    if best_is_delta > 0:
        result = run_full_ab(spy, vix, best_thresh)
        print(f"\n=== VERDICT ===")
        oos_pos = result["oos_delta"] > 0
        sw_ok = result["sw_hurt"] <= 1
        print(f"  OOS positive: {oos_pos} (OOS_delta={result['oos_delta']:+.0f})")
        print(f"  SW hurt<=1:   {sw_ok} ({result['sw_hurt']}/4)")
        if oos_pos and sw_ok:
            print(f"  -> CANDIDATE: block trendline-only when VIX >= {best_thresh:.0f}")
        else:
            print(f"  -> REJECT or INCONCLUSIVE")
    else:
        print("No positive IS candidate found. Trendline VIX gate does not help.")


if __name__ == "__main__":
    main()
