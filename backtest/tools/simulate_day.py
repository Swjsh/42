"""Walk the heartbeat logic through a full trading day, candle by candle.

Shows what the engine SEES at each 5-min bar:
  - Filter score (1-10) + blockers
  - Triggers fired (level_reject, ribbon_flip, confluence, sequence_rejection)
  - Ribbon state (Fast/Pivot/Slow stack + spread)
  - Volume ratio vs 20-bar avg
  - Candle pattern (hammer / shooting_star / marubozu / doji / red / green)
  - HTF 15m stack
  - Whether ENTRY fires; if yes, plays out the v8 exit logic to EOD

Run on multiple days to validate the engine fires on right setups + skips chop.

Usage:
    python tools/simulate_day.py 2026-05-04
    python tools/simulate_day.py 2026-05-07         # today
    python tools/simulate_day.py --all-recent       # 6 days
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.orchestrator import run_backtest  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "data"


# ── Candle classifier (matches simulator_real conventions) ─────────────────

def classify_candle(o: float, h: float, l: float, c: float) -> str:
    rng = h - l
    if rng <= 0:
        return "flat"
    body = abs(c - o) / rng
    upper = (h - max(o, c)) / rng
    lower = (min(o, c) - l) / rng
    is_red = c < o
    is_green = c > o
    if body < 0.10:
        return "doji"
    if body >= 0.75 and upper <= 0.10 and lower <= 0.10:
        return "BEAR_marubozu" if is_red else "BULL_marubozu"
    if upper >= 0.50 and lower <= 0.20 and body <= 0.30:
        return "shooting_star" if is_red else "inv_hammer"
    if lower >= 0.50 and upper <= 0.20 and body <= 0.30:
        return "hammer" if is_green else "hanging_man"
    return "red" if is_red else "green"


# ── Day simulator ──────────────────────────────────────────────────────────

def simulate(date_str: str, verbose: bool = True):
    """Run heartbeat-equivalent logic on a single day. Show detailed timeline."""
    target = dt.date.fromisoformat(date_str)

    # Load master SPY + VIX data covering the target date
    master_spy = DATA_DIR / "spy_5m_2026-03-15_2026-05-07.csv"
    master_vix = DATA_DIR / "vix_5m_2026-03-15_2026-05-07.csv"
    if not master_spy.exists() or not master_vix.exists():
        print(f"Missing master data files at {DATA_DIR}/")
        return None

    spy = pd.read_csv(master_spy)
    vix = pd.read_csv(master_vix)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"])

    # Run the full orchestrator on just the target date (it handles warmup)
    # use_real_fills=True so we use the cached OPRA option bars when available
    result = run_backtest(
        spy, vix,
        start_date=target, end_date=target,
        use_real_fills=True,
    )

    decisions = result.decisions
    trades = result.trades

    if not decisions:
        print(f"\nNo decisions for {date_str} — likely outside data window.")
        return result

    # Header
    print("\n" + "=" * 110)
    print(f"  DAY-BY-DAY SIMULATION  ::  {date_str}  ({len(decisions)} bars evaluated)")
    print("=" * 110)

    # Build SPY RTH lookup for candle classification
    spy_rth = spy[
        (spy["timestamp_et"].dt.date == target)
        & (spy["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)

    # Compute volume baseline (20-bar) per bar
    spy_rth["vol_avg20"] = spy_rth["volume"].rolling(20, min_periods=5).mean()

    # Print timeline
    if verbose:
        print(f"  {'TIME':<6} {'SPY':<8} {'CANDLE':<14} {'VOL':<6} {'V/20':<6} "
              f"{'STACK':<5} {'SPRD':<5} {'HTF':<5} {'SCORE':<6} {'TRIGGERS':<24} "
              f"{'EVENT'}")
        print("  " + "-" * 105)

        # Map decisions to spy_rth bars
        d_by_ts = {pd.Timestamp(d["timestamp_et"]): d for d in decisions}

        entry_fired_at = None
        for _, row in spy_rth.iterrows():
            ts = row["timestamp_et"]
            t_str = ts.strftime("%H:%M")
            spy_close = row["close"]
            vol = int(row["volume"])
            v20 = row["vol_avg20"]
            v_ratio = (vol / v20) if v20 and v20 > 0 else 0
            cand = classify_candle(row["open"], row["high"], row["low"], row["close"])

            d = d_by_ts.get(ts)
            if d is None:
                # Bar before the first decision (not yet 09:35) — skip
                continue

            stack = d["ribbon_stack"][:4]
            spread = f"{d['ribbon_spread_cents']:.0f}c"
            htf = (d["htf_15m_stack"] or "—")[:4]
            score = f"{d['bear_score']}/10"
            triggers = "+".join(d["triggers_fired"]) if d["triggers_fired"] else "—"

            event = ""
            if d["passed"]:
                event = ">>> ENTRY"
                entry_fired_at = ts
            elif d["bear_score"] >= 8:
                blocked = "+".join(map(str, d["blockers"]))
                event = f"near-miss (blocked: {blocked})"

            print(
                f"  {t_str:<6} {spy_close:<8.2f} {cand:<14} {vol:<6,} {v_ratio:<5.1f}x "
                f"{stack:<5} {spread:<5} {htf:<5} {score:<6} {triggers[:22]:<24} {event}"
            )

    # Trade outcomes
    print()
    if trades:
        print(f"  ENGINE FIRED {len(trades)} TRADE(S):")
        for t in trades:
            entry_t = pd.Timestamp(t.entry_time_et).strftime("%H:%M")
            exit_t = pd.Timestamp(t.runner_exit_time_et).strftime("%H:%M") if t.runner_exit_time_et else "—"
            tp1_t = pd.Timestamp(t.tp1_time_et).strftime("%H:%M") if t.tp1_time_et else "—"
            tp1_p = f"${t.tp1_premium:.2f}" if t.tp1_premium else "—"
            exit_p = f"${t.runner_exit_premium:.2f}" if t.runner_exit_premium else "—"
            sign = "+" if t.dollar_pnl >= 0 else ""
            print(
                f"    {entry_t} BEARISH @ ${t.entry_premium:.2f} (strike {t.strike}P, "
                f"reject {t.rejection_level:.2f})\n"
                f"      TP1: {tp1_t} {tp1_p}  EXIT: {exit_t} {exit_p}  "
                f"PnL ${sign}{int(t.dollar_pnl)} ({t.exit_reason.value if t.exit_reason else 'n/a'})"
            )
    else:
        # Show why nothing fired — top blockers across the day
        from collections import Counter
        bc = Counter()
        for d in decisions:
            if d["bear_score"] >= 5:  # don't count noise bars
                for b in d["blockers"]:
                    bc[b] += 1
        if bc:
            top = ", ".join(f"f{f}({n}x)" for f, n in bc.most_common(5))
            print(f"  ENGINE DID NOT FIRE.  Top blockers across day: {top}")
            high_score_bars = sum(1 for d in decisions if d["bear_score"] >= 8)
            if high_score_bars:
                print(f"  {high_score_bars} bars hit score 8+ but were blocked.")
        else:
            print(f"  ENGINE DID NOT FIRE — no high-score bars at all today.")

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", help="Date YYYY-MM-DD")
    ap.add_argument("--all-recent", action="store_true",
                    help="Run on 4/29, 5/1, 5/4, 5/5, 5/6, 5/7")
    ap.add_argument("--quiet", action="store_true",
                    help="Skip the per-bar timeline; just show summary")
    args = ap.parse_args()

    if args.all_recent:
        days = ["2026-04-29", "2026-05-01", "2026-05-04",
                "2026-05-05", "2026-05-06", "2026-05-07"]
    elif args.date:
        days = [args.date]
    else:
        ap.print_help()
        return 1

    for d in days:
        simulate(d, verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
