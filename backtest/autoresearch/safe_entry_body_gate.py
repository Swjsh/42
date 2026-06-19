"""
Safe Account — Entry Bar Bearish-Body Gate Analysis.

From prior entry_bar_quality analysis (old baseline, IS n=75 BEARISH_REJECTION):
  - Bearish-body trades: n=46, WR=41.3%
  - Bullish-body trades: n=29, WR=3.4%

Gate hypothesis: skip BEARISH_REJECTION trades where the signal bar has a bullish body
(close >= open). These are "ambiguous" entries — price closed higher than it opened on the
rejection bar, indicating weak rejection.

Method:
  1. Run baseline (current production params) IS/OOS
  2. Match each trade to its signal bar in spy_df by entry_time_et
  3. Classify: bearish_body = (close < open), bullish_body = (close >= open)
  4. Compute gate impact: IS_delta, OOS_delta, WF, SW_hurt
  5. Report: would skipping bullish-body trades pass the full gate set?

Gate: skip trade if bar.close >= bar.open (entry bar has bullish body)
i.e., IS_delta = IS_pnl(baseline) - IS_pnl(bullish-body-excluded)
           = -1 × sum(pnl of bullish-body IS trades)

If bullish-body IS trades are net losers, IS_delta > 0 (removing them improves P&L).
Similarly for OOS. WF >= 0.70 and SW_hurt <= 1 = ratifiable.

Security note: read-only. No Alpaca tools. $0 cost.
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

SUBWINDOWS = [
    ("W1_2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2_2025Q3", dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("W3_2025Q4", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("W4_2026H1", dt.date(2026, 1, 2),  dt.date(2026, 5, 7)),
]

# Current production Safe params (post all 2026-06-17 ratifications)
SAFE_PARAMS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,
)


def build_bar_index(spy_df):
    """Build {(date_str, time_str): (open, high, low, close)} lookup."""
    ts_col = next((c for c in spy_df.columns if "timestamp" in c.lower()), None)
    if ts_col:
        import pytz
        ts = pd.to_datetime(spy_df[ts_col], utc=True).dt.tz_convert("America/New_York")
        spy_df = spy_df.copy()
        spy_df["_date"] = ts.dt.date.astype(str)
        spy_df["_time"] = ts.dt.strftime("%H:%M")
    else:
        spy_df = spy_df.copy()
        spy_df["_date"] = spy_df["date"].astype(str)
        spy_df["_time"] = spy_df["time"].astype(str)

    idx = {}
    for _, row in spy_df.iterrows():
        key = (row["_date"], row["_time"])
        idx[key] = (float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))
    return idx


def classify_body(trade, bar_idx):
    """Return 'BEAR_BODY', 'BULL_BODY', or 'UNKNOWN' for trade's entry bar."""
    t = trade.entry_time_et
    date_str = t.date().isoformat()
    time_str = t.strftime("%H:%M")
    bar = bar_idx.get((date_str, time_str))
    if bar is None:
        # Try previous bar (sometimes entry is on next bar after signal)
        prev_min = t - dt.timedelta(minutes=5)
        time_str2 = prev_min.strftime("%H:%M")
        bar = bar_idx.get((date_str, time_str2))
    if bar is None:
        return "UNKNOWN", None
    o, h, lo, c = bar
    return ("BEAR_BODY" if c < o else "BULL_BODY"), (o, h, lo, c)


def run_window(spy_df, vix_df, start, end, **params):
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end, **params)


def wf_norm(oos_d, n_oos, is_d, n_is):
    if is_d == 0 or n_is == 0 or n_oos == 0:
        return float("nan")
    return (oos_d / n_oos) / (is_d / n_is)


def main():
    out_path = ROOT / "backtest" / "autoresearch" / "results" / "safe_entry_body_gate.txt"
    lines = []

    def emit(s=""):
        lines.append(s)
        print(s)

    emit("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    emit(f"SPY {len(spy)} rows  VIX {len(vix)} rows")

    bar_idx = build_bar_index(spy)
    emit(f"Bar index: {len(bar_idx)} bars")
    emit()

    emit("=" * 70)
    emit("SAFE Entry Bar Bearish-Body Gate Analysis")
    emit("Gate: skip BEARISH_REJECTION if signal bar has bullish body (close >= open)")
    emit("=" * 70)
    emit()

    # Run IS/OOS baseline
    emit("Running baseline (all trades)...")
    base_is  = run_window(spy, vix, IS_S,  IS_E,  **SAFE_PARAMS)
    base_oos = run_window(spy, vix, OOS_S, OOS_E, **SAFE_PARAMS)

    b_is_trades  = [t for t in base_is.trades  if "BEARISH_REJECTION" in t.setup]
    b_oos_trades = [t for t in base_oos.trades if "BEARISH_REJECTION" in t.setup]

    emit(f"IS  total: n={len(base_is.trades)}  pnl={sum(t.dollar_pnl for t in base_is.trades):+,.0f}")
    emit(f"    BEARISH_REJECTION only: n={len(b_is_trades)}  pnl={sum(t.dollar_pnl for t in b_is_trades):+,.0f}")
    emit(f"OOS total: n={len(base_oos.trades)}  pnl={sum(t.dollar_pnl for t in base_oos.trades):+,.0f}")
    emit(f"    BEARISH_REJECTION only: n={len(b_oos_trades)}  pnl={sum(t.dollar_pnl for t in b_oos_trades):+,.0f}")
    emit()

    # Classify trades by entry bar body
    emit("Classifying entry bar body direction...")
    def classify_group(trades, label):
        unknown = 0
        bear = []
        bull = []
        for t in trades:
            cls, bar = classify_body(t, bar_idx)
            if cls == "BEAR_BODY":
                bear.append(t)
            elif cls == "BULL_BODY":
                bull.append(t)
            else:
                unknown += 1
        total = len(bear) + len(bull) + unknown
        bear_pnl = sum(t.dollar_pnl for t in bear)
        bull_pnl = sum(t.dollar_pnl for t in bull)
        bear_wr = sum(1 for t in bear if t.dollar_pnl > 0) / len(bear) * 100 if bear else 0
        bull_wr = sum(1 for t in bull if t.dollar_pnl > 0) / len(bull) * 100 if bull else 0
        emit(f"{label} ({total} trades, unknown={unknown}):")
        emit(f"  BEAR_BODY: n={len(bear):>4}  pnl={bear_pnl:>+9,.0f}  WR={bear_wr:.0f}%  avg={bear_pnl/len(bear):>+7.0f}/t" if bear else "  BEAR_BODY: n=0")
        emit(f"  BULL_BODY: n={len(bull):>4}  pnl={bull_pnl:>+9,.0f}  WR={bull_wr:.0f}%  avg={bull_pnl/len(bull):>+7.0f}/t" if bull else "  BULL_BODY: n=0")
        return bear, bull, unknown

    is_bear, is_bull, is_unk = classify_group(b_is_trades,  "IS BEARISH_REJECTION")
    emit()
    oos_bear, oos_bull, oos_unk = classify_group(b_oos_trades, "OOS BEARISH_REJECTION")
    emit()

    # Gate impact: skip bull-body trades
    emit("--- Gate impact: skip BULL_BODY entries ---")
    # gate removes bull-body trades: IS_delta = -1 × IS_bull_pnl (we're removing these losers)
    is_bull_pnl  = sum(t.dollar_pnl for t in is_bull)
    oos_bull_pnl = sum(t.dollar_pnl for t in oos_bull)
    base_is_total  = sum(t.dollar_pnl for t in base_is.trades)
    base_oos_total = sum(t.dollar_pnl for t in base_oos.trades)

    is_d  = -is_bull_pnl   # removing bull-body trades from IS
    oos_d = -oos_bull_pnl  # removing bull-body trades from OOS

    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    wf = wf_norm(oos_d, n_oos, is_d, n_is)
    wf_s = f"{wf:.3f}" if wf == wf else "nan"

    emit(f"  IS  baseline pnl={base_is_total:+,.0f}  bull_body_pnl={is_bull_pnl:+,.0f}")
    emit(f"  IS  gated pnl={base_is_total + is_d:+,.0f}  delta={is_d:+,.0f}  (removing {len(is_bull)} bull-body IS trades)")
    emit(f"  OOS baseline pnl={base_oos_total:+,.0f}  bull_body_pnl={oos_bull_pnl:+,.0f}")
    emit(f"  OOS gated pnl={base_oos_total + oos_d:+,.0f}  delta={oos_d:+,.0f}  (removing {len(oos_bull)} bull-body OOS trades)")
    emit(f"  WF = (oos_d/n_oos)/(is_d/n_is) = {wf_s}")
    emit()

    # Sub-window analysis
    emit("--- Sub-window analysis ---")
    sw_results = {}
    sw_hurt = 0
    for wname, ws, we in SUBWINDOWS:
        sw_r = run_window(spy, vix, ws, we, **SAFE_PARAMS)
        sw_bear_r = [t for t in sw_r.trades if "BEARISH_REJECTION" in t.setup]
        sw_bull = [t for t in sw_bear_r if classify_body(t, bar_idx)[0] == "BULL_BODY"]
        sw_bull_pnl = sum(t.dollar_pnl for t in sw_bull)
        sw_d = -sw_bull_pnl  # removing bull-body trades
        tag = "HELP" if sw_d > 50 else ("HURT" if sw_d < -50 else "FLAT")
        if tag == "HURT":
            sw_hurt += 1
        sw_results[wname] = (len(sw_bull), sw_bull_pnl, sw_d, tag)
        emit(f"  {wname}: n_bull={len(sw_bull)}  bull_pnl={sw_bull_pnl:+,.0f}  gate_d={sw_d:+,.0f}  -> {tag}")

    emit()
    emit("--- Anchor check ---")
    ANCHOR_DAYS = {
        "4/29 (J winner)": "2026-04-29",
        "5/01 (J winner)": "2026-05-01",
        "5/04 (J winner)": "2026-05-04",
        "5/05 (J loser)":  "2026-05-05",
        "5/06 (J loser)":  "2026-05-06",
        "5/07 (J loser)":  "2026-05-07",
    }
    anchor_trades = {t.entry_time_et.date().isoformat(): t for t in b_is_trades}
    for label, date in ANCHOR_DAYS.items():
        t = anchor_trades.get(date)
        if t:
            cls, bar = classify_body(t, bar_idx)
            keep = "KEEP" if cls == "BEAR_BODY" else "SKIP (BULL_BODY)"
            emit(f"  {label}: pnl={t.dollar_pnl:+,.0f}  entry_bar={cls}  gate -> {keep}")
        else:
            emit(f"  {label}: no IS trade on this date")

    emit()
    emit("=" * 70)
    emit("VERDICT")
    emit("=" * 70)

    oos_pos = oos_d > 0
    wf_ok   = wf == wf and wf >= 0.70
    sw_ok   = sw_hurt <= 1

    if oos_pos and wf_ok and sw_ok:
        verdict = "RATIFIABLE: OOS_pos AND WF>=0.70 AND SW_hurt<=1"
    else:
        reasons = []
        if not oos_pos:
            reasons.append(f"OOS_NEG (oos_d={oos_d:+,.0f})")
        if not wf_ok:
            reasons.append(f"WF_FAIL ({wf_s})")
        if not sw_ok:
            reasons.append(f"SW_FAIL (hurt={sw_hurt})")
        verdict = "REJECT: " + " | ".join(reasons)

    emit(f"  OOS_pos: {oos_pos} (oos_d={oos_d:+,.0f})")
    emit(f"  WF: {wf_s} (gate: >=0.70): {wf_ok}")
    emit(f"  SW_hurt: {sw_hurt}/4 (gate: <=1): {sw_ok}")
    emit(f"  SW details: {' | '.join(f'{k}:{v[3]}({v[2]:+.0f})' for k, v in sw_results.items())}")
    emit()
    emit(f"  {verdict}")
    emit()

    # Additional: distribution of bull-body trades across time-of-day
    emit("--- Bull-body IS trades: entry time distribution ---")
    from collections import Counter
    hour_counter = Counter(t.entry_time_et.strftime("%H:xx") for t in is_bull)
    for h, n in sorted(hour_counter.items()):
        emit(f"  {h}: n={n}")

    emit()
    emit("DONE.")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
