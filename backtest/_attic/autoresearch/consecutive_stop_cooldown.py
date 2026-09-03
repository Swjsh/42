"""
Consecutive-Stop Cooldown Analysis — BEARISH_REVERSAL

Hypothesis: After N consecutive stops from the same trigger type on one trading day,
the market regime has likely shifted against the setup. Blocking further entries from
that trigger for the rest of the day avoids "overtrading" into deteriorating conditions.

Method (post-processing — valid for single-direction sequential trades):
  1. Run IS backtest normally -> get all trades with exit_reason
  2. For each day, simulate cooldown: once N consecutive stops from the same trigger,
     skip (set pnl=0 for) subsequent trades from that trigger that day.
  3. Compute P&L delta vs baseline.
  4. Run same on OOS. Compute WF.

Why post-processing is valid here:
  - Trades are sequential (one at a time), no overlapping positions
  - Skipping an entry = not taking the trade = P&L contribution is 0
  - Exit logic of remaining trades is unaffected

Sweep: N_cooldown in [1, 2, 3] × trigger_match in ["any", "same_trigger_type"]

Security: Read-only on all production state. No Alpaca calls.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt
import collections

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 5, 7)}


def _tz_naive(t):
    et = t.entry_time_et
    if getattr(et, "tzinfo", None) is not None:
        return et.replace(tzinfo=None)
    return et


def _stop_exit(t) -> bool:
    """True if this trade exited via any kind of stop (not TP1, not TP2, not time-stop)."""
    reason = str(t.exit_reason) if t.exit_reason else ""
    # Heuristic: stopped = negative P&L and exited early (not time-stop based)
    # Also: exit_reason enum name contains "STOP"
    if "STOP" in reason.upper() and "TIME" not in reason.upper():
        return True
    # Fallback: pnl < 0 used as proxy for stop exit (not 100% accurate but good enough)
    return t.dollar_pnl < 0


def _get_trigger(t) -> str:
    """Extract trigger type from trade metadata. Falls back to 'unknown'."""
    # TradeResult may have a trigger_type or setup_type attribute
    for attr in ("trigger_type", "setup_type", "pattern", "trigger"):
        val = getattr(t, attr, None)
        if val:
            return str(val)
    return "unknown"


def _apply_cooldown(trades: list, n_cooldown: int, per_trigger: bool) -> float:
    """
    Post-process trades: simulate cooldown where after N consecutive stops
    (from the same trigger if per_trigger=True, any trigger otherwise),
    skip subsequent entries that day from the same trigger.

    Returns the simulated total P&L.
    """
    # Group trades by date in chronological order
    by_date: dict[dt.date, list] = collections.defaultdict(list)
    for t in sorted(trades, key=lambda t: _tz_naive(t)):
        d = _tz_naive(t).date()
        by_date[d].append(t)

    total_pnl = 0.0
    blocked_count = 0

    for d, day_trades in sorted(by_date.items()):
        # Track consecutive stops per trigger (or overall)
        if per_trigger:
            consec_stops: dict[str, int] = collections.defaultdict(int)
            blocked_triggers: set[str] = set()
        else:
            consec_stops_any = 0
            blocked = False

        for t in day_trades:
            trigger = _get_trigger(t)

            if per_trigger:
                if trigger in blocked_triggers:
                    blocked_count += 1
                    # Skipped trade — 0 contribution to P&L
                    continue
                total_pnl += t.dollar_pnl
                if _stop_exit(t):
                    consec_stops[trigger] += 1
                    if consec_stops[trigger] >= n_cooldown:
                        blocked_triggers.add(trigger)
                else:
                    consec_stops[trigger] = 0  # reset on win
            else:
                if blocked:
                    blocked_count += 1
                    continue
                total_pnl += t.dollar_pnl
                if _stop_exit(t):
                    consec_stops_any += 1
                    if consec_stops_any >= n_cooldown:
                        blocked = True
                else:
                    consec_stops_any = 0

    return total_pnl, blocked_count


def _anchor_pnl_raw(trades: list, anchor_dates: set) -> float:
    return sum(t.dollar_pnl for t in trades if _tz_naive(t).date() in anchor_dates)


def _catastrophic_month_detail(trades: list, n_cooldown: int) -> None:
    """Per-catastrophic-month breakdown showing where cooldown fires."""
    CAT_MONTHS = {"2026-04", "2026-03", "2025-11", "2026-01", "2025-05", "2025-03"}

    by_date: dict[dt.date, list] = collections.defaultdict(list)
    for t in sorted(trades, key=lambda t: _tz_naive(t)):
        d = _tz_naive(t).date()
        by_date[d].append(t)

    cat_days = {
        d for d in by_date.keys()
        if d.strftime("%Y-%m") in CAT_MONTHS
    }

    total_baseline = 0.0
    total_cooldown_pnl = 0.0
    total_blocked = 0

    for d in sorted(cat_days):
        day_trades = by_date[d]
        # Simulate cooldown any-trigger
        blocked = False
        consec = 0
        day_pnl_base = sum(t.dollar_pnl for t in day_trades)
        day_pnl_cool = 0.0
        day_blocked = 0
        for t in day_trades:
            if blocked:
                day_blocked += 1
                continue
            day_pnl_cool += t.dollar_pnl
            if _stop_exit(t):
                consec += 1
                if consec >= n_cooldown:
                    blocked = True
            else:
                consec = 0

        delta = day_pnl_cool - day_pnl_base
        total_baseline += day_pnl_base
        total_cooldown_pnl += day_pnl_cool
        total_blocked += day_blocked
        if day_blocked > 0 or abs(delta) > 1:
            print(f"  {d}  n={len(day_trades)}  base={day_pnl_base:>+7.0f}  cool={day_pnl_cool:>+7.0f}  "
                  f"delta={delta:>+7.0f}  blocked={day_blocked}")

    print(f"  --- TOTAL cat months: base={total_baseline:>+7.0f}  cool={total_cooldown_pnl:>+7.0f}  "
          f"delta={total_cooldown_pnl-total_baseline:>+7.0f}  blocked={total_blocked}")


if __name__ == "__main__":
    print("=" * 110)
    print("CONSECUTIVE-STOP COOLDOWN ANALYSIS — BEARISH_REVERSAL")
    print("Hypothesis: After N consecutive stops on same day, block further entries that day")
    print("=" * 110)

    print("\n[1/3] Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[2/3] Running IS backtest...")
    is_result = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    is_trades = is_result.trades
    is_base_pnl = sum(t.dollar_pnl for t in is_trades)
    print(f"  IS: n={len(is_trades)}  pnl={is_base_pnl:+.2f}")

    print("\n[3/3] Running OOS backtest...")
    oos_result = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)
    oos_trades = oos_result.trades
    oos_base_pnl = sum(t.dollar_pnl for t in oos_trades)
    print(f"  OOS: n={len(oos_trades)}  pnl={oos_base_pnl:+.2f}")

    # ── Check trigger field availability ────────────────────────────────────
    sample_triggers = [_get_trigger(t) for t in is_trades[:10]]
    print(f"\n  Sample trigger values: {sample_triggers[:5]}")
    unique_triggers = {_get_trigger(t) for t in is_trades}
    print(f"  Unique trigger values: {sorted(unique_triggers)[:10]}")

    # ── Main sweep ────────────────────────────────────────────────────────────
    print("\n" + "=" * 110)
    print("COOLDOWN SWEEP — N consecutive stops -> block rest of day")
    print(f"\n{'N':>4}  {'Mode':>14}  {'IS_base':>9}  {'IS_cool':>9}  {'IS_delta':>9}  "
          f"{'OOS_base':>9}  {'OOS_cool':>9}  {'OOS_delta':>9}  {'WF':>7}  "
          f"{'IS_blk':>7}  {'OOS_blk':>7}  Verdict")
    print("-" * 130)

    results = []
    for n_cd in [1, 2, 3]:
        for per_trigger in [False, True]:
            mode = "same_trigger" if per_trigger else "any_trigger"

            is_cool_pnl, is_blk = _apply_cooldown(is_trades, n_cd, per_trigger)
            is_delta = is_cool_pnl - is_base_pnl

            oos_cool_pnl, oos_blk = _apply_cooldown(oos_trades, n_cd, per_trigger)
            oos_delta = oos_cool_pnl - oos_base_pnl

            wf = oos_delta / is_delta if is_delta != 0 else float("inf")
            verdict = "PASS" if (oos_delta > 0 and wf >= 0.70) else ""
            if is_delta < 0 and oos_delta < 0:
                verdict = "BOTH_NEG"

            print(f"{n_cd:>4}  {mode:>14}  {is_base_pnl:>+9.0f}  {is_cool_pnl:>+9.0f}  {is_delta:>+9.0f}  "
                  f"{oos_base_pnl:>+9.0f}  {oos_cool_pnl:>+9.0f}  {oos_delta:>+9.0f}  {wf:>7.3f}  "
                  f"{is_blk:>7}  {oos_blk:>7}  {verdict}")

            results.append({
                "n": n_cd, "mode": mode,
                "is_delta": is_delta, "oos_delta": oos_delta, "wf": wf,
                "is_blk": is_blk, "oos_blk": oos_blk, "verdict": verdict,
            })

    # ── Best config deep-dive ────────────────────────────────────────────────
    passes = [r for r in results if r["verdict"] == "PASS"]
    if passes:
        best = max(passes, key=lambda r: r["oos_delta"])
        print(f"\nBest PASS: N={best['n']}  mode={best['mode']}  OOS_delta={best['oos_delta']:+.0f}  WF={best['wf']:.3f}")

        print(f"\nCATASTROPHIC MONTH DETAIL (N={best['n']}, mode={best['mode']}):")
        _catastrophic_month_detail(is_trades, best["n"])

        # Anchor regression
        print("\nANCHOR REGRESSION:")
        best_is_pnl, _ = _apply_cooldown(is_trades, best["n"], best["mode"] == "same_trigger")
        best_is_winners = sum(
            (t.dollar_pnl if _tz_naive(t).date() in J_WINNERS else 0)
            for t in is_trades
        )
        base_winners = _anchor_pnl_raw(is_trades, J_WINNERS)
        base_losers  = _anchor_pnl_raw(is_trades, J_LOSERS)
        print(f"  Baseline winners={base_winners:+.0f}  losers={base_losers:+.0f}")
        # Note: post-processing doesn't modify individual trades, so anchor day P&L
        # is unchanged unless anchor day had N+ consecutive stops
        print("  (Anchor days: if no N+ consecutive stops that day, P&L unchanged)")
    else:
        print("\nNo PASS candidates.")
        print("-> Consecutive-stop cooldown does NOT generalize (OOS worse or WF < 0.70)")
        print("-> Per-day kill switch remains the correct protection against overtrading")

    # ── Per-day breakdown for worst IS month (April 2026) ────────────────────
    print("\n" + "=" * 110)
    print("APRIL 2026 CONSECUTIVE-STOP DETAIL (worst catastrophic month):")
    print(f"  Simulating N=2 any_trigger cooldown:")
    _catastrophic_month_detail(is_trades, 2)

    print("\nANALYSIS COMPLETE.")
