"""SNIPER shadow watcher -- EOD retroactive signal logger.

PURPOSE
-------
Build J's OP-16 SNIPER anchor dataset by retroactively logging
SNIPER_LEVEL_BREAK signals for each trading day where the VIX-trend
condition was active.

J reviews journal/sniper-shadow-trades.jsonl each morning in premarket.
After confirming 3+ live SNIPER signals, the OP-16 anchor set is built
and SNIPER_VIX_TREND can be ratified (leaderboard #14, WF=0.983).

VIX-TREND CONDITION (2026-05-24-sniper-vix-trend-oos-confirmed.md):
    prior_day_VIX >= 18  AND  prior_day_VIX > prior_5d_avg_VIX

COMBO (recommended off=2, OOS WF=0.983):
    strike_offset=2, premium_stop_pct=-0.10, tp1_premium_pct=0.50,
    runner_target_pct=1.25, profit_lock=0.05/0.08, qty=10

OUTPUT
------
journal/sniper-shadow-trades.jsonl  (append-only)
  One JSON line per trading day where VIX condition was active, showing
  whether a SNIPER signal fired and the simulated outcome.

SCHEDULED
---------
RETIRED 2026-06-19. The `Gamma_SniperShadowEOD` task was unregistered from Windows
Task Scheduler (SNIPER strategy never promoted; watcher-fleet de-sprawl). This
worker is left in place per project convention but is ORPHANED -- no scheduled task
or PS1 wrapper invokes it. It imports only KEPT modules (lib.sniper_detector et al.),
so it still runs if invoked manually for ad-hoc SNIPER shadow backfill.
Each run processes only days not already in the log (idempotent).

CLI
---
  python automation/scripts/sniper_shadow_eod.py             # last 30 days
  python automation/scripts/sniper_shadow_eod.py --days 90   # last 90 days
  python automation/scripts/sniper_shadow_eod.py --date 2026-05-22  # one day
  python automation/scripts/sniper_shadow_eod.py --all       # full history (2025-01-01+)
  python automation/scripts/sniper_shadow_eod.py --dry-run   # no writes, just print

Per CLAUDE.md OP-22 ENGINE-BENEFIT AUTONOMY: this script is data-collection
infrastructure; it does NOT modify heartbeat.md or params*.json and NEVER
places orders.
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Optional

import pandas as pd
import pytz

REPO = Path(__file__).resolve().parent.parent.parent  # automation/scripts -> automation -> repo root
sys.path.insert(0, str(REPO / "backtest"))

from autoresearch import runner as _runner  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.sniper_detector import (  # noqa: E402
    SniperParams,
    compute_levels,
    detect_sniper_break,
)

# ---------------------------------------------------------------------------
# Config: VIX condition + recommended off=2 combo (OOS WF=0.983)
# ---------------------------------------------------------------------------

VIX_LOWER: float = 18.0
VIX_TREND_WINDOW: int = 5  # trading days (= 1 calendar week, uniquely optimal)

COMBO: dict = {
    "strike_offset": 2,
    "premium_stop_pct": -0.10,
    "tp1_premium_pct": 0.50,
    "runner_target_pct": 1.25,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.08,
    "qty": 10,
}

SNIPER_PARAMS = SniperParams(
    vol_mult=1.1,
    body_min_cents=0.02,
    min_stars=2,
    proximity_dollars=1.5,
    no_trade_before=dt.time(9, 30),
    no_trade_after=dt.time(15, 50),
    require_break_above_open=True,
)

# Latest master CSV coverage -- update when data is extended
DATA_START = dt.date(2025, 1, 1)
DATA_END = dt.date(2026, 5, 22)

OUT = REPO / "journal" / "sniper-shadow-trades.jsonl"
TZ_ET = pytz.timezone("US/Eastern")


# ---------------------------------------------------------------------------
# VIX maps
# ---------------------------------------------------------------------------


def _build_vix_maps(
    vix_df: pd.DataFrame,
    trade_dates: list[dt.date],
) -> tuple[dict[dt.date, float], dict[dt.date, float]]:
    """Return (prior_close_map, prior_5d_avg_map) for each trade date."""
    vix_by_date: dict[dt.date, float] = (
        vix_df.groupby(vix_df["timestamp_et"].dt.date)["close"]
        .last()
        .to_dict()
    )
    sorted_days = sorted(vix_by_date.keys())
    sorted_vals = [vix_by_date[d] for d in sorted_days]

    prior_close: dict[dt.date, float] = {}
    prior_avg: dict[dt.date, float] = {}

    for trade_date in trade_dates:
        idx = bisect.bisect_left(sorted_days, trade_date) - 1
        if idx < 0:
            prior_close[trade_date] = 15.0
            prior_avg[trade_date] = 15.0
            continue
        prior_close[trade_date] = float(sorted_vals[idx])
        start_idx = max(0, idx - VIX_TREND_WINDOW + 1)
        window_vals = sorted_vals[start_idx : idx + 1]
        prior_avg[trade_date] = float(mean(window_vals)) if window_vals else 15.0

    return prior_close, prior_avg


# ---------------------------------------------------------------------------
# Per-day SNIPER detection + simulation
# ---------------------------------------------------------------------------


def _process_day(
    trade_date: dt.date,
    spy_full: pd.DataFrame,
    prior_close_map: dict[dt.date, float],
    prior_avg_map: dict[dt.date, float],
) -> dict:
    """Return a log entry dict for one trading day."""
    vix_prev = prior_close_map.get(trade_date, 15.0)
    vix_5d = prior_avg_map.get(trade_date, 15.0)

    entry: dict = {
        "date": str(trade_date),
        "vix_prev": round(vix_prev, 2),
        "vix_5d_avg": round(vix_5d, 2),
        "vix_condition": "LOW_VIX",
        "signal_found": False,
        "signal_time": None,
        "signal_direction": None,
        "level_label": None,
        "level_price": None,
        "entry_price": None,
        "strike": None,
        "simulated_pnl": None,
        "simulated_outcome": None,
        "j_anchor": False,
        "j_confirmed": None,
        "j_notes": None,
        "run_at": dt.datetime.now().isoformat(),
    }

    # VIX condition check
    if vix_prev < VIX_LOWER:
        entry["vix_condition"] = "LOW_VIX"
        return entry  # Not a SNIPER day
    if vix_prev <= vix_5d:
        entry["vix_condition"] = "DECLINING"
        return entry  # Spike-and-revert; skip

    entry["vix_condition"] = "ESCALATING"

    # Get day's intraday bars
    day_bars = spy_full[
        (spy_full["timestamp_et"].dt.date == trade_date)
        & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)

    if day_bars.empty:
        return entry

    # Get pre-market context bars (for level computation + ribbon warmup)
    first_ts = day_bars["timestamp_et"].iloc[0]
    pre_bars = spy_full[spy_full["timestamp_et"] < first_ts].tail(80).reset_index(drop=True)
    combined = pd.concat([pre_bars, day_bars], ignore_index=True)
    day_offset = len(pre_bars)

    # Compute levels
    levels = compute_levels(spy_full, first_ts, SNIPER_PARAMS)
    if not levels:
        return entry

    # Compute ribbon on combined bars
    ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)

    # Walk bars, fire on first valid signal (short only -- VIX escalating = bear)
    for i in range(len(day_bars)):
        bar_idx = day_offset + i
        bar = combined.iloc[bar_idx]
        signal = detect_sniper_break(bar, bar_idx, combined, levels, SNIPER_PARAMS)
        if signal is None or signal.direction != "short":
            continue

        entry_spot = float(signal.entry_price)
        strike = round(entry_spot) + COMBO["strike_offset"]

        # Simulate trade
        fill = simulate_trade_real(
            entry_bar_idx=bar_idx,
            entry_bar=bar,
            spy_df=combined,
            ribbon_df=ribbon_df,
            rejection_level=signal.level.price,
            triggers_fired=["sniper_level_break"],
            side="P",
            qty=COMBO["qty"],
            setup="SNIPER_LEVEL_BREAK",
            levels_active=[lv.price for lv in levels if lv.tier == "Active"],
            levels_carry=[lv.price for lv in levels if lv.tier == "Carry"],
            use_tiered_exits=True,
            strike_override=int(strike),
            premium_stop_pct=COMBO["premium_stop_pct"],
            profit_lock_threshold_pct=COMBO["profit_lock_threshold_pct"],
            profit_lock_stop_offset_pct=COMBO["profit_lock_stop_offset_pct"],
        )

        entry["signal_found"] = True
        entry["signal_time"] = str(signal.bar_timestamp_et)
        entry["signal_direction"] = signal.direction
        entry["level_label"] = signal.level.label
        entry["level_price"] = round(signal.level.price, 2)
        entry["entry_price"] = round(entry_spot, 2)
        entry["strike"] = int(strike)

        if fill is not None:
            pnl = float(fill.dollar_pnl or 0.0)
            entry["simulated_pnl"] = round(pnl, 2)
            entry["simulated_outcome"] = "winner" if pnl > 0 else "loser"
        else:
            entry["simulated_pnl"] = None
            entry["simulated_outcome"] = "no_fill"

        break  # One trade per day

    return entry


# ---------------------------------------------------------------------------
# Already-logged dates (idempotency)
# ---------------------------------------------------------------------------


def _load_logged_dates() -> set[str]:
    """Return set of date strings already in the log."""
    if not OUT.exists():
        return set()
    logged: set[str] = set()
    for line in OUT.read_text(encoding="utf-8").strip().splitlines():
        try:
            obj = json.loads(line)
            if obj.get("date"):
                logged.add(obj["date"])
        except json.JSONDecodeError:
            pass
    return logged


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------


def _print_summary(entries: list[dict]) -> None:
    active = [e for e in entries if e["vix_condition"] == "ESCALATING"]
    signals = [e for e in active if e["signal_found"]]
    winners = [e for e in signals if e.get("simulated_outcome") == "winner"]
    losers = [e for e in signals if e.get("simulated_outcome") == "loser"]

    print()
    print("=" * 72)
    print("SNIPER SHADOW LOG -- EOD Summary")
    print("=" * 72)
    print(f"  Days scanned       : {len(entries)}")
    print(f"  VIX escalating days: {len(active)}")
    print(f"  SNIPER signals     : {len(signals)}")
    print(f"  Winners / Losers   : {len(winners)} / {len(losers)}")
    filled = [e for e in signals if e.get("simulated_outcome") in ("winner", "loser")]
    no_fills = [e for e in signals if e.get("simulated_outcome") == "no_fill"]
    if signals:
        wr = len(winners) / len(filled) if filled else 0.0
        total_pnl = sum(e.get("simulated_pnl") or 0 for e in signals)
        print(f"  No-fill days       : {len(no_fills)} (OPRA data gaps)")
        print(f"  Win rate (filled)  : {wr:.1%}  [{len(winners)}W / {len(losers)}L]")
        print(f"  Simulated P&L      : ${total_pnl:,.0f}")
    print()

    if active:
        print(f"  {'Date':<12} {'VIX':>5} {'5dAvg':>6} {'Signal':^8} {'Level':<18} {'Strike':>7} {'P&L':>8} {'Outcome'}")
        print("  " + "-" * 68)
        for e in active:
            sig = "YES" if e["signal_found"] else "no"
            lbl = e.get("level_label") or "-"
            strike = str(e.get("strike") or "-")
            pnl = f"${e['simulated_pnl']:+,.0f}" if e.get("simulated_pnl") is not None else "-"
            outcome = e.get("simulated_outcome") or "-"
            print(
                f"  {e['date']:<12} {e['vix_prev']:>5.1f} {e['vix_5d_avg']:>6.1f}"
                f"  {sig:^8} {lbl:<18} {strike:>7} {pnl:>8}  {outcome}"
            )

    print()
    print(f"  Log file: {OUT}")
    print(f"  OP-16 status: {len(signals)}/3 SNIPER signals logged")
    if len(signals) >= 3:
        print("  ** OP-16 threshold met -- J can now build anchor set from log **")
    else:
        remaining = 3 - len(signals)
        print(f"  ** Need {remaining} more VIX-escalating SNIPER signal days for OP-16 **")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="SNIPER shadow EOD watcher")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, default=30,
                       help="Scan the last N trading days (default 30)")
    group.add_argument("--date", type=str,
                       help="Process a specific date YYYY-MM-DD")
    group.add_argument("--all", action="store_true",
                       help="Process full history from DATA_START")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results without writing to log")
    args = parser.parse_args()

    print(f"SNIPER Shadow EOD Watcher -- {dt.datetime.now():%Y-%m-%d %H:%M}")
    print(f"VIX condition: VIX >= {VIX_LOWER} AND VIX > {VIX_TREND_WINDOW}d_avg")
    print(f"Combo: off={COMBO['strike_offset']} stp={COMBO['premium_stop_pct']} "
          f"tp1={COMBO['tp1_premium_pct']} run={COMBO['runner_target_pct']} qty={COMBO['qty']}")

    # Determine date range
    if args.date:
        try:
            target = dt.date.fromisoformat(args.date)
        except ValueError:
            print(f"ERROR: invalid date '{args.date}', expected YYYY-MM-DD")
            sys.exit(1)
        scan_start = target
        scan_end = target
    elif args.all:
        scan_start = DATA_START
        scan_end = DATA_END
    else:
        scan_end = DATA_END
        scan_start = scan_end - dt.timedelta(days=args.days * 2)  # over-estimate to get N trading days

    print(f"\nLoading SPY + VIX data ({DATA_START} .. {DATA_END})...", end=" ", flush=True)
    spy_full, vix_full = _runner.load_data(DATA_START, DATA_END)
    for df in (spy_full, vix_full):
        df["timestamp_et"] = (
            pd.to_datetime(df["timestamp_et"], utc=True)
            .dt.tz_convert(TZ_ET)
            .dt.tz_localize(None)
        )
    print("done")

    # All available trading dates
    all_dates = sorted(set(spy_full["timestamp_et"].dt.date.unique()))
    trade_dates = [d for d in all_dates if d >= DATA_START and d <= DATA_END]

    # Build VIX maps for all dates (O(n log n))
    print("Building VIX maps...", end=" ", flush=True)
    prior_close_map, prior_avg_map = _build_vix_maps(vix_full, trade_dates)
    print("done")

    # Filter to scan window
    if args.date:
        scan_dates = [d for d in trade_dates if d == target]
    else:
        scan_dates = [d for d in trade_dates if d >= scan_start and d <= scan_end]
        if not args.all:
            # Trim to last --days trading days
            scan_dates = scan_dates[-args.days:]

    print(f"Scanning {len(scan_dates)} trading days ({scan_dates[0] if scan_dates else 'none'} .. {scan_dates[-1] if scan_dates else 'none'})")

    # Idempotency: skip already-logged dates
    logged_dates = _load_logged_dates()
    to_process = [d for d in scan_dates if str(d) not in logged_dates]
    skipped = len(scan_dates) - len(to_process)
    if skipped:
        print(f"  Skipping {skipped} already-logged dates")
    if not to_process:
        print("  Nothing new to process")
        _print_summary(_load_all_entries(scan_dates))
        return

    print(f"  Processing {len(to_process)} new dates...")

    # Process each day
    new_entries: list[dict] = []
    for trade_date in to_process:
        entry = _process_day(trade_date, spy_full, prior_close_map, prior_avg_map)
        new_entries.append(entry)
        cond = entry["vix_condition"]
        sig = "SIGNAL" if entry["signal_found"] else "no-signal"
        pnl_str = ""
        if entry.get("simulated_pnl") is not None:
            pnl_str = f" ${entry['simulated_pnl']:+,.0f}"
        print(f"  {trade_date}  {cond:<10} {sig}{pnl_str}")

    # Write to log
    if not args.dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as f:
            for entry in new_entries:
                f.write(json.dumps(entry) + "\n")
        print(f"\n  Appended {len(new_entries)} entries to {OUT}")
    else:
        print(f"\n  [dry-run] would append {len(new_entries)} entries")

    # Summary over scan window (including already-logged + newly processed)
    all_scan_entries = _load_all_entries(scan_dates) if not args.dry_run else new_entries
    _print_summary(all_scan_entries)


def _load_all_entries(scan_dates: list[dt.date]) -> list[dict]:
    """Load all log entries whose date is in scan_dates."""
    if not OUT.exists():
        return []
    scan_set = {str(d) for d in scan_dates}
    entries: list[dict] = []
    for line in OUT.read_text(encoding="utf-8").strip().splitlines():
        try:
            obj = json.loads(line)
            if obj.get("date") in scan_set:
                entries.append(obj)
        except json.JSONDecodeError:
            pass
    return entries


if __name__ == "__main__":
    main()
