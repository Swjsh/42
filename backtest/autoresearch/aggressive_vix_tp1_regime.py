"""
Aggressive TP1 VIX-Regime Conditioning Analysis.

Q1: What is the flat optimal TP1 for the Aggressive account?
Q2: Does VIX at entry condition the optimal TP1 choice?

Hypothesis: High-VIX entries have faster/larger premium moves -> holding to 75%
makes sense. Low-VIX entries move slowly -> locking gains at 50% avoids reversal.

Method (post-processing hybrid — no simulator changes):
  1. Run Aggressive backtest with tp1=0.50 AND tp1=0.75 AND tp1=1.00
  2. Match trades by date (same entries, different exits)
  3. For hybrid combos at each VIX threshold:
     - VIX <= threshold -> use LOW_VIX_tp1 result
     - VIX >  threshold -> use HIGH_VIX_tp1 result
  4. Apply gates: OOS_positive AND WF>=0.70 AND SW_hurt<=1

Security note: read-only. No Alpaca tools. No OpenRouter calls. $0 cost.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_S  = dt.date(2025, 1, 2)
IS_E  = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 16)

SUB_WINDOWS = [
    ("W1_2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2_2025Q3", dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("W3_2025Q4", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("W4_2026H1", dt.date(2026, 1, 2),  dt.date(2026, 5, 7)),
]

# Current production Aggressive params (post-TIGHTER_STOP_2 2026-06-17)
AGG_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.07,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bear_threshold": 15.0, "vix_bull_max": 30.0},
)

VIX_THRESHOLDS = [17.5, 20.0, 22.0, 25.0, 30.0]

# Hybrids: (label, low_vix_tp1, high_vix_tp1)
# Meaning: VIX <= threshold -> low_vix_tp1; VIX > threshold -> high_vix_tp1
HYBRID_COMBOS = [
    ("50lo_75hi", 0.50, 0.75),   # hypothesis: slow regime exits early
    ("75lo_50hi", 0.75, 0.50),   # reverse hypothesis
    ("75lo_100hi", 0.75, 1.00),  # let winners run in high-VIX
    ("100lo_75hi", 1.00, 0.75),  # reverse
]


def run_with_tp1(spy, vix, tp1_pct, start, end, **extra):
    kwargs = dict(AGG_BASE)
    kwargs.update(extra)
    kwargs["tp1_premium_pct"] = tp1_pct
    return run_backtest(spy, vix, start_date=start, end_date=end, **kwargs)


def build_trade_pnl_by_date(result):
    """Return {date: (total_dollar_pnl, first_entry_time_et)}."""
    by_date = {}
    for trade in result.trades:
        d = trade.entry_time_et.date()
        prev = by_date.get(d, (0.0, trade.entry_time_et))
        by_date[d] = (prev[0] + trade.dollar_pnl, prev[1])
    return by_date


def get_vix_at_time(vix_df, trade_time):
    """Return VIX close at trade_time (tz-naive ET datetime)."""
    date_str = trade_time.date().isoformat()
    time_str = trade_time.strftime("%H:%M")
    mask = (vix_df["date"] == date_str) & (vix_df["time"] == time_str)
    rows = vix_df[mask]["close"]
    if len(rows) > 0:
        return float(rows.iloc[0])
    mask2 = (
        (vix_df["date"] == date_str)
        & (vix_df["time"] >= "09:30")
        & (vix_df["time"] <= "10:30")
    )
    rows2 = vix_df[mask2]["close"]
    if len(rows2) > 0:
        return float(rows2.median())
    day_mask = vix_df["date"] == date_str
    rows3 = vix_df[day_mask]["close"]
    return float(rows3.median()) if len(rows3) > 0 else float("nan")


def compute_hybrid_pnl(low_by_date, high_by_date, vix_df, threshold, start, end):
    """
    For each trade date in [start, end]:
      VIX > threshold -> use high_by_date result (HIGH_VIX_tp1)
      VIX <= threshold -> use low_by_date result (LOW_VIX_tp1)
    Returns (n_trades, total_pnl).
    """
    all_dates = set(low_by_date) | set(high_by_date)
    dates = sorted(d for d in all_dates if start <= d <= end)
    total = 0.0
    n = 0
    for d in dates:
        low_e  = low_by_date.get(d)
        high_e = high_by_date.get(d)
        if low_e is not None and high_e is not None:
            vix = get_vix_at_time(vix_df, low_e[1])
            total += high_e[0] if (vix == vix and vix > threshold) else low_e[0]
            n += 1
        elif low_e is not None:
            total += low_e[0]
            n += 1
        elif high_e is not None:
            vix = get_vix_at_time(vix_df, high_e[1])
            if vix == vix and vix > threshold:
                total += high_e[0]
                n += 1
    return n, total


def wf_norm(oos_d, n_oos, is_d, n_is):
    if is_d == 0 or n_is == 0 or n_oos == 0:
        return float("nan")
    return (oos_d / n_oos) / (is_d / n_is)


def main():
    out_path = ROOT / "backtest" / "autoresearch" / "results" / "aggressive_vix_tp1_regime.txt"
    lines = []

    def emit(s=""):
        lines.append(s)
        print(s)

    emit("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)

    import pytz
    ts_col = "timestamp_et" if "timestamp_et" in vix_df.columns else vix_df.columns[0]
    ts_parsed = pd.to_datetime(vix_df[ts_col], utc=True).dt.tz_convert("America/New_York")
    vix_df["date"] = ts_parsed.dt.date.astype(str)
    vix_df["time"] = ts_parsed.dt.strftime("%H:%M")
    if "close" not in vix_df.columns:
        cands = [c for c in vix_df.columns if "close" in c.lower()]
        vix_df["close"] = vix_df[cands[0]] if cands else vix_df.iloc[:, 4]

    emit(f"SPY {len(spy)} rows  VIX {len(vix_df)} rows")
    emit()
    emit("=" * 70)
    emit("Aggressive TP1 VIX-Regime Conditioning — current prod stop=-7%")
    emit("=" * 70)

    # -----------------------------------------------------------------------
    # PART 1: Flat TP1 sweep (0.50, 0.75 baseline, 1.00)
    # -----------------------------------------------------------------------
    emit()
    emit("PART 1 — Flat TP1 comparison")
    emit("-" * 70)

    emit("  Running tp1=0.75 (baseline)...")
    b75_is   = run_with_tp1(spy, vix_df, 0.75, IS_S,  IS_E)
    b75_oos  = run_with_tp1(spy, vix_df, 0.75, OOS_S, OOS_E)
    base_is_pnl  = sum(t.dollar_pnl for t in b75_is.trades)
    base_oos_pnl = sum(t.dollar_pnl for t in b75_oos.trades)
    n_is  = len(b75_is.trades)
    n_oos = len(b75_oos.trades)
    emit(f"  BASELINE (tp1=75%): IS n={n_is} pnl={base_is_pnl:+,.0f} | OOS n={n_oos} pnl={base_oos_pnl:+,.0f}")

    flat_results = {}
    for tp1, label in [(0.50, "50%"), (0.75, "75% (base)"), (1.00, "100%")]:
        emit(f"  Running tp1={label}...")
        r_is  = run_with_tp1(spy, vix_df, tp1, IS_S,  IS_E)
        r_oos = run_with_tp1(spy, vix_df, tp1, OOS_S, OOS_E)
        is_pnl  = sum(t.dollar_pnl for t in r_is.trades)
        oos_pnl = sum(t.dollar_pnl for t in r_oos.trades)
        is_d  = is_pnl  - base_is_pnl
        oos_d = oos_pnl - base_oos_pnl
        wf    = wf_norm(oos_d, n_oos, is_d, n_is)
        wf_s  = f"{wf:.3f}" if wf == wf else "  nan"
        verdict = "BASELINE" if tp1 == 0.75 else ("CANDIDATE" if oos_d > 0 and wf >= 0.70 else ("OOS_NEG" if oos_d <= 0 else "WF_FAIL"))
        emit(f"  tp1={label:>11} IS={is_pnl:>+9,.0f} (d={is_d:>+7,.0f})  OOS={oos_pnl:>+8,.0f} (d={oos_d:>+7,.0f})  WF={wf_s}  {verdict}")
        flat_results[tp1] = {
            "is": build_trade_pnl_by_date(r_is),
            "oos": build_trade_pnl_by_date(r_oos),
            "sw": {},
        }
        for wname, ws, we in SUB_WINDOWS:
            sw_r = run_with_tp1(spy, vix_df, tp1, ws, we)
            flat_results[tp1]["sw"][wname] = build_trade_pnl_by_date(sw_r)

    # Baseline sub-window by-date maps
    flat_results[0.75]["is"]  = build_trade_pnl_by_date(b75_is)
    flat_results[0.75]["oos"] = build_trade_pnl_by_date(b75_oos)
    for wname, ws, we in SUB_WINDOWS:
        sw_r = run_with_tp1(spy, vix_df, 0.75, ws, we)
        flat_results[0.75]["sw"][wname] = build_trade_pnl_by_date(sw_r)

    # -----------------------------------------------------------------------
    # PART 2: VIX-conditional hybrid analysis
    # -----------------------------------------------------------------------
    emit()
    emit("PART 2 — VIX-conditional hybrid (low_vix_tp1 vs high_vix_tp1)")
    emit("  Baseline = tp1=0.75 constant (production)")
    emit(f"  IS  baseline: n={n_is}  pnl={base_is_pnl:+,.0f}")
    emit(f"  OOS baseline: n={n_oos}  pnl={base_oos_pnl:+,.0f}")
    emit()

    # Sub-window baseline PnL sums
    base_sw_pnl = {}
    for wname, ws, we in SUB_WINDOWS:
        base_sw_pnl[wname] = sum(v[0] for v in flat_results[0.75]["sw"][wname].values())

    for combo_label, low_tp1, high_tp1 in HYBRID_COMBOS:
        emit(f"  Hybrid {combo_label}: VIX<=thr->{low_tp1*100:.0f}% | VIX>thr->{high_tp1*100:.0f}%")
        low_data  = flat_results[low_tp1]
        high_data = flat_results[high_tp1]

        ratifiable = []
        hdr = f"    {'VIX>':>5} {'IS_n':>5} {'IS_pnl':>10} {'IS_d':>8} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_d':>8} {'WF':>7} {'SW_h':>5} VERDICT"
        emit(hdr)
        emit("    " + "-" * (len(hdr) - 4))

        for thresh in VIX_THRESHOLDS:
            # IS
            h_is_n, h_is_pnl = compute_hybrid_pnl(
                low_data["is"], high_data["is"], vix_df, thresh, IS_S, IS_E
            )
            # OOS
            h_oos_n, h_oos_pnl = compute_hybrid_pnl(
                low_data["oos"], high_data["oos"], vix_df, thresh, OOS_S, OOS_E
            )

            is_d  = h_is_pnl  - base_is_pnl
            oos_d = h_oos_pnl - base_oos_pnl
            wf    = wf_norm(oos_d, n_oos, is_d, n_is)
            wf_s  = f"{wf:.3f}" if wf == wf else "  nan"

            sw_hurt = 0
            sw_tags = []
            for wname, ws, we in SUB_WINDOWS:
                h_sw_n, h_sw_pnl = compute_hybrid_pnl(
                    low_data["sw"][wname], high_data["sw"][wname], vix_df, thresh, ws, we
                )
                sw_d = h_sw_pnl - base_sw_pnl[wname]
                tag = "H" if sw_d > 50 else ("X" if sw_d < -50 else "F")
                if tag == "X":
                    sw_hurt += 1
                sw_tags.append(f"{wname[:6]}:{sw_d:+.0f}")

            oos_pos = oos_d > 0
            wf_ok   = wf == wf and wf >= 0.70
            sw_ok   = sw_hurt <= 1

            if oos_pos and wf_ok and sw_ok:
                verdict = "RATIFIABLE"
                ratifiable.append((thresh, oos_d, wf))
            elif not oos_pos:
                verdict = "OOS_NEG"
            elif not wf_ok:
                verdict = f"WF_FAIL({wf:.3f})"
            else:
                verdict = f"SW_FAIL({sw_hurt})"

            emit(
                f"    {thresh:>5.1f} {h_is_n:>5} {h_is_pnl:>+10,.0f} {is_d:>+8,.0f}"
                f" {h_oos_n:>6} {h_oos_pnl:>+10,.0f} {oos_d:>+8,.0f} {wf_s:>7}"
                f" {sw_hurt:>5} {verdict}"
            )
            emit(f"           SW: {' | '.join(sw_tags)}")

        if ratifiable:
            best = max(ratifiable, key=lambda x: x[1])
            emit(f"    *** RATIFIABLE: VIX>{best[0]:.1f} {combo_label} OOS_d={best[1]:+,.0f} WF={best[2]:.3f} ***")
        else:
            emit(f"    No ratifiable threshold for {combo_label}.")
        emit()

    # -----------------------------------------------------------------------
    # PART 3: VIX distribution diagnostic
    # -----------------------------------------------------------------------
    emit("PART 3 — VIX diagnostic per sub-window")
    for wname, ws, we in SUB_WINDOWS:
        mask = (vix_df["date"] >= ws.isoformat()) & (vix_df["date"] <= we.isoformat())
        v = vix_df[mask]["close"]
        if len(v):
            pct_above_20 = (v > 20).mean() * 100
            pct_above_25 = (v > 25).mean() * 100
            emit(
                f"  {wname}: median={v.median():.1f}  p25={v.quantile(0.25):.1f}"
                f"  p75={v.quantile(0.75):.1f}  max={v.max():.1f}"
                f"  pct>20={pct_above_20:.0f}%  pct>25={pct_above_25:.0f}%"
            )

    emit()
    emit("DONE.")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
